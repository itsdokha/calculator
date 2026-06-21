# compose v2 (`docker compose`) по умолчанию; для v1 — `make up DC=docker-compose`
DC ?= docker compose

.PHONY: help install test up down logs migrate seed shell

help:
	@echo "install  - установить зависимости"
	@echo "test     - прогнать тесты"
	@echo "up       - поднять стек (app+postgres+redis)"
	@echo "down     - остановить стек"
	@echo "logs     - логи приложения"
	@echo "migrate  - сгенерировать и применить миграции (внутри контейнера app)"
	@echo "seed     - импорт справочников"

install:
	pip install -r requirements.txt

test:
	pytest -q

up:
	$(DC) up -d --build

down:
	$(DC) down

logs:
	$(DC) logs -f app

migrate:
	$(DC) exec app flask db upgrade

seed:
	$(DC) exec app flask seed

shell:
	$(DC) exec app bash
