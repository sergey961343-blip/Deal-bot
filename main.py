import asyncio
import logging
import os
import re
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from uuid import uuid4

load_dotenv()
logging.basicConfig(level=logging.INFO)

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher(storage=MemoryStorage())


def parse_number(text: str):
    cleaned = text.replace(" ", "").replace(",", ".")
    match = re.search(r"\d+\.?\d*", cleaned)
    if match:
        return float(match.group())
    return None


def format_number(number: float) -> str:
    return f"{number:,.3f}".replace(",", " ").replace(".", ",")


def try_parse(text: str):
    parts = text.strip().split()
    if len(parts) < 4:
        return None

    rate = parse_number(parts[0])
    amount = parse_number(parts[-1])

    if not rate or not amount or rate <= 0 or amount <= 0:
        return None

    requisites = parts[1]
    bank = " ".join(parts[2:-1])

    return rate, requisites, bank, amount


@dp.inline_query()
async def inline_calc(query: InlineQuery):
    parsed = try_parse(query.query)

    if not parsed:
        return

    rate, req, bank, amount = parsed
    result = amount / rate

    text = (
        "✅ Сделка рассчитана\n"
        f"🏦 Банк: {bank}\n"
        f"💳 Реквизит: {req}\n"
        f"📈 Курс: {format_number(rate)}\n"
        f"💰 Сумма: {format_number(amount)}\n"
        f"🧮 {format_number(amount)} / {format_number(rate)} = {format_number(result)}"
    )

    await query.answer(
        results=[
            InlineQueryResultArticle(
                id=str(uuid4()),
                title="Рассчитать сделку",
                input_message_content=InputTextMessageContent(message_text=text),
            )
        ],
        cache_time=1
    )


@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 Напиши в любом чате:\n\n"
        "@Calculat3Bot 76 2200701002300314 Тинь 36500"
    )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
