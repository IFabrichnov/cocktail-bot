"""Тесты отчёта о качестве данных."""

from __future__ import annotations

from cocktail.models import Cocktail
from cocktail.report import build_report


def test_report_counts(cocktails: tuple[Cocktail, ...]) -> None:
    report = build_report(cocktails)
    assert report.cocktails == 3
    assert report.measures == 10
    # Единственная строка без количества - «Salt» у Маргариты.
    assert report.with_amount == 9
    assert report.with_unit == 9
    assert report.amounts_ratio == 0.9


def test_report_top_ingredients(cocktails: tuple[Cocktail, ...]) -> None:
    report = build_report(cocktails, top=3)
    names = [name for name, _count in report.top_ingredients]
    assert "gin" in names
    assert len(report.top_ingredients) <= 3


def test_report_to_dict(cocktails: tuple[Cocktail, ...]) -> None:
    payload = build_report(cocktails).to_dict()
    assert payload["cocktails"] == 3
    assert isinstance(payload["top_ingredients"], list)


def test_empty_catalog() -> None:
    report = build_report([])
    assert report.cocktails == 0
    assert report.amounts_ratio == 0.0
