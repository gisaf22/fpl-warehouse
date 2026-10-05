-- Layer: int
-- Tests: int_admitted_capture, stg_gameweek
-- Asserts: every passed deadline from 2026-09-24 on has an admitted capture in
--          [deadline - 125m, deadline). Warn severity: detection only, the
--          build and the publish proceed, and the warning names each miss.
--          Promotion to error with an acknowledgment seed is #80.
-- Origin: new in #111
-- Tier: e2e (live only: until #81 the fixture tree holds no passed in-scope
--       deadline with its window captures, so it would warn by construction)
{{ config(group='warehouse_internal', tags=['e2e'], severity='warn', meta={'covers': '#111 AC3'}) }}

with gameweeks as (
    select season, gameweek, deadline_time, observed_at, run_id
    from {{ ref('stg_gameweek') }}
)

{{ missed_pre_deadline_windows('gameweeks', ref('int_admitted_capture')) }}
