"""Тесты разбора рецептов - самое хрупкое место проекта."""

from __future__ import annotations

from typing import Any

import pytest

from cocktail.parse import cocktail_from_raw, parse_measure


@pytest.mark.parametrize(
    ("text", "amount", "unit", "name"),
    [
        ("2 oz", 2.0, "oz", ""),
        ("1 1/2 oz Fresh Lime Juice", 1.5, "oz", "Fresh Lime Juice"),
        ("1/2 oz", 0.5, "oz", ""),
        ("2 cl Gin", 2.0, "cl", "Gin"),
        ("50 ml", 50.0, "ml", ""),
        ("¾ oz", 0.75, "oz", ""),
        ("1½ oz", 1.5, "oz", ""),
        ("Dash Angostura Bitters", None, "dash", "Angostura Bitters"),
        ("3 dashes", 3.0, "dash", ""),
        ("Juice of 1 Lime", 1.0, None, "Lime"),
        ("Juice of 1/2 Lemon", 0.5, None, "Lemon"),
        ("juice of 2 limes", 2.0, None, "limes"),
        ("Fresh Lime Juice", None, None, "Fresh Lime Juice"),
        ("", None, None, ""),
    ],
)
def test_parse_measure(text: str, amount: float | None, unit: str | None, name: str) -> None:
    parsed = parse_measure(text)
    if amount is None:
        assert parsed.amount is None
    else:
        assert parsed.amount == pytest.approx(amount)
    assert parsed.unit == unit
    assert parsed.name == name


def test_amount_word_does_not_become_number() -> None:
    parsed = parse_measure("One part gin")
    assert parsed.amount is None
    assert parsed.name == "One part gin"


def test_free_text_is_extracted() -> None:
    parsed = parse_measure("Salt to taste")
    assert parsed.name == "Salt"
    assert parsed.free_text == "to taste"
    assert parsed.amount is None


def test_garnish_phrase() -> None:
    parsed = parse_measure("Lime for garnish")
    assert parsed.name == "Lime"
    assert parsed.free_text == "for garnish"


def test_unit_requires_word_boundary() -> None:
    # "Liver" не должен распознаться как единица "l".
    parsed = parse_measure("1 oz Liver")
    assert parsed.unit == "oz"
    assert parsed.name == "Liver"


def test_comma_decimal() -> None:
    parsed = parse_measure("1,5 oz Gin")
    assert parsed.amount == pytest.approx(1.5)
    assert parsed.name == "Gin"


def test_cocktail_from_raw_keeps_raw_lines(raw_drinks: list[dict[str, Any]]) -> None:
    cocktail = cocktail_from_raw(raw_drinks[0])
    assert cocktail.id == "101"
    assert cocktail.name == "Gin Tonic"
    assert cocktail.ingredients == ("Gin", "Tonic water", "Lime")
    assert cocktail.measures[0].raw == "2 oz Gin"
    assert cocktail.tags == ("IBA", "Classic")
    assert cocktail.glass == "Highball glass"


def test_cocktail_from_raw_handles_empty_measure(raw_drinks: list[dict[str, Any]]) -> None:
    cocktail = cocktail_from_raw(raw_drinks[1])
    salt = cocktail.measures[-1]
    assert salt.ingredient == "Salt"
    assert salt.raw == "Salt"
    assert salt.amount is None


def test_cocktail_from_raw_roundtrip(raw_drinks: list[dict[str, Any]]) -> None:
    cocktail = cocktail_from_raw(raw_drinks[2])
    restored = type(cocktail).from_dict(cocktail.to_dict())
    assert restored == cocktail
