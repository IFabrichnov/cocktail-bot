"""Сборка бота: диспетчер, разметка кнопок. aiogram нужен, сеть нет."""

from __future__ import annotations

from pathlib import Path

import pytest

from cocktail.bot.service import QueryCache, Reply, build_reply
from cocktail.models import Cocktail
from cocktail.search import IngredientMatcher

pytest.importorskip("aiogram")

from cocktail.bot.app import create_dispatcher
from cocktail.bot.handlers import to_markup
from cocktail.bot.runtime import BotApp
from cocktail.config import Config


def test_dispatcher_wires_router(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    app = BotApp(cocktails=cocktails, matcher=matcher)
    dispatcher = create_dispatcher(app)
    assert dispatcher.sub_routers
    assert dispatcher.workflow_data["app"] is app


def test_to_markup_builds_inline_keyboard(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    reply = build_reply("джин, тоник, лайм", cocktails, matcher, QueryCache())
    markup = to_markup(reply)
    assert markup is not None
    button = markup.inline_keyboard[0][0]
    assert button.text == "докупить 2"
    assert button.callback_data is not None
    assert button.callback_data.startswith("m2:")


def test_to_markup_is_none_without_buttons() -> None:
    assert to_markup(Reply(text="просто текст")) is None


def test_bot_app_loads_snapshot(snapshot_file: Path) -> None:
    config = Config(
        data_dir=snapshot_file.parent,
        snapshot_path=snapshot_file,
        aliases_path=Path("data/aliases.yaml"),
    )
    app = BotApp.load(config)
    assert app.size == 3
    assert app.snapshot_path == snapshot_file
