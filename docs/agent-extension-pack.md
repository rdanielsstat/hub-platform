# Agent Extension Pack

This document describes the AI agent infrastructure for Hub-Platform: reusable skills, specialized subagents, custom agents, and how they orchestrate.

## Overview

The extension pack enables AI agents to assist with development workflows without hands-on intervention. It consists of:

- **Skills**: Reusable, discoverable workflows for repeatable tasks (release, security scanning, E2E testing, design review)
- **Subagents**: Specialized agents in fresh contexts for focused tasks (QA engineer for independent validation)
- **Custom agents**: Agents a person runs in response to an event, with reviewer approval (on-call diagnostic for Grafana alerts in dev)
- **Permissions & guardrails**: Clear boundaries on what agents can and cannot do

## Structure

```
.claude/
  ├── skills/
  │   ├── release/SKILL.md
  │   ├── security-scanning/SKILL.md
  │   ├── e2e-testing/SKILL.md
  │   └── design-review/SKILL.md
  └── agents/
      └── qa-engineer.md

custom-agent/
  └── on-call-diagnostic/
      └── README.md

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

**Key point**: The suite is done: 202 Playwright tests in `frontend/tests/` cover all workflows, run against a real backend (local uvicorn, or the Docker Compose stack with Postgres). CI runs them against the Compose stack on every PR and push, and they gate the dev deploy.

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

## Custom Agents

Custom agents are run by a person in response to an external event, with a reviewer approving each run.

### On-Call Diagnostic Agent

**Purpose**: Give the on-call person a quick first diagnosis of a Grafana alert in the dev environment.

**Trigger**: The Grafana Cloud alert rule "Registration Error Rate > 10%" fires when more than 10% of dev registration requests return an error (4xx or 5xx) for 5 minutes. Its webhook notifies the on-call person, who starts `observability-alert-handler.yml` by hand in GitHub Actions.

**Technology**: Python + OpenAI GPT-4o-mini (no new dependencies; uses stdlib urllib)

**Workflow**:
1. The on-call person starts the workflow with two inputs: `alert_summary` (the alert text) and `runs_per_month` (for the cost estimate)
2. The run waits for a reviewer's approval in the `observability-oncall` environment
3. The script estimates the monthly cost and skips the call, with a warning, if it would exceed $5/month
4. It makes one OpenAI API call for a 2-3 sentence diagnosis: likely causes and the first thing to check or fix
5. The diagnosis and cost estimate are written to the GitHub Actions run log and job summary

**Location**: `backend/oncall/diagnose.py` (see `custom-agent/on-call-diagnostic/README.md`)

**Trigger mechanism**: `.github/workflows/observability-alert-handler.yml` (manual `workflow_dispatch`, with reviewer approval)

**Cost**: one GPT-4o-mini call per approved run, kept under an estimated $5/month by the spend guard

**Key point**: A read-only diagnostic aid. The on-call person reads the diagnosis and decides what to do.

## Orchestration and Workflow

### Solo Developer Workflow (Current)

1. **Develop a feature**: Write code, commit regularly
2. **Self-review**: Use Claude Code interactively to iterate and refine
3. **Run tests locally**: `make check` (unit, lint, format, build), plus `make test-integration` for database changes
4. **Request QA**: Launch QA subagent to validate independently
5. **Address QA findings**: Fix issues if QA reports problems
6. **Commit and push**: Human commits and pushes to main
7. **CI runs**: GitHub Actions runs unit tests, the dependency scan, gitleaks, integration and E2E tests, and deploys to dev only if all pass
8. **Verify dev**: Check dev Lambda logs and dashboards
9. **Release**: Use release skill to tag, push, verify dev deployment
10. **Promote to prod**: Manual workflow_dispatch for promote.yml
11. **Respond to alerts**: When the Grafana alert notifies you, run the on-call diagnostic and review its output

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

- **Skills and subagents**: Never commit code, never deploy, never modify .env, never destructive data changes
- **Skills and subagents**: Can read code, run tests, generate reports, provide recommendations
- **Custom agents**: The on-call diagnostic makes one OpenAI call on the alert text it is given and writes the diagnosis to the run log; it has no access to data or infrastructure
- **Human**: Reviews agent output, makes all decisions, commits and deploys manually

## Configuration and Environment

### AGENTS.md

Project-level instructions that all agents read. Covers:
- Project architecture and stack
- Testing requirements
- Agent permissions and boundaries
- Reusable skills and subagents
- Deployment and release gates

### CLAUDE.md

`.claude/CLAUDE.md` exists but is empty; project instructions live in `AGENTS.md`. Use it for Claude Code-specific preferences if needed.

### Environment setup

Agents expect:
- Backend running locally on http://localhost:8000
- Frontend running locally on http://localhost:5173
- Demo data seeded: `SEED_DEMO_DATA=true uv run python -m app.db.init_local`
- GitHub Actions configured with OIDC trust for deployment
- Grafana Cloud configured for observability (dev and prod Lambdas)

## Future Work

- **Security scanning in releases**: The dependency scan (pip-audit, pnpm audit) and gitleaks already gate every deploy; the rest of the security-scanning skill (bandit, trivy, IaC scans) still runs by hand. Done: E2E tests in CI (2026-10-02).
- **Design review on schedule**: Quarterly design audits via GitHub Actions scheduled job
- **Multi-agent orchestration**: Formal PM/SWE/QA workflow with git worktrees for feature backlogs
- **Custom agents for other events**: Extend on-call agent to handle other production scenarios (deployment rollback, database alerts, etc.)
