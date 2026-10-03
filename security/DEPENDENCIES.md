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
| trivy (image) | not run | Backend `prod` image | **Open**: trivy not installed, and Docker wasn't running |
| checkov / tfsec | not run | `infra/` OpenTofu | **Open**: neither installed |

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
- **Frontend**: `package.json` ranges, `pnpm-lock.yaml` pins;
  `pnpm install --frozen-lockfile` in CI fails on any drift. pnpm itself
  is pinned (`packageManager`).
- **Base images**: `public.ecr.aws/lambda/python:3.12` (prod) and
  `python:3.12-slim` (local Compose) by tag, not digest, so each build
  picks up the latest patch of that tag.
- **CI tooling**: GitHub Actions by major version tag (`@v4`, `@v5`);
  gitleaks by version plus a SHA-256 check of the download.

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

## Supply-chain notes and gaps

- Image tags aren't pinned to digests. A compromised or broken upstream
  tag would reach the next build. Pinning by digest (and bumping it
  deliberately) would close that; Dependabot or Renovate could do the
  bumping.
- No automated dependency update PRs (Dependabot or Renovate) yet, so
  updates happen when someone runs `uv lock --upgrade` or
  `pnpm update`.
- GitHub Actions are pinned to tags, not commit SHAs. A moved tag on a
  third-party action would run new code with this repo's OIDC token in
  the deploy job. Pinning third-party actions to SHAs in `ci.yml` and
  `promote.yml` is the standard fix.
- The `security-scanning` skill runs `uvx pip-audit`, `uvx bandit` and
  installs trufflehog with Homebrew without version pins (see
  `security/AGENT_SECURITY.md`).
- None of the scans run in CI yet. Adding pip-audit and pnpm audit as a
  CI job is cheap; trivy needs the built image, so it belongs after the
  build step in `deploy-dev`.
