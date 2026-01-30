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

# --- ПРОВЕРКА ТОКЕНА ---
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    logging.error("❌ ОШИБКА: Токен не найден в переменных окружения Railway (BOT_TOKEN)!")
    # Если на сервере пусто, бот просто не запустится и выдаст понятную ошибку
    sys.exit("Error: BOT_TOKEN variable is missing. Check Railway Variables tab.")

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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="USD 💵", callback_data="set_curr_USD"), 
         InlineKeyboardButton(text="RUB ₽", callback_data="set_curr_RUB")],
        [InlineKeyboardButton(text="TMT 🇹🇲", callback_data="set_curr_TMT"), 
         InlineKeyboardButton(text="THB 🇹🇭", callback_data="set_curr_THB")]
    ])

def get_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 График", callback_data="get_chart"), 
         InlineKeyboardButton(text="📋 Отчет (CSV)", callback_data="export")]
    ])

# --- ОБРАБОТЧИКИ ---

@dp.message(CommandStart())
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    init_db()
    # Проверяем, есть ли пользователь в базе
    user = db_query("SELECT currency FROM users WHERE user_id = ?", (message.from_user.id,), fetch=True)
    
    if not user:
        await message.answer("Добро пожаловать! 👋\nВыберите вашу основную валюту:", reply_markup=get_currency_kb())
        await state.set_state(Setup.choosing_currency)
    else:
        curr = user[0][0]
        await message.answer(f"Бот готов. Ваша валюта: {curr}\n\nВведите 'Сумма Категория' (например: `500 Еда`) или отправьте голосовое сообщение.", 
                             reply_markup=get_main_kb())

