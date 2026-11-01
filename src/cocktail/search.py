"""Поиск коктейлей по имеющимся ингредиентам.

Ядро детерминированное: множества, пересечения, сортировка. Никаких моделей
и никакой недетерминированности - одинаковый ввод всегда даёт одинаковый
вывод, а значит результат можно проверять тестами и сравнивать в регрессии.

Ранжирование: сначала те, где меньше всего не хватает, затем те, где больше
совпало, затем выше доля покрытия, затем по алфавиту (для стабильности).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from cocktail.models import Cocktail
from cocktail.normalize import AliasBook, normalize_text, tokens

#: Минимальная длина слова, при которой допускается частичное совпадение
#: («lime» -> «Lime Juice»). Короткие слова требуют точного равенства.
MIN_PARTIAL_TOKEN_LEN = 3


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Один результат поиска."""

    cocktail: Cocktail
    matched: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def coverage(self) -> float:
        total = len(self.matched) + len(self.missing)
        return len(self.matched) / total if total else 0.0

    @property
    def is_complete(self) -> bool:
        return not self.missing


class IngredientMatcher:
    """Сравнение названий ингредиентов.

    Три уровня, от строгого к мягкому:

    1. совпадение канонических названий (после словаря алиасов);
    2. равенство множеств значимых слов;
    3. вложенность слов при условии, что слова достаточно длинные:
       «lime» находит «Lime Juice», но «gin» не находит «Ginger Ale».
    """

    def __init__(self, book: AliasBook | None = None) -> None:
        self._book = book or AliasBook.empty()
        self._cache: dict[str, frozenset[str]] = {}

    def key(self, name: str) -> str:
        """Канонический ключ названия."""
        return self._book.canonical(name)

    def token_set(self, name: str) -> frozenset[str]:
        cached = self._cache.get(name)
        if cached is None:
            cached = tokens(self.key(name))
            self._cache[name] = cached
        return cached

    def matches(self, left: str, right: str) -> bool:
        left_key = self.key(left)
        right_key = self.key(right)
        if left_key and left_key == right_key:
            return True
        left_tokens = self.token_set(left)
        right_tokens = self.token_set(right)
        if not left_tokens or not right_tokens:
            return False
        if left_tokens == right_tokens:
            return True
        if left_tokens < right_tokens:
            return _is_specific(left_tokens)
        if right_tokens < left_tokens:
            return _is_specific(right_tokens)
        return False


def _is_specific(token_set: frozenset[str]) -> bool:
    """Достаточно ли слово длинным, чтобы частичное совпадение было безопасным."""
    return all(len(token) >= MIN_PARTIAL_TOKEN_LEN for token in token_set)


def find(
    cocktails: Sequence[Cocktail],
    have: Iterable[str],
    *,
    matcher: IngredientMatcher | None = None,
    max_missing: int = 0,
    limit: int | None = None,
) -> list[MatchResult]:
    """Найти коктейли, которые можно приготовить из ``have``.

    :param cocktails: каталог (обычно результат ``Snapshot.cocktails()``)
    :param have: ингредиенты пользователя, на любом языке (см. ``aliases.yaml``)
    :param max_missing: сколько ингредиентов пользователь готов докупить
    :param limit: сколько результатов вернуть (None - все)
    """
    wanted = [item.strip() for item in have if item and item.strip()]
    if not wanted:
        raise ValueError("Список ингредиентов пуст")
    if max_missing < 0:
        raise ValueError("max_missing не может быть отрицательным")
    if limit is not None and limit < 0:
        raise ValueError("limit не может быть отрицательным")

    cmp = matcher or IngredientMatcher()

    results: list[MatchResult] = []
    for cocktail in cocktails:
        matched: list[str] = []
        missing: list[str] = []
        for measure in cocktail.measures:
            if any(cmp.matches(measure.ingredient, item) for item in wanted):
                matched.append(measure.ingredient)
            else:
                missing.append(measure.ingredient)
        if len(missing) > max_missing:
            continue
        if not matched:
            continue
        results.append(
            MatchResult(
                cocktail=cocktail,
                matched=tuple(matched),
                missing=tuple(missing),
            ),
        )

    results.sort(
        key=lambda result: (
            len(result.missing),
            -len(result.matched),
            -result.coverage,
            normalize_text(result.cocktail.name),
        ),
    )
    if limit is not None:
        return results[:limit]
    return results
