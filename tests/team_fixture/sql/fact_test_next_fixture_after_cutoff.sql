-- Test: days_until_next_fixture may only be populated when a strictly
-- post-cutoff next fixture exists.
--
-- Expectation: returns 0 rows.
WITH fixture_by_team AS (
    SELECT
        fixture_id,
        kickoff_time,
        home_team_id AS team_fpl_id
    FROM fact_fixtures
    UNION ALL
    SELECT
        fixture_id,
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
next_fixture AS (
    SELECT
        s.as_of_gw,
        s.team_fpl_id,
        MIN(fbt.kickoff_time) AS next_kickoff
    FROM fact_team_fixture_snapshot s
    JOIN cutoff_gws c
        ON c.as_of_gw = s.as_of_gw
    LEFT JOIN fixture_by_team fbt
        ON fbt.team_fpl_id = s.team_fpl_id
       AND fbt.kickoff_time > c.cutoff_time
    GROUP BY s.as_of_gw, s.team_fpl_id
)
SELECT
    s.as_of_gw,
    s.team_fpl_id,
    s.days_until_next_fixture,
    n.next_kickoff,
    c.cutoff_time
FROM fact_team_fixture_snapshot s
JOIN cutoff_gws c
    ON c.as_of_gw = s.as_of_gw
LEFT JOIN next_fixture n
    ON n.as_of_gw = s.as_of_gw
   AND n.team_fpl_id = s.team_fpl_id
WHERE
    (s.days_until_next_fixture IS NOT NULL AND n.next_kickoff IS NULL)
    OR (n.next_kickoff IS NOT NULL AND julianday(n.next_kickoff) <= julianday(c.cutoff_time))