-- Layer: stg
-- Tests: stg_player_fixture
-- Asserts: staging holds more than one distinct capture of the same
--          (fpl_id, fixture_id), which is only true of a build against the real
--          accumulated raw tree.
-- Origin: new in Phase 4
-- Tier: e2e
{{ config(group='warehouse_internal', tags=['e2e']) }}

-- Group membership is required, not cosmetic: this test ref()s
-- stg_player_fixture, which is access: private to warehouse_internal. Without
-- it dbt refuses to parse the test. See CLAUDE.md, "Served contract".

-- This is the tier's reason for existing. Every dedup assertion in the
-- integration tier — ratified-preference, retracted rows, grain uniqueness —
-- passes vacuously when staging holds one capture per key, because there is
-- nothing to collapse. A build against a single local capture
-- (`--vars '{raw_root: .local/raw}'`, the documented no-AWS-session fallback)
-- produces exactly that, and would report a green suite that has proved
-- nothing about the dedup rule.
--
-- So this test asserts the precondition rather than an invariant: that the
-- build actually read the accumulated tree. It fails on a local or fixture
-- build by design, which is why it is e2e and excluded from the default run.
-- On 2026-09-03 the live tree held 50,568 rows over 1,238 distinct keys, with
-- 558 keys carrying both a provisional and a ratified capture.

with capture_counts as (

    select
        fpl_id,
        fixture_id,
        count(distinct run_id) as capture_count
    from {{ ref('stg_player_fixture') }}
    group by fpl_id, fixture_id

)

select
    'no key has more than one capture — staging was built from a single run, '
    || 'so every dedup assertion in the integration tier passes vacuously'
        as failure,
    count(*)                                as keys_total,
    coalesce(max(capture_count), 0)         as max_captures_per_key
from capture_counts
-- COALESCE matters: over empty staging max() is NULL, `NULL < 2` is NULL, and
-- the test would pass on a build that read nothing at all.
having coalesce(max(capture_count), 0) < 2
