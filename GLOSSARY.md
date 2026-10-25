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
- **run**: one execution of fpl-ingest, identified by `run_id` (e.g.
  `20260920T190000Z-aaaaaa`), with one run manifest at
  `raw/fpl/_manifests/<extraction_date>/<run_id>/manifest.json`. A run is **finalized**
  when its manifest's status is anything but `IN_PROGRESS` (`stg_run`). A run holds many
  captures.
- **capture day**: the date segment of a raw capture's key
  (`raw/fpl/<endpoint>/.../<capture day>/<run_id>/payload.json`), the run's start date in
  UTC. A run that spans midnight keeps its start date. It equals the run manifest's
  `extraction_date`, which the compaction writer checks per file (#78 W10, W11). It is the
  `date=` partition value under `compacted/` (`docs/compacted.md`).
- **closed day**: a capture day that may be compacted. Day D is closed once
  `D+1 00:00 UTC` plus the ingest job timeout has passed and every run manifest under
  `raw/fpl/_manifests/D/` is finalized (#198 D1). A day with a run still `IN_PROGRESS`
  stays open.
- **compacted capture**: a capture read from a capture day's parquet under `compacted/`
  instead of from its raw payload file. The row is unchanged and keeps the raw file's
  `filename`. A day's captures count as compacted only once its compaction manifest exists
  (ADR 0004, `docs/compacted.md`).
- **repeat**: the same record appearing more than once, for example in two runs. Staging
  resolves a repeat by `run_id`, which breaks an `observed_at` tie in capture order (#104).
  A repeat is expected; a tie is not.
- **capture clock**: per season, the newest staged `bootstrap-static` capture's `observed_at`.
  Staged means the capture has rows in `stg_gameweek`, so an admitted capture whose payload
  did not stage does not move it (#163 S12, S14c). A gameweek has **passed** when its
  `deadline_time` is at or before the capture clock. It stands in for `now()` so that a
  rebuild from the same captures gives the same rows (#163 S10).

## State and outcome

- **pre-deadline state**: what was observable before a deadline: a player's status, price
  and ownership as of that deadline (`dim_player_status_history`, `fct_player_market_snapshot`),
  and the fixture schedule as of that deadline (slice 1c).
- **pre-deadline freshness**: for a passed gameweek, how old the newest staged
  `bootstrap-static` capture strictly before its deadline was: `last_capture_before_deadline_at`
  and `state_age_seconds` on `dim_gameweek` (#169). NULL when the gameweek has not passed by
  the capture clock, or when no staged capture exists before the deadline (#163 S10, S13).
  Distinct from *freshness at cutoff*, which counts admitted live captures (#113); neither
  measures the other.
- **fixture schedule**: which gameweek a fixture is in, its kickoff time, its home and away
  teams, and each side's difficulty rating. Not its result: a score is a ratified outcome.
- **fixture count at deadline** (`fixture_count_at_deadline`): for a player and a gameweek,
  the number of fixtures the player's club had in the gameweek's fixture schedule as of its
  deadline, the club also as of the deadline (#221). Not the realised `fixture_count`: a
  fixture postponed after the deadline still counts. NULL when no staged capture, no
  schedule row, or no status row for the player precedes the deadline.
- **reschedule**: FPL changing a fixture's kickoff time after publishing it. A reschedule moves
  the fixture; the fixture keeps its id.
- **ratified outcome**: a gameweek's results after FPL has ratified its points and bonus
  (`is_ratified`, the `ratified` doc block in `models/marts/docs.md`). Not knowable before the
  deadline.

## Managers

- **manager**: one FPL team, identified by FPL's `entry_id`. The warehouse reads a manager's
  `entry-picks` captures. Like `fpl_id`, an `entry_id` is matched within season.
- **panel**: the season's managers fpl-ingest draws once and captures every gameweek,
  listed in `raw/fpl/_panels/<season>/manager-panel.json` (fpl-ingest#100, #102). Only
  managers whose history had picks are kept.
- **cohort**: why a manager is on the panel: `random` (drawn at random from every
  manager) or `self` (named outside the draw). A column on `fct_manager_gameweek`
  (#216 D10).
- **join week** (`first_active_gw`): a manager's first marked gameweek with an admitted
  picks capture (#216 D6, amended by O1). Before it the manager had no team, and FPL
  answers a picks request with 404. NULL when the manager has no admitted capture in
  any marked gameweek; every marked gameweek then reads `not_yet_joined`. The panel
  file's `joined_gw` is not it: it is 1 for every manager.
- **settlement marker (picks)**: `raw/fpl/_settlement/entry-picks/<gameweek>/marker.json`,
  which fpl-ingest writes once every panel manager's picks for that gameweek are captured,
  as a payload or as a pre-join 404 (fpl-ingest ADR 006). A **marked gameweek** has one.
  An unmarked gameweek is not settled and is hidden (#216 D4).
- **manager-gameweek status**: for a panel manager and a marked gameweek, one of
  `not_yet_joined` (before the join week, or with no join week), `captured` (an admitted picks capture exists) or
  `missing_after_join` (neither) (#216 D1). Held in `int_manager_gameweek_status`.
- **slot**: a pick's position, 1–15, as FPL returns it after automatic substitutions:
  slots 1–11 are the eleven FPL scored, 12–15 the bench. A starter that was substituted
  sits on the bench and the substitute in a slot of 1–11.
- **scored eleven**: a manager-gameweek's slots 1–11 as FPL returns them, after automatic
  substitutions: the eleven whose points FPL counted.
- **chosen eleven**: the eleven the manager picked before the deadline: the slot 1–11
  picks not substituted in, plus the picks substituted out (#216 D7, amended by O4).
  The metric #216 serves sums it.
- **overall rank** (`overall_rank`): a manager's overall rank at the end of a gameweek,
  from FPL's `entry_history.overall_rank` (#219 D1). Served on `fct_manager_gameweek`, NULL
  where FPL reports no valid rank: FPL reports such a team as null or 0, cause unknown.
  Staging keeps the 0.
- **ranked count** (`ranked_count`): FPL's count of ranked teams for a gameweek,
  `events[].ranked_count` in `bootstrap-static` (#219 D2). Served on `dim_gameweek` once
  the gameweek is ratified, and NULL before: FPL reads 0 for a gameweek not yet played and a
  provisional, too-high count for one in progress. It is the denominator of an overall rank
  for the same gameweek. NULL for 2025-26, which is not served (D3).

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

## Naming

- **column names** (#133 S8, limited by #163 S14b): a field read from FPL keeps FPL's name
  (`deadline_time`, `kickoff_time`). A point-in-time timestamp the warehouse derives ends in
  `_at` (`observed_at`, `last_capture_before_deadline_at`). SCD2 interval bounds are outside
  this rule and keep ADR 0001's `valid_from` / `valid_to`.

## Words to avoid

- **"snapshot"** unqualified: say capture, as-of state, or the model's name.
- **"latest"** without saying before what: say "latest before the deadline" or "latest
  admitted capture".
