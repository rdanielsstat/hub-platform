import pytest

from app.core.config import DEV_JWT_SECRET, require_safe_jwt_secret

REAL_LOOKING_SECRET = "a-unique-generated-secret-that-is-not-the-dev-default"


def test_local_with_dev_secret_does_not_raise():
    require_safe_jwt_secret(
        environment="local", secret=DEV_JWT_SECRET, dev_default=DEV_JWT_SECRET
    )


def test_local_with_missing_secret_does_not_raise():
    require_safe_jwt_secret(
        environment="local", secret="", dev_default=DEV_JWT_SECRET
    )


def test_development_alias_is_also_treated_as_local():
    require_safe_jwt_secret(
        environment="development", secret=DEV_JWT_SECRET, dev_default=DEV_JWT_SECRET
    )


def test_local_check_is_case_insensitive():
    require_safe_jwt_secret(
        environment="Local", secret=DEV_JWT_SECRET, dev_default=DEV_JWT_SECRET
    )


def test_production_with_dev_secret_raises():
    with pytest.raises(RuntimeError):
        require_safe_jwt_secret(
            environment="production",
            secret=DEV_JWT_SECRET,
            dev_default=DEV_JWT_SECRET,
        )


def test_production_with_missing_secret_raises():
    with pytest.raises(RuntimeError):
        require_safe_jwt_secret(
            environment="production", secret="", dev_default=DEV_JWT_SECRET
        )


def test_any_non_local_environment_with_dev_secret_raises():
    with pytest.raises(RuntimeError):
        require_safe_jwt_secret(
            environment="staging", secret=DEV_JWT_SECRET, dev_default=DEV_JWT_SECRET
        )


def test_production_with_a_real_secret_does_not_raise():
    require_safe_jwt_secret(
        environment="production",
        secret=REAL_LOOKING_SECRET,
        dev_default=DEV_JWT_SECRET,
    )
