"""Тесты бота в CLI: запуск без токена, наличие команды в справке."""

from __future__ import annotations

import pytest

from cocktail.cli import main


def test_bot_command_in_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    assert "bot" in capsys.readouterr().out


def test_bot_without_token_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main(["bot"])
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "токен" in err.lower()
    assert "BotFather" in err


def test_bot_does_not_start_with_empty_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "   ")
    with pytest.raises(SystemExit) as exc_info:
        main(["bot"])
    assert exc_info.value.code == 1
    assert "токен" in capsys.readouterr().err.lower()
