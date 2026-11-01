"""Нормализация названий ингредиентов.

Проблема, которую решает модуль: «сок лайма», «Fresh Lime Juice» и
«lime juice» - это один ингредиент, а «Lime» и «Lime Juice» - разные
(в коктейле нужен либо фрукт, либо сок).

Стратегия двух слоёв:

1. **Словарь алиасов** (``data/aliases.yaml``) - ручной, точный, версионируется.
   Это основной рабочий инструмент: 40-60 записей закрывают почти всё.
2. **Токенизация** - запасной вариант для незнакомых названий: убираем
   служебные слова («fresh», «of», «chopped») и сравниваем множества слов.
   Так «Fresh Lime Juice» находит «Lime Juice» без записи в словаре.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from cocktail.errors import ConfigError

#: Слова, которые не меняют смысл ингредиента.
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "chilled",
        "chopped",
        "cold",
        "crushed",
        "fresh",
        "freshly",
        "hot",
        "of",
        "or",
        "the",
        "to",
    },
)

_TOKEN_RE = re.compile(r"[0-9a-zа-яё]+")
_DASHES = str.maketrans({"\u2013": "-", "\u2014": "-", "ё": "е"})


def normalize_text(text: str) -> str:
    """Привести название к сравнимому виду: регистр, ё, пробелы, пунктуация."""
    result = text.casefold().translate(_DASHES)
    result = re.sub(r"\s+", " ", result).strip()
    return result.strip(" .,;:!?")


def tokens(text: str) -> frozenset[str]:
    """Множество значимых слов названия."""
    return frozenset(
        token for token in _TOKEN_RE.findall(normalize_text(text)) if token not in STOPWORDS
    )


@dataclass(frozen=True, slots=True)
class AliasBook:
    """Словарь: каноническое название -> список синонимов.

    Канонические названия берутся из каталога (TheCocktailDB, английский),
    алиасы - на любом языке, включая русский: пользователь пишет «джин»,
    каталог хранит «Gin».
    """

    entries: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    version: int = 1
    _index: Mapping[str, str] = field(init=False, repr=False, compare=False, default_factory=dict)

    def __post_init__(self) -> None:
        index: dict[str, str] = {}
        for canonical, aliases in self.entries.items():
            for alias in (canonical, *aliases):
                key = normalize_text(alias)
                if key and key not in index:
                    index[key] = canonical
        object.__setattr__(self, "_index", index)

    def canonical(self, name: str) -> str:
        """Каноническое название, если известно; иначе нормализованное исходное."""
        key = normalize_text(name)
        return self._index.get(key, key)

    def lookup(self, name: str) -> str | None:
        return self._index.get(normalize_text(name))

    def __len__(self) -> int:
        return len(self.entries)

    @classmethod
    def empty(cls) -> AliasBook:
        return cls()

    @classmethod
    def load(cls, path: Path) -> AliasBook:
        """Прочитать ``aliases.yaml``.

        Формат::

            version: 1
            ingredients:
              gin: [джин, джина]
              lime juice: [сок лайма, fresh lime juice]
        """
        if not path.is_file():
            raise ConfigError(f"Словарь алиасов не найден: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ConfigError(f"{path}: ожидался YAML-словарь")
        raw_version = raw.get("version", 1)
        ingredients = raw.get("ingredients") or {}
        if not isinstance(ingredients, dict):
            raise ConfigError(f"{path}: секция 'ingredients' должна быть словарём")

        entries: dict[str, tuple[str, ...]] = {}
        for canonical, aliases in ingredients.items():
            if not isinstance(canonical, str):
                raise ConfigError(f"{path}: ключ {canonical!r} должен быть строкой")
            if aliases is None:
                entries[canonical] = ()
                continue
            if isinstance(aliases, str):
                aliases = [aliases]
            if not isinstance(aliases, Sequence):
                raise ConfigError(f"{path}: алиасы для {canonical!r} должны быть списком")
            entries[canonical] = tuple(_as_str(item) for item in aliases)

        return cls(entries=entries, version=int(raw_version))


def _as_str(value: object) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"Алиас должен быть строкой, получено: {value!r}")
    return value


def load_aliases(path: Path) -> AliasBook:
    """Загрузить словарь, а при его отсутствии - пустой (словарь не обязателен)."""
    if not path.is_file():
        return AliasBook.empty()
    return AliasBook.load(path)
