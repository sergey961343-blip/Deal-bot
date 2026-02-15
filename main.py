import asyncio
import logging
import os
import re
from datetime import date
from uuid import uuid4

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

# Итоги по пользователю за день (inline -> считаем "на пользователя", не на чат)
# key: (user_id, yyyy-mm-dd)
totals = {}


def parse_number(text: str) -> float | None:
    """
    Достаёт число из строки.
    Поддержка: "76", "76.5", "76,5", "14к", "36 500", "36500р"
    """
    t = (text or "").strip().lower()
    if not t:
        return None

    t = t.replace(" ", "").replace(",", ".")

    mult = 1.0
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


def fmt_trim(x: float, max_decimals: int = 3) -> str:
    """
    75.500 -> "75,5"
    76.000 -> "76"
    43800.000 -> "43 800"
    480.263 -> "480,263"
    """
    s = f"{x:,.{max_decimals}f}"
    s = s.replace(",", " ").replace(".", ",")
    # убираем хвостовые нули после запятой
    if "," in s:
        s = s.rstrip("0").rstrip(",")
    return s


def fmt_rub(x: float) -> str:
    # RUB обычно без копеек — но если вдруг пришло с .5, всё равно красиво обрежем
    return fmt_trim(x, max_decimals=3)


def fmt_rate(x: float) -> str:
    # курс: без лишних нулей
    return fmt_trim(x, max_decimals=6)


def fmt_usdt(x: float) -> str:
    # USDT: до 3 знаков (и без лишних нулей)
    return fmt_trim(x, max_decimals=3)


def try_parse_4_lines(text: str):
    """
    Ожидаем 4 строки:
    1) курс
    2) реквизит (любой текст)
    3) банк (любой текст)
    4) сумма (руб)
    """
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
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


def day_key(user_id: int):
    return (user_id, str(date.today()))


def make_help_article() -> InlineQueryResultArticle:
    help_text = (
        "✅ Как пользоваться:\n\n"
        "1) Расчёт одной сделки (4 строки):\n"
        "76\n2200701002300314\nТинь\n36500\n\n"
        "2) Итоги за сегодня:\n"
        "total\n\n"
        "3) Обнулить итоги:\n"
        "reset\n\n"
        "Пиши в любом чате:\n"
        "@Calculat3Bot + текст\n"
        "и выбирай подсказку из списка."
    )
    return InlineQueryResultArticle(
        id=str(uuid4()),
        title="Инструкция (пример ввода)",
        description="Покажу формат: 4 строки / total / reset",
        input_message_content=InputTextMessageContent(
            message_text=help_text
        ),
    )


@dp.inline_query()
async def on_inline_query(inline_query: InlineQuery):
    q = (inline_query.query or "").strip()

    # если пусто — показываем инструкцию
    if not q:
        await inline_query.answer(
            results=[make_help_article()],
            cache_time=1,
            is_personal=True,
        )
        return

    q_low = q.lower()

    user_id = inline_query.from_user.id
    k = day_key(user_id)
    if k not in totals:
        totals[k] = {"count": 0, "rub": 0.0, "usdt": 0.0}

    # ===== total =====
    if q_low in ("total", "итог", "итоги"):
        data = totals.get(k, {"count": 0, "rub": 0.0, "usdt": 0.0})
        text = (
            "📊 Итоги за сегодня:\n"
            f"🧾 Сделок: {data['count']}\n"
            f"💰 RUB: {fmt_rub(data['rub'])}\n"
            f"💵 USDT: {fmt_usdt(data['usdt'])}"
        )
        result = InlineQueryResultArticle(
            id=str(uuid4()),
            title="Итоги за сегодня",
            description=f"Сделок: {data['count']} • RUB: {fmt_rub(data['rub'])} • USDT: {fmt_usdt(data['usdt'])}",
            input_message_content=InputTextMessageContent(message_text=text),
        )
        await inline_query.answer(
            results=[result],
            cache_time=1,
            is_personal=True,
        )
        return

    # ===== reset =====
    if q_low in ("reset", "сброс", "обнулить"):
        totals[k] = {"count": 0, "rub": 0.0, "usdt": 0.0}
        text = "✅ Итоги за сегодня обнулены."
        result = InlineQueryResultArticle(
            id=str(uuid4()),
            title="Обнулить итоги за сегодня",
            description="Сброшу счётчик сделок/RUB/USDT",
            input_message_content=InputTextMessageContent(message_text=text),
        )
        await inline_query.answer(
            results=[result],
            cache_time=1,
            is_personal=True,
        )
        return

    # ===== 4 строки =====
    parsed = try_parse_4_lines(q)
    if not parsed:
        # если формат не подошёл — даём подсказку (чтобы ты видел, почему не считает)
        hint = (
            "❌ Не понял формат.\n\n"
            "Нужно ровно 4 строки:\n"
            "1) курс\n2) реквизит\n3) банк\n4) сумма (руб)\n\n"
            "Пример:\n"
            "76\n2200701002300314\nТинь\n36500\n\n"
            "Или напиши: total / reset"
        )
        result = InlineQueryResultArticle(
            id=str(uuid4()),
            title="Ошибка формата (нажми — покажу пример)",
            description="Нужно 4 строки или total/reset",
            input_message_content=InputTextMessageContent(message_text=hint),
        )
        await inline_query.answer(
            results=[result],
            cache_time=1,
            is_personal=True,
        )
        return

    rate, req, bank, amount_rub, amount_usdt = parsed

    # сохраняем итоги по пользователю (за день)
    totals[k]["count"] += 1
    totals[k]["rub"] += amount_rub
    totals[k]["usdt"] += amount_usdt

    text = (
        "✅ Сделка рассчитана\n"
        f"📈 Курс: {fmt_rate(rate)}\n"
        f"💳 Реквизит: {req}\n"
        f"🏦 Банк: {bank}\n"
        f"💰 RUB: {fmt_rub(amount_rub)}\n"
        f"💵 USDT: {fmt_usdt(amount_usdt)}\n\n"
        "Чтобы увидеть итог: @Calculat3Bot total"
    )

    result = InlineQueryResultArticle(
        id=str(uuid4()),
        title=f"Сделка: {fmt_rub(amount_rub)} RUB → {fmt_usdt(amount_usdt)} USDT",
        description=f"Курс {fmt_rate(rate)} • Нажми чтобы отправить в чат",
        input_message_content=InputTextMessageContent(message_text=text),
    )

    await inline_query.answer(
        results=[result],
        cache_time=1,
        is_personal=True,
    )


async def main():
    logging.info("Bot started (INLINE MODE)")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
