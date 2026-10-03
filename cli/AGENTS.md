# cli DOX

## Purpose

- Hand-run CLI and smoke-test scripts that exercise `src` code from the terminal; nothing here is imported by the service

## Ownership

- `instagram_graphql.py` — fetches a reel/post via `src.link_scrapers.instagram_graphql.fetch_reel`, prints it, saves the video to `main_settings.INSTAGRAM_TEMP_DIR_PATH / "test.mp4"` (does not create the directory), `--out` dumps the raw JSON
- `threads.py` — fetches a post via `src.link_scrapers.threads.fetch_post`, prints it, downloads media to `main_settings.THREADS_TEMP_DIR_PATH / <shortcode>` (created) unless `--no-download`, `--out` dumps the raw post JSON
- `qwen.py` — loads `QWEN3_4B`, encodes three passages, exits non-zero if the paraphrase pair is not more similar than the unrelated pair
- `nvidia_cosmos.py` — downloads a sample clip, embeds it and six captions through `CosmosEmbeddingManager`, exits non-zero if vectors are not `output_dim`-wide or the expected caption does not rank first; its `download_video` is a smoke-test helper, production downloads belong in `src.utils.basic`
- `embedder_registry.py` — prints every `EmbeddersEnum` member's backend, dim and load kwargs

## Local Contracts

- One script per file, named after the `src` module or model it exercises, run as `uv run python -m cli.<name>` from the repository root
- CLI entrypoints (`argparse`, `main()`, `if __name__ == "__main__"`) live here, never in `src`; `src` modules expose only library functions these scripts call
- Scripts import `src` with absolute imports and may open their own `aiohttp.ClientSession`; `print` is the output channel here
- Smoke scripts return an exit code from `main() -> int` (`raise SystemExit(main())`); they are not pytest cases

## Work Guidance

## Verification

- `uv run python -m cli.embedder_registry`
- `uv run python -m cli.qwen`
- `uv run python -m cli.nvidia_cosmos`
- `uv run python -m cli.instagram_graphql <reel-url> [--out raw.json]`
- `uv run python -m cli.threads <post-url-or-shortcode> [--out raw.json] [--no-download]`
- `make cli <instagram|threads> "<url>" [ARGS="..."]` is the root `Makefile` shortcut for the two scraper scripts above; a new scraper script needs a `CLI_MODULE_<platform>` line there

## Child DOX Index
