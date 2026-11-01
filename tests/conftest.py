"""Общие фикстуры: синтетический снапшот без сети."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cocktail.models import Cocktail
from cocktail.parse import cocktail_from_raw


@pytest.fixture
def raw_drinks() -> list[dict[str, Any]]:
    """Три напитка, повторяющие структуру ответа TheCocktailDB."""
    return [
        {
            "idDrink": "101",
            "strDrink": "Gin Tonic",
            "strCategory": "Cocktail",
            "strAlcoholic": "Alcoholic",
            "strGlass": "Highball glass",
            "strInstructions": "Build over ice.",
            "strTags": "IBA,Classic",
            "strIngredient1": "Gin",
            "strMeasure1": "2 oz",
            "strIngredient2": "Tonic water",
            "strMeasure2": "4 oz",
            "strIngredient3": "Lime",
            "strMeasure3": "1 wedge",
            "strIngredient4": None,
            "strMeasure4": None,
        },
        {
            "idDrink": "102",
            "strDrink": "Margarita",
            "strCategory": "Cocktail",
            "strAlcoholic": "Alcoholic",
            "strGlass": "Cocktail glass",
            "strInstructions": "Shake with ice.",
            "strTags": None,
            "strIngredient1": "Tequila",
            "strMeasure1": "1 1/2 oz",
            "strIngredient2": "Triple sec",
            "strMeasure2": "1/2 oz",
            "strIngredient3": "Lime juice",
            "strMeasure3": "1 oz",
            "strIngredient4": "Salt",
            "strMeasure4": "",
        },
        {
            "idDrink": "103",
            "strDrink": "Negroni",
            "strCategory": "Cocktail",
            "strAlcoholic": "Alcoholic",
            "strGlass": "Old-fashioned glass",
            "strInstructions": "Stir and serve.",
            "strTags": "IBA",
            "strIngredient1": "Gin",
            "strMeasure1": "1 oz",
            "strIngredient2": "Campari",
            "strMeasure2": "1 oz",
            "strIngredient3": "Sweet Vermouth",
            "strMeasure3": "1 oz",
        },
    ]


@pytest.fixture
def cocktails(raw_drinks: list[dict[str, Any]]) -> tuple[Cocktail, ...]:
    return tuple(cocktail_from_raw(raw) for raw in raw_drinks)


@pytest.fixture
def snapshot_file(tmp_path: Path, raw_drinks: list[dict[str, Any]]) -> Path:
    payload = {
        "schema": 1,
        "source": "https://example.test/api",
        "fetched_at": "2026-11-01T12:00:00+00:00",
        "letters": ["g", "m", "n"],
        "items": raw_drinks,
    }
    path = tmp_path / "cocktails.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path
