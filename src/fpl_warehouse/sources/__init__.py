"""External data source clients used by the warehouse.

# WARNING: this package is architectural debt. See docs/history/sources_refresh_debt.md.
"""

from .fpl import get_bootstrap

__all__ = [
    "get_bootstrap",
]
