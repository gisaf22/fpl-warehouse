-- Layer: stg
-- Tests: stg_fixture
-- Asserts: every fixtures capture stages exactly one row per fixture it lists —
--          no capture collapsed into another, no fixture dropped or duplicated.
-- Origin: new in #37
-- Tier: unit
{{ config(group='warehouse_internal', tags=['unit'], meta={'covers': '#37 AC1'}) }}

-- Compared per capture against the source's own rows, so a fixture missing
-- from staging, one staged twice, and one staged under a capture that never
-- listed it all surface as a row here. Nothing is filtered by fixture id: the
-- tree's live captures hold 381 fixtures, synthetic fixture 999 included (see
-- SYNTHETIC_DGW in tests/fixtures/build_fixtures.py), and staging must carry it
-- like any other.
--
-- A collapse — staging keeping one capture per fixture — shows as the other
-- captures' rows missing. That needs a fixture the source lists in more than
-- one capture, so the test also fails when there is none rather than passing
-- without having checked anything.

with source_fixtures as (

    select
        {{ season_from_filename() }}   as season,
        str_split(filename, '/')[-2]   as run_id,
        cast(id as integer)            as fixture_id
    from {{ source('fpl_raw', 'fixtures') }}

),

staged as (

    select
        season,
        run_id,
        fixture_id,
        count(*)                       as row_count
    from {{ ref('stg_fixture') }}
    group by season, run_id, fixture_id

)

select
    coalesce(source_fixtures.season, staged.season)         as season,
    coalesce(source_fixtures.run_id, staged.run_id)         as run_id,
    coalesce(source_fixtures.fixture_id, staged.fixture_id) as fixture_id,
    case
        when staged.fixture_id is null          then 'missing from staging'
        when source_fixtures.fixture_id is null then 'not in the capture'
        else 'duplicated'
    end                                                     as failure
from source_fixtures
full outer join staged
    on  staged.season     = source_fixtures.season
    and staged.run_id     = source_fixtures.run_id
    and staged.fixture_id = source_fixtures.fixture_id
where staged.fixture_id is null
   or source_fixtures.fixture_id is null
   or staged.row_count > 1

union all

select null, null, null, 'no fixture captured more than once to test against'
where not exists (
    select 1
    from source_fixtures
    group by season, fixture_id
    having count(distinct run_id) > 1
)
