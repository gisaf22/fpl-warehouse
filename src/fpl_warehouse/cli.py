"""CLI entry point for fpl-warehouse."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .build import build_all
from .warehouse.db import DEFAULT_FPL_DB, DEFAULT_UNDERSTAT_DB, DEFAULT_WAREHOUSE_DB


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
