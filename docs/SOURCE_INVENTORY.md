# Source inventory — what the raw captures hold, what is staged, what is demanded

**Measured 2026-09-24** against `s3://fpl-data-safari` (`raw/` live tree, `history/2025-26/`
ported tree, `archive/2025-26/`), fpl-warehouse `origin/main` @ `842ffe3`, fpl-ingest `main` @
`469dd3d`, and fpl-intelligence's working tree (branch `predictive-cleanup-and-redesign-spec`).
Read-only: no S3 writes, no ingest runs, no dispatches.

Parts 1–3 are facts. Part 4 is a recommendation and is marked as one. **OBSERVED** means read
from real keys, manifests or payloads. **INFERRED** means reasoned from them, or from FPL's
documented behaviour, but not measured.

**Legend for the field tables.**
- **25-26 / 26-27:** the field is present in that season's payload.
- **Class:**
  - `STATIC`: identity or schedule, fixed for the season.
  - `PRE-DL`: can change between captures and is knowable before a deadline (price,
    status, ownership, difficulty).
  - `OUTCOME`: known only after the gameweek is played. `OUTCOME (cum.)` is a season-to-date
    aggregate. Its value at a deadline is knowable, but only from a capture taken before that
    deadline.
  - `STATE`: the game's own state flags.
- **As-of:** whether the field can be read leakage-free for a given gameweek in that season. For
  a `✗ snapshot` field the only 2025-26 capture postdates every gameweek. For a `✓ from GW3`
  field, a capture precedes the deadline of GW3 and every later gameweek (see §1.0). GW1–2 have
  none.
- **Extracted:** the staging model and column that reads the field today, or `—`.

---

## Part 1 — Inventory

### 1.0 Capture profile per season (OBSERVED)

| | 2025-26 (`history/2025-26/fpl/`) | 2026-27 (`raw/fpl/`) |
|---|---|---|
| Origin | Re-keyed from the SQLite-era archive (`archive/2025-26/raw/`) by `scripts/rekey_history_season.py`. Every sidecar says `"synthetic": true`. | Written by fpl-ingest. |
| Runs | **1**: `20260526T034626Z-2a6b73`, every object fetched within about 90s of 2026-05-26T03:46:26Z. | 180 manifests, 2026-08-29 01:23 → 2026-09-24 17:23 UTC, all `SUCCESS`. |
| As-of | **One end-of-season snapshot**, taken after GW38. Every recency comparison over it is a singleton. | Many captures per round. The capture time is in the key (`run_id` prefix) and in the sidecar (`received_at` minus the CDN `age`). |
| Key layout | Same as live, with a season segment: `history/2025-26/fpl/{endpoint}[/{id}]/{date}/{run_id}/payload.json` + `metadata.json`. | `raw/fpl/{endpoint}[/{id}]/{date}/{run_id}/payload.json` + `metadata.json`. There is no season segment (the warehouse takes it from the `season` var). |
| Manifests | None under `history/`. `archive/2025-26/fpl.manifest.json` describes the old mart build. | `raw/fpl/_manifests/{date}/{run_id}/manifest.json`. **Only 1 of 180 carries `trigger`** (`manual`, 09-24 17:23). The key was added in fpl-ingest PR #15. |
| Other trees | `archive/2025-26/`: `fpl.db` (the SQLite source, 12 MB), `fpl.mart.parquet` (the old 64-column mart), `raw/` (bootstrap, fixtures, 38 × `gw_N.json`, 841 × `players/N.json`), `SHA256SUMS`. | `raw/fpl/_settlement/{element-summary,event-live}/{gw}/marker.json` (9 markers). |

Per endpoint:

| Endpoint | 2025-26 objects | 2026-27 payloads | 2026-27 cadence (OBSERVED) | 2026-27 cadence (policy from 2026-09-24) |
|---|---|---|---|---|
| bootstrap-static | 1 | 179 (27 dates) | Every run. 07:xx and 19:xx daily, plus roughly hourly 11–21 UTC on matchdays (the retired `scheduled_run_live.yml`), plus 1 manual pre-deadline run. | 07:00 and 19:00 daily, plus `pre-deadline` (`*/30 9-19`) within 75 min of a deadline. |
| fixtures | 1 | 178 | Every run, same as bootstrap-static. | Every run of the daily workflow. |
| event-status | **0**: the endpoint serves only the current round | 178 | Every run. | Every daily run. |
| event-live/{gw} | 38 (GW01–38, one each) | 170 (GW1 ×19, GW2 ×40, GW3–5 ×37) | Every run until fpl-ingest `1beaa23` (2026-09-23). | Once per GW, after ratification with ICT present, gated by `_settlement/event-live/{gw}`. |
| element-summary/{id} | 841 | 78,711 (126 runs, 622–667 players per run) | Every daily run until 2026-09-16. Skipped on the live cron from `f0680b6`. **Last capture 2026-09-21 19:13.** | Skip once settled. One forced refetch per settlement transition. |

**Pre-deadline coverage in 2026-27 (OBSERVED from run_id times):**

| GW | Deadline (UTC) | Latest bootstrap-static / fixtures before it | Lead | Latest element-summary before it |
|---|---|---|---|---|
| 1 | 08-21 17:30 | none (captures start 08-29) | — | none |
| 2 | 08-28 17:30 | none | — | none |
| 3 | 09-04 17:30 | 09-04 17:12 | 17m | 09-03 19:12 (22h) |
| 4 | 09-12 12:30 | 09-12 12:19 | 11m | 09-11 19:12 (17h) |
| 5 | 09-18 17:30 | 09-18 17:11 | 18m | 09-15 19:13 (2d 22h) |
| 6 | 10-10 10:00 | not yet; the pre-deadline workflow should produce the first scheduled `trigger: pre_deadline` capture | — | — |

The GW3–5 captures came from the hourly live workflow, which was retired on 2026-09-24 (`46d3c19`). Their
manifests carry no `trigger`, so they can be found only by time, not by the `trigger ==
"pre_deadline"` rule that fpl-ingest's CLAUDE.md prescribes. The CDN may serve a response up to
426s old (fpl-ingest CLAUDE.md), so a lead of 11m still precedes the deadline.

**What changes between captures within 2026-27 (OBSERVED: the first capture, 08-29 01:23,
against the latest, 09-24):**
- Players: 622 → 667 (registrations).
- `now_cost` changed for 299 players, `status` for 131 and `team` for 9.
- `element_type` changed for 0 players.
- Team `strength_*` changed for 0 of 20 teams.
- Fixture difficulty changed for 0 of 380 fixtures.
- `kickoff_time` changed for 55 of 380 fixtures.

### 1.1 bootstrap-static

Top level: `chips`, `element_stats`, `element_types`, `elements`, `events`, `game_config`,
`game_settings`, `phases`, `teams`, `total_players`. The row counts differ between seasons:
- **2025-26:** 841 elements, 20 teams, 38 events.
- **2026-27:** 667 elements, 20 teams, 38 events.

`stg_player` reads `elements[]` and `stg_gameweek` reads `events[]`. Both read both seasons.

#### `elements[]` (109 fields, 4 extracted)

| Field | 25-26 | 26-27 | Type / example | Class | As-of 25-26 | As-of 26-27 | Extracted |
|---|---|---|---|---|---|---|---|
| `assists` | ✓ | ✓ | int `0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `birth_date` | ✓ | ✓ | null or str `1995-09-15` | STATIC | ✓ | ✓ | — |
| `bonus` | ✓ | ✓ | int `3` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `bps` | ✓ | ✓ | int `104` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `can_select` | ✓ | ✓ | bool `True` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `can_transact` | ✓ | ✓ | bool `True` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `chance_of_playing_next_round` | ✓ | ✓ | int or null `100` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `chance_of_playing_this_round` | ✓ | ✓ | int or null `100` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `clean_sheets` | ✓ | ✓ | int `3` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `clean_sheets_per_90` | ✓ | ✓ | float or int `0.6` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `clearances_blocks_interceptions` | ✓ | ✓ | int `6` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `code` | ✓ | ✓ | int `154561` | STATIC | ✓ | ✓ | stg_player.player_code |
| `corners_and_indirect_freekicks_order` | ✓ | ✓ | int or null `2` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `corners_and_indirect_freekicks_text` | ✓ | ✓ | str `` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `cost_change_event` | ✓ | ✓ | int `1` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `cost_change_event_fall` | ✓ | ✓ | int `-1` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `cost_change_start` | ✓ | ✓ | int `1` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `cost_change_start_fall` | ✓ | ✓ | int `-1` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `creativity` | ✓ | ✓ | str `0.2` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `creativity_rank` | ✓ | ✓ | int `389` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `creativity_rank_type` | ✓ | ✓ | int `5` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `defensive_contribution` | ✓ | ✓ | int `0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `defensive_contribution_per_90` | ✓ | ✓ | float or int `0.0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `direct_freekicks_order` | ✓ | ✓ | int or null `2` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `direct_freekicks_text` | ✓ | ✓ | str `` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `dreamteam_count` | ✓ | ✓ | int `1` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `element_type` | ✓ | ✓ | int `1` | STATIC | ✓ (INFERRED) | ✓ | — |
| `ep_next` | ✓ | ✓ | null or str → str `6.0` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `ep_this` | ✓ | ✓ | str `6.0` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `event_points` | ✓ | ✓ | int `1` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `expected_assists` | ✓ | ✓ | str `0.01` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `expected_assists_per_90` | ✓ | ✓ | float or int `0.0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `expected_goal_involvements` | ✓ | ✓ | str `0.01` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `expected_goal_involvements_per_90` | ✓ | ✓ | float or int `0.0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `expected_goals` | ✓ | ✓ | str `0.00` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `expected_goals_conceded` | ✓ | ✓ | str `4.03` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `expected_goals_conceded_per_90` | ✓ | ✓ | float or int `0.81` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `expected_goals_per_90` | ✓ | ✓ | float or int `0.0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `first_name` | ✓ | ✓ | str `David` | STATIC | ✓ | ✓ | — |
| `form` | ✓ | ✓ | str `6.0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `form_rank` | ✓ | ✓ | int `21` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `form_rank_type` | ✓ | ✓ | int `3` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `goals_conceded` | ✓ | ✓ | int `4` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `goals_conceded_per_90` | ✓ | ✓ | float or int `0.8` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `goals_scored` | ✓ | ✓ | int `0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `has_temporary_code` | ✓ | ✓ | bool `False` | STATIC | ✓ | ✓ | — |
| `ict_index` | ✓ | ✓ | str `10.6` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `ict_index_rank` | ✓ | ✓ | int `202` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `ict_index_rank_type` | ✓ | ✓ | int `13` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `id` | ✓ | ✓ | int `1` | STATIC | ✓ | ✓ | stg_player.fpl_id |
| `in_dreamteam` | ✓ | ✓ | bool `False` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `influence` | ✓ | ✓ | str `104.6` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `influence_rank` | ✓ | ✓ | int `70` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `influence_rank_type` | ✓ | ✓ | int `13` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `known_name` | ✓ | ✓ | str `` | STATIC | ✓ | ✓ | — |
| `minutes` | ✓ | ✓ | int `450` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `news` | ✓ | ✓ | str `` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `news_added` | ✓ | ✓ | null or str `2026-07-23T12:01:23.2729` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `now_cost` | ✓ | ✓ | int `61` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `now_cost_rank` | ✓ | ✓ | int `60` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `now_cost_rank_type` | ✓ | ✓ | int `1` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `opta_code` | ✓ | ✓ | str `p154561` | STATIC | ✓ | ✓ | — |
| `own_goals` | ✓ | ✓ | int `0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `penalties_missed` | ✓ | ✓ | int `0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `penalties_order` | ✓ | ✓ | int or null `1` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `penalties_saved` | ✓ | ✓ | int `1` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `penalties_text` | ✓ | ✓ | str `` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `photo` | ✓ | ✓ | str `154561.jpg` | STATIC | ✓ | ✓ | — |
| `points_per_game` | ✓ | ✓ | str `6.0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `points_per_game_rank` | ✓ | ✓ | int `32` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `points_per_game_rank_type` | ✓ | ✓ | int `2` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `price_change_calibrating` | — | ✓ | bool `False` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `price_change_hourly_rate` | — | ✓ | int `36` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `price_change_locked_until` | — | ✓ | null or str `2026-10-02T19:12:30.1307` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `price_change_percent` | ✓ | ✓ | str `0.9` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `price_change_projections` | — | ✓ | list | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `recoveries` | ✓ | ✓ | int `58` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `red_cards` | ✓ | ✓ | int `0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `region` | ✓ | ✓ | int or null `200` | STATIC | ✓ | ✓ | — |
| `removed` | ✓ | ✓ | bool `False` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `saves` | ✓ | ✓ | int `9` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `saves_per_90` | ✓ | ✓ | float or int `1.8` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `scout_news_link` | ✓ | ✓ | str `` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `scout_risks` | ✓ | ✓ | list | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `second_name` | ✓ | ✓ | str `Raya Martín` | STATIC | ✓ | ✓ | — |
| `selected_by_percent` | ✓ | ✓ | str `42.2` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `selected_rank` | ✓ | ✓ | int `4` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `selected_rank_type` | ✓ | ✓ | int `1` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `special` | ✓ | ✓ | bool `False` | STATIC | ✓ | ✓ | — |
| `squad_number` | ✓ | ✓ | null | STATIC | ✓ | ✓ | — |
| `starts` | ✓ | ✓ | int `5` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `starts_per_90` | ✓ | ✓ | float or int `1.0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `status` | ✓ | ✓ | str `a` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `tackles` | ✓ | ✓ | int `1` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `team` | ✓ | ✓ | int `1` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `team_code` | ✓ | ✓ | int `3` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `team_join_date` | ✓ | ✓ | null or str `2024-07-04` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `threat` | ✓ | ✓ | str `0.0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `threat_rank` | ✓ | ✓ | int `657` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `threat_rank_type` | ✓ | ✓ | int `73` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `total_points` | ✓ | ✓ | int `30` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | stg_player.total_points |
| `transfers_in` | ✓ | ✓ | int `952575` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `transfers_in_event` | ✓ | ✓ | int `112176` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `transfers_out` | ✓ | ✓ | int `631777` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `transfers_out_event` | ✓ | ✓ | int `39373` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `value_form` | ✓ | ✓ | str `1.0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `value_season` | ✓ | ✓ | str `4.9` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `web_name` | ✓ | ✓ | str `Raya` | STATIC | ✓ | ✓ | stg_player.web_name |
| `yellow_cards` | ✓ | ✓ | int `0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |

Nested lists on `elements[]`:
- **`scout_risks[]`**: `gameweek` int, `notes` str, `property` str (e.g. `loan_ineligible`),
  `url` null. Class PRE-DL. The key exists in 2025-26 but is empty for all 841 players. It is
  non-empty for 8 players in 2026-27.
- **`price_change_projections[]`**: `offset` int (0–2), `projected_percent` str, `likelihood`
  int (−3…+3). Class PRE-DL. 2026-27 only.
- `price_change_percent` exists in both seasons but is `"0"` for all 841 players in 2025-26.

#### `teams[]` (22 fields, 0 extracted)

| Field | 25-26 | 26-27 | Type / example | Class | As-of 25-26 | As-of 26-27 | Extracted |
|---|---|---|---|---|---|---|---|
| `code` | ✓ | ✓ | int `3` | STATIC | ✓ | ✓ | — |
| `draw` | ✓ | ✓ | int `0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `form` | ✓ | ✓ | null | STATIC | ✓ | ✓ | — |
| `id` | ✓ | ✓ | int `1` | STATIC | ✓ | ✓ | — |
| `link_url` | ✓ | ✓ | str `` | STATIC | ✓ | ✓ | — |
| `loss` | ✓ | ✓ | int `0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `name` | ✓ | ✓ | str `Arsenal` | STATIC | ✓ | ✓ | — |
| `played` | ✓ | ✓ | int `0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `points` | ✓ | ✓ | int `0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `position` | ✓ | ✓ | int `2` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |
| `pulse_id` | ✓ | ✓ | int `1` | STATIC | ✓ | ✓ | — |
| `short_name` | ✓ | ✓ | str `ARS` | STATIC | ✓ | ✓ | — |
| `strength` | ✓ | ✓ | int → null `5` | PRE-DL | ✗ snapshot | ✗ always null | — |
| `strength_attack_away` | ✓ | ✓ | int `0` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `strength_attack_home` | ✓ | ✓ | int `0` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `strength_defence_away` | ✓ | ✓ | int `0` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `strength_defence_home` | ✓ | ✓ | int `0` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `strength_overall_away` | ✓ | ✓ | int `5` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `strength_overall_home` | ✓ | ✓ | int `4` | PRE-DL | ✗ snapshot | ✓ from GW3 | — |
| `team_division` | ✓ | ✓ | null | STATIC | ✓ | ✓ | — |
| `unavailable` | ✓ | ✓ | bool `False` | STATIC | ✓ | ✓ | — |
| `win` | ✓ | ✓ | int `0` | OUTCOME (cum.) | ✗ snapshot | ✓ from GW3 | — |

`strength` is an int in 2025-26 and **null for all 20 teams in 2026-27**. The six
`strength_{overall,attack,defence}_{home,away}` fields are populated in both seasons.

#### `events[]` (29 fields, 5 extracted)

| Field | 25-26 | 26-27 | Type / example | Class | As-of 25-26 | As-of 26-27 | Extracted |
|---|---|---|---|---|---|---|---|
| `average_entry_score` | ✓ | ✓ | int `50` | OUTCOME | ✓ (past GWs final) | ✓ after GW | — |
| `can_enter` | ✓ | ✓ | bool `False` | STATE | ✗ final state | ✓ per capture | — |
| `can_manage` | ✓ | ✓ | bool `False` | STATE | ✗ final state | ✓ per capture | — |
| `chip_plays` | ✓ | ✓ | list | OUTCOME | ✓ (past GWs final) | ✓ after GW | — |
| `cup_leagues_created` | ✓ | ✓ | bool `False` | STATE | ✗ final state | ✓ per capture | — |
| `data_checked` | ✓ | ✓ | bool `True` | STATE | ✗ final state | ✓ per capture | stg_gameweek.data_checked |
| `deadline_time` | ✓ | ✓ | str `2026-08-21T17:30:00Z` | STATIC | ✓ | ✓ | stg_gameweek.deadline_time |
| `deadline_time_epoch` | ✓ | ✓ | int `1787333400` | STATIC | ✓ | ✓ | — |
| `deadline_time_game_offset` | ✓ | ✓ | int `0` | STATIC | ✓ | ✓ | — |
| `finished` | ✓ | ✓ | bool `True` | STATE | ✗ final state | ✓ per capture | stg_gameweek.finished |
| `h2h_ko_matches_created` | ✓ | ✓ | bool `False` | STATE | ✗ final state | ✓ per capture | — |
| `highest_score` | ✓ | ✓ | int → int or null `131` | OUTCOME | ✓ (past GWs final) | ✓ after GW | — |
| `highest_scoring_entry` | ✓ | ✓ | int → int or null `120245` | OUTCOME | ✓ (past GWs final) | ✓ after GW | — |
| `id` | ✓ | ✓ | int `1` | STATIC | ✓ | ✓ | stg_gameweek.round |
| `is_current` | ✓ | ✓ | bool `False` | STATE | ✗ final state | ✓ per capture | stg_gameweek.is_current |
| `is_next` | ✓ | ✓ | bool `False` | STATE | ✗ final state | ✓ per capture | — |
| `is_previous` | ✓ | ✓ | bool `False` | STATE | ✗ final state | ✓ per capture | — |
| `most_captained` | ✓ | ✓ | int → int or null `411` | OUTCOME | ✓ (past GWs final) | ✓ after GW | — |
| `most_selected` | ✓ | ✓ | int → int or null `411` | OUTCOME | ✓ (past GWs final) | ✓ after GW | — |
| `most_transferred_in` | ✓ | ✓ | int → int or null `1` | OUTCOME | ✓ (past GWs final) | ✓ after GW | — |
| `most_vice_captained` | ✓ | ✓ | int → int or null `1` | OUTCOME | ✓ (past GWs final) | ✓ after GW | — |
| `name` | ✓ | ✓ | str `Gameweek 1` | STATIC | ✓ | ✓ | — |
| `overrides` | ✓ | ✓ | obj | STATIC | ✓ | ✓ | — |
| `ranked_count` | ✓ | ✓ | int `8903411` | OUTCOME | ✓ (past GWs final) | ✓ after GW | — |
| `release_time` | ✓ | ✓ | null | STATIC | ✓ | ✓ | — |
| `released` | ✓ | ✓ | bool `True` | STATE | ✗ final state | ✓ per capture | — |
| `top_element` | ✓ | ✓ | int → int or null `115` | OUTCOME | ✓ (past GWs final) | ✓ after GW | — |
| `top_element_info` | ✓ | ✓ | obj → null or obj | OUTCOME | ✓ (past GWs final) | ✓ after GW | — |
| `transfers_made` | ✓ | ✓ | int `0` | OUTCOME | ✓ (past GWs final) | ✓ after GW | — |

Nested fields on `events[]`:
- `chip_plays[]` (`chip_name`, `num_played`): OUTCOME.
- `top_element_info` (`id`, `points`): OUTCOME. Null for unplayed rounds in 2026-27.
- `overrides` (`element_types`, `pick_multiplier`, `rules`, `scoring`): STATIC.

#### `element_types[]` (13 fields, 0 extracted)

| Field | 25-26 | 26-27 | Type / example | Class | As-of 25-26 | As-of 26-27 | Extracted |
|---|---|---|---|---|---|---|---|
| `element_count` | ✓ | ✓ | int `73` | STATIC | ✓ | ✓ | — |
| `id` | ✓ | ✓ | int `1` | STATIC | ✓ | ✓ | — |
| `plural_name` | ✓ | ✓ | str `Goalkeepers` | STATIC | ✓ | ✓ | — |
| `plural_name_short` | ✓ | ✓ | str `GKP` | STATIC | ✓ | ✓ | — |
| `singular_name` | ✓ | ✓ | str `Goalkeeper` | STATIC | ✓ | ✓ | — |
| `singular_name_short` | ✓ | ✓ | str `GKP` | STATIC | ✓ | ✓ | — |
| `squad_max_play` | ✓ | ✓ | int `1` | STATIC | ✓ | ✓ | — |
| `squad_max_select` | ✓ | ✓ | null | STATIC | ✓ | ✓ | — |
| `squad_min_play` | ✓ | ✓ | int `1` | STATIC | ✓ | ✓ | — |
| `squad_min_select` | ✓ | ✓ | null | STATIC | ✓ | ✓ | — |
| `squad_select` | ✓ | ✓ | int `2` | STATIC | ✓ | ✓ | — |
| `sub_positions_locked` | ✓ | ✓ | list | STATIC | ✓ | ✓ | — |
| `ui_shirt_specific` | ✓ | ✓ | bool `True` | STATIC | ✓ | ✓ | — |

#### Other bootstrap-static sections (all STATIC game configuration, none extracted)

| Section | Leaf fields | 25-26 | 26-27 | Notes |
|---|---|---|---|---|
| `chips[]` | 7 (`id`, `name`, `number`, `chip_type`, `start_event`, `stop_event`, `overrides.*`) | ✓ | ✓ | 8 chips in both seasons |
| `phases[]` | 5 (`id`, `name`, `start_event`, `stop_event`, `highest_score`) | ✓ | ✓ | `highest_score` is OUTCOME, int → int or null |
| `element_stats[]` | 2 (`label`, `name`) | ✓ | ✓ | 26 stat labels |
| `game_settings` | 33 | ✓ | ✓ | League, squad and transfer rules, e.g. `squad_team_limit`, `squad_total_spend`, `transfers_sell_on_fee` |
| `game_config.rules` | 32 | ✓ | ✓ | Mirrors `game_settings` |
| `game_config.scoring` | 65 | ✓ | ✓ | Per-action points; per-position maps for `goals_scored`, `clean_sheets`, `goals_conceded`, `defensive_contribution`, `mng_*` |
| `game_config.settings` | 4 | 3 | 4 | **Added:** `price_change_deadlines[]` (str) |
| `game_config.status` | 1 | — | ✓ | **Added:** `price_change_last_updated` (str) |
| `total_players` | 1 | ✓ | ✓ | int |

### 1.2 fixtures

A top-level list of 380 fixtures in both seasons. 2025-26 has 380 finished; 2026-27 had 50
finished at 09-24.

| Field | 25-26 | 26-27 | Type / example | Class | As-of 25-26 | As-of 26-27 | Extracted |
|---|---|---|---|---|---|---|---|
| `code` | ✓ | ✓ | int `2645195` | STATIC | ✓ | ✓ | — |
| `event` | ✓ | ✓ | int `1` | PRE-DL | ✗ snapshot | ✓ per capture | — |
| `finished` | ✓ | ✓ | bool `True` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `finished_provisional` | ✓ | ✓ | bool `True` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `id` | ✓ | ✓ | int `1` | STATIC | ✓ | ✓ | — |
| `kickoff_time` | ✓ | ✓ | str `2026-08-21T19:00:00Z` | PRE-DL | ✗ snapshot | ✓ per capture | — |
| `minutes` | ✓ | ✓ | int `90` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `provisional_start_time` | ✓ | ✓ | bool `False` | PRE-DL | ✗ snapshot | ✓ per capture | — |
| `pulse_id` | ✓ | ✓ | int `0` | STATIC | ✓ | ✓ | — |
| `started` | ✓ | ✓ | bool `True` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `stats` | ✓ | ✓ | list | STATIC | ✓ | ✓ | — |
| `team_a` | ✓ | ✓ | int `7` | STATIC | ✓ | ✓ | — |
| `team_a_difficulty` | ✓ | ✓ | int `5` | PRE-DL | ✗ snapshot | ✓ per capture | — |
| `team_a_score` | ✓ | ✓ | int → int or null `0` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `team_h` | ✓ | ✓ | int `1` | STATIC | ✓ | ✓ | — |
| `team_h_difficulty` | ✓ | ✓ | int `2` | PRE-DL | ✗ snapshot | ✓ per capture | — |
| `team_h_score` | ✓ | ✓ | int → int or null `3` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |

`stats[]` has one entry per `identifier`:

```
assists, bonus, bps, defensive_contribution, goals_scored, own_goals,
penalties_missed, penalties_saved, red_cards, saves, yellow_cards
```

Each entry carries `h[]` and `a[]` lists of `{element, value}`. That is 5 leaf fields, all OUTCOME, in both
seasons. Nothing is extracted.

### 1.3 event-live/{gw}

`{"elements": [{id, modified, stats{…}, explain[…]}]}`: one entry per player, GW-aggregated.

| Field | 25-26 | 26-27 | Type / example | Class | As-of 25-26 | As-of 26-27 | Extracted |
|---|---|---|---|---|---|---|---|
| `assists` | ✓ | ✓ | int `0` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `bonus` | ✓ | ✓ | int `0` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `bps` | ✓ | ✓ | int `6` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `clean_sheets` | ✓ | ✓ | int `0` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `clearances_blocks_interceptions` | ✓ | ✓ | int `0` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `creativity` | ✓ | ✓ | str `0.0` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `defensive_contribution` | ✓ | ✓ | int `0` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `expected_assists` | ✓ | ✓ | str `0.00` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `expected_goal_involvements` | ✓ | ✓ | str `0.00` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `expected_goals` | ✓ | ✓ | str `0.00` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `expected_goals_conceded` | ✓ | ✓ | str `1.31` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `goals_conceded` | ✓ | ✓ | int `3` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `goals_scored` | ✓ | ✓ | int `0` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `ict_index` | ✓ | ✓ | str `2.1` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `in_dreamteam` | ✓ | ✓ | bool `False` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `influence` | ✓ | ✓ | str `20.6` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `minutes` | ✓ | ✓ | int `90` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `own_goals` | ✓ | ✓ | int `0` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `penalties_missed` | ✓ | ✓ | int `0` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `penalties_saved` | ✓ | ✓ | int `0` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `played` | — | ✓ | bool `True` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `recoveries` | ✓ | ✓ | int `14` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `red_cards` | ✓ | ✓ | int `0` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `saves` | ✓ | ✓ | int `2` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `starts` | ✓ | ✓ | int `1` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `tackles` | ✓ | ✓ | int `1` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `threat` | ✓ | ✓ | str `0.0` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `total_points` | ✓ | ✓ | int `1` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |
| `yellow_cards` | ✓ | ✓ | int `0` | OUTCOME | ✓ (post-GW) | ✓ (post-GW) | — |

- **`explain[]`** is the per-fixture points breakdown: `fixture` int, then `stats[]` with
  `identifier`, `points`, `value`, `points_modification`. It is OUTCOME and present in both
  seasons. It is the only per-fixture breakdown of points.
- `elements[].id` and `elements[].modified` are present in both seasons.
- **`stats.played`** is new in 2026-27. In the GW5 capture it is true for 302 players and false
  for 365.
- Nothing from event-live is extracted today. The warehouse has no source for it.

### 1.4 element-summary/{player}

Three arrays: `history[]` (the season so far, per fixture), `fixtures[]` (upcoming) and
`history_past[]` (prior-season totals). The field union was taken over all 841 (2025-26) and
all 667 (2026-27) payloads of each season's last run.

#### `history[]` (41 fields, 41 extracted, into `stg_player_fixture`)

| Field | 25-26 | 26-27 | Type / example | Class | As-of 25-26 | As-of 26-27 | Extracted |
|---|---|---|---|---|---|---|---|
| `assists` | ✓ | ✓ | int `0` | OUTCOME | ✓ | ✓ | stg_player_fixture.assists |
| `bonus` | ✓ | ✓ | int `0` | OUTCOME | ✓ | ✓ | stg_player_fixture.bonus |
| `bps` | ✓ | ✓ | int `6` | OUTCOME | ✓ | ✓ | stg_player_fixture.bps |
| `clean_sheets` | ✓ | ✓ | int `0` | OUTCOME | ✓ | ✓ | stg_player_fixture.clean_sheets |
| `clearances_blocks_interceptions` | ✓ | ✓ | int `1` | OUTCOME | ✓ | ✓ | stg_player_fixture.clearances_blocks_interceptions |
| `creativity` | ✓ | ✓ | str `14.6` | OUTCOME | ✓ | ✓ | stg_player_fixture.creativity |
| `defensive_contribution` | ✓ | ✓ | int `1` | OUTCOME | ✓ | ✓ | stg_player_fixture.defensive_contribution |
| `element` | ✓ | ✓ | int `379` | STATIC | ✓ | ✓ | stg_player_fixture.fpl_id |
| `expected_assists` | ✓ | ✓ | str `0.01` | OUTCOME | ✓ | ✓ | stg_player_fixture.expected_assists |
| `expected_goal_involvements` | ✓ | ✓ | str `1.10` | OUTCOME | ✓ | ✓ | stg_player_fixture.expected_goal_involvements |
| `expected_goals` | ✓ | ✓ | str `1.09` | OUTCOME | ✓ | ✓ | stg_player_fixture.expected_goals |
| `expected_goals_conceded` | ✓ | ✓ | str `1.58` | OUTCOME | ✓ | ✓ | stg_player_fixture.expected_goals_conceded |
| `fixture` | ✓ | ✓ | int `9` | STATIC | ✓ | ✓ | stg_player_fixture.fixture_id |
| `goals_conceded` | ✓ | ✓ | int `2` | OUTCOME | ✓ | ✓ | stg_player_fixture.goals_conceded |
| `goals_scored` | ✓ | ✓ | int `0` | OUTCOME | ✓ | ✓ | stg_player_fixture.goals_scored |
| `ict_index` | ✓ | ✓ | str `9.2` | OUTCOME | ✓ | ✓ | stg_player_fixture.ict_index |
| `influence` | ✓ | ✓ | str `11.4` | OUTCOME | ✓ | ✓ | stg_player_fixture.influence |
| `kickoff_time` | ✓ | ✓ | str `2026-08-23T15:30:00Z` | STATIC | ✓ | ✓ | stg_player_fixture.kickoff_time |
| `minutes` | ✓ | ✓ | int `90` | OUTCOME | ✓ | ✓ | stg_player_fixture.minutes |
| `modified` | ✓ | ✓ | bool `False` | META | ✓ | ✓ | stg_player_fixture.modified |
| `opponent_team` | ✓ | ✓ | int `17` | STATIC | ✓ | ✓ | stg_player_fixture.opponent_team_fpl_id |
| `own_goals` | ✓ | ✓ | int `0` | OUTCOME | ✓ | ✓ | stg_player_fixture.own_goals |
| `penalties_missed` | ✓ | ✓ | int `0` | OUTCOME | ✓ | ✓ | stg_player_fixture.penalties_missed |
| `penalties_saved` | ✓ | ✓ | int `0` | OUTCOME | ✓ | ✓ | stg_player_fixture.penalties_saved |
| `recoveries` | ✓ | ✓ | int `0` | OUTCOME | ✓ | ✓ | stg_player_fixture.recoveries |
| `red_cards` | ✓ | ✓ | int `0` | OUTCOME | ✓ | ✓ | stg_player_fixture.red_cards |
| `round` | ✓ | ✓ | int `1` | STATIC | ✓ | ✓ | stg_player_fixture.round |
| `saves` | ✓ | ✓ | int `0` | OUTCOME | ✓ | ✓ | stg_player_fixture.saves |
| `selected` | ✓ | ✓ | int `1493302` | PRE-DL (per round) | ✓ (INFERRED) | ✓ (INFERRED) | stg_player_fixture.selected |
| `starts` | ✓ | ✓ | int `1` | OUTCOME | ✓ | ✓ | stg_player_fixture.starts |
| `tackles` | ✓ | ✓ | int `0` | OUTCOME | ✓ | ✓ | stg_player_fixture.tackles |
| `team_a_score` | ✓ | ✓ | int `2` | OUTCOME | ✓ | ✓ | stg_player_fixture.team_a_score |
| `team_h_score` | ✓ | ✓ | int `2` | OUTCOME | ✓ | ✓ | stg_player_fixture.team_h_score |
| `threat` | ✓ | ✓ | str `66.0` | OUTCOME | ✓ | ✓ | stg_player_fixture.threat |
| `total_points` | ✓ | ✓ | int `2` | OUTCOME | ✓ | ✓ | stg_player_fixture.total_points |
| `transfers_balance` | ✓ | ✓ | int `0` | PRE-DL (per round) | ✓ (INFERRED) | ✓ (INFERRED) | stg_player_fixture.transfers_balance |
| `transfers_in` | ✓ | ✓ | int `0` | PRE-DL (per round) | ✓ (INFERRED) | ✓ (INFERRED) | stg_player_fixture.transfers_in |
| `transfers_out` | ✓ | ✓ | int `0` | PRE-DL (per round) | ✓ (INFERRED) | ✓ (INFERRED) | stg_player_fixture.transfers_out |
| `value` | ✓ | ✓ | int `90` | PRE-DL (per round) | ✓ (INFERRED) | ✓ (INFERRED) | stg_player_fixture.value |
| `was_home` | ✓ | ✓ | bool `False` | STATIC | ✓ | ✓ | stg_player_fixture.was_home |
| `yellow_cards` | ✓ | ✓ | int `0` | OUTCOME | ✓ | ✓ | stg_player_fixture.yellow_cards |

The market fields (`value`, `selected`, `transfers_*`) are published per round, so a
past round's value survives in the end-of-season snapshot. That is what makes them usable in
2025-26. Their exact as-of instant, e.g. whether `selected` is ownership at that round's
deadline, is **INFERRED** from FPL's behaviour and has not been measured against a pre-deadline
bootstrap. The influence, creativity, threat and xG family arrive as strings and are cast to
double in staging.

#### `fixtures[]` (upcoming; 14 fields, 0 extracted)

| Field | 25-26 | 26-27 | Type / example | Class | As-of 25-26 | As-of 26-27 | Extracted |
|---|---|---|---|---|---|---|---|
| `code` | — | ✓ | int `2645252` | STATIC | ✗ empty | ✓ per capture | — |
| `difficulty` | — | ✓ | int `4` | PRE-DL | ✗ empty | ✓ per capture | — |
| `event` | — | ✓ | int `6` | PRE-DL | ✗ empty | ✓ per capture | — |
| `event_name` | — | ✓ | str `Gameweek 6` | PRE-DL | ✗ empty | ✓ per capture | — |
| `finished` | — | ✓ | bool `False` | OUTCOME | ✗ empty | ✓ per capture | — |
| `id` | — | ✓ | int `58` | STATIC | ✗ empty | ✓ per capture | — |
| `is_home` | — | ✓ | bool `True` | STATIC | ✗ empty | ✓ per capture | — |
| `kickoff_time` | — | ✓ | str `2026-10-11T15:30:00Z` | PRE-DL | ✗ empty | ✓ per capture | — |
| `minutes` | — | ✓ | int `0` | OUTCOME | ✗ empty | ✓ per capture | — |
| `provisional_start_time` | — | ✓ | bool `False` | PRE-DL | ✗ empty | ✓ per capture | — |
| `team_a` | — | ✓ | int `15` | STATIC | ✗ empty | ✓ per capture | — |
| `team_a_score` | — | ✓ | null | OUTCOME | ✗ empty | ✓ per capture | — |
| `team_h` | — | ✓ | int `14` | STATIC | ✗ empty | ✓ per capture | — |
| `team_h_score` | — | ✓ | null | OUTCOME | ✗ empty | ✓ per capture | — |

**Empty for all 841 players in 2025-26**, because the snapshot was taken after GW38. In 2026-27
there are 33 entries per player.

#### `history_past[]` (31 fields, 0 extracted)

Fields: `season_name`, `element_code`, `start_cost`, `end_cost`, `total_points` and the 26
season-total stat columns (the same names as `history[]`'s outcomes). The class is
PRIOR-SEASON: closed seasons only. **No leakage in either season (OBSERVED):**
- The latest entry in the 2025-26 snapshot is `2024/25`.
- The latest entry in 2026-27 is `2025/26`.

### 1.5 event-status (2026-27 only)

`{"status": [...], "leagues": str}`. `leagues` is not extracted.

| Field | 25-26 | 26-27 | Type / example | Class | As-of 25-26 | As-of 26-27 | Extracted |
|---|---|---|---|---|---|---|---|
| `bonus_added` | — | ✓ | bool `True` | STATE | ✗ not captured | ✓ per capture | stg_event_status.bonus_added |
| `date` | — | ✓ | str `2026-09-18` | STATE | ✗ not captured | ✓ per capture | stg_event_status.match_date |
| `event` | — | ✓ | int `5` | STATE | ✗ not captured | ✓ per capture | stg_event_status.round |
| `points` | — | ✓ | str `r` | STATE | ✗ not captured | ✓ per capture | stg_event_status.points |

### 1.6 Staging coverage (OBSERVED)

| stg model | Source collection | Extracted / available | % | Reads 25-26? | Reads 26-27? |
|---|---|---|---|---|---|
| `stg_player` | bootstrap `elements[]` | 4 / 109 | 3.7% | ✓ | ✓ |
| `stg_gameweek` | bootstrap `events[]` | 5 / 29 | 17.2% | ✓ | ✓ |
| `stg_player_fixture` | element-summary `history[]` | 41 / 41 | 100% | ✓ | ✓ |
| `stg_event_status` | event-status `status[]` | 4 / 4 (`leagues` not read) | 100% | n/a (not captured) | ✓ |
| — | bootstrap `teams[]`, `element_types[]`, `chips`, `phases`, `element_stats`, `game_*` | 0 | 0% | | |
| — | **fixtures** (whole endpoint) | 0 / 17 + `stats[]` | 0% | | |
| — | **event-live** (whole endpoint) | 0 / 29 + `explain[]` | 0% | | |
| — | element-summary `fixtures[]`, `history_past[]` | 0 | 0% | | |

`sources.yml` declares three sources: `element_summary`, `bootstrap_static` and `event_status`.
It declares none for fixtures or event-live.

---

## Part 2 — Season mismatch

### 2.1 Schema drift per endpoint (OBSERVED)

| Endpoint | Added in 2026-27 | Removed | Type or nullability change |
|---|---|---|---|
| bootstrap-static | `elements[].price_change_calibrating`, `price_change_hourly_rate`, `price_change_locked_until`, `price_change_projections[]{offset, projected_percent, likelihood}`. `game_config.settings.price_change_deadlines[]`. `game_config.status.price_change_last_updated`. `scout_risks[]` gains entries. | none | `teams[].strength` int → **always null**. `ep_next` null or str → str. `events[]` outcome fields (`highest_score`, `most_*`, `top_element*`) become nullable, because future rounds are unplayed. `phases[].highest_score` also becomes nullable. |
| fixtures | none | none | `team_h_score` and `team_a_score` become nullable (unplayed fixtures) |
| event-live | `elements[].stats.played` (bool) | none | none |
| element-summary | none in the schema. `fixtures[]` is populated in 26-27 and empty in 25-26 (a content difference) | none | none |
| event-status | the whole endpoint (no 25-26 capture exists) | — | — |

Apart from `teams[].strength`, every nullability change is mid-season against end-of-season
content, not a change in FPL's schema. No field present in 2025-26 is absent in 2026-27.

### 2.2 Capture-profile differences that change usability (OBSERVED)

1. **2025-26 is one post-GW38 snapshot.** Every bootstrap `elements[]`, `teams[]` and `events[]`
   field shows its end-of-season value. So do fixture difficulty and kickoff times. Only
   per-round arrays (element-summary `history[]`, event-live per GW) carry per-GW history.
2. **2026-27 has repeated captures,** with pre-deadline bootstrap and fixtures for GW3–5 (§1.0).
   GW1–2 are unrecoverable: capture began 2026-08-29.
3. **event-status has no 2025-26 capture.** The warehouse substitutes the `closed_seasons` var.
4. **element-summary capture has stopped for now.** The latest capture is 2026-09-21, and the
   settle-once policy means `fixtures[]` (upcoming difficulty) will no longer refresh per
   capture.

### 2.3 New in 2026-27: fields that are leakage-free only this season

| Field(s) | Why only 2026-27 | Earliest usable GW |
|---|---|---|
| `elements[].status`, `chance_of_playing_this_round`, `chance_of_playing_next_round`, `news`, `news_added` | 2025-26 has only the end-of-season value | GW3 |
| `elements[].now_cost`, `cost_change_*`, `selected_by_percent`, `transfers_*_event`, `ep_this`, `ep_next`, `form` | same | GW3 |
| `elements[].price_change_*`, `scout_risks[]` | the fields are new (or empty in 25-26) | GW3 |
| `elements[].team` (as-of club) | snapshot in 25-26 (9 changes seen in 26-27 already) | GW3 |
| `teams[].strength_*`, fixture `team_*_difficulty`, `kickoff_time` | snapshot in 25-26. No difficulty change was seen across 4 weeks of 26-27, but 25-26's in-season values are **unverifiable** | GW3 |
| event-status | not captured in 25-26 | GW2 (first capture 08-29) |
| event-live `stats.played` | new field | GW1 |

This confirms the expectation stated in the task. Per-gameweek availability, per-deadline price
and per-deadline ownership exist leakage-free **only** in 2026-27, from GW3. Price and ownership
**per round** also exist for 2025-26 through `history[].value` and `history[].selected`, which
are already staged. The availability family has no 2025-26 per-GW source anywhere in the bucket
or the archive (OBSERVED for `archive/2025-26/fpl.db`: its `players` table is the same snapshot, with 841
rows and 563 `status = 'a'`, identical to the history bootstrap).

### 2.4 Consequence per field class

| Field class | 2025-26 backtest | 2026-27 prospective |
|---|---|---|
| element-summary `history[]` (all 41, incl. `value` and `selected` per round) | ✓ | ✓ |
| event-live `stats` and `explain` | ✓ (all 38 GWs, final) | ✓ (once per GW post-ratification) |
| fixtures outcome fields, `event`, `team_h`, `team_a` | ✓ | ✓ |
| fixture difficulty, team `strength_*` | ⚠ end-of-season values only; leakage-free only if FPL never revised them (unverified) | ✓ as-of |
| bootstrap availability, price, ownership, `form`, `ep_*`, `team` | ✗ | ✓ from GW3 |
| bootstrap STATIC (`code`, names, `element_type`) | ✓ (`element_type` stable: INFERRED, 0 changes observed in 26-27) | ✓ |
| event-status | n/a (the var override) | ✓ |

---

## Part 3 — Demand gap (fpl-intelligence)

fpl-intelligence currently reads the SQLite-era `fpl.db` through six staging contracts
(`dal/staging/contracts/*.yaml`, 146 source columns). It builds a 64-column
`(player_id, gw)` mart from them (`~/.fpl/fpl.mart.parquet`, 31,958 rows, 2025-26 only). It
does not read `served/` yet.

**Status key:**
- **SERVED:** in `fct_player_fixture` or `fct_player_gameweek`.
- **STG:** in a staging model but not served.
- **RAW:** in raw S3 but not extracted.
- **DERIVED:** computable from served columns.
- **INTEL:** computed inside intelligence from other mart columns.
- **NONE:** not available anywhere.

### 3.1 Staging-contract source columns (146)

| Contract (source) | SERVED | STG only | RAW only | NONE |
|---|---|---|---|---|
| `player_histories` (41; element-summary `history[]`) | 40: every column except `in_dreamteam`. Renames: `element_id`→`fpl_id`, `fixture`→`fixture_id`, `opponent_team`→`opponent_team_fpl_id` | — | `in_dreamteam`: not in `history[]`; event-live `stats.in_dreamteam` is the only raw carrier. The SQLite lineage is INFERRED. Per-GW grain, not per-fixture | — |
| `players` (46; bootstrap `elements[]`) | `web_name` (`fct_player_gameweek.web_name`) | `id`, `code`, `total_points` (`stg_player`) | the other 42: `first_name`, `second_name`, `team`, `element_type`, `now_cost`, `status`, `event_points`, 17 cumulative stats, `form`, `points_per_game`, `selected_by_percent`, `transfers_in`, `transfers_out`, `transfers_in_event`, `transfers_out_event`, `cost_change_event`, `cost_change_start`, `chance_of_playing_next_round`, `chance_of_playing_this_round`, `news`, `team_join_date` | — |
| `events` (18; bootstrap `events[]`) | `deadline_time` | `id`, `finished`, `data_checked`, `is_current` (`stg_gameweek`) | `name`, `deadline_time_epoch`, `is_previous`, `is_next`, `average_entry_score`, `highest_score`, `transfers_made`, `most_selected`, `most_transferred_in`, `most_captained`, `most_vice_captained`, `top_element`, `top_element_points` (= `top_element_info.points`) | — |
| `fixtures` (14; fixtures endpoint) | partially at player grain: `id`, `event`, `kickoff_time` and both scores ride on `fct_player_fixture` | — | all 14 at fixture grain, incl. `team_h`, `team_a`, `team_h_difficulty`, `team_a_difficulty`, `started`, `finished`, `finished_provisional`, `minutes`, `code` | — |
| `teams` (18; bootstrap `teams[]`) | — | — | all 18 | `strength` is null for every team in 2026-27, so it is effectively NONE for the live season |
| `element_types` (9; bootstrap `element_types[]`) | — | — | all 9 | — |

### 3.2 Mart columns (64)

| Mart column(s) | Warehouse status | Definition or grain mismatch |
|---|---|---|
| `player_id`, `gw` | SERVED (`fpl_id`, `round`) | The warehouse grain adds `season`, and the served tables hold both seasons. An unfiltered group-by on `fpl_id` or `round` merges seasons. |
| `player_name` | SERVED (`web_name`) | — |
| `position_code`, `position_label`, `position` | **RAW** (`elements[].element_type`, `element_types[]`) | — |
| `team_id` | **RAW** | Intelligence resolves it per fixture from fixtures `team_h`/`team_a`, because `players.team` is a snapshot. The warehouse has neither. |
| `purchase_price` | SERVED (`value`) | Integer tenths vs float £ (÷10). **DGW rule differs:** intelligence takes the first fixture, the warehouse `max_by(kickoff_time)` (last). **Blank rounds:** intelligence forward-fills from a later round, the warehouse gives NULL. |
| `ownership_count`, `transfers_in`, `transfers_out` | SERVED (`selected`, `transfers_*`) | Same DGW last-vs-first difference. |
| `total_points`, `minutes`, `goals_scored`, `assists`, `clean_sheets`, `yellow_cards`, `red_cards`, `saves`, `bonus`, `bps`, `goals_conceded`, `starts`, `penalties_saved`, `own_goals`, `penalties_missed`, `tackles`, `clearances_blocks_interceptions`, `recoveries`, `defensive_contribution`, `influence`, `creativity`, `threat`, `ict_index` | SERVED | **Blank-round null semantics differ.** Intelligence keeps these NULL on BGW rows ("NULL = context does not exist", `dal/README.md:76`). `fct_player_gameweek` coalesces to **0**. `fixture_count = 0` distinguishes them. |
| `xg`, `xa`, `xgi`, `xgc` | SERVED (`expected_goals`, `expected_assists`, `expected_goal_involvements`, `expected_goals_conceded`) | Renames only, plus the same BGW 0-vs-NULL difference. |
| `fixture_count` | SERVED | — |
| `is_bgw`, `is_dgw`, `fixture_context` | DERIVED (`fixture_count` = 0, ≥2) | — |
| `was_home`, `home_count`, `away_count` | DERIVED from `fct_player_fixture.was_home` | Not on `fct_player_gameweek`. |
| `fdr_avg` | **RAW** (fixtures `team_*_difficulty`) | 2025-26 values are end-of-season (§2.4). |
| `deadline_time` | SERVED | — |
| `finished`, `is_live` (`is_current`) | STG (`stg_gameweek`) | These are capture-time state. In a 2025-26 snapshot every round is `finished` and only GW38 `is_current`. |
| `is_previous`, `is_next` | **RAW** | Same capture-time caveat. |
| `minutes_roll3/5/8`, `xgi_roll3/5`, `xgc_roll3/5`, `clean_sheets_roll3/5`, `goals_conceded_roll3/5`, `minutes_trend`, `is_warmup_gw` | INTEL | Inputs are SERVED, but the BGW 0-vs-NULL difference changes the rolling windows. |

Totals (distinct columns, 64):
- **SERVED:** 36, incl. the 4 xG renames.
- **DERIVED:** 5 (`is_bgw`, `is_dgw`, `was_home`, `home_count`, `away_count`).
- **STG:** 2 (`finished`, `is_live`).
- **RAW:** 7 (`position_code`, `position_label`, `position`, `team_id`, `fdr_avg`,
  `is_previous`, `is_next`).
- **INTEL:** 14 (the 11 rolling columns, `minutes_trend`, `is_warmup_gw`, `fixture_context`).
- **NONE:** 0.

### 3.3 Starting XI slice: documented needs

Source: `decisions/starting_xi/INVENTORY.md` §2.2, §2.5–2.7, §2.10, §2.12, and `DESIGN.md` §6.2.

| Need | Warehouse today | Note |
|---|---|---|
| Availability signal | **RAW only, prospective only** | `DESIGN.md` §6.2 *forbids* rankers from reading `status` and `chance_of_playing`: "a ranker reaching outside the mart for them would be reading a post-season snapshot against every gameweek". That is correct for 2025-26 (§2.3). A leakage-free per-deadline signal exists only for 2026-27 GW3+. |
| Minutes (incl. NULL vs 0) | SERVED | The BGW 0-vs-NULL mismatch (§3.2) affects the NULL-vs-0 semantics INVENTORY §2.5 depends on. |
| Position (legality, formations) | **RAW** | `element_type` plus the `element_types[]` squad limits. |
| Price (budget) | SERVED (`value`) | ÷10. Blank or prefix rows are NULL in the warehouse, where intelligence forward-fills (INVENTORY §2.7 records that forward-fill as a later-season value). |
| Fixture context (BGW, DGW, home/away, difficulty) | `fixture_count` SERVED; `was_home` DERIVED; difficulty **RAW** | — |
| Club (3-per-club rule) | **RAW** | `team_id`, per fixture via the fixtures endpoint. |

---

## Part 4 — RECOMMENDATION

*Everything in this part is a proposal. Parts 1–3 are the evidence.*

### Tier 1: needed by a named consumer now

| # | Field(s) | Consumer | Target | Grain | Season caveat |
|---|---|---|---|---|---|
| 1 | `elements[].element_type` → `position_code`, and served `position_code` on both `fct_` models | Intelligence mart `position_code`/`position_label`/`position`; Starting XI position legality (INVENTORY §2.2, §2.12) | new column on `stg_player`; carried through `int_player_gameweek_spine` exactly as `web_name` is; plus a served column | capture (stg) → `(season, fpl_id)` | Both seasons. Assumes position is fixed within a season (0 changes observed in 26-27); add a test asserting one `element_type` per `(season, fpl_id)` |
| 2 | fixtures endpoint: `id`, `code`, `event`, `team_h`, `team_a`, `team_h_difficulty`, `team_a_difficulty`, `kickoff_time`, `team_h_score`, `team_a_score`, `started`, `finished`, `finished_provisional`, `minutes` | Intelligence `fdr_avg`, `team_id` resolution, `fixtures.yaml`; Starting XI fixture context and 3-per-club | **new model** `stg_fixture` + new `fixtures` source reading both trees | `(season, fixture_id, capture)` | Both seasons for identity, teams and scores. **Difficulty in 2025-26 is end-of-season only**, so it must be documented as not as-of for backtests |
| 3 | per-fixture `team_fpl_id` on `fct_player_fixture` (from #2: `team_h` if `was_home` else `team_a`) | Intelligence `team_id`; Starting XI club limit | served column | `(season, fpl_id, fixture_id)` | Both seasons, and as-of by construction. This avoids warehouse known-bug #1 (team resolved at build time) |

### Tier 2: cheap and plausibly needed soon

| Field(s) | Why | Target | Grain | Caveat |
|---|---|---|---|---|
| `element_types[]` (`id`, `singular_name_short`, `squad_select`, `squad_min_play`, `squad_max_play`) | Position label and formation limits for Starting XI | a seed, or a small `stg_element_type` | `(season, element_type)` | Both seasons (STATIC) |
| `elements[].status`, `chance_of_playing_this_round`, `chance_of_playing_next_round`, `news`, `news_added` | The Starting XI availability gap. **Not Tier 1:** the only named consumer currently forbids reading it (DESIGN §6.2), and it cannot feed any 2025-26 backtest | columns on `stg_player` (capture grain), then a **new model** selecting the latest capture before each deadline (`int_player_deadline_snapshot` or similar) | `(season, fpl_id, round)` as-of deadline | **Prospective only, 2026-27 GW3+.** Deadline selection must go by capture time, because pre-09-24 manifests carry no `trigger` |
| `elements[].now_cost`, `selected_by_percent`, `transfers_in_event`, `transfers_out_event`, `cost_change_event`, `form`, `ep_next`, `team` | Per-capture market state; the scoped-out `fct_player_market_daily` idea | **new model**, not new columns on a served fact | `(season, fpl_id, capture)` | Prospective only. Per-round price and ownership for both seasons are **already served** (`value`, `selected`) |
| `events[].is_previous`, `is_next` on `stg_gameweek` | Intelligence mart parity | `stg_gameweek` columns | capture | Capture-time state; meaningless per GW for 2025-26 |
| `elements[].team` on `stg_player` | Consistency check for Tier 1 #3 (bootstrap club vs fixture-derived club) | `stg_player` column | capture | Never to be served as per-GW team |

### Tier 3: available, no current consumer (leave in raw)

- event-live `stats` and `explain[]`, including `in_dreamteam` and `played`. They duplicate
  `history[]` except for the points breakdown.
- fixtures `stats[]`.
- `teams[]`, including `strength_*`. Intelligence stages them, but nothing reaches the mart.
- `events[]` crowd aggregates (`average_entry_score`, `most_*`, `top_element*`, `chip_plays`).
- bootstrap cumulative season stats, `*_per_90`, `*_rank*`.
- `price_change_*` and `scout_risks[]`.
- element-summary `fixtures[]` (redundant with #2) and `history_past[]`.
- `chips`, `phases`, `element_stats`, `game_settings`, `game_config`.
- event-status `leagues`.

### Smallest first PR

**Tier 1 #1, position only.** The PR adds:
- `cast(e.element_type as integer) as position_code` to `stg_player`;
- the column carried through `int_player_gameweek_spine` (the same latest-capture pick as
  `web_name`) onto `fct_player_gameweek`;
- one entry in `models/marts/schema.yml` (the enforced contract);
- a unit test asserting a single `position_code` per `(season, fpl_id)` across captures.

No new source is needed and the model count does not change. Both seasons are covered by the
existing globs.

The fixture tree needs no change. All five checked-in bootstrap payloads, live and 2025-26,
already carry `element_type` (verified).

The fixtures endpoint (#2, #3) is the second PR. It needs a new source, a new stg model, and a
contract addition on `fct_player_fixture`.
