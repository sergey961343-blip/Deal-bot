import asyncio
import logging
import os
import re

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# ====== CONFIG ======
load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Add it to Render Environment Variables.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

HELP_TEXT = (
    "🧮 Формат (одним сообщением, 4 строки):\n\n"
    "1) Курс (пример: 76 / 76.5 / 76,5 / '76 курс')\n"
    "2) Реквизит (любой текст)\n"
    "3) Банк (любой текст)\n"
    "4) Сумма (пример: 36500 / 36 500)\n\n"
    "Пример:\n"
    "76 курс\n"
    "2200701002300314\n"
    "Тинь\n"
    "36500"
)

# ====== HELPERS ======
def parse_number(text: str) -> float | None:
    """Extract first number from text. Supports spaces and comma as decimal separator."""
    cleaned = text.strip().replace(" ", "").replace(",", ".")
    m = re.search(r"\d+(\.\d+)?", cleaned)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def format_number(n: float) -> str:
    """Format with space thousands separator and comma decimal separator, 3 decimals."""
    return f"{n:,.3f}".replace(",", " ").replace(".", ",")


def try_parse_4_lines(text: str):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) != 4:
        return None

    rate_raw, req, bank, amount_raw = lines
    rate = parse_number(rate_raw)
    amount = parse_number(amount_raw)

    if rate is None or amount is None:
        return None
    if rate <= 0 or amount <= 0:
        return None

    return rate, req, bank, amount


# ====== HANDLERS ======
@dp.message(Command("start"))
@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT)


@dp.message(F.text)
async def one_message_calc(message: Message):
    parsed = try_parse_4_lines(message.text)
    if not parsed:
        await message.answer(
            "❌ Не понял формат.\n\n"
            f"{HELP_TEXT}\n\n"
            "Отправь данные одним сообщением в 4 строки."
        )
        return

    rate, req, bank, amount = parsed
    result = amount / rate

    text = (
        "✅ Сделка рассчитана\n"
        f"🏦 Банк: {bank}\n"
        f"💳 Реквизит: {req}\n"
        f"📈 Курс: {format_number(rate)}\n"
        f"💰 Сумма: {format_number(amount)}\n"
        f"🧮 {format_number(amount)} / {format_number(rate)} = {format_number(result)}\n\n"
        "Для нового расчёта отправь снова 4 строки."
    )
    await message.answer(text)


async def main():
    logging.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
