#!/bin/sh
# API container start: apply migrations, then serve.
set -eu
cd /app
echo '{"event": "migrations.upgrade.start", "service": "api"}'
alembic -c /app/alembic.ini upgrade head
echo '{"event": "migrations.upgrade.done", "service": "api"}'
exec uvicorn chatledger_api.main:app --host 0.0.0.0 --port 8000 --no-access-log --proxy-headers
