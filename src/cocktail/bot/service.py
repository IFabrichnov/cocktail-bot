"""Логика бота, не зависящая от Telegram.

Здесь всё, что можно проверить тестами без сети и без токена: разбор
пользовательского ввода, подбор коктейлей, форматирование сообщения и
содержимое кнопок. ``handlers.py`` остаётся тонким слоем транспорта, поэтому
замена aiogram на HTTP или на что-то ещё затронет только его.

Два измерения навигации:

* **страница подбора** - сколько ингредиентов разрешено докупить (0, 1, 2);
* **лист** - смещение внутри страницы, по ``PAGE_SIZE`` карточек.

Это разные вещи, и путать их нельзя: страница отвечает на вопрос «что мне
нужно купить», лист - «покажи остальные варианты из этого же набора».
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from cocktail.models import Cocktail
from cocktail.search import IngredientMatcher, MatchResult, find
from cocktail.translate import Translator

#: Одна карточка = одно сообщение с фотографией.
#: Telegram ограничивает подпись к фото 1024 символами, оставляем запас.
CAPTION_LIMIT = 1000
#: Три страницы подбора: готово сейчас, докупить один, докупить два.
BUCKETS = (0, 1, 2)
#: Подписи кнопок-переключателей страниц.
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
    "Кнопки под ответом переключают страницы, стрелки листают список "
    "внутри страницы. «Только своё» - строгое условие, без покупок.\n\n"
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

BACK_LABEL = "◀ назад"
FORWARD_LABEL = "вперёд ▶"


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
    photo: str | None = None

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


def parse_callback(data: str) -> tuple[int, int, str] | None:
    """Разобрать callback_data.

    Два формата: ``m1:ключ`` (страница без листания) и ``m1:ключ:8``
    (страница и смещение). Возвращает ``(страница, смещение, ключ)``.
    """
    prefix, separator, rest = data.partition(":")
    if not separator or not prefix.startswith("m"):
        return None

    try:
        bucket = int(prefix[1:])
    except ValueError:
        return None
    if bucket < 0:
        return None

    parts = rest.split(":")
    key = parts[0].strip()
    if not key:
        return None

    offset = 0
    if len(parts) > 1:
        try:
            offset = int(parts[1])
        except ValueError:
            return None
        if offset < 0:
            offset = 0
    if len(parts) > 2:
        return None
    return bucket, offset, key


def build_reply(
    text: str,
    cocktails: Sequence[Cocktail],
    matcher: IngredientMatcher,
    cache: QueryCache,
    *,
    translator: Translator | None = None,
    bucket: int = 0,
    offset: int = 0,
) -> Reply:
    """Собрать ответ на пользовательский текст.

    :param bucket: страница подбора - 0 (готово сейчас), 1 или 2 (сколько
        ингредиентов разрешено докупить). Если для страницы ничего нет, бот
        сам переходит к следующей и говорит об этом: молчаливое «ничего не
        найдено» раздражает сильнее, чем честное «покажу ближайшее».
    :param offset: смещение внутри страницы, кратно ``PAGE_SIZE``.
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

    index = _clamp_offset(offset, len(page))
    result = page[index]

    note = ""
    if current != requested:
        note = NOTE_NO_READY if requested == 0 else NOTE_ONE_MISSING_EMPTY
        note += "\n\n"

    renderer = translator or Translator.empty()
    message = (
        f"Что можно сделать: {_escape(', '.join(have))}\n\n"
        f"{note}{_header(current, len(page), index)}\n\n"
        f"{_format_result(result, renderer)}"
    )
    rows = _bucket_rows(text, cache, current, pages) + _navigation_rows(
        text,
        cache,
        current,
        index,
        len(page),
    )
    return Reply(text=_clamp_caption(message), rows=rows, photo=result.cocktail.image)


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


def _format_result(result: MatchResult, translator: Translator) -> str:
    """Карточка коктейля: название, полный состав, чего не хватает.

    Строки идут без отступа: Telegram по-разному обращается с ведущими
    пробелами в подписях к фото, и «Состав» с «Докупить» начинали
    выглядеть сдвинутыми друг относительно друга.
    """
    total = len(result.matched) + len(result.missing)
    name = _bold(_title(result.cocktail.name, translator))
    matched = len(result.matched)
    title = f"{name} - {matched}/{total}"
    composition = ", ".join(
        _unique(translator.ingredient(measure.ingredient) for measure in result.cocktail.measures)
    )
    lines = [title, f"<b>Состав:</b> {_escape(composition)}"]
    if not result.missing:
        lines.append("Всё есть")
        return "\n".join(lines)

    missing = ", ".join(
        _unique(translator.ingredient(item) for item in result.missing[:MISSING_INLINE])
    )
    if len(result.missing) > MISSING_INLINE:
        missing += f" и ещё {len(result.missing) - MISSING_INLINE}"
    lines.append(f"<b>Докупить:</b> {_escape(missing)}")
    return "\n".join(lines)


def _escape(text: str) -> str:
    """Экранировать текст для HTML-разметки Telegram.

    Сообщения уходят с parse_mode=HTML, поэтому любые амперсанды и угловые
    скобки - в том числе в названиях вроде «AT&T» и во вводе пользователя -
    должны быть экранированы, иначе Telegram отклонит сообщение.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _bold(text: str) -> str:
    return f"<b>{_escape(text)}</b>"


def _unique(names: Iterable[str]) -> list[str]:
    """Убрать повторы, сохранив порядок.

    В каталоге один ингредиент может встречаться дважды: у Whiskey Sour
    лимон указан и как «сок половины», и как «половина слайса». Для состава
    это шум, поэтому в карточке он показывается один раз.
    """
    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(name)
    return result


def _title(name: str, translator: Translator) -> str:
    """Название с переводом в скобках, если перевод есть."""
    translated = translator.cocktail(name)
    return f"{name} ({translated})" if translated else name


def _header(bucket: int, total: int, index: int) -> str:
    if bucket == 0:
        title = f"Готово к приготовлению: {total}"
    else:
        noun = "ингредиент" if bucket == 1 else "ингредиента"
        title = f"Докупить {bucket} {noun}: {total}"
    if total > 1:
        title += f"\nКоктейль {index + 1} из {total}"
    return title


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


def _navigation_rows(
    text: str,
    cache: QueryCache,
    bucket: int,
    index: int,
    total: int,
) -> tuple[tuple[Button, ...], ...]:
    """Стрелки листания: по одной карточке в каждую сторону.

    Кнопка появляется только если в ту сторону действительно есть карточки:
    стрелка, которая ничего не делает, хуже отсутствующей.
    """
    if total <= 1:
        return ()

    key = cache.put(text)
    buttons: list[Button] = []
    if index > 0:
        buttons.append(Button(text=BACK_LABEL, data=f"m{bucket}:{key}:{index - 1}"))
    if index + 1 < total:
        buttons.append(Button(text=FORWARD_LABEL, data=f"m{bucket}:{key}:{index + 1}"))
    if not buttons:
        return ()
    return (tuple(buttons),)


def _clamp_bucket(bucket: int) -> int:
    if bucket in BUCKETS:
        return bucket
    return min(max(bucket, min(BUCKETS)), max(BUCKETS))


def _clamp_offset(offset: int, total: int) -> int:
    """Привести смещение к существующей карточке."""
    if offset <= 0 or total <= 0:
        return 0
    return min(offset, total - 1)


def _clamp_caption(message: str) -> str:
    """Уложиться в лимит подписи к фотографии."""
    if len(message) <= CAPTION_LIMIT:
        return message
    return message[: CAPTION_LIMIT - len(TRUNCATED_SUFFIX)].rstrip() + TRUNCATED_SUFFIX
