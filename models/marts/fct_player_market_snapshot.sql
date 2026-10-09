-- Typed empty stub for #141's failing tests; the model is written in the
-- implementation commit.
select
    null::varchar       as season,
    null::integer       as fpl_id,
    null::varchar       as capture_key,
    null::timestamp     as observed_at,
    null::integer       as now_cost,
    null::decimal(4, 1) as selected_by_percent,
    null::integer       as transfers_in_event,
    null::integer       as transfers_out_event,
    null::integer       as total_players
where false
