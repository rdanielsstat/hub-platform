---
name: release
description: Tag a new release, push to main, verify dev deployment, and document the release
---

# Release

Automate the release workflow: create a semantic version tag, push it along with any pending code to main, wait for dev to deploy, verify SERVICE_VERSION, and document what was released.

## Prerequisites

- You are on the `main` branch, up to date with origin
- All tests pass locally (`uv run pytest` in backend/, `pnpm test` in frontend/)
- All lint, format, and build checks pass locally
- No uncommitted changes

## Steps

### 1. Determine the next version

Inspect the current version:

```bash
git describe --tags --long --match 'v[0-9]*.[0-9]*.[0-9]*'
```

This shows the current tag and how many commits past it you are (e.g., `v0.1.0-5-g629aa29`).

Suggest the next semantic version based on the changes since the last tag:
- Patch release (0.1.1): bug fixes, small improvements, no API changes
- Minor release (0.2.0): new features, backward compatible
- Major release (1.0.0): breaking changes, significant milestones

Confirm the version with the human. Format: `vX.Y.Z` (e.g., `v0.2.0`).

### 2. Create and push the release tag

From the repo root:

```bash
git tag -a <VERSION> -m "Release <VERSION>"
git push origin <VERSION>
```

Example: `git tag -a v0.2.0 -m "Release v0.2.0"`

### 3. Ensure code is pushed to main

Check if there are any uncommitted changes or unpushed commits:

```bash
git status
git log --oneline origin/main..main
```

If there are unpushed commits, push them:

```bash
git push origin main
```

(If status shows uncommitted changes, stop and ask the human to commit them first.)

### 4. Wait for CI to deploy to dev

The tag push does not trigger CI; the next push to main does.

Go to `.github/workflows/` and check the live `ci.yml` run for your commit:
- Open https://github.com/rdanielsstat/hub-platform/actions
- Look for the most recent run on main
- Wait for `deploy-dev` to complete (tests → build image → apply infra → bootstrap → build frontend → smoke-test)
- Verify it succeeded (all steps green, smoke-test passed /api/health)

If the run fails, report the failure and stop; the human needs to fix the issue before proceeding.

### 5. Verify SERVICE_VERSION on dev Lambda

Once deploy-dev succeeds, the dev Lambda should report the new SERVICE_VERSION in its telemetry.

Ask the human to verify one of:
- Check the Grafana Cloud dashboard "Hub Platform" (dev Lambda's `service.version` attribute)
- Or check the CloudWatch logs for the dev Lambda: look for `service_version` in any startup message
- Or check `.github/workflows/ci.yml` output to see what `service-version.sh` computed

Expected SERVICE_VERSION:
- If you tagged the commit that was just deployed: `X.Y.Z` (e.g., `0.2.0`)
- If you tagged an earlier commit: `X.Y.Z+N.g<sha>` (e.g., `0.2.0+5.g629aa29`)

Report the actual SERVICE_VERSION.

### 6. Document the release

Summarize for the human:

```
Release: <VERSION>
Commit: <SHA>
Branch: main
Status: deployed to dev

What changed since <PREVIOUS_TAG>:
- [List key commits or features]

Where artifacts are:
- Backend image: dev ECR repo, tag YYYYMMDD-HHMMSS-<sha>
- Frontend: dev S3 + CloudFront
- SERVICE_VERSION on dev Lambda: X.Y.Z[+N.g<sha>]

Next: when ready to promote to prod, run promote.yml workflow manually.
```

### Tech debt notes

This workflow does not yet:
- Run E2E tests before releasing (planned: `e2e-testing` skill)
- Run security scans before releasing (planned: `security-scanning` skill)
- Sync version in `backend/pyproject.toml` and `frontend/package.json` with the git tag
- Publish to PyPI, npm, or GitHub Releases
- Set SERVICE_VERSION on the prod Lambda (it remains off)

## Troubleshooting

**Tag already exists:**
```bash
git tag -d <VERSION>  # delete local tag
git push origin --delete <VERSION>  # delete remote tag
# then re-create and push
```

**CI deploy-dev failed:**
- Check the workflow logs for the specific failure (test, build, infra, frontend, or smoke-test)
- The human should fix the issue and push again (which re-runs CI)
- Do not promote to prod until dev succeeds

**SERVICE_VERSION not updated:**
- SERVICE_VERSION only updates on the next push to main after the tag is pushed
- If the tagged commit was already deployed to dev, dev won't redeploy unless main is pushed again
- Ask the human if they want to push a no-op commit or re-run the CI workflow manually to pick up the tag

**Promoting to prod:**
- This skill does not handle promotion; that is a separate manual `promote.yml` workflow
- The skill has succeeded when dev is deployed and SERVICE_VERSION is verified
- Promotion is a human decision via GitHub Actions
