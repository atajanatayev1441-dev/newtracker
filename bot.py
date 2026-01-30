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
ADMIN_USERNAME = "atadjan_dev" # Твой ник без @

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
            [KeyboardButton(text="⚙️ Валюта"), KeyboardButton(text="↩️ Удалить последнюю")]
        ],
        resize_keyboard=True
    )

def currency_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="USD 💵", callback_data="setcurr:USD"), InlineKeyboardButton(text="TMT 🇹🇲", callback_data="setcurr:TMT")],
        [InlineKeyboardButton(text="RUB ₽", callback_data="setcurr:RUB"), InlineKeyboardButton(text="THB 🇹🇭", callback_data="setcurr:THB")]
    ])

def confirm_kb(amt, cat):
    cat_s = cat[:15].strip() or "Разное"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"➕ Доход ({amt})", callback_data=f"sv:in:{amt}:{cat_s}"),
         InlineKeyboardButton(text=f"➖ Расход ({amt})", callback_data=f"sv:ex:{amt}:{cat_s}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

# --- ОБРАБОТЧИКИ ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    init_db()
    db_exec("INSERT OR IGNORE INTO users (user_id, curr) VALUES (?, ?)", (message.from_user.id, "TMT"))
    await message.answer(f"Привет, {message.from_user.first_name}! Waller готов. 🟢", reply_markup=main_reply_kb())

# 💰 БАЛАНС
@dp.message(F.text == "💰 Баланс")
async def btn_balance(message: types.Message):
    res = db_exec("SELECT SUM(amount) FROM ops WHERE user_id = ?", (message.from_user.id,))
    u = db_exec("SELECT curr FROM users WHERE user_id = ?", (message.from_user.id,))
    total = res[0][0] if res[0][0] else 0
    curr = u[0][0] if u else "TMT"
    await message.answer(f"🏦 Ваш баланс: **{total:,.2f} {curr}**", parse_mode="Markdown")

# 📊 АНАЛИЗ ТРАТ
@dp.message(F.text == "📊 Анализ трат")
async def btn_analysis(message: types.Message):
    rows = db_exec("SELECT cat, SUM(ABS(amount)) as tot FROM ops WHERE user_id = ? AND amount < 0 GROUP BY cat ORDER BY tot DESC", (message.from_user.id,))
    if not rows: return await message.answer("Нет данных для анализа.")
    
    u = db_exec("SELECT curr FROM users WHERE user_id = ?", (message.from_user.id,))
    curr = u[0][0] if u else "TMT"
    
    rep = "📊 **Анализ расходов:**\n\n"
    for r in rows: rep += f"• {r[0]}: {r[1]:,.2f} {curr}\n"
    await message.answer(rep, parse_mode="Markdown")

# 📜 ИСТОРИЯ
@dp.message(F.text == "📜 История")
async def btn_history(message: types.Message):
    rows = db_exec("SELECT date, amount, cat FROM ops WHERE user_id = ? ORDER BY id DESC LIMIT 5", (message.from_user.id,))
    if not rows: return await message.answer("История пуста.")
    txt = "📜 **Последние 5 операций:**\n\n"
    for r in rows:
        sign = "➕" if r[1] > 0 else "➖"
        txt += f"{r[0]} | {sign} {abs(r[1])} | {r[2]}\n"
    await message.answer(txt, parse_mode="Markdown")

# ↩️ УДАЛЕНИЕ
@dp.message(F.text == "↩️ Удалить последнюю")
async def btn_del(message: types.Message):
    last = db_exec("SELECT id, amount, cat FROM ops WHERE user_id = ? ORDER BY id DESC LIMIT 1", (message.from_user.id,))
    if last:
        db_exec("DELETE FROM ops WHERE id = ?", (last[0][0],))
        await message.answer(f"🗑 Удалено: {last[0][1]} ({last[0][2]})")
    else: await message.answer("Записей нет.")

# ⚙️ ВАЛЮТА
@dp.message(F.text == "⚙️ Валюта")
async def btn_curr(message: types.Message):
    await message.answer("Выберите валюту:", reply_markup=currency_kb())

# ✍️ ОБРАТНАЯ СВЯЗЬ
@dp.message(F.text == "✍️ Обратная связь")
async def btn_feed(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Написать", url=f"https://t.me/{ADMIN_USERNAME}")]])
    await message.answer("Есть вопросы? Напиши мне!", reply_markup=kb)

# --- ВВОД ДАННЫХ ---

@dp.message(F.text)
async def handle_text(message: types.Message):
    # Если это не системная кнопка, ищем цифры
    nums = re.findall(r"\d+", message.text)
    if not nums: return
    amt = "".join(nums)
    cat = message.text.replace(amt, "").strip() or "Прочее"
    await message.answer(f"💵 Сумма: **{amt}**\nКуда запишем?", reply_markup=confirm_kb(amt, cat))

@dp.message(F.voice)
async def handle_voice(message: types.Message):
    msg = await message.answer("⏳ Слушаю...")
    file = await bot.get_file(message.voice.file_id)
    path = f"v_{message.from_user.id}.ogg"
    wav = path.replace(".ogg", ".wav")
    await bot.download_file(file.file_path, path)
    try:
        AudioSegment.from_ogg(path).export(wav, format="wav")
        with sr.AudioFile(wav) as s:
            t = recognizer.recognize_google(recognizer.record(s), language="ru-RU")
            nums = re.findall(r"\d+", t)
            if nums:
                amt = "".join(nums)
                cat = t.replace(amt, "").strip() or "Голос"
                await msg.edit_text(f"🎙 **{amt}** ({cat})", reply_markup=confirm_kb(amt, cat))
            else: await msg.edit_text(f"Не понял сумму в: {t}")
    except: await msg.edit_text("Ошибка звука.")
    finally:
        for f in [path, wav]:
            if os.path.exists(f): os.remove(f)

# --- CALLBACKS ---

@dp.callback_query(F.data.startswith("sv:"))
async def save_op(callback: types.CallbackQuery):
    await callback.answer()
    _, tp, amt, cat = callback.data.split(":")
    val = float(amt) if tp == "in" else -float(amt)
    db_exec("INSERT INTO ops (user_id, type, amount, cat, date) VALUES (?, ?, ?, ?, ?)",
            (callback.from_user.id, tp, val, cat, datetime.now().strftime("%d.%m %H:%M")))
    await callback.message.edit_text(f"✅ Записано: {amt}")

@dp.callback_query(F.data == "cancel")
async def cancel_op(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.delete()

@dp.callback_query(F.data.startswith("setcurr:"))
async def set_curr(callback: types.CallbackQuery):
    await callback.answer()
    c = callback.data.split(":")[1]
    db_exec("INSERT OR REPLACE INTO users (user_id, curr) VALUES (?, ?)", (callback.from_user.id, c))
    await callback.message.edit_text(f"✅ Валюта изменена на {c}")

async def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
