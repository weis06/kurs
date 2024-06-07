import asyncio
import logging
import sys
from os import getenv

from aiogram.filters import Command, CommandObject, CommandStart
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

import aiohttp

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
TOKEN = "7489322861:AAEuYx1ruXbTyGCHPW8vTq54twyOVhdDKV4"
API_URL = "http://localhost:8000"

bot = Bot(token=TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """Handles the /start command"""
    await message.answer("Welcome to the Joke Bot!")


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
    try:
        joke_id = int(command.args)
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_URL}/userjoke/{joke_id}") as response:
                if response.status == 200:
                    joke = await response.json()
                    await message.answer(joke["joketext"])
                else:
                    await message.answer("Joke not found.")
    except ValueError:
        await message.answer("Please provide a valid joke ID.")


@dp.message(Command(commands="add"))
async def add_joke_handler(message: Message, command: CommandObject) -> None:
    """Handles the /add command to add a new joke"""
    try:
        joke_text = command.args
        if not joke_text:
            await message.answer("Please provide a joke text.")
            return

        user_id = message.from_user.id
        secret = "user_secret"  # Ideally, this should be securely handled

        async with aiohttp.ClientSession() as session:
            payload = {"tgid": user_id, "secret": secret, "joketext": joke_text}
            async with session.post(f"{API_URL}/userjoke", json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    await message.answer(f"Joke added with ID: {result['jokeid']}")
                else:
                    await message.answer("Failed to add joke.")
    except:
        await message.answer("Failed to add joke.")


@dp.message(Command(commands="change"))
async def change_joke_handler(message: Message, command: CommandObject) -> None:
    """Handles the /change command to update an existing joke"""
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

        user_id = message.from_user.id
        secret = "user_secret"  # Ideally, this should be securely handled

        async with aiohttp.ClientSession() as session:
            payload = {"tgid": user_id, "secret": secret, "joketext": new_joke_text}
            async with session.put(
                f"{API_URL}/userjoke/{joke_id}", json=payload
            ) as response:
                if response.status == 200:
                    await message.answer("Joke updated.")
                else:
                    await message.answer("Failed to update joke.")
    except:
        await message.answer("Failed to update joke.")


@dp.message(Command(commands=["delete"]))
async def delete_joke_handler(message: Message, command: CommandObject) -> None:
    """Handles the /delete command to delete a joke by ID"""
    try:
        args = command.args.split()
        if len(args) != 2:
            await message.answer("Please provide a joke ID and secret.")
            return

        try:
            joke_id = int(args[0])
            secret = args[1]
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
                    await message.answer(f"Failed to delete joke.\n{await response.text()}")
    except:
        await message.answer("Failed to delete joke.")

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    with asyncio.Runner() as r:
        r.run(main())
