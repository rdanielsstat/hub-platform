# Agent capabilities

Everything an AI agent can do in this repo, in one list: what each
capability is, where it lives, and what it's allowed to do. The files
themselves stay where their tools look for them (Claude Code discovers
skills in `.claude/skills/`, for example); this is the index.

Every capability works inside the boundaries in `AGENTS.md`: agents never
commit, deploy, read secrets or delete data, and a human reviews
everything. `agent-hooks/guard.py` enforces the first three.

## Capabilities

| Capability | Kind | Where | Invoked by | Can | Cannot |
|---|---|---|---|---|---|
| Project instructions | Context | `AGENTS.md` | Read by every agent at the start of a session | (instructions) | |
| `release` | Skill (reusable workflow) | `.claude/skills/release/SKILL.md` | A human asking to release | Tag, push a tag and `main` (dev deploys through CI), verify dev | Promote to prod; push without the human confirming (the hook asks) |
| `e2e-testing` | Skill | `.claude/skills/e2e-testing/SKILL.md` | A human asking to run or check the E2E tests | Start a local backend, run Playwright, report | Change fixtures without asking; commit fixes |
| `security-scanning` | Skill | `.claude/skills/security-scanning/SKILL.md` | A human, before a release or for an audit | Run pip-audit, pnpm audit, bandit, trufflehog, trivy, the IaC scans; report | Commit fixes; rewrite history |
| `design-review` | Skill | `.claude/skills/design-review/SKILL.md` | A human, on demand or quarterly | Audit the UI, research tools, recommend | Change the code |
| QA engineer | Subagent (fresh context) | `.claude/agents/qa-engineer.md` | "Launch QA subagent to review [feature]" | Run the tests, check acceptance criteria and edge cases, report PASS or FAIL with evidence | Implement fixes |
| Hub MCP server | MCP server (5 tools) | `mcp-server/`, registered in `.mcp.json` | An MCP client (Claude Code, Claude Desktop) the user connects | List, read, create and update the user's project ideas (updates are destructive: Claude Code asks; no blanking without `allow_clear`; `confirm_bulk` for mass status changes); add notes | Delete anything; act as anyone but the configured user; reach other endpoints (ids must be UUIDs); see the password (keychain wrapper) |
| Guard hook | Hook (guardrail) | `agent-hooks/guard.py`, registered in `.claude/settings.json` | Claude Code, before every shell command and file access | Deny secret access (files, environment, AWS), commits, deploys and publishing; ask before pushes and data loss; fail closed | (it only restricts) |
| Secret scan | Hook (guardrail) | `.pre-commit-config.yaml` (gitleaks) | git, before every commit, where installed; CI scans the full history regardless | Block a commit containing a secret | |
| On-call diagnostic | Custom agent | `custom-agent/on-call-diagnostic/README.md`, code in `backend/oncall/` | A human, after a Grafana alert, with a reviewer's approval (`observability-alert-handler.yml`) | One OpenAI call on the pasted alert text; write a diagnosis to the run log | Change anything; see user data |

## More

- How the pieces fit together, and the workflows that use them:
  `docs/agent-extension-pack.md`
- The permission model, per capability: `docs/permissions.md`
- The risks behind the rules, and how each is contained:
  `security/AGENT_SECURITY.md`
- What data reaches which AI service: `security/DATA_POLICY.md`
