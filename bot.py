import asyncio
import logging
import sqlite3
import os
import re
import speech_recognition as sr
from datetime import datetime
from pydub import AudioSegment
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- КОНФИГ ---
TOKEN = "8396694675:AAHHW21vA_aMH9AKYXGkFRLD-9BoUFdfgoE"
bot = Bot(token=TOKEN)
dp = Dispatcher()
recognizer = sr.Recognizer()

# --- БАЗА ДАННЫХ (Оптимизированная) ---
def db_exec(query, params=()):
    # Используем контекстный менеджер для гарантии закрытия БД
    with sqlite3.connect('finance_pro.db', timeout=10) as conn:
        conn.execute("PRAGMA journal_mode=WAL;") # Включаем режим быстрой записи
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        return cur.fetchall()

def init_db():
    db_exec("CREATE TABLE IF NOT EXISTS ops (id INTEGER PRIMARY KEY, type TEXT, user_id INTEGER, amount REAL, cat TEXT, date TEXT)")
    db_exec("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, curr TEXT)")

# --- КЛАВИАТУРЫ ---
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Баланс", callback_data="check_bal")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="check_stats")]
    ])

def confirm_kb(amt, cat):
    cat_short = cat[:15].strip() or "Разное"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"➕ Доход ({amt})", callback_data=f"sv:in:{amt}:{cat_short}"),
         InlineKeyboardButton(text=f"➖ Расход ({amt})", callback_data=f"sv:ex:{amt}:{cat_short}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

# --- ОБРАБОТЧИКИ ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    init_db()
    db_exec("INSERT OR IGNORE INTO users (user_id, curr) VALUES (?, ?)", (message.from_user.id, "TMT"))
    await message.answer(f"Привет, {message.from_user.first_name}! 🚀\nЯ готов к работе. Напиши сумму или отправь голос.", reply_markup=main_kb())

@dp.message(F.text)
async def handle_text(message: types.Message):
    match = re.search(r"(\d+)", message.text)
    if not match: return
    
    amount = match.group(1)
    category = message.text.replace(amount, "").strip() or "Прочее"
    await message.answer(f"💵 Сумма: **{amount}**\nКуда запишем?", reply_markup=confirm_kb(amount, category), parse_mode="Markdown")

@dp.message(F.voice)
async def handle_voice(message: types.Message):
    msg = await message.answer("⏳ Распознаю голос...")
    file = await bot.get_file(message.voice.file_id)
    o_path, w_path = f"v_{message.from_user.id}.ogg", f"v_{message.from_user.id}.wav"
    await bot.download_file(file.file_path, o_path)
    
    try:
        AudioSegment.from_ogg(o_path).export(w_path, format="wav")
        with sr.AudioFile(w_path) as source:
            text = recognizer.recognize_google(recognizer.record(source), language="ru-RU")
            nums = re.findall(r"\d+", text)
            if nums:
                amount = "".join(nums)
                cat = text.replace(amount, "").strip() or "Голос"
                await msg.edit_text(f"🎙 Распознано: **{amount}** ({cat})\nЗаписать?", reply_markup=confirm_kb(amount, cat), parse_mode="Markdown")
            else:
                await msg.edit_text(f"🎙 Текст: '{text}'\nЧисло не найдено.")
    except:
        await msg.edit_text("❌ Ошибка распознавания.")
    finally:
        for p in [o_path, w_path]:
            if os.path.exists(p): os.remove(p)

# СУПЕР-БЫСТРОЕ СОХРАНЕНИЕ
@dp.callback_query(F.data.startswith("sv:"))
async def save_op(callback: types.CallbackQuery):
    # 1. Сразу отвечаем серверу Telegram, чтобы кнопка не глючила
    await callback.answer("Записываю...") 
    
    try:
        _, op_type, amt, cat = callback.data.split(":")
        val = float(amt) if op_type == "in" else -float(amt)
        
        db_exec("INSERT INTO ops (user_id, type, amount, cat, date) VALUES (?, ?, ?, ?, ?)",
                (callback.from_user.id, op_type, val, cat, datetime.now().strftime("%d.%m %H:%M")))
        
        await callback.message.edit_text(f"✅ Сохранено: {amt} ({cat})", reply_markup=main_kb())
    except Exception as e:
        await callback.message.answer(f"Ошибка сохранения: {e}")

@dp.callback_query(F.data == "check_bal")
async def get_balance(callback: types.CallbackQuery):
    await callback.answer() # Убираем часики с кнопки
    res = db_exec("SELECT SUM(amount) FROM ops WHERE user_id = ?", (callback.from_user.id,))
    total = res[0][0] if res[0][0] else 0
    await callback.message.answer(f"🏦 Текущий баланс: **{total:,.2f} TMT**", parse_mode="Markdown")

@dp.callback_query(F.data == "cancel")
async def cancel_op(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.delete()
    await callback.message.answer("Отменено. Жду новую сумму.", reply_markup=main_kb())

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
