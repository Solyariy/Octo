import uvicorn
from fastapi import FastAPI, Response
from pydantic import BaseModel, HttpUrl

app = FastAPI()


class SaveData(BaseModel):
    type: str
    data: str


@app.get("/", status_code=200)
async def get_info():
    return dict(ok=True)


@app.post(
    "/save",
    status_code=201
)
async def post_save(
        data: SaveData
):
    print("Accepted data", data)
    return Response(status_code=201)


@app.post(
    "/save/all",
    status_code=201
)
async def post_save(
        data: list[SaveData]
):
    print("Accepted data", data)
    return Response(status_code=201)


if __name__ == '__main__':
    uvicorn.run(app, port=8000, host="localhost", loop="uvloop")
