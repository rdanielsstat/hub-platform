# syntax=docker/dockerfile:1

# Multi-stage build with two independent final targets:
#   prod  - AWS Lambda container image (runs via Mangum + the Lambda runtime)
#   dev   - plain uvicorn image for local Docker Compose (hot-reload friendly)
#
# Both install the exact same dependency set, resolved from this project's
# uv.lock (`uv export --frozen`), so prod and dev never drift.

# ---- stage: deps -----------------------------------------------------
# Only resolves/exports the locked dependency set; not used as a runtime
# base for either final image, so it can use its own small image freely.
FROM ghcr.io/astral-sh/uv:0.9-alpine AS deps
WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-hashes -o requirements.txt

# ---- stage: prod (AWS Lambda container image) -------------------------
FROM public.ecr.aws/lambda/python:3.12 AS prod

# Security fixes the base image doesn't have yet. AWS publishes this image
# on its own schedule, and trivy found HIGH CVEs in its OS packages (curl,
# pcre2, rpm) with fixes already released. Amazon Linux 2023 locks dnf to
# the image's release snapshot, so --releasever=latest is what reaches the
# fixes. See security/DEPENDENCIES.md.
RUN dnf upgrade -y --releasever=latest \
    && dnf clean all \
    && rm -rf /var/cache/dnf

# pip is removed once the app's dependencies are in: the function never
# uses it, and it carries its own bundled copies of urllib3, msgpack and
# setuptools' pkg_resources, which trivy flags (HIGH) independently of the
# app's own, patched, urllib3.
COPY --from=deps /src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --target "${LAMBDA_TASK_ROOT}" \
    && pip uninstall -y pip

# The Lambda Runtime Interface Emulator only runs when the image is
# started outside Lambda (/lambda-entrypoint.sh uses it when
# AWS_LAMBDA_RUNTIME_API is unset); in Lambda, /var/runtime/bootstrap runs
# directly. It's a Go binary whose bundled standard library trivy flags
# (3 HIGH on 2026-10-13, security/IAC_SCANS.md), so it isn't shipped.
# Local runs use the dev stage below (Docker Compose), never this one.
RUN rm -f /usr/local/bin/aws-lambda-rie

COPY app ${LAMBDA_TASK_ROOT}/app
COPY observability ${LAMBDA_TASK_ROOT}/observability
# Migration scripts, applied by the bootstrap Lambda (app/bootstrap_db.py).
COPY alembic ${LAMBDA_TASK_ROOT}/alembic
COPY alembic.ini ${LAMBDA_TASK_ROOT}/alembic.ini

# Mangum-wrapped FastAPI app; see app/lambda_handler.py.
CMD ["app.lambda_handler.handler"]

# ---- stage: dev (local Docker Compose, plain ASGI server) -------------
FROM python:3.12-slim AS dev

WORKDIR /app

COPY --from=deps /src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY observability ./observability
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

# Not root, like the frontend container (trivy DS-0002). The code is
# read-only to it; nothing in the Compose services writes inside /app.
RUN useradd --system --uid 10001 --no-create-home app
USER app

EXPOSE 8000
# The API's own health route (no database), for `docker compose ps`.
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
