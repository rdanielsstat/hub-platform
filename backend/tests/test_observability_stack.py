"""The local observability stack (observability/docker-compose.yml):
valid YAML, the expected services and ports, no hardcoded secrets, and
config files that actually wire the collector to Tempo, Prometheus and
Loki and Grafana to all three.

Static checks only; nothing here needs Docker running.
"""

import re
from pathlib import Path

import pytest
import yaml

STACK_DIR = Path(__file__).resolve().parent.parent / "observability"
COMPOSE_PATH = STACK_DIR / "docker-compose.yml"

# service -> (image repository, host port it must publish)
EXPECTED_SERVICES = {
    "otel-collector": ("otel/opentelemetry-collector-contrib", 4318),
    "prometheus": ("prom/prometheus", 9090),
    "loki": ("grafana/loki", 3100),
    "tempo": ("grafana/tempo", 3200),
    "grafana": ("grafana/grafana", 3000),
}

_SECRET_KEY = re.compile(r"PASSWORD|SECRET|TOKEN|API_KEY", re.IGNORECASE)
# ${VAR} or ${VAR:-default}: the value comes from the environment.
_INTERPOLATED = re.compile(r"^\$\{[A-Z_][A-Z0-9_]*(:?-[^}]*)?\}$")


def _load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict), f"{path.name} is not a YAML mapping"
    return data


@pytest.fixture(scope="module")
def compose() -> dict:
    return _load(COMPOSE_PATH)


def _environment(service: dict) -> dict[str, str]:
    env = service.get("environment", {})
    if isinstance(env, list):
        env = dict(item.split("=", 1) for item in env)
    return {k: str(v) for k, v in env.items()}


def _host_ports(service: dict) -> list[tuple[str, int]]:
    """(host ip, host port) for each short-syntax "ip:host:container"
    mapping."""
    published = []
    for mapping in service.get("ports", []):
        parts = str(mapping).split(":")
        assert len(parts) == 3, f"expected ip:host:container, got {mapping!r}"
        published.append((parts[0], int(parts[1])))
    return published


def test_compose_file_is_valid_yaml(compose: dict) -> None:
    assert isinstance(compose["services"], dict)


def test_all_services_defined(compose: dict) -> None:
    assert set(compose["services"]) == set(EXPECTED_SERVICES)


@pytest.mark.parametrize("name", sorted(EXPECTED_SERVICES))
def test_service_image_is_pinned(compose: dict, name: str) -> None:
    repo, _port = EXPECTED_SERVICES[name]
    image = compose["services"][name]["image"]
    image_repo, _, tag = image.partition(":")
    assert image_repo == repo
    assert tag and tag != "latest", f"{name} image should pin a version"


@pytest.mark.parametrize("name", sorted(EXPECTED_SERVICES))
def test_service_publishes_expected_port_on_localhost(
    compose: dict, name: str
) -> None:
    _repo, port = EXPECTED_SERVICES[name]
    # Local only: nothing is reachable from outside this machine.
    assert _host_ports(compose["services"][name]) == [("127.0.0.1", port)]


def test_host_ports_do_not_conflict(compose: dict) -> None:
    ports = [
        port
        for service in compose["services"].values()
        for _ip, port in _host_ports(service)
    ]
    assert len(ports) == len(set(ports))
    # Nor with the app stack in the repo root (Postgres, the API).
    assert not {5432, 8000} & set(ports)


def test_no_hardcoded_secrets(compose: dict) -> None:
    for name, service in compose["services"].items():
        for key, value in _environment(service).items():
            if _SECRET_KEY.search(key):
                assert _INTERPOLATED.match(value), (
                    f"{name}: {key} must come from the environment, "
                    f"e.g. ${{{key}:-...}}, not a literal"
                )


def test_grafana_admin_login_from_environment(compose: dict) -> None:
    env = _environment(compose["services"]["grafana"])
    assert env["GF_SECURITY_ADMIN_USER"] == "${GRAFANA_ADMIN_USER:-admin}"
    assert env["GF_SECURITY_ADMIN_PASSWORD"] == "${GRAFANA_ADMIN_PASSWORD:-admin}"


def test_mounted_config_files_exist(compose: dict) -> None:
    for name, service in compose["services"].items():
        for volume in service.get("volumes", []):
            source = str(volume).split(":")[0]
            if source.startswith("./"):
                assert (STACK_DIR / source).is_file(), f"{name}: {source} missing"


# ---- the configs wire everything together ------------------------------


def test_collector_routes_each_signal_to_its_backend() -> None:
    config = _load(STACK_DIR / "collector-config.yaml")
    assert config["receivers"]["otlp"]["protocols"]["http"]["endpoint"] == "0.0.0.0:4318"

    exporters = config["exporters"]
    pipelines = config["service"]["pipelines"]
    assert pipelines["traces"]["receivers"] == ["otlp"]
    assert pipelines["metrics"]["receivers"] == ["otlp"]
    assert pipelines["logs"]["receivers"] == ["otlp"]

    (traces_out,) = pipelines["traces"]["exporters"]
    assert exporters[traces_out]["endpoint"] == "tempo:4317"

    (metrics_out,) = pipelines["metrics"]["exporters"]
    assert metrics_out.split("/")[0] == "prometheus"
    assert exporters[metrics_out]["endpoint"] == "0.0.0.0:8889"

    (logs_out,) = pipelines["logs"]["exporters"]
    assert exporters[logs_out]["endpoint"] == "http://loki:3100/otlp"


def test_prometheus_scrapes_the_collector() -> None:
    config = _load(STACK_DIR / "prometheus.yml")
    targets = [
        target
        for job in config["scrape_configs"]
        for static in job.get("static_configs", [])
        for target in static["targets"]
    ]
    assert "otel-collector:8889" in targets


def test_grafana_datasources_for_all_three_backends() -> None:
    config = _load(STACK_DIR / "grafana-datasources.yaml")
    by_type = {ds["type"]: ds for ds in config["datasources"]}
    assert by_type["prometheus"]["url"] == "http://prometheus:9090"
    assert by_type["loki"]["url"] == "http://loki:3100"
    assert by_type["tempo"]["url"] == "http://tempo:3200"
    assert sum(ds.get("isDefault", False) for ds in config["datasources"]) == 1


def test_tempo_accepts_otlp_grpc_from_the_collector() -> None:
    config = _load(STACK_DIR / "tempo.yaml")
    assert config["server"]["http_listen_port"] == 3200
    grpc = config["distributor"]["receivers"]["otlp"]["protocols"]["grpc"]
    assert grpc["endpoint"] == "0.0.0.0:4317"
