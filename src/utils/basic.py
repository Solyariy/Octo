from pathlib import Path
import aiofiles

import aiohttp


async def download_file(url: str, aiohttp_client: aiohttp.ClientSession) -> bytes:
    async with aiohttp_client.get(
            url=url,
            headers={"User-Agent": "octo-smoke-test/0.1"},
            raise_for_status=True
    ) as response:
        data = await response.read()
        return data


async def download_and_save_file(
        url: str,
        destination: Path,
        aiohttp_client: aiohttp.ClientSession
):
    async with aiohttp_client.get(
            url=url,
            headers={"User-Agent": "octo-smoke-test/0.1"},
            raise_for_status=True
    ) as response, aiofiles.open(destination, "wb") as file:
        async for data in response.content.iter_chunked(1024):
            await file.write(data)
    return destination