"""Исключения ядра.

Все прикладные ошибки наследуются от :class:`CocktailError`, чтобы CLI мог
поймать их одним `except` и вернуть ненулевой код, а не стектрейс.
"""

from __future__ import annotations


class CocktailError(Exception):
    """Базовая ошибка приложения."""


class ConfigError(CocktailError):
    """Некорректная конфигурация: путь, переменная окружения, значение."""


class SnapshotError(CocktailError):
    """Снапшот отсутствует, повреждён или несовместимой версии схемы."""


class ApiError(CocktailError):
    """Ошибка обращения к внешнему API."""


class ParseError(CocktailError):
    """Строку рецепта не удалось разобрать."""
