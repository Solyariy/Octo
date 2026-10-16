# src/db/qdrant DOX

## Purpose

- Vector storage for embeddings, one Qdrant collection per embedding model

## Ownership

- `init_db.py` — `build_qdrant_client()`, the `qdrant_client_lifespan()` async CM, `init_qdrant_collections()`, `QdrantCollectionMismatchError`
- `models.py` — `RegisteredCollection`, `QdrantCollection`, the `QDRANT_COLLECTIONS` registry (`cosmos_zero`, `gemma2_omni`), `get_collection(embedder)` and `PAYLOAD_INDEX_FIELDS`
- `schemas.py` — `QdrantVector`: one point (`post_id`, `platform`, `modality`, `media_index`, `vector`), its deterministic `point_id` and its `payload(user_id)`
- `manager.py` — `QdrantManager`

## Local Contracts

- Settings: `QDRANT_URL`, `QDRANT_PREFER_GRPC`, `QDRANT_API_KEY`, `QDRANT_TIMEOUT`, `QDRANT_POOL_SIZE`, `QDRANT_CHECK_COMPATIBILITY` in `db_settings`. Storage is bind-mounted to `./qdrant_data`
- `QdrantManager` takes an already-built `AsyncQdrantClient`: the app passes the one from `app.state`
- `qdrant_client_lifespan()` is app-scoped — never enter it inside a request. `AsyncQdrantClient` is not itself an async context manager, which is why the wrapper exists
- `QDRANT_COLLECTIONS` is keyed by `EmbeddersEnum` (look one up with `get_collection`), and each collection is sized from `member.get_dim()` — never a literal
- `RegisteredCollection` must stay a `StrEnum`: a `(str, Enum)` member stringifies as `RegisteredCollection.MEMBER` on Python 3.12+ and the client then creates and queries a collection under that name
- Point payload is `{user_id, platform, post_id, modality, media_index}` with UUIDs as strings; `user_id`, `post_id`, `platform` and `modality` get `KEYWORD` indexes when a collection is created (existing collections are not back-filled). Point ids are `uuid5(post_id:modality:media_index)`, so re-processing a post overwrites its points
- `init_qdrant_collections()` creates what is missing and validates what exists; it **never deletes**. A size/distance mismatch raises `QdrantCollectionMismatchError` and aborts startup so the operator migrates deliberately. There must be no `delete_collection` call anywhere in this package
- Pass `vectors_config=` a real `VectorParams`, never `**collection.model_dump()`: a flattened dump reaches the gRPC path as a *named-vectors* mapping and dies in `RestToGrpc.convert_vectors_config`
- Catch collection-creation failures on both `UnexpectedResponse` and `grpc.RpcError`, then re-probe `collection_exists()` instead of matching a status code — that distinguishes a lost create race between gunicorn workers from a spec the server rejected

## Work Guidance

- `find_similar` filters by `user_id` but has no route since `/find` was removed; a new search route must embed its query with the collection's own embedder

## Verification

- Plant a mismatched `cosmos_zero` (`size 512`, `Cosine`), start the app, and confirm it exits non-zero with `QdrantCollectionMismatchError` and leaves the collection untouched
