import asyncio
import logging
import sqlite3
import os
import csv
import re
import matplotlib.pyplot as plt
import speech_recognition as sr
from datetime import datetime
from pydub import AudioSegment

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

# --- ВСТАВЬ СВОЙ ТОКЕН ТУТ ---
TOKEN = "8396694675:AAHHW21vA_aMH9AKYXGkFRLD-9BoUFdfgoE" 

bot = Bot(token=TOKEN)
dp = Dispatcher()
recognizer = sr.Recognizer()

# Состояния для пошаговой работы
class Setup(StatesGroup):
    choosing_currency = State()
    confirming_op = State() # Состояние подтверждения операции

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
        [InlineKeyboardButton(text="USD 💵", callback_data="set_curr_USD"), InlineKeyboardButton(text="RUB ₽", callback_data="set_curr_RUB")],
        [InlineKeyboardButton(text="TMT 🇹🇲", callback_data="set_curr_TMT"), InlineKeyboardButton(text="THB 🇹🇭", callback_data="set_curr_THB")]
    ])

def get_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Мой Баланс", callback_data="get_balance")],
        [InlineKeyboardButton(text="📊 Аналитика", callback_data="get_chart"), InlineKeyboardButton(text="📋 Отчет", callback_data="export")]
    ])

# Кнопки выбора: Расход или Доход
def get_confirm_kb(amount, category):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"➕ Доход ({amount})", callback_data="op_plus"),
         InlineKeyboardButton(text=f"➖ Расход ({amount})", callback_data="op_minus")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="op_cancel")]
    ])

# --- ОБРАБОТЧИКИ ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    init_db()
    user = db_query("SELECT currency FROM users WHERE user_id = ?", (message.from_user.id,), fetch=True)
    if not user:
        await message.answer("Привет! Давай настроим бота. Выбери валюту:", reply_markup=get_currency_kb())
        await state.set_state(Setup.choosing_currency)
    else:
        await message.answer(f"Бот готов! Пришли текст (100 еда) или голос.", reply_markup=get_main_kb())

@dp.callback_query(Setup.choosing_currency, F.data.startswith("set_curr_"))
async def set_currency(callback: types.CallbackQuery, state: FSMContext):
    curr = callback.data.split("_")[2]
    db_query("INSERT OR REPLACE INTO users (user_id, currency) VALUES (?, ?)", (callback.from_user.id, curr))
    await state.clear()
    await callback.message.edit_text(f"✅ Валюта {curr} установлена!", reply_markup=get_main_kb())

# ОБРАБОТКА ТЕКСТА (Ручной ввод)
@dp.message(F.text)
async def process_text(message: types.Message, state: FSMContext):
    match = re.search(r"(\d+[\.,]?\d*)\s*(.*)", message.text)
    if match:
        amount = match.group(1).replace(",", ".")
        category = match.group(2).strip() or "Прочее"
        await state.update_data(temp_amount=amount, temp_category=category)
        await message.answer(f"Куда добавить {amount} за '{category}'?", reply_markup=get_confirm_kb(amount, category))
        await state.set_state(Setup.confirming_op)

# ОБРАБОТКА ГОЛОСА
@dp.message(F.voice)
async def handle_voice(message: types.Message, state: FSMContext):
    file = await bot.get_file(message.voice.file_id)
    o_path, w_path = f"v_{message.from_user.id}.ogg", f"v_{message.from_user.id}.wav"
    await bot.download_file(file.file_path, o_path)
    
    try:
        AudioSegment.from_ogg(o_path).export(w_path, format="wav")
        with sr.AudioFile(w_path) as source:
            text = recognizer.recognize_google(recognizer.record(source), language="ru-RU")
            match = re.search(r"(\d+)", text)
            if match:
                amount = match.group(1)
                category = text.replace(amount, "").strip() or "Голос"
                await state.update_data(temp_amount=amount, temp_category=category)
                await message.answer(f"🎙 Распознал: '{text}'\nКуда записать?", reply_markup=get_confirm_kb(amount, category))
                await state.set_state(Setup.confirming_op)
            else:
                await message.answer(f"Распознал: '{text}', но не нашел сумму.")
    except:
        await message.answer("Не удалось разобрать голос.")
    finally:
        for p in [o_path, w_path]:
            if os.path.exists(p): os.remove(p)

# ПОДТВЕРЖДЕНИЕ ОПЕРАЦИИ (Кнопки Доход/Расход)
@dp.callback_query(Setup.confirming_op, F.data.startswith("op_"))
async def confirm_op(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "op_cancel":
        await state.clear()
        await callback.message.edit_text("Операция отменена ❌", reply_markup=get_main_kb())
        return

    data = await state.get_data()
    amount = float(data['temp_amount'])
    category = data['temp_category']
    op_type = "income" if callback.data == "op_plus" else "expense"
    
    user_curr = db_query("SELECT currency FROM users WHERE user_id = ?", (callback.from_user.id,), fetch=True)
    curr = user_curr[0][0] if user_curr else ""

    # В базе расходы храним как минус, доходы как плюс
    final_amount = amount if op_type == "income" else -amount
    db_query("INSERT INTO operations (user_id, type, amount, category, currency, date) VALUES (?, ?, ?, ?, ?, ?)",
             (callback.from_user.id, op_type, final_amount, category, curr, datetime.now().strftime("%Y-%m-%d")))
    
    status = "➕ Доход" if op_type == "income" else "➖ Расход"
    await callback.message.edit_text(f"✅ Сохранено в {status}: {amount} {curr}\nКатегория: {category}", reply_markup=get_main_kb())
    await state.clear()

# БАЛАНС
@dp.callback_query(F.data == "get_balance")
async def show_balance(callback: types.CallbackQuery):
    user_curr = db_query("SELECT currency FROM users WHERE user_id = ?", (callback.from_user.id,), fetch=True)
    curr = user_curr[0][0] if user_curr else ""
    
    rows = db_query("SELECT SUM(amount) FROM operations WHERE user_id = ?", (callback.from_user.id,), fetch=True)
    balance = rows[0][0] if rows[0][0] else 0
    
    # Детализация
    inc = db_query("SELECT SUM(amount) FROM operations WHERE user_id = ? AND type = 'income'", (callback.from_user.id,), fetch=True)[0][0] or 0
    exp = db_query("SELECT SUM(amount) FROM operations WHERE user_id = ? AND type = 'expense'", (callback.from_user.id,), fetch=True)[0][0] or 0
    
    text = (f"🏦 **Ваш баланс:** `{balance:,.2f} {curr}`\n\n"
            f"📈 Доходы: `+{inc:,.2f}`\n"
            f"📉 Расходы: `{exp:,.2f}`")
    
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=get_main_kb())
    await callback.answer()

# ГРАФИК
@dp.callback_query(F.data == "get_chart")
async def send_chart(callback: types.CallbackQuery):
    rows = db_query("SELECT category, SUM(ABS(amount)) FROM operations WHERE user_id = ? AND type = 'expense' GROUP BY category", (callback.from_user.id,), fetch=True)
    if not rows: return await callback.answer("Расходов для графика нет!")

    plt.figure(figsize=(6, 4))
    plt.pie([r[1] for r in rows], labels=[r[0] for r in rows], autopct='%1.1f%%')
    plt.title("Твои расходы")
    path = f"c_{callback.from_user.id}.png"
    plt.savefig(path)
    plt.close()
    await callback.message.answer_photo(FSInputFile(path), caption="📊 Аналитика расходов")
    os.remove(path)

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
