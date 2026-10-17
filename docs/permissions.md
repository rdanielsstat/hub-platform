# Agent Permissions and Security Boundaries

This document defines what AI agents can and cannot do in the Hub-Platform extension pack.

## Core Principles

1. **Agents advise; humans decide and act.**
   - Agents generate reports, recommendations, and analyses
   - Only humans commit code, deploy, or make architectural decisions

2. **No destructive autonomy.**
   - Agents cannot delete data, reset databases, or modify production state
   - Agents cannot deploy without explicit human approval

3. **Auditable and transparent.**
   - All agent actions are logged and reviewable
   - Humans can trace what an agent did and why

4. **Least privilege.**
   - Agents have only the minimum access needed for their task
   - Agents do not have production database access

5. **Enforced, not only stated.**
   - The guard hook (`agent-hooks/guard.py`) denies commits, deploys, publishing and secret access before the command runs, asks the human before pushes and data loss, and fails closed
   - The MCP server has no delete tools at all, rather than a rule against using them

## Reusable Skills (.claude/skills/)

Skills are workflows that agents execute at human request. The human invokes the skill; the agent follows it.

### Universal permissions (all skills)

**CAN do:**
- Read project files, code, and documentation
- Run local tests and build commands
- Query local databases (SQLite)
- Generate reports and analyses
- Provide recommendations and suggestions
- Run git commands (status, log, diff); `tag` and `push` only after the human confirms (the guard hook asks)

**CANNOT do:**
- Commit code (agent generates summary + suggested message; human commits)
- Deploy to any environment (agent verifies deployment would work; human triggers it)
- Modify `.env` files or any secrets
- Delete data or reset databases
- Modify architecture or make design decisions without asking
- Access production databases or logs
- Run destructive commands (force push, rebase main, etc.)

One exception to "deploy": the release skill pushes to `main`, which deploys to dev automatically through CI. It never deploys to prod.

### Skill-specific details

**release skill**:
- Can: Tag, push tags, push to `main` (which deploys dev only, through CI), wait for the dev deployment, verify SERVICE_VERSION
- Cannot: Deploy to prod (human does via promote.yml)
- Cannot: Modify version in source files (pyproject.toml, package.json); documents that they're out of sync

**security-scanning skill**:
- Can: Run pip-audit, pnpm audit, bandit, truffleHog, ESLint, license checks
- Can: Query Claude's most capable security model for deep analysis
- Cannot: Commit fixes for vulnerabilities; only reports findings
- Cannot: Force-push to remove secrets from history; recommends approach, human executes

**e2e-testing skill**:
- Can: Run Playwright tests, install browsers, generate reports
- Can: Query backend/frontend APIs locally
- Cannot: Modify test fixtures without asking
- Cannot: Commit test fixes; reports failures, human decides

**design-review skill**:
- Can: Inspect UI, run accessibility checks, research tools and alternatives
- Can: Query Claude for design analysis
- Cannot: Make design changes to the codebase; only recommends
- Cannot: Commit changes; produces audit report for human decision

## Specialized Subagents (.claude/agents/)

Subagents run in fresh, isolated contexts with a specialized role.

### QA Engineer subagent

**Role**: Independent feature validator with no knowledge of implementation.

**CAN do:**
- Run E2E tests
- Test features manually against acceptance criteria
- Test edge cases and error paths
- Report findings with severity levels
- Ask clarifying questions about acceptance criteria
- Request backend/frontend restart if needed (asks human)

**CANNOT do:**
- Implement fixes (reports only)
- Write test code or production code
- Make architectural or design decisions
- Access production data or logs
- Commit or deploy anything
- Make decisions about risk acceptance (human decides)

**Data access**:
- Local demo account only (seeded via SEED_DEMO_DATA)
- No access to user accounts or personal data
- Can create test projects/notes within the local session (expected to be ephemeral)

**Context isolation**:
- Subagent starts with no knowledge of how the feature was built
- This prevents "implementer bias" where builders overlook their own mistakes
- QA report is independent and objective

## MCP Server (mcp-server/)

An MCP client (Claude Code, Claude Desktop) the user connects calls these tools, each one a request to the Hub API as one configured user.

**CAN do:**
- List and read that user's project ideas and notes (`list_projects`, `get_project`)
- Create ideas, update their fields, and add notes (`create_project`, `update_project`, `add_note`)
- `update_project` is marked destructive (Claude Code asks before each call), refuses to blank a pitch or description without `allow_clear` (never the name), and refuses a fourth status change within ten minutes without `confirm_bulk`, which the agent may pass only after the user agrees

**CANNOT do:**
- Delete an idea or a note (no tool for it; the client has no DELETE call, and a test keeps it that way)
- See or change another user's data (the API scopes every request to the signed-in user)
- Go beyond the API's checks: field limits, usage caps and the login rate limit apply as for the web app
- Reach the database, AWS, or anything but the Hub API at `HUB_API_URL`
- Reach another endpoint through a crafted project id (ids must be UUIDs)

**Credentials**:
- The password is in the macOS keychain; `mcp-server/run-with-keychain.sh` passes it to the server process only, so it's never in Claude Code's environment or `.mcp.json`. The email comes from `HUB_EMAIL`. Never export `HUB_PASSWORD` in a shell an agent uses
- Never sent over plain http to a remote host (override: `HUB_ALLOW_INSECURE_HTTP=1`, trusted networks only)
- The Bearer token is held in memory for the server's lifetime
- The API has no scoped or read-only tokens, so the agent has the account's full non-delete access: use your own account or a dedicated one, and the demo account locally

**Human control**:
- The user decides whether to connect a client at all, and with which account
- Claude Code asks before using a project MCP server, and before each tool call unless the user has allowed it

## Guard Hook (agent-hooks/)

`agent-hooks/guard.py` runs before every Claude Code `Bash`, `Read`, `Edit`, `Write`, `MultiEdit`, `NotebookEdit` and `Grep` call (`.claude/settings.json`).

**Denies** (the agent is told why and stops):
- Reading, editing or searching real `.env` files, `.secrets` and `*.tfvars` (templates such as `.env.example` are allowed)
- Printing the environment (`printenv`, bare `env`/`set`/`export`, `declare -p`, `ps eww`, `/proc/*/environ`, `$HUB_PASSWORD`)
- AWS reads that return secrets (`ssm` with `--with-decryption`, `secretsmanager`, `kms decrypt`, full Lambda configurations, temporary credentials)
- Anything that creates a commit: `git commit`, `commit-tree`, `merge`, `cherry-pick`, `revert`, `am`, `rebase`, git aliases
- `tofu`/`terraform` apply, destroy, import, taint, untaint, force-unlock, state changes, workspace delete (with or without `-chdir=`); starting workflows (`gh workflow run`/`enable`, `gh run rerun`, `gh api` dispatches); AWS calls that change resources; publishing packages

**Asks the human** (proceeds only on a yes):
- `git push`, `git tag`, `git pull`, `gh pr merge`, `gh release create`, other `gh api` writes
- `aws ecr get-login-password`
- `docker compose down -v`, `docker volume rm`/`prune`, `alembic downgrade`

Commands inside `bash -c`/`sh -c`/`eval` and wrappers (`env`, `sudo`, `xargs`, `nohup`, `nice`, `timeout`) are checked as the command they run. If the hook crashes or `python3` is missing, the call is blocked (fail closed).

**Limits**: It reads command lines as written, so it stops accidents and casual prompt injection, not a determined bypass; the other layers (human review, CI gates, branch protection, no agent credentials) stay in place. Rules and tests: `agent-hooks/README.md`.

## Custom Agents (custom-agent/)

Custom agents respond to external events. The on-call agent is started by a Grafana alert, with no human in the loop on its automatic path; what it may do is scoped below.

### On-call agent

**Role**: Respond first to an alert on real user impact: diagnose it, and on dev, fix it by rolling back to the previous image.

**Trigger**: The Grafana Cloud rules "Project creation 5xx rate above 2% (dev)" and "(prod)" (`infra/hub/grafana.tf`) fire when more than 2% of `POST /projects` requests answer 5xx over 5 minutes, with at least 10 requests in the window. The contact point calls GitHub's `repository_dispatch` API (event type `grafana-alert`), which starts `.github/workflows/observability-alert-handler.yml` on `main`. No human starts or approves the automatic path. A manual path (`workflow_dispatch`, diagnosis only) still waits for reviewer approval in the `observability-oncall` environment.

**CAN do**:
- Read the alert payload (labels, summary, counts) and decide to act or ignore it (`backend/oncall/alert.py`)
- Open, comment on and find a GitHub issue for the incident (`issues: write`, the workflow's own token)
- Make one OpenAI GPT-4o-mini API call for a 2-3 sentence diagnosis and post it on the issue
- **On dev only:** run `rollback-dev.yml`, which points the two dev Lambdas at the previous image in ECR (targeted OpenTofu apply in the dev workspace), checks `/api/health`, and comments the outcome. Once per incident.

**CANNOT do**:
- Touch prod in any way: the rollback workflow never selects the prod workspace or the prod environment (`backend/tests/test_workflow_permissions.py`)
- Roll back across a database migration, or more than once per incident
- Act on an alert without `hub_oncall="true"`, or on a test or malformed payload
- Access any database, logs, metrics or user data
- Change secrets, variables or GitHub settings
- Commit, push or merge code

**Data access**:
- The alert payload's labels and summary; nothing from users
- AWS: only inside `rollback-dev.yml`, through the dev environment's OIDC trust
- OpenAI: `OPENAI_API_KEY`, for the diagnosis only

**Cost controls**:
- Spend guard: the script estimates the monthly cost (one call x 30 runs) and skips the call, with a warning, if it exceeds $5/month
- The notification policy repeats a firing alert at most every 4 hours

**Decision authority**:
- Dev: the agent decides and acts (rollback), then hands over on the issue
- Prod: the agent recommends; a human decides and promotes the fix

**Why this is the only agent that deploys**: interactive agents (Claude Code) never deploy and the guard hook blocks them. The on-call agent is a workflow whose one deploy path is narrow, tested and dev only, and it exists so users on dev aren't left with a broken journey while nobody is watching.

## Integration with CI/CD

### GitHub Actions

**Workflows**:
- `observability-alert-handler.yml`: On-call agent, started by Grafana's alert (`repository_dispatch`), or by hand for a diagnosis only (`workflow_dispatch`, reviewer approval)
- `rollback-dev.yml`: Dev rollback to the previous image, called by the on-call agent or started by hand
- `ci.yml`: Unit tests, dependency scan, gitleaks, integration and E2E tests and the OpenTofu checks run automatically on PR/push (no agent involved)
- `promote.yml`: Human-triggered promotion to prod

**Agent permissions in CI**:
- Read-only: repository files, secrets (used via GitHub contexts)
- Write: GitHub Actions logs, artifacts (build output)
- No write to main branch or tags (except via explicit human action)

### Deployment gates

**Dev deployment** (automatic on main push):
- CI runs; every check passes (unit, dependency scan, gitleaks, integration, E2E)
- No agent approval needed
- CI role has IAM permission to push images to ECR, apply OpenTofu

**Prod promotion** (manual, human-triggered):
- Human reviews CI results and on-call diagnostics
- Human runs promote.yml and types "promote" to confirm
- The job then waits in the GitHub `prod` environment for a required reviewer's approval and a wait timer
- `main` is protected by the `protect-main` ruleset: no force-pushes, no deletion

## Data and Privacy

### What agents can see

**Agents can read:**
- Source code (frontend, backend, infra)
- Architecture and configuration (AGENTS.md, CLAUDE.md, OpenAPI)
- Git history and commit messages
- Test results and logs (local dev, CI logs)
- Grafana metrics (dev only; app-level, no PII)
- General documentation

**Through the MCP server, an agent can read** the project ideas and notes of the one account it's configured with, and nothing else.

**Agents cannot read:**
- Production database (no credentials)
- User data or PII (even from logs; logs sanitized by design)
- Environment variables with secrets (.env files)
- SSM parameters (credentials stored there)
- Credentials in GitHub secrets (used by workflows, not visible to agents)

### What agents output

**Agent outputs are:**
- Shown in the agent session for the human to review
- Logged to GitHub Actions and the tracking issue, for the on-call agent (searchable, auditable)
- Committed to the repo only when a human chooses to

**Agents should NOT output:**
- Credentials, API keys, or tokens
- User PII or sensitive data
- Hardcoded secrets (even in examples)

**Review process**:
- Security reports are reviewed before acting on them
- Recommendations are reviewed before implementation
- On-call diagnoses are reviewed before taking action

## Audit and Oversight

### Logging

Where agent activity is recorded:
- GitHub Actions logs and tracking issues, for workflow runs including the on-call agent (timestamped, accessible)
- Git history, for any changes a human commits
- The agent session, for guard hook decisions (each deny or ask shows its reason) and MCP tool calls
- The Hub API's own logs and traces, for MCP tool calls (they are ordinary API requests)

Skill runs, QA reports, and security scan reports are not saved automatically; they exist only in the agent session unless a human saves them.

**Retention**: GitHub Actions logs are kept per the GitHub default (90 days); anything committed to the repo is kept indefinitely.

### Review

**For manual agent use**:
- Human reviews agent output before acting on recommendations
- Human decides whether to follow, modify, or reject suggestions
- Human commits code (agent provides summary + suggested message)

**For the on-call agent**:
- A reviewer approves every run before it starts
- On-call agent output is visible in GitHub Actions logs
- Human reads diagnosis and decides on remediation

### Audit trail

To audit what an agent did:
1. Check GitHub Actions logs for workflow runs
2. Check git commit history for changes (all manual, reviewed)

## Role-Based Access

### Development (local)

**Skills (release, security-scanning, e2e-testing, design-review):**
- Run locally against local environment
- No production access
- Human-invoked

**QA subagent:**
- Runs locally against demo account
- No production access
- Human-invoked

**MCP server:**
- Against the local API with the demo account, or the deployed API with the user's own account
- Only what that account can do through the API, minus deletes
- Connected by the user; nothing runs until they do

**Guard hook:**
- Runs on the developer's machine, inside Claude Code, before each tool call
- Restricts only; it grants nothing

### Production (via GitHub Actions)

**On-call agent:**
- Started automatically by a Grafana alert on dev or prod (`repository_dispatch`)
- Makes one OpenAI API call and posts the diagnosis on a tracking issue
- On dev only, rolls back to the previous image (`rollback-dev.yml`) and checks health
- No permission to deploy or change anything in prod

**CI/CD workflows:**
- `ci.yml`: Runs tests, builds images, deploys to dev (automatic)
- `promote.yml`: Promotes dev image to prod (human-triggered, environment gate)

## Escalation and Approval

**For blocking security issues:**
- Security-scanning skill flags CRITICAL/HIGH findings
- Human must approve release if issues exist
- Alternatively, human documents risk acceptance (with justification)

**For QA failures:**
- QA subagent reports CRITICAL/HIGH issues
- Feature cannot be merged until issues are resolved or risk is accepted
- Human decides: fix, document exception, or defer

**For on-call diagnoses:**
- The diagnosis is a starting point; the on-call engineer verifies it before acting

## Future Enhancements

- **Automated testing gates**: done. Unit, integration and E2E tests run in CI and gate the dev deploy.
- **Automated security gates**: partly done. The dependency scan blocks on HIGH/CRITICAL and gitleaks blocks on any secret; bandit, trivy and the IaC scans still run by hand.
- **Webhook-triggered on-call**: Grafana alerts trigger on-call agent automatically (currently manual dispatch)
- **Automated remediation**: On-call agent can perform known-safe fixes (requires approval first, high risk)
- **Feedback loop**: On-call engineer rates diagnoses (correct/incorrect); feedback used to improve future diagnoses
- **Cost controls**: partly done. The on-call agent estimates monthly spend and skips the call above $5; no billing alert yet.
