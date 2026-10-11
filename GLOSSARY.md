# Glossary

One definition per term. A term is added here before an issue, PR or check cites it
(`CLAUDE.md`, opening). Where a decision record holds the full rule, the entry points to it.

## Captures and time

- **capture**: one payload fpl-ingest fetched from one FPL endpoint in one run, with its
  entry in the capture index. Identified by `capture_key`. Captures are immutable (ADR 0003).
- **admitted capture**: a capture the warehouse may read: from a finalized production run,
  usable and with a season (`int_capture_admission`, #97). Staging holds admitted captures
  only (#104).
- **observed_at / received_at**: when a capture was received. `observed_at` is the
  warehouse's name for fpl-ingest's `received_at`, read from the capture index (#104). It is
  not a field in FPL's data.
  - **Live captures:** taken when the HTTP response arrives, written with `isoformat()`,
    stored to the **microsecond** (PR #147).
  - **History port captures (2025-26):** the run's start time, in **whole seconds**.
- **moment / cutoff**: the time an as-of lookup is made at. The caller supplies it; it is
  not wired to the gameweek deadline (#142 P4). A deadline is one common cutoff.
- **as-of**: the latest capture strictly before the moment. A capture exactly at the moment
  is excluded (ADR 0002).
- **max_age**: an optional limit on an as-of lookup. The usable window is
  `[moment − max_age, moment)`. A latest capture older than that returns NULL; there is no
  fallback to an older one (#142 P3).
- **tie**: two captures of the same player claim the same `observed_at`. A tie is a defect:
  as-of needs unique times to be deterministic, so a tie on `(season, fpl_id, observed_at)`
  fails the build (#142 AC5).
- **repeat**: the same record appearing more than once, for example in two runs. Staging
  resolves a repeat by `run_id`, which breaks an `observed_at` tie in capture order (#104).
  A repeat is expected; a tie is not.

## State and outcome

- **pre-deadline state**: what was observable before a deadline: a player's status, price
  and ownership as of that deadline (`dim_player_status_history`, `fct_player_market_snapshot`).
- **ratified outcome**: a gameweek's results after FPL has ratified its points and bonus
  (`is_ratified`, the `ratified` doc block in `models/marts/docs.md`). Not knowable before the
  deadline.

## Serving

- **served**: published to `served/` as parquet, `access: public` with an enforced contract
  (`CLAUDE.md`, "Served contract"). Consumers read only served tables.
- **private**: `access: private`; a model only this project's models and tests may `ref()`.
  Not published.

## Work

- **slice**: a Feature's vertical increment that delivers usable value end to end on its
  own (`AGENT_WORKFLOW.md`, "Story splitting").
- **gate**: an action only the human takes: merges, live writes, permission and access
  changes, workflow dispatches that write, and changes to a contract consumers depend on
  (`AGENT_WORKFLOW.md`, "Boundaries").

## Service levels

- **freshness at cutoff**: at each cutoff, the latest admitted live `bootstrap-static`
  capture before it is at most 15 min old. Target: ≥ 90% of gameweeks from GW6 of 2026-27,
  measured at the deadline, deadline − 1h and deadline − 5h (#113).

## Words to avoid

- **"snapshot"** unqualified: say capture, as-of state, or the model's name.
- **"latest"** without saying before what: say "latest before the deadline" or "latest
  admitted capture".
