-- Zero-row stub so the #42 tests parse, run and fail before the model exists.
-- Replaced by the implementation in the next commit.

select
    cast(null as varchar)   as season,
    cast(null as integer)   as fixture_id,
    cast(null as integer)   as round,
    cast(null as timestamp) as kickoff_time,
    cast(null as integer)   as team_h_fpl_id,
    cast(null as integer)   as team_a_fpl_id,
    cast(null as integer)   as team_h_score,
    cast(null as integer)   as team_a_score,
    cast(null as boolean)   as finished,
    cast(null as integer)   as team_h_difficulty,
    cast(null as integer)   as team_a_difficulty,
    cast(null as boolean)   as difficulty_is_pre_kickoff
where false
