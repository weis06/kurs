from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import aiosqlite
from contextlib import asynccontextmanager
from aiohttp import ClientSession
import random


DATABASE = "jokes.db"

db = aiosqlite.connect(DATABASE)


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jokes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tgid INTEGER,
                secret TEXT,
                joketext TEXT
            )
        """)
        await db.commit()
        yield
    await db.close()


app = FastAPI(lifespan=lifespan)


class Joke(BaseModel):
    tgid: int
    secret: str
    joketext: str


class JokeFromApi(BaseModel):
    type: str
    setup: str
    punchline: str
    id: int


class JokeUpdate(BaseModel):
    tgid: int | None = None
    secret: str | None = None
    joketext: str | None = None


async def get_req():
    global req
    req = ClientSession()
    try:
        yield req
    finally:
        await req.close()


async def get_random_joke_from_api(req: ClientSession) -> str | None:
    async with req.get("https://official-joke-api.appspot.com/jokes/random") as resp:
        if resp.status == 200:
            j = JokeFromApi.model_validate(await resp.json())
            return f"{j.setup}\n\n\n{j.punchline}"
        return None


async def get_random_joke_user(db: aiosqlite.Connection) -> str | None:
    cursor = await db.execute("SELECT * FROM jokes ORDER BY RANDOM() LIMIT 1")
    joke = await cursor.fetchone()
    if joke is None:
        return None

    return joke[3]


@app.get("/randomjoke")
async def get_random_joke(req: ClientSession = Depends(get_req)):
    r = random.random()
    j = await (get_random_joke_from_api(req) if r < 0.5 else get_random_joke_user(db))
    if j is None:
        j = await (
            get_random_joke_from_api(req) if r > 0.5 else get_random_joke_user(db)
        )
    if j is None:
        raise HTTPException(status_code=404, detail="No jokes available")
    return {"result": j}


@app.get("/userjoke/{id}")
async def get_user_joke(id: int):
    cursor = await db.execute("SELECT * FROM jokes WHERE id = ?", (id,))
    joke = await cursor.fetchone()
    if joke is None:
        raise HTTPException(status_code=404, detail="Joke not found")
    return {"id": joke[0], "tgid": joke[1], "joketext": joke[3]}


@app.post("/userjoke")
async def create_user_joke(joke: Joke):
    cursor = await db.execute(
        "INSERT INTO jokes (tgid, secret, joketext) VALUES (?, ?, ?)",
        (joke.tgid, joke.secret, joke.joketext),
    )
    await db.commit()
    joke_id = cursor.lastrowid
    return {"result": "Joke added", "jokeid": joke_id}


@app.put("/userjoke/{id}")
async def update_user_joke(id: int, joke_update: JokeUpdate):
    cursor = await db.execute("SELECT * FROM jokes WHERE id = ?", (id,))
    joke = await cursor.fetchone()
    if joke is None:
        raise HTTPException(status_code=404, detail="Joke not found")

    updated_tgid = joke_update.tgid if joke_update.tgid is not None else joke[1]
    updated_secret = joke_update.secret if joke_update.secret is not None else joke[2]
    updated_joketext = (
        joke_update.joketext if joke_update.joketext is not None else joke[3]
    )

    await db.execute(
        "UPDATE jokes SET tgid = ?, secret = ?, joketext = ? WHERE id = ?",
        (updated_tgid, updated_secret, updated_joketext, id),
    )
    await db.commit()
    return {"result": "Joke updated"}


class Secret(BaseModel):
    secret: str


@app.delete("/userjoke/{id}")
async def delete_user_joke(id: int, secret: Secret):
    cursor = await db.execute("SELECT * FROM jokes WHERE id = ?", (id,))
    joke = await cursor.fetchone()
    if joke is None:
        raise HTTPException(status_code=404, detail="Joke not found")
    if joke[2] != secret.secret:
        raise HTTPException(status_code=403, detail="Incorrect secret")
    await db.execute("DELETE FROM jokes WHERE id = ?", (id,))
    await db.commit()
    return {"result": "Joke deleted"}
