-- Test: int_team_fixture_base rows must respect the finished-fixture cutoff.
--
-- Expectation: returns 0 rows.
WITH cutoff_gws AS (
    SELECT
        g.as_of_gw,
        MAX(f.kickoff_time) AS cutoff_time
    FROM (SELECT DISTINCT event AS as_of_gw FROM fact_fixtures WHERE finished = 1) g
    JOIN fact_fixtures f
        ON f.finished = 1
       AND f.event <= g.as_of_gw
    GROUP BY g.as_of_gw
)
SELECT
    b.as_of_gw,
    b.team_fpl_id,
    b.understat_match_id,
    ms.datetime AS match_datetime,
    c.cutoff_time
FROM int_team_fixture_base b
JOIN fact_match_stats ms
    ON ms.understat_match_id = b.understat_match_id
JOIN cutoff_gws c
    ON c.as_of_gw = b.as_of_gw
WHERE julianday(ms.datetime) > julianday(c.cutoff_time)