import pytest
from pydantic import ValidationError

from vetorthoplan.config.settings import Settings


def test_local_identity_is_allowed_for_local_environment() -> None:
    settings = Settings(app_env="local", identity_mode="local")

    assert settings.identity_mode == "local"


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_local_identity_is_rejected_outside_safe_environments(environment: str) -> None:
    with pytest.raises(ValidationError, match="não é permitido"):
        Settings(app_env=environment, identity_mode="local")

