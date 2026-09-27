-- Stub for #40: the column shape only, zero rows, so the tests committed ahead
-- of the implementation parse and run — and fail — rather than being disabled
-- as referencing a missing node. Replaced by the implementation commit.

select
    cast(null as varchar) as season,
    cast(null as integer) as team_fpl_id,
    cast(null as integer) as team_code,
    cast(null as varchar) as team_name,
    cast(null as varchar) as team_short_name
where false
