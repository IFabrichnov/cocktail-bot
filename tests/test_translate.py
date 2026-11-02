"""Тесты словаря переводов и карточек с русским текстом."""

from __future__ import annotations

from pathlib import Path

import pytest

from cocktail.bot.service import QueryCache, build_reply
from cocktail.errors import ConfigError
from cocktail.models import Cocktail
from cocktail.normalize import AliasBook
from cocktail.search import IngredientMatcher
from cocktail.translate import Translator, coverage, load_translations


@pytest.fixture
def translator() -> Translator:
    return Translator(
        ingredients={
            "gin": "джин",
            "tonic water": "тоник",
            "lime": "лайм",
            "lime juice": "сок лайма",
        },
        cocktails={"Gin Tonic": "Джин-тоник"},
        instructions={"Gin Tonic": "Смешать джин с тоником."},
    )


def test_ingredient_lookup_is_case_insensitive(translator: Translator) -> None:
    assert translator.ingredient("GIN") == "джин"
    assert translator.ingredient("  Tonic Water ") == "тоник"


def test_unknown_ingredient_stays_as_is(translator: Translator) -> None:
    assert translator.ingredient("Unobtainium") == "Unobtainium"


def test_cocktail_lookup(translator: Translator) -> None:
    assert translator.cocktail("Gin Tonic") == "Джин-тоник"
    assert translator.cocktail("Negroni") is None


def test_empty_translator_returns_original() -> None:
    book = Translator.empty()
    assert book.ingredient("Gin") == "Gin"
    assert book.cocktail("Gin Tonic") is None
    assert len(book) == 0


def test_load_translations_from_file(tmp_path: Path) -> None:
    path = tmp_path / "translations.yaml"
    path.write_text(
        "version: 1\ningredients:\n  gin: джин\ncocktails:\n  Margarita: Маргарита\n",
        encoding="utf-8",
    )
    book = Translator.load(path)
    assert book.ingredient("gin") == "джин"
    assert book.cocktail("margarita") == "Маргарита"


def test_missing_translations_file_is_empty(tmp_path: Path) -> None:
    assert len(load_translations(tmp_path / "absent.yaml")) == 0


def test_project_translations_cover_all_ingredients() -> None:
    book = load_translations(Path("data/translations.yaml"))
    assert book.ingredient("gin") == "джин"
    assert book.ingredient("ice") == "лёд"
    assert book.cocktail("Margarita") == "Маргарита"
    assert len(book) > 400


def test_bad_translation_value_raises(tmp_path: Path) -> None:
    path = tmp_path / "translations.yaml"
    path.write_text("ingredients:\n  gin: 42\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="строкой"):
        Translator.load(path)


def test_coverage_counts(cocktails: tuple[Cocktail, ...], translator: Translator) -> None:
    stats = coverage(cocktails, translator)
    assert stats.cocktails == 3
    assert stats.cocktails_translated == 1
    assert stats.ingredient_rows == 10
    # Перевод есть: gin, tonic water, lime, lime juice, salt? - salt нет,
    # поэтому строки с солью считаются непереведёнными.
    assert 0 < stats.ingredient_rows_translated < stats.ingredient_rows
    assert 0 < stats.ingredient_rows_ratio < 1


def test_coverage_to_dict(cocktails: tuple[Cocktail, ...], translator: Translator) -> None:
    payload = coverage(cocktails, translator).to_dict()
    assert payload["cocktails"] == 3
    assert "ingredient_rows_ratio" in payload


def test_card_shows_russian_name_and_composition(
    cocktails: tuple[Cocktail, ...],
    translator: Translator,
) -> None:
    matcher = IngredientMatcher(
        AliasBook(entries={"gin": ("джин",), "tonic water": ("тоник",), "lime": ("лайм",)}),
    )
    reply = build_reply(
        "джин, тоник, лайм",
        cocktails,
        matcher,
        QueryCache(),
        translator=translator,
    )
    assert "<b>Gin Tonic (Джин-тоник)</b>" in reply.text
    assert "<b>Состав:</b> джин (Gin) 59,1 мл" in reply.text
    assert "долька" in reply.text
    assert "Всё есть" in reply.text


def test_untranslated_ingredient_has_no_parentheses(
    cocktails: tuple[Cocktail, ...],
    translator: Translator,
) -> None:
    matcher = IngredientMatcher(AliasBook(entries={"gin": ("джин",)}))
    reply = build_reply(
        "джин, тоник, лайм",
        cocktails,
        matcher,
        QueryCache(),
        translator=translator,
        bucket=2,
        offset=1,
    )
    # Negroni: Campari и Sweet Vermouth перевода не имеют, скобок быть не должно.
    assert "Campari" in reply.text
    assert "Campari (" not in reply.text


def test_card_without_translation_has_no_brackets(
    cocktails: tuple[Cocktail, ...],
    translator: Translator,
) -> None:
    matcher = IngredientMatcher(AliasBook(entries={"gin": ("джин",)}))
    reply = build_reply(
        "джин, тоник, лайм",
        cocktails,
        matcher,
        QueryCache(),
        translator=translator,
        bucket=2,
        offset=1,
    )
    # Вторая карточка страницы - Negroni, перевода у него нет,
    # поэтому скобок быть не должно.
    assert "<b>Negroni</b>" in reply.text
    assert "Negroni (" not in reply.text


def test_recipe_is_always_shown(
    cocktails: tuple[Cocktail, ...],
    translator: Translator,
) -> None:
    matcher = IngredientMatcher(AliasBook(entries={"gin": ("джин",)}))
    cards = build_reply(
        "джин, тоник, лайм",
        cocktails,
        matcher,
        QueryCache(),
        translator=translator,
        bucket=0,
    )
    assert "<b>Готовить:</b> Смешать джин с тоником." in cards.text
    labels = [button.text for row in cards.rows for button in row]
    assert "Как готовить" not in labels
    assert "Скрыть рецепт" not in labels


def test_recipe_button_absent_without_translation(
    cocktails: tuple[Cocktail, ...],
) -> None:
    matcher = IngredientMatcher(AliasBook(entries={"gin": ("джин",)}))
    reply = build_reply(
        "джин, тоник, лайм",
        cocktails,
        matcher,
        QueryCache(),
        translator=Translator(ingredients={"gin": "джин"}),
        bucket=2,
        offset=1,
    )
    labels = [button.text for row in reply.rows for button in row]
    assert "Как готовить" not in labels


def test_missing_line_is_translated(
    cocktails: tuple[Cocktail, ...],
    translator: Translator,
) -> None:
    matcher = IngredientMatcher(AliasBook(entries={"gin": ("джин",), "tonic water": ("тоник",)}))
    reply = build_reply(
        "джин, тоник",
        cocktails,
        matcher,
        QueryCache(),
        translator=translator,
        bucket=1,
    )
    assert "<b>Докупить:</b> лайм" in reply.text
