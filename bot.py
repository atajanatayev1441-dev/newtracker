import asyncio
import logging
import sqlite3
import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Настройки
TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

class Setup(StatesGroup):
    choosing_currency = State()

# --- КЛАВИАТУРЫ (Вынес отдельно для надежности) ---
def get_currency_kb():
    buttons = [
        [InlineKeyboardButton(text="USD 💵", callback_data="set_curr_USD"),
         InlineKeyboardButton(text="RUB ₽", callback_data="set_curr_RUB")],
        [InlineKeyboardButton(text="TMT 🇹🇲", callback_data="set_curr_TMT"),
         InlineKeyboardButton(text="THB 🇹🇭", callback_data="set_curr_THB")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_main_kb():
    buttons = [
        [InlineKeyboardButton(text="📊 График", callback_data="get_chart"),
         InlineKeyboardButton(text="📋 Отчет (CSV)", callback_data="export")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- ОБРАБОТЧИКИ ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    # Логируем для проверки в Railway Logs
    print(f"Пользователь {message.from_user.id} нажал старт")
    
    # Сразу предлагаем валюту при старте
    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Я твой финансовый бот. Чтобы начать, выбери свою валюту:",
        reply_markup=get_currency_kb()
    )
    await state.set_state(Setup.choosing_currency)

@dp.callback_query(Setup.choosing_currency, F.data.startswith("set_curr_"))
async def set_currency(callback: types.CallbackQuery, state: FSMContext):
    selected_curr = callback.data.split("_")[2]
    
    # Здесь можно добавить сохранение в БД
    
    await state.clear()
    await callback.message.edit_text(
        f"✅ Валюта **{selected_curr}** установлена!\n\n"
        "Теперь ты можешь записывать расходы.\n"
        "Просто напиши: `500 Еда` или отправь голос.",
        reply_markup=get_main_kb(),
        parse_mode="Markdown"
    )
    await callback.answer()

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
