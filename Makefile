.DEFAULT_GOAL := help
.PHONY: help install format lint test live

help:
	@echo install - install dependencies and git hooks
	@echo format  - format code and apply safe lint fixes
	@echo lint    - check formatting, lint rules and types
	@echo test    - run tests with coverage
	@echo live    - scan the public pages in live/targets.txt

install:
	poetry sync --all-extras
	poetry run pre-commit install

format:
	poetry run ruff format .
	poetry run ruff check --fix .

lint:
	poetry run ruff format --check .
	poetry run ruff check .
	poetry run mypy

test:
	poetry run pytest --cov

live:
	-poetry run allymend scan --format markdown --output live/report.md @live/targets.txt
