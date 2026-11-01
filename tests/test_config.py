"""Тесты конфигурации и .env."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cocktail.config import Config, load_dotenv
from cocktail.errors import ConfigError


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("COCKTAIL_DATA_DIR", "COCKTAIL_SNAPSHOT", "COCKTAIL_ALIASES", "COCKTAIL_API_BASE"):
        monkeypatch.delenv(key, raising=False)
    config = Config.from_env({})
    assert config.snapshot_path == Path("data/raw/cocktails.json")
    assert config.aliases_path == Path("data/aliases.yaml")
    assert config.http_timeout == 20.0
    assert config.api_base_url.startswith("https://")
    assert config.telegram_token is None


def test_telegram_token_from_env() -> None:
    config = Config.from_env({"TELEGRAM_BOT_TOKEN": " 123:abc "})
    assert config.telegram_token == "123:abc"


def test_empty_telegram_token_is_none() -> None:
    assert Config.from_env({"TELEGRAM_BOT_TOKEN": "  "}).telegram_token is None
    assert Config.from_env({}).telegram_token is None


def test_env_override() -> None:
    config = Config.from_env(
        {
            "COCKTAIL_DATA_DIR": "tmp/data",
            "COCKTAIL_ALIASES": "custom.yaml",
            "COCKTAIL_HTTP_TIMEOUT": "5",
        },
    )
    assert config.snapshot_path == Path("tmp/data/cocktails.json")
    assert config.aliases_path == Path("custom.yaml")
    assert config.http_timeout == 5.0


def test_bad_url_rejected() -> None:
    with pytest.raises(ConfigError, match="http"):
        Config.from_env({"COCKTAIL_API_BASE": "ftp://example.test"})


def test_bad_timeout_rejected() -> None:
    with pytest.raises(ConfigError, match="не число"):
        Config.from_env({"COCKTAIL_HTTP_TIMEOUT": "fast"})
    with pytest.raises(ConfigError, match="больше нуля"):
        Config.from_env({"COCKTAIL_HTTP_TIMEOUT": "0"})


def test_load_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COCKTAIL_TEST_VALUE", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# комментарий\nCOCKTAIL_TEST_VALUE=42\n\nBAD_LINE\nQUOTED='text'\n",
        encoding="utf-8",
    )
    load_dotenv(env_file)
    assert os.environ["COCKTAIL_TEST_VALUE"] == "42"
    monkeypatch.delenv("COCKTAIL_TEST_VALUE")


def test_load_dotenv_does_not_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COCKTAIL_TEST_EXISTING", "original")
    env_file = tmp_path / ".env"
    env_file.write_text("COCKTAIL_TEST_EXISTING=overridden\n", encoding="utf-8")
    load_dotenv(env_file)
    assert os.environ["COCKTAIL_TEST_EXISTING"] == "original"


def test_load_dotenv_missing_file(tmp_path: Path) -> None:
    load_dotenv(tmp_path / "absent.env")
