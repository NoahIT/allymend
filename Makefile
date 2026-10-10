.DEFAULT_GOAL := help
.PHONY: help install format lint test

help:
	@echo install - install dependencies and git hooks
	@echo format  - format code and apply safe lint fixes
	@echo lint    - check formatting, lint rules and types
	@echo test    - run tests with coverage

install:
	poetry sync
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
