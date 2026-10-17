# Agent Extension Pack

This document describes the AI agent infrastructure for Hub-Platform: project instructions, reusable skills, a specialized subagent, an MCP server, guard hooks, a custom agent, and how they fit together. `agent-capabilities/README.md` lists every capability in one table.

## Overview

The extension pack enables AI agents to assist with development workflows without hands-on intervention. It consists of:

- **Project instructions**: `AGENTS.md`, the standing rules and commands every agent reads first
- **Skills**: Reusable, discoverable workflows for repeatable tasks (release, security scanning, E2E testing, design review)
- **Subagents**: Specialized agents in fresh contexts for focused tasks (QA engineer for independent validation)
- **MCP server**: Five tools that let an agent work with Hub data through the API, as one signed-in user, with no deletes (`mcp-server/`)
- **Hooks and guardrails**: A Claude Code hook that denies commits, deploys, publishing and secret access, asks before pushes and data loss, and fails closed (`agent-hooks/`), plus the gitleaks pre-commit hook
- **Custom agents**: Agents that respond to an event (the on-call agent: wakes on a Grafana alert, diagnoses it, rolls dev back)
- **Permissions**: Clear boundaries on what agents can and cannot do (`docs/permissions.md`)

## Structure

```
AGENTS.md                       project instructions
.mcp.json                       registers the MCP server for Claude Code
.pre-commit-config.yaml         gitleaks pre-commit hook
.claude/
  ├── settings.json             registers the guard hook (PreToolUse)
  ├── CLAUDE.md                 intentionally empty; AGENTS.md is the source
  ├── skills/
  │   ├── release/SKILL.md
  │   ├── security-scanning/SKILL.md
  │   ├── e2e-testing/SKILL.md
  │   └── design-review/SKILL.md
  └── agents/
      └── qa-engineer.md

agent-capabilities/
  └── README.md                 every capability, in one table

agent-hooks/
  ├── README.md
  ├── guard.py                  the PreToolUse hook (standard library, Python 3.9+)
  ├── ruff.toml
  └── tests/test_guard.py

mcp-server/
  ├── README.md
  ├── hub_mcp/                  server.py (tools), client.py (API client), __main__.py
  ├── tests/                    fake API, tools, contract, stdio, live
  └── pyproject.toml, uv.lock

custom-agent/
  └── on-call-diagnostic/
      └── README.md             code in backend/oncall/

docs/
  ├── agent-extension-pack.md (this file)
  └── permissions.md
```

## Reusable Skills

Skills are discoverable workflows that agents load automatically when they match the task. Located in `.claude/skills/<NAME>/SKILL.md`.

### release

**Purpose**: Tag a new semantic version, push to main, verify dev deployment, and document the release.

**When to use**: When tagging a new version. It deploys to dev only (through CI); promoting to prod is a separate manual step.

**Workflow**:
1. Determine next semantic version
2. Create and push git tag (vX.Y.Z)
3. Push code to main (triggers CI)
4. Wait for dev deploy to complete
5. Verify SERVICE_VERSION on dev Lambda
6. Document what was released and where artifacts are

**Key point**: Tags do not trigger CI; the next push to main does. SERVICE_VERSION is updated on the dev Lambda only.

### security-scanning

**Purpose**: Comprehensive security audit of dependencies, secrets, code patterns, and configuration.

**When to use**: Before releases (gate), on demand for periodic audits.

**Workflow**:
1. Check backend dependencies for vulnerabilities (pip-audit)
2. Check frontend dependencies for vulnerabilities (pnpm audit)
3. Scan git history for secrets (trufflehog)
4. Static analysis: Python (bandit) for SQL injection, hardcoded secrets, weak crypto, etc.
5. Static analysis: JavaScript (ESLint + manual checks) for XSS vectors
6. Configuration security (env files, hardcoded secrets in Terraform)
7. License audit (flags GPL/AGPL/SSPL)
8. Dangerous patterns (unvalidated writes, hardcoded URLs, debug logging)
9. Deep threat analysis with latest Claude security model (as of Oct 2026: Claude Fable 5.1)
10. Summarize findings with risk prioritization and mitigation recommendations

**Key point**: Raw tool findings are escalated to Claude's most capable security model for context-aware judgment. Distinguishes real risks from false positives and evaluates code path reachability.

### e2e-testing

**Purpose**: Run Playwright end-to-end tests, validate test fixtures, and report results.

**When to use**: Before features ship, after QA reports issues, before releases.

**Workflow**:
1. Verify test environment (backend + frontend running, demo data seeded)
2. Install Playwright browsers
3. Run full test suite (or specific tests)
4. Review test output and HTML reports
5. Validate test fixtures (isolation, data setup, cleanup)
6. Report results: pass/fail, timing, failures with evidence

**Test scope**: Auth and sessions, dashboard states, project create/edit/delete, filtering, sorting and search, notes, error states, multiple tabs, rapid sequences, responsive layouts, and every API endpoint with its error cases and user isolation.

**Key point**: The suite is done: 204 Playwright tests in `frontend/tests/` cover all workflows, run against a real backend (local uvicorn, or the Docker Compose stack with Postgres). CI runs them against the Compose stack on every PR and push, and they gate the dev deploy.

### design-review

**Purpose**: Audit UI/UX against best practices, review component library, research emerging tools, and recommend improvements.

**When to use**: Quarterly audits, on demand when evaluating features or tools.

**Workflow**:
1. Review UI/UX against modern standards (visual hierarchy, navigation, forms, data presentation, accessibility, responsiveness)
2. Evaluate component library (Tailwind 4.3, shadcn/ui base-nova, @base-ui/react 1.5, lucide-react)
3. Review data presentation and layout efficiency
4. Research emerging design tools and frameworks (UI libraries, rapid prototyping, design systems, performance/accessibility tools)
5. Identify improvement opportunities (quick wins, medium efforts, future roadmap)
6. Evaluate tool swap opportunities
7. Produce comprehensive design audit report

**Key point**: Research-oriented, not just procedural. Identifies both immediate improvements and longer-term initiatives.

## Specialized Subagents

Subagents run in fresh contexts with specialized roles, preventing implementation bias.

### QA Engineer

**Role**: Independent feature validator in a fresh context without knowledge of implementation details.

**Responsibilities**:
- Run E2E tests (if they exist)
- Test happy path (all acceptance criteria)
- Test edge cases and error paths (empty states, invalid input, rapid interactions, state persistence, accessibility)
- Document findings with severity (CRITICAL, HIGH, MEDIUM, LOW)
- Generate QA report with pass/review/fail status

**What QA does NOT do**:
- Implement fixes (reports findings only)
- Write code
- Make architectural decisions
- Assume implementation details

**When to invoke**: After a feature is implemented and ready for QA review. Say: "Launch QA subagent to review [feature]"

**Output**: QA report with acceptance criteria validation, issues by severity, edge cases tested, and overall status.

**Key point**: Fresh context prevents the "implementer bias" where the person who built something overlooks their own mistakes.

## MCP Server

**Purpose**: Let an AI agent (Claude Code, Claude Desktop, any MCP client) read and update the user's project ideas, the same way the web app does.

**Location**: `mcp-server/` (Python 3.12, the official `mcp` SDK v2, stdio). Registered for Claude Code as the `hub` server in `.mcp.json`.

**Tools**:

| Tool | Kind | Does |
|---|---|---|
| `list_projects` | read-only | Ideas filtered by status, tag or a search query, most recently updated first |
| `get_project` | read-only | One idea in full, with its notes |
| `create_project` | write | Capture a new idea (only the name is required) |
| `update_project` | destructive | Change only the fields given; won't blank text without `allow_clear`; `confirm_bulk` after three status changes in ten minutes |
| `add_note` | write | Add a note to an idea |

**How it works**: `mcp-server/run-with-keychain.sh` reads the password from the macOS keychain and starts the server with it in that process only (never in Claude Code's environment). The server logs in once with `HUB_EMAIL` and that password, then calls the REST API at `HUB_API_URL` (https, or http to a local host only) with a Bearer token, logging in again once if the token expires. Project ids must be UUIDs before they go into a path. Every path it calls is checked against `openapi.yaml` by a test, and its instructions tell the model that user-written text is untrusted data.

**Key point**: No delete tools. The API's ownership checks, limits and caps apply exactly as for the web app, and deleting stays a human action. Details and security notes: `mcp-server/README.md`.

## Hooks and Guardrails

### Guard hook (`agent-hooks/guard.py`)

**Purpose**: Enforce the `AGENTS.md` boundaries mechanically, before an agent's tool call runs, rather than relying on the agent following instructions.

**Trigger**: Claude Code's `PreToolUse` event for `Bash`, `Read`, `Edit`, `Write`, `MultiEdit`, `NotebookEdit` and `Grep` (registered in `.claude/settings.json`, which runs it through `agent-hooks/run-guard.sh`; active for anyone using Claude Code in the repo).

**Denies**: reading or editing real `.env` files, `.secrets` and `*.tfvars`; printing the environment; AWS reads that return secrets; anything that creates a commit (`git commit`, merge, cherry-pick, revert, am, rebase, aliases); `tofu`/`terraform` apply, destroy, import, taint, state changes; starting workflows (`gh workflow run`, `gh run rerun`, `gh api` dispatches); AWS calls that change resources; publishing packages.

**Asks the human**: `git push`, `git tag`, `git pull`, `gh pr merge`, `gh release create`, other `gh api` writes; `aws ecr get-login-password`; `docker compose down -v` and other volume deletion; `alembic downgrade`.

**Key point**: Checks the command inside `bash -c`, `eval` and wrappers such as `env` and `sudo`; fails closed if it crashes or `python3` is missing. Standard library only (Python 3.9+), tested rule by rule, one test per known bypass (`agent-hooks/tests/`). A guardrail against accidents and casual prompt injection, not a sandbox: human review, CI and branch protection stay in place behind it. Details: `agent-hooks/README.md`.

### Secret scan (gitleaks)

`.pre-commit-config.yaml` runs gitleaks on the staged changes before every commit, where a developer has installed it, and CI scans the full history on every push regardless (`security/GITLEAKS_CONFIG.md`).

## Custom Agents

Custom agents respond to external events. The on-call agent is started by a Grafana alert, with no human in the loop on its automatic path.

### On-Call Agent

**Purpose**: Respond first to an alert on real user impact: diagnose it, and on dev fix it by rolling back to the previous image.

**Trigger**: The Grafana Cloud rules "Project creation 5xx rate above 2% (dev)" and "(prod)" (`infra/hub/grafana.tf`): more than 2% of `POST /projects` requests answer 5xx over 5 minutes, with at least 10 requests. The contact point calls GitHub's `repository_dispatch` API (event type `grafana-alert`), which starts `observability-alert-handler.yml`.

**Technology**: Python + OpenAI GPT-4o-mini (no new dependencies; uses stdlib urllib), GitHub Actions, OpenTofu for the rollback

**Workflow**:
1. `triage` (`backend/oncall/alert.py`) reads the payload and ignores anything that isn't a firing or resolved alert from a rule labeled `hub_oncall="true"`
2. `record` opens or reuses the tracking issue
3. `diagnose` makes one OpenAI call (spend guard: $5/month) and posts the diagnosis on the issue
4. On dev, `rollback` calls `rollback-dev.yml`: previous image from ECR, targeted apply of the two dev Lambdas, health check, outcome on the issue (once per incident, never across a migration)
5. On prod, nothing more: a human decides and promotes
6. A resolved notification is recorded on the issue

**Location**: `backend/oncall/` (see `custom-agent/on-call-diagnostic/README.md`)

**Trigger mechanism**: `.github/workflows/observability-alert-handler.yml` (`repository_dispatch`, automatic; `workflow_dispatch`, manual diagnosis with reviewer approval)

**Cost**: one GPT-4o-mini call per firing notification, kept under an estimated $5/month by the spend guard

**Key point**: The one agent allowed to deploy, and only a dev rollback. Interactive agents still never deploy (`AGENTS.md`, `docs/permissions.md`).

## Orchestration and Workflow

### Solo Developer Workflow (Current)

1. **Develop a feature**: Start from a GitHub issue with acceptance criteria; the agent comments progress on it (`AGENT_TEAM.md`)
2. **Self-review**: Use Claude Code interactively to iterate and refine (the guard hook stops it committing, deploying or reading secrets)
3. **Run tests locally**: `make check` (unit tests, lint, format, build, for the backend, frontend, MCP server and hook), then `make test-all` (every test layer, on the Compose stack)
4. **Request QA**: Launch QA subagent to validate independently
5. **Address QA findings**: Fix issues if QA reports problems
6. **Commit and push**: Human commits and pushes to main
7. **CI runs**: GitHub Actions runs unit tests, lint and build, the dependency scan, gitleaks, integration tests, the E2E and live MCP tests against Docker Compose, and the OpenTofu checks, and deploys to dev only if all pass
8. **Verify dev**: Check dev Lambda logs and dashboards
9. **Release**: Use release skill to tag, push, verify dev deployment
10. **Promote to prod**: Manual workflow_dispatch for promote.yml
11. **Respond to alerts**: The on-call agent responds first (diagnosis, and a rollback on dev); read its tracking issue and take it from there

### Parallel Workflow (Future, with git worktrees and multiple agents)

When independent issues can be parallelized:

1. **Orchestrator** (main session) splits backlog into independent tracks
2. **PM agent** grooms an issue in a worktree
3. **SWE agent** implements in a separate worktree
4. **QA agent** validates in a fresh context (no implementation context)
5. **Orchestrator** merges approved work to main one at a time
6. Repeat for up to 5 parallel issues

This is not currently in use but the infrastructure supports it.

## Permissions and Security

See `docs/permissions.md` for detailed permissions model.

**High-level boundaries**:

- **Skills and subagents**: Never commit code, never deploy, never modify .env, never destructive data changes (the first three enforced by the guard hook)
- **Skills and subagents**: Can read code, run tests, generate reports, provide recommendations
- **MCP server**: Acts as one configured user through the public API; can read, create and update that user's ideas and add notes; cannot delete
- **Custom agents**: The on-call agent makes one OpenAI call on the alert summary, records it on a tracking issue, and on dev only rolls back to the previous image; it has no access to user data and no way to reach prod
- **Human**: Reviews agent output, makes all decisions, commits, and promotes to prod; the on-call agent's dev rollback is the only deploy that doesn't wait for a human

## Configuration and Environment

### AGENTS.md

Project-level instructions that all agents read. Covers:
- Project architecture and stack
- Testing requirements
- Agent permissions and boundaries
- Reusable skills and subagents
- Deployment and release gates

### CLAUDE.md

`.claude/CLAUDE.md` exists but is empty on purpose; project instructions live in `AGENTS.md`, so there is one source and the two can't drift. Use it for Claude Code-specific preferences if needed.

### .claude/settings.json and .mcp.json

`.claude/settings.json` registers the guard hook; `.mcp.json` registers the MCP server, started through `mcp-server/run-with-keychain.sh` (the email comes from `HUB_EMAIL`, the password from the macOS keychain; neither is in the file). Claude Code asks once before using a project MCP server.

### Environment setup

Agents expect:
- Backend running locally on http://localhost:8000
- Frontend running locally on http://localhost:5173 (Vite), or the whole system in Docker Compose with the web app on http://localhost:8080
- Demo data seeded: `SEED_DEMO_DATA=true uv run python -m app.db.init_local`
- GitHub Actions configured with OIDC trust for deployment
- Grafana Cloud configured for observability (dev and prod Lambdas)

## Future Work

- **Security scanning in releases**: The dependency scan (pip-audit, pnpm audit) and gitleaks already gate every deploy; the rest of the security-scanning skill (bandit, trivy, IaC scans) still runs by hand. Done: E2E tests in CI (2026-10-02); the MCP server, the guard hook and the capability index (2026-10-13).
- **Design review on schedule**: Quarterly design audits via GitHub Actions scheduled job
- **Multi-agent orchestration**: Formal PM/SWE/QA workflow with git worktrees for feature backlogs
- **Custom agents for other events**: Extend the on-call agent to other alerts (database outages, latency). Done: the automatic trigger and the dev rollback (2026-10-17).
