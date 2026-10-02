#!/usr/bin/env bash
# F03 performance check: the `large` preset must generate in under 5 minutes with a generator
# peak RSS under 500 MB, and hold exactly 1,000,000 message records.
#
# Usage: scripts/e2e/generator_perf.sh [--profile clean|default] [--seed N] [--out DIR]
#   clean   (default) also counts the regular message records inside the ZIP
#   default           checks time, memory and the ground-truth record total only
# Needs /usr/bin/time (GNU), uv and ~2 GB of free disk.
set -euo pipefail

PROFILE=clean
SEED=42
OUT=""
MAX_SECONDS=300
MAX_RSS_KB=$((500 * 1024))

usage() { sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="${2:-}"; shift 2 ;;
    --seed) SEED="${2:-}"; shift 2 ;;
    --out) OUT="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$PROFILE" in clean|default) ;; *) echo "--profile must be clean or default" >&2; exit 2 ;; esac
[[ "$SEED" =~ ^[0-9]+$ ]] || { echo "--seed must be a non-negative integer" >&2; exit 2; }
[[ -x /usr/bin/time ]] || { echo "/usr/bin/time is required" >&2; exit 2; }

cd "$(dirname "$0")/../.."
if [[ -z "$OUT" ]]; then OUT="$(mktemp -d)"; CLEANUP=1; else CLEANUP=0; fi
TIME_LOG="$OUT/time.log"
mkdir -p "$OUT"

/usr/bin/time -v -o "$TIME_LOG" \
  uv run chatledger-gen --seed "$SEED" --preset large --profile "$PROFILE" --out "$OUT" >"$OUT/stdout.log"

ELAPSED=$(awk -F': ' '/Elapsed \(wall clock\)/ {print $2}' "$TIME_LOG" | awk -F: '{ if (NF==3) print $1*3600+$2*60+$3; else print $1*60+$2 }')
RSS_KB=$(awk -F': ' '/Maximum resident set size/ {print $2}' "$TIME_LOG")
echo "wall seconds: $ELAPSED  peak RSS kB: $RSS_KB"

ZIP="$OUT/slack-export-$SEED-large-$PROFILE.zip"
TRUTH="$OUT/ground-truth-$SEED.json"
python_check='
import json, sys, zipfile
zip_path, truth_path, profile = sys.argv[1:4]
truth = json.load(open(truth_path))
assert truth["totals"]["message_records"] == 1_000_000, truth["totals"]["message_records"]
with zipfile.ZipFile(zip_path) as archive:
    names = archive.namelist()
    assert len(names) <= 200_000, len(names)
    if profile == "clean":
        events = {"channel_join", "channel_leave", "message_changed", "message_deleted"}
        regular, folders = 0, set()
        for name in names:
            if "/" not in name:
                continue
            folders.add(name.split("/")[0])
            regular += sum(1 for r in json.loads(archive.read(name)) if r.get("subtype") not in events)
        assert regular == 1_000_000, regular
        assert len(folders) == 5_000, len(folders)
print("records ok")
'
uv run python -c "$python_check" "$ZIP" "$TRUTH" "$PROFILE"

awk -v e="$ELAPSED" -v m="$MAX_SECONDS" 'BEGIN { exit !(e < m) }' || { echo "too slow: ${ELAPSED}s" >&2; exit 1; }
(( RSS_KB < MAX_RSS_KB )) || { echo "too much memory: ${RSS_KB} kB" >&2; exit 1; }
[[ $CLEANUP -eq 1 ]] && rm -rf "$OUT"
echo "generator perf check passed"
