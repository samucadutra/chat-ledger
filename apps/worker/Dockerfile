# syntax=docker/dockerfile:1
# ChatLedger worker image (also ships the `chatledger-admin` CLI). Build context: repository root.
ARG PYTHON_IMAGE=python:3.12-slim
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.5.31

# ---------------------------------------------------------------- git-sha
FROM ${PYTHON_IMAGE} AS git-sha
ARG GIT_SHA=""
COPY scripts/resolve_git_sha.sh /usr/local/bin/resolve_git_sha
COPY scripts/resolve_git_sha.sh .gi[t] /src/.git/
RUN resolve_git_sha /src/.git > /GIT_SHA && cat /GIT_SHA

# ---------------------------------------------------------------- deps
FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE} AS deps
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package chatledger-worker
COPY packages/core packages/core
COPY apps/worker apps/worker
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package chatledger-worker

# ---------------------------------------------------------------- runtime
FROM ${PYTHON_IMAGE} AS runtime
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=UTC
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin chatledger \
 && mkdir -p /data/blobs && chown chatledger:chatledger /data/blobs
WORKDIR /app
COPY --from=deps /app/.venv /app/.venv
COPY --from=git-sha /GIT_SHA /app/GIT_SHA
USER chatledger
# SIGTERM -> finish the current job, then exit 0 (see stop_grace_period in compose).
STOPSIGNAL SIGTERM
ENTRYPOINT ["chatledger-worker"]
