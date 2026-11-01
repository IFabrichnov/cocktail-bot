"""Состояние бота: загруженный каталог, поиск и память запросов.

Каталог читается один раз при старте, а не на каждое сообщение: 441 напиток
разбирается за доли секунды, но делать это на каждый запрос бессмысленно.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from cocktail.config import Config
from cocktail.models import Cocktail
from cocktail.normalize import AliasBook, load_aliases
from cocktail.search import IngredientMatcher
from cocktail.store import load_snapshot
from cocktail.translate import Translator, load_translations

from .service import QueryCache


@dataclass(frozen=True, slots=True)
class BotApp:
    """Всё, что нужно обработчикам, кроме самого Telegram."""

    cocktails: Sequence[Cocktail]
    matcher: IngredientMatcher
    cache: QueryCache = field(default_factory=QueryCache)
    translator: Translator = field(default_factory=Translator.empty)
    snapshot_path: Path | None = None

    @classmethod
    def load(cls, config: Config) -> BotApp:
        """Прочитать снапшот, словарь алиасов и переводы с диска."""
        snapshot = load_snapshot(config.snapshot_path)
        book: AliasBook = load_aliases(config.aliases_path)
        return cls(
            cocktails=snapshot.cocktails(),
            matcher=IngredientMatcher(book),
            cache=QueryCache(),
            translator=load_translations(config.translations_path),
            snapshot_path=config.snapshot_path,
        )

    @property
    def size(self) -> int:
        return len(self.cocktails)
