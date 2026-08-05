"""Unit tests for configuration parsing.

`cors_origin_list` splits a string that comes from an environment variable, so
it meets whatever whitespace and stray commas a hand-edited .env file contains.
Getting this wrong fails at runtime as a browser CORS error, which is slow to
diagnose, so the edge cases are pinned here.
"""

import pytest

from app.config import Settings


def test_single_origin() -> None:
    settings = Settings(cors_origins="http://localhost:3000")
    assert settings.cors_origin_list == ["http://localhost:3000"]


def test_multiple_origins() -> None:
    settings = Settings(cors_origins="http://localhost:3000,https://bilingers.app")
    assert settings.cors_origin_list == [
        "http://localhost:3000",
        "https://bilingers.app",
    ]


@pytest.mark.parametrize(
    "raw",
    [
        " http://a.test , http://b.test ",
        "http://a.test,,http://b.test",
        ",http://a.test,http://b.test,",
        "http://a.test,   ,http://b.test",
    ],
)
def test_whitespace_and_empty_entries_are_dropped(raw: str) -> None:
    assert Settings(cors_origins=raw).cors_origin_list == [
        "http://a.test",
        "http://b.test",
    ]


def test_empty_string_yields_no_origins() -> None:
    assert Settings(cors_origins="").cors_origin_list == []


def test_defaults_are_usable_without_any_environment() -> None:
    settings = Settings()
    assert settings.app_name
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.cors_origin_list
