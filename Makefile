# Удобные команды разработки. На Windows без make используй те же команды
# напрямую через .venv\Scripts\python.exe - они все в README.

ifeq ($(OS),Windows_NT)
	VENV_PY := .venv/Scripts/python.exe
else
	VENV_PY := .venv/bin/python
endif

PYTHON ?= $(VENV_PY)

.DEFAULT_GOAL := help
.PHONY: help venv install lint format typecheck test test-cov check fetch find report clean

help: ## Показать список команд
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

venv: ## Создать виртуальное окружение
	python -m venv .venv

install: ## Установить пакет с dev-зависимостями (editable)
	$(PYTHON) -m pip install -e ".[dev]"

lint: ## Проверить стиль и импорты
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format: ## Отформатировать код
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check --fix .

typecheck: ## Строгая проверка типов
	$(PYTHON) -m mypy

test: ## Запустить тесты
	$(PYTHON) -m pytest

test-cov: ## Тесты с покрытием
	$(PYTHON) -m pytest --cov=cocktail --cov-report=term-missing

check: lint typecheck test ## Всё сразу - то, что должен проходить CI

fetch: ## Скачать снапшот каталога
	$(PYTHON) -m cocktail fetch

report: ## Отчёт о качестве данных
	$(PYTHON) -m cocktail report

find: ## Пример поиска (переопредели HAVE="..." при вызове)
	$(PYTHON) -m cocktail find --have "$(or $(HAVE),джин, лайм, тоник)"

clean: ## Удалить кэши
	rm -rf .ruff_cache .mypy_cache .pytest_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
