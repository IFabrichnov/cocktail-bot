"""Логика бота, не зависящая от Telegram.

Здесь всё, что можно проверить тестами без сети и без токена: разбор
пользовательского ввода, подбор коктейлей, форматирование сообщения и
содержимое кнопок. ``handlers.py`` остаётся тонким слоем транспорта, поэтому
замена aiogram на HTTP или на что-то ещё затронет только его.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass

from cocktail.models import Cocktail
from cocktail.search import IngredientMatcher, MatchResult, find

#: Сколько коктейлей показываем в одном ответе.
MAX_ITEMS = 5
#: Варианты кнопки «сколько готов докупить».
MAX_MISSING_CHOICES = (0, 1, 2, 3)
#: Если точных совпадений нет, пробуем этот порог автоматически.
FALLBACK_MAX_MISSING = 2
#: Telegram ограничивает сообщение 4096 символами, оставляем запас.
TEXT_LIMIT = 3800
#: Предел запоминаемых запросов для кнопок.
CACHE_LIMIT = 500
#: Сколько названий в строке «докупить», прежде чем свернуть в «и ещё N».
MISSING_INLINE = 4

START_TEXT = (
    "Привет. Пришли ингредиенты, которые есть под рукой, и я подберу коктейли.\n\n"
    "Например:\n"
    "джин, лайм, тоник\n"
    "ром, мята, сок лайма, сахарный сироп\n\n"
    "Пиши через запятую, по-русски или по-английски, регистр не важен.\n\n"
    "/help - как это работает\n"
    "/about - откуда данные"
)

HELP_TEXT = (
    "Как это работает.\n\n"
    "1. Ты присылаешь список ингредиентов через запятую.\n"
    "2. Я ищу коктейли, которые из них получаются.\n"
    "3. Если чего-то не хватает, показываю чего именно.\n\n"
    "По умолчанию показываю только то, что можно сделать прямо сейчас. "
    "Кнопки под ответом разрешают докупить один, два или три ингредиента.\n\n"
    "Названия сопоставляются по словарю синонимов: «сок лайма», «lime juice» "
    "и «Lime Juice» - это один ингредиент, а «лайм» и «сок лайма» - разные.\n\n"
    "Количества не учитываются: если у тебя есть джин, а в рецепте нужно "
    "две унции, коктейль подойдёт."
)

ABOUT_TEXT = (
    "Данные: TheCocktailDB (thecocktaildb.com). Каталог скачан один раз и "
    "лежит рядом с ботом, поэтому ответы приходят мгновенно и не зависят "
    "от доступности API.\n\n"
    "Ядро детерминированное: подбор - это пересечение множеств, без моделей "
    "и без генерации текста. Одинаковый запрос всегда даёт одинаковый ответ."
)

EMPTY_TEXT = "Не вижу ингредиентов. Пришли список через запятую, например:\nджин, лайм, тоник"

NOTHING_TEXT = (
    "Ничего не нашлось. Попробуй другие ингредиенты или разреши докупить пару позиций кнопкой ниже."
)

TRUNCATED_SUFFIX = "\n\nСписок длинный, показал первые варианты."


@dataclass(frozen=True, slots=True)
class Button:
    """Кнопка под сообщением."""

    text: str
    data: str


@dataclass(frozen=True, slots=True)
class Reply:
    """Готовый ответ: текст и ряды кнопок."""

    text: str
    rows: tuple[tuple[Button, ...], ...] = ()

    @property
    def has_buttons(self) -> bool:
        return bool(self.rows)


class QueryCache:
    """Короткая память запросов для кнопок.

    Telegram ограничивает callback_data 64 байтами, а русские ингредиенты
    в UTF-8 занимают по два байта на букву. Поэтому в кнопку кладём короткий
    ключ, а сам список храним в памяти процесса.
    """

    def __init__(self, limit: int = CACHE_LIMIT) -> None:
        self._limit = limit
        self._items: OrderedDict[str, str] = OrderedDict()

    def put(self, text: str) -> str:
        key = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
        self._items[key] = text
        self._items.move_to_end(key)
        while len(self._items) > self._limit:
            self._items.popitem(last=False)
        return key

    def get(self, key: str) -> str | None:
        value = self._items.get(key)
        if value is not None:
            self._items.move_to_end(key)
        return value

    def __len__(self) -> int:
        return len(self._items)


def parse_have(text: str) -> list[str]:
    """Разобрать сообщение пользователя в список ингредиентов."""
    cleaned = text.replace(";", ",").replace("\n", ",")
    items = [part.strip(" \t.-") for part in cleaned.split(",")]
    result: list[str] = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result


def parse_callback(data: str) -> tuple[int, str] | None:
    """Разобрать callback_data вида ``m2:abcd123456``."""
    prefix, separator, rest = data.partition(":")
    if not separator or not prefix.startswith("m"):
        return None
    key = rest.strip()
    if not key:
        return None
    try:
        max_missing = int(prefix[1:])
    except ValueError:
        return None
    if max_missing < 0:
        return None
    return max_missing, key


def build_reply(
    text: str,
    cocktails: Sequence[Cocktail],
    matcher: IngredientMatcher,
    cache: QueryCache,
    *,
    max_missing: int = 0,
) -> Reply:
    """Собрать ответ на пользовательский текст."""
    have = parse_have(text)
    if not have:
        return Reply(text=EMPTY_TEXT)

    results = find(
        cocktails,
        have,
        matcher=matcher,
        max_missing=max_missing,
        limit=MAX_ITEMS,
    )
    note = ""
    if not results and max_missing < FALLBACK_MAX_MISSING:
        max_missing = FALLBACK_MAX_MISSING
        results = find(
            cocktails,
            have,
            matcher=matcher,
            max_missing=max_missing,
            limit=MAX_ITEMS,
        )
        if results:
            note = "Точных совпадений нет. Вот что почти готово:\n\n"

    if not results:
        return Reply(text=NOTHING_TEXT, rows=_missing_rows(text, cache, max_missing))

    header = f"Что можно сделать: {', '.join(have)}\n\n"
    body = "\n\n".join(_format_result(index, result) for index, result in enumerate(results, 1))
    footer = (
        "\n\nЕсли чего-то не хватает, разреши докупить кнопкой ниже."
        if any(result.missing for result in results)
        else ""
    )
    message = f"{header}{note}{body}{footer}"
    return Reply(
        text=_clamp(message),
        rows=_missing_rows(text, cache, max_missing),
    )


def _format_result(index: int, result: MatchResult) -> str:
    total = len(result.matched) + len(result.missing)
    head = f"{index}. {result.cocktail.name} - {len(result.matched)}/{total}"
    if not result.missing:
        return f"{head}\n   всё есть"
    missing = ", ".join(result.missing[:MISSING_INLINE])
    if len(result.missing) > MISSING_INLINE:
        missing += f" и ещё {len(result.missing) - MISSING_INLINE}"
    return f"{head}\n   докупить: {missing}"


def _missing_rows(
    text: str,
    cache: QueryCache,
    current: int,
) -> tuple[tuple[Button, ...], ...]:
    """Кнопки-переключатели порога «сколько докупить»."""
    choices = [choice for choice in MAX_MISSING_CHOICES if choice != current]
    if not choices:
        return ()
    key = cache.put(text)
    buttons = tuple(
        Button(text=f"докупить {choice}", data=f"m{choice}:{key}") for choice in choices
    )
    return (buttons,)


def _clamp(message: str) -> str:
    if len(message) <= TEXT_LIMIT:
        return message
    return message[: TEXT_LIMIT - len(TRUNCATED_SUFFIX)].rstrip() + TRUNCATED_SUFFIX
