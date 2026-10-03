.PHONY: server clear pg qdrant cli

# `make clear` wipes both stores; `make clear pg` / `make clear qdrant` wipes one
CLEAR_TARGETS := $(filter pg qdrant,$(MAKECMDGOALS))
ifeq ($(CLEAR_TARGETS),)
CLEAR_TARGETS := pg qdrant
endif

server:
	docker compose up -d --wait postgres qdrant
	uv run python -m src.main

clear:
ifneq ($(filter pg,$(CLEAR_TARGETS)),)
	docker compose rm -sf postgres
	docker volume rm -f $$(docker compose config | sed -n 's/^name: //p')_pgdata
endif
ifneq ($(filter qdrant,$(CLEAR_TARGETS)),)
	docker compose rm -sf qdrant
	rm -rf qdrant_data
endif

# Arguments for `make clear`, not standalone targets
pg qdrant:
	@:

# `make cli <platform> <url> [ARGS="--out raw.json"]` runs `cli.<platform>` (the scraper smoke scripts); quote the url
CLI_MODULE_instagram := cli.instagram_graphql
CLI_MODULE_threads := cli.threads
CLI_PLATFORM := $(word 2,$(MAKECMDGOALS))
CLI_URL := $(wordlist 3,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))

cli:
	@test -n "$(CLI_MODULE_$(CLI_PLATFORM))" && test -n "$(CLI_URL)" || \
		{ echo 'usage: make cli <instagram|threads> "<url>" [ARGS="--out raw.json"]'; exit 1; }
	uv run python -m $(CLI_MODULE_$(CLI_PLATFORM)) '$(CLI_URL)' $(ARGS)

# The platform and url are arguments for `make cli`, not standalone targets
ifeq ($(firstword $(MAKECMDGOALS)),cli)
%:
	@:
endif
