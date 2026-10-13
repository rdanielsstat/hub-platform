"""The prod image ships without the Lambda Runtime Interface Emulator
(security/REMEDIATION_LOG.md M3): it only runs outside Lambda, and its Go
binary carried HIGH CVEs (security/IAC_SCANS.md)."""

from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def _stage(name: str) -> str:
    text = DOCKERFILE.read_text()
    start = text.index(f" AS {name}\n")
    end = text.find("\nFROM ", start)
    return text[start : end if end != -1 else len(text)]


def test_prod_stage_removes_the_runtime_interface_emulator():
    assert "rm -f /usr/local/bin/aws-lambda-rie" in _stage("prod")


def test_prod_stage_still_uses_the_lambda_runtime_entrypoint():
    # Removing the emulator relies on the base image's entrypoint running
    # /var/runtime/bootstrap whenever AWS_LAMBDA_RUNTIME_API is set (Lambda).
    stage = _stage("prod")
    assert "FROM public.ecr.aws/lambda/python:3.12 AS prod" in DOCKERFILE.read_text()
    assert "ENTRYPOINT" not in stage
    assert 'CMD ["app.lambda_handler.handler"]' in stage


def test_dev_stage_runs_as_a_non_root_user_with_a_healthcheck():
    # The dev stage is the local Docker Compose backend (bootstrap,
    # init_local, app). Lambda ignores USER and HEALTHCHECK, so the prod
    # stage is left alone (security/REMEDIATION_LOG.md N2).
    stage = _stage("dev")
    assert "\nUSER app\n" in stage
    assert "HEALTHCHECK" in stage and "/health" in stage
