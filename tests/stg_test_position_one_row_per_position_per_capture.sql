-- Layer: stg
-- Tests: stg_position
-- Asserts: every bootstrap-static capture stages exactly one row per position
--          (element_type) it defines.
-- Origin: new in #38
-- Tier: unit
{{ config(group='warehouse_internal', tags=['unit'], meta={'covers': '#38 AC3'}) }}

-- Compared per capture against the source's own `element_types` array, so a
-- position missing from staging or staged twice surfaces as a row here. The
-- ported season's single capture is checked the same way as each live one.

with source_positions as (

    select
        {{ season_from_filename() }}   as season,
        str_split(filename, '/')[-2]   as run_id,
        cast(p.id as integer)          as position_id
    from (
        select filename, unnest(element_types) as p
        from {{ source('fpl_raw', 'bootstrap_static') }}
    )

),

staged as (

    select season, run_id, position_id, count(*) as row_count
    from {{ ref('stg_position') }}
    group by season, run_id, position_id

)

select
    coalesce(source_positions.season, staged.season)           as season,
    coalesce(source_positions.run_id, staged.run_id)           as run_id,
    coalesce(source_positions.position_id, staged.position_id) as position_id,
    case
        when staged.position_id is null           then 'missing from staging'
        when source_positions.position_id is null then 'not in the capture'
        else 'duplicated'
    end                                                        as failure
from source_positions
full outer join staged
    on  staged.season      = source_positions.season
    and staged.run_id      = source_positions.run_id
    and staged.position_id = source_positions.position_id
where staged.position_id is null
   or source_positions.position_id is null
   or staged.row_count > 1
