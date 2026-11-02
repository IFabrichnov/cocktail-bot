"""Человеческие подписи для карточки: количества, бокал, тип напитка.

Каталог отдаёт количества в унциях и «дэшах», бокалы по-английски и категории
вроде ``Punch / Party Drink``. Пользователю это не нужно, поэтому здесь
собирается один слой перевода: объёмы приводим к миллилитрам, штучные
единицы склоняем по-русски, бокалы и категории переводим словарём.
"""

from __future__ import annotations

from typing import Final

#: Объёмы: множитель к миллилитрам.
VOLUME_UNITS: Final[dict[str, float]] = {
    "ml": 1.0,
    "cl": 10.0,
    "l": 1000.0,
    "oz": 29.5735,
    "tsp": 5.0,
    "tbsp": 15.0,
    "cup": 240.0,
    "pint": 473.0,
    "quart": 946.0,
    "gallon": 3785.0,
    "shot": 44.0,
    "jigger": 44.0,
    "splash": 3.0,
    "barspoon": 5.0,
    "g": 1.0,
}

#: Штучные единицы: формы для 1, 2-4 и остальных.
COUNT_UNITS: Final[dict[str, tuple[str, str, str]]] = {
    "dash": ("дэш", "дэша", "дэшей"),
    "drop": ("капля", "капли", "капель"),
    "pinch": ("щепотка", "щепотки", "щепоток"),
    "twist": ("твист", "твиста", "твистов"),
    "slice": ("слайс", "слайса", "слайсов"),
    "wedge": ("долька", "дольки", "долек"),
    "sprig": ("веточка", "веточки", "веточек"),
    "leaf": ("листик", "листика", "листиков"),
    "cube": ("кубик", "кубика", "кубиков"),
    "can": ("банка", "банки", "банок"),
    "bottle": ("бутылка", "бутылки", "бутылок"),
    "scoop": ("ложка", "ложки", "ложек"),
    "glass": ("стакан", "стакана", "стаканов"),
    "part": ("часть", "части", "частей"),
    "whole": ("штука", "штуки", "штук"),
}

#: Бокалы из каталога. Ключи в нижнем регистре: в данных встречаются
#: «Highball glass» и «Highball Glass».
GLASSES: Final[dict[str, str]] = {
    "cocktail glass": "коктейльный бокал",
    "martini glass": "бокал мартини",
    "margarita glass": "бокал маргариты",
    "margarita/coupette glass": "бокал маргариты",
    "coupe glass": "бокал-купе",
    "highball glass": "хайбол",
    "collins glass": "коллинз",
    "old-fashioned glass": "олд-фэшн",
    "shot glass": "шот",
    "pousse cafe glass": "бокал для слоистых коктейлей",
    "whiskey sour glass": "бокал для сауэра",
    "whiskey glass": "бокал для виски",
    "cordial glass": "бокал для ликёра",
    "nick and nora glass": "бокал ник-и-нора",
    "hurricane glass": "бокал-ураган",
    "balloon glass": "бокал-баллон",
    "brandy snifter": "снифтер",
    "champagne flute": "флюте",
    "wine glass": "винный бокал",
    "white wine glass": "бокал для белого вина",
    "pint glass": "пивной бокал",
    "beer glass": "пивной бокал",
    "beer mug": "пивная кружка",
    "beer pilsner": "пильзнер",
    "coffee mug": "кружка",
    "irish coffee cup": "бокал для ирландского кофе",
    "copper mug": "медная кружка",
    "mason jar": "банка",
    "jar": "банка",
    "pitcher": "кувшин",
    "punch bowl": "пуншевая чаша",
    "cocoa mug": "кружка для какао",
}

#: Категории каталога.
CATEGORIES: Final[dict[str, str]] = {
    "ordinary drink": "обычный напиток",
    "cocktail": "коктейль",
    "shot": "шот",
    "punch / party drink": "пунш",
    "coffee / tea": "кофе или чай",
    "shake": "шейк",
    "beer": "пиво",
    "soft drink": "безалкогольный напиток",
    "cocoa": "какао",
    "homemade liqueur": "домашний ликёр",
    "other / unknown": "другое",
}

#: Категории IBA.
IBA_LABELS: Final[dict[str, str]] = {
    "unforgettables": "классика IBA",
    "contemporary classics": "современная классика IBA",
    "new era drinks": "новые коктейли IBA",
}


def plural(count: float, one: str, few: str, many: str) -> str:
    """Русская форма слова для числа: 1 кубик, 2 кубика, 5 кубиков."""
    value = abs(round(count))
    tail = value % 100
    if 11 <= tail <= 14:
        return many
    last = value % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


def number(value: float) -> str:
    """Число по-русски: целые без дробной части, дробные через запятую."""
    rounded = round(value, 1)
    if abs(rounded - round(rounded)) < 0.05:
        return str(round(rounded))
    return f"{rounded:.1f}".replace(".", ",")


def format_amount(amount: float | None, unit: str | None) -> str | None:
    """Количество для карточки: «60 мл», «2 дэша» или просто число."""
    if amount is None or amount <= 0:
        return None

    if unit is None:
        # В каталоге бывает просто «1» без единицы: для фруктов и яиц это штуки.
        return f"{number(amount)} шт"

    factor = VOLUME_UNITS.get(unit)
    if factor is not None:
        return f"{number(amount * factor)} мл"

    forms = COUNT_UNITS.get(unit)
    if forms is not None:
        word = plural(amount, *forms)
        return f"{number(amount)} {word}"

    return f"{number(amount)} {unit}"


def glass_label(value: str | None) -> str | None:
    if not value:
        return None
    return GLASSES.get(value.strip().lower(), value)


def category_label(value: str | None) -> str | None:
    if not value:
        return None
    return CATEGORIES.get(value.strip().lower(), value)


def iba_label(value: str | None) -> str | None:
    if not value:
        return None
    return IBA_LABELS.get(value.strip().lower(), value)


def alcoholic_label(value: str | None) -> str | None:
    """Пометка только для безалкогольных: остальное и так понятно."""
    if not value:
        return None
    text = value.strip().lower()
    if text in {"non alcoholic", "non-alcoholic", "non_alcoholic"}:
        return "безалкогольный"
    if text == "optional alcohol":
        return "алкоголь по желанию"
    return None
