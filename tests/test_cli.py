"""Тесты CLI: коды возврата, вывод, обработка ошибок."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from cocktail import __version__
from cocktail.cli import main


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_version_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == 0
    assert f"cocktail-bot {__version__}" in capsys.readouterr().out


def test_find_prints_results(
    snapshot_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["--snapshot", str(snapshot_file), "find", "--have", "джин, тоник, лайм"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Gin Tonic" in out
    assert "Найдено" in out


def test_find_respects_max_missing(
    snapshot_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # По умолчанию ничего докупать нельзя: без лайма Gin Tonic не подходит.
    main(["--snapshot", str(snapshot_file), "find", "--have", "джин, тоник"])
    strict = capsys.readouterr().out
    main(
        ["--snapshot", str(snapshot_file), "find", "--have", "джин, тоник", "--max-missing", "1"],
    )
    relaxed = capsys.readouterr().out
    assert "Найдено 0" in strict
    assert "Gin Tonic" in relaxed


def test_find_json(snapshot_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["--snapshot", str(snapshot_file), "find", "--have", "gin", "--max-missing", "2", "--json"],
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert payload[0]["name"] == "Gin Tonic"
    assert "coverage" in payload[0]
    assert payload[0]["missing"] == ["Tonic water", "Lime"]


def test_find_no_results_message(snapshot_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--snapshot", str(snapshot_file), "find", "--have", "unobtainium"])
    assert code == 0
    assert "Найдено 0" in capsys.readouterr().out


def test_find_without_snapshot_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--snapshot", str(tmp_path / "absent.json"), "find", "--have", "gin"])
    assert exc_info.value.code == 1
    assert "Ошибка" in capsys.readouterr().err


def test_report(snapshot_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--snapshot", str(snapshot_file), "report"]) == 0
    out = capsys.readouterr().out
    assert "Коктейлей: 3" in out
    assert "Строк ингредиентов" in out


def test_report_json(snapshot_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--snapshot", str(snapshot_file), "report", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["cocktails"] == 3
    assert payload["measures"] > 0


def test_fetch_refuses_to_overwrite(
    snapshot_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--snapshot", str(snapshot_file), "fetch"]) == 1
    assert "--force" in capsys.readouterr().err


def test_help_does_not_crash(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    assert "find" in capsys.readouterr().out


def test_cli_survives_ascii_console(
    snapshot_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Консоль с cp1252 не должна ронять CLI трейсбеком.

    Такое окружение есть на Windows-раннере GitHub Actions: русский текст
    не кодируется, и раньше команда завершалась UnicodeEncodeError.
    """
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(
        buffer,
        encoding="cp1252",
        errors="strict",
        newline="",
        write_through=True,
    )
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", stream)

    code = main(["--snapshot", str(snapshot_file), "find", "--have", "джин, тоник, лайм"])

    assert code == 0
    output = buffer.getvalue().decode("cp1252")
    # Английские названия коктейлей видны всегда, кириллица заменена.
    assert "Gin Tonic" in output
    assert "?" in output
