import asyncio
import logging
import sys
from os import getenv
import string
import random


from aiogram.filters import Command, CommandObject, CommandStart
from aiogram import Bot, Dispatcher, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
import aiosqlite
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder

import aiohttp

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
TOKEN = "7489322861:AAEuYx1ruXbTyGCHPW8vTq54twyOVhdDKV4"
API_URL = "http://localhost:8000"

bot = Bot(token=TOKEN)
dp = Dispatcher()


class MState(StatesGroup):
    add = State()
    change_id = State()
    change_text = State()
    delete = State()


async def on_startup():
    db = await aiosqlite.connect("bot.db")
    dp["db"] = db
    await db.execute("""
    CREATE TABLE IF NOT EXISTS users (
        uid INTEGER PRIMARY KEY,
        secret TEXT
    )
    """)
    await db.commit()


async def on_shutdown():
    await dp["db"].close()


async def register_user(db: aiosqlite.Connection, user_id: int, secret: str) -> None:
    async with db.execute(
        "INSERT OR IGNORE INTO users (uid, secret) VALUES (?, ?)", (user_id, secret)
    ):
        await db.commit()


async def get_user_secret(db: aiosqlite.Connection, user_id: int) -> str:
    async with await db.execute(
        "SELECT secret FROM users WHERE uid = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if row:
            return row[0]
        raise ValueError()


@dp.message(CommandStart())
async def start_handler(message: Message, db: aiosqlite.Connection) -> None:
    """Handles the /start command"""
    secret = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    assert message.from_user is not None
    await register_user(db, message.from_user.id, secret)
    builder = ReplyKeyboardBuilder()
    builder.button(text="Random 🎲")
    builder.button(text="Add +")
    builder.button(text="Change +-")
    builder.button(text="Delete -")
    builder.adjust(1)
    m = builder.as_markup()
    m.resize_keyboard = True
    await message.answer("Welcome to the Joke Bot!", reply_markup=m)


@dp.message(F.text == "Add +")
async def add_reply(message: Message, state: FSMContext):
    await state.set_state(MState.add)
    await message.answer("Input joke text")


@dp.message(MState.add)
async def add_reply_finish(
    message: Message, db: aiosqlite.Connection, state: FSMContext
):
    assert message.from_user is not None
    assert message.text is not None
    user_id = message.from_user.id
    secret = await get_user_secret(db, user_id)

    try:
        async with aiohttp.ClientSession() as session:
            payload = {"tgid": user_id, "secret": secret, "joketext": message.text}
            async with session.post(f"{API_URL}/userjoke", json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    await message.answer(f"Joke added with ID: {result['jokeid']}")
                else:
                    await message.answer("Failed to add joke.")
    except Exception:
        await message.answer("Failed to add joke.")
    finally:
        await state.clear()


@dp.message(F.text == "Change +-")
async def change_reply(message: Message, state: FSMContext):
    await state.set_state(MState.change_id)
    await message.answer("Input id of a joke")


@dp.message(MState.change_id)
async def change_reply_id(message: Message, state: FSMContext):
    assert message.text is not None
    if message.text.isdigit():
        await state.update_data(id=int(message.text))
        await message.answer("Input new joke text")
        await state.set_state(MState.change_text)
        return

    await message.answer("Id must be numeric!")


@dp.message(MState.change_text)
async def change_reply_text(
    message: Message, db: aiosqlite.Connection, state: FSMContext
):
    assert message.text is not None
    assert message.from_user is not None

    d = await state.get_data()
    try:
        user_id = message.from_user.id
        secret = await get_user_secret(db, user_id)

        async with aiohttp.ClientSession() as session:
            payload = {"tgid": user_id, "secret": secret, "joketext": message.text}
            async with session.put(
                f"{API_URL}/userjoke/{d["id"]}", json=payload
            ) as response:
                if response.status == 200:
                    await message.answer("Joke updated.")
                else:
                    await message.answer("Failed to update joke.")
    except Exception:
        await message.answer("Failed to update joke.")
    finally:
        await state.clear()


@dp.message(F.text == "Delete -")
async def remove_reply(message: Message, state: FSMContext):
    await state.set_state(MState.delete)
    await message.answer("Input joke id")


@dp.message(MState.delete)
async def remove_reply_finish(
    message: Message, db: aiosqlite.Connection, state: FSMContext
):
    assert message.text is not None
    assert message.from_user is not None
    if not message.text.isdigit():
        await message.answer("Id must be numeric!")
        return

    secret = await get_user_secret(db, message.from_user.id)

    try:
        async with aiohttp.ClientSession() as session:
            payload = {"secret": secret}
            async with session.delete(
                f"{API_URL}/userjoke/{message.text}", json=payload
            ) as response:
                if response.status == 200:
                    await message.answer("Joke deleted.")
                else:
                    await message.answer(
                        f"Failed to delete joke.\n{await response.text()}"
                    )
    except Exception:
        await message.answer("Failed to delete joke.")


@dp.message(Command("cancel"))
@dp.message(F.text.casefold() == "cancel")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    """
    Allow user to cancel any action
    """
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.clear()
    await message.answer("Cancelled.")


@dp.message(F.text == "Random 🎲")
@dp.message(Command("random"))
async def random_joke_handler(message: Message) -> None:
    """Handles the /random command to fetch a random joke"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_URL}/randomjoke") as response:
            if response.status == 200:
                joke = await response.json()
                await message.answer(joke["result"])
            else:
                await message.answer("No jokes available right now.")


@dp.message(Command(commands="user"))
async def user_joke_handler(message: Message, command: CommandObject) -> None:
    """Handles the /user command to fetch a specific joke by ID"""
    if command.args is None or not command.args.isdigit():
        await message.answer("Please provide a valid joke ID.")
        return

    joke_id = int(command.args)
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_URL}/userjoke/{joke_id}") as response:
            if response.status == 200:
                joke = await response.json()
                await message.answer(joke["joketext"])
            else:
                await message.answer("Joke not found.")


@dp.message(Command(commands="add"))
async def add_joke_handler(
    message: Message, command: CommandObject, db: aiosqlite.Connection
) -> None:
    """Handles the /add command to add a new joke"""
    joke_text = command.args
    if not joke_text:
        await message.answer("Please provide a joke text.")
        return

    assert message.from_user is not None
    user_id = message.from_user.id
    secret = await get_user_secret(db, user_id)

    try:
        async with aiohttp.ClientSession() as session:
            payload = {"tgid": user_id, "secret": secret, "joketext": joke_text}
            async with session.post(f"{API_URL}/userjoke", json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    await message.answer(f"Joke added with ID: {result['jokeid']}")
                else:
                    await message.answer("Failed to add joke.")
    except Exception:
        await message.answer("Failed to add joke.")


@dp.message(Command(commands="change"))
async def change_joke_handler(
    message: Message, command: CommandObject, db: aiosqlite.Connection
) -> None:
    """Handles the /change command to update an existing joke"""
    if command.args is None:
        await message.answer("Please provide a joke ID and new joke text.")
        return

    try:
        args = command.args.split(maxsplit=1)
        if len(args) != 2:
            await message.answer("Please provide a joke ID and new joke text.")
            return

        try:
            joke_id = int(args[0])
            new_joke_text = args[1]
        except ValueError:
            await message.answer("Please provide a valid joke ID.")
            return

        assert message.from_user is not None
        user_id = message.from_user.id
        secret = await get_user_secret(db, user_id)

        async with aiohttp.ClientSession() as session:
            payload = {"tgid": user_id, "secret": secret, "joketext": new_joke_text}
            async with session.put(
                f"{API_URL}/userjoke/{joke_id}", json=payload
            ) as response:
                if response.status == 200:
                    await message.answer("Joke updated.")
                else:
                    await message.answer("Failed to update joke.")
    except Exception:
        await message.answer("Failed to update joke.")


@dp.message(Command(commands=["delete"]))
async def delete_joke_handler(
    message: Message, db: aiosqlite.Connection, command: CommandObject
) -> None:
    """Handles the /delete command to delete a joke by ID"""
    try:
        try:
            joke_id = int(command.args)
            secret = await get_user_secret(db, message.from_user.id)
        except ValueError:
            await message.answer("Please provide a valid joke ID and secret.")
            return

        async with aiohttp.ClientSession() as session:
            payload = {"secret": secret}
            async with session.delete(
                f"{API_URL}/userjoke/{joke_id}", json=payload
            ) as response:
                if response.status == 200:
                    await message.answer("Joke deleted.")
                else:
                    await message.answer(
                        f"Failed to delete joke.\n{await response.text()}"
                    )
    except Exception:
        await message.answer("Failed to delete joke.")


async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await dp.start_polling(bot)


if __name__ == "__main__":
    with asyncio.Runner() as r:
        r.run(main())
