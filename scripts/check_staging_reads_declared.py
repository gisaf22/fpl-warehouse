"""Fail CI when a payload staging model reads its source around the declared columns.

A staging model must read an fpl_raw payload source through `declared_records`
(macros/declared_records.sql), which selects only the columns declared in
models/staging/sources.yml (#115 D1). A model that calls `source()` itself can
read any field, and a field nobody declared escapes the presence test (#114 D4).

`run_manifests` and `backfill_catalog` are exempt (#115 D3): their
`read_json(columns = struct_pack(...))` in sources.yml already fixes the
schema, so a field outside that list cannot be read.

Run after `dbt parse`: `python scripts/check_staging_reads_declared.py`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SOURCE_PREFIX = "source.fpl_warehouse.fpl_raw."
NOT_PAYLOAD = {"run_manifests", "backfill_catalog"}

DIRECT_SOURCE_CALL = re.compile(r"\bsource\s*\(")
# SQL line and block comments and Jinja comments, so prose naming source( in a
# model's header does not trip the check. Not string-aware: a quoted "--" would
# hide the rest of its line, which no staging model has.
COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/|\{#.*?#\}", re.DOTALL)


def problems(manifest: dict) -> list[str]:
    checked = 0
    out = []
    for node in manifest.get("nodes", {}).values():
        if node.get("resource_type") != "model" or not node.get("name", "").startswith("stg_"):
            continue
        payload = sorted(
            uid.removeprefix(SOURCE_PREFIX)
            for uid in (node.get("depends_on") or {}).get("nodes", [])
            if uid.startswith(SOURCE_PREFIX) and uid.removeprefix(SOURCE_PREFIX) not in NOT_PAYLOAD
        )
        if not payload:
            continue
        checked += 1
        if DIRECT_SOURCE_CALL.search(COMMENT.sub(" ", node.get("raw_code", ""))):
            out.append(
                f"{node['name']} calls source() on fpl_raw.{', fpl_raw.'.join(payload)} "
                "itself; read payload fields through declared_records so only "
                "columns declared in sources.yml can be read (#115)"
            )
    if not checked:
        out.append("no payload staging models found; nothing was checked")
    return out


def main() -> int:
    manifest = json.loads(Path("target/manifest.json").read_text())
    found = problems(manifest)
    for problem in found:
        print(f"::error::{problem}")
    if not found:
        print("every payload staging model reads through declared_records")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
