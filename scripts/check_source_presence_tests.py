"""Fail CI when a payload source is not fully covered by consumed_keys_present.

Every fpl_raw payload source must carry the presence test twice (#114 D1):
`mode: removed` at error severity and `mode: partial` at warn. A declared
column can opt out only through `meta.presence_exempt` with a non-empty reason.
`run_manifests` and `backfill_catalog` are not payloads: they are read with
explicit columns and are not captures in the admission index.

Run after `dbt parse`: `python scripts/check_source_presence_tests.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SOURCE_NAME = "fpl_raw"
NOT_PAYLOAD = {"run_manifests", "backfill_catalog"}
TEST_NAME = "consumed_keys_present"
SEVERITY = {"removed": "error", "partial": "warn"}


def problems(manifest: dict) -> list[str]:
    payload = {
        uid: source
        for uid, source in manifest.get("sources", {}).items()
        if source.get("source_name") == SOURCE_NAME and source.get("name") not in NOT_PAYLOAD
    }
    if not payload:
        return [f"no {SOURCE_NAME} payload sources found; nothing was checked"]

    found: dict[tuple[str, str], str] = {}
    for node in manifest.get("nodes", {}).values():
        meta = node.get("test_metadata") or {}
        if node.get("resource_type") != "test" or meta.get("name") != TEST_NAME:
            continue
        mode = (meta.get("kwargs") or {}).get("mode")
        severity = str((node.get("config") or {}).get("severity", "")).lower()
        for uid in (node.get("depends_on") or {}).get("nodes", []):
            if uid in payload:
                found[(uid, mode)] = severity

    out = []
    for uid, source in sorted(payload.items()):
        name = source["name"]
        for mode, severity in SEVERITY.items():
            if (uid, mode) not in found:
                out.append(f"{name} has no {TEST_NAME} test with mode {mode}")
            elif found[(uid, mode)] != severity:
                out.append(
                    f"{name}'s {TEST_NAME} test with mode {mode} has severity "
                    f"{found[(uid, mode)] or 'unset'}; expected {severity}"
                )
        for column in source.get("columns", {}).values():
            meta = column.get("meta") or {}
            if "presence_exempt" in meta and not str(meta["presence_exempt"] or "").strip():
                out.append(
                    f"{name}.{column['name']} is exempt from {TEST_NAME} with no reason "
                    "in meta.presence_exempt"
                )
    return out


def main() -> int:
    manifest = json.loads(Path("target/manifest.json").read_text())
    found = problems(manifest)
    for problem in found:
        print(f"::error::{problem}")
    if not found:
        print(f"every {SOURCE_NAME} payload source carries both {TEST_NAME} tests")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
