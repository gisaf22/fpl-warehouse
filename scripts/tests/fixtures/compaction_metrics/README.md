`compaction.json` is the W13 object of live-tests dry run 38828339698 (2026-10-16),
dispatched with `compaction_dry_run=2026-08-30,2026-09-20,2026-10-13`. Each day's
values are its summary line in the "Compaction dry run" step log:

    gh run view 38828339698 --log | grep -E 'compacted \('

`seconds` is the step total W16 cites (24m04s). The log does not print peak RSS,
so `peak_rss_mib` is null, as the step records an unmeasured value. The run named
the field `n` (W13 before the #205 rename to `budget_seconds`); its value is 0:
a dry run reads no budget.
