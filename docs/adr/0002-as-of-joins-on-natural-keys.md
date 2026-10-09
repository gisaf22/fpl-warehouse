# 0002. As-of joins on natural keys, no surrogate keys

- Status: accepted
- Date: 2026-10-09
- Decided on: #32 (decision 1), #41, #123

## Context

Served models are keyed by FPL's own identifiers. `fpl_id`, `fixture_id` and
`gameweek` are reassigned every season, so `season` is part of every key
(CLAUDE.md, "Grain"). Time-ranged models such as `dim_player_status_history`
(ADR 0001) need a way for a consumer to find the row in force at a moment.

## Decision

Join on the natural key plus a time range:

- A time-ranged row is identified by `(season, fpl_id)` and its interval
  `[valid_from, valid_to)`. There is no surrogate key.
- An as-of lookup at moment `t` matches the row of the same `(season, fpl_id)`
  with `valid_from <= t` and (`valid_to` is null or `t < valid_to`). Exactly one
  row matches when `t` is at or after the player's first capture, and none
  before it.
- `season` appears in a join only as same-season equality. No join matches one
  season's rows with another's.

## Rejected

| Option | Why rejected |
|---|---|
| Surrogate keys (a key per version of a row) | Lock each join to one version at build time, which reintroduces the "current value at build time" class of bug (CLAUDE.md, known bug 1), and add key bookkeeping a full rebuild would have to keep stable. |
| Cross-season ids (`player_code`) as the key | No question needs a cross-season join; `player_code` is carried, never used (CLAUDE.md). |

## Consequences

- A consumer's as-of join is a range predicate on `(season, fpl_id)`, with no
  lookup table.
- The interval rules (no overlap, no gap, exactly one open row per key) are what
  make the lookup return exactly one row, so they are tested on every build
  (#126 AC5).
