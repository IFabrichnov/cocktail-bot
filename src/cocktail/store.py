"""Чтение и запись снапшота каталога.

Снапшот - это единственный источник данных для приложения. Скачиваем один
раз, коммитим в репозиторий, дальше работаем без сети: быстро, воспроизводимо
и без зависимости от лимитов API.

Внутри снапшота лежат **сырые** объекты API, без преобразований. Разбор
(``parse.cocktail_from_raw``) выполняется при загрузке, поэтому парсер можно
переписать и перепроверить, не ходя в интернет.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cocktail.errors import SnapshotError
from cocktail.models import Cocktail
from cocktail.parse import cocktail_from_raw

SNAPSHOT_SCHEMA = 1


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Прочитанный снапшот: метаданные + сырые объекты."""

    schema: int
    source: str
    fetched_at: str
    letters: tuple[str, ...]
    items: tuple[Mapping[str, Any], ...]

    def cocktails(self) -> tuple[Cocktail, ...]:
        """Разобрать все записи в модели. Дорогая операция, кэшируйте результат."""
        return tuple(cocktail_from_raw(item) for item in self.items)

    def __len__(self) -> int:
        return len(self.items)


def load_snapshot(path: Path) -> Snapshot:
    """Прочитать снапшот с диска."""
    if not path.is_file():
        raise SnapshotError(f"Снапшот не найден: {path}. Выполни: cocktail fetch")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SnapshotError(f"Снапшот повреждён ({path}): {exc}") from exc
    if not isinstance(payload, dict):
        raise SnapshotError(f"{path}: ожидался JSON-объект")

    schema = payload.get("schema")
    if schema != SNAPSHOT_SCHEMA:
        raise SnapshotError(
            f"{path}: схема снапшота {schema!r}, ожидается {SNAPSHOT_SCHEMA}. "
            "Пересоздай снапшот: cocktail fetch --force",
        )
    items = payload.get("items")
    if not isinstance(items, list):
        raise SnapshotError(f"{path}: поле 'items' должно быть списком")
    raw_letters = payload.get("letters") or []

    return Snapshot(
        schema=SNAPSHOT_SCHEMA,
        source=str(payload.get("source", "")),
        fetched_at=str(payload.get("fetched_at", "")),
        letters=tuple(str(letter) for letter in raw_letters),
        items=tuple(item for item in items if isinstance(item, dict)),
    )


def build_snapshot(
    items: Sequence[Mapping[str, Any]],
    *,
    letters: Sequence[str],
    source: str,
    fetched_at: datetime | None = None,
) -> dict[str, Any]:
    """Собрать словарь снапшота (без записи на диск)."""
    moment = fetched_at or datetime.now(tz=UTC)
    return {
        "schema": SNAPSHOT_SCHEMA,
        "source": source,
        "fetched_at": moment.isoformat(timespec="seconds"),
        "letters": list(letters),
        "items": list(items),
    }


def save_snapshot(path: Path, payload: Mapping[str, Any]) -> Path:
    """Атомарно записать снапшот: сначала .tmp, потом rename.

    Атомарность важна из-за OneDrive: файл, записанный «наполовину», потом
    синхронизируется и ломает загрузку.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)
    return path
