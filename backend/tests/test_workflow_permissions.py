"""Least privilege in GitHub Actions (security/REMEDIATION_LOG.md L2): a
job gets `id-token: write`, which lets it ask GitHub for an OIDC token to
assume the AWS role, only if it actually configures AWS credentials."""

from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _jobs():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = yaml.safe_load(path.read_text())
        for name, job in workflow["jobs"].items():
            # A job's own permissions replace the workflow's entirely.
            permissions = job.get("permissions", workflow.get("permissions", {}))
            uses_aws = any(
                "aws-actions/configure-aws-credentials" in step.get("uses", "")
                for step in job.get("steps", [])
            )
            yield pytest.param(
                path.name, permissions, uses_aws, id=f"{path.name}:{name}"
            )


@pytest.mark.parametrize("workflow, permissions, uses_aws", list(_jobs()))
def test_id_token_only_where_aws_credentials_are_configured(
    workflow, permissions, uses_aws
):
    has_id_token = (permissions or {}).get("id-token") == "write"
    assert has_id_token == uses_aws


def test_ci_workflow_level_permissions_are_read_only():
    ci = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())
    assert ci["permissions"] == {"contents": "read"}
    assert ci["jobs"]["deploy-dev"]["permissions"] == {
        "contents": "read",
        "id-token": "write",
    }
