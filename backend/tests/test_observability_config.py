"""The OTEL_ENABLED toggle: app/core/config.py reads it (off unless set
to a true value), app/main.py passes it to initialize_observability(),
and disabled means no instrumentation and no export at all, even with
an OTLP endpoint configured.

The app-level tests import app.main in a fresh subprocess, like
test_startup.py: config reads OTEL_ENABLED once, at import.
"""

import os
import subprocess
import sys
from pathlib import Path

import yaml
from fastapi import FastAPI

from observability import initialize_observability

BACKEND_DIR = Path(__file__).resolve().parent.parent
CI_PATH = BACKEND_DIR.parent / ".github" / "workflows" / "ci.yml"
PROMOTE_PATH = BACKEND_DIR.parent / ".github" / "workflows" / "promote.yml"

_OTEL_VARS = {
    "OTEL_ENABLED",
    "OTEL_SDK_DISABLED",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_HEADERS",
    "ENVIRONMENT",
    "USE_SSM",
    "HUB_JWT_SECRET",
    "SEED_DEMO_DATA",
}


def _import_app_main(**env: str) -> str:
    clean = {k: v for k, v in os.environ.items() if k not in _OTEL_VARS}
    clean["DATABASE_URL"] = "sqlite:///:memory:"
    clean.update(env)
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=BACKEND_DIR,
        env=clean,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_otel_enabled_unset_disables_observability() -> None:
    # An endpoint alone (as in a developer's .env) must not turn it on.
    out = _import_app_main(OTEL_EXPORTER_OTLP_ENDPOINT="https://otlp.invalid/otlp")
    assert "observability: disabled" in out
    assert "exporting" not in out


def test_otel_enabled_true_enables_observability() -> None:
    out = _import_app_main(OTEL_ENABLED="true")
    assert "observability: exporting traces, metrics and logs to local collector" in out
    assert "observability: disabled" not in out


def test_disabled_initialization_does_nothing(capsys, monkeypatch) -> None:
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://otlp.invalid/otlp")
    app = FastAPI()

    assert initialize_observability(app, enabled=False) is None

    assert capsys.readouterr().out.strip() == "observability: disabled"
    assert app.user_middleware == []
    assert not getattr(app, "_is_instrumented_by_opentelemetry", False)


def test_dev_and_prod_get_otel_secrets() -> None:
    ci = yaml.safe_load(CI_PATH.read_text())
    env = ci["jobs"]["deploy-dev"]["env"]
    assert (
        env["TF_VAR_otel_endpoint_dev"]
        == "${{ secrets.OTEL_EXPORTER_OTLP_ENDPOINT_DEV }}"
    )
    assert (
        env["TF_VAR_otel_headers_dev"]
        == "${{ secrets.OTEL_EXPORTER_OTLP_HEADERS_DEV }}"
    )

    promote = yaml.safe_load(PROMOTE_PATH.read_text())
    env = promote["jobs"]["promote"]["env"]
    assert (
        env["TF_VAR_otel_endpoint_prod"]
        == "${{ secrets.TF_VAR_OTEL_EXPORTER_OTLP_ENDPOINT_PROD }}"
    )
    assert (
        env["TF_VAR_otel_headers_prod"]
        == "${{ secrets.TF_VAR_OTEL_EXPORTER_OTLP_HEADERS_PROD }}"
    )


def test_deploy_dev_passes_semver_service_version() -> None:
    ci = yaml.safe_load(CI_PATH.read_text())
    steps = ci["jobs"]["deploy-dev"]["steps"]

    (checkout,) = [s for s in steps if s.get("uses", "").startswith("actions/checkout")]
    # git describe needs the history and tags; the default is depth 1.
    assert checkout["with"]["fetch-depth"] == 0

    (compute,) = [s for s in steps if s.get("id") == "tag"]
    assert ".github/scripts/service-version.sh" in compute["run"]
    assert "version=" in compute["run"]

    (apply,) = [s for s in steps if s.get("name") == "Apply"]
    assert '-var="service_version=${{ steps.tag.outputs.version }}"' in apply["run"]
    # Image tags stay unique per build.
    assert '-var="lambda_image_tag=${{ steps.tag.outputs.tag }}"' in apply["run"]


def test_promote_passes_semver_service_version_for_prod() -> None:
    promote = yaml.safe_load(PROMOTE_PATH.read_text())
    steps = promote["jobs"]["promote"]["steps"]

    (checkout,) = [s for s in steps if s.get("uses", "").startswith("actions/checkout")]
    # git describe needs the history and tags; the default is depth 1.
    assert checkout["with"]["fetch-depth"] == 0

    (derive,) = [s for s in steps if s.get("name") == "Derive SERVICE_VERSION"]
    assert derive["id"] == "version"
    # The version is for the commit the promoted image was built from: the
    # sha at the end of its timestamp-sha tag, not main's HEAD.
    assert 'SHA="${{ steps.tag.outputs.tag }}"' in derive["run"]
    assert 'SHA="${SHA##*-}"' in derive["run"]
    assert 'git switch --detach "$SHA"' in derive["run"]
    assert ".github/scripts/service-version.sh" in derive["run"]
    assert "version=" in derive["run"]

    # Derived before prod is applied.
    names = [s.get("name") for s in steps]
    assert names.index("Derive SERVICE_VERSION") < names.index("Apply prod")

    (apply,) = [s for s in steps if s.get("name") == "Apply prod"]
    assert '-var="service_version=${{ steps.version.outputs.version }}"' in apply["run"]
    assert '-var="lambda_image_tag=${{ steps.tag.outputs.tag }}"' in apply["run"]
