"""Конфигурация: переменные окружения, .env и значения по умолчанию.

Приоритет: явный аргумент -> переменная окружения -> .env -> default.
Пути относительные, разрешаются от текущего каталога, поэтому CLI надо
запускать из корня репозитория (или задать абсолютные пути в окружении).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from cocktail.errors import ConfigError

DEFAULT_API_BASE = "https://www.thecocktaildb.com/api/json/v1/1"
DEFAULT_DATA_DIR = Path("data") / "raw"
DEFAULT_TIMEOUT = 20.0


@dataclass(frozen=True, slots=True)
class Config:
    """Всё, что приложению нужно знать о внешнем мире."""

    data_dir: Path
    snapshot_path: Path
    aliases_path: Path
    api_base_url: str = DEFAULT_API_BASE
    http_timeout: float = DEFAULT_TIMEOUT

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        source = os.environ if env is None else env
        data_dir = Path(source.get("COCKTAIL_DATA_DIR", str(DEFAULT_DATA_DIR)))
        snapshot_path = Path(source.get("COCKTAIL_SNAPSHOT", str(data_dir / "cocktails.json")))
        aliases_path = Path(source.get("COCKTAIL_ALIASES", "data/aliases.yaml"))
        api_base_url = source.get("COCKTAIL_API_BASE", DEFAULT_API_BASE).strip()
        if not api_base_url.startswith(("http://", "https://")):
            raise ConfigError(f"COCKTAIL_API_BASE должен быть http(s)-URL: {api_base_url!r}")

        raw_timeout = source.get("COCKTAIL_HTTP_TIMEOUT")
        if raw_timeout is None:
            timeout = DEFAULT_TIMEOUT
        else:
            try:
                timeout = float(raw_timeout)
            except ValueError as exc:
                raise ConfigError(f"COCKTAIL_HTTP_TIMEOUT не число: {raw_timeout!r}") from exc
            if timeout <= 0:
                raise ConfigError("COCKTAIL_HTTP_TIMEOUT должен быть больше нуля")

        return cls(
            data_dir=data_dir,
            snapshot_path=snapshot_path,
            aliases_path=aliases_path,
            api_base_url=api_base_url.rstrip("/"),
            http_timeout=timeout,
        )


def load_dotenv(path: Path | None = None) -> None:
    """Загрузить простой KEY=VALUE из .env, не перетирая окружение.

    Полноценный парсер не нужен: .env здесь только для удобства разработки.
    """
    env_path = path if path is not None else Path(".env")
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
