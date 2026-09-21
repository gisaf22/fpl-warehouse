"""Re-key one archived season's raw capture into fpl-ingest's key layout.

A one-time port, not part of any build. The 2025-26 season was captured by the
pre-S3 fpl-ingest, which wrote a single overwritten snapshot per endpoint to
``~/.fpl/raw`` with no run identity in the path:

    bootstrap.json  fixtures.json  gw_{n}.json  players/{fpl_id}.json

That tree is backed up verbatim at s3://fpl-data-safari/archive/2025-26/raw/.
This script reads it and writes the same payloads under the layout the current
fpl-ingest uses and fpl-warehouse's staging models parse:

    {dest}/{season}/fpl/{endpoint}/{extraction_date}/{run_id}/payload.json
                                                             /metadata.json

WHY A SEPARATE ROOT, NOT raw/
-----------------------------
The destination is a history root (s3://fpl-data-safari/history/), never the
live raw/ prefix, for two independent reasons:

  1. fpl-warehouse's live sources glob raw/fpl/{endpoint}/*/*/payload.json.
     Objects written there would be read as 2026-27 data and stamped with the
     live season.

  2. fpl-ingest skips an endpoint it believes it has already captured —
     ``_has_element_summary_capture`` and ``_has_event_live_capture`` test for
     *any* object under ``element-summary/{fpl_id}/`` or ``event-live/{gw}/``.
     Last season's ids run to 841 against this season's ~660, so writing there
     would silently stop new players ever being fetched.

THE SYNTHETIC RUN ID
--------------------
One run_id for the whole archive: it really was one load, and fpl-ingest's own
convention is one run_id shared across the endpoints of a run. Per-file ids
would add nothing, since dedup downstream is per player.

    run_id          {timestamp}-{first 6 hex of the archived bootstrap sha256}
    extraction_date the UTC date of that timestamp

The default timestamp is the *start* of the ingest run that fetched these
payloads — fpl.db's ``_runs.started_at`` / ``last_successful_run_at``,
2026-05-26T03:46:26Z — which is exactly what a real run_id prefix means. It is
not the load's completion (03:47:55Z): every archived file was written between
those two instants, so each payload was fetched within ~90s of the run_id.

That distinction matters because downstream logic reads this instant as capture
recency — fct_player_fixture's dedup ordering and latest-run lookup, and the
spine's latest capture. One run_id for the whole season means the season has
exactly one capture, so those comparisons are singletons here and the instant
never arbitrates between rows.

The format satisfies fpl-ingest's own ``_RUN_ID_RE`` (``\\d{8}T\\d{6}Z-``
plus six lowercase hex) and staging's strptime of the prefix. Nothing can
collide: the run_id derives from the content, and it is written under a root
fpl-ingest never reads or writes.

PAYLOAD BYTES
-------------
The archived files are not the API's bytes — the old ingest parsed each
response and rewrote it with ``indent=2``. They are re-serialised here compact
(``separators=(',', ':')``), which is the shape live payloads have, so the
history tree reads like the live one. The JSON *values* are untouched: this
script parses and re-dumps, it never edits content. Both digests are recorded
in metadata.json, so the archived original remains identifiable.

USAGE
-----
    # plan only, no writes anywhere
    python scripts/rekey_history_season.py --dry-run

    # write the tree locally to inspect it
    python scripts/rekey_history_season.py --dest /tmp/history-dryrun

    # the real thing
    python scripts/rekey_history_season.py --dest s3://fpl-data-safari/history

--source and --dest each accept an s3:// URL or a local path. The script never
deletes and never overwrites: an existing destination object is a hard error
unless --overwrite is passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import boto3

DEFAULT_SOURCE = "s3://fpl-data-safari/archive/2025-26/raw"
DEFAULT_DEST = "s3://fpl-data-safari/history"
DEFAULT_SEASON = "2025-26"

# Start of the pre-S3 ingest run that fetched these payloads: fpl.db's
# _runs.started_at / last_successful_run_at. The run finished at 03:47:55Z and
# every archived file's mtime falls between the two, so this is a fetch-run
# start instant — the same meaning a real run_id prefix carries — not a
# load-completion time.
DEFAULT_RUN_TIMESTAMP = "20260526T034626Z"

RAW_CONTRACT_VERSION = "1.0.0"
SOURCE_NAME = "fpl"
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{6}$")
GW_FILE_RE = re.compile(r"^gw_(\d{1,2})\.json$")
PLAYER_FILE_RE = re.compile(r"^(\d+)\.json$")


class Location:
    """An s3:// URL or a local directory, with the few operations needed here."""

    def __init__(self, raw: str) -> None:
        self.raw = raw.rstrip("/")
        self.is_s3 = self.raw.startswith("s3://")
        if self.is_s3:
            without_scheme = self.raw[len("s3://") :]
            self.bucket, _, self.prefix = without_scheme.partition("/")
            if not self.bucket:
                raise ValueError(f"missing bucket in {raw!r}")
        else:
            self.path = Path(self.raw).expanduser()

    def __str__(self) -> str:
        return self.raw

    def join(self, *parts: str) -> str:
        return "/".join([self.raw, *parts])

    def read(self, relative: str, client) -> bytes:
        if self.is_s3:
            key = f"{self.prefix}/{relative}" if self.prefix else relative
            return client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return (self.path / relative).read_bytes()

    def list_files(self, client) -> list[str]:
        """Every file under this location, as paths relative to it."""
        if self.is_s3:
            paginator = client.get_paginator("list_objects_v2")
            prefix = f"{self.prefix}/" if self.prefix else ""
            found: list[str] = []
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for item in page.get("Contents", []):
                    found.append(item["Key"][len(prefix) :])
            return sorted(found)
        return sorted(
            str(p.relative_to(self.path)) for p in self.path.rglob("*") if p.is_file()
        )

    def exists(self, relative: str, client) -> bool:
        if self.is_s3:
            key = f"{self.prefix}/{relative}" if self.prefix else relative
            response = client.list_objects_v2(
                Bucket=self.bucket, Prefix=key, MaxKeys=1
            )
            return any(item["Key"] == key for item in response.get("Contents", []))
        return (self.path / relative).exists()

    def write(self, relative: str, data: bytes, client) -> None:
        if self.is_s3:
            key = f"{self.prefix}/{relative}" if self.prefix else relative
            client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType="application/json",
                ChecksumAlgorithm="SHA256",
            )
            return
        target = self.path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def endpoint_for(relative_path: str) -> str | None:
    """The fpl-ingest endpoint identity an archived file maps to.

    Returns None for a file the archive holds that has no endpoint — there are
    none today, and an unmapped file must stop the run rather than be skipped
    silently.
    """
    if relative_path == "bootstrap.json":
        return "bootstrap-static"
    if relative_path == "fixtures.json":
        return "fixtures"

    gameweek = GW_FILE_RE.match(relative_path)
    if gameweek:
        # Zero-padded, matching fpl-ingest's gameweeks.raw_endpoint, so
        # event-live/02 sorts before event-live/10.
        return f"event-live/{int(gameweek.group(1)):02d}"

    head, _, tail = relative_path.partition("/")
    if head == "players":
        player = PLAYER_FILE_RE.match(tail)
        if player:
            return f"element-summary/{int(player.group(1))}"
    return None


def build_run_id(bootstrap_sha256: str, timestamp: str) -> str:
    run_id = f"{timestamp}-{bootstrap_sha256[:6]}"
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"synthetic run_id {run_id!r} is not a valid fpl-ingest run id")
    return run_id


def extraction_date_for(timestamp: str) -> str:
    return datetime.strptime(timestamp, "%Y%m%dT%H%M%SZ").strftime("%Y-%m-%d")


def metadata_for(
    *,
    endpoint: str,
    run_id: str,
    extraction_date: str,
    season: str,
    source_uri: str,
    original_sha256: str,
    payload_sha256: str,
    payload_length: int,
) -> bytes:
    """The companion metadata.json.

    Mirrors the field names fpl-ingest writes, so the two trees read alike, and
    states plainly that this object was not captured from the API in this form.
    fpl-warehouse reads only payload.json; nothing downstream parses this.
    """
    document = {
        "raw_contract_version": RAW_CONTRACT_VERSION,
        "source": SOURCE_NAME,
        "endpoint": endpoint,
        "run_id": run_id,
        "extraction_date": extraction_date,
        "season": season,
        "synthetic": True,
        "synthetic_note": (
            "Re-keyed from an archived pre-S3 capture by "
            "scripts/rekey_history_season.py. The payload was parsed and "
            "re-serialised compact; its JSON values are exactly as archived. "
            "This object was NOT written at this key by fpl-ingest, and no "
            "request was made to produce it: the key was constructed after "
            "the fact from a snapshot tree that carried no run identity."
        ),
        "run_id_timestamp_meaning": (
            "The instant in run_id is the start of the pre-S3 ingest run that "
            "fetched these payloads (fpl.db _runs.started_at and "
            "last_successful_run_at, 2026-05-26T03:46:26Z) — the same meaning "
            "a real run_id prefix carries. It is the run's start, not its "
            "completion (03:47:55Z) and not a per-request time: every archived "
            "file was written between 03:46:26Z and 03:47:55Z, so each payload "
            "was fetched within about 90 seconds after it. All payloads of "
            "this season share one run_id because they were one run; the "
            "season therefore has exactly one capture, and every downstream "
            "recency comparison over it is a singleton."
        ),
        "archive_source_uri": source_uri,
        "archive_sha256": original_sha256,
        "content_sha256": payload_sha256,
        "content_length": payload_length,
        "payload_filename": "payload.json",
        "rekeyed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return json.dumps(document, indent=2, sort_keys=True).encode("utf-8")


def plan(source: Location, client) -> Iterator[tuple[str, str]]:
    """(relative archive path, endpoint) for every file in the archive."""
    files = source.list_files(client)
    if not files:
        raise SystemExit(f"no files found under {source}")
    for relative in files:
        endpoint = endpoint_for(relative)
        if endpoint is None:
            raise SystemExit(
                f"unmapped archive file {relative!r} — refusing to run, because "
                "skipping it would silently drop data from the history tree"
            )
        yield relative, endpoint


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--dest", default=DEFAULT_DEST)
    parser.add_argument("--season", default=DEFAULT_SEASON)
    parser.add_argument("--run-timestamp", default=DEFAULT_RUN_TIMESTAMP)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="plan and print, writing nothing to either destination",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="allow replacing an object that already exists at the destination",
    )
    parser.add_argument("--limit", type=int, help="process only the first N files")
    args = parser.parse_args(argv)

    source = Location(args.source)
    dest = Location(args.dest)
    client = boto3.client("s3") if (source.is_s3 or dest.is_s3) else None

    entries = list(plan(source, client))
    if args.limit:
        entries = entries[: args.limit]

    bootstrap_bytes = source.read("bootstrap.json", client)
    bootstrap_sha256 = hashlib.sha256(bootstrap_bytes).hexdigest()
    run_id = build_run_id(bootstrap_sha256, args.run_timestamp)
    extraction_date = extraction_date_for(args.run_timestamp)

    print(f"source          {source}")
    print(f"dest            {dest}/{args.season}/fpl/...")
    print(f"season          {args.season}")
    print(f"run_id          {run_id}")
    print(f"extraction_date {extraction_date}")
    print(f"archived bootstrap sha256 {bootstrap_sha256}")
    print(f"files           {len(entries)}")
    print(f"mode            {'DRY RUN — no writes' if args.dry_run else 'WRITING'}")
    print()

    by_endpoint_kind: dict[str, int] = {}
    written = 0
    for relative, endpoint in entries:
        kind = endpoint.split("/")[0]
        by_endpoint_kind[kind] = by_endpoint_kind.get(kind, 0) + 1
        prefix = f"{args.season}/fpl/{endpoint}/{extraction_date}/{run_id}"
        payload_key = f"{prefix}/payload.json"
        metadata_key = f"{prefix}/metadata.json"

        original = source.read(relative, client)
        payload = json.dumps(
            json.loads(original), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        metadata = metadata_for(
            endpoint=endpoint,
            run_id=run_id,
            extraction_date=extraction_date,
            season=args.season,
            source_uri=source.join(relative),
            original_sha256=hashlib.sha256(original).hexdigest(),
            payload_sha256=hashlib.sha256(payload).hexdigest(),
            payload_length=len(payload),
        )

        if args.dry_run:
            if written < 5:
                print(f"  would write {dest.join(payload_key)}  ({len(payload)} bytes)")
                print(f"  would write {dest.join(metadata_key)}")
            written += 1
            continue

        if not args.overwrite:
            for key in (payload_key, metadata_key):
                if dest.exists(key, client):
                    raise SystemExit(
                        f"refusing to overwrite existing object: {dest.join(key)} "
                        "(pass --overwrite to replace it)"
                    )
        dest.write(payload_key, payload, client)
        dest.write(metadata_key, metadata, client)
        written += 1
        if written % 100 == 0:
            print(f"  {written}/{len(entries)} files")

    print()
    for kind in sorted(by_endpoint_kind):
        print(f"  {kind:16} {by_endpoint_kind[kind]} payloads")
    verb = "planned" if args.dry_run else "written"
    print(f"\n{written} payloads {verb} ({written * 2} objects including metadata.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
