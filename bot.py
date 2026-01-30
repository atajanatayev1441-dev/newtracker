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

# --- ТВОЙ ТОКЕН ---
TOKEN = "8396694675:AAHHW21vA_aMH9AKYXGkFRLD-9BoUFdfgoE"

bot = Bot(token=TOKEN)
dp = Dispatcher()
recognizer = sr.Recognizer()

# --- БАЗА ДАННЫХ ---
def db_exec(query, params=()):
    with sqlite3.connect('finance_pro.db') as conn:
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
         InlineKeyboardButton(text="📊 История", callback_data="check_history")]
    ])

def confirm_kb(amt, cat):
    # Ограничиваем длину категории для корректной передачи в кнопках
    cat_short = cat[:15].strip() or "Разное"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"➕ Доход ({amt})", callback_data=f"save:in:{amt}:{cat_short}"),
         InlineKeyboardButton(text=f"➖ Расход ({amt})", callback_data=f"save:ex:{amt}:{cat_short}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

# --- ОБРАБОТЧИКИ ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    init_db()
    # По умолчанию ставим валюту TMT (можно сменить на USD)
    db_exec("INSERT OR IGNORE INTO users (user_id, curr) VALUES (?, ?)", (message.from_user.id, "TMT"))
    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Я помогу вести учет твоих финансов.\n"
        "• Напиши: `500 такси` или `10000 премия`\n"
        "• Или отправь **голосовое сообщение**.\n\n"
        "Я спрошу, куда именно записать сумму!", 
        reply_markup=main_kb()
    )

# Обработка текста
@dp.message(F.text)
async def handle_text(message: types.Message):
    # Ищем любую цифру в сообщении
    match = re.search(r"(\d+[\.,]?\d*)", message.text)
    if not match:
        return await message.answer("Я не нашел сумму в твоем сообщении. Напиши, например: `300 ужин`.")
    
    amount = match.group(1).replace(",", ".")
    category = message.text.replace(match.group(1), "").strip() or "Прочее"
    
    await message.answer(
        f"💵 Сумма: **{amount}**\n📂 Категория: **{category}**\n\nКуда запишем?", 
        reply_markup=confirm_kb(amount, category), 
        parse_mode="Markdown"
    )

# Обработка голоса
@dp.message(F.voice)
async def handle_voice(message: types.Message):
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
                category = text.replace(amount, "").strip() or "Голосовой ввод"
                await message.answer(
                    f"🎙 Распознано: '{text}'\n\n"
                    f"💵 Сумма: **{amount}**\n\nКуда запишем?", 
                    reply_markup=confirm_kb(amount, category), 
                    parse_mode="Markdown"
                )
            else:
                await message.answer(f"🎙 Текст: '{text}'\nСумму не нашел. Попробуй еще раз.")
    except Exception:
        await message.answer("Не удалось обработать голос. Попробуй сказать четче.")
    finally:
        for p in [o_path, w_path]:
            if os.path.exists(p): os.remove(p)

# Сохранение в базу
@dp.callback_query(F.data.startswith("save:"))
async def save_op(callback: types.CallbackQuery):
    _, op_type, amt, cat = callback.data.split(":")
    val = float(amt) if op_type == "in" else -float(amt)
    
    db_exec("INSERT INTO ops (user_id, type, amount, cat, date) VALUES (?, ?, ?, ?, ?)",
            (callback.from_user.id, op_type, val, cat, datetime.now().strftime("%d.%m %H:%M")))
    
    res_text = "💰 Доход" if op_type == "in" else "📉 Расход"
    await callback.message.edit_text(
        f"✅ **Записано!**\n\nТип: {res_text}\nСумма: {amt}\nКатегория: {cat}", 
        reply_markup=main_kb(), 
        parse_mode="Markdown"
    )

# Проверка баланса
@dp.callback_query(F.data == "check_bal")
async def get_balance(callback: types.CallbackQuery):
    res = db_exec("SELECT SUM(amount) FROM ops WHERE user_id = ?", (callback.from_user.id,))
    total = res[0][0] if res[0][0] else 0
    inc = db_exec("SELECT SUM(amount) FROM ops WHERE user_id = ? AND amount > 0", (callback.from_user.id,))[0][0] or 0
    exp = db_exec("SELECT SUM(amount) FROM ops WHERE user_id = ? AND amount < 0", (callback.from_user.id,))[0][0] or 0
    
    text = (f"🏦 **Ваш кошелек:**\n\n"
            f"💰 Итого: `{total:,.2f}`\n\n"
            f"➕ Всего доходов: `{inc:,.2f}`\n"
            f"➖ Всего расходов: `{abs(exp):,.2f}`")
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=main_kb())
    await callback.answer()

@dp.callback_query(F.data == "cancel")
async def cancel_op(callback: types.CallbackQuery):
    await callback.message.edit_text("Действие отменено. Жду новых команд.", reply_markup=main_kb())

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
