import asyncio
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Твоя таймзона +03
TZ = timezone(timedelta(hours=3))
DB_PATH = "deals.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            rate REAL NOT NULL,
            amount_rub REAL NOT NULL,
            usdt REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def parse_number(text: str) -> float | None:
    cleaned = text.strip().replace(" ", "").replace(",", ".")
    m = re.search(r"\d+(\.\d+)?", cleaned)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def format_number(n: float) -> str:
    # 12 345,678
    return f"{n:,.3f}".replace(",", " ").replace(".", ",")


def try_parse_4_lines(text: str):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) != 4:
        return None

    rate_raw = lines[0]
    amount_raw = lines[3]

    rate = parse_number(rate_raw)
    amount = parse_number(amount_raw)

    if rate is None or amount is None:
        return None
    if rate <= 0 or amount <= 0:
        return None

    return rate, amount


def save_deal(chat_id: int, rate: float, amount: float, usdt: float):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO deals (chat_id, created_at, rate, amount_rub, usdt)
        VALUES (?, ?, ?, ?, ?)
        """,
        (chat_id, datetime.now(TZ).isoformat(), rate, amount, usdt),
    )
    conn.commit()
    conn.close()


def today_range_iso():
    now = datetime.now(TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def get_today_totals(chat_id: int):
    start_iso, end_iso = today_range_iso()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*),
               COALESCE(SUM(amount_rub), 0),
               COALESCE(SUM(usdt), 0)
        FROM deals
        WHERE chat_id = ? AND created_at >= ? AND created_at < ?
        """,
        (chat_id, start_iso, end_iso),
    )
    count, sum_rub, sum_usdt = cur.fetchone()
    conn.close()
    return int(count), float(sum_rub), float(sum_usdt)


def clear_today(chat_id: int):
    start_iso, end_iso = today_range_iso()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM deals
        WHERE chat_id = ? AND created_at >= ? AND created_at < ?
        """,
        (chat_id, start_iso, end_iso),
    )
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted


@dp.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "Отправь заявку ОДНИМ сообщением (4 строки):\n"
        "1) Курс\n2) Реквизит (любой)\n3) Банк (любой)\n4) Сумма (RUB)\n\n"
        "Пример:\n"
        "76\n2200701002300314\nТинь\n36500\n\n"
        "Итог за сегодня: /total"
    )


@dp.message(Command("total"))
async def total_cmd(message: Message):
    count, sum_rub, sum_usdt = get_today_totals(message.chat.id)
    await message.answer(
        "📊 Итог за сегодня:\n"
        f"Сделок: {count}\n"
        f"RUB: {format_number(sum_rub)}\n"
        f"USDT: {format_number(sum_usdt)}"
    )


@dp.message(Command("clear"))
async def clear_cmd(message: Message):
    deleted = clear_today(message.chat.id)
    await message.answer(f"🧹 Удалено сделок за сегодня: {deleted}\nИтог: /total")


@dp.message(F.text)
async def calc_and_store(message: Message):
    parsed = try_parse_4_lines(message.text)
    if not parsed:
        return  # молча игнорим всё остальное

    rate, amount = parsed
    usdt = amount / rate

    save_deal(message.chat.id, rate, amount, usdt)

    await message.reply(
        "✅ Рассчитано\n"
        f"🧮 {format_number(amount)} / {format_number(rate)} = {format_number(usdt)} USDT\n"
        "Итог за сегодня: /total"
    )


async def main():
    init_db()
    logging.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
