import random
import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ========== ПЕРЕВОДЫ ==========
TRANSLATIONS = {
    'ru': {
        'welcome': "🎮 *ИГРА «УГАДАЙ ДА/НЕТ»*\n\n📖 *Правила:*\n• Я даю утверждение\n• Ты отвечаешь ДА или НЕТ\n• За правильный ответ +1 очко\n• Ошибка = конец игры\n\n👇 *Выбери действие:*",
        'main_menu': "🏠 *ГЛАВНОЕ МЕНЮ*\n\nВыбери действие:",
        'new_game': "🎮 Новая игра",
        'language': "🌐 Язык",
        'back': "🔙 Назад",
        'yes': "✅ ДА",
        'no': "❌ НЕТ",
        'game_start': "🎲 *ИГРА НАЧАЛАСЬ!*\n\n📢 *Вопрос:*\n{}\n\n📊 Счёт: *0* очков\n\n✅ ДА или ❌ НЕТ?",
        'correct': "✅ *ПРАВИЛЬНО!* +1 очко\n\n📢 *Вопрос:*\n{}\n\n📊 Счёт: *{}* очков",
        'game_over': "❌ *ИГРА ОКОНЧЕНА!*\n\nПравильный ответ: *{}*\nТы набрал(а): *{}* очков\n\n🏅 Твой лучший результат: *{}* очков\n\nНажми «Новая игра», чтобы продолжить!",
        'play_again': "🎮 Играть снова",
    },
    'en': {
        'welcome': "🎮 *GUESS YES/NO GAME*\n\n📖 *Rules:*\n• I give you a statement\n• You answer YES or NO\n• Correct answer gives +1 point\n• Wrong answer = game over\n\n👇 *Choose action:*",
        'main_menu': "🏠 *MAIN MENU*\n\nChoose action:",
        'new_game': "🎮 New Game",
        'language': "🌐 Language",
        'back': "🔙 Back",
        'yes': "✅ YES",
        'no': "❌ NO",
        'game_start': "🎲 *GAME STARTED!*\n\n📢 *Question:*\n{}\n\n📊 Score: *0* points\n\n✅ YES or ❌ NO?",
        'correct': "✅ *CORRECT!* +1 point\n\n📢 *Question:*\n{}\n\n📊 Score: *{}* points",
        'game_over': "❌ *GAME OVER!*\n\nCorrect answer: *{}*\nYou scored: *{}* points\n\n🏅 Your best score: *{}* points\n\nPress «New Game» to continue!",
        'play_again': "🎮 Play Again",
    }
}

# ========== ВОПРОСЫ ==========
QUESTIONS = {
    'ru': [
        ("Земля вращается вокруг Солнца", True),
        ("Акулы — это млекопитающие", False),
        ("Вода кипит при 90°C на уровне моря", False),
        ("Банан — это ягода", True),
        ("Страусы прячут голову в песок", False),
        ("У осьминога три сердца", True),
        ("Великая Китайская стена видна из космоса", False),
        ("Ватикан — самая маленькая страна в мире", True),
        ("Шоколад ядовит для собак", True),
    ],
    'en': [
        ("The Earth revolves around the Sun", True),
        ("Sharks are mammals", False),
        ("Water boils at 90°C at sea level", False),
        ("Banana is a berry", True),
        ("Ostriches bury their heads in the sand", False),
        ("Octopuses have three hearts", True),
        ("The Great Wall of China is visible from space", False),
        ("Vatican City is the smallest country in the world", True),
        ("Chocolate is poisonous to dogs", True),
    ]
}

# ========== БАЗА ДАННЫХ ==========
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
                best_score INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0
            )
        ''')
        self.conn.commit()
    
    def get_or_create_user(self, user_id, username=None, first_name=None, last_name=None):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = self.cursor.fetchone()
        if not user:
            self.cursor.execute('INSERT INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)',
                              (user_id, username, first_name, last_name))
            self.conn.commit()
            return {'user_id': user_id, 'language': 'ru', 'best_score': 0, 'games_played': 0}
        return {'user_id': user[0], 'language': user[4], 'best_score': user[5], 'games_played': user[6]}
    
    def update_best_score(self, user_id, score):
        self.cursor.execute('SELECT best_score FROM users WHERE user_id = ?', (user_id,))
        current_best = self.cursor.fetchone()[0]
        if score > current_best:
            self.cursor.execute('UPDATE users SET best_score = ? WHERE user_id = ?', (score, user_id))
            self.conn.commit()
            return True
        return False
    
    def increment_games_played(self, user_id):
        self.cursor.execute('UPDATE users SET games_played = games_played + 1 WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def set_language(self, user_id, language):
        self.cursor.execute('UPDATE users SET language = ? WHERE user_id = ?', (language, user_id))
        self.conn.commit()
    
    def close(self):
        self.conn.close()

db = Database()

def get_text(user_id, key, *args):
    user = db.get_or_create_user(user_id)
    lang = user.get('language', 'ru')
    text = TRANSLATIONS[lang].get(key, TRANSLATIONS['ru'][key])
    if args:
        return text.format(*args)
    return text

# ========== ХРАНЕНИЕ СОСТОЯНИЙ ИГР ==========
user_games = {}

# ========== ОБРАБОТЧИКИ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    
    keyboard = [
        [InlineKeyboardButton(get_text(user.id, 'new_game'), callback_data="new_game")],
        [InlineKeyboardButton(get_text(user.id, 'language'), callback_data="language")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(get_text(user.id, 'welcome'), parse_mode="Markdown", reply_markup=reply_markup)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton(get_text(user_id, 'new_game'), callback_data="new_game")],
        [InlineKeyboardButton(get_text(user_id, 'language'), callback_data="language")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(get_text(user_id, 'main_menu'), parse_mode="Markdown", reply_markup=reply_markup)

async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
         InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("🌐 Выбери язык / Choose language:", reply_markup=reply_markup)

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    db.set_language(user_id, lang)
    await main_menu(update, context)

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    lang = db.get_or_create_user(user_id)['language']
    
    # Выбираем случайный вопрос
    question, correct_answer = random.choice(QUESTIONS[lang])
    
    # Сохраняем состояние игры
    user_games[user_id] = {
        'score': 0,
        'correct_answer': correct_answer,
        'current_question': question
    }
    
    keyboard = [
        [InlineKeyboardButton(get_text(user_id, 'yes'), callback_data="answer_yes"),
         InlineKeyboardButton(get_text(user_id, 'no'), callback_data="answer_no")],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        get_text(user_id, 'game_start', question),
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    lang = db.get_or_create_user(user_id)['language']
    
    # Получаем ответ пользователя
    is_yes = query.data == "answer_yes"
    
    # Получаем состояние игры
    game = user_games.get(user_id)
    if not game:
        await query.edit_message_text("Ошибка! Начни игру заново.")
        return
    
    correct_answer = game['correct_answer']
    current_score = game['score']
    
    # Проверяем правильность
    if is_yes == correct_answer:
        # Правильно!
        current_score += 1
        
        # Выбираем новый вопрос
        question, new_correct = random.choice(QUESTIONS[lang])
        
        # Обновляем состояние
        user_games[user_id] = {
            'score': current_score,
            'correct_answer': new_correct,
            'current_question': question
        }
        
        keyboard = [
            [InlineKeyboardButton(get_text(user_id, 'yes'), callback_data="answer_yes"),
             InlineKeyboardButton(get_text(user_id, 'no'), callback_data="answer_no")],
            [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            get_text(user_id, 'correct', question, current_score),
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        # Неправильно - конец игры
        correct_word = "ДА" if correct_answer else "НЕТ" if lang == 'ru' else "YES" if correct_answer else "NO"
        
        # Обновляем лучший результат
        is_new_record = db.update_best_score(user_id, current_score)
        db.increment_games_played(user_id)
        best_score = db.get_or_create_user(user_id)['best_score']
        
        # Удаляем игру
        del user_games[user_id]
        
        keyboard = [
            [InlineKeyboardButton(get_text(user_id, 'play_again'), callback_data="new_game")],
            [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = get_text(user_id, 'game_over', correct_word, current_score, best_score)
        if is_new_record and current_score > 0:
            message += "\n\n🎉 *НОВЫЙ РЕКОРД!* 🎉"
        
        await query.edit_message_text(
            message,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

async def cmd_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /play - быстрый старт"""
    await start(update, context)

# ========== ЗАПУСК ==========
def main():
    import os
    TOKEN = os.environ.get("Yes_0r_No_Bot")
    if not TOKEN:
        print("❌ Ошибка: BOT_TOKEN не найден в переменных окружения!")
        print("Добавь переменную BOT_TOKEN в Railway (Settings -> Variables)")
        return
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", cmd_play))
    
    app.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(choose_language, pattern="^language$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_language(u,c,'ru'), pattern="^lang_ru$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_language(u,c,'en'), pattern="^lang_en$"))
    app.add_handler(CallbackQueryHandler(new_game, pattern="^new_game$"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^answer_yes$"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^answer_no$"))
    
    print("🤖 Бот успешно запущен!")
    print("✅ Доступные команды: /start, /play")
    app.run_polling()

if __name__ == "__main__":
    main()