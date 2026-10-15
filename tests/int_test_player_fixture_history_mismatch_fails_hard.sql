-- Layer: int
-- Tests: int_player_fixture_history_mismatch
-- Asserts: every admitted element-summary capture stages exactly as many
--          stg_player_fixture rows as its payload's history[] has entries
--          (#175 G7). Error severity: an empty history[] expects 0 rows and
--          passes; a full or partial drop fails the build.
-- Origin: new in #175
-- Tier: integration (also runs in every live build)
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#175 AC2b'}) }}

select season, run_id, capture_key, expected_rows, staged_rows
from {{ ref('int_player_fixture_history_mismatch') }}
