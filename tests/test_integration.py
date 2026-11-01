"""Проверка на реальном снапшоте каталога.

Тесты этого модуля не ходят в сеть, но читают `data/raw/cocktails.json`,
который коммитится. Если снапшота нет (например, его скачали заново в другой
файл), тесты пропускаются, а не падают.

Смысл: синтетические фикстуры проверяют логику, а здесь проверяется, что
весь конвейер даёт ожидаемый ответ на настоящих данных. Такой тест ловит
регрессии в разборе и алиасах, которые синтетика не заметит.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cocktail.models import Cocktail
from cocktail.normalize import load_aliases
from cocktail.search import IngredientMatcher, find
from cocktail.store import load_snapshot

SNAPSHOT = Path("data/raw/cocktails.json")
ALIASES = Path("data/aliases.yaml")

pytestmark = pytest.mark.skipif(
    not SNAPSHOT.is_file(),
    reason="нет снапшота каталога: выполни cocktail fetch",
)


@pytest.fixture(scope="module")
def cocktails() -> tuple[Cocktail, ...]:
    return load_snapshot(SNAPSHOT).cocktails()


@pytest.fixture(scope="module")
def matcher() -> IngredientMatcher:
    return IngredientMatcher(load_aliases(ALIASES))


def test_gimlet_is_found_and_complete(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    results = find(
        cocktails,
        ["джин", "сок лайма", "лайм", "сахарный сироп"],
        matcher=matcher,
        limit=3,
    )
    assert results, "для полного набора ингредиентов ничего не нашлось"
    assert results[0].cocktail.name == "Gimlet"
    assert results[0].is_complete


def test_russian_input_finds_cocktail(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    results = find(
        cocktails,
        ["ром", "лайм", "мята"],
        matcher=matcher,
        max_missing=2,
        limit=5,
    )
    assert any("Mint" in result.cocktail.name for result in results)


def test_catalog_size_is_stable(cocktails: tuple[Cocktail, ...]) -> None:
    # Снапшот заморожен, поэтому число коктейлей не должно «плыть».
    # Если каталог перекачали сознательно, обнови ожидание вместе с данными.
    assert len(cocktails) == 441
