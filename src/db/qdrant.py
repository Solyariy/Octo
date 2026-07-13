from pydantic_settings import BaseSettings
from qdrant_client import AsyncQdrantClient


class Settings(BaseSettings):
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_prefer_grpc: bool = False

    model_config = {"env_prefix": ""}


settings = Settings()

client: AsyncQdrantClient | None = None


async def get_client() -> AsyncQdrantClient:
    """Get or create the shared async Qdrant client."""
    global client
    if client is None:
        client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            prefer_grpc=settings.qdrant_prefer_grpc,
        )
    return client


async def close_client() -> None:
    """Close the shared async Qdrant client if it exists."""
    global client
    if client is not None:
        await client.close()
        client = None
