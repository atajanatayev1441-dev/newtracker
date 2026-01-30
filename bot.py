import asyncio
import logging
import sqlite3
import os
import csv
import sys
import matplotlib.pyplot as plt
import speech_recognition as sr
from datetime import datetime
from pydub import AudioSegment

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

# --- ВСТАВЬ СВОЙ ТОКЕН НИЖЕ ---
TOKEN = "8396694675:AAHHW21vA_aMH9AKYXGkFRLD-9BoUFdfgoE" 

if not TOKEN or "ЗДЕСЬ" in TOKEN:
    sys.exit("Ошибка: Ты не вставил токен в кавычки!")

bot = Bot(token=TOKEN)
dp = Dispatcher()
recognizer = sr.Recognizer()

class Setup(StatesGroup):
    choosing_currency = State()

# --- БАЗА ДАННЫХ ---
def db_query(query, params=(), fetch=False):
    conn = sqlite3.connect('finance_pro.db')
    cur = conn.cursor()
    cur.execute(query, params)
    res = cur.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return res

def init_db():
    db_query("CREATE TABLE IF NOT EXISTS operations (id INTEGER PRIMARY KEY, user_id INTEGER, type TEXT, amount REAL, category TEXT, currency TEXT, date TEXT)")
    db_query("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, currency TEXT)")

# --- КЛАВИАТУРЫ ---
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
    init_db()
    # Проверка пользователя (исправленная скобка тут)
    user = db_query("SELECT currency FROM users WHERE user_id = ?", (message.from_user.id,), fetch=True)
    
    if not user:
        await message.answer("Добро пожаловать! 👋\nВыберите вашу валюту:", reply_markup=get_currency_kb())
        await state.set_state(Setup.choosing_currency)
    else:
        curr = user[0][0]
        await message.answer(f"Бот активен! 💰\nВалюта: {curr}\n\nПиши: `100 Еда` или отправь голос.", reply_markup=get_main_kb())

@dp.callback_query(Setup.choosing_currency, F.data.startswith("set_curr_"))
async def set_currency(callback: types.CallbackQuery, state: FSMContext):
    curr = callback.data.split("_")[2]
    db_query("INSERT OR REPLACE INTO users (user_id, currency) VALUES (?, ?)", (callback.from_user.id, curr))
    await state.clear()
    await callback.message.edit_text(f"✅ Валюта {curr} установлена!", reply_markup=get_main_kb())
    await callback.answer()

@dp.message(F.text.regexp(r"(\d+)\s+(.+)"))
async def add_expense(message: types.Message):
    user_data = db_query("SELECT currency FROM users WHERE user_id = ?", (message.from_user.id,), fetch=True)
    if not user_data: return
    
    curr = user_data[0][0]
    parts = message.text.split(maxsplit=1)
    amount, category = parts[0], parts[1]
    
    db_query("INSERT INTO operations (user_id, type, amount, category, currency, date) VALUES (?, ?, ?, ?, ?, ?)",
             (message.from_user.id, "minus", float(amount), category, curr, datetime.now().strftime("%Y-%m-%d")))
    await message.answer(f"✅ Учтено: {amount} {curr} на '{category}'")

@dp.callback_query(F.data == "get_chart")
async def send_chart(callback: types.CallbackQuery):
    rows = db_query("SELECT category, SUM(amount) FROM operations WHERE user_id = ? AND type = 'minus' GROUP BY category", (callback.from_user.id,), fetch=True)
    if not rows: return await callback.answer("Данных нет!")

    plt.figure(figsize=(6, 4))
    plt.pie([r[1] for r in rows], labels=[r[0] for r in rows], autopct='%1.1f%%')
    plt.title("Твои расходы")
    
    path = f"chart_{callback.from_user.id}.png"
    plt.savefig(path)
    plt.close()
    await callback.message.answer_photo(FSInputFile(path))
    os.remove(path)

@dp.callback_query(F.data == "export")
async def export_csv(callback: types.CallbackQuery):
    rows = db_query("SELECT date, amount, category, currency FROM operations WHERE user_id = ?", (callback.from_user.id,), fetch=True)
    path = f"report_{callback.from_user.id}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Дата", "Сумма", "Категория", "Валюта"])
        writer.writerows(rows)
    await callback.message.answer_document(FSInputFile(path), caption="Твой отчет 📁")
    os.remove(path)

@dp.message(F.voice)
async def handle_voice(message: types.Message):
    file = await bot.get_file(message.voice.file_id)
    o_path = f"v_{message.from_user.id}.ogg"
    w_path = f"v_{message.from_user.id}.wav"
    await bot.download_file(file.file_path, o_path)
    
    try:
        AudioSegment.from_ogg(o_path).export(w_path, format="wav")
        with sr.AudioFile(w_path) as source:
            text = recognizer.recognize_google(recognizer.record(source), language="ru-RU")
            await message.answer(f"🎙 Распознано: '{text}'")
    except:
        await message.answer("Не удалось разобрать голос.")
    finally:
        for p in [o_path, w_path]:
            if os.path.exists(p): os.remove(p)

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
