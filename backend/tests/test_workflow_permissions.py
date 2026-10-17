"""Least privilege in GitHub Actions (security/REMEDIATION_LOG.md L2): a
job gets `id-token: write`, which lets it ask GitHub for an OIDC token to
assume the AWS role, only if it actually configures AWS credentials.

Plus the on-call agent's one deploy path, rollback-dev.yml: dev only."""

import re
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
ROLLBACK = WORKFLOWS / "rollback-dev.yml"


def _workflow_uses_aws(path: Path) -> bool:
    workflow = yaml.safe_load(path.read_text())
    return any(
        "aws-actions/configure-aws-credentials" in step.get("uses", "")
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
    )


def _jobs():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = yaml.safe_load(path.read_text())
        for name, job in workflow["jobs"].items():
            # A job's own permissions replace the workflow's entirely.
            permissions = job.get("permissions", workflow.get("permissions", {}))
            uses = job.get("uses", "")
            if uses.startswith("./.github/workflows/"):
                # A call to a reusable workflow: the caller has to grant
                # whatever the called workflow's jobs need.
                uses_aws = _workflow_uses_aws(WORKFLOWS / Path(uses).name)
            else:
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


# ---- rollback-dev.yml: the agent's only deploy, dev only -------------


@pytest.fixture(scope="module")
def rollback() -> dict:
    return yaml.safe_load(ROLLBACK.read_text())


def _code(path: Path) -> str:
    """The workflow without its comments, which may mention prod."""
    return "\n".join(
        line
        for line in path.read_text().splitlines()
        if not line.lstrip().startswith("#")
    )


def test_rollback_runs_in_the_dev_environment_only(rollback: dict) -> None:
    (job,) = rollback["jobs"].values()
    assert job["environment"] == "dev"


def test_rollback_only_ever_selects_the_dev_workspace() -> None:
    code = _code(ROLLBACK)
    selects = re.findall(r"tofu workspace (?:select|new)\s+(\S+)", code)
    assert selects and set(selects) == {"dev"}
    assert "workspace new" not in code


def test_rollback_never_mentions_prod_outside_comments() -> None:
    code = _code(ROLLBACK).lower()
    assert "prod" not in code
    assert "promote" not in code


def test_rollback_is_a_targeted_apply_of_the_two_lambdas() -> None:
    code = _code(ROLLBACK)
    applies = [line for line in code.splitlines() if "tofu apply" in line]
    assert len(applies) == 1
    targets = re.findall(r"-target=(\S+)", code)
    assert sorted(targets) == [
        "aws_lambda_function.backend",
        "aws_lambda_function.bootstrap",
    ]


def test_rollback_does_not_pass_the_fault_flag() -> None:
    assert "fault_inject" not in _code(ROLLBACK).lower()


def test_rollback_triggers(rollback: dict) -> None:
    assert set(rollback[True]) == {"workflow_call", "workflow_dispatch"}


def test_only_the_rollback_and_ci_deploy_use_the_dev_environment() -> None:
    users = set()
    for path in WORKFLOWS.glob("*.yml"):
        workflow = yaml.safe_load(path.read_text())
        for name, job in workflow["jobs"].items():
            if job.get("environment") == "dev":
                users.add(f"{path.name}:{name}")
    assert users == {
        "ci.yml:deploy-dev",
        "rollback-dev.yml:rollback",
        "probe-dev.yml:probe",
    }


def test_rollback_scripts_take_no_interpolated_expressions(rollback: dict) -> None:
    (job,) = rollback["jobs"].values()
    for step in job["steps"]:
        run = step.get("run", "")
        # Only the static workflow env (TOFU and AWS settings) may appear.
        assert "${{ inputs" not in run, step.get("name")
        assert "${{ steps" not in run, step.get("name")
