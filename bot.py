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

# --- БАЗА ДАННЫХ ---
def db_exec(query, params=()):
    with sqlite3.connect('finance_pro.db', timeout=10) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        return cur.fetchall()

def init_db():
    db_exec("CREATE TABLE IF NOT EXISTS ops (id INTEGER PRIMARY KEY, user_id INTEGER, type TEXT, amount REAL, cat TEXT, date TEXT)")
    db_exec("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, curr TEXT)")

# --- КЛАВИАТУРЫ ---
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Баланс", callback_data="check_bal"), 
         InlineKeyboardButton(text="📜 История", callback_data="check_history")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="check_stats")],
        [InlineKeyboardButton(text="↩️ Удалить последнюю", callback_data="del_last")],
        [InlineKeyboardButton(text="⚙️ Валюта", callback_data="change_curr")]
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
    user = db_exec("SELECT curr FROM users WHERE user_id = ?", (message.from_user.id,))
    if not user:
        await message.answer("Добро пожаловать! 👋\nВыберите вашу валюту:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="USD 💵", callback_data="setcurr:USD"), InlineKeyboardButton(text="TMT 🇹🇲", callback_data="setcurr:TMT")],
            [InlineKeyboardButton(text="RUB ₽", callback_data="setcurr:RUB"), InlineKeyboardButton(text="THB 🇹🇭", callback_data="setcurr:THB")]
        ]))
    else:
        await message.answer(f"Бот Waller активен! 🟢\nТвоя валюта: **{user[0][0]}**", reply_markup=main_kb(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("setcurr:"))
async def set_currency(callback: types.CallbackQuery):
    await callback.answer()
    new_curr = callback.data.split(":")[1]
    db_exec("INSERT OR REPLACE INTO users (user_id, curr) VALUES (?, ?)", (callback.from_user.id, new_curr))
    await callback.message.edit_text(f"✅ Установлена валюта: **{new_curr}**", reply_markup=main_kb())

# ТЕКСТ И ГОЛОС
@dp.message(F.text)
async def handle_text(message: types.Message):
    nums = re.findall(r"\d+", message.text)
    if not nums: return
    amount = "".join(nums)
    cat = message.text.replace(amount, "").strip() or "Прочее"
    await message.answer(f"💵 Сумма: **{amount}**\nКуда запишем?", reply_markup=confirm_kb(amount, cat), parse_mode="Markdown")

@dp.message(F.voice)
async def handle_voice(message: types.Message):
    msg = await message.answer("⏳ Обработка голоса...")
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
                await msg.edit_text(f"🎙 Распознано: '{text}'\nСумма не найдена.")
    except: await msg.edit_text("❌ Ошибка звука.")
    finally:
        for p in [o_path, w_path]: 
            if os.path.exists(p): os.remove(p)

# КНОПКИ СОХРАНЕНИЯ
@dp.callback_query(F.data.startswith("sv:"))
async def save_op(callback: types.CallbackQuery):
    await callback.answer("✅")
    _, op_type, amt, cat = callback.data.split(":")
    val = float(amt) if op_type == "in" else -float(amt)
    db_exec("INSERT INTO ops (user_id, type, amount, cat, date) VALUES (?, ?, ?, ?, ?)",
            (callback.from_user.id, op_type, val, cat, datetime.now().strftime("%d.%m %H:%M")))
    await callback.message.edit_text(f"✅ Сохранено: {amt} ({cat})", reply_markup=main_kb())

# НОВАЯ ФУНКЦИЯ: УДАЛЕНИЕ ПОСЛЕДНЕЙ ЗАПИСИ
@dp.callback_query(F.data == "del_last")
async def delete_last_op(callback: types.CallbackQuery):
    await callback.answer("Удаляю...")
    last_op = db_exec("SELECT id, amount, cat FROM ops WHERE user_id = ? ORDER BY id DESC LIMIT 1", (callback.from_user.id,))
    if last_op:
        db_exec("DELETE FROM ops WHERE id = ?", (last_op[0][0],))
        await callback.message.answer(f"🗑 Удалена запись: {last_op[0][1]} ({last_op[0][2]})", reply_markup=main_kb())
    else:
        await callback.answer("Записей пока нет", show_alert=True)

# НОВАЯ ФУНКЦИЯ: ИСТОРИЯ
@dp.callback_query(F.data == "check_history")
async def show_history(callback: types.CallbackQuery):
    await callback.answer()
    rows = db_exec("SELECT date, amount, cat FROM ops WHERE user_id = ? ORDER BY id DESC LIMIT 5", (callback.from_user.id,))
    if not rows: return await callback.message.answer("История пуста.")
    
    text = "📜 **Последние 5 операций:**\n\n"
    for r in rows:
        sign = "➕" if r[1] > 0 else "➖"
        text += f"{r[0]} | {sign} {abs(r[1])} | {r[2]}\n"
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=main_kb())

@dp.callback_query(F.data == "check_bal")
async def get_balance(callback: types.CallbackQuery):
    await callback.answer()
    res = db_exec("SELECT SUM(amount) FROM ops WHERE user_id = ?", (callback.from_user.id,))
    curr = db_exec("SELECT curr FROM users WHERE user_id = ?", (callback.from_user.id,))
    total = res[0][0] if res[0][0] else 0
    await callback.message.answer(f"🏦 Баланс: **{total:,.2f} {curr[0][0]}**", parse_mode="Markdown")

@dp.callback_query(F.data == "cancel")
async def cancel_op(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.delete()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
