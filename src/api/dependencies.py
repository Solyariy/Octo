from typing import Annotated

import aiohttp
from fastapi import Depends, Request

from src.db.postgres.manager import PostgresManager
from src.db.qdrant.manager import QdrantManager
from src.embedders.managers.omni_manager import OmniEmbeddingManager


async def get_aiohttp_client(request: Request) -> aiohttp.ClientSession:
    return request.app.state.aiohttp_client


async def get_embedder(request: Request) -> OmniEmbeddingManager:
    return request.app.state.embedder


async def get_qdrant_manager(request: Request) -> QdrantManager:
    return QdrantManager(request.app.state.qdrant_client)


async def get_postgres_manager(request: Request) -> PostgresManager:
    return PostgresManager(request.app.state.postgres_sessionmaker)


AiohttpClientDep = Annotated[aiohttp.ClientSession, Depends(get_aiohttp_client)]
EmbedderDep = Annotated[OmniEmbeddingManager, Depends(get_embedder)]
QdrantManagerDep = Annotated[QdrantManager, Depends(get_qdrant_manager)]
PostgresManagerDep = Annotated[PostgresManager, Depends(get_postgres_manager)]
