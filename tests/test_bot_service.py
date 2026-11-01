"""Тесты логики бота: без сети, без токена, без aiogram."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from cocktail.bot.service import (
    EMPTY_TEXT,
    NOTHING_TEXT,
    Button,
    QueryCache,
    build_reply,
    parse_callback,
    parse_have,
)
from cocktail.models import Cocktail, IngredientMeasure
from cocktail.normalize import AliasBook
from cocktail.search import IngredientMatcher


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("джин, лайм, тоник", ["джин", "лайм", "тоник"]),
        ("джин;лайм\nтоник", ["джин", "лайм", "тоник"]),
        ("  джин ,  лайм  ", ["джин", "лайм"]),
        ("джин, джин", ["джин"]),
        ("", []),
        ("   ", []),
        (",,,", []),
    ],
)
def test_parse_have(text: str, expected: list[str]) -> None:
    assert parse_have(text) == expected


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ("m0:abcd123456", (0, "abcd123456")),
        ("m3:key", (3, "key")),
        ("x0:key", None),
        ("m:key", None),
        ("m0:", None),
        ("mabc:key", None),
        ("m-1:key", None),
    ],
)
def test_parse_callback(data: str, expected: tuple[int, str] | None) -> None:
    assert parse_callback(data) == expected


def test_cache_roundtrip() -> None:
    cache = QueryCache()
    key = cache.put("джин, лайм")
    assert cache.get(key) == "джин, лайм"
    assert cache.get("nope") is None


def test_cache_key_is_deterministic() -> None:
    first = QueryCache()
    second = QueryCache()
    assert first.put("джин") == second.put("джин")


def test_cache_evicts_oldest() -> None:
    cache = QueryCache(limit=2)
    first = cache.put("a")
    cache.put("b")
    cache.put("c")
    assert len(cache) == 2
    assert cache.get(first) is None


def test_reply_for_complete_match(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    reply = build_reply("джин, тоник, лайм", cocktails, matcher, QueryCache())
    assert "Gin Tonic" in reply.text
    assert "всё есть" in reply.text
    assert reply.has_buttons


def test_reply_counts_missing(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    reply = build_reply(
        "текила, сок лайма",
        cocktails,
        matcher,
        QueryCache(),
        max_missing=3,
    )
    assert "Margarita" in reply.text
    assert "докупить: Triple sec, Salt" in reply.text


def test_reply_falls_back_when_nothing_exact(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    reply = build_reply("джин", cocktails, matcher, QueryCache())
    assert "почти готово" in reply.text
    assert "Gin Tonic" in reply.text or "Negroni" in reply.text


def test_reply_when_nothing_at_all(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    reply = build_reply("unobtainium", cocktails, matcher, QueryCache())
    assert reply.text == NOTHING_TEXT
    assert reply.has_buttons


def test_reply_on_empty_input(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    reply = build_reply("  ,  ", cocktails, matcher, QueryCache())
    assert reply.text == EMPTY_TEXT
    assert not reply.has_buttons


def test_buttons_offer_other_limits(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    cache = QueryCache()
    # При пороге 1 Gin Tonic подходит (не хватает только лайма), поэтому
    # автофолбэк не срабатывает и текущий порог остаётся 1.
    reply = build_reply("джин, тоник", cocktails, matcher, cache, max_missing=1)
    buttons = [button for row in reply.rows for button in row]
    assert [button.text for button in buttons] == [
        "докупить 0",
        "докупить 2",
        "докупить 3",
    ]
    assert all(button.data.startswith("m") for button in buttons)
    assert len(buttons[0].data.encode("utf-8")) <= 64


def test_button_data_roundtrip(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    cache = QueryCache()
    reply = build_reply("джин, тоник, лайм", cocktails, matcher, cache)
    button = reply.rows[0][0]
    parsed = parse_callback(button.data)
    assert parsed is not None
    max_missing, key = parsed
    # Текущий порог 0, поэтому первая кнопка предлагает 1.
    assert max_missing == 1
    assert cache.get(key) == "джин, тоник, лайм"


def test_reply_is_clamped() -> None:
    matcher = IngredientMatcher(AliasBook(entries={"gin": ("джин",)}))
    many = tuple(
        Cocktail(
            id=str(index),
            name=f"Коктейль номер {index} " * 60,
            measures=(IngredientMeasure(ingredient="Gin", raw="Gin"),),
        )
        for index in range(5)
    )
    reply = build_reply("джин", many, matcher, QueryCache())
    assert len(reply.text) <= 3800
    assert reply.text.endswith("показал первые варианты.")


def test_button_is_frozen() -> None:
    button = Button(text="x", data="m0:key")
    with pytest.raises(FrozenInstanceError):
        button.text = "y"  # type: ignore[misc]
