"""Тесты слоя подписей: количества, бокалы, категории, метки."""

from __future__ import annotations

import pytest

from cocktail.format import (
    alcoholic_label,
    category_label,
    format_amount,
    glass_label,
    iba_label,
    number,
    plural,
)


@pytest.mark.parametrize(
    ("amount", "unit", "expected"),
    [
        (2, "oz", "59,1 мл"),
        (1.5, "oz", "44,4 мл"),
        (2, "cl", "20 мл"),
        (50, "ml", "50 мл"),
        (0.5, "oz", "14,8 мл"),
        (1, "tsp", "5 мл"),
        (2, "tbsp", "30 мл"),
        (1, "dash", "1 дэш"),
        (2, "dash", "2 дэша"),
        (5, "dash", "5 дэшей"),
        (1, "wedge", "1 долька"),
        (2, "wedge", "2 дольки"),
        (3, "wedge", "3 дольки"),
        (7, "wedge", "7 долек"),
        (2, "cube", "2 кубика"),
        (1, "sprig", "1 веточка"),
        (12, "drop", "12 капель"),
        (2, None, "2 шт"),
        (1, None, "1 шт"),
        (None, "oz", None),
        (0, "oz", None),
    ],
)
def test_format_amount(amount: float | None, unit: str | None, expected: str | None) -> None:
    assert format_amount(amount, unit) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1, "дэш"),
        (2, "дэша"),
        (4, "дэша"),
        (5, "дэшей"),
        (11, "дэшей"),
        (21, "дэш"),
        (1.4, "дэш"),
    ],
)
def test_plural(value: float, expected: str) -> None:
    assert plural(value, "дэш", "дэша", "дэшей") == expected


def test_number_uses_comma() -> None:
    assert number(1.5) == "1,5"
    assert number(2.0) == "2"
    assert number(0.25) == "0,2" or number(0.25) == "0,3"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Highball glass", "хайбол"),
        ("Highball Glass", "хайбол"),
        ("Old-fashioned glass", "олд-фэшн"),
        ("Shot glass", "шот"),
        ("Неизвестный бокал", "Неизвестный бокал"),
        (None, None),
    ],
)
def test_glass_label(raw: str | None, expected: str | None) -> None:
    assert glass_label(raw) == expected


def test_category_label() -> None:
    assert category_label("Cocktail") == "коктейль"
    assert category_label("Punch / Party Drink") == "пунш"
    assert category_label("Coffee / Tea") == "кофе или чай"
    assert category_label(None) is None


def test_iba_label() -> None:
    assert iba_label("Unforgettables") == "классика IBA"
    assert iba_label("Contemporary Classics") == "современная классика IBA"
    assert iba_label(None) is None


def test_alcoholic_label() -> None:
    assert alcoholic_label("Non alcoholic") == "безалкогольный"
    assert alcoholic_label("Optional alcohol") == "алкоголь по желанию"
    assert alcoholic_label("Alcoholic") is None
    assert alcoholic_label(None) is None
