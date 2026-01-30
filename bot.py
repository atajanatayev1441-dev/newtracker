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
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, 
    ReplyKeyboardMarkup, KeyboardButton
)

# --- КОНФИГ ---
TOKEN = "8396694675:AAHHW21vA_aMH9AKYXGkFRLD-9BoUFdfgoE"
# Твой ID или никнейм для обратной связи
ADMIN_CONTACT = "8283258905" 

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

def main_reply_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="📊 Анализ трат")],
            [KeyboardButton(text="📜 История"), KeyboardButton(text="✍️ Обратная связь")],
            [KeyboardButton(text="↩️ Удалить последнюю")]
        ],
        resize_keyboard=True
    )

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
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="USD 💵", callback_data="setcurr:USD"), InlineKeyboardButton(text="TMT 🇹🇲", callback_data="setcurr:TMT")],
            [InlineKeyboardButton(text="RUB ₽", callback_data="setcurr:RUB"), InlineKeyboardButton(text="THB 🇹🇭", callback_data="setcurr:THB")]
        ])
        await message.answer("Добро пожаловать в Waller! 👋\nВыберите валюту:", reply_markup=kb)
    else:
        await message.answer(f"С возвращением! 🟢", reply_markup=main_reply_kb())

# АНАЛИЗ ПО КАТЕГОРИЯМ
@dp.message(F.text == "📊 Анализ трат")
async def btn_analysis(message: types.Message):
    # Берем только расходы (amount < 0) и группируем по категориям
    rows = db_exec(
        "SELECT cat, SUM(ABS(amount)) as total FROM ops WHERE user_id = ? AND amount < 0 GROUP BY cat ORDER BY total DESC",
        (message.from_user.id,)
    )
    
    if not rows:
        return await message.answer("У вас пока нет расходов для анализа.")
    
    u_curr = db_exec("SELECT curr FROM users WHERE user_id = ?", (message.from_user.id,))
    curr = u_curr[0][0] if u_curr else ""
    
    report = "📊 **Анализ ваших трат:**\n\n"
    grand_total = sum(item[1] for item in rows)
    
    for i, (cat, total) in enumerate(rows, 1):
        percent = (total / grand_total) * 100
        report += f"{i}. **{cat}**: `{total:,.2f} {curr}` ({percent:.1f}%)\n"
    
    report += f"\n💰 Всего потрачено: `{grand_total:,.2f} {curr}`"
    await message.answer(report, parse_mode="Markdown")

# ОБРАТНАЯ СВЯЗЬ
@dp.message(F.text == "✍️ Обратная связь")
async def btn_feedback(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Написать разработчику ✉️", url=f"https://t.me/{ADMIN_CONTACT.replace('@','')}")]
    ])
    await message.answer(
        "Есть идеи, как улучшить бота, или нашли ошибку? \nНажмите на кнопку ниже, чтобы связаться со мной!",
        reply_markup=kb
    )

# Остальные стандартные функции
@dp.message(F.text == "💰 Баланс")
async def btn_balance(message: types.Message):
    res = db_exec("SELECT SUM(amount) FROM ops WHERE user_id = ?", (message.from_user.id,))
    curr = db_exec("SELECT curr FROM users WHERE user_id = ?", (message.from_user.id,))
    total = res[0][0] if res[0][0] else 0
    await message.answer(f"🏦 Ваш баланс: **{total:,.2f} {curr[0][0] if curr else ''}**", parse_mode="Markdown")

@dp.message(F.text == "📜 История")
async def btn_history(message: types.Message):
    rows = db_exec("SELECT date, amount, cat FROM ops WHERE user_id = ? ORDER BY id DESC LIMIT 5", (message.from_user.id,))
    if not rows: return await message.answer("История пуста.")
    text = "📜 **Последние 5 операций:**\n\n"
    for r in rows:
        sign = "➕" if r[1] > 0 else "➖"
        text += f"{r[0]} | {sign} {abs(r[1])} | {r[2]}\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "↩️ Удалить последнюю")
async def btn_del_last(message: types.Message):
    last_op = db_exec("SELECT id, amount, cat FROM ops WHERE user_id = ? ORDER BY id DESC LIMIT 1", (message.from_user.id,))
    if last_op:
        db_exec("DELETE FROM ops WHERE id = ?", (last_op[0][0],))
        await message.answer(f"🗑 Удалена запись: {last_op[0][1]} ({last_op[0][2]})")
    else:
        await message.answer("Записей нет.")

@dp.message(F.text)
async def handle_text(message: types.Message):
    nums = re.findall(r"\d+", message.text)
    if not nums: return
    amount = "".join(nums)
    cat = message.text.replace(amount, "").strip() or "Прочее"
    await message.answer(f"💵 Сумма: **{amount}**\nКуда запишем?", reply_markup=confirm_kb(amount, cat), parse_mode="Markdown")

@dp.message(F.voice)
async def handle_voice(message: types.Message):
    msg = await message.answer("⏳ Обработка...")
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
                await msg.edit_text(f"🎙 Текст: '{text}'\nСумма не найдена.")
    except: await msg.edit_text("❌ Ошибка звука.")
    finally:
        for p in [o_path, w_path]: 
            if os.path.exists(p): os.remove(p)

@dp.callback_query(F.data.startswith("sv:"))
async def save_op(callback: types.CallbackQuery):
    await callback.answer("✅")
    _, op_type, amt, cat = callback.data.split(":")
    val = float(amt) if op_type == "in" else -float(amt)
    db_exec("INSERT INTO ops (user_id, type, amount, cat, date) VALUES (?, ?, ?, ?, ?)",
            (callback.from_user.id, op_type, val, cat, datetime.now().strftime("%d.%m %H:%M")))
    await callback.message.edit_text(f"✅ Сохранено: {amt} ({cat})")

@dp.callback_query(F.data == "cancel")
async def cancel_op(callback: types.CallbackQuery):
    await callback.answer("Отменено")
    await callback.message.delete()

@dp.callback_query(F.data.startswith("setcurr:"))
async def set_currency(callback: types.CallbackQuery):
    await callback.answer()
    new_curr = callback.data.split(":")[1]
    db_exec("INSERT OR REPLACE INTO users (user_id, curr) VALUES (?, ?)", (callback.from_user.id, new_curr))
    await callback.message.edit_text(f"✅ Валюта: {new_curr}")
    await callback.message.answer("Меню активировано!", reply_markup=main_reply_kb())

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
