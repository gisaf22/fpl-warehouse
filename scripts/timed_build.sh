#!/usr/bin/env bash
# Run a build under `/usr/bin/time -v` and keep what the metrics step needs (#191).
#
# Usage: bash scripts/timed_build.sh OUT_DIR COMMAND [ARGS...]
#
# Writes, into OUT_DIR:
#   time_v.log        time -v's report: peak RSS and wall clock (#190's measurement)
#   dbt_exit_code     the command's exit code; absent if it never returned
#   run_results.json  dbt's target/run_results.json from this command, if it wrote one
#
# Exits with the command's own code, so a failed build still fails its step.
# target/run_results.json is removed first: later `dbt show` steps overwrite it,
# and an earlier one's file must never be read as this build's.
# TIME_BIN overrides the time binary, for tests on a machine without GNU time.
set -u
out=$1
shift
mkdir -p "$out"
rm -f target/run_results.json
status=0
"${TIME_BIN:-/usr/bin/time}" -v -o "$out/time_v.log" "$@" || status=$?
echo "$status" > "$out/dbt_exit_code"
if [ -f target/run_results.json ]; then
  cp target/run_results.json "$out/run_results.json"
fi
exit "$status"
