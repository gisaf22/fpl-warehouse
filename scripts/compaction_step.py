"""The compaction step: select closed element-summary days and compact them (#198).

Runs before `dbt build` in the scheduled build, with continue-on-error, so it can
never change the build's outcome or the healthchecks.io ping. It:

1. reads `compaction.yml`: N (`max_days_per_run`) and the ingest job timeout;
2. with N = 0, stops there: no listing, no write (W12);
3. otherwise lists the run manifests and selects, oldest first and at most N,
   every day D that is
   - closed: past D+1 00:00 UTC + the timeout, with every run manifest under
     `raw/fpl/_manifests/D/` finalized (any status but IN_PROGRESS);
   - a candidate: its finalized manifests record an element-summary object
     written (O1). A day with none is skipped, not failed;
   - uncompacted: it has no compaction manifest under the destination;
4. compacts each with the #193 writer, and writes the W13 `compaction` object
   for build_metrics.py and a job summary naming compacted, failed, skipped
   and killed-run days.

A day that fails stays a candidate and takes one slot on every run; no failure
state is kept (O1). `--days` is the compaction_dry_run path (O2): those days go
straight to the writer, with no selection. A failed day exits 1; an unexpected
exception propagates. See docs/compacted.md.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import yaml

from compact_element_summary import (
    ENDPOINT,
    KEY_PREFIX,
    check_destination,
    compact_days,
    list_payloads,
    manifest_path,
)

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "compaction.yml"


@dataclass
class CompactionConfig:
    max_days_per_run: int
    ingest_job_timeout: timedelta


@dataclass
class Selection:
    days: list[str] = field(default_factory=list)
    skipped_empty: list[str] = field(default_factory=list)
    killed: list[str] = field(default_factory=list)


@dataclass
class StepResult:
    compaction: dict
    summary: str
    exit_code: int


def load_config(path: Path = CONFIG) -> CompactionConfig:
    config = yaml.safe_load(Path(path).read_text())
    return CompactionConfig(
        max_days_per_run=int(config["max_days_per_run"]),
        ingest_job_timeout=timedelta(hours=float(config["ingest_job_timeout_hours"])),
    )


def _connect(*roots: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    if any(r.startswith("s3://") for r in roots):
        con.sql("create secret (type s3, provider credential_chain, chain 'env')")
    return con


def list_run_manifests(raw_root: str) -> list[tuple[str, dict]]:
    """Every run manifest, as (the date folder it sits under, its contents)."""
    raw_root = raw_root.rstrip("/")
    con = _connect(raw_root)
    rows = con.execute(
        "select filename, content from read_text(?)",
        [f"{raw_root}/fpl/_manifests/*/*/manifest.json"],
    ).fetchall()
    return [(name.split("/")[-3], json.loads(content)) for name, content in rows]


def _compacted_days(dest_root: str) -> set[str]:
    con = _connect(dest_root)
    pattern = manifest_path(dest_root, "*")
    names = [r[0] for r in con.execute("select file from glob(?)", [pattern]).fetchall()]
    return {n.rsplit("date=", 1)[1].removesuffix(".json") for n in names}


def _writes_element_summary(manifest: dict) -> bool:
    objects = manifest.get("objects") or {}
    if any(
        k.startswith(f"{ENDPOINT}/") and (v or {}).get("written", 0) > 0
        for k, v in objects.items()
    ):
        return True
    return any(c["key"].startswith(KEY_PREFIX) for c in manifest.get("captures") or [])


def select_days(
    raw_root: str, dest_root: str, now: datetime, n: int, timeout: timedelta
) -> Selection:
    if n <= 0:
        return Selection()
    by_day: dict[str, list[dict]] = {}
    for day, manifest in list_run_manifests(raw_root):
        by_day.setdefault(day, []).append(manifest)
    compacted = _compacted_days(dest_root)

    selection = Selection()
    candidates = []
    for day in sorted(by_day):
        closes = datetime.combine(
            date.fromisoformat(day) + timedelta(days=1), datetime.min.time(), timezone.utc
        ) + timeout
        if now <= closes or day in compacted:
            continue
        manifests = by_day[day]
        if any(m.get("status") == "IN_PROGRESS" for m in manifests):
            selection.killed.append(day)
        elif any(_writes_element_summary(m) for m in manifests):
            candidates.append(day)
        else:
            selection.skipped_empty.append(day)
    selection.days = candidates[:n]
    return selection


def _peak_rss_mib() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports KiB, macOS bytes.
    return round(peak / 1024 / (1024 if sys.platform == "darwin" else 1), 1)


def _summary(days: list[dict], selection: Selection, n: int, dry_run: bool) -> str:
    failed = [d for d in days if not d["ok"]]
    title = "dry run" if dry_run else f"N = {n}"
    lines = [
        f"### Compaction (#198, {title}): {'**failed**' if failed else 'ok'}",
        "",
    ]
    if not days:
        lines.append("No days compacted.")
    for d in days:
        outcome = "compacted" if d["ok"] else f"**failed**: {d['reason']}"
        lines.append(
            f"- `{d['capture_day']}` {outcome} ({d['files_read']} files, "
            f"{d['rows_written']} rows, {d['seconds']:.1f}s)"
        )
    if failed:
        lines.append(
            "\nA failed day stays a candidate and takes one slot on every run until "
            "it is fixed (#198 O1)."
        )
    if selection.killed:
        lines.append(
            "\nOpen, a run manifest still `IN_PROGRESS` (killed run?): "
            + ", ".join(f"`{d}`" for d in selection.killed)
        )
    if selection.skipped_empty:
        lines.append(
            "\nSkipped, no element-summary captures: "
            + ", ".join(f"`{d}`" for d in selection.skipped_empty)
        )
    return "\n".join(lines) + "\n"


def run_step(
    raw_root: str,
    dest_root: str,
    now: datetime,
    n: int,
    timeout: timedelta,
    days: list[str] | None = None,
    out: Path | None = None,
    event_name: str | None = None,
) -> StepResult:
    started = time.monotonic()
    dry_run = days is not None
    if dry_run:
        selection = Selection(days=list(days))
    else:
        if n > 0:
            check_destination(dest_root, _event(event_name))
        selection = select_days(raw_root, dest_root, now, n, timeout)

    entries = []
    if selection.days:
        check_destination(dest_root, _event(event_name))
    listing = list_payloads(raw_root) if selection.days else {}
    for day in selection.days:
        day_started = time.monotonic()
        result = compact_days(
            [day], raw_root=raw_root, dest_root=dest_root, event_name=event_name,
            listing=listing,
        )[day]
        seconds = time.monotonic() - day_started
        # F4: flushed per day, so a killed run still shows the days it finished.
        print(
            f"compaction: day={day} files={result.files_read} "
            f"seconds={seconds:.1f} ok={result.ok}",
            flush=True,
        )
        entries.append({
            "capture_day": day,
            "ok": result.ok,
            "reason": result.reason,
            "seconds": round(seconds, 3),
            "files_read": result.files_read,
            "rows_written": result.rows_written,
        })

    compaction = {
        "n": n,
        "seconds": round(time.monotonic() - started, 3),
        "days_selected": len(selection.days),
        "days": entries,
        "peak_rss_mib": _peak_rss_mib(),
    }
    if out is not None:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(compaction, indent=2) + "\n")
    return StepResult(
        compaction=compaction,
        summary=_summary(entries, selection, n, dry_run),
        exit_code=1 if any(not e["ok"] for e in entries) else 0,
    )


def _event(event_name: str | None) -> str | None:
    return event_name if event_name is not None else os.environ.get("GITHUB_EVENT_NAME")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-root", required=True, help="e.g. s3://fpl-data-safari/raw")
    parser.add_argument("--dest-root", required=True)
    parser.add_argument("--out", type=Path, help="where build_metrics.py reads the object")
    parser.add_argument("--days", help="dry run: comma-separated YYYY-MM-DD, no selection")
    parser.add_argument("--summary", type=Path, help="appended to, e.g. $GITHUB_STEP_SUMMARY")
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()

    config = load_config(args.config)
    days = [d.strip() for d in args.days.split(",") if d.strip()] if args.days else None
    result = run_step(
        args.raw_root,
        args.dest_root,
        datetime.now(timezone.utc),
        config.max_days_per_run,
        config.ingest_job_timeout,
        days=days,
        out=args.out,
    )
    print(result.summary)
    if args.summary:
        with args.summary.open("a") as f:
            f.write(result.summary)
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
