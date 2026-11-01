"""Обработчики Telegram. Тонкий слой: вся логика в service.py."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from cocktail.bot.runtime import BotApp
from cocktail.bot.service import (
    ABOUT_TEXT,
    HELP_TEXT,
    START_TEXT,
    Button,
    Reply,
    build_reply,
    parse_callback,
)

router = Router(name="cocktail")

UNKNOWN_COMMAND_TEXT = "Не знаю такой команды. /help покажет, что я умею."


@router.message(CommandStart())
async def on_start(message: Message) -> None:
    await message.answer(START_TEXT)


@router.message(Command("help"))
async def on_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("about"))
async def on_about(message: Message) -> None:
    await message.answer(ABOUT_TEXT)


@router.message(F.text.startswith("/"))
async def on_unknown_command(message: Message) -> None:
    await message.answer(UNKNOWN_COMMAND_TEXT)


@router.message(F.text)
async def on_text(message: Message, app: BotApp) -> None:
    reply = build_reply(message.text or "", app.cocktails, app.matcher, app.cache)
    await message.answer(reply.text, reply_markup=to_markup(reply))


@router.callback_query(F.data.startswith("m"))
async def on_more(callback: CallbackQuery, app: BotApp) -> None:
    parsed = parse_callback(callback.data or "")
    if parsed is None:
        await callback.answer()
        return

    max_missing, key = parsed
    text = app.cache.get(key)
    if text is None:
        await callback.answer("Запрос устарел. Пришли ингредиенты заново.", show_alert=True)
        return

    reply = build_reply(
        text,
        app.cocktails,
        app.matcher,
        app.cache,
        max_missing=max_missing,
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_text(reply.text, reply_markup=to_markup(reply))
    await callback.answer()


def to_markup(reply: Reply) -> InlineKeyboardMarkup | None:
    """Преобразовать кнопки из логики в разметку Telegram."""
    if not reply.has_buttons:
        return None
    rows = [
        [InlineKeyboardButton(text=button.text, callback_data=button.data) for button in row]
        for row in reply.rows
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


__all__ = ["Button", "router", "to_markup"]
