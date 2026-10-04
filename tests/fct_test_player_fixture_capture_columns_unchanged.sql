-- Layer: fct
-- Tests: fct_player_fixture
-- Asserts: the served capture columns keep the values they had when parsed
--          from object keys (E1): extracted_at is the run_id's start instant
--          and extraction_date is that instant's date.
-- Origin: new in #104 (C2d of #88). The key's date directory equalled the
--         manifest's extraction_date for 198 of 198 manifests (#88 step 0).
-- Tier: integration
{{ config(tags=['integration'], meta={'covers': '#104 AC4'}) }}

select season, fpl_id, fixture_id, run_id, extraction_date, extracted_at
from {{ ref('fct_player_fixture') }}
where extracted_at is distinct from strptime(split_part(run_id, '-', 1), '%Y%m%dT%H%M%SZ')
   or extraction_date is distinct from cast(strptime(split_part(run_id, '-', 1), '%Y%m%dT%H%M%SZ') as date)
