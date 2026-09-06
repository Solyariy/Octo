from contextlib import asynccontextmanager

import uvicorn
import aiohttp
from fastapi import FastAPI

from src.api.router import main_router
from src.db.qdrant.init_db import init_qdrant_collections, close_qdrant_client, get_qdrant_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    qdrant_client = await get_qdrant_client()
    await init_qdrant_collections(qdrant_client)
    app.state.qdrant_client = qdrant_client

    aiohttp_client = aiohttp.ClientSession()
    app.state.aiohttp_client = aiohttp_client

    yield
    await aiohttp_client.close()
    await close_qdrant_client()


app = FastAPI(lifespan=lifespan)

app.include_router(router=main_router)

if __name__ == '__main__':
    uvicorn.run(app, port=8000, host="localhost", loop="uvloop")
