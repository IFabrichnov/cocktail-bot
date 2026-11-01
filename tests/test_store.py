"""Тесты снапшота: загрузка, схема, атомарная запись."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cocktail.errors import SnapshotError
from cocktail.store import build_snapshot, load_snapshot, save_snapshot


def test_load_snapshot(snapshot_file: Path) -> None:
    snapshot = load_snapshot(snapshot_file)
    assert len(snapshot) == 3
    assert snapshot.letters == ("g", "m", "n")
    assert snapshot.source == "https://example.test/api"


def test_load_snapshot_parses_cocktails(snapshot_file: Path) -> None:
    cocktails = load_snapshot(snapshot_file).cocktails()
    assert [c.name for c in cocktails] == ["Gin Tonic", "Margarita", "Negroni"]


def test_missing_snapshot_raises(tmp_path: Path) -> None:
    with pytest.raises(SnapshotError, match="не найден"):
        load_snapshot(tmp_path / "absent.json")


def test_broken_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SnapshotError, match="повреждён"):
        load_snapshot(path)


def test_wrong_schema_raises(tmp_path: Path) -> None:
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"schema": 0, "items": []}), encoding="utf-8")
    with pytest.raises(SnapshotError, match="схема"):
        load_snapshot(path)


def test_items_must_be_list(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema": 1, "items": {}}), encoding="utf-8")
    with pytest.raises(SnapshotError, match="items"):
        load_snapshot(path)


def test_build_and_save_roundtrip(tmp_path: Path, raw_drinks: list[dict[str, Any]]) -> None:
    payload = build_snapshot(raw_drinks, letters=["a"], source="https://example.test")
    destination = tmp_path / "nested" / "dir" / "snap.json"
    save_snapshot(destination, payload)

    assert destination.is_file()
    assert not destination.with_suffix(".json.tmp").exists()
    restored = load_snapshot(destination)
    assert len(restored) == 3
    assert restored.fetched_at.startswith("20")
