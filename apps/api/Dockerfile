# syntax=docker/dockerfile:1
# ChatLedger API image. Build context: repository root.
ARG PYTHON_IMAGE=python:3.12-slim
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.5.31

# ---------------------------------------------------------------- git-sha
# Resolves `git rev-parse HEAD` from the build context's .git (or the GIT_SHA
# build arg). Only the resulting one-line file reaches the final image.
FROM ${PYTHON_IMAGE} AS git-sha
ARG GIT_SHA=""
COPY scripts/resolve_git_sha.sh /usr/local/bin/resolve_git_sha
# `.gi[t]` copies .git when present and is a no-op when it is absent.
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
    uv sync --frozen --no-dev --no-install-workspace --package chatledger-api
COPY packages/core packages/core
COPY apps/api apps/api
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package chatledger-api

# ---------------------------------------------------------------- runtime
FROM ${PYTHON_IMAGE} AS runtime
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=UTC
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin chatledger \
 && mkdir -p /data/blobs && chown chatledger:chatledger /data/blobs
WORKDIR /app
COPY --from=deps /app/.venv /app/.venv
COPY alembic.ini /app/alembic.ini
COPY --chmod=0755 apps/api/entrypoint.sh /app/entrypoint.sh
COPY --from=git-sha /GIT_SHA /app/GIT_SHA
USER chatledger
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --start-period=30s --retries=6 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]
ENTRYPOINT ["/app/entrypoint.sh"]
