"""Warehouse schema management. Reads DDL from base_tables/*.sql and applies it."""

from __future__ import annotations

import logging
from pathlib import Path

from .db import connect_warehouse

logger = logging.getLogger(__name__)

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "base_tables"


def create_schema(warehouse_db: str) -> None:
    """Create all base warehouse tables from base_tables/*.sql files. Idempotent."""
    conn = connect_warehouse(warehouse_db)
    for sql_file in sorted(_SCHEMA_DIR.glob("*.sql")):
        conn.execute(sql_file.read_text())
    conn.commit()
    conn.close()
    logger.info("Warehouse schema created/verified at %s", warehouse_db)