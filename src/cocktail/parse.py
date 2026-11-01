"""Разбор рецептов: строки вида «1 1/2 oz Fresh Lime Juice» в структуру.

Два уровня:

* :func:`parse_measure` - разбирает одну строку API на количество, единицу
  и название ингредиента;
* :func:`cocktail_from_raw` - собирает :class:`~cocktail.models.Cocktail`
  из «сырого» объекта TheCocktailDB.

Принцип: ничего не теряем. Если строку не удалось разобрать, ``amount``
и ``unit`` будут ``None``, но ``raw`` и название ингредиента сохранятся -
такие случаи попадают в отчёт и чинятся словарём алиасов, а не кодом.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cocktail.models import Cocktail, IngredientMeasure

MAX_SLOTS = 15

_UNICODE_FRACTIONS = {
    "½": "1/2",
    "⅓": "1/3",
    "⅔": "2/3",
    "¼": "1/4",
    "¾": "3/4",
    "⅛": "1/8",
    "⅜": "3/8",
    "⅝": "5/8",
    "⅞": "7/8",
}

#: Варианты написания единиц -> каноническая единица. Ключи в нижнем регистре.
UNIT_VARIANTS: dict[str, str] = {
    "oz": "oz",
    "oz.": "oz",
    "ounce": "oz",
    "ounces": "oz",
    "fl oz": "oz",
    "cl": "cl",
    "ml": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "l": "l",
    "liter": "l",
    "litre": "l",
    "dash": "dash",
    "dashes": "dash",
    "tsp": "tsp",
    "tsp.": "tsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "t": "tsp",
    "tbsp": "tbsp",
    "tbsp.": "tbsp",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "tb": "tbsp",
    "cup": "cup",
    "cups": "cup",
    "pint": "pint",
    "pints": "pint",
    "quart": "quart",
    "gallon": "gallon",
    "shot": "shot",
    "shots": "shot",
    "jigger": "jigger",
    "splash": "splash",
    "spl": "splash",
    "barspoon": "barspoon",
    "part": "part",
    "parts": "part",
    "drop": "drop",
    "drops": "drop",
    "pinch": "pinch",
    "pinches": "pinch",
    "twist": "twist",
    "twists": "twist",
    "slice": "slice",
    "slices": "slice",
    "wedge": "wedge",
    "wedges": "wedge",
    "sprig": "sprig",
    "sprigs": "sprig",
    "leaf": "leaf",
    "leaves": "leaf",
    "can": "can",
    "cans": "can",
    "bottle": "bottle",
    "bottles": "bottle",
    "cube": "cube",
    "cubes": "cube",
    "scoop": "scoop",
    "scoops": "scoop",
    "glass": "glass",
    "glasses": "glass",
    "whole": "whole",
    "gr": "g",
    "g": "g",
    "gram": "g",
    "grams": "g",
}

_AMOUNT_RE = re.compile(
    r"^(?P<amount>\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)\s*(?P<rest>.*)$",
)
_FRACTION_RE = re.compile(r"(?:(?P<whole>\d+)\s+)?(?P<num>\d+)/(?P<den>\d+)")
#: «Juice of 1/2 Lemon» - количество относится к фрукту, а не к миллилитрам.
_JUICE_OF_RE = re.compile(
    r"^juice\s+of\s+(?P<amount>\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_FREE_TEXT_RE = re.compile(
    r"\b(?P<text>to taste|for garnish|for serving|as needed|to fill)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ParsedMeasure:
    """Результат разбора одной строки рецепта."""

    name: str
    amount: float | None = None
    unit: str | None = None
    free_text: str | None = None


def parse_measure(text: str) -> ParsedMeasure:
    """Разобрать строку количества и названия ингредиента.

    Примеры::

        "1 1/2 oz Fresh Lime Juice" -> 1.5, "oz", "Fresh Lime Juice"
        "Dash Angostura Bitters"    -> None, "dash", "Angostura Bitters"
        "Salt to taste"             -> None, None, "Salt", free_text="to taste"
        "Juice of 1/2 Lemon"        -> 0.5, None, "Lemon"
    """
    cleaned = _prepare(text)
    if not cleaned:
        return ParsedMeasure(name="")

    amount, rest = _split_amount(cleaned)
    if amount is None:
        juice = _JUICE_OF_RE.match(cleaned)
        if juice is not None:
            amount = _parse_amount(juice.group("amount"))
            rest = juice.group("rest").strip()
    rest = _strip_leading_of(rest)

    unit, rest = _split_unit(rest)
    rest = _strip_leading_of(rest).strip()

    free_text: str | None = None
    match = _FREE_TEXT_RE.search(rest)
    if match is not None:
        free_text = match.group("text").lower()
        rest = _FREE_TEXT_RE.sub("", rest, count=1)
        rest = re.sub(r"\s{2,}", " ", rest).strip(" ,;")

    return ParsedMeasure(name=rest, amount=amount, unit=unit, free_text=free_text)


def cocktail_from_raw(raw: Mapping[str, Any]) -> Cocktail:
    """Собрать коктейль из «сырого» объекта TheCocktailDB."""
    measures: list[IngredientMeasure] = []
    for slot in range(1, MAX_SLOTS + 1):
        ingredient = _field(raw, f"strIngredient{slot}")
        if not ingredient:
            continue
        measure = _field(raw, f"strMeasure{slot}")
        if measure:
            parsed = parse_measure(measure)
            measures.append(
                IngredientMeasure(
                    ingredient=ingredient,
                    raw=f"{measure} {ingredient}".strip(),
                    amount=parsed.amount,
                    unit=parsed.unit,
                    free_text=parsed.free_text,
                ),
            )
        else:
            # В API количество часто пустое ("Ice", "Salt") - это нормально.
            measures.append(IngredientMeasure(ingredient=ingredient, raw=ingredient))

    tags = tuple(tag.strip() for tag in _field(raw, "strTags").split(",") if tag.strip())
    return Cocktail(
        id=_field(raw, "idDrink"),
        name=_field(raw, "strDrink"),
        measures=tuple(measures),
        category=_field(raw, "strCategory"),
        alcoholic=_field(raw, "strAlcoholic"),
        glass=_field(raw, "strGlass"),
        instructions=_field(raw, "strInstructions"),
        tags=tags,
        image=_field(raw, "strDrinkThumb") or None,
    )


def _prepare(text: str) -> str:
    result = text.strip()
    for fraction, replacement in _UNICODE_FRACTIONS.items():
        result = result.replace(fraction, f" {replacement}" if result else replacement)
    result = re.sub(r"\s+", " ", result)
    result = re.sub(r"\s*([.,;])\s*$", "", result)
    return result.strip()


def _split_amount(text: str) -> tuple[float | None, str]:
    match = _AMOUNT_RE.match(text)
    if match is None:
        return None, text
    return _parse_amount(match.group("amount")), match.group("rest").strip()


def _parse_amount(token: str) -> float | None:
    text = token.replace(",", ".").strip()
    match = _FRACTION_RE.fullmatch(text)
    if match is not None:
        whole = float(match.group("whole") or 0)
        denominator = float(match.group("den"))
        if denominator == 0:
            return None
        return whole + float(match.group("num")) / denominator
    try:
        return float(text)
    except ValueError:
        return None


def _strip_leading_of(text: str) -> str:
    return re.sub(r"^(?:of|of the)\s+", "", text.strip(), flags=re.IGNORECASE).strip()


def _split_unit(text: str) -> tuple[str | None, str]:
    """Отделить единицу измерения от названия ингредиента."""
    words = text.split(" ")
    for size in (2, 1):
        if len(words) < size:
            continue
        candidate = " ".join(words[:size]).lower()
        canonical = UNIT_VARIANTS.get(candidate)
        if canonical is not None:
            return canonical, " ".join(words[size:]).strip()
    return None, text


def _field(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if value is None:
        return ""
    return str(value).strip()
