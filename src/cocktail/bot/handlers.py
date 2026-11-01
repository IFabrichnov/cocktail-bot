"""Обработчики Telegram. Тонкий слой: вся логика в service.py.

Роутер собирается функцией, а не создаётся один раз на импорте: один и тот же
объект ``Router`` нельзя подключить к двум диспетчерам, а диспетчеры нужны
и в тестах, и при повторной инициализации. Явная регистрация обработчиков
заодно делает порядок фильтров видимым.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from cocktail.bot.runtime import BotApp
from cocktail.bot.service import (
    ABOUT_TEXT,
    HELP_TEXT,
    START_TEXT,
    Reply,
    build_reply,
    parse_callback,
)

UNKNOWN_COMMAND_TEXT = "Не знаю такой команды. /help покажет, что я умею."
STALE_QUERY_TEXT = "Запрос устарел. Пришли ингредиенты заново."


async def on_start(message: Message) -> None:
    await message.answer(START_TEXT)


async def on_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


async def on_about(message: Message) -> None:
    await message.answer(ABOUT_TEXT)


async def on_unknown_command(message: Message) -> None:
    await message.answer(UNKNOWN_COMMAND_TEXT)


async def on_text(message: Message, app: BotApp) -> None:
    reply = build_reply(
        message.text or "",
        app.cocktails,
        app.matcher,
        app.cache,
        translator=app.translator,
    )
    await message.answer(reply.text, reply_markup=to_markup(reply), parse_mode=ParseMode.HTML)


async def on_page(callback: CallbackQuery, app: BotApp) -> None:
    parsed = parse_callback(callback.data or "")
    if parsed is None:
        await callback.answer()
        return

    bucket, offset, key = parsed
    text = app.cache.get(key)
    if text is None:
        await callback.answer(STALE_QUERY_TEXT, show_alert=True)
        return

    reply = build_reply(
        text,
        app.cocktails,
        app.matcher,
        app.cache,
        translator=app.translator,
        bucket=bucket,
        offset=offset,
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            reply.text,
            reply_markup=to_markup(reply),
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()


def build_router() -> Router:
    """Собрать роутер с обработчиками.

    Порядок важен: команды регистрируются раньше общего текстового фильтра,
    иначе ``/help`` попал бы в обработчик ингредиентов.
    """
    router = Router(name="cocktail")
    router.message.register(on_start, CommandStart())
    router.message.register(on_help, Command("help"))
    router.message.register(on_about, Command("about"))
    router.message.register(on_unknown_command, F.text.startswith("/"))
    router.message.register(on_text, F.text)
    router.callback_query.register(on_page, F.data.startswith("m"))
    return router


def to_markup(reply: Reply) -> InlineKeyboardMarkup | None:
    """Преобразовать кнопки из логики в разметку Telegram."""
    if not reply.has_buttons:
        return None
    rows = [
        [InlineKeyboardButton(text=button.text, callback_data=button.data) for button in row]
        for row in reply.rows
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


__all__ = ["build_router", "to_markup"]
