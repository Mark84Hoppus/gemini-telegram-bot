import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai
from collections import defaultdict
from datetime import datetime, timedelta

# Конфигурация через переменные окружения
TOKEN = os.getenv("TELEGRAM_TOKEN")
API_KEY = os.getenv("GEMINI_API_KEY")

if not TOKEN or not API_KEY:
    raise ValueError("TELEGRAM_TOKEN и GEMINI_API_KEY должны быть установлены в переменных окружения")

MAX_HISTORY_LENGTH = 500  # Максимальное количество сообщений в истории
SESSION_TIMEOUT = 1440     # Время жизни сессии в минутах

# Инициализация модели Gemini
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Хранилище сессий пользователей
user_sessions = defaultdict(dict)

def get_user_session(user_id: int):
    """Инициализация или получение сессии пользователя"""
    session = user_sessions.get(user_id, {})
    if not session or (datetime.now() - session['last_active']) > timedelta(minutes=SESSION_TIMEOUT):
        user_sessions[user_id] = {
            'history': [],
            'last_active': datetime.now()
        }
    return user_sessions[user_id]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user = update.effective_user
    session = get_user_session(user.id)
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n"
        "Я ваш персональный помощник на базе Gemini 1.5 Flash.\n"
        "Я помню наш диалог и могу анализировать предыдущие сообщения.\n\n"
        "Используйте /clear чтобы очистить историю диалога."
    )

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Очистка истории диалога"""
    user = update.effective_user
    session = get_user_session(user.id)
    session['history'].clear()
    await update.message.reply_text("🔄 История диалога очищена!")

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка сообщений с учетом контекста, с разделением длинных ответов"""
    try:
        user = update.effective_user
        session = get_user_session(user.id)
        user_message = update.message.text
        session['history'].append({"role": "user", "parts": [user_message]})
        session['last_active'] = datetime.now()

        context_messages = [{"role": "model", "parts": ["Ты - полезный ассистент. Отвечай подробно и учитывай контекст диалога."]}]
        context_messages.extend(session['history'][-MAX_HISTORY_LENGTH:])

        chat_session = model.start_chat(history=context_messages)
        response = chat_session.send_message(user_message)

        if response.text:
            session['history'].append({"role": "model", "parts": [response.text]})
            if len(session['history']) > MAX_HISTORY_LENGTH * 2:
                session['history'] = session['history'][-MAX_HISTORY_LENGTH:]

            # Разбиваем ответ, если он слишком длинный
            chunk_size = 4000
            chunks = [response.text[i:i + chunk_size] for i in range(0, len(response.text), chunk_size)]

            # Отправляем по частям
            for chunk in chunks:
                await update.message.reply_text(chunk)

        else:
            await update.message.reply_text("❌ Не удалось сгенерировать ответ")

    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка: {str(e)}")
        if session and session['history']:
            session['history'].pop()

# Сборка и запуск приложения
app = ApplicationBuilder().token(TOKEN).build()

# Регистрация обработчиков
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("clear", clear_history))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

# Запуск бота
app.run_polling()
