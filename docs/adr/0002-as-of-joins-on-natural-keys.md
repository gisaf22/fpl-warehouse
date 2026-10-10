# 0002. As-of joins on natural keys, no surrogate keys

- Status: accepted
- Date: 2026-10-09
- Decided on: #32 (decision 1), #41, #123
- Amended: 2026-10-10 (#143). The lookup is strictly before the moment, as #128 and #142
  shipped it. The half-open lookup this record first stated is now under Rejected.

## Context

Served models are keyed by FPL's own identifiers. `fpl_id`, `fixture_id` and
`gameweek` are reassigned every season, so `season` is part of every key
(CLAUDE.md, "Grain"). Time-ranged models such as `dim_player_status_history`
(ADR 0001) need a way for a consumer to find the row in force at a moment.

## Decision

Join on the natural key plus a time range:

- A time-ranged row is identified by `(season, fpl_id)` and its interval
  `[valid_from, valid_to)`. There is no surrogate key.
- An as-of lookup at moment `t` uses only captures **strictly before** `t`. On a
  time-ranged model it matches the row of the same `(season, fpl_id)` with
  `valid_from < t` and (`valid_to` is null or `t <= valid_to`) (#128). Row
  boundaries are capture times, so this is the row holding the player's last
  capture before `t`. Exactly one row matches when `t` is after the player's
  first capture, and none at or before it.
- On a capture-grain model, such as `fct_player_market_snapshot`, the lookup
  takes the player's latest row with `observed_at < t` (#142). Two captures of a
  player at the same `observed_at` would make that row ambiguous, so a tie fails
  the build (#142 AC5).
- Why strictly before: a capture at exactly `t`, such as a deadline, was not
  knowable before `t`. A backtest that used it would see the future.
- `season` appears in a join only as same-season equality. No join matches one
  season's rows with another's.

## Rejected

| Option | Why rejected |
|---|---|
| Surrogate keys (a key per version of a row) | Lock each join to one version at build time, which reintroduces the "current value at build time" class of bug (CLAUDE.md, known bug 1), and add key bookkeeping a full rebuild would have to keep stable. |
| Half-open lookup: `valid_from <= t` and (`valid_to` is null or `t < valid_to`). This record stated it until 2026-10-10. | A capture taken exactly at `t` opens a row that would match, so the lookup returns a state that was not knowable before `t`. #128 proved the difference with a literal capture at the deadline. |
| Cross-season ids (`player_code`) as the key | No question needs a cross-season join; `player_code` is carried, never used (CLAUDE.md). |

## Consequences

- A consumer's as-of join is a range predicate on `(season, fpl_id)`, with no
  lookup table.
- The interval rules (no overlap, no gap, exactly one open row per key) are what
  make the lookup return exactly one row, so they are tested on every build
  (#126 AC5).
