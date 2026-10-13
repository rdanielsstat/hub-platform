# Agent hooks

Guardrails that turn the boundaries in `AGENTS.md` into checks that run
on their own, instead of relying on an agent remembering the rules.

| Hook | Runs | Enforces |
|---|---|---|
| `guard.py`, through `run-guard.sh` | Claude Code, before every Bash command and file access (`PreToolUse`) | No secrets, no commits, no deploys; a human confirms pushes and data loss |
| gitleaks (`.pre-commit-config.yaml`, repo root) | git, before every commit, where installed | No secret in a commit, whoever (or whatever) wrote it |

## guard.py

Registered in `.claude/settings.json` for the `Bash`, `Read`, `Edit`,
`Write`, `MultiEdit`, `NotebookEdit` and `Grep` tools, so it's active for
anyone running Claude Code in this repo, with nothing to install. Claude
Code runs `run-guard.sh`, which runs `guard.py`: the tool call goes in as
JSON on stdin, and a permission decision comes out on stdout.

### Denied

| What | Why (`AGENTS.md`) |
|---|---|
| Reading, editing or grepping real `.env` files (`.env`, `.env.*`, `*.env`), `.secrets`, `*.tfvars`, through file tools or in a shell command (`cat`, `source`, redirections, `--env-file=`) | Never read secrets into output or edit them. The `.env.example` and `*.tfvars.example` templates are allowed |
| Printing the environment: `printenv`, bare `env`, bare `set`, bare `export` or `export -p`, `declare -p`/`-x`, `typeset -x`, `ps` showing environments (`ps eww`, `ps auxe`, `ps -E`), any `/proc/*/environ` read, and expanding `$HUB_PASSWORD` | Credentials can sit in an environment (the MCP server's password, if it were ever exported). `env FOO=1 cmd`, `set -e` and `export FOO=1` are fine |
| AWS reads that return secrets: `ssm get-parameter(s)`/`get-parameters-by-path` with `--with-decryption`, `secretsmanager get-secret-value`, `kms decrypt`, `lambda get-function`/`get-function-configuration`/`list-functions` (environment variables hold the OTLP token) unless `--query` narrows the output to fields without them (`--query Code.ResolvedImageUri`), `configure export-credentials`, `sts get-session-token`/`assume-role*` | Never read secrets into output. `ssm get-parameter` without decryption, `sts get-caller-identity` and logs are fine |
| Anything that creates a commit: `git commit`, `commit-tree`, `merge`, `cherry-pick`, `revert`, `am`, `rebase`, however written (`git -C dir`, `GIT_*=...`, after `&&`), and git aliases (`git -c alias.x=...`, `git config alias.x ...`), which can hide one | Agents never commit; the human reviews and commits |
| `tofu`/`terraform` `apply`, `destroy`, `import`, `taint`, `untaint`, `force-unlock`, `state rm`/`mv`/`push`/`replace-provider`, `workspace delete`, with or without global options (`-chdir=dir`, `-no-color`) | Agents never deploy (`plan`, `validate`, `fmt`, `state list` are fine) |
| Starting workflows: `gh workflow run`/`enable`, `gh run rerun`, and `gh api` dispatch calls (`.../dispatches`) | Starting CI, deploy or promote workflows is a human action |
| AWS calls that change resources (`update-*`, `create-*`, `delete-*`, `put-*`, `invoke`, `publish-*`; S3 uploads and deletes), wherever the options sit (`--region`, `--profile`, `--cache-control` before or after) | Agents never deploy (`describe`, `list`, `get`, S3 downloads are fine) |
| Publishing packages: `pnpm`/`npm`/`yarn`/`uv`/`poetry publish`, `twine upload` | Agents never publish or deploy |

### Asks the human first

| What | Why |
|---|---|
| `git push`, `git tag` (listing tags is fine), `git pull`, `gh pr merge`, `gh release create`, and other `gh api` writes (`-X POST/PATCH/PUT/DELETE`, or fields, which make it a POST) | Publishes to the remote, and a push to `main` deploys dev; a pull can create a merge commit. The `release` skill does push a tag and `main`; this makes the human confirm each |
| `aws ecr get-login-password` | Prints a registry token (the image scan in `security/IAC_SCANS.md` pipes it to `docker login`) |
| `docker compose down -v`, `docker volume rm`/`prune`, `docker system prune --volumes`, `alembic downgrade` | Deletes the local database or schema (never make destructive data changes) |

Commands run through a wrapper are checked as the command they run:
`bash -c`/`sh -c`/`zsh -c` scripts (also `-lc`, `-ec`) and `eval` are
checked recursively, and `env`, `sudo`, `xargs`, `nohup`, `nice`,
`timeout`, `time`, `command` and `exec` are unwrapped with their options.
A deny anywhere in a command line wins over an ask.

Anything else gets no answer from the hook, and Claude Code's normal
permission settings apply. A deny shows the agent the reason, so it can
explain and stop instead of retrying.

### Design notes

- **Standard library only, Python 3.9+**, so it runs under whatever
  `python3` the machine has (macOS ships 3.9) with nothing to install.
  `ruff.toml` here targets 3.9 so Ruff can't suggest newer syntax.
- **It fails closed.** Input it can't read, and any exception in the
  rules, produce a deny with the reason. `run-guard.sh` blocks the call
  (exit 2, with a message) if `python3` is missing or `guard.py` exits
  with an error, such as a syntax error. A broken hook therefore stops
  the agent instead of silently turning every rule off; fix it with
  `make test-hooks`.
- **Command lines are split outside quotes only.** `;`, `&&`, `||`, `|`
  and `&` inside a quoted string don't split it, so
  `bash -c 'cd infra/hub && tofu apply'` is checked as one script.
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
obfuscated command can get past it: a script file that commits
(`bash deploy.sh`), a program that reads a secret itself
(`python3 -c "open(...)"`), a heredoc fed to a shell, or text assembled
at run time (`eval "$(echo ...)"`). It only covers Claude Code. The other
layers stay in place: the human reviews every change before committing,
gitleaks runs at commit and in CI, `main` can't be force-pushed or
deleted, prod needs a typed confirmation and a reviewer, and agents have
no AWS or production credentials (`security/AGENT_SECURITY.md`).

## Tests

```
python3 -m unittest discover -s agent-hooks/tests -t agent-hooks   # from the repo root
```

Or `make test-hooks`, and `make lint-hooks` for Ruff. CI runs both in the
`test` job. `tests/test_guard.py` checks every rule above with one case
per variant (each bypass found in the 2026-10-13 security sweep has its
own, `security/REMEDIATION_LOG.md`), the cases that must stay allowed
(templates, read-only git, `tofu plan`, S3 downloads, grep patterns,
exclusion options, heredoc bodies, `env FOO=1 cmd`), the hook's JSON
contract with Claude Code by running `guard.py` as a subprocess, and
`run-guard.sh` failing closed with no `python3` and with a crashing hook.
