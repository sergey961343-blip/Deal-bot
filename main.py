import asyncio
import logging
import os
import re
from datetime import date

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хранилище итогов в памяти (на Render при рестарте обнулится)
# Структура: { (chat_id, yyyy-mm-dd): {"count": int, "rub": float, "usdt": float} }
totals = {}


def parse_number(text: str) -> float | None:
    """
    Достаёт число из строки.
    Поддержка: "76", "76.5", "76,5", "14к", "36 500", "36500р"
    """
    t = text.strip().lower().replace(" ", "").replace(",", ".")

    mult = 1.0
    # 14к = 14000
    if "к" in t:
        mult = 1000.0
        t = t.replace("к", "")

    m = re.search(r"\d+(\.\d+)?", t)
    if not m:
        return None

    try:
        return float(m.group(0)) * mult
    except ValueError:
        return None


def fmt3(x: float) -> str:
    # 12345.678 -> "12 345,678"
    return f"{x:,.3f}".replace(",", " ").replace(".", ",")


def try_parse_4_lines(text: str):
    """
    Ожидаем 4 строки:
    1) курс
    2) реквизит (любой текст)
    3) банк (любой текст)
    4) сумма (руб)
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) != 4:
        return None

    rate_raw, req, bank, amount_raw = lines

    rate = parse_number(rate_raw)
    amount_rub = parse_number(amount_raw)

    if rate is None or amount_rub is None:
        return None
    if rate <= 0 or amount_rub <= 0:
        return None

    amount_usdt = amount_rub / rate
    return rate, req, bank, amount_rub, amount_usdt


def day_key(chat_id: int):
    return (chat_id, str(date.today()))


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Отправь одним сообщением 4 строки:\n"
        "1) курс\n2) реквизит\n3) банк\n4) сумма (руб)\n\n"
        "Пример:\n"
        "76\n2200701002300314\nТинь\n36500\n\n"
        "Команды:\n"
        "/total — итоги за сегодня\n"
        "/reset — обнулить итоги за сегодня"
    )


@dp.message(Command("total"))
async def cmd_total(message: Message):
    k = day_key(message.chat.id)
    data = totals.get(k, {"count": 0, "rub": 0.0, "usdt": 0.0})

    await message.answer(
        "📊 Итоги за сегодня:\n"
        f"🧾 Сделок: {data['count']}\n"
        f"💰 RUB: {fmt3(data['rub'])}\n"
        f"💵 USDT: {fmt3(data['usdt'])}"
    )


@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    k = day_key(message.chat.id)
    totals[k] = {"count": 0, "rub": 0.0, "usdt": 0.0}
    await message.answer("✅ Итоги за сегодня обнулены.")


@dp.message(F.text)
async def handle_text(message: Message):
    parsed = try_parse_4_lines(message.text)
    if not parsed:
        # Ничего не пишем, чтобы бот не флудил в группе.
        # Если хочешь — могу включить подсказку при ошибке формата.
        return

    rate, req, bank, amount_rub, amount_usdt = parsed

    # Сохраняем в итоги дня
    k = day_key(message.chat.id)
    if k not in totals:
        totals[k] = {"count": 0, "rub": 0.0, "usdt": 0.0}

    totals[k]["count"] += 1
    totals[k]["rub"] += amount_rub
    totals[k]["usdt"] += amount_usdt

    await message.answer(
        "✅ Сделка рассчитана\n"
        f"📈 Курс: {fmt3(rate)}\n"
        f"💳 Реквизит: {req}\n"
        f"🏦 Банк: {bank}\n"
        f"💰 RUB: {fmt3(amount_rub)}\n"
        f"💵 USDT: {fmt3(amount_usdt)}"
    )


async def main():
    logging.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
