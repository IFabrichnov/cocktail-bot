"""Командная строка.

Интерфейс сознательно на argparse: ноль зависимостей, работает сразу после
установки, не ломается при обновлении сторонней библиотеки. Команды - это
этапы проекта:

* ``fetch`` - скачать снапшот каталога (этап 1);
* ``report`` - измерить качество разбора ингредиентов (этап 2);
* ``find`` - подобрать коктейли по имеющимся ингредиентам (этап 3);
* ``version`` - версия пакета.

Бот появится отдельной командой ``bot`` на этапе 6, когда ядро будет стабильно.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from cocktail import __version__
from cocktail.config import Config, load_dotenv
from cocktail.errors import CocktailError
from cocktail.fetch import CocktailDbClient, crawl, parse_letters
from cocktail.normalize import load_aliases
from cocktail.report import IngredientReport, build_report
from cocktail.search import IngredientMatcher, MatchResult, find
from cocktail.store import build_snapshot, load_snapshot, save_snapshot

LOGGER = logging.getLogger("cocktail")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cocktail",
        description="Подбор коктейлей по ингредиентам, которые уже есть под рукой.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="подробный лог (прогресс скачивания, разбор данных)",
    )
    parser.add_argument(
        "--snapshot",
        default=None,
        metavar="ПУТЬ",
        help="путь к снапшоту каталога (по умолчанию data/raw/cocktails.json)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="КОМАНДА")

    subparsers.add_parser("version", help="показать версию")

    fetch_parser = subparsers.add_parser("fetch", help="скачать снапшот каталога с TheCocktailDB")
    fetch_parser.add_argument(
        "--letters",
        default=None,
        help="символы для обхода каталога (по умолчанию a-z0-9)",
    )
    fetch_parser.add_argument(
        "--force",
        action="store_true",
        help="перезаписать существующий снапшот",
    )

    report_parser = subparsers.add_parser("report", help="отчёт о качестве разбора ингредиентов")
    report_parser.add_argument("--top", type=int, default=20, help="сколько строк в топах")
    report_parser.add_argument("--json", action="store_true", help="вывод в JSON")

    find_parser = subparsers.add_parser("find", help="подобрать коктейли по ингредиентам")
    find_parser.add_argument(
        "--have",
        required=True,
        help="ингредиенты через запятую, на русском или английском: 'джин, лайм, тоник'",
    )
    find_parser.add_argument(
        "--max-missing",
        type=int,
        default=0,
        help="сколько ингредиентов готов докупить (по умолчанию 0)",
    )
    find_parser.add_argument("--limit", type=int, default=5, help="сколько результатов показать")
    find_parser.add_argument("--json", action="store_true", help="вывод в JSON")

    bot_parser = subparsers.add_parser("bot", help="запустить Telegram-бота")
    bot_parser.add_argument(
        "--token",
        default=None,
        help="токен бота (по умолчанию из TELEGRAM_BOT_TOKEN)",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(verbose=bool(args.verbose))

    try:
        if args.command == "version":
            return _cmd_version()
        if args.command == "fetch":
            return _cmd_fetch(args)
        if args.command == "find":
            return _cmd_find(args)
        if args.command == "report":
            return _cmd_report(args)
        if args.command == "bot":
            return _cmd_bot(args)
    except CocktailError as exc:
        _fail(str(exc))
    except ValueError as exc:
        _fail(str(exc))
    except KeyboardInterrupt:
        print("\nПрервано", file=sys.stderr)
        return 130
    return 0


def _cmd_version() -> int:
    print(f"cocktail-bot {__version__}")
    return 0


def _cmd_fetch(args: argparse.Namespace) -> int:
    config = _config(snapshot_override=args.snapshot)
    snapshot_path = config.snapshot_path
    if snapshot_path.is_file() and not args.force:
        print(
            f"Ошибка: снапшот уже существует: {snapshot_path}. Перезаписать: --force",
            file=sys.stderr,
        )
        return 1

    letters = parse_letters(args.letters)
    print(f"Скачиваю каталог с {config.api_base_url} ({len(letters)} символов)...", file=sys.stderr)
    with CocktailDbClient(config.api_base_url, timeout=config.http_timeout) as client:
        drinks = crawl(client, letters, progress=bool(args.verbose))

    payload = build_snapshot(drinks, letters=letters, source=config.api_base_url)
    save_snapshot(snapshot_path, payload)
    print(f"Готово: {len(drinks)} напитков -> {snapshot_path}", file=sys.stderr)
    return 0


def _cmd_find(args: argparse.Namespace) -> int:
    config = _config(snapshot_override=args.snapshot)
    snapshot = load_snapshot(config.snapshot_path)
    cocktails = snapshot.cocktails()
    book = load_aliases(config.aliases_path)
    matcher = IngredientMatcher(book)

    have = [item.strip() for item in args.have.replace(";", ",").split(",") if item.strip()]
    results = find(
        cocktails,
        have,
        matcher=matcher,
        max_missing=args.max_missing,
        limit=args.limit,
    )

    if args.json:
        payload = [_match_to_dict(result) for result in results]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(_format_header(have, len(results), args.max_missing, len(cocktails)))
    for index, result in enumerate(results, start=1):
        print(_format_match(index, result))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    config = _config(snapshot_override=args.snapshot)
    snapshot = load_snapshot(config.snapshot_path)
    report = build_report(snapshot.cocktails(), top=args.top)

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print(_format_report(report))
    return 0


def _cmd_bot(args: argparse.Namespace) -> int:
    config = _config(snapshot_override=None)
    token = (args.token or config.telegram_token or "").strip()
    if not token:
        raise CocktailError(
            "Нужен токен Telegram. Получи его у @BotFather и положи в .env "
            "строкой TELEGRAM_BOT_TOKEN=..., либо передай флагом --token",
        )

    try:
        from cocktail.bot.app import run
    except ModuleNotFoundError as exc:
        raise CocktailError(
            'Для бота нужна зависимость aiogram: pip install -e ".[bot]"',
        ) from exc

    print(
        f"Бот запущен на {config.snapshot_path}. Остановить: Ctrl+C",
        file=sys.stderr,
    )
    run(token, config)
    return 0


def _config(snapshot_override: str | None) -> Config:
    config = Config.from_env()
    if snapshot_override is None:
        return config
    return Config(
        data_dir=config.data_dir,
        snapshot_path=Path(snapshot_override),
        aliases_path=config.aliases_path,
        api_base_url=config.api_base_url,
        http_timeout=config.http_timeout,
        telegram_token=config.telegram_token,
    )


def _format_header(have: Sequence[str], found: int, max_missing: int, total: int) -> str:
    suffix = f"не хватает не больше {max_missing}" if max_missing else "ничего не докупать"
    ingredients = ", ".join(have)
    return f"\nЕсть: {ingredients}\nУсловие: {suffix}\nНайдено {found} из {total} коктейлей.\n"


def _format_match(index: int, result: MatchResult) -> str:
    total = len(result.matched) + len(result.missing)
    lines = [
        f"{index}. {result.cocktail.name} - {len(result.matched)}/{total} ({result.coverage:.0%})",
        f"   есть: {', '.join(result.matched)}",
    ]
    if result.missing:
        lines.append(f"   нужно докупить: {', '.join(result.missing)}")
    return "\n".join(lines)


def _format_report(report: IngredientReport) -> str:
    lines = [
        "",
        f"Коктейлей: {report.cocktails}",
        f"Строк ингредиентов: {report.measures}",
        f"С количеством: {report.with_amount} ({report.amounts_ratio:.1%})",
        f"С единицей: {report.with_unit} ({report.units_ratio:.1%})",
        f"С пометкой (to taste / for garnish): {report.with_free_text}",
    ]
    if report.top_ingredients:
        lines.append("")
        lines.append("Частые ингредиенты:")
        for name, count in report.top_ingredients[:10]:
            lines.append(f"  {count:4d}  {name}")
    if report.unknown_units:
        lines.append("")
        lines.append("Строки без количества и единицы (первые 10):")
        for raw, count in report.unknown_units[:10]:
            lines.append(f"  {count:4d}  {raw}")
    return "\n".join(lines)


def _match_to_dict(result: MatchResult) -> dict[str, object]:
    cocktail = result.cocktail
    return {
        "id": cocktail.id,
        "name": cocktail.name,
        "coverage": round(result.coverage, 4),
        "matched": list(result.matched),
        "missing": list(result.missing),
        "glass": cocktail.glass,
        "category": cocktail.category,
        "alcoholic": cocktail.alcoholic,
        "instructions": cocktail.instructions,
    }


def _configure_logging(*, verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(message)s",
        stream=sys.stderr,
    )


def _fail(message: str) -> NoReturn:
    print(f"Ошибка: {message}", file=sys.stderr)
    raise SystemExit(1)


__all__ = ["build_parser", "main"]
