---
name: security-scanning
description: Run comprehensive security checks on dependencies, secrets, code patterns, and configuration
---

# Security Scanning

Perform a thorough security audit of the codebase: check for dependency vulnerabilities, detect secrets in history, run static analysis, and flag dangerous patterns in code and configuration.

## When to run

- Before tagging a release (check via `release` skill)
- On demand to audit the current state
- Periodically (quarterly) to stay ahead of new vulnerabilities

## Prerequisites

- You are in the repo root
- Backend and frontend dependencies are installed (`uv sync` in backend/, `pnpm install` in frontend/)
- No uncommitted changes (or they are staged for review)

## Steps

### 1. Check backend dependencies for vulnerabilities

From `backend/`:

```bash
uv export --frozen --no-hashes --format requirements-txt > /tmp/hub-requirements.txt
uvx pip-audit --disable-pip --no-deps -r /tmp/hub-requirements.txt
```

(`uv export` pins every dependency, so `--disable-pip --no-deps` audits that exact list without building a temporary virtualenv.)

Report any vulnerabilities found:
- If severity is HIGH or CRITICAL, report the issue and stop
- If severity is MEDIUM or LOW, document it but continue
- For each vuln, note: package, version, CVE, and whether there's a fix available

Also check for known issues in the uv.lock:

```bash
grep -E 'rsa|pycryptodome|pyyaml' uv.lock | head -20
```

(These are historically problematic; report any unexpected versions.)

### 2. Check frontend dependencies for vulnerabilities

From `frontend/`:

```bash
pnpm audit --audit-level=moderate
```

Report findings same as backend:
- HIGH/CRITICAL stops the scan; report and exit
- MEDIUM/LOW is documented and continues

Check for suspicious package names in package.json:

```bash
grep -E '"dependencies":|"devDependencies":' package.json -A 30 | grep -E '"[^"]*(eval|shell|exec)[^"]*":'
```

(Should find nothing; if it does, look at the package. The pattern leaves out "script" on purpose: it would always match `typescript`.)

### 3. Scan for secrets in git history

Check if any secrets (keys, tokens, passwords) are accidentally committed:

```bash
# Install the v3 binary if needed (the pip package "truffleHog" is the old v2 tool and doesn't support these flags)
brew install trufflehog

# Scan the last 50 commits
trufflehog git file://. --since-commit HEAD~50 --only-verified
```

If secrets are found:
- Report the location (file, commit, line)
- Recommend rotating any exposed credentials
- Suggest using git filter-branch or BFG to remove from history (if in prod)

### 4. Static analysis: Python (backend)

From `backend/`:

```bash
uvx bandit -r app/ --severity-level=medium
```

(Bandit exits non-zero when it finds issues at or above that severity.)

Bandit checks for:
- SQL injection risks (unparameterized queries)
- Hardcoded secrets
- Use of insecure crypto (MD5, SHA1)
- Unsafe pickle usage
- Weak random number generators
- Disabled SSL verification

Report each finding with:
- File, line number, function
- Issue description
- Severity (HIGH/MEDIUM)
- Remediation (if obvious)

### 5. Static analysis: JavaScript (frontend)

From `frontend/`:

```bash
pnpm lint --max-warnings=0
```

ESLint has no security plugins configured (only the React hooks and React Refresh rules), so lint mostly catches correctness issues. Report any warnings that bear on security. Then check manually for:

```bash
grep -r "eval(" src/ --include="*.ts" --include="*.tsx"
grep -r "dangerouslySetInnerHTML" src/ --include="*.tsx"
grep -r "innerHTML\s*=" src/ --include="*.ts" --include="*.tsx"
```

(These are XSS vectors; should not appear. If they do, report them.)

### 6. Configuration and environment security

Check `.env` and environment handling:

```bash
# Should not exist in repo (should be .gitignored)
ls -la .env* 2>/dev/null | grep -v example

# Check .gitignore covers secrets
grep -E '.env|.key|.pem|credentials|secret' .gitignore

# Check infra secrets aren't hardcoded
grep -r 'HUB_JWT_SECRET\|PASSWORD\|TOKEN\|KEY' infra/ --include="*.tf" --exclude-dir=.terraform | grep -v 'var\.' | grep -v 'ssm' | grep -v 'default'
```

Report:
- Any .env files in repo (should all be .gitignored)
- Missing .gitignore entries
- Hardcoded secrets in Terraform (should use SSM, not literals)

### 7. Dependency license audit

Check that no GPL or other restrictive licenses sneak in:

```bash
# From backend/: runs pip-licenses inside the project's environment
uv run --with pip-licenses pip-licenses --fail-on="GNU General Public License;GNU Affero General Public License"

# For frontend (manual check of package.json)
pnpm licenses list 2>/dev/null | grep -E 'GPL|AGPL|SSPL'
```

Report any GPL/AGPL/SSPL dependencies. If found, evaluate whether they are dev-only or transitive; if in production code, that's a legal risk.

### 8. Check for known dangerous patterns

```bash
# Python: no direct file writes without validation
grep -r "open(" backend/app --include="*.py" | grep -v "test" | grep -v "rb\|r'" | head -10

# Check for hardcoded URLs/IPs
grep -rE '(http|ftp)://[0-9]{1,3}\.[0-9]{1,3}' backend/ frontend/src --include="*.py" --include="*.ts" --include="*.tsx"

# Check for debug/logging that might leak data
grep -r "print(" backend/app --include="*.py" | grep -v "test" | head -5
```

(These are not necessarily exploits, but risky patterns worth reviewing.)

### 9. Deep threat analysis with the latest Claude model optimized for security

For nuanced risk assessment and context-aware judgment, escalate findings to Claude's most capable model with cybersecurity expertise. As of October 2026, this is Claude Fable 5.1 (Mythos-tier with cybersecurity safety measures), but future releases may offer better alternatives.

This model excels at:
- Distinguishing real exploitable risks from tool noise and false positives
- Evaluating whether vulnerabilities are reachable in your specific code paths
- Recommending pragmatic mitigations when fixes are unavailable
- Providing business-context risk judgment (not just tool severity scores)

**Prepare a summary for the model:**

Collect all findings from steps 1-8 and ask the latest Claude security model to evaluate:

```
I've run a comprehensive security scan on the Hub-Platform codebase.
Here are the findings:

[Dependency vulnerabilities]
- Backend: <list pip-audit findings with severity and fixability>
- Frontend: <list pnpm audit findings with severity and fixability>

[Secrets in history]
- <list any findings, age, whether rotated>

[Static analysis issues]
- Python (bandit): <list findings with file/line>
- JavaScript (ESLint): <list findings with file/line>

[Configuration risks]
- <list .env, hardcoded secrets in Terraform, etc.>

[License issues]
- <list GPL/AGPL/SSPL dependencies, if any>

[Dangerous patterns]
- <list unvalidated writes, hardcoded URLs, debug logging>

Please evaluate these findings and provide:

1. Real vs. false positive assessment
   - Which findings are actual exploitable risks?
   - Which are tool noise or acceptable patterns in this context?

2. Context-aware risk assessment
   - For hardcoded secrets/URLs in dev-only config: is the exposure real?
   - For unpatched vulnerabilities: are they reachable in the code path?
   - For lint warnings: which ones are security-critical vs. style?

3. Prioritization
   - Which should be fixed immediately (blocking release)?
   - Which should be fixed in the next sprint (high priority)?
   - Which are acceptable to defer (low risk)?

4. Mitigation recommendations
   - For issues without immediate fixes, what's the safe approach?
   - Are there compensating controls (e.g., WAF, rate limiting)?
   - Should this be tracked as tech debt?

5. Overall risk assessment
   - Is the codebase secure enough to release?
   - Are there patterns or practices to change long-term?

Output a prioritized risk report.
```

**Fable will provide:**
- Exploitation likelihood (not just tool severity)
- Business impact assessment
- Pragmatic fix recommendations (vs. "fix everything")
- Risk acceptance guidance (when fixing is infeasible)
- Compensating control suggestions

Record Fable's assessment for the final summary (step 10).

### 10. Summarize findings (incorporating Fable's assessment)

Produce a comprehensive report that combines tool findings with Fable's risk evaluation:

```
Security Scan Summary
====================

Tool findings:
  Backend dependencies: [✓ PASS | X FAIL] 
    - <N> vulnerabilities found
    - Severity: [HIGH|MEDIUM|LOW]
    - Fixable: [Y|N]

  Frontend dependencies: [✓ PASS | X FAIL]
    - <N> vulnerabilities found
    - Severity: [HIGH|MEDIUM|LOW]
    - Fixable: [Y|N]

  Secrets in history: [✓ CLEAN | X FOUND]
    - <N> potential secrets detected
    - Age and rotation status: [list]

  Static analysis (Python): [✓ PASS | X ISSUES]
    - <N> issues found, severities: [list]

  Static analysis (JavaScript): [✓ PASS | X ISSUES]
    - <N> issues found

  Configuration: [✓ SECURE | X RISKS]
    - .env files in repo: [Y|N]
    - Hardcoded secrets in infra: [Y|N]

  Licenses: [✓ OK | X ISSUES]
    - Restrictive licenses found: [Y|N]

  Dangerous patterns: [✓ NONE | X REVIEW]
    - Unvalidated file writes: [Y|N]
    - Hardcoded URLs: [Y|N]

Fable's risk assessment (Claude 5.1 Mythos-tier cybersecurity evaluation):
  Real vs. false positive breakdown:
    - True risks: [N] ([list critical and high-priority issues])
    - False positives or acceptable patterns: [N] ([list with explanation])

  Prioritized risk breakdown:
    - Blocking (must fix before release): [list with mitigation]
    - High priority (fix in next sprint): [list with workaround]
    - Medium priority (acceptable to defer): [list with compensating controls]
    - Low risk (track as tech debt): [list]

  Context-aware findings:
    - Hardcoded secrets/URLs in dev-only config: [acceptable | need rotation]
    - Unpatched vulnerabilities: [exploitable in code path | unreachable | mitigated]
    - Lint issues: [security-critical | style-only]

  Recommended mitigations:
    - For unfixable issues: [compensating control | risk acceptance]
    - Long-term practices to adopt: [list]

Overall assessment:
  Security posture: [✓ STRONG | ⚠ ACCEPTABLE | X WEAK]
  Release readiness: [✓ APPROVED | ⚠ CONDITIONAL | X BLOCKED]
  
  If APPROVED: ready for release; document any conditional approvals
  If CONDITIONAL: approve release with documented risk acceptance (specific items and justification)
  If BLOCKED: blocking issues must be fixed before release; list them and required remediation

Risk acceptance (if applicable):
  Issue: <issue>
  Risk: <impact if exploited>
  Mitigation: <control in place>
  Accepted by: [human approval required]
```

## Best practices in this skill

**Deep analysis with the latest Claude security model:** This skill escalates findings to Claude's most capable model for cybersecurity (as of October 2026: Claude Fable 5.1; subject to change as new models release) for context-aware risk assessment. This model excels at:
- Distinguishing real exploitable risks from tool noise
- Evaluating whether vulnerabilities are reachable in your code
- Recommending pragmatic mitigations when fixes are unavailable
- Providing business-context risk judgment (not just severity scores)

This ensures the final risk assessment is accurate and actionable, not just raw tool output. The skill will remain current as Claude releases new models; update the model reference if a better alternative becomes available.

## Tech debt and limitations

This skill does not yet:
- Run container image scans (ECR image vulnerability scanning)
- Check for exposed AWS credentials or IAM misconfigurations
- Perform network/infrastructure security tests
- Run DAST (dynamic application security testing)
- Check SBOM (Software Bill of Materials) for supply chain risks
- Validate SSL/TLS certificate configuration

These are aspirational checks for future work.

## Troubleshooting

**Command not found (pip-audit, bandit, trufflehog):**
`uvx` runs pip-audit and bandit without installing them. Install trufflehog v3 with Homebrew:
```bash
uvx pip-audit --version
uvx bandit --version
brew install trufflehog
```

**Secrets found in history:**
If they are old and already rotated:
```bash
git log --all --full-history -- <file> | head -20
# Evaluate if rotation is needed
```

If they are recent and active, rotate immediately and consider removing from history.

**Too many ESLint warnings:**
Check if they are security-related:
```bash
pnpm lint --max-warnings=100 | grep -i 'security\|xss\|inject'
```

If warnings are non-security style issues, address separately from this scan.

**Dependency versions conflict with recommendations:**
If a HIGH/CRITICAL vuln has no fix yet:
- Document the risk
- Track an issue to upgrade when available
- Flag for manual human review before release
