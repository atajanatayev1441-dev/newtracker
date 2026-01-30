import asyncio
import logging
import sqlite3
import os
import csv
import matplotlib.pyplot as plt
import speech_recognition as sr
from datetime import datetime
from pydub import AudioSegment

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

# Настройки
TOKEN = os.getenv("BOT_TOKEN", "8396694675:AAHHW21vA_aMH9AKYXGkFRLD-9BoUFdfgoE")
bot = Bot(token=TOKEN)
dp = Dispatcher()
recognizer = sr.Recognizer()

class Setup(StatesGroup):
    choosing_currency = State()

def db_query(query, params=(), fetch=False):
    conn = sqlite3.connect('database.db')
    cur = conn.cursor()
    cur.execute(query, params)
    res = cur.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return res

def init_db():
    db_query("CREATE TABLE IF NOT EXISTS operations (id INTEGER PRIMARY KEY, user_id INTEGER, type TEXT, amount REAL, category TEXT, currency TEXT, date TEXT)")
    db_query("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, currency TEXT)")

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    init_db()
    user = db_query("SELECT currency FROM users WHERE user_id = ?", (message.from_user.id,), fetch=True)
    if not user:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="USD 💵", callback_data="set_curr_USD"), InlineKeyboardButton(text="RUB ₽", callback_data="set_curr_RUB")],
            [InlineKeyboardButton(text="TMT 🇹🇲", callback_data="set_curr_TMT"), InlineKeyboardButton(text="THB 🇹🇭", callback_data="set_curr_THB")]
        ])
        await message.answer("Добро пожаловать! Выберите валюту:", reply_markup=kb)
        await state.set_state(Setup.choosing_currency)
    else:
        await message.answer("Бот активен! Введите 'Сумма Категория' или отправьте голос.", 
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                 [InlineKeyboardButton(text="📊 График", callback_data="get_chart"),
                                  InlineKeyboardButton(text="📋 Отчет", callback_data="export")]
                             ]))

@dp.callback_query(Setup.choosing_currency, F.data.startswith("set_curr_"))
async def set_currency(callback: types.CallbackQuery, state: FSMContext):
    curr = callback.data.split("_")[2]
    db_query("INSERT OR REPLACE INTO users (user_id, currency) VALUES (?, ?)", (callback.from_user.id, curr))
    await state.clear()
    await callback.message.edit_text(f"Валюта {curr} установлена. Начинайте учет!")

@dp.callback_query(F.data == "get_chart")
async def send_chart(callback: types.CallbackQuery):
    rows = db_query("SELECT category, SUM(amount) FROM operations WHERE user_id = ? AND type = 'minus' GROUP BY category", (callback.from_user.id,), fetch=True)
    if not rows: return await callback.answer("Нет данных!")
    
    plt.figure(figsize=(6, 4))
    plt.pie([r[1] for r in rows], labels=[r[0] for r in rows], autopct='%1.1f%%')
    plt.savefig(f"c_{callback.from_user.id}.png")
    plt.close()
    await callback.message.answer_photo(FSInputFile(f"c_{callback.from_user.id}.png"))
    os.remove(f"c_{callback.from_user.id}.png")

@dp.message(F.text.regexp(r"(\d+)\s+(.+)"))
async def add_expense(message: types.Message):
    curr = db_query("SELECT currency FROM users WHERE user_id = ?", (message.from_user.id,), fetch=True)
    amt, cat = message.text.split(maxsplit=1)
    db_query("INSERT INTO operations (user_id, type, amount, category, currency, date) VALUES (?, ?, ?, ?, ?, ?)",
             (message.from_user.id, "minus", float(amt), cat, curr[0][0], datetime.now().strftime("%Y-%m-%d")))
    await message.answer(f"✅ Учтено: {amt} {curr[0][0]}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

