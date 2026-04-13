-- Test: cs_pct is between 0 and 1 inclusive where not NULL.
--
-- Expectation: returns 0 rows.
-- cs_pct = SUM(clean_sheets) / COUNT(*) over the window. Since clean_sheets is
-- 0 or 1 per row and COUNT >= 1, the result must be in [0, 1].
SELECT as_of_gw, fpl_id, cs_pct
FROM fct_player_performance_features
WHERE cs_pct IS NOT NULL
  AND (cs_pct < 0 OR cs_pct > 1)
