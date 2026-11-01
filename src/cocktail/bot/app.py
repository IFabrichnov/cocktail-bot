"""Сборка и запуск бота.

Разделение намеренное: ``create_dispatcher`` можно вызвать в тестах без
сети, а ``run`` делает то, что делает боевой процесс - логинится и уходит
в long polling.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from cocktail.bot.handlers import router
from cocktail.bot.runtime import BotApp
from cocktail.config import Config
from cocktail.errors import ConfigError

LOGGER = logging.getLogger(__name__)


def create_dispatcher(app: BotApp) -> Dispatcher:
    """Собрать диспетчер: состояние прокидывается в обработчики как ``app``."""
    dispatcher = Dispatcher()
    dispatcher["app"] = app
    dispatcher.include_router(router)
    return dispatcher


async def run_polling(token: str, app: BotApp) -> None:
    """Запустить long polling и не возвращаться до остановки."""
    if not token:
        raise ConfigError("Пустой токен Telegram")
    bot = Bot(token)
    dispatcher = create_dispatcher(app)
    LOGGER.info("Бот запущен, в каталоге %d коктейлей", app.size)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


def run(token: str, config: Config) -> None:
    """Загрузить данные и запустить бота (блокирующая функция)."""
    app = BotApp.load(config)
    try:
        asyncio.run(run_polling(token, app))
    except KeyboardInterrupt:
        LOGGER.info("Остановлено пользователем")
