# src/db/qdrant DOX

## Purpose

- Vector storage for embeddings, one Qdrant collection per embedding model

## Ownership

- `init_db.py` — `build_qdrant_client()`, the `qdrant_client_lifespan()` async CM, `init_qdrant_collections()`, `QdrantCollectionMismatchError`
- `models.py` — `QdrantCollection` and the `QDRANT_COLLECTIONS` registry
- `schemas.py` — `QdrantVector`, an empty placeholder model
- `manager.py` — `QdrantManager`

## Local Contracts

- Settings: `QDRANT_URL`, `QDRANT_PREFER_GRPC`, `QDRANT_API_KEY`, `QDRANT_TIMEOUT`, `QDRANT_POOL_SIZE`, `QDRANT_CHECK_COMPATIBILITY` in `db_settings`. Storage is bind-mounted to `./qdrant_data`
- `QdrantManager` takes an already-built `AsyncQdrantClient`: the app passes the one from `app.state`
- `qdrant_client_lifespan()` is app-scoped — never enter it inside a request. `AsyncQdrantClient` is not itself an async context manager, which is why the wrapper exists
- `QDRANT_COLLECTIONS` is keyed by `EmbeddersEnum`, and each collection is sized from `member.get_dim()` — never a literal
- `init_qdrant_collections()` creates what is missing and validates what exists; it **never deletes**. A size/distance mismatch raises `QdrantCollectionMismatchError` and aborts startup so the operator migrates deliberately. There must be no `delete_collection` call anywhere in this package
- Pass `vectors_config=` a real `VectorParams`, never `**collection.model_dump()`: a flattened dump reaches the gRPC path as a *named-vectors* mapping and dies in `RestToGrpc.convert_vectors_config`
- Catch collection-creation failures on both `UnexpectedResponse` and `grpc.RpcError`, then re-probe `collection_exists()` instead of matching a status code — that distinguishes a lost create race between gunicorn workers from a spec the server rejected

## Work Guidance

- `QdrantManager.upsert_vectors` stores bare vectors under random ids with no payload, so points carry no link back to `media_files`. Adding that payload is the prerequisite for any search or delete-by-source feature

## Verification

- Plant a mismatched `cosmos_zero` (`size 512`, `Cosine`), start the app, and confirm it exits non-zero with `QdrantCollectionMismatchError` and leaves the collection untouched
