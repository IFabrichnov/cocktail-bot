"""Перевод названий для отображения.

Словарь отдельный от ``aliases.yaml``, потому что задачи разные:

* ``aliases.yaml`` отвечает на вопрос «что ввёл пользователь» и нужен поиску;
* ``translations.yaml`` отвечает на вопрос «как это показать» и нужен только
  выводу в чат.

Один и тот же ингредиент может иметь несколько синонимов для поиска и ровно
одну подпись для показа. Смешивать это в одном файле значит ломать обе задачи.

Правило: нет перевода - показываем оригинал. Скобки не рисуются, если
перевода нет: выдуманное русское название хуже английского.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from cocktail.errors import ConfigError
from cocktail.models import Cocktail
from cocktail.normalize import normalize_text


@dataclass(frozen=True, slots=True)
class Translator:
    """Словарь подписей: ключ - название из каталога, значение - подпись."""

    ingredients: Mapping[str, str] = field(default_factory=dict)
    cocktails: Mapping[str, str] = field(default_factory=dict)
    instructions: Mapping[str, str] = field(default_factory=dict)
    version: int = 1
    _ingredients: Mapping[str, str] = field(init=False, repr=False, compare=False)
    _cocktails: Mapping[str, str] = field(init=False, repr=False, compare=False)
    _instructions: Mapping[str, str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_ingredients",
            {normalize_text(key): value for key, value in self.ingredients.items()},
        )
        object.__setattr__(
            self,
            "_cocktails",
            {normalize_text(key): value for key, value in self.cocktails.items()},
        )
        object.__setattr__(
            self,
            "_instructions",
            {normalize_text(key): value for key, value in self.instructions.items()},
        )

    def ingredient(self, name: str) -> str:
        """Подпись ингредиента или исходное название."""
        return self._ingredients.get(normalize_text(name), name)

    def cocktail(self, name: str) -> str | None:
        """Подпись коктейля или None, если перевода нет."""
        return self._cocktails.get(normalize_text(name))

    def instruction(self, name: str) -> str | None:
        """Рецепт по-русски или None, если перевода нет."""
        return self._instructions.get(normalize_text(name))

    def has_ingredient(self, name: str) -> bool:
        return normalize_text(name) in self._ingredients

    def has_cocktail(self, name: str) -> bool:
        return normalize_text(name) in self._cocktails

    def has_instruction(self, name: str) -> bool:
        return normalize_text(name) in self._instructions

    def __len__(self) -> int:
        return len(self._ingredients) + len(self._cocktails) + len(self._instructions)

    @classmethod
    def empty(cls) -> Translator:
        return cls()

    @classmethod
    def load(cls, path: Path) -> Translator:
        """Прочитать ``translations.yaml``.

        Формат::

            version: 1
            ingredients:
              gin: джин
            cocktails:
              Margarita: Маргарита
        """
        if not path.is_file():
            raise ConfigError(f"Словарь переводов не найден: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ConfigError(f"{path}: ожидался YAML-словарь")
        version = raw.get("version", 1)
        ingredients = _section(raw.get("ingredients"), path, "ingredients")
        cocktails = _section(raw.get("cocktails"), path, "cocktails")
        instructions = _section(raw.get("instructions", {}), path, "instructions")
        return cls(
            ingredients=ingredients,
            cocktails=cocktails,
            instructions=instructions,
            version=int(version),
        )


@dataclass(frozen=True, slots=True)
class TranslationCoverage:
    """Сколько строк и названий реально переведено."""

    ingredient_rows: int
    ingredient_rows_translated: int
    unique_ingredients: int
    unique_ingredients_translated: int
    cocktails: int
    cocktails_translated: int
    instructions: int
    instructions_translated: int

    @property
    def ingredient_rows_ratio(self) -> float:
        return (
            self.ingredient_rows_translated / self.ingredient_rows if self.ingredient_rows else 0.0
        )

    @property
    def unique_ingredients_ratio(self) -> float:
        if not self.unique_ingredients:
            return 0.0
        return self.unique_ingredients_translated / self.unique_ingredients

    @property
    def cocktails_ratio(self) -> float:
        return self.cocktails_translated / self.cocktails if self.cocktails else 0.0

    @property
    def instructions_ratio(self) -> float:
        return self.instructions_translated / self.instructions if self.instructions else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "ingredient_rows": self.ingredient_rows,
            "ingredient_rows_translated": self.ingredient_rows_translated,
            "ingredient_rows_ratio": round(self.ingredient_rows_ratio, 4),
            "unique_ingredients": self.unique_ingredients,
            "unique_ingredients_translated": self.unique_ingredients_translated,
            "unique_ingredients_ratio": round(self.unique_ingredients_ratio, 4),
            "cocktails": self.cocktails,
            "cocktails_translated": self.cocktails_translated,
            "cocktails_ratio": round(self.cocktails_ratio, 4),
            "instructions": self.instructions,
            "instructions_translated": self.instructions_translated,
            "instructions_ratio": round(self.instructions_ratio, 4),
        }


def coverage(cocktails: Sequence[Cocktail], translator: Translator) -> TranslationCoverage:
    """Посчитать покрытие перевода по каталогу."""
    rows = 0
    rows_translated = 0
    unique: set[str] = set()
    unique_translated: set[str] = set()

    for cocktail in cocktails:
        for measure in cocktail.measures:
            rows += 1
            key = normalize_text(measure.ingredient)
            unique.add(key)
            if translator.has_ingredient(measure.ingredient):
                rows_translated += 1
                unique_translated.add(key)

    names = 0
    names_translated = 0
    recipes = 0
    recipes_translated = 0
    for cocktail in cocktails:
        names += 1
        if translator.has_cocktail(cocktail.name):
            names_translated += 1
        recipes += 1
        if translator.has_instruction(cocktail.name):
            recipes_translated += 1

    return TranslationCoverage(
        ingredient_rows=rows,
        ingredient_rows_translated=rows_translated,
        unique_ingredients=len(unique),
        unique_ingredients_translated=len(unique_translated),
        cocktails=names,
        cocktails_translated=names_translated,
        instructions=recipes,
        instructions_translated=recipes_translated,
    )


def load_translations(path: Path) -> Translator:
    """Загрузить словарь, а при его отсутствии - пустой (переводы необязательны)."""
    if not path.is_file():
        return Translator.empty()
    return Translator.load(path)


def _section(raw: object, path: Path, name: str) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: секция '{name}' должна быть словарём")

    result: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ConfigError(f"{path}: {name}[{key!r}] должен быть строкой")
        text = value.strip()
        if not text:
            raise ConfigError(f"{path}: пустой перевод для {key!r}")
        result[key] = text
    return result
