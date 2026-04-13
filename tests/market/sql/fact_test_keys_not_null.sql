-- Test: primary key columns are never NULL.
--
-- Expectation: returns 0 rows.
-- NULL in as_of_gw or fpl_id breaks the primary key contract.
-- Market snapshot has no team_fpl_id — all market signals derive from
-- fact_player_gw alone.
SELECT as_of_gw, fpl_id
FROM fact_player_market_snapshot
WHERE
    as_of_gw   IS NULL
    OR fpl_id    IS NULL
