"""CLI entry point for fpl-warehouse."""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

from .build import (
    build_all,
    build_fact_manager_squad,
    build_fact_transfer_snapshot,
    refresh_player_availability,
)

DEFAULT_FPL_DB = str(Path.home() / "Documents/FPL/data/fpl/fpl.db")
DEFAULT_UNDERSTAT_DB = str(Path.home() / "Documents/FPL/data/understat/understat.db")
DEFAULT_WAREHOUSE_DB = str(Path.home() / "Documents/FPL/data/warehouse/master.db")


def main(argv: list[str] | None = None) -> None:
    """Entry point for the fpl-warehouse CLI. Materialises warehouse tables from ingestion databases."""
    parser = argparse.ArgumentParser(
        description="Build FPL warehouse from FPL + Understat source databases."
    )
    parser.add_argument(
        "--fpl-db", default=DEFAULT_FPL_DB,
        help=f"Path to FPL source database (default: {DEFAULT_FPL_DB})",
    )
    parser.add_argument(
        "--understat-db", default=DEFAULT_UNDERSTAT_DB,
        help=f"Path to Understat source database (default: {DEFAULT_UNDERSTAT_DB})",
    )
    parser.add_argument(
        "--warehouse-db", default=DEFAULT_WAREHOUSE_DB,
        help=f"Path to warehouse output database (default: {DEFAULT_WAREHOUSE_DB})",
    )
    parser.add_argument(
        "--threshold", type=int, default=75,
        help="Minimum fuzzy match confidence for player matching (default: 75)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--build-transfer-snapshot", action="store_true",
        help="Build only fact_transfer_snapshot (requires fact_decision_snapshot to exist)",
    )
    parser.add_argument(
        "--build-manager-squad", action="store_true",
        help="Fetch and store manager squad from FPL API",
    )
    parser.add_argument(
        "--team-id", type=int, default=None,
        help="FPL manager team ID (required for --build-manager-squad)",
    )
    parser.add_argument(
        "--gw", type=int, default=None,
        help="Gameweek number (required for --build-manager-squad)",
    )
    parser.add_argument(
        "--refresh-availability", action="store_true",
        help="Refresh player availability from bootstrap-static API",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Validate source DBs exist
    for label, path in [("FPL", args.fpl_db), ("Understat", args.understat_db)]:
        if not Path(path).exists():
            logging.error("%s database not found: %s", label, path)
            sys.exit(1)

    if args.build_transfer_snapshot:
        wh = sqlite3.connect(args.warehouse_db)
        build_fact_transfer_snapshot(wh)
        total = wh.execute(
            "SELECT COUNT(*) FROM fact_transfer_snapshot"
        ).fetchone()[0]
        wh.close()
        print(f"\nfact_transfer_snapshot: {total:,} rows")
        print(f"Database: {args.warehouse_db}")
        return

    if args.build_manager_squad:
        if args.team_id is None or args.gw is None:
            logging.error("--team-id and --gw are required for --build-manager-squad")
            sys.exit(1)
        wh = sqlite3.connect(args.warehouse_db)
        count = build_fact_manager_squad(wh, args.team_id, args.gw)
        wh.close()
        print(f"\nfact_manager_squad: {count} rows for team {args.team_id} GW {args.gw}")
        print(f"Database: {args.warehouse_db}")
        return

    if args.refresh_availability:
        wh = sqlite3.connect(args.warehouse_db)
        count = refresh_player_availability(wh)
        wh.close()
        print(f"\nPlayer availability refreshed: {count} players updated")
        print(f"Database: {args.warehouse_db}")
        return

    results = build_all(
        fpl_db=args.fpl_db,
        understat_db=args.understat_db,
        warehouse_db=args.warehouse_db,
        threshold=args.threshold,
    )

    print("\n=== Warehouse Build Complete ===")
    for table, count in results.items():
        print(f"  {table}: {count:,}")
    print(f"\nDatabase: {args.warehouse_db}")


if __name__ == "__main__":
    main()
