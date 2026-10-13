# Dependencies and supply chain

Scan results and how dependencies are managed. Re-run the scans before
each release (the `security-scanning` skill does them) and update the
results table.

## Latest results

| Scan | Date | Scope | Result |
|---|---|---|---|
| pip-audit 2.10.1 | 2026-10-02 | Backend runtime deps, 61 pinned packages from `uv.lock` | No known vulnerabilities |
| pip-audit 2.10.1 | 2026-10-02 | Backend runtime + dev deps, 69 packages | No known vulnerabilities |
| pnpm audit | 2026-10-02 | Frontend, full tree from `pnpm-lock.yaml` | No known vulnerabilities |
| trivy 0.75.0 (image) | 2026-10-03 | Backend `prod` image in prod, then the patched Dockerfile | Prod image: 8 HIGH, 12 MEDIUM (base image OS packages, base image pip). Patched build: 0 CRITICAL/HIGH/MEDIUM/LOW, 1 UNKNOWN accepted. `security/IAC_SCANS.md` |
| tfsec 1.28.14 / checkov 3.3.22 | 2026-10-03 | `infra/hub` OpenTofu | 2 HIGH fixed, 2 HIGH accepted; checkov failures triaged. `security/IAC_SCANS.md` |
| pip-audit 2.10.1 | 2026-10-03 | Backend runtime + dev deps, 71 packages, after adding `opentelemetry-instrumentation-logging` | No known vulnerabilities |
| bandit (medium and above) | 2026-10-03 | `backend/app/` | No issues |
| pnpm audit --prod | 2026-10-03 | Frontend production dependencies | No known vulnerabilities |
| pip-audit 2.10.1, with the CI severity gate | 2026-10-13 | MCP server runtime + dev deps, 38 packages from `mcp-server/uv.lock` (30 runtime) | No known vulnerabilities |
| bandit 1.9.4 (medium and above) | 2026-10-13 | `mcp-server/hub_mcp/`, `agent-hooks/guard.py` | No issues |
| trivy 0.75.0 (image and config) | 2026-10-13 | Local Compose frontend image (nginx) and `frontend/Dockerfile` | 1 MEDIUM (zlib) and 1 LOW config finding, both fixed; 0 after. `security/IAC_SCANS.md` |

Commands used:

```
# backend/
uv export --frozen --no-hashes --no-dev --format requirements-txt > /tmp/req.txt
uvx pip-audit --disable-pip --no-deps -r /tmp/req.txt

# frontend/
pnpm audit --audit-level=low
```

To run the open scans:

```
# Image (from the repo root; needs Docker running)
docker build --target prod -t hub-backend:scan backend
trivy image --severity HIGH,CRITICAL hub-backend:scan

# Infrastructure as code
checkov -d infra/          # or: tfsec infra/
```

The image scan matters beyond pip-audit: it also covers the AWS Lambda
Python base image's OS packages (`public.ecr.aws/lambda/python:3.12`).

## How dependencies are pinned

- **Backend**: `pyproject.toml` declares minimums; `uv.lock` pins every
  package, transitive ones included, with hashes. The image installs
  exactly the lock (`uv export --frozen` in the Dockerfile), so dev, CI
  and the deployed Lambda run the same versions.
- **MCP server** (`mcp-server/`): the same as the backend, `pyproject.toml`
  minimums and `uv.lock` pins; CI's `dependency-scan` audits its lock
  with the same HIGH/CRITICAL gate.
- **Agent hook** (`agent-hooks/`): standard library only, no
  dependencies.
- **Frontend**: `package.json` ranges, `pnpm-lock.yaml` pins;
  `pnpm install --frozen-lockfile` in CI fails on any drift. pnpm itself
  is pinned (`packageManager`).
- **Base images**: `public.ecr.aws/lambda/python:3.12` (prod),
  `python:3.12-slim` (local Compose backend), and `node:22-alpine` plus
  `nginxinc/nginx-unprivileged:1.30-alpine` (local Compose frontend), by
  tag, not digest, so each build picks up the latest patch of that tag.
- **CI tooling**: every GitHub Action pinned to a full commit SHA, with
  the version in a trailing comment; gitleaks by version plus a SHA-256
  check of the download; pip-audit pinned (`pip-audit==2.10.1`).

## Adding a dependency

`AGENTS.md`: only what a task needs, justified. Before adding one:

- Is it maintained, and by whom? Downloads, recent releases, open
  security issues.
- How big is its transitive tree? Each new package is more attack
  surface.
- Does it run install scripts (npm `postinstall`)? pnpm only runs build
  scripts for packages listed under `allowBuilds` in
  `frontend/pnpm-workspace.yaml` (just `esbuild` today); a new package
  that needs one has to be added there deliberately.
- Run the audits above after adding it.

Added on 2026-10-02: `alembic` (backend runtime), for schema migrations.
Brings in `mako` and `markupsafe`. Maintained by the SQLAlchemy project.

Changed on 2026-10-02, to clear test-run deprecation warnings:
`httpx` (dev only, used by FastAPI's `TestClient`) replaced by `httpx2`
2.13.1, which Starlette now asks for; brings in `httpcore2` and
`truststore`. `starlette` 1.6.0 to 1.7.0 (stops using anyio's deprecated
`BlockingPortal` alias). pip-audit on the new lock: no known
vulnerabilities. Mangum 0.22.0 is still the latest release; its one
remaining warning is filtered in `pyproject.toml`, with the reason.

Added on 2026-10-03: `opentelemetry-instrumentation-logging` (backend
runtime), the OpenTelemetry project's logging handler, to export
selected app logs to Grafana (`ops/MONITORING.md`). Replaces the SDK's
own `LoggingHandler`, which is deprecated. Same project and version line
as the FastAPI and SQLAlchemy instrumentation already in use.

Changed on 2026-10-03, prod image (`backend/Dockerfile`): OS security
updates applied at build time and pip removed from the final image,
after the trivy findings in `security/IAC_SCANS.md`.

Added on 2026-10-13: the MCP server (`mcp-server/`), a separate project
with its own lock. Runtime: `mcp` (the official Model Context Protocol
Python SDK, maintained by the MCP project; locked at 2.2.0, released
2026-09-07, rather than the 11-day-old 2.3.0) and `httpx2` 2.13.1, which
`mcp` already depends on and the backend already uses in its tests.
Brings in `pydantic`, `starlette`, `uvicorn`, `sse-starlette`, `pyjwt`,
`jsonschema` and their dependencies (30 runtime packages). Dev: `pytest`,
`pyyaml`, `ruff`, as in the backend. pip-audit: no known vulnerabilities.

Added on 2026-10-13, local Compose only (`frontend/Dockerfile`): the
`node:22-alpine` build stage and the `nginxinc/nginx-unprivileged`
serving stage, with OS updates applied at build after trivy's zlib
finding.

## Supply-chain notes and gaps

- The base images are still referenced by tag, not digest, so a
  compromised or broken upstream tag would reach the next build. The prod
  stage now applies OS security updates itself (`dnf upgrade
  --releasever=latest`) and removes pip, so staleness is covered; digest
  pinning would cover tampering. Pinning by digest (and bumping it
  deliberately) would close that; Dependabot or Renovate could do the
  bumping.
- No automated dependency update PRs (Dependabot or Renovate) yet, so
  updates happen when someone runs `uv lock --upgrade` or
  `pnpm update`.
- GitHub Actions: pinned to full commit SHAs in every workflow since
  2026-10-03, with the version in a trailing comment
  (`uses: actions/checkout@<sha> # v7.0.1`). A moved or hijacked tag
  can no longer change what runs with this repo's OIDC token. To bump
  one: resolve the new release tag to its commit
  (`gh api repos/<owner>/<repo>/git/ref/tags/<tag>`, dereferencing an
  annotated tag) and update both the SHA and the comment.
- The `security-scanning` skill runs `uvx pip-audit`, `uvx bandit` and
  installs trufflehog with Homebrew without version pins (see
  `security/AGENT_SECURITY.md`).
- pip-audit and pnpm audit run in CI since 2026-10-04 (`dependency-scan`
  job in `ci.yml`, after the unit tests), and gate the dev deploy on HIGH
  and CRITICAL; MODERATE and LOW show as warnings on the run. pip-audit
  reports no severities, so `.github/scripts/pip_audit_gate.py` looks each
  finding up in OSV (GitHub advisory severity) and fails on HIGH, CRITICAL,
  or a severity it can't determine. Tested against a known HIGH (jinja2
  2.10: fails), a MODERATE-only set (requests 2.31.0: passes with
  warnings), an unknown severity (fails) and the real lock (passes); the
  pnpm gate against lodash 4.17.20 (2 high: fails at `high`). trivy still
  runs by hand (it needs the built image); ECR scans every pushed image.
