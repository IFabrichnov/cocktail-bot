"""Тесты поиска: детерминированность, ранжирование, алиасы."""

from __future__ import annotations

import pytest

from cocktail.models import Cocktail, IngredientMeasure
from cocktail.normalize import AliasBook
from cocktail.search import IngredientMatcher, find


@pytest.fixture
def book() -> AliasBook:
    return AliasBook(
        entries={
            "gin": ("джин",),
            "lime juice": ("сок лайма",),
            "lime": ("лайм",),
            "tonic water": ("тоник",),
            "sweet vermouth": ("сладкий вермут",),
            "campari": ("кампари",),
            "salt": ("соль",),
        },
    )


def test_all_ingredients_present(cocktails: tuple[Cocktail, ...]) -> None:
    results = find(cocktails, ["Gin", "Tonic water", "Lime"])
    names = [result.cocktail.name for result in results]
    assert "Gin Tonic" in names
    tonic = next(result for result in results if result.cocktail.name == "Gin Tonic")
    assert tonic.is_complete
    assert tonic.coverage == pytest.approx(1.0)


def test_russian_input(cocktails: tuple[Cocktail, ...], book: AliasBook) -> None:
    matcher = IngredientMatcher(book)
    results = find(cocktails, ["джин", "тоник", "лайм"], matcher=matcher)
    assert any(result.cocktail.name == "Gin Tonic" for result in results)


def test_missing_filters_results(cocktails: tuple[Cocktail, ...]) -> None:
    only_gin = find(cocktails, ["Gin"], max_missing=5)
    names = {result.cocktail.name for result in only_gin}
    assert names == {"Gin Tonic", "Negroni"}
    assert all(result.missing for result in only_gin)


def test_max_missing_lets_buy(cocktails: tuple[Cocktail, ...]) -> None:
    results = find(cocktails, ["Gin", "Tonic water"], max_missing=1)
    assert any(result.cocktail.name == "Gin Tonic" for result in results)


def test_partial_word_match(cocktails: tuple[Cocktail, ...]) -> None:
    # "lime" находит "Lime juice" через вложенность слов.
    results = find(cocktails, ["Lime"], max_missing=5)
    lime_juice = next(result for result in results if result.cocktail.name == "Margarita")
    assert "Lime juice" in lime_juice.matched


def test_short_tokens_do_not_partially_match() -> None:
    matcher = IngredientMatcher()
    assert not matcher.matches("ab", "ab cd")
    assert matcher.matches("lime", "lime juice")


def test_ranking_prefers_complete() -> None:
    easy = Cocktail(id="1", name="Easy Gin", measures=(_m("Gin"),))
    harder = Cocktail(id="2", name="Hard Gin", measures=(_m("Gin"), _m("Campari")))
    results = find([harder, easy], ["Gin"], max_missing=5)
    assert [result.cocktail.name for result in results] == ["Easy Gin", "Hard Gin"]
    assert results[0].coverage == pytest.approx(1.0)
    assert results[1].coverage == pytest.approx(0.5)


def test_limit(cocktails: tuple[Cocktail, ...]) -> None:
    results = find(cocktails, ["Gin"], max_missing=10, limit=1)
    assert len(results) == 1


def test_empty_have_raises(cocktails: tuple[Cocktail, ...]) -> None:
    with pytest.raises(ValueError, match="пуст"):
        find(cocktails, [])


def test_negative_max_missing_raises(cocktails: tuple[Cocktail, ...]) -> None:
    with pytest.raises(ValueError, match="отрицательным"):
        find(cocktails, ["Gin"], max_missing=-1)


def test_no_results_when_nothing_matches(cocktails: tuple[Cocktail, ...]) -> None:
    assert find(cocktails, ["Unobtainium"]) == []


def test_result_is_deterministic(cocktails: tuple[Cocktail, ...]) -> None:
    first = find(cocktails, ["Gin"], max_missing=5)
    second = find(cocktails, ["Gin"], max_missing=5)
    assert [r.cocktail.id for r in first] == [r.cocktail.id for r in second]


def _m(name: str) -> IngredientMeasure:
    return IngredientMeasure(ingredient=name, raw=name)
