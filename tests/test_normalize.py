"""Тесты нормализации и словаря алиасов."""

from __future__ import annotations

from pathlib import Path

import pytest

from cocktail.errors import ConfigError
from cocktail.normalize import AliasBook, load_aliases, normalize_text, tokens


def test_normalize_text_case_and_spaces() -> None:
    assert normalize_text("  Fresh   LIME Juice. ") == "fresh lime juice"


def test_normalize_text_yo() -> None:
    assert normalize_text("Лёд") == "лед"


def test_normalize_text_dashes() -> None:
    # Длинное и среднее тире в исходных названиях приводим к обычному дефису.
    assert normalize_text("Lime\u2014Juice") == "lime-juice"
    assert normalize_text("Lime\u2013Juice") == "lime-juice"


def test_tokens_drop_stopwords() -> None:
    assert tokens("Fresh Lime Juice") == frozenset({"lime", "juice"})
    assert tokens("of the Gin") == frozenset({"gin"})


def test_alias_book_resolves_russian() -> None:
    book = AliasBook(entries={"gin": ("джин",), "lime juice": ("сок лайма",)})
    assert book.canonical("Джин") == "gin"
    assert book.canonical("сок лайма") == "lime juice"
    assert book.canonical("unknown thing") == "unknown thing"


def test_alias_book_canonical_is_idempotent() -> None:
    book = AliasBook(entries={"gin": ("джин",)})
    assert book.canonical(book.canonical("Джин")) == "gin"


def test_alias_book_empty_passthrough() -> None:
    book = AliasBook.empty()
    assert book.canonical("Gin") == "gin"
    assert len(book) == 0
    assert book.lookup("gin") is None


def test_load_aliases_from_project_file() -> None:
    book = load_aliases(Path("data/aliases.yaml"))
    assert len(book) > 30
    assert book.canonical("джин") == "gin"
    assert book.canonical("сок лайма") == "lime juice"
    assert book.canonical("лёд") == "ice"


def test_load_aliases_missing_file_is_empty(tmp_path: Path) -> None:
    assert len(load_aliases(tmp_path / "nope.yaml")) == 0


def test_load_aliases_bad_yaml(tmp_path: Path) -> None:
    path = tmp_path / "aliases.yaml"
    path.write_text("ingredients: [1, 2, 3]\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        AliasBook.load(path)


def test_load_aliases_bad_alias_type(tmp_path: Path) -> None:
    path = tmp_path / "aliases.yaml"
    path.write_text("ingredients:\n  gin: [123]\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        AliasBook.load(path)


def test_alias_book_loads_string_alias(tmp_path: Path) -> None:
    path = tmp_path / "aliases.yaml"
    path.write_text("ingredients:\n  gin: джин\n", encoding="utf-8")
    book = AliasBook.load(path)
    assert book.canonical("джин") == "gin"
