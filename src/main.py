from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from src.api.router import main_router
from src.db.qdrant.init_db import init_qdrant_collections, close_qdrant_client, get_qdrant_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    qdrant_client = await get_qdrant_client()
    await init_qdrant_collections(qdrant_client)
    yield
    await close_qdrant_client()


app = FastAPI(lifespan=lifespan)

app.include_router(router=main_router)

if __name__ == '__main__':
    uvicorn.run(app, port=8000, host="localhost", loop="uvloop")
