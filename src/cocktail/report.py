"""Отчёт о качестве данных.

Смысл отчёта - сделать работу с данными измеримой. Пока нет цифры
«распознано 96% ингредиентов», любое улучшение парсера - вкусовщина.
Именно на этот отчёт опирается этап 2 («разбор и нормализация»).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from cocktail.models import Cocktail


@dataclass(frozen=True, slots=True)
class IngredientReport:
    """Сводка по разбору ингредиентов каталога."""

    cocktails: int
    measures: int
    with_amount: int
    with_unit: int
    with_free_text: int
    unknown_units: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    top_ingredients: tuple[tuple[str, int], ...] = field(default_factory=tuple)

    @property
    def amounts_ratio(self) -> float:
        """Доля строк, где количество распознано."""
        return self.with_amount / self.measures if self.measures else 0.0

    @property
    def units_ratio(self) -> float:
        return self.with_unit / self.measures if self.measures else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "cocktails": self.cocktails,
            "measures": self.measures,
            "with_amount": self.with_amount,
            "with_unit": self.with_unit,
            "with_free_text": self.with_free_text,
            "amounts_ratio": round(self.amounts_ratio, 4),
            "units_ratio": round(self.units_ratio, 4),
            "unknown_units": [{"raw": unit, "count": count} for unit, count in self.unknown_units],
            "top_ingredients": [
                {"name": name, "count": count} for name, count in self.top_ingredients
            ],
        }


def build_report(
    cocktails: Sequence[Cocktail],
    *,
    top: int = 20,
) -> IngredientReport:
    """Посчитать покрытие разбора и частотные словари."""
    measures = 0
    with_amount = 0
    with_unit = 0
    with_free_text = 0
    unknown_units: Counter[str] = Counter()
    ingredients: Counter[str] = Counter()

    for cocktail in cocktails:
        for measure in cocktail.measures:
            measures += 1
            ingredients[measure.ingredient.strip().casefold()] += 1
            if measure.amount is not None:
                with_amount += 1
            if measure.unit is not None:
                with_unit += 1
            if measure.free_text is not None:
                with_free_text += 1
            if measure.amount is None and measure.unit is None and measure.free_text is None:
                # Строка без количества и без распознанной единицы: либо это
                # ингредиент «по вкусу», либо парсер не справился.
                unknown_units[measure.raw.strip().casefold()] += 1

    return IngredientReport(
        cocktails=len(cocktails),
        measures=measures,
        with_amount=with_amount,
        with_unit=with_unit,
        with_free_text=with_free_text,
        unknown_units=tuple(unknown_units.most_common(top)),
        top_ingredients=tuple(ingredients.most_common(top)),
    )
