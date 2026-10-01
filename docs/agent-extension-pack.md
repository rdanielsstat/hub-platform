# Agent Extension Pack

This document describes the AI agent infrastructure for Hub-Platform: reusable skills, specialized subagents, custom autonomous agents, and how they orchestrate.

## Overview

The extension pack enables AI agents to assist with development workflows without hands-on intervention. It consists of:

- **Skills**: Reusable, discoverable workflows for repeatable tasks (release, security scanning, E2E testing, design review)
- **Subagents**: Specialized agents in fresh contexts for focused tasks (QA engineer for independent validation)
- **Custom agents**: Autonomous agents that trigger on events without human interaction (on-call diagnostic for production alerts)
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
      ├── README.md
      ├── diagnose.py
      └── WORKFLOW.md

docs/
  ├── agent-extension-pack.md (this file)
  ├── permissions.md
  └── ops/
      └── on-call-alerting.md
```

## Reusable Skills

Skills are discoverable workflows that agents load automatically when they match the task. Located in `.claude/skills/<NAME>/SKILL.md`.

### release

**Purpose**: Tag a new semantic version, push to main, verify dev deployment, and document the release.

**When to use**: When releasing a new version to production.

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

**Test scope**: Auth, project CRUD, interview workflow, search/filtering, navigation, accessibility, responsive design, edge cases.

**Key point**: Tests are currently planned; skill is template-ready for when Playwright is integrated.

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

## Custom Autonomous Agents

Custom agents run independently, triggered by external events, with no human in the loop.

### On-Call Diagnostic Agent

**Purpose**: Automatically diagnose and respond to production alerts from Grafana without human intervention.

**Trigger**: Grafana Cloud alert fired → webhook to GitHub Actions → `observability-alert-handler.yml` → on-call diagnostic agent runs

**Technology**: Python + OpenAI GPT-4o-mini (no new dependencies; uses stdlib urllib)

**Workflow**:
1. Receive alert details (service, metric, threshold, current value)
2. Query backend Lambda CloudWatch logs for context
3. Analyze error patterns and symptom root cause
4. Recommend remediation (code fix, infra change, monitoring adjustment)
5. Output diagnosis to GitHub Actions log
6. Post summary to GitHub issue (if applicable)

**Location**: `backend/oncall/diagnose.py`

**Trigger mechanism**: `.github/workflows/observability-alert-handler.yml` (manual workflow_dispatch, but could be automated via Grafana webhook)

**Cost**: ~$0.000060-0.000198 per run (~$5/month budget for frequent alerts)

**Key point**: Autonomous, fire-and-forget. Reduces MTTR (mean time to recovery) for production issues by diagnosing while the human reads the alert.

## Orchestration and Workflow

### Solo Developer Workflow (Current)

1. **Develop a feature**: Write code, commit regularly
2. **Self-review**: Use Claude Code interactively to iterate and refine
3. **Run tests locally**: Verify all tests pass (unit, lint, format, build)
4. **Request QA**: Launch QA subagent to validate independently
5. **Address QA findings**: Fix issues if QA reports problems
6. **Commit and push**: Human commits and pushes to main
7. **CI runs**: GitHub Actions runs tests and deploys to dev
8. **Verify dev**: Check dev Lambda logs and dashboards
9. **Release**: Use release skill to tag, push, verify dev deployment
10. **Promote to prod**: Manual workflow_dispatch for promote.yml
11. **Monitor**: On-call agent watches for issues

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
- **Custom agents**: Can query logs, analyze data, post findings; cannot access production data or make infrastructure changes
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

(Optional; not used for Hub-Platform.) Claude Code-specific preferences if needed.

### Environment setup

Agents expect:
- Backend running locally on http://localhost:8000/api
- Frontend running locally on http://localhost:5173
- Demo data seeded: `SEED_DEMO_DATA=true uv run python -m app.db.init_local`
- GitHub Actions configured with OIDC trust for deployment
- Grafana Cloud configured for observability (dev Lambda only)

## Future Work

- **E2E automation in CI**: Wire e2e-testing skill into GitHub Actions on releases
- **Security scanning in releases**: Wire security-scanning skill into release gate
- **Design review on schedule**: Quarterly design audits via GitHub Actions scheduled job
- **Multi-agent orchestration**: Formal PM/SWE/QA workflow with git worktrees for feature backlogs
- **Custom agents for other events**: Extend on-call agent to handle other production scenarios (deployment rollback, database alerts, etc.)
