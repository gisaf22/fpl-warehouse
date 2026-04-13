# Architectural Debt: Live API Calls In The Warehouse

Version: 1.0.0

## The violation

The warehouse currently makes live FPL API calls in two places.

`builders/snapshots.py` — `refresh_player_availability` calls `sources/fpl.get_bootstrap()`
directly to update `chance_of_playing_next_round`, `news`, and `news_updated` on `dim_players`.

`sources/fpl.py` — an FPL API client module that lives inside the warehouse package. Its
functions (`get_bootstrap`, `get_picks`, `get_entry`, `get_entry_history`) are used by
`refresh_player_availability` and `builders/manager.py`.

## Why this is wrong

The warehouse has one job: read from `fpl.db` and `understat.db`, build, validate. It must
have no live API dependency. The correct boundary is:

```
fpl ingestion       ← owns: when to pull, which fields, freshness contract, fpl.db
understat ingestion ← owns: when to pull, freshness contract, understat.db
        ↓
warehouse           ← reads fpl.db + understat.db only. no API calls. no refresh logic.
```

Calling the FPL API from the warehouse violates this boundary in three ways.

1. The warehouse has an undeclared runtime dependency on the FPL API being reachable.
2. Live fields updated via `refresh_player_availability` are not governed by the same
   ingestion timestamp as the rest of `dim_players`. There is no single source of truth
   for when those values were fetched.
3. The `--refresh-availability` CLI flag sits at the wrong layer. Operators should refresh
   `fpl.db`, then rebuild the warehouse — not trigger a live API call from inside the
   warehouse CLI.

## What the correct behavior is

`fpl.db` ingestion is responsible for keeping `chance_of_playing_next_round`, `news`, and
`news_updated` current. The warehouse reads those fields from `fpl.db` during `dim_players`
build, the same as every other player field.

There is no live refresh path in the warehouse. Freshness is owned entirely by the ingestion
layer.

## Artefacts to remove

| Artefact | Location | Action |
|---|---|---|
| `refresh_player_availability` | `builders/snapshots.py` | remove once fields exist in `fpl.db` |
| `sources/fpl.py` | `sources/fpl.py` | remove; `get_picks` moves with `manager.py` if that feature is retained |
| `sources/__init__.py` | `sources/__init__.py` | remove |
| `sources/` directory | `src/fpl_warehouse/sources/` | remove |
| `--refresh-availability` CLI flag | `cli.py` | remove |

`builders/manager.py` uses `get_picks` and `get_entry`. That is a separate optional
operational feature, not a refresh concern. Its API dependency is intentional and does not
violate the warehouse source boundary — it is not part of the warehouse build pipeline.
See `docs/system/architecture.md` for the optional operational workflow note.

## Prerequisite

`fpl.db` ingestion must persist `chance_of_playing_next_round`, `news`, and `news_updated`
in the `elements` table before the warehouse artefacts above can be removed.
