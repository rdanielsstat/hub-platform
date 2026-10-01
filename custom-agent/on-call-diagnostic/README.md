# On-Call Diagnostic Agent

An autonomous agent that responds to production alerts in real time, diagnoses root causes, and recommends remediation actions.

## Overview

When Grafana Cloud detects a production anomaly (high error rate, elevated latency, etc.), a webhook triggers GitHub Actions, which runs the on-call diagnostic agent. The agent queries production logs, analyzes error patterns, and outputs a diagnosis with recommendations, all without human intervention.

**Goal**: Reduce mean time to recovery (MTTR) by providing automated initial diagnosis while the on-call engineer is reading the alert.

## Architecture

```
Grafana Cloud alert
        ↓
GitHub Actions webhook
        ↓
observability-alert-handler.yml (workflow_dispatch)
        ↓
backend/oncall/diagnose.py
        ↓
Query CloudWatch logs (boto3)
        ↓
Claude GPT-4o-mini diagnosis
        ↓
Output to GitHub Actions logs
```

## Implementation

**Location**: `backend/oncall/diagnose.py`

**Language**: Python 3.12

**Dependencies**: Uses only stdlib (urllib); no new packages required.

**Model**: OpenAI GPT-4o-mini (fast, low-cost, sufficient for log analysis and pattern recognition)

**Cost**: ~$0.000060-0.000198 per run (estimated $5/month for frequent alerts)

## Trigger Mechanism

### Manual dispatch (current)

File: `.github/workflows/observability-alert-handler.yml`

```yaml
name: observability-alert-handler
on: workflow_dispatch
  inputs:
    alert_rule_name:
      description: 'Name of the alert rule that fired'
      required: true
    service_name:
      description: 'Service name (e.g., "hub-platform-api")'
      required: true
    metric:
      description: 'Metric name (e.g., "error_rate")'
      required: true
    threshold:
      description: 'Alert threshold'
      required: true
    current_value:
      description: 'Current metric value'
      required: true
```

When an alert fires in Grafana, you manually trigger the workflow with the alert details.

### Webhook dispatch (future)

Can be automated: Grafana webhook → GitHub Actions webhook → workflow triggers automatically. Not currently set up.

## Workflow

### 1. Receive alert details

Inputs from workflow dispatch:
- Alert rule name (e.g., "Registration Error Rate > 10%")
- Service name (e.g., "hub-platform-api")
- Metric (e.g., "error_rate")
- Threshold (e.g., "10%")
- Current value (e.g., "25%")

### 2. Query production logs

Agent uses boto3 to read CloudWatch logs from the dev/prod Lambda:

```python
import boto3

logs = boto3.client('logs', region_name='us-east-1')
response = logs.get_log_events(
    logGroupName='/aws/lambda/hub-platform-api-dev',
    logStreamName='latest',
    limit=100
)
```

Retrieves the last 100 log lines (configurable).

### 3. Analyze with Claude

Sends logs + alert context to Claude GPT-4o-mini for analysis:

```
Alert: Registration Error Rate > 10% (currently 25%)
Service: hub-platform-api
Time: 2026-10-01 10:15 UTC

Recent logs:
[logs excerpt]

Analyze these logs and diagnose:
1. Root cause of the high error rate
2. Is this a code issue, infra issue, or external dependency?
3. Recommended immediate action
4. Long-term fix (if applicable)

Output: structured diagnosis
```

Claude evaluates patterns like:
- Exception types and frequency
- Stack traces
- Correlation with deployments or infra changes
- Database connection errors, timeout patterns
- External API failures
- Rate limiting or quota issues

### 4. Generate diagnosis

Output format:

```
On-Call Diagnosis Report
========================

Alert: Registration Error Rate > 10%
Severity: HIGH (currently 25% vs. 10% threshold)
Time: 2026-10-01 10:15 UTC
Service: hub-platform-api-dev

Root Cause Assessment:
- Primary: [analysis of logs]
- Contributing factors: [list]
- Likelihood of this being the issue: [high/medium/low]

Evidence:
- [log excerpts or metrics supporting diagnosis]

Recommended Actions (in priority order):
1. Immediate (do this now):
   - [action]: [why this fixes it]
   - Expected recovery: [time frame]

2. Short-term (do in the next hours):
   - [action]: [why]

3. Long-term (track as tech debt):
   - [preventive measure]: [why]

If wrong diagnosis:
- Secondary hypothesis: [alternative diagnosis]
- How to verify: [steps to check]

Next steps:
- Monitor [metric] for recovery
- Check [log stream] for new errors
- If no recovery in [time], escalate to [team/person]
```

### 5. Post output

Results are logged to GitHub Actions logs and (optionally) posted to a GitHub issue or Slack.

## Configuration

### Required permissions

The GitHub Actions runner needs:
- IAM role with CloudWatch Logs read access
- AWS account ID and region (configured in workflow)
- OpenAI API key (for Claude/GPT-4o-mini)

### Environment variables

```bash
AWS_ROLE_ARN=arn:aws:iam::ACCOUNT:role/github-actions-role
AWS_REGION=us-east-1
OPENAI_API_KEY=<api key>
LOG_GROUP_NAME=/aws/lambda/hub-platform-api-dev
```

Set in GitHub secrets and passed to the workflow.

## How to test

### Manually trigger the workflow

1. Go to GitHub Actions
2. Select "observability-alert-handler"
3. Click "Run workflow"
4. Fill in alert details (use sample values for testing)
5. Monitor the run logs for diagnosis output

### Test with sample logs

Add a test mode to `diagnose.py`:

```python
# test mode: use mock logs instead of querying CloudWatch
if TEST_MODE:
    sample_logs = [
        "ERROR: database connection timeout",
        "ERROR: database connection timeout",
        "ERROR: database connection timeout",
        ...
    ]
    diagnosis = analyze_logs(sample_logs, alert_context)
else:
    logs = query_cloudwatch_logs()
    diagnosis = analyze_logs(logs, alert_context)
```

## Troubleshooting

### Diagnosis doesn't match the actual issue

The agent provides a best-effort diagnosis based on available logs. If logs don't contain the root cause (e.g., external service outage, configuration drift), the diagnosis may be incomplete.

**Improvement**: Feed the agent more context:
- Recent deployments (git log)
- Infrastructure changes (Terraform plans)
- External service status (status pages)
- Known ongoing issues

### OpenAI API rate limit or timeout

If the API is slow or rate-limited, the diagnosis times out.

**Mitigation**: Set a timeout and fallback to simpler analysis (keyword search in logs).

### CloudWatch logs not readable

IAM permissions issue. Verify the GitHub Actions role has `logs:GetLogEvents` permission on the Lambda log group.

### Alert is in a different region or log group

Update `LOG_GROUP_NAME` and `AWS_REGION` for the Lambda being monitored (dev vs. prod).

## Cost estimate

**OpenAI GPT-4o-mini pricing** (as of Oct 2026):
- Input: ~$0.15 / 1M tokens
- Output: ~$0.60 / 1M tokens

**Per run**:
- Logs (100 lines, ~500 tokens): $0.000075
- Diagnosis output (~200 tokens): $0.00012
- **Total per run**: ~$0.00020

**Monthly** (assuming 1 alert per hour during business hours, ~40/month):
- 40 runs × $0.00020 = ~$0.008
- Plus API overhead: ~$5-10/month practical budget

## Future enhancements

- **Automated webhook trigger**: Grafana webhook directly to GitHub Actions (no manual dispatch)
- **Slack notifications**: Post diagnosis to on-call Slack channel
- **Escalation logic**: If diagnosis is low-confidence or issue is CRITICAL, page the on-call engineer immediately
- **Feedback loop**: On-call engineer rates the diagnosis (correct/incorrect); feedback is logged for model improvement
- **Runbook linking**: When diagnosis identifies a known issue type, link to the runbook
- **Automated remediation**: For known-safe fixes (restart service, scale up, etc.), take action automatically (high risk; requires approval first)
- **Custom agent for other triggers**: Deployment rollback alerts, database performance alerts, etc.

## References

- `backend/oncall/diagnose.py`: Implementation code
- `.github/workflows/observability-alert-handler.yml`: Trigger workflow
- `docs/ops/on-call-alerting.md`: Operational guide (how to respond to alerts)
- `backend/observability/README.md`: Grafana Cloud setup and alert configuration
