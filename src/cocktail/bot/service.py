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
#: Три страницы подбора: готово сейчас, докупить один, докупить два.
BUCKETS = (0, 1, 2)
#: Подписи кнопок-переключателей.
BUCKET_LABELS = {0: "только своё", 1: "докупить 1", 2: "докупить 2"}
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
    "3. Показываю три страницы: что готово прямо сейчас, что можно собрать, "
    "докупив один ингредиент, и что можно собрать, докупив два.\n\n"
    "Кнопки под ответом переключают страницы. «Только своё» - строгое "
    "условие, без покупок.\n\n"
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
    "Ничего не нашлось даже с двумя докупками. Попробуй другие ингредиенты "
    "или пришли более короткий список."
)

TRUNCATED_SUFFIX = "\n\nСписок длинный, показал первые варианты."

NOTE_NO_READY = "Готовых коктейлей нет. Показываю ближайшее:"
NOTE_ONE_MISSING_EMPTY = "И с одним недостающим пусто. Дальше только с двумя:"


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
    """Разобрать callback_data вида ``m1:abcd123456``."""
    prefix, separator, rest = data.partition(":")
    if not separator or not prefix.startswith("m"):
        return None
    key = rest.strip()
    if not key:
        return None
    try:
        bucket = int(prefix[1:])
    except ValueError:
        return None
    if bucket < 0:
        return None
    return bucket, key


def build_reply(
    text: str,
    cocktails: Sequence[Cocktail],
    matcher: IngredientMatcher,
    cache: QueryCache,
    *,
    bucket: int = 0,
) -> Reply:
    """Собрать ответ на пользовательский текст.

    :param bucket: страница подбора - 0 (готово сейчас), 1 или 2 (сколько
        ингредиентов разрешено докупить). Если для страницы ничего нет, бот
        сам переходит к следующей и говорит об этом: молчаливое «ничего не
        найдено» раздражает сильнее, чем честное «покажу ближайшее».
    """
    have = parse_have(text)
    if not have:
        return Reply(text=EMPTY_TEXT)

    requested = _clamp_bucket(bucket)
    pages = _split_by_bucket(cocktails, have, matcher)
    current = requested

    while not pages[current]:
        following = [candidate for candidate in BUCKETS if candidate > current]
        if not following:
            break
        current = following[0]

    page = pages[current]
    if not page:
        return Reply(text=NOTHING_TEXT)

    note = ""
    if current != requested:
        note = NOTE_NO_READY if requested == 0 else NOTE_ONE_MISSING_EMPTY
        note += "\n\n"

    blocks = "\n\n".join(
        _format_result(index, result) for index, result in enumerate(page[:MAX_ITEMS], 1)
    )
    message = (
        f"Что можно сделать: {', '.join(have)}\n\n"
        f"{note}{_header(current, len(page))}\n\n"
        f"{blocks}\n\nКнопки ниже переключают страницы."
    )
    return Reply(text=_clamp(message), rows=_bucket_rows(text, cache, current, pages))


def _split_by_bucket(
    cocktails: Sequence[Cocktail],
    have: Sequence[str],
    matcher: IngredientMatcher,
) -> dict[int, list[MatchResult]]:
    """Разложить результаты по страницам: 0, 1 или 2 недостающих."""
    results = find(
        cocktails,
        have,
        matcher=matcher,
        max_missing=max(BUCKETS),
        limit=None,
    )
    pages: dict[int, list[MatchResult]] = {bucket: [] for bucket in BUCKETS}
    for result in results:
        missing = len(result.missing)
        if missing in pages:
            pages[missing].append(result)
    return pages


def _format_result(index: int, result: MatchResult) -> str:
    total = len(result.matched) + len(result.missing)
    head = f"{index}. {result.cocktail.name} - {len(result.matched)}/{total}"
    if not result.missing:
        return f"{head}\n   всё есть"
    missing = ", ".join(result.missing[:MISSING_INLINE])
    if len(result.missing) > MISSING_INLINE:
        missing += f" и ещё {len(result.missing) - MISSING_INLINE}"
    return f"{head}\n   докупить: {missing}"


def _header(bucket: int, total: int) -> str:
    if bucket == 0:
        return f"Готово к приготовлению: {total}"
    noun = "ингредиент" if bucket == 1 else "ингредиента"
    return f"Докупить {bucket} {noun}: {total}"


def _bucket_rows(
    text: str,
    cache: QueryCache,
    current: int,
    pages: dict[int, list[MatchResult]],
) -> tuple[tuple[Button, ...], ...]:
    """Кнопки-переключатели страниц.

    Пустые страницы не показываем: кнопка, ведущая на пустоту, выглядит
    сломанной, а после автоперехода она ещё и возвращает туда же, откуда
    пользователь только что пришёл.
    """
    others = [bucket for bucket in BUCKETS if bucket != current and pages[bucket]]
    if not others:
        return ()
    key = cache.put(text)
    buttons = tuple(
        Button(text=BUCKET_LABELS[bucket], data=f"m{bucket}:{key}") for bucket in others
    )
    return (buttons,)


def _clamp_bucket(bucket: int) -> int:
    if bucket in BUCKETS:
        return bucket
    return min(max(bucket, min(BUCKETS)), max(BUCKETS))


def _clamp(message: str) -> str:
    if len(message) <= TEXT_LIMIT:
        return message
    return message[: TEXT_LIMIT - len(TRUNCATED_SUFFIX)].rstrip() + TRUNCATED_SUFFIX
