import logging
import sqlite3
from flask import Flask, request, abort
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, CallbackQueryHandler, filters
)
import asyncio

# Настройки
BOT_TOKEN = '7548597124:AAFnT4qW4sL2jCnQrDf1tiQs1F61yqpdeRw'
EXPERT_CHAT_ID = -1002610167622
ADMIN_ID = 151678905

logging.basicConfig(level=logging.INFO)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('messages.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        first_name TEXT,
        question TEXT,
        group_msg_id INTEGER,
        answer TEXT,
        status TEXT DEFAULT 'waiting',
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

init_db()

# Flask-приложение
flask_app = Flask(_name_)

# Создаем Application
app = ApplicationBuilder().token(BOT_TOKEN).build()

# Команды и сообщения
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [['Задати питання', 'Отримати допомогу']]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Привіт! Я бот для зв'язку з Правлінням ОСББ.", reply_markup=markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Напишіть повідомлення — я передам його правлінню, і ви отримаєте відповідь.")

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Доступ заборонено.")
        return

    conn = sqlite3.connect('messages.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM messages WHERE status = 'waiting'")
    waiting = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM messages WHERE status = 'answered'")
    answered = c.fetchone()[0]
    conn.close()

    await update.message.reply_text(
        f"Усього питань: {total}\nОчікують відповіді: {waiting}\nВідповіді надано: {answered}"
    )

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    markup = ReplyKeyboardMarkup([['Повернутися до головного меню']], resize_keyboard=True)
    await update.message.reply_text("Напишіть своє питання:", reply_markup=markup)

async def get_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    markup = ReplyKeyboardMarkup([['Повернутися до головного меню']], resize_keyboard=True)
    await update.message.reply_text("Щоб задати питання, натисніть «Задати питання».", reply_markup=markup)

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    markup = ReplyKeyboardMarkup([['Задати питання', 'Отримати допомогу']], resize_keyboard=True)
    await update.message.reply_text("Головне меню.", reply_markup=markup)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    sent = await context.bot.send_message(
        chat_id=EXPERT_CHAT_ID,
        text=f"Питання від @{user.username or user.first_name}:\n\n{text}"
    )

    conn = sqlite3.connect('messages.db')
    c = conn.cursor()
    c.execute("INSERT INTO messages (user_id, username, first_name, question, group_msg_id) VALUES (?, ?, ?, ?, ?)",
              (user.id, user.username, user.first_name, text, sent.message_id))
    conn.commit()
    conn.close()

    await update.message.reply_text("Ваше питання передано. Очікуйте на відповідь.")

async def handle_expert_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        group_msg_id = update.message.reply_to_message.message_id
        answer_text = update.message.text

        conn = sqlite3.connect('messages.db')
        c = conn.cursor()
        c.execute("SELECT user_id FROM messages WHERE group_msg_id = ?", (group_msg_id,))
        row = c.fetchone()

        if row:
            user_id = row[0]
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("Підтвердити отримання", callback_data=f"confirm_{group_msg_id}")
            ]])
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Відповідь від правління:\n\n{answer_text}",
                reply_markup=keyboard
            )
            c.execute("UPDATE messages SET answer = ?, status = 'answered' WHERE group_msg_id = ?",
                      (answer_text, group_msg_id))
            conn.commit()
        conn.close()

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("confirm_"):
        group_msg_id = int(query.data.split("_")[1])
        conn = sqlite3.connect('messages.db')
        c = conn.cursor()
        c.execute("UPDATE messages SET status = 'confirmed' WHERE group_msg_id = ?", (group_msg_id,))
        conn.commit()
        conn.close()
        await query.edit_message_reply_markup(None)
        await query.message.reply_text("Дякуємо за підтвердження!")

# Обработчики
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("admin", admin))
app.add_handler(MessageHandler(filters.Regex('^Задати питання$'), ask_question))
app.add_handler(MessageHandler(filters.Regex('^Отримати допомогу$'), get_help))
app.add_handler(MessageHandler(filters.Regex('^Повернутися до головного меню$'), back_to_menu))
app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT, handle_user_message))
app.add_handler(MessageHandler(filters.Chat(chat_id=EXPERT_CHAT_ID) & filters.REPLY & filters.TEXT, handle_expert_reply))
app.add_handler(CallbackQueryHandler(button_handler))

# Webhook route
@flask_app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), app.bot)
        asyncio.create_task(app.process_update(update))
        return "OK"
    else:
        abort(403)

@flask_app.route("/", methods=["GET"])
def index():
    return "Бот працює!"

# Запуск
if _name_ == "_main_":
    flask_app.run(host="0.0.0.0", port=5000)