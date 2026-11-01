"""Модели предметной области.

Модели неизменяемые (frozen + slots): снапшот каталога читается один раз,
а поиск работает по tuple'ам. Это убирает целый класс багов «кто-то
поправил объект между запросами».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class IngredientMeasure:
    """Одна строка рецепта: ингредиент, количество, единица.

    ``raw`` - исходная строка из API, сохраняется всегда. Она нужна, чтобы
    ошибку разбора можно было увидеть и починить, не ходя в сеть.
    """

    ingredient: str
    raw: str
    amount: float | None = None
    unit: str | None = None
    free_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ingredient": self.ingredient,
            "raw": self.raw,
            "amount": self.amount,
            "unit": self.unit,
            "free_text": self.free_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IngredientMeasure:
        amount = data.get("amount")
        return cls(
            ingredient=str(data["ingredient"]),
            raw=str(data.get("raw", data["ingredient"])),
            amount=float(amount) if isinstance(amount, int | float) else None,
            unit=str(data["unit"]) if data.get("unit") is not None else None,
            free_text=str(data["free_text"]) if data.get("free_text") is not None else None,
        )


@dataclass(frozen=True, slots=True)
class Cocktail:
    """Коктейль с разобранным списком ингредиентов."""

    id: str
    name: str
    measures: tuple[IngredientMeasure, ...]
    category: str | None = None
    alcoholic: str | None = None
    glass: str | None = None
    instructions: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    image: str | None = None

    @property
    def ingredients(self) -> tuple[str, ...]:
        """Названия ингредиентов без количеств и единиц."""
        return tuple(m.ingredient for m in self.measures)

    @property
    def ingredient_count(self) -> int:
        return len(self.measures)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "alcoholic": self.alcoholic,
            "glass": self.glass,
            "instructions": self.instructions,
            "tags": list(self.tags),
            "image": self.image,
            "measures": [m.to_dict() for m in self.measures],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Cocktail:
        raw_tags = data.get("tags") or []
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            measures=tuple(IngredientMeasure.from_dict(m) for m in data.get("measures", [])),
            category=_opt_str(data.get("category")),
            alcoholic=_opt_str(data.get("alcoholic")),
            glass=_opt_str(data.get("glass")),
            instructions=_opt_str(data.get("instructions")),
            tags=tuple(str(t) for t in raw_tags),
            image=_opt_str(data.get("image")),
        )


def _opt_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
