-- Typed stub for #152's failing tests; the implementation replaces it.
select
    season,
    fixture_id,
    observed_at                     as valid_from,
    cast(null as timestamp)         as valid_to,
    gameweek,
    kickoff_time,
    team_h_fpl_id,
    team_a_fpl_id,
    team_h_difficulty,
    team_a_difficulty,
    capture_key
from {{ ref('stg_fixture') }}
where false
