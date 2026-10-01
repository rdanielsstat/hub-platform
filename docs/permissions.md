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
   - Agents do not have production database access (except read-only for diagnostics)

## Reusable Skills (.claude/skills/)

Skills are workflows that agents execute at human request. The human invokes the skill; the agent follows it.

### Universal permissions (all skills)

**CAN do:**
- Read project files, code, and documentation
- Run local tests and build commands
- Query local databases (SQLite)
- Generate reports and analyses
- Provide recommendations and suggestions
- Run git commands (status, log, tag, push)

**CANNOT do:**
- Commit code (agent generates summary + suggested message; human commits)
- Deploy to any environment (agent verifies deployment would work; human triggers it)
- Modify `.env` files or any secrets
- Delete data or reset databases
- Modify architecture or make design decisions without asking
- Access production databases or logs (except on-call agent; see below)
- Run destructive commands (force push, rebase main, etc.)

### Skill-specific details

**release skill**:
- Can: Tag, push tags, trigger CI, wait for deployment, verify SERVICE_VERSION
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
- Can create test projects/interviews within the local session (expected to be ephemeral)

**Context isolation**:
- Subagent starts with no knowledge of how the feature was built
- This prevents "implementer bias" where builders overlook their own mistakes
- QA report is independent and objective

## Custom Autonomous Agents (custom-agent/)

Custom agents run independently in response to external events, with no human in the loop at execution time.

### On-call diagnostic agent

**Role**: Diagnose production alerts and recommend remediation.

**Trigger**: Grafana Cloud alert → GitHub Actions workflow → agent runs

**CAN do**:
- Query CloudWatch logs (read-only, last 100 entries per run)
- Analyze error patterns and root causes
- Query Claude GPT-4o-mini for diagnosis
- Output diagnosis to GitHub Actions logs
- Post findings to GitHub issues (if configured)
- Recommend actions to take

**CANNOT do**:
- Access production database (no credentials provided)
- Access user data or PII
- Modify configuration or environment variables
- Restart services or trigger deployments
- Make any changes to production state
- Commit or push any code
- Send emails or notifications without human review first

**Data access**:
- CloudWatch logs only (no sensitive user data in logs by design)
- Log retention: 7 days (AWS default)
- Logs are application/infrastructure logs, not user data

**Cost controls**:
- API calls are rate-limited to OpenAI's account limits
- Budget: ~$5/month for on-call agent (est. 40 alerts/month)
- High-cost operations are logged and reviewed

**Decision authority**:
- Agent recommends actions; human reads diagnosis and decides
- Human executes any remediation (via deploy pipeline or manual action)

## Integration with CI/CD

### GitHub Actions

**Agent-triggered workflows**:
- `observability-alert-handler.yml`: On-call agent (manual workflow_dispatch)
- `ci.yml`: Tests run automatically on PR/push (no agent involved)
- `promote.yml`: Human-triggered promotion to prod

**Agent permissions in CI**:
- Read-only: repository files, secrets (used via GitHub contexts)
- Write: GitHub Actions logs, artifacts (build output)
- No write to main branch or tags (except via explicit human action)

### Deployment gates

**Dev deployment** (automatic on main push):
- CI runs, tests pass
- No agent approval needed
- CI role has IAM permission to push images to ECR, apply Terraform

**Prod promotion** (manual, human-triggered):
- Human reviews CI results and on-call diagnostics
- Human approves promote.yml workflow
- GitHub environment approval gates the action

## Data and Privacy

### What agents can see

**Agents can read:**
- Source code (frontend, backend, infra)
- Architecture and configuration (AGENTS.md, CLAUDE.md, OpenAPI)
- Git history and commit messages
- Test results and logs (local dev, CI logs)
- Grafana metrics and CloudWatch logs (app-level, no PII)
- General documentation

**Agents cannot read:**
- Production database (no credentials)
- User data or PII (even from logs; logs sanitized by design)
- Environment variables with secrets (.env files)
- SSM parameters (credentials stored there)
- Credentials in GitHub secrets (used by workflows, not visible to agents)

### What agents output

**Agent outputs are:**
- Logged to GitHub Actions (searchable, auditable)
- Stored in `.claude/` and `docs/` (version controlled)
- Visible to anyone with repo access

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

All agent actions are logged:
- GitHub Actions logs (timestamped, accessible)
- `.claude/` skill runs (in version control)
- QA reports and findings (stored in repo)
- Security scan reports (stored in repo)

**Retention**: Logs retained per GitHub Actions default (90 days) + any committed to repo (indefinite).

### Review

**For manual agent use**:
- Human reviews agent output before acting on recommendations
- Human decides whether to follow, modify, or reject suggestions
- Human commits code (agent provides summary + suggested message)

**For autonomous agents**:
- On-call agent output is visible in GitHub Actions logs
- Human reads diagnosis and decides on remediation
- High-severity issues trigger human review

### Audit trail

To audit what an agent did:
1. Check `.claude/skills/` for skill runs and outputs
2. Check GitHub Actions logs for workflow runs
3. Check git commit history for changes (all manual, reviewed)
4. Check `docs/` for agent-generated reports

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

### Production (via GitHub Actions)

**On-call agent:**
- Reads CloudWatch logs (dev Lambda only, prod Lambda eventually)
- Queries OpenAI API
- Posts findings to GitHub
- No deployment or state-change permissions

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

**For on-call diagnostic confidence:**
- If agent diagnosis is low-confidence or issue is CRITICAL, on-call engineer verifies before acting
- Agent notes confidence level in output

## Future Enhancements

- **Automated testing gates**: E2E tests run automatically before release (currently manual)
- **Automated security gates**: Security scanning runs before release, blocks if HIGH/CRITICAL found
- **Webhook-triggered on-call**: Grafana alerts trigger on-call agent automatically (currently manual dispatch)
- **Automated remediation**: On-call agent can perform known-safe fixes (requires approval first, high risk)
- **Feedback loop**: On-call engineer rates diagnoses (correct/incorrect); feedback used to improve future diagnoses
- **Cost controls**: Monthly budget for API calls, with alerts if exceeded
