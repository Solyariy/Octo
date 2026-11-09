import asyncio
from contextlib import AsyncExitStack, asynccontextmanager

import aiohttp
import uvicorn
from fastapi import FastAPI

from src.api.auth.router import auth_router
from src.api.middleware import trace_requests
from src.api.router import main_router
from src.db.postgres.init_db import postgres_lifespan
from src.db.qdrant.init_db import init_qdrant_collections, qdrant_client_lifespan
from src.embedders.factory import get_embedding_manager
from src.services.omni_pipeline import OmniPipeline
from src.utils.logs import Logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Single owner for every connection.

    AsyncExitStack unwinds in exact reverse order on any exception, including one
    raised out of `yield`, so a failure part-way through startup cannot leak an
    already-created client.
    """
    async with AsyncExitStack() as stack:
        engine, session_factory = await stack.enter_async_context(postgres_lifespan())
        qdrant_client = await stack.enter_async_context(qdrant_client_lifespan())
        await init_qdrant_collections(qdrant_client)
        aiohttp_client = await stack.enter_async_context(aiohttp.ClientSession())

        # Loaded once and shared by the pipeline and search; downloads on first boot.
        embedder = get_embedding_manager(OmniPipeline.EMBEDDER)
        stack.callback(embedder.unload)
        await asyncio.to_thread(embedder.load_model)
        Logger.info("Embedder loaded", embedder=OmniPipeline.EMBEDDER.value)

        app.state.postgres_engine = engine
        app.state.postgres_sessionmaker = session_factory
        app.state.qdrant_client = qdrant_client
        app.state.aiohttp_client = aiohttp_client
        app.state.embedder = embedder

        yield


app = FastAPI(lifespan=lifespan)
app.middleware("http")(trace_requests)

app.include_router(router=main_router)
app.include_router(router=auth_router, prefix="/auth", tags=["Auth"])

if __name__ == '__main__':
    uvicorn.run(app, port=8000, host="localhost", loop="uvloop")
