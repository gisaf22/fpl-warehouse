"""CLI entry point for fpl-warehouse."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .build import build_all
from .warehouse.db import (
    _load_fpl_env,
    _DEFAULT_FPL_PATH,
    _DEFAULT_UNDERSTAT_PATH,
    _DEFAULT_WAREHOUSE_PATH,
)


def main(argv: list[str] | None = None) -> None:
    """Entry point for the fpl-warehouse CLI. Materialises warehouse tables from ingestion databases."""
    import os
    _load_fpl_env()
    fpl_db = os.environ.get("FPL_DB_PATH", str(_DEFAULT_FPL_PATH))
    understat_db = os.environ.get("UNDERSTAT_DB_PATH", str(_DEFAULT_UNDERSTAT_PATH))
    warehouse_db = os.environ.get("WAREHOUSE_DB_PATH", str(_DEFAULT_WAREHOUSE_PATH))

    parser = argparse.ArgumentParser(
        description="Build FPL warehouse from FPL + Understat source databases."
    )
    parser.add_argument(
        "--fpl-db", default=fpl_db,
        help=f"Path to FPL source database (default: {fpl_db})",
    )
    parser.add_argument(
        "--understat-db", default=understat_db,
        help=f"Path to Understat source database (default: {understat_db})",
    )
    parser.add_argument(
        "--warehouse-db", default=warehouse_db,
        help=f"Path to warehouse output database (default: {warehouse_db})",
    )
    parser.add_argument(
        "--threshold", type=int, default=75,
        help="Minimum fuzzy match confidence for player matching (default: 75)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    for label, path in [("FPL", args.fpl_db), ("Understat", args.understat_db)]:
        if not Path(path).exists():
            logging.error("%s database not found: %s", label, path)
            sys.exit(1)

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
