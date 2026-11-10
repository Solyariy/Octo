COMPOSE := docker compose

.DEFAULT_GOAL := help

.PHONY: help up down restart logs ps migrate migration admin seed smoke db-shell db-reset cli

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-15s %s\n", $$1, $$2}'

up: ## Start postgres + qdrant detached, then run the API locally on :8000
	$(COMPOSE) up --detach --wait postgres qdrant
	uv run python -m src.main

down: ## Stop the stack, keep the stored data
	$(COMPOSE) down

restart: down up ## down + up

logs: ## Follow logs; service=<name> to filter
	$(COMPOSE) logs --follow $(service)

ps: ## Show service status
	$(COMPOSE) ps --all

migrate: ## Run alembic upgrade head
	uv run alembic upgrade head

migration: ## Create an Alembic revision; requires name=<slug>, optional rev=<id>
	@test -n "$(name)" || (echo "usage: make migration name=<slug> [rev=<id>]" && exit 1)
	uv run alembic revision --autogenerate -m "$(name)" $(if $(rev),--rev-id "$(rev)")

admin: ## Upsert the admin user (testing only); args="--email ... --password ..."
	uv run python -m cli.postgres $(args)

seed: ## Insert seed post urls as PENDING for the admin user; optional file=<path> (default cli/seed_urls.txt), args="--email ..."
	uv run python -m cli.seeder $(if $(file),--file "$(file)") $(args)

smoke: ## Call GET /health on the local API (server must be up)
	curl -fsS http://localhost:8123/health
	@echo

db-shell: ## Open psql in the postgres container
	$(COMPOSE) exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

# store=pg|qdrant limits db-reset to one store; both when unset
DB_RESET_STORES := $(if $(store),$(store),pg qdrant)

db-reset: ## DESTRUCTIVE: wipe postgres + qdrant data (store=pg|qdrant for one), re-run migrations
ifneq ($(filter pg,$(DB_RESET_STORES)),)
	$(COMPOSE) rm -sf postgres
	docker volume rm -f $$($(COMPOSE) config | sed -n 's/^name: //p')_pgdata
	$(COMPOSE) up --detach --wait postgres
	uv run alembic upgrade head
endif
ifneq ($(filter qdrant,$(DB_RESET_STORES)),)
	$(COMPOSE) rm -sf qdrant
	rm -rf qdrant_data
	$(COMPOSE) up --detach --wait qdrant
endif

# `make cli <instagram|threads|link|youtube> "<url>" [args="--out raw.json"]` runs the matching scraper smoke script
CLI_MODULE_instagram := cli.instagram_graphql
CLI_MODULE_threads := cli.threads
CLI_MODULE_link := cli.link_scraper
CLI_MODULE_youtube := cli.youtube
CLI_PLATFORM := $(word 2,$(MAKECMDGOALS))
CLI_URL := $(wordlist 3,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))

cli: ## Run a scraper script: make cli <instagram|threads|link|youtube> "<url>" [args=...]
	@test -n "$(CLI_MODULE_$(CLI_PLATFORM))" && test -n "$(CLI_URL)" || \
		{ echo 'usage: make cli <instagram|threads|link|youtube> "<url>" [args="--out raw.json"]'; exit 1; }
	uv run python -m $(CLI_MODULE_$(CLI_PLATFORM)) '$(CLI_URL)' $(args)

# The platform and url are arguments for `make cli`, not standalone targets
ifeq ($(firstword $(MAKECMDGOALS)),cli)
%:
	@:
endif
