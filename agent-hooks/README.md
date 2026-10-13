# Agent hooks

Guardrails that turn the boundaries in `AGENTS.md` into checks that run
on their own, instead of relying on an agent remembering the rules.

| Hook | Runs | Enforces |
|---|---|---|
| `guard.py` | Claude Code, before every Bash command and file access (`PreToolUse`) | No secrets, no commits, no deploys; a human confirms pushes and data loss |
| gitleaks (`.pre-commit-config.yaml`, repo root) | git, before every commit, where installed | No secret in a commit, whoever (or whatever) wrote it |

## guard.py

Registered in `.claude/settings.json` for the `Bash`, `Read`, `Edit`,
`Write`, `MultiEdit`, `NotebookEdit` and `Grep` tools, so it's active for
anyone running Claude Code in this repo, with nothing to install. Claude
Code sends each tool call to it as JSON on stdin; it answers with a
permission decision on stdout.

### Denied

| What | Why (`AGENTS.md`) |
|---|---|
| Reading, editing or grepping real `.env` files (`.env`, `.env.*`, `*.env`), `.secrets`, `*.tfvars`, through file tools or in a shell command (`cat`, `source`, redirections, `--env-file=`) | Never read secrets into output or edit them. The `.env.example` and `*.tfvars.example` templates are allowed |
| `git commit`, however written (`git -C dir commit`, `GIT_*=... git commit`, after `&&`) | Agents never commit; the human reviews and commits |
| `tofu`/`terraform` `apply`, `destroy`, `import`, `taint` | Agents never deploy (`plan`, `validate`, `fmt` are fine) |
| `gh workflow run`/`enable` | Starting CI, deploy or promote workflows is a human action |
| AWS calls that change resources (`update-*`, `create-*`, `delete-*`, `put-*`, `invoke`, `publish-*`; S3 uploads and deletes) | Agents never deploy (`describe`, `list`, `get`, S3 downloads are fine) |

### Asks the human first

| What | Why |
|---|---|
| `git push`, `git tag` (listing tags is fine), `gh pr merge`, `gh release create` | Publishes to the remote, and a push to `main` deploys dev. The `release` skill does push a tag and `main`; this makes the human confirm each |
| `docker compose down -v`, `docker volume rm`/`prune`, `docker system prune --volumes`, `alembic downgrade` | Deletes the local database or schema (never make destructive data changes) |

Anything else gets no answer from the hook, and Claude Code's normal
permission settings apply. A deny shows the agent the reason, so it can
explain and stop instead of retrying.

### Design notes

- **Standard library only, Python 3.9+**, so it runs under whatever
  `python3` the machine has (macOS ships 3.9) with nothing to install.
  `ruff.toml` here targets 3.9 so Ruff can't suggest newer syntax.
- **It never blocks on its own failure.** Input that isn't a hook payload
  gets no decision.
- **Patterns are not paths.** A word with regex or glob characters
  (`grep '\.env'`) isn't treated as a file, so searching for the string
  `.env` is fine. `$VAR/.env` still counts as a path.
- **Excluding a file isn't reading it.** The value of an exclusion option
  (`--exclude`, `--exclude-dir`, `--exclude-path`, `--ignore`,
  `--ignore-path`, `--skip-path`) is skipped, so the documented scans
  (`tfsec ... --exclude-path terraform.tfvars`, `checkov --skip-path`)
  run. Only that one value is skipped.
- **Heredoc bodies are data.** The text between `<<EOF` and `EOF` (a file
  being written, a script for `python3 -`) isn't checked as command words,
  so writing documentation that mentions `.env` is fine. The operator's
  own line is still checked: `cat <<EOF > backend/.env` is denied.

### Limits

It's a guardrail against accidents and casual prompt injection, not a
sandbox. It reads the command line as written, so a deliberately
obfuscated command (`eval "$(echo ...)"`, a script or a heredoc fed to a
shell that commits) can get past it, and it only covers Claude Code. The other layers stay in place:
the human reviews every change before committing, gitleaks runs at commit
and in CI, `main` can't be force-pushed or deleted, prod needs a typed
confirmation and a reviewer, and agents have no AWS or production
credentials (`security/AGENT_SECURITY.md`).

## Tests

```
python3 -m unittest discover -s agent-hooks/tests -t agent-hooks   # from the repo root
```

Or `make test-hooks`, and `make lint-hooks` for Ruff. CI runs both in the
`test` job. `tests/test_guard.py` checks every rule above, the cases that
must stay allowed (templates, read-only git, `tofu plan`, S3 downloads,
grep patterns, exclusion options, heredoc bodies), and the hook's JSON contract with Claude Code, by running
`guard.py` as a subprocess.
