"""Тесты логики бота: без сети, без токена, без aiogram."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from cocktail.bot.service import (
    EMPTY_TEXT,
    NOTHING_TEXT,
    Button,
    QueryCache,
    Reply,
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
        ("m0:abcd123456", (0, 0, "abcd123456")),
        ("m3:key", (3, 0, "key")),
        ("m2:key:8", (2, 8, "key")),
        ("m1:key:0", (1, 0, "key")),
        ("m1:key:-5", (1, 0, "key")),
        ("x0:key", None),
        ("m:key", None),
        ("m0:", None),
        ("mabc:key", None),
        ("m-1:key", None),
        ("m1:key:abc", None),
        ("m1:key:8:9", None),
    ],
)
def test_parse_callback(data: str, expected: tuple[int, int, str] | None) -> None:
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
    assert "Всё есть" in reply.text
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
        bucket=2,
    )
    assert "Margarita" in reply.text
    assert "<b>Докупить:</b> Triple sec, Salt" in reply.text


def test_reply_falls_back_when_nothing_exact(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    # Только джин: готовых нет, с одним недостающим тоже нет, поэтому
    # бот показывает страницу «докупить 2» и говорит об этом.
    reply = build_reply("джин", cocktails, matcher, QueryCache())
    assert "Готовых коктейлей нет" in reply.text
    assert "Gin Tonic" in reply.text or "Negroni" in reply.text


def test_pages_differ(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    # Главное требование к кнопкам: нажатие меняет содержимое, а не только
    # заголовок. Джин и тоник дают Gimlet-подобный напиток на странице 1
    # и Negroni на странице 2.
    first = build_reply("джин, тоник", cocktails, matcher, QueryCache(), bucket=1)
    second = build_reply("джин, тоник", cocktails, matcher, QueryCache(), bucket=2)
    assert "Gin Tonic" in first.text
    assert "Negroni" in second.text
    assert "Negroni" not in first.text


def test_bucket_is_clamped(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    # Раньше кнопка умела «докупить 3», теперь такого нет.
    reply = build_reply("джин, тоник", cocktails, matcher, QueryCache(), bucket=99)
    assert "Докупить 2" in reply.text


def test_reply_when_nothing_at_all(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    reply = build_reply("unobtainium", cocktails, matcher, QueryCache())
    assert reply.text == NOTHING_TEXT
    # Все страницы пусты, поэтому кнопок нет: вести пользователя некуда.
    assert not reply.has_buttons


def test_reply_on_empty_input(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    reply = build_reply("  ,  ", cocktails, matcher, QueryCache())
    assert reply.text == EMPTY_TEXT
    assert not reply.has_buttons


def test_buttons_offer_other_pages(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    cache = QueryCache()
    # На странице 1 Gin Tonic подходит (не хватает только лайма).
    # Страница 0 пуста (готовых нет), поэтому кнопки «только своё» нет:
    # она вела бы на пустой экран.
    reply = build_reply("джин, тоник", cocktails, matcher, cache, bucket=1)
    buttons = [button for row in reply.rows for button in row]
    assert [button.text for button in buttons] == ["докупить 2"]
    assert all(button.data.startswith("m") for button in buttons)
    assert len(buttons[0].data.encode("utf-8")) <= 64


def test_buttons_never_lead_to_empty_page(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    cache = QueryCache()
    for bucket in (0, 1, 2):
        reply = build_reply("джин, тоник", cocktails, matcher, cache, bucket=bucket)
        for button in (button for row in reply.rows for button in row):
            target = int(button.data[1:].split(":")[0])
            follow_up = build_reply(
                "джин, тоник",
                cocktails,
                matcher,
                cache,
                bucket=target,
            )
            assert follow_up.text != NOTHING_TEXT


def test_no_button_for_three(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    cache = QueryCache()
    for bucket in (0, 1, 2):
        reply = build_reply("джин, тоник", cocktails, matcher, cache, bucket=bucket)
        texts = [button.text for row in reply.rows for button in row]
        assert "докупить 3" not in texts


def test_button_data_roundtrip(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    cache = QueryCache()
    reply = build_reply("джин, тоник, лайм", cocktails, matcher, cache)
    button = reply.rows[0][0]
    parsed = parse_callback(button.data)
    assert parsed is not None
    bucket, offset, key = parsed
    # Текущая страница 0: готов Gin Tonic. Из остальных непустая только 2,
    # потому что Negroni не хватает двух ингредиентов.
    assert bucket == 2
    assert offset == 0
    assert cache.get(key) == "джин, тоник, лайм"


def test_caption_shows_position(
    many_cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    reply = build_reply("джин", many_cocktails, matcher, QueryCache(), bucket=1)
    assert "Коктейль 1 из 20" in reply.text
    # На сообщении одна карточка, а не список.
    assert reply.text.count("<b>Test ") == 1


def test_forward_arrow_then_back(
    many_cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    cache = QueryCache()
    first = build_reply("джин", many_cocktails, matcher, cache, bucket=1)
    forward = _button(first, "вперёд ▶")
    assert forward is not None
    assert _button(first, "◀ назад") is None, "на первой карточке назад идти некуда"

    parsed = parse_callback(forward.data)
    assert parsed is not None
    bucket, offset, _key = parsed
    assert offset == 1, "стрелка листает по одной карточке"

    second = build_reply("джин", many_cocktails, matcher, cache, bucket=bucket, offset=offset)
    assert "Коктейль 2 из 20" in second.text
    assert _button(second, "◀ назад") is not None

    back = _button(second, "◀ назад")
    assert back is not None
    parsed_back = parse_callback(back.data)
    assert parsed_back is not None
    assert parsed_back[1] == 0


def test_last_card_has_no_forward_arrow(
    many_cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    cache = QueryCache()
    total = len(many_cocktails)
    reply = build_reply(
        "джин",
        many_cocktails,
        matcher,
        cache,
        bucket=1,
        offset=total - 1,
    )
    assert _button(reply, "вперёд ▶") is None
    assert _button(reply, "◀ назад") is not None
    assert f"Коктейль {total} из {total}" in reply.text


def test_offset_is_clamped(
    many_cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    reply = build_reply("джин", many_cocktails, matcher, QueryCache(), bucket=1, offset=9999)
    assert "Коктейль 20 из 20" in reply.text
    assert "9999" not in reply.text


def test_single_result_has_no_position_and_arrows(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    reply = build_reply("джин, тоник", cocktails, matcher, QueryCache(), bucket=1)
    assert _button(reply, "вперёд ▶") is None
    assert _button(reply, "◀ назад") is None
    assert "Коктейль" not in reply.text


def test_reply_carries_photo(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    reply = build_reply("джин, тоник", cocktails, matcher, QueryCache(), bucket=1)
    assert reply.photo == "https://example.test/gin-tonic.jpg"


def test_reply_without_photo_falls_back_to_text(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    reply = build_reply("unobtainium", cocktails, matcher, QueryCache())
    assert reply.photo is None


def test_caption_is_clamped() -> None:
    matcher = IngredientMatcher(AliasBook(entries={"gin": ("джин",)}))
    long_name = "Коктейль " + "очень длинное название " * 60
    many = tuple(
        Cocktail(
            id=str(index),
            name=f"{long_name} {index}",
            measures=(IngredientMeasure(ingredient="Gin", raw="Gin"),),
        )
        for index in range(3)
    )
    reply = build_reply("джин", many, matcher, QueryCache())
    assert len(reply.text) <= 1000


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


def _button(reply: Reply, label: str) -> Button | None:
    for row in reply.rows:
        for button in row:
            if button.text == label:
                return button
    return None
