import asyncio
import logging
import os
import re
from datetime import date

from aiogram import Bot, Dispatcher
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Итоги в памяти: (user_id, yyyy-mm-dd) -> {"count": int, "rub": float, "usdt": float}
# Важно: при рестарте Render всё обнулится. Для постоянного хранения нужен SQLite/Redis.
totals = {}


def parse_number(text: str) -> float | None:
    """
    Достаёт число из строки.
    Поддерживает: "76", "76.5", "76,5", "14к", "36 500", "36500р"
    """
    t = text.strip().lower().replace(" ", "").replace(",", ".")

    mult = 1.0
    if "к" in t:  # 14к = 14000
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


def key_today(user_id: int):
    return (user_id, str(date.today()))


def totals_text(user_id: int) -> str:
    k = key_today(user_id)
    data = totals.get(k, {"count": 0, "rub": 0.0, "usdt": 0.0})
    return (
        "📊 Итоги за сегодня:\n"
        f"🧾 Сделок: {data['count']}\n"
        f"💰 RUB: {fmt3(data['rub'])}\n"
        f"💵 USDT: {fmt3(data['usdt'])}"
    )


@dp.inline_query()
async def inline_handler(inline: InlineQuery):
    q = (inline.query or "").strip()

    # Команды inline
    if q.lower() in {"total", "/total"}:
        text = totals_text(inline.from_user.id)
        results = [
            InlineQueryResultArticle(
                id="total_today",
                title="📊 Итоги за сегодня",
                description="Показать количество сделок, сумму RUB и сумму USDT",
                input_message_content=InputTextMessageContent(message_text=text),
            )
        ]
        await bot.answer_inline_query(
            inline_query_id=inline.id,
            results=results,
            cache_time=0,
            is_personal=True,
        )
        return

    if q.lower() in {"reset", "/reset"}:
        totals[key_today(inline.from_user.id)] = {"count": 0, "rub": 0.0, "usdt": 0.0}
        text = "✅ Итоги за сегодня обнулены."
        results = [
            InlineQueryResultArticle(
                id="reset_today",
                title="✅ Сбросить итоги",
                description="Обнулить итоги за сегодня",
                input_message_content=InputTextMessageContent(message_text=text),
            )
        ]
        await bot.answer_inline_query(
            inline_query_id=inline.id,
            results=results,
            cache_time=0,
            is_personal=True,
        )
        return

    # Расчёт заявки (4 строки)
    parsed = try_parse_4_lines(q)
    if not parsed:
        help_text = (
            "Отправь 4 строки:\n"
            "1) курс\n2) реквизит\n3) банк\n4) сумма (руб)\n\n"
            "Пример:\n"
            "76\n2200701002300314\nТинь\n36500\n\n"
            "Команды:\n"
            "total — итоги за день\n"
            "reset — сброс итога"
        )
        results = [
            InlineQueryResultArticle(
                id="help",
                title="ℹ️ Формат ввода",
                description="Покажу пример, как отправлять заявку в 4 строки",
                input_message_content=InputTextMessageContent(message_text=help_text),
            )
        ]
        await bot.answer_inline_query(
            inline_query_id=inline.id,
            results=results,
            cache_time=0,
            is_personal=True,
        )
        return

    rate, req, bank, amount_rub, amount_usdt = parsed

    # копим итоги по пользователю
    k = key_today(inline.from_user.id)
    if k not in totals:
        totals[k] = {"count": 0, "rub": 0.0, "usdt": 0.0}
    totals[k]["count"] += 1
    totals[k]["rub"] += amount_rub
    totals[k]["usdt"] += amount_usdt

    text = (
        "✅ Сделка рассчитана\n"
        f"📈 Курс: {fmt3(rate)}\n"
        f"💳 Реквизит: {req}\n"
        f"🏦 Банк: {bank}\n"
        f"💰 RUB: {fmt3(amount_rub)}\n"
        f"💵 USDT: {fmt3(amount_usdt)}\n\n"
        "Чтобы увидеть итог: @Calculat3Bot total"
    )

    results = [
        InlineQueryResultArticle(
            id=f"calc_{inline.from_user.id}_{inline.id}",
            title="✅ Рассчитать сделку",
            description=f"USDT: {fmt3(amount_usdt)} | RUB: {fmt3(amount_rub)} | Курс: {fmt3(rate)}",
            input_message_content=InputTextMessageContent(message_text=text),
        )
    ]

    await bot.answer_inline_query(
        inline_query_id=inline.id,
        results=results,
        cache_time=0,
        is_personal=True,
    )


async def main():
    logging.info("Inline bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
