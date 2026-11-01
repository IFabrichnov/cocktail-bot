"""Тесты клиента API - на MockTransport, без сети."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from cocktail.errors import ApiError
from cocktail.fetch import CocktailDbClient, crawl, parse_letters


def make_client(handler: Any, base_url: str = "https://api.test/v1/1") -> CocktailDbClient:
    return CocktailDbClient(base_url, transport=httpx.MockTransport(handler))


def test_search_by_letter_sends_expected_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"drinks": [{"idDrink": "1", "strDrink": "A"}]})

    with make_client(handler) as client:
        drinks = client.search_by_letter("a")

    assert drinks == [{"idDrink": "1", "strDrink": "A"}]
    assert str(seen[0].url) == "https://api.test/v1/1/search.php?f=a"


def test_null_drinks_means_empty_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"drinks": None})

    with make_client(handler) as client:
        assert client.search_by_letter("z") == []


def test_http_error_becomes_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    with make_client(handler) as client, pytest.raises(ApiError, match="503"):
        client.search_by_letter("a")


def test_non_json_becomes_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>")

    with make_client(handler) as client, pytest.raises(ApiError):
        client.search_by_letter("a")


def test_multi_char_letter_rejected() -> None:
    with (
        make_client(lambda request: httpx.Response(200, json={})) as client,
        pytest.raises(ValueError, match="один символ"),
    ):
        client.search_by_letter("ab")


def test_crawl_deduplicates() -> None:
    pages: dict[str, list[dict[str, Any]]] = {
        "a": [{"idDrink": "1", "strDrink": "A"}, {"idDrink": "2", "strDrink": "B"}],
        "b": [{"idDrink": "2", "strDrink": "B"}, {"idDrink": "3", "strDrink": "C"}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        letter = request.url.params["f"]
        return httpx.Response(200, json={"drinks": pages.get(letter)})

    with make_client(handler) as client:
        drinks = crawl(client, ["a", "b"], progress=False)

    assert [drink["idDrink"] for drink in drinks] == ["1", "2", "3"]


def test_parse_letters_default() -> None:
    letters = parse_letters(None)
    assert "a" in letters
    assert "0" in letters
    assert len(letters) == 36


def test_parse_letters_dedupes_and_lowercases() -> None:
    assert parse_letters("aAbB1") == ("a", "b", "1")


def test_parse_letters_empty_raises() -> None:
    with pytest.raises(ValueError, match="буквы"):
        parse_letters(" , ")
