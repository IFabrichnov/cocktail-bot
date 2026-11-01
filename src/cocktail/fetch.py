"""Клиент TheCocktailDB: скачивание каталога.

Публичный тестовый ключ - ``1``, регистрация не нужна. Полный каталог
обходится по алфавиту: ``search.php?f=<символ>`` возвращает все напитки,
начинающиеся с символа. Это 36 запросов вместо пагинации по id.

Снапшот пишется отдельно (``store.save_snapshot``), клиент в файловую
систему не пишет - так его проще тестировать и переиспользовать.
"""

from __future__ import annotations

import logging
import string
from collections.abc import Iterable, Sequence
from typing import Any

import httpx

from cocktail.errors import ApiError

LOGGER = logging.getLogger(__name__)

#: Символы, по которым обходим каталог: латиница + цифры.
DEFAULT_ALPHABET: tuple[str, ...] = tuple(string.ascii_lowercase) + tuple(string.digits)


class CocktailDbClient:
    """Минимальный клиент TheCocktailDB.

    Клиент можно использовать как контекстный менеджер::

        with CocktailDbClient(base_url) as client:
            drinks = client.search_by_letter("a")
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        # base_url с завершающим слэшем: иначе httpx отбросит последний сегмент
        # пути и запрос уйдёт на /api/json/v1/search.php вместо /api/json/v1/1/.
        self._base_url = base_url.rstrip("/") + "/"
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            headers={"User-Agent": "cocktail-bot/0.1 (+https://thecocktaildb.com)"},
            transport=transport,
            follow_redirects=True,
        )

    def __enter__(self) -> CocktailDbClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def search_by_letter(self, letter: str) -> list[dict[str, Any]]:
        """Все напитки, название которых начинается с ``letter``."""
        if len(letter) != 1:
            raise ValueError(f"Ожидался один символ, получено: {letter!r}")
        payload = self._get("search.php", {"f": letter})
        return _as_drinks(payload)

    def lookup(self, drink_id: str) -> dict[str, Any] | None:
        """Один напиток по id."""
        payload = self._get("lookup.php", {"i": drink_id})
        drinks = _as_drinks(payload)
        return drinks[0] if drinks else None

    def list_ingredients(self) -> list[dict[str, Any]]:
        """Полный список ингредиентов каталога (пригодится для словаря алиасов)."""
        payload = self._get("list.php", {"i": "list"})
        raw = payload.get("drinks")
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, dict)]

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = self._client.get(path, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ApiError(
                f"API вернул {exc.response.status_code} на {path}: {exc.response.text[:200]}",
            ) from exc
        except httpx.HTTPError as exc:
            raise ApiError(f"Сетевая ошибка при запросе {path}: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiError(f"Ответ {path} - не JSON: {response.text[:200]}") from exc
        if not isinstance(payload, dict):
            raise ApiError(f"Ответ {path} - не JSON-объект")
        return payload


def crawl(
    client: CocktailDbClient,
    letters: Sequence[str] = DEFAULT_ALPHABET,
    *,
    progress: bool = True,
) -> list[dict[str, Any]]:
    """Обойти каталог по алфавиту и вернуть уникальные напитки.

    Дубликаты возможны: некоторые напитки находятся по нескольким буквам.
    Дедупликация по ``idDrink`` с сохранением порядка первого появления.
    """
    seen: dict[str, dict[str, Any]] = {}
    for index, letter in enumerate(letters, start=1):
        drinks = client.search_by_letter(letter)
        for drink in drinks:
            drink_id = str(drink.get("idDrink") or "")
            if drink_id and drink_id not in seen:
                seen[drink_id] = drink
        if progress:
            LOGGER.info(
                "[%d/%d] %r: +%d, всего %d",
                index,
                len(letters),
                letter,
                len(drinks),
                len(seen),
            )
    return list(seen.values())


def parse_letters(raw: str | Iterable[str] | None) -> tuple[str, ...]:
    """Разобрать строку ``--letters abc`` в кортеж символов."""
    if raw is None:
        return DEFAULT_ALPHABET
    if isinstance(raw, str):
        chars = [char for char in raw.strip().lower() if not char.isspace()]
    else:
        chars = [char.lower() for char in raw]
    unique: list[str] = []
    for char in chars:
        if not char.isalnum() or len(char) != 1:
            raise ValueError(f"Ожидались буквы и цифры, получено: {char!r}")
        if char not in unique:
            unique.append(char)
    if not unique:
        raise ValueError("Список букв пуст")
    return tuple(unique)


def _as_drinks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("drinks")
    if raw is None:
        # TheCocktailDB возвращает "drinks": null, когда ничего не найдено.
        return []
    if not isinstance(raw, list):
        raise ApiError("Поле 'drinks' в ответе API имеет неожиданный тип")
    return [item for item in raw if isinstance(item, dict)]
