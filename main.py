import asyncio
import logging
import os
import re
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=os.getenv('BOT_TOKEN'))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# Состояния для FSM
class DealStates(StatesGroup):
    waiting_for_rate = State()
    waiting_for_requisites = State()
    waiting_for_bank = State()
    waiting_for_amount = State()


HELP_TEXT = """
📝 Формат ввода данных для расчёта сделки:

Отправьте 4 сообщения по очереди:

1️⃣ Курс (примеры: "76", "76.5", "76,5", "Курс 76р")
2️⃣ Реквизит (любой текст)
3️⃣ Банк (любой текст)
4️⃣ Сумма (примеры: "43800", "43 800")

Бот автоматически рассчитает результат деления суммы на курс.
"""


def parse_number(text: str) -> float | None:
    """Парсит число из текста, поддерживая разные форматы"""
    # Удаляем пробелы и заменяем запятую на точку
    cleaned = text.strip().replace(' ', '').replace(',', '.')
    
    # Ищем число в тексте (включая с буквами вокруг)
    match = re.search(r'\d+\.?\d*', cleaned)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def format_number(number: float) -> str:
    """Форматирует число с запятой как десятичным разделителем"""
    return f"{number:,.3f}".replace(',', ' ').replace('.', ',')

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
    @dp.message(F.text)
async def one_message_calc(message: Message, state: FSMContext):
    parsed = try_parse_4_lines(message.text)
    if not parsed:
        return

    rate, req, bank, amount = parsed
    result = amount / rate

    await state.clear()

    text = (
        "✅ Сделка рассчитана\n"
        f"🏦 Банк: {bank}\n"
        f"💳 Реквизит: {req}\n"
        f"📈 Курс: {format_number(rate)}\n"
        f"💰 Сумма: {format_number(amount)}\n"
        f"🧮 {format_number(amount)} / {format_number(rate)} = {format_number(result)}\n\n"
        "Для нового расчёта отправь снова 4 строки или /start"
    )

    await message.answer(text)
@dp.message(Command('start'))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    await message.answer(
        f"👋 Добро пожаловать!\n\n{HELP_TEXT}"
    )
    await message.answer("Введите курс:")
    await state.set_state(DealStates.waiting_for_rate)


@dp.message(Command('help'))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    await message.answer(HELP_TEXT)


@dp.message(DealStates.waiting_for_rate)
async def process_rate(message: Message, state: FSMContext):
    """Обработка ввода курса"""
    rate = parse_number(message.text)
    
    if rate is None or rate <= 0:
        await message.answer(
            "❌ Неверный формат курса!\n\n"
            "Примеры правильного ввода:\n"
            "• 76\n"
            "• 76.5\n"
            "• 76,5\n"
            "• Курс 76р\n\n"
            "Попробуйте снова:"
        )
        return
    
    await state.update_data(rate=rate)
    await message.answer("Введите реквизит:")
    await state.set_state(DealStates.waiting_for_requisites)


@dp.message(DealStates.waiting_for_requisites)
async def process_requisites(message: Message, state: FSMContext):
    """Обработка ввода реквизита"""
    await state.update_data(requisites=message.text)
    await message.answer("Введите банк:")
    await state.set_state(DealStates.waiting_for_bank)


@dp.message(DealStates.waiting_for_bank)
async def process_bank(message: Message, state: FSMContext):
    """Обработка ввода банка"""
    await state.update_data(bank=message.text)
    await message.answer("Введите сумму:")
    await state.set_state(DealStates.waiting_for_amount)


@dp.message(DealStates.waiting_for_amount)
async def process_amount(message: Message, state: FSMContext):
    """Обработка ввода суммы и вывод результата"""
    amount = parse_number(message.text)
    
    if amount is None or amount <= 0:
        await message.answer(
            "❌ Неверный формат суммы!\n\n"
            "Примеры правильного ввода:\n"
            "• 43800\n"
            "• 43 800\n"
            "• 43800.50\n\n"
            "Попробуйте снова:"
        )
        return
    
    # Получаем все данные
    data = await state.get_data()
    rate = data['rate']
    requisites = data['requisites']
    bank = data['bank']
    
    # Вычисляем результат
    result = amount / rate
    
    # Форматируем вывод
    response = (
        "✅ Сделка рассчитана\n"
        f"🏦 Банк: {bank}\n"
        f"💳 Реквизит: {requisites}\n"
        f"📈 Курс: {format_number(rate)}\n"
        f"💰 Сумма: {format_number(amount)}\n"
        f"🧮 {format_number(amount)} / {format_number(rate)} = {format_number(result)}"
    )
    
    await message.answer(response)
    
    # Очищаем состояние
    await state.clear()
    
    # Предлагаем начать новый расчёт
    await message.answer("\nДля нового расчёта введите /start")


@dp.message()
async def handle_unknown(message: Message):
    """Обработка неизвестных сообщений"""
    await message.answer(
        "❓ Неизвестная команда.\n\n"
        "Используйте:\n"
        "/start — начать расчёт\n"
        "/help — показать справку"
    )


async def main():
    """Запуск бота"""
    logging.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
