#!/usr/bin/env bash
# Upload memory check (F02): uploads the 1.5 GB fixture through the running stack and asserts
# that the API's uvicorn worker RSS grows by less than 100 MB, the response SHA-256 equals
# `sha256sum`, and the stored blob is mode 0444. Run `make fixtures-intake` and `make up` first.
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
FIXTURE="${FIXTURE:-tests/fixtures/intake/generated/large-export-1_5gb.zip}"
LIMIT_KB=$((100 * 1024))

[[ -f "$FIXTURE" ]] || { echo "missing $FIXTURE (run: make fixtures-intake)" >&2; exit 2; }

rss_kb() {
  # RSS (KB) of the uvicorn worker: the largest python process in the api container.
  docker compose exec -T api ps -eo rss=,args= | grep -i uvicorn | awk '{print $1}' | sort -n | tail -1
}

name="Upload memory check $(date +%s)"
matter_id=$(curl -fsS -X POST "$API_URL/api/v1/matters" -H 'Content-Type: application/json' \
  -d "{\"name\": \"$name\"}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

idle=$(rss_kb)
peak=$idle
out=$(mktemp)
curl -fsS -X POST "$API_URL/api/v1/matters/$matter_id/collections" \
  -H 'Content-Type: application/zip' -H "X-Filename: $(basename "$FIXTURE")" \
  --data-binary "@$FIXTURE" -o "$out" &
curl_pid=$!
while kill -0 "$curl_pid" 2>/dev/null; do
  now=$(rss_kb || echo 0)
  (( now > peak )) && peak=$now
  sleep 0.5
done
wait "$curl_pid"

sha=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "$out")
expected=$(sha256sum "$FIXTURE" | cut -d' ' -f1)
growth=$((peak - idle))
mode=$(docker compose exec -T api stat -c '%a' "/data/blobs/sha256/${sha:0:2}/$sha.zip" | tr -d '\r')

echo "idle RSS ${idle} KB, peak ${peak} KB, growth ${growth} KB (limit ${LIMIT_KB} KB)"
[[ "$sha" == "$expected" ]] || { echo "SHA-256 mismatch: $sha != $expected" >&2; exit 1; }
[[ "$mode" == "444" ]] || { echo "blob mode is $mode, expected 444" >&2; exit 1; }
(( growth < LIMIT_KB )) || { echo "memory growth above limit" >&2; exit 1; }
echo "OK: hash matches, blob is 0444, memory bounded"
