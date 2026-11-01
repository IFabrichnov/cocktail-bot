"""Разметка сообщений: жирный текст и экранирование.

Сообщения уходят с ``parse_mode=HTML``, поэтому любая динамическая строка
должна быть экранирована: амперсанд в названии вроде «AT&T» или угловая
скобка во вводе пользователя иначе заставят Telegram отклонить сообщение
с ошибкой разбора разметки.
"""

from __future__ import annotations

from cocktail.bot.service import QueryCache, build_reply
from cocktail.models import Cocktail, IngredientMeasure
from cocktail.normalize import AliasBook
from cocktail.search import IngredientMatcher


def test_card_uses_bold_for_labels(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    reply = build_reply("джин, тоник, лайм", cocktails, matcher, QueryCache())
    assert "<b>Gin Tonic</b>" in reply.text
    assert "<b>Состав:</b>" in reply.text
    assert "<b>Докупить:</b>" not in reply.text
    assert "Всё есть" in reply.text


def test_card_bolds_missing_line(
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
    assert "<b>Margarita</b>" in reply.text
    assert "<b>Докупить:</b> Triple sec, Salt" in reply.text


def test_no_pages_hint(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    reply = build_reply("джин, тоник", cocktails, matcher, QueryCache(), bucket=1)
    assert "Стрелки листают" not in reply.text


def test_user_input_is_escaped(
    cocktails: tuple[Cocktail, ...],
    matcher: IngredientMatcher,
) -> None:
    reply = build_reply("джин, <тоник>", cocktails, matcher, QueryCache())
    assert "&lt;тоник&gt;" in reply.text
    assert "<тоник>" not in reply.text

    ampersand = build_reply("джин, at&t", cocktails, matcher, QueryCache())
    assert "at&amp;t" in ampersand.text


def test_catalog_names_are_escaped() -> None:
    cocktail = Cocktail(
        id="1",
        name="Tom & Jerry <Special>",
        measures=(IngredientMeasure(ingredient="Gin", raw="Gin"),),
    )
    matcher = IngredientMatcher(AliasBook(entries={"gin": ("джин",)}))
    reply = build_reply("джин", (cocktail,), matcher, QueryCache())
    assert "<b>Tom &amp; Jerry &lt;Special&gt;</b>" in reply.text
