-- Layer: stg
-- Tests: stg_player
-- Asserts: the fixture tree really contains a player who is in an earlier
--          bootstrap capture and absent from the latest, so the spine's
--          union-across-captures player list is tested against a real
--          departure rather than vacuously.
-- Origin: new — modelled on
--         stg_test_player_fixture_multiple_captures_present, which asserts a
--         precondition of the fixture tree rather than an invariant.
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration']) }}

-- Group membership is required, not cosmetic: this test ref()s stg_player,
-- which is access: private to warehouse_internal. See CLAUDE.md, "Served
-- contract".

-- fct_test_player_gameweek_spine_covers_departed_players and
-- fct_test_player_gameweek_covers_every_fixture both pass trivially when
-- every capture holds the same players — which was true of this tree before
-- player 4's synthetic departure was added, and is true of the live tree
-- today. A green suite would then prove nothing about the union fix.
--
-- So this asserts the precondition: at least one player is present in some
-- capture and absent from the latest one.
--
-- Fixtures target only. The live tree has no departure yet (verified
-- 2026-09-14: the union of `elements` across all 128 captures is 658 and the
-- latest capture is 658), so asserting this against `dev` would fail on
-- correct data. Guarded rather than tiered as e2e because it must run in the
-- same fast PR check as the two tests whose non-vacuity it protects — those
-- are integration, and a guard in a tier nobody runs alongside them protects
-- nothing.

{% if target.name != 'fixtures' %}

select null as failure where false

{% else %}

with latest_capture as (

    select run_id
    from {{ ref('stg_player') }}
    order by extracted_at desc, run_id desc
    limit 1

),

departed as (

    select distinct fpl_id
    from {{ ref('stg_player') }}

    except

    select distinct fpl_id
    from {{ ref('stg_player') }}
    where run_id = (select run_id from latest_capture)

)

select
    'no player is absent from the latest bootstrap capture — the fixture tree '
    || 'has no departure, so the spine union tests pass vacuously'
        as failure,
    count(*) as departed_players
from departed
having count(*) < 1

{% endif %}
