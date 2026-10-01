#!/usr/bin/env bash
# End-to-end smoke test: boot the stack from a clean state, wait for /health,
# check the web shell, then run a noop job to completion through the worker.
#
#   ./scripts/smoke.sh            # uses http://localhost:8000 and :3000
#   KEEP_STACK=1 ./scripts/smoke.sh  # leave the stack running afterwards
set -euo pipefail
cd "$(dirname "$0")/.."

API_URL="${API_URL:-http://localhost:8000}"
WEB_URL="${WEB_URL:-http://localhost:3000}"
TIMEOUT="${SMOKE_TIMEOUT:-60}"

log() { printf '\n==> %s\n' "$*"; }
fail() { printf 'SMOKE FAILED: %s\n' "$*" >&2; exit 1; }

cleanup() {
  if [[ "${KEEP_STACK:-0}" != "1" ]]; then
    log "Stopping stack"
    docker compose down >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

log "Starting stack (docker compose up -d --build)"
start=$(date +%s)
docker compose up -d --build

log "Waiting for ${API_URL}/health (timeout ${TIMEOUT}s)"
until curl -fsS "${API_URL}/health" >/tmp/chatledger-smoke-health.json 2>/dev/null; do
  (( $(date +%s) - start > TIMEOUT )) && fail "/health not 200 within ${TIMEOUT}s"
  sleep 1
done
echo "healthy after $(( $(date +%s) - start ))s: $(cat /tmp/chatledger-smoke-health.json)"
grep -q '"migration_revision":"0001_foundation"' /tmp/chatledger-smoke-health.json \
  || fail "unexpected migration revision"

log "Checking ${WEB_URL}/matters"
until curl -fsS "${WEB_URL}/matters" >/tmp/chatledger-smoke-web.html 2>/dev/null; do
  (( $(date +%s) - start > TIMEOUT + 30 )) && fail "web not reachable"
  sleep 1
done
grep -q "No matters yet" /tmp/chatledger-smoke-web.html || fail "matters empty state missing"

log "Running a noop job through the worker"
job_id=$(docker compose exec -T worker chatledger-admin enqueue-noop | tr -d '[:space:]')
echo "enqueued ${job_id}"
for _ in $(seq 1 30); do
  status=$(docker compose exec -T worker chatledger-admin job-status "${job_id}")
  if grep -q '"state": "done"' <<<"${status}"; then
    echo "${status}"
    log "SMOKE OK"
    exit 0
  fi
  sleep 1
done
fail "noop job did not finish: ${status}"
