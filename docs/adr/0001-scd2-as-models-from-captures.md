# 0001. SCD2 as ordinary models from immutable captures, not dbt snapshots

- Status: accepted
- Date: 2026-10-09
- Decided on: #32 ("Snapshots — not used"), #123, #126

## Context

fpl-intelligence needs a player's status, news and availability as they stood at
any moment, so that a decision or backtest uses only what was knowable before a
deadline (#123). That is a Type 2 (time-ranged) history.

Every build rebuilds the warehouse from fpl-ingest's raw captures in S3. Each
bootstrap-static capture is immutable and is indexed with the moment it was
received (`observed_at`, #104).

## Decision

Build Type 2 history as an ordinary dbt model over the admitted captures, not as a
dbt snapshot. `dim_player_status_history` is the first one:

- **Ordering:** a player's captures are ordered by `observed_at`, with `run_id`
  breaking a tie, as everywhere else (#104).
- **Change detection:** a capture opens a row when any tracked field differs from
  the previous capture (`IS DISTINCT FROM`, so two nulls are equal). The tracked
  fields are `status`, `chance_of_playing_this_round`,
  `chance_of_playing_next_round`, `news`, `can_select`, `removed`, `team_fpl_id`
  and `position_id`.
- **Interval:** `valid_from` is the opening capture's `observed_at`; `valid_to` is
  the next row's `valid_from`, null on the open row. Half-open, `[valid_from,
  valid_to)`.
- **No backdating:** a player's first row opens at their first capture. Before it
  there is no row. 2025-26 has one capture, taken 2026-05-26 after the season
  ended, so an as-of lookup at any 2025-26 deadline matches nothing, by design.
- **No closing on absence:** a player missing from later captures keeps an open
  row. A warn-severity test names them (#123 rejected an absence-closing rule:
  0 drops in 209 captures).
- **Attributes come from the opening capture.** `news_added`, `player_code` and
  `capture_key` never open a row, and each row carries the values from the
  capture that opened it. `capture_key` is then the evidence for `valid_from`:
  it names the capture that observed the state. And a row's values are stable
  across rebuilds: later captures can close a row, never change it.

`team_fpl_id` is tracked here as the club the player was listed at, as of each
capture. That is safe because it is time-ranged and joined only as of a moment
inside its interval. It is never a build-time "current team" joined onto past
fixtures (CLAUDE.md, known bug 1). The club a player played for in a fixture
stays `fct_player_fixture.team_fpl_id` (#43). This retires the earlier
`stg_player` note that `team` was deliberately not carried.

## Rejected

| Option | Why rejected |
|---|---|
| dbt snapshots | Stateful: wiped by every full rebuild, and cannot backfill existing captures. The raw capture tree already is the history; a snapshot would duplicate it in a form that cannot be rebuilt (#32). |
| Attributes from the latest capture in the interval | `capture_key` would no longer identify the capture behind `valid_from`, and an open row's values would change on every build. |
| Backdating the first row to the season's start | Claims a state before it was observed. |

## Consequences

- The history is reproducible: rebuilding from the same captures gives the same
  rows.
- A change is visible only from the capture that first showed it, so the
  resolution of `valid_from` is the capture cadence.
- History cannot extend before the first capture: 2026-27 starts 2026-08-29,
  and 2025-26 has a single row per player.
