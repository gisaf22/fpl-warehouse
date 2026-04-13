-- Test: matches_count_last_7d must be computed only from finished fixtures
-- at or before the global cutoff for each as_of_gw.
--
-- Expectation: returns 0 rows.
WITH fixture_by_team AS (
    SELECT
        fixture_id,
        event,
        finished,
        kickoff_time,
        home_team_id AS team_fpl_id
    FROM fact_fixtures
    UNION ALL
    SELECT
        fixture_id,
        event,
        finished,
        kickoff_time,
        away_team_id AS team_fpl_id
    FROM fact_fixtures
),
cutoff_gws AS (
    SELECT
        g.as_of_gw,
        MAX(f.kickoff_time) AS cutoff_time
    FROM (SELECT DISTINCT event AS as_of_gw FROM fact_fixtures WHERE finished = 1) g
    JOIN fact_fixtures f
        ON f.finished = 1
       AND f.event <= g.as_of_gw
    GROUP BY g.as_of_gw
),
expected AS (
    SELECT
        s.as_of_gw,
        s.team_fpl_id,
        COUNT(fbt.fixture_id) AS expected_matches_last_7d
    FROM fact_team_fixture_snapshot s
    JOIN cutoff_gws c
        ON c.as_of_gw = s.as_of_gw
    LEFT JOIN fixture_by_team fbt
        ON fbt.team_fpl_id = s.team_fpl_id
       AND fbt.finished = 1
       AND fbt.event <= s.as_of_gw
       AND fbt.kickoff_time <= c.cutoff_time
       AND julianday(fbt.kickoff_time) >= julianday(c.cutoff_time) - 7
    GROUP BY s.as_of_gw, s.team_fpl_id
)
SELECT
    s.as_of_gw,
    s.team_fpl_id,
    s.matches_count_last_7d,
    e.expected_matches_last_7d
FROM fact_team_fixture_snapshot s
JOIN expected e
    ON e.as_of_gw = s.as_of_gw
   AND e.team_fpl_id = s.team_fpl_id
WHERE COALESCE(s.matches_count_last_7d, -1) != COALESCE(e.expected_matches_last_7d, -1)
