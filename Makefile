.PHONY: server clear pg qdrant

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
