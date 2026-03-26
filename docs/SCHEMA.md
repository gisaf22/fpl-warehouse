# FPL Warehouse — Schema Documentation

## Overview

The warehouse merges two source databases into a unified star schema:

| Source | Database | Tables |
|--------|----------|--------|
| FPL API | `~/Documents/FPL/data/fpl/fpl.db` | 10 tables |
| Understat | `~/Documents/FPL/data/understat/understat.db` | 4 tables |
| **Warehouse** | **`~/Documents/FPL/data/warehouse/master.db`** | **6 tables** |

---

## Target Schema (Warehouse)

### `dim_teams`

Unified team dimension linking FPL and Understat naming conventions.

| Column | Type | Description |
|--------|------|-------------|
| `team_id` | INTEGER PK | Warehouse surrogate key (auto-increment) |
| `fpl_id` | INTEGER | FPL team ID |
| `fpl_name` | TEXT | FPL team name (e.g., "Man City", "Spurs") |
| `understat_name` | TEXT | Understat team name (e.g., "Manchester City", "Tottenham") |
| `short_name` | TEXT | 3-letter abbreviation |

**Source:** FPL `teams` table + hardcoded FPL↔Understat name mapping.

---

### `dim_players`

Player dimension with cross-source fuzzy matching.

| Column | Type | Description |
|--------|------|-------------|
| `player_id` | INTEGER PK | Warehouse surrogate key (auto-increment) |
| `fpl_id` | INTEGER | FPL player ID (UNIQUE) |
| `understat_id` | INTEGER | Understat player ID (NULL if unmatched) |
| `web_name` | TEXT | FPL short display name (e.g., "Salah", "White") |
| `fpl_name` | TEXT | FPL full name — `first_name + second_name` (e.g., "Mohamed Salah", "Benjamin White") |
| `understat_name` | TEXT | Understat full name (e.g., "Mohamed Salah"), NULL if unmatched |
| `team_id` | INTEGER | FK → `dim_teams.team_id` |
| `confidence` | INTEGER | Fuzzy match score (0–100), NULL if unmatched |

**Source:** FPL `players` table + Understat `rosters` table, linked via 6-tier matching (manual overrides → exact → accent-stripped → fuzzy + position guard → surname + team → cross-team fuzzy). 518 of 820 players matched at default threshold of 75.

---

### `fact_player_gw`

Per-player, per-gameweek performance facts from FPL.

| Column | Type | Description |
|--------|------|-------------|
| `fpl_id` | INTEGER | FK → `dim_players.fpl_id` |
| `round` | INTEGER | Gameweek number |
| `minutes` | INTEGER | Minutes played |
| `goals_scored` | INTEGER | Goals |
| `assists` | INTEGER | Assists |
| `clean_sheets` | INTEGER | Clean sheets |
| `goals_conceded` | INTEGER | Goals conceded |
| `bonus` | INTEGER | Bonus points |
| `bps` | INTEGER | Bonus points system score |
| `total_points` | INTEGER | FPL points earned |
| `value` | INTEGER | Player price (÷10 for £m) |
| `selected` | INTEGER | Number of managers who selected |
| `transfers_in` | INTEGER | Transfers in that GW |
| `transfers_out` | INTEGER | Transfers out that GW |
| `fpl_xg` | REAL | FPL xG |
| `fpl_xa` | REAL | FPL xA |
| `fpl_xgi` | REAL | FPL xGI (xG + xA) |
| `expected_goals_conceded` | REAL | FPL xGC |
| `influence` | REAL | ICT influence score |
| `creativity` | REAL | ICT creativity score |
| `threat` | REAL | ICT threat score |
| `ict_index` | REAL | Combined ICT index |
| `starts` | INTEGER | Whether played from start |
| `tackles` | INTEGER | Tackles made |
| `recoveries` | INTEGER | Ball recoveries |
| `clearances_blocks_interceptions` | INTEGER | Combined defensive actions |
| `defensive_contribution` | INTEGER | FPL defensive contribution score |
| `us_xg` | REAL | Understat xG — uses a different model than FPL (summed across matches in DGWs) |
| `us_xa` | REAL | Understat xA — uses a different model than FPL (summed across matches in DGWs) |
| `us_xgi` | REAL | Understat xGI — `us_xg + us_xa` (summed across matches in DGWs) |
| `xg_chain` | REAL | Understat xGChain — xG of possessions player was involved in (summed across matches in DGWs) |
| `xg_buildup` | REAL | Understat xGBuildup — xGChain minus shot-taker and assister (summed across matches in DGWs) |

**UNIQUE constraint:** `(fpl_id, round)`
**Source:** FPL `gameweeks` table for all FPL columns (`element_id` renamed to `fpl_id`). Understat columns (`us_xg`, `us_xa`, `us_xgi`, `xg_chain`, `xg_buildup`) enriched from Understat `rosters` table via fixture bridge (Understat `match_id` → FPL `event` via team + date matching). In DGWs, Understat values are summed across both matches to match FPL's aggregated GW row.

---

### `fact_shots`

Individual shot events from Understat with expected-goals data.

| Column | Type | Description |
|--------|------|-------------|
| `shot_id` | INTEGER PK | Understat shot ID |
| `match_id` | INTEGER | Understat match ID |
| `understat_player_id` | INTEGER | FK → `dim_players.understat_id` |
| `minute` | INTEGER | Minute of shot |
| `result` | TEXT | Outcome (Goal, SavedShot, MissedShots, BlockedShot, etc.) |
| `x` | REAL | Pitch x-coordinate (0–1) |
| `y` | REAL | Pitch y-coordinate (0–1) |
| `xg` | REAL | Expected goals value for the shot |
| `situation` | TEXT | Play type (OpenPlay, FromCorner, SetPiece, DirectFreekick, Penalty) |
| `shot_type` | TEXT | Shot type (RightFoot, LeftFoot, Head) |
| `player` | TEXT | Player name |
| `h_a` | TEXT | Home/away indicator |
| `player_assisted` | TEXT | Assisting player name |
| `last_action` | TEXT | Action before shot (Pass, Cross, TakeOn, etc.) |
| `season` | TEXT | Season identifier |

**Source:** Understat `shots` table. Columns renamed: `X`→`x`, `Y`→`y`, `xG`→`xg`, `shotType`→`shot_type`, `lastAction`→`last_action`, `player_id`→`understat_player_id`.

---

### `fact_fixtures`

Match-level fixture data from FPL.

| Column | Type | Description |
|--------|------|-------------|
| `fixture_id` | INTEGER PK | FPL fixture ID |
| `event` | INTEGER | Gameweek number |
| `home_team_id` | INTEGER | FPL home team ID |
| `away_team_id` | INTEGER | FPL away team ID |
| `home_score` | INTEGER | Home goals |
| `away_score` | INTEGER | Away goals |
| `kickoff_time` | TEXT | ISO kickoff timestamp |
| `finished` | INTEGER | 1 if match complete |
| `home_difficulty` | INTEGER | FDR home (1–5) |
| `away_difficulty` | INTEGER | FDR away (1–5) |

**Source:** FPL `fixtures` table. Columns renamed: `id`→`fixture_id`, `team_h`→`home_team_id`, `team_a`→`away_team_id`, `team_h_score`→`home_score`, `team_a_score`→`away_score`, `team_h_difficulty`→`home_difficulty`, `team_a_difficulty`→`away_difficulty`.

---

### `fact_match_stats`

Match-level team stats from Understat, bridged to FPL fixtures.

| Column | Type | Description |
|--------|------|-------------|
| `understat_match_id` | INTEGER PK | Understat match ID |
| `fpl_fixture_id` | INTEGER | FK → `fact_fixtures.fixture_id` (bridge key) |
| `event` | INTEGER | FPL gameweek number |
| `home_team` | TEXT | Understat home team name |
| `away_team` | TEXT | Understat away team name |
| `home_goals` | INTEGER | Home goals scored |
| `away_goals` | INTEGER | Away goals scored |
| `home_xg` | REAL | Home team total xG |
| `away_xg` | REAL | Away team total xG |
| `home_ppda` | REAL | Home PPDA (passes allowed per defensive action — lower = more pressing) |
| `away_ppda` | REAL | Away PPDA |
| `home_deep` | INTEGER | Home deep completions (passes within 20 yards of goal) |
| `away_deep` | INTEGER | Away deep completions |
| `home_shots` | INTEGER | Home total shots |
| `away_shots` | INTEGER | Away total shots |
| `home_sot` | INTEGER | Home shots on target |
| `away_sot` | INTEGER | Away shots on target |
| `prob_home` | REAL | Pre-match home win probability |
| `prob_draw` | REAL | Pre-match draw probability |
| `prob_away` | REAL | Pre-match away win probability |
| `datetime` | TEXT | Match datetime |

**Source:** Understat `match_info` table. Bridged to FPL via team name mapping (`dim_teams`) + date matching. 291/291 matches successfully bridged.

---

### Fixture Bridge

The fixture bridge is an internal mapping (not a persisted table) that links Understat `match_id` → FPL `fixture_id` + `event` (GW round). It works by:

1. Resolving FPL team IDs to Understat team names via `dim_teams`
2. Matching on `(home_team, away_team, date)` — date extracted from kickoff timestamps
3. Used by `fact_match_stats` (to populate `fpl_fixture_id` + `event`) and `fact_player_gw` (to aggregate Understat roster xGChain/xGBuildup by GW round)

---

## Source Schemas — What Was Ingested vs Rejected

### FPL Source (`fpl.db`) — 10 tables

#### `players` — 105 columns

**Ingested into warehouse (via `dim_players`):**

| Column | Used As |
|--------|---------|
| `id` | `dim_players.fpl_id` |
| `first_name` | `dim_players.fpl_name` (combined as `first_name + second_name`) |
| `second_name` | `dim_players.fpl_name` (combined as `first_name + second_name`) |
| `web_name` | `dim_players.web_name` |
| `team` | Resolved to `dim_players.team_id` |

**Rejected (not carried to warehouse):**

| Column | Reason |
|--------|--------|
| `known_name` | Redundant with `web_name` |
| `team_code`, `code`, `opta_code`, `pulse_id` | Internal FPL/Opta identifiers — no analytical value |
| `element_type` | Available via `element_types` table if needed; not denormalized |
| `now_cost`, `status` | Point-in-time snapshot values — GW-level `value` in `fact_player_gw` is more useful |
| `photo`, `birth_date`, `team_join_date` | Biographical metadata |
| `region`, `squad_number`, `special` | Low analytical value |
| `removed`, `can_transact`, `can_select`, `has_temporary_code` | UI/transaction flags |
| `total_points`, `event_points`, `minutes`, `goals_scored`, `assists`, etc. (season totals) | Aggregatable from `fact_player_gw` — storing both would create inconsistency |
| `*_per_90` columns (8 fields) | Derivable from `fact_player_gw` minutes + raw stats |
| `*_rank`, `*_rank_type` columns (16 fields) | Point-in-time rankings — stale after each GW |
| `form`, `points_per_game`, `value_form`, `value_season` | Derivable from `fact_player_gw` |
| `selected_by_percent`, `ep_next`, `ep_this`, `price_change_percent` | Ephemeral prediction values — change every GW |
| `chance_of_playing_*` | Ephemeral availability flags |
| `transfers_in`, `transfers_out`, `transfers_in_event`, `transfers_out_event` | Season-level transfer totals; GW-level transfers in `fact_player_gw` |
| `cost_change_*` columns (4 fields) | Price movement — derivable from `fact_player_gw.value` across GWs |
| `penalties_order`, `penalties_text`, `corners_*`, `direct_freekicks_*` | Set-piece order metadata — changes frequently |
| `news`, `news_added` | Free-text injury/availability news |

#### `teams` — 21 columns

**Ingested into warehouse (via `dim_teams`):**

| Column | Used As |
|--------|---------|
| `id` | `dim_teams.fpl_id` |
| `name` | `dim_teams.fpl_name` + Understat name mapping key |
| `short_name` | `dim_teams.short_name` |

**Rejected:**

| Column | Reason |
|--------|--------|
| `code`, `pulse_id` | Internal identifiers |
| `strength`, `strength_overall_*`, `strength_attack_*`, `strength_defence_*` (7 fields) | FPL's internal strength ratings — opaque, change in-season |
| `played`, `win`, `draw`, `loss`, `points`, `position` | League table — derivable from `fact_fixtures` |
| `form` | Derivable from results |
| `team_division`, `unavailable` | Administrative flags |

#### `gameweeks` — 41 columns

**Ingested into `fact_player_gw` (27 of 41 columns):**

`element_id` (as `fpl_id`), `round`, `minutes`, `goals_scored`, `assists`, `clean_sheets`, `goals_conceded`, `bonus`, `bps`, `total_points`, `value`, `selected`, `transfers_in`, `transfers_out`, `expected_goals` (as `fpl_xg`), `expected_assists` (as `fpl_xa`), `expected_goal_involvements` (as `fpl_xgi`), `expected_goals_conceded`, `influence`, `creativity`, `threat`, `ict_index`, `starts`, `tackles`, `recoveries`, `clearances_blocks_interceptions`, `defensive_contribution`

Additionally, `us_xg`, `us_xa`, `us_xgi`, `xg_chain`, and `xg_buildup` are enriched from Understat `rosters` via the fixture bridge.

**Rejected:**

| Column | Reason |
|--------|--------|
| `own_goals`, `penalties_saved`, `penalties_missed` | Rare events — low signal for most analyses |
| `yellow_cards`, `red_cards`, `saves` | Available if needed; excluded to keep fact table focused |
| `in_dreamteam` | FPL game feature, not performance data |
| `fixture`, `opponent_team`, `was_home` | Match context — joinable via `fact_fixtures` + `round` |
| `kickoff_time`, `team_h_score`, `team_a_score` | Duplicated from `fact_fixtures` |
| `transfers_balance` | Derivable: `transfers_in - transfers_out` |

#### `fixtures` — 16 columns

**Ingested into `fact_fixtures` (10 of 16 columns):**

`id` (as `fixture_id`), `event`, `team_h` (as `home_team_id`), `team_a` (as `away_team_id`), `team_h_score` (as `home_score`), `team_a_score` (as `away_score`), `kickoff_time`, `finished`, `team_h_difficulty` (as `home_difficulty`), `team_a_difficulty` (as `away_difficulty`)

**Rejected:**

| Column | Reason |
|--------|--------|
| `code`, `pulse_id` | Internal identifiers |
| `minutes`, `started`, `finished_provisional`, `provisional_start_time` | Match lifecycle metadata |

#### Tables not carried to warehouse

| Table | Rows | Reason |
|-------|------|--------|
| `fixture_stats` | 20,051 | Per-player fixture stats (goals, assists, bonus, saves). Granular data available via `fact_player_gw` join on `round` — redundant. |
| `events` | 38 | Gameweek metadata (deadlines, chip_plays, most_captained). FPL game-management data, not performance data. |
| `element_types` | 4 | Position definitions (GKP/DEF/MID/FWD). Static reference data — only 4 rows, better as application constants. |
| `phases` | 11 | Season phase groupings. Administrative structure. |
| `explain_stats` | 29,987 | FPL points breakdown per stat type. Useful for understanding FPL scoring but not for performance analytics. |
| `player_history` | 2,345 | Historical season totals. Prior-season data — useful but out of scope for current-season warehouse. |

---

### Understat Source (`understat.db`) — 4 tables

#### `shots` — 17 columns

**Ingested into `fact_shots` (15 of 17 columns):**

`id` (as `shot_id`), `match_id`, `player_id` (as `understat_player_id`), `minute`, `result`, `X` (as `x`), `Y` (as `y`), `xG` (as `xg`), `situation`, `shotType` (as `shot_type`), `player`, `h_a`, `player_assisted`, `lastAction` (as `last_action`), `season`

**Rejected:**

| Column | Reason |
|--------|--------|
| `h_team` | Home team name — joinable via `match_id` → `fact_fixtures` |
| `a_team` | Away team name — same reason |

#### `rosters` — 21 columns

**Used for player matching + xGChain/xGBuildup enrichment.**

| Column | Used For |
|--------|----------|
| `player_id` | `dim_players.understat_id` + key for xG enrichment |
| `player` | Fuzzy name matching against FPL names |
| `team_id`, `h_a` + match join | Determining player's team for team-scoped matching |
| `match_id` | Joined to fixture bridge for GW mapping |
| `xGChain` | Summed per GW → `fact_player_gw.xg_chain` |
| `xGBuildup` | Summed per GW → `fact_player_gw.xg_buildup` |

**Rejected:**

| Column | Reason |
|--------|--------|
| `position`, `positionOrder` | Match-level roster metadata |
| `goals`, `own_goals`, `assists`, `shots`, `key_passes` | Per-match stats — aggregatable from `fact_shots` |
| `xG`, `xA` | Per-match xG/xA — `fact_shots` has shot-level granularity, `fact_player_gw` has GW-level |
| `yellow_card`, `red_card` | Discipline data |
| `time`, `roster_in`, `roster_out` | Substitution data |

#### `matches` — 11 columns

**Not carried to warehouse.**

| Column | Reason |
|--------|--------|
| All columns | Match metadata (teams, scores, xG totals). `fact_fixtures` covers match results from FPL side. Understat match-level xG (`home_xg`, `away_xg`) can be derived by summing `fact_shots.xg` per match. |

#### `match_info` — 19 columns

**Ingested into `fact_match_stats` (all 19 columns):**

All columns carried to warehouse. `match_id` becomes `understat_match_id`. Enriched with `fpl_fixture_id` and `event` via the fixture bridge.

| Column | Warehouse Column |
|--------|------------------|
| `match_id` | `understat_match_id` |
| `home_team`, `away_team` | Kept as-is (Understat names) |
| `home_goals`, `away_goals` | Kept as-is |
| `home_xg`, `away_xg` | Kept as-is |
| `home_ppda`, `away_ppda` | Kept as-is |
| `home_deep`, `away_deep` | Kept as-is |
| `home_shots`, `away_shots` | Kept as-is |
| `home_sot`, `away_sot` | Kept as-is |
| `prob_home`, `prob_draw`, `prob_away` | Kept as-is |
| `datetime` | Kept as-is |

---

## Joining Across Sources

The primary join path from FPL to Understat data:

```
fact_player_gw.fpl_id
    → dim_players.fpl_id / dim_players.understat_id
        → fact_shots.understat_player_id

fact_match_stats.fpl_fixture_id
    → fact_fixtures.fixture_id
    → fact_fixtures.event = fact_player_gw.round
```

### Example Queries

**Player xG vs FPL points per gameweek:**
```sql
SELECT
    p.fpl_name,
    gw.round,
    gw.total_points,
    gw.expected_goals AS fpl_xg,
    COALESCE(SUM(s.xg), 0) AS understat_xg,
    COUNT(s.shot_id) AS shot_count
FROM dim_players p
JOIN fact_player_gw gw ON p.fpl_id = gw.fpl_id
LEFT JOIN fact_shots s ON p.understat_id = s.understat_player_id
WHERE p.understat_id IS NOT NULL
GROUP BY p.fpl_name, gw.round
ORDER BY gw.round, gw.total_points DESC;
```

**Team-level shot quality:**
```sql
SELECT
    t.fpl_name AS team,
    COUNT(s.shot_id) AS total_shots,
    ROUND(SUM(s.xg), 2) AS total_xg,
    ROUND(AVG(s.xg), 3) AS avg_xg_per_shot
FROM dim_teams t
JOIN dim_players p ON p.team_id = t.team_id
JOIN fact_shots s ON p.understat_id = s.understat_player_id
WHERE p.understat_id IS NOT NULL
GROUP BY t.fpl_name
ORDER BY total_xg DESC;
```

**Team pressing profile with match context:**
```sql
SELECT
    ms.home_team,
    ms.away_team,
    ms.home_ppda,
    ms.away_ppda,
    ms.home_deep,
    ms.away_deep,
    ms.prob_home,
    f.home_score,
    f.away_score
FROM fact_match_stats ms
JOIN fact_fixtures f ON ms.fpl_fixture_id = f.fixture_id
ORDER BY ms.event;
```

**Player xGChain contribution vs FPL points:**
```sql
SELECT
    p.fpl_name,
    SUM(gw.total_points) AS total_pts,
    ROUND(SUM(gw.xg_chain), 2) AS total_xg_chain,
    ROUND(SUM(gw.xg_buildup), 2) AS total_xg_buildup,
    SUM(gw.tackles) AS total_tackles,
    SUM(gw.recoveries) AS total_recoveries
FROM dim_players p
JOIN fact_player_gw gw ON p.fpl_id = gw.fpl_id
WHERE gw.xg_chain IS NOT NULL
GROUP BY p.fpl_name
ORDER BY total_xg_chain DESC
LIMIT 20;
```

---

## Future Candidates

Data not currently in the warehouse but worth considering:

| Data | Source | Value |
|------|--------|-------|
| Points breakdown | FPL `explain_stats` | Understanding FPL scoring system |
| Historical seasons | FPL `player_history` | Multi-season trend analysis |
