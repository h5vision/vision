"""Settings validation without loading real credentials."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.core.config import Settings


def test_empty_optional_environment_values_are_unset() -> None:
    settings = Settings(rag_lab_token="", database_url="")

    assert settings.rag_lab_token is None
    assert settings.database_url is None


def test_database_url_is_secret_in_settings_representation() -> None:
    database_url = "postgresql://db.example/vision"
    settings = Settings(database_url=database_url)

    assert settings.database_url is not None
    assert settings.database_url.get_secret_value() == database_url
    assert database_url not in repr(settings)


def test_api_prefix_and_log_level_are_normalized() -> None:
    settings = Settings(api_prefix="/v1/", log_level="warning")

    assert settings.api_prefix == "/v1"
    assert settings.log_level == "WARNING"


@pytest.mark.parametrize("timeout", [10, 10.1, 60])
def test_index_accept_timeout_must_stay_below_frontend_limit(timeout: float) -> None:
    with pytest.raises(ValidationError):
        Settings(rag_lab_index_accept_timeout_seconds=timeout)


def test_rag_lab_token_is_secret_in_settings_representation() -> None:
    token = "not-a-real-token"
    settings = Settings(rag_lab_token=token)

    assert settings.rag_lab_token is not None
    assert settings.rag_lab_token.get_secret_value() == token
    assert token not in repr(settings)
