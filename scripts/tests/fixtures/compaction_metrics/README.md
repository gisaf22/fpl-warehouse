`compaction.json` is the W13 object of live-tests dry run 38828339698 (2026-10-16),
dispatched with `compaction_dry_run=2026-08-30,2026-09-20,2026-10-13`. Each day's
values are its summary line in the "Compaction dry run" step log:

    gh run view 38828339698 --log | grep -E 'compacted \('

`seconds` is the step total W16 cites (24m04s). The log does not print peak RSS,
so `peak_rss_mib` is null, as the step records an unmeasured value. `n` is 0:
the dry run reads no budget.
