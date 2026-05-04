import random
import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TRANSLATIONS = {
    'ru': {
        'welcome': "🎮 *ИГРА «УГАДАЙ ДА/НЕТ»*\n\nВыбери действие:",
        'main_menu': "🏠 *ГЛАВНОЕ МЕНЮ*",
        'new_game': "🎮 Новая игра",
        'daily_bonus': "💰 Ежедневный бонус",
        'leaderboard': "🏆 Таблица лидеров",
        'stats': "📊 Моя статистика",
        'achievements': "🏅 Мои достижения",
        'language': "🌐 Язык",
        'back': "🔙 Назад",
        'yes': "✅ ДА",
        'no': "❌ НЕТ",
    },
    'en': {
        'welcome': "🎮 *GUESS YES/NO GAME*\n\nChoose action:",
        'main_menu': "🏠 *MAIN MENU*",
        'new_game': "🎮 New Game",
        'daily_bonus': "💰 Daily Bonus",
        'leaderboard': "🏆 Leaderboard",
        'stats': "📊 My Stats",
        'achievements': "🏅 My Achievements",
        'language': "🌐 Language",
        'back': "🔙 Back",
        'yes': "✅ YES",
        'no': "❌ NO",
    }
}

QUESTIONS = {
    'easy': {
        'ru': [("Земля вращается вокруг Солнца", True), ("Вода мокрая", True)],
        'en': [("The Earth revolves around the Sun", True), ("Water is wet", True)]
    },
    'hard': {
        'ru': [("У осьминога три сердца", True), ("Банан — это ягода", True)],
        'en': [("Octopuses have three hearts", True), ("Banana is a berry", True)]
    }
}

ACHIEVEMENTS = {
    5: {"name_ru": "НОВИЧОК", "name_en": "BEGINNER", "emoji": "🌱"},
    10: {"name_ru": "ЭКСПЕРТ", "name_en": "EXPERT", "emoji": "⚡"},
}

class Database:
    def __init__(self, db_name="game_bot.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_tables()
    
    def _create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                language TEXT DEFAULT 'ru',
                total_score INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                best_score INTEGER DEFAULT 0,
                total_correct INTEGER DEFAULT 0,
                last_played TIMESTAMP,
                daily_bonus_date TEXT
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_achievements (
                user_id INTEGER,
                achievement_id INTEGER,
                achieved_at TIMESTAMP,
                PRIMARY KEY (user_id, achievement_id)
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_games (
                user_id INTEGER PRIMARY KEY,
                current_score INTEGER,
                difficulty TEXT,
                streak INTEGER,
                question TEXT,
                correct_answer BOOLEAN,
                started_at TIMESTAMP
            )
        ''')
        self.conn.commit()
    
    def get_or_create_user(self, user_id, username=None, first_name=None, last_name=None):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = self.cursor.fetchone()
        if not user:
            self.cursor.execute('INSERT INTO users (user_id, username, first_name, last_name, last_played) VALUES (?, ?, ?, ?, ?)',
                              (user_id, username, first_name, last_name, datetime.now()))
            self.conn.commit()
            return {'user_id': user_id, 'language': 'ru'}
        return {'user_id': user[0], 'language': user[4]}
    
    def set_language(self, user_id, language):
        self.cursor.execute('UPDATE users SET language = ? WHERE user_id = ?', (language, user_id))
        self.conn.commit()
    
    def close(self):
        self.conn.close()

db = Database()

def get_text(user_id, key):
    user = db.get_or_create_user(user_id)
    lang = user.get('language', 'ru')
    return TRANSLATIONS[lang].get(key, TRANSLATIONS['ru'][key])

async def start(update, context):
    user = update.effective_user
    db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    
    keyboard = [[InlineKeyboardButton(get_text(user.id, 'new_game'), callback_data="new_game")],
                [InlineKeyboardButton(get_text(user.id, 'language'), callback_data="language")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(get_text(user.id, 'welcome'), parse_mode="Markdown", reply_markup=reply_markup)

async def main_menu(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    keyboard = [[InlineKeyboardButton(get_text(user_id, 'new_game'), callback_data="new_game")],
                [InlineKeyboardButton(get_text(user_id, 'language'), callback_data="language")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(get_text(user_id, 'main_menu'), parse_mode="Markdown", reply_markup=reply_markup)

async def choose_language(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    keyboard = [[InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
                 InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
                [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("🌐 Выбери язык / Choose language:", reply_markup=reply_markup)

async def set_language(update, context, lang):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    db.set_language(user_id, lang)
    await main_menu(update, context)

def main():
    import os
    TOKEN = os.environ.get("Yes_0r_No_Bot")
    if not TOKEN:
        print("❌ Ошибка: BOT_TOKEN не найден в переменных окружения!")
        return
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(choose_language, pattern="^language$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_language(u,c,'ru'), pattern="^lang_ru$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_language(u,c,'en'), pattern="^lang_en$"))
    
    print("🤖 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()