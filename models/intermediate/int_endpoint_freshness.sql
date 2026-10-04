-- =============================================================================
-- Layer: int_ (intermediate)
-- Model: int_endpoint_freshness
-- =============================================================================
--
-- Purpose:
--   The scheduled build's input guard (#103, #88 E2; replaces #39's
--   `dbt source freshness`). Per live endpoint, the newest admitted capture's
--   received_at and its age, so a stale input blocks the build and publish.
--
-- Grain:
--   One row per live endpoint: bootstrap-static, fixtures, event-status and
--   element-summary. element-summary's per-player endpoints
--   (element-summary/<fpl_id>) are one endpoint here.
--
-- Rule:
--   Only admitted captures count (int_capture_admission), so a local or
--   otherwise unadmitted capture can never make an endpoint look fresh.
--   Ported history captures (scope = 'history') are excluded: a closed
--   season's age means nothing.
--   freshness_status is 'warn' over 6h and 'error' over 18h, strictly over.
--   element-summary is always 'exempt': ingest stops capturing it once the
--   latest gameweek is settled, so its age is not a staleness signal. An
--   endpoint with no admitted live capture at all reads 'error'.
--   The int_test_endpoint_freshness_* tests turn the status into a warning
--   and an error. See CLAUDE.md, "Source freshness".
--
-- Age:
--   Measured against the `freshness_as_of` var when set (the unit tests pin
--   it), else the current UTC time. This model is a view, so the age is taken
--   when it is read, not when it was built.
-- =============================================================================

with endpoints as (

    select * from (values
        ('bootstrap-static'),
        ('fixtures'),
        ('event-status'),
        ('element-summary')
    ) as t(endpoint)

),

newest as (

    select
        split_part(captures.endpoint, '/', 1)  as endpoint,
        max(captures.received_at)              as newest_received_at
    from {{ ref('base_capture_index') }} as captures
    inner join {{ ref('int_capture_admission') }} as admission
        on admission.capture_key = captures.capture_key
    where admission.admitted
      and captures.scope is distinct from 'history'
    group by 1

),

aged as (

    select
        endpoints.endpoint,
        newest.newest_received_at,
        epoch(
            {% if var('freshness_as_of', none) %}
            cast('{{ var("freshness_as_of") }}' as timestamp)
            {% else %}
            timezone('UTC', current_timestamp)
            {% endif %}
            - newest.newest_received_at
        ) / 3600.0                             as age_hours_exact
    from endpoints
    left join newest
        on newest.endpoint = endpoints.endpoint

)

select
    endpoint,
    newest_received_at,
    round(age_hours_exact, 1)                  as age_hours,
    case
        when endpoint = 'element-summary'      then 'exempt'
        when newest_received_at is null        then 'error'
        when age_hours_exact > 18              then 'error'
        when age_hours_exact > 6               then 'warn'
        else 'ok'
    end                                        as freshness_status
from aged
