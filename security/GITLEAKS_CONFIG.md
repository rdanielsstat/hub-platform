# gitleaks: secret scanning

How committed secrets are caught, where the configuration lives, and
how to handle a finding.

## Two layers

| Layer | When | Scope | Config |
|---|---|---|---|
| pre-commit hook | Every `git commit`, where installed | The staged changes | `.pre-commit-config.yaml` |
| CI `secrets-scan` job | Every PR and every push | The **full git history** | `.github/workflows/ci.yml` |

Both use gitleaks 8.30.1 with its built-in rules (there's no custom
`.gitleaks.toml`). Both read `.gitleaksignore` for reviewed false
positives.

### pre-commit hook

Opt-in per clone, so it can't be relied on, only helps:

```
uvx pre-commit install           # once per clone
uvx pre-commit run --all-files   # scan the working tree by hand
```

pre-commit builds gitleaks from source on first run (it fetches its own
Go toolchain). A hit blocks the commit and prints the file, line and
rule.

### CI job

`secrets-scan` in `ci.yml`:

- checks out with `fetch-depth: 0` (full history);
- downloads the gitleaks release tarball and verifies its SHA-256
  against a pinned checksum before running it, so a tampered download
  fails the job;
- runs `gitleaks git --redact --no-banner --verbose .`; `--redact` keeps
  secret values out of the job log;
- `deploy-dev` needs it, so nothing deploys while a finding is open.

Full history rather than just the new commits: it takes seconds, and it
also catches a secret that arrives through a force-push or rewritten
history.

To bump the version, change `GITLEAKS_VERSION` and `GITLEAKS_SHA256`
in `ci.yml` (checksum from the release's checksums file) and `rev` in
`.pre-commit-config.yaml` together.

## False positives: .gitleaksignore

One fingerprint per line: `<commit>:<file>:<rule>:<line>`. Each silences
exactly that one finding, so the same value anywhere else, including the
same file in a later commit, is still reported.

Current entries (2):

| Fingerprint (abbreviated) | What it is |
|---|---|
| `7bbf23d...:frontend/tests/api.spec.ts:generic-api-key:90` | Test fixture password for the duplicate-email E2E case |
| `de9737e...:README.md:curl-auth-header:529` | README curl example with a placeholder password, since rewritten |

## Handling a finding

1. **Look at the value.** Run the scan locally without `--redact` to see
   it: `gitleaks git --verbose .` (or the pre-commit output).
2. **If it's a real secret**, treat it as leaked the moment it was
   pushed, whether or not the repo is public (it is):
   - rotate it first (new value in SSM or the provider; for the JWT
     secret, every session is invalidated, which is fine);
   - then remove it from the code going forward;
   - rewriting history is optional once rotated, and needs a human: it
     means a force-push to `main`, which agents never do.
   - **Never** add a real secret to `.gitleaksignore`.
3. **If it's a false positive** (test fixture, placeholder, example):
   copy the fingerprint gitleaks prints into `.gitleaksignore` with a
   one-line comment saying what the value is and why it's safe. A
   reviewer should check the value before approving that line.

Prefer avoiding the false positive in the first place: test passwords
that don't look like keys, and `<placeholder>` style values in docs.

## What's not covered

- Secrets in places that aren't git: GitHub Actions logs (gitleaks runs
  with `--redact`, and Actions masks registered secrets), CloudWatch
  logs (the app never logs secrets; origin verification logs only
  whether the header was missing or wrong), local `.env` files
  (gitignored, and agents don't read them).
- Built images: nothing scans the backend image for embedded secrets.
  The Dockerfile copies only `app/`, `observability/` and `alembic/`,
  and `.dockerignore` excludes `.env*` files, so none should get in.
