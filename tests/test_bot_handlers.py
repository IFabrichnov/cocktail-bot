"""Обновление уже отправленного сообщения: фото, подпись, текст.

Проверяем именно поведение транспорта: при листании карточек должна меняться
и картинка, а не только подпись. Это единственное место, где легко ошибиться
и не заметить: ``edit_caption`` меняет текст под фото, оставляя снимок от
предыдущего коктейля.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from cocktail.bot.handlers import deliver, replace
from cocktail.bot.service import Button, Reply

pytest.importorskip("aiogram")

from aiogram.types import Message


class FakeMessage:
    """Минимальная заглушка сообщения: запоминает вызовы."""

    def __init__(self, has_photo: bool = False) -> None:
        self.photo: list[object] | None = [object()] if has_photo else None
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def edit_media(self, **kwargs: Any) -> None:
        self.calls.append(("edit_media", kwargs))

    async def edit_caption(self, **kwargs: Any) -> None:
        self.calls.append(("edit_caption", kwargs))

    async def edit_text(self, text: str, **kwargs: Any) -> None:
        self.calls.append(("edit_text", {"text": text, **kwargs}))

    async def answer_photo(self, **kwargs: Any) -> None:
        self.calls.append(("answer_photo", kwargs))

    async def answer(self, text: str, **kwargs: Any) -> None:
        self.calls.append(("answer", {"text": text, **kwargs}))


def _message(fake: FakeMessage) -> Message:
    return cast("Message", fake)


def test_replace_changes_photo_when_message_has_photo() -> None:
    fake = FakeMessage(has_photo=True)
    reply = Reply(text="карточка", photo="https://example.test/new.jpg")

    asyncio.run(replace(_message(fake), reply))

    assert fake.calls[0][0] == "edit_media"
    media = fake.calls[0][1]["media"]
    assert media.media == "https://example.test/new.jpg"
    assert media.caption == "карточка"


def test_replace_without_new_photo_edits_caption() -> None:
    fake = FakeMessage(has_photo=True)

    asyncio.run(replace(_message(fake), Reply(text="ничего не нашлось")))

    assert fake.calls[0][0] == "edit_caption"
    assert fake.calls[0][1]["caption"] == "ничего не нашлось"


def test_replace_text_message_with_photo_sends_new() -> None:
    fake = FakeMessage(has_photo=False)
    reply = Reply(text="карточка", photo="https://example.test/new.jpg")

    asyncio.run(replace(_message(fake), reply))

    assert fake.calls[0][0] == "answer_photo"
    assert fake.calls[0][1]["photo"] == "https://example.test/new.jpg"


def test_replace_text_message_edits_text() -> None:
    fake = FakeMessage(has_photo=False)

    asyncio.run(replace(_message(fake), Reply(text="просто текст")))

    assert fake.calls[0][0] == "edit_text"
    assert fake.calls[0][1]["text"] == "просто текст"


def test_deliver_sends_photo_or_text() -> None:
    with_photo = FakeMessage()
    asyncio.run(deliver(_message(with_photo), Reply(text="x", photo="https://example.test/a.jpg")))
    assert with_photo.calls[0][0] == "answer_photo"

    plain = FakeMessage()
    asyncio.run(deliver(_message(plain), Reply(text="x")))
    assert plain.calls[0][0] == "answer"


def test_markup_is_attached_to_photo_message() -> None:
    fake = FakeMessage(has_photo=True)
    reply = Reply(
        text="карточка",
        rows=((Button(text="вперёд ▶", data="m1:key:1"),),),
        photo="https://example.test/new.jpg",
    )

    asyncio.run(replace(_message(fake), reply))

    markup = fake.calls[0][1]["reply_markup"]
    assert markup is not None
    assert markup.inline_keyboard[0][0].callback_data == "m1:key:1"
