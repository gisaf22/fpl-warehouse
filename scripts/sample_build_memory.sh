#!/usr/bin/env bash
# Sample the dbt build's memory every 5s until killed (#190 D4).
#
# Usage: sample_build_memory.sh OUT_CSV TEMP_DIRECTORY
#
# Writes one `epoch_seconds,rss_kib,spill_bytes` line per sample: the summed RSS
# of every running `dbt run` process, and the size of DuckDB's temp directory.
# It is sampled during the build because DuckDB removes its temp files when the
# connection closes, so a size read after the build shows 0.
# live-tests starts it in the background before `dbt run` and kills it after;
# scripts/summarize_experiment.py reads the file.
set -u
out="$1"
temp_dir="$2"
: > "$out"
while true; do
  pids=$(pgrep -d, -f 'dbt run' || true)
  rss=0
  if [ -n "$pids" ]; then
    rss=$(ps -o rss= -p "$pids" 2>/dev/null | awk '{s += $1} END {print s + 0}')
  fi
  spill=$(du -sb "$temp_dir" 2>/dev/null | cut -f1)
  echo "$(date +%s),${rss},${spill:-0}" >> "$out"
  sleep 5
done
