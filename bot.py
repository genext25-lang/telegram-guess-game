import random
import logging
import sqlite3
import json
import urllib.request
import asyncio
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ========== НАСТРОЙКИ ==========
QUESTION_TIME_LIMIT = 30  # Секунд на ответ
MAX_QUESTION_HISTORY = 10  # Сколько последних вопросов запоминать

# ========== ЗАГРУЗКА ВОПРОСОВ ИЗ ИНТЕРНЕТА ==========
def load_questions_online():
    """Загружает вопросы из открытого API"""
    questions = {'ru': [], 'en': []}
    
    try:
        url = "https://opentdb.com/api.php?amount=50&type=boolean"
        
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
            for item in data['results']:
                import html
                question_text = html.unescape(item['question'])
                correct = item['correct_answer'] == "True"
                questions['en'].append((question_text, correct))
                
    except Exception as e:
        print(f"Не удалось загрузить вопросы из API: {e}")
    
    return questions

# ========== ВСТРОЕННЫЕ ВОПРОСЫ ==========
BUILTIN_QUESTIONS = {
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
        ("Солнце — это звезда", True),
        ("Луна сделана из сыра", False),
        ("У кошек 9 жизней", False),
        ("Человек может дышать под водой", False),
        ("Пауки — насекомые", False),
        ("Антарктида — пустыня", True),
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
        ("The Sun is a star", True),
        ("The Moon is made of cheese", False),
        ("Cats have 9 lives", False),
        ("Humans can breathe underwater", False),
        ("Spiders are insects", False),
        ("Antarctica is a desert", True),
    ]
}

ONLINE_QUESTIONS = load_questions_online()
QUESTIONS = {
    'ru': BUILTIN_QUESTIONS['ru'],
    'en': BUILTIN_QUESTIONS['en'] + ONLINE_QUESTIONS.get('en', [])
}

print(f"📚 Загружено вопросов: RU={len(QUESTIONS['ru'])}, EN={len(QUESTIONS['en'])}")

# ========== СИСТЕМА ПРЕДОТВРАЩЕНИЯ ПОВТОРОВ ==========
class QuestionManager:
    def __init__(self, max_history=10):
        self.user_history = {}
        self.max_history = max_history
    
    def get_unique_question(self, user_id, language):
        """Возвращает вопрос, который не был в истории"""
        questions_list = QUESTIONS[language]
        available_questions = []
        
        history = self.user_history.get(user_id, [])
        
        for q in questions_list:
            if q[0] not in history:
                available_questions.append(q)
        
        if not available_questions:
            self.user_history[user_id] = []
            available_questions = questions_list
        
        selected = random.choice(available_questions)
        
        if user_id not in self.user_history:
            self.user_history[user_id] = []
        
        self.user_history[user_id].append(selected[0])
        
        if len(self.user_history[user_id]) > self.max_history:
            self.user_history[user_id].pop(0)
        
        return selected
    
    def clear_history(self, user_id):
        if user_id in self.user_history:
            self.user_history[user_id] = []

question_manager = QuestionManager(max_history=MAX_QUESTION_HISTORY)

# ========== ПЕРЕВОДЫ ==========
TRANSLATIONS = {
    'ru': {
        'welcome': "🎮 *ИГРА «УГАДАЙ ДА/НЕТ»*\n\n📖 *Правила:*\n• Я даю утверждение\n• Ты отвечаешь ДА или НЕТ\n• За правильный ответ +1 очко\n• Ошибка = конец игры\n• На ответ даётся {} секунд!\n\n👇 *Выбери действие:*",
        'main_menu': "🏠 *ГЛАВНОЕ МЕНЮ*\n\nВыбери действие:",
        'new_game': "🎮 Новая игра",
        'leaderboard': "🏆 Таблица лидеров",
        'group_leaderboard': "🏆 Топ группы",
        'language': "🌐 Язык",
        'back': "🔙 Назад",
        'yes': "✅ ДА",
        'no': "❌ НЕТ",
        'game_start': "🎲 *ИГРА НАЧАЛАСЬ!*\n\n📢 *Вопрос:*\n{}\n\n⏱️ У тебя {} секунд!\n📊 Счёт: *0* очков\n\n✅ ДА или ❌ НЕТ?",
        'correct': "✅ *ПРАВИЛЬНО!* +1 очко\n\n📢 *Вопрос:*\n{}\n\n⏱️ У тебя {} секунд!\n📊 Счёт: *{}* очков",
        'game_over': "❌ *ИГРА ОКОНЧЕНА!*\n\nПравильный ответ: *{}*\nТы набрал(а): *{}* очков\n\n🏅 Твой лучший результат: *{}* очков",
        'timeout': "⏰ *ВРЕМЯ ВЫШЛО!*\n\nПравильный ответ: *{}*\nТы набрал(а): *{}* очков",
        'play_again': "🎮 Играть снова",
        'leaderboard_title': "🏆 *ТАБЛИЦА ЛИДЕРОВ* 🏆\n\n",
        'group_leaderboard_title': "🏆 *ТОП ГРУППЫ* 🏆\n\n",
        'no_players': "Пока никто не играл! Будь первым!",
        'welcome_group': "🎮 *Привет! Я игровой бот «Угадай Да/Нет»*\n\n📖 *Как играть:*\n• Напиши /play чтобы начать игру\n• Нажми /top — таблица лидеров\n• Нажми /grouptop — топ по группе\n\n⏱️ На ответ даётся {} секунд!\n\nУдачи! 🍀",
    },
    'en': {
        'welcome': "🎮 *GUESS YES/NO GAME*\n\n📖 *Rules:*\n• I give you a statement\n• You answer YES or NO\n• Correct answer gives +1 point\n• Wrong answer = game over\n• You have {} seconds to answer!\n\n👇 *Choose action:*",
        'main_menu': "🏠 *MAIN MENU*\n\nChoose action:",
        'new_game': "🎮 New Game",
        'leaderboard': "🏆 Leaderboard",
        'group_leaderboard': "🏆 Group Top",
        'language': "🌐 Language",
        'back': "🔙 Back",
        'yes': "✅ YES",
        'no': "❌ NO",
        'game_start': "🎲 *GAME STARTED!*\n\n📢 *Question:*\n{}\n\n⏱️ You have {} seconds!\n📊 Score: *0* points\n\n✅ YES or ❌ NO?",
        'correct': "✅ *CORRECT!* +1 point\n\n📢 *Question:*\n{}\n\n⏱️ You have {} seconds!\n📊 Score: *{}* points",
        'game_over': "❌ *GAME OVER!*\n\nCorrect answer: *{}*\nYou scored: *{}* points\n\n🏅 Your best score: *{}* points",
        'timeout': "⏰ *TIME IS OVER!*\n\nCorrect answer: *{}*\nYou scored: *{}* points",
        'play_again': "🎮 Play Again",
        'leaderboard_title': "🏆 *LEADERBOARD* 🏆\n\n",
        'group_leaderboard_title': "🏆 *GROUP TOP* 🏆\n\n",
        'no_players': "Nobody has played yet! Be the first!",
        'welcome_group': "🎮 *Hi! I'm the «Guess Yes/No» game bot*\n\n📖 *How to play:*\n• Type /play to start the game\n• Type /top — leaderboard\n• Type /grouptop — group top\n\n⏱️ You have {} seconds to answer!\n\nGood luck! 🍀",
    }
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
                games_played INTEGER DEFAULT 0,
                total_score INTEGER DEFAULT 0
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS group_stats (
                group_id INTEGER PRIMARY KEY,
                group_name TEXT,
                total_players INTEGER DEFAULT 0,
                total_games INTEGER DEFAULT 0,
                total_points INTEGER DEFAULT 0,
                record_score INTEGER DEFAULT 0,
                record_holder TEXT
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS group_scores (
                group_id INTEGER,
                user_id INTEGER,
                best_score INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                total_points INTEGER DEFAULT 0,
                PRIMARY KEY (group_id, user_id)
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
            return {'user_id': user_id, 'language': 'ru', 'best_score': 0, 'games_played': 0, 'total_score': 0}
        return {'user_id': user[0], 'language': user[4], 'best_score': user[5], 'games_played': user[6], 'total_score': user[7]}
    
    def update_score(self, user_id, score):
        user = self.get_or_create_user(user_id)
        is_record = False
        if score > user['best_score']:
            self.cursor.execute('UPDATE users SET best_score = ? WHERE user_id = ?', (score, user_id))
            is_record = True
        self.cursor.execute('UPDATE users SET total_score = total_score + ?, games_played = games_played + 1 WHERE user_id = ?', 
                          (score, user_id))
        self.conn.commit()
        return is_record
    
    def update_group_score(self, group_id, user_id, score, username=None):
        self.cursor.execute('SELECT * FROM group_scores WHERE group_id = ? AND user_id = ?', (group_id, user_id))
        existing = self.cursor.fetchone()
        if existing:
            if score > existing[3]:
                self.cursor.execute('UPDATE group_scores SET best_score = ?, games_played = games_played + 1, total_points = total_points + ? WHERE group_id = ? AND user_id = ?',
                                  (score, score, group_id, user_id))
            else:
                self.cursor.execute('UPDATE group_scores SET games_played = games_played + 1, total_points = total_points + ? WHERE group_id = ? AND user_id = ?',
                                  (score, group_id, user_id))
        else:
            self.cursor.execute('INSERT INTO group_scores (group_id, user_id, best_score, games_played, total_points) VALUES (?, ?, ?, 1, ?)',
                              (group_id, user_id, score, score))
        self.cursor.execute('SELECT * FROM group_stats WHERE group_id = ?', (group_id,))
        group = self.cursor.fetchone()
        if group:
            self.cursor.execute('SELECT COUNT(*) FROM group_scores WHERE group_id = ?', (group_id,))
            new_total_players = self.cursor.fetchone()[0]
            new_record = max(group[5], score)
            record_holder = group[6]
            if score > group[5]:
                new_record = score
                record_holder = username or str(user_id)
            self.cursor.execute('UPDATE group_stats SET total_players = ?, total_games = total_games + 1, total_points = total_points + ?, record_score = ?, record_holder = ? WHERE group_id = ?',
                              (new_total_players, score, new_record, record_holder, group_id))
        else:
            self.cursor.execute('INSERT INTO group_stats (group_id, total_players, total_games, total_points, record_score, record_holder) VALUES (?, 1, 1, ?, ?, ?)',
                              (group_id, score, score, username or str(user_id)))
        self.conn.commit()
    
    def get_group_leaderboard(self, group_id, limit=10):
        self.cursor.execute('SELECT user_id, best_score, games_played, total_points FROM group_scores WHERE group_id = ? AND games_played > 0 ORDER BY best_score DESC, total_points DESC LIMIT ?', (group_id, limit))
        return self.cursor.fetchall()
    
    def get_group_stats(self, group_id):
        self.cursor.execute('SELECT * FROM group_stats WHERE group_id = ?', (group_id,))
        return self.cursor.fetchone()
    
    def get_leaderboard(self, limit=10):
        self.cursor.execute('SELECT username, first_name, best_score, games_played, total_score FROM users WHERE games_played > 0 ORDER BY best_score DESC, total_score DESC LIMIT ?', (limit,))
        return self.cursor.fetchall()
    
    def get_user_stats(self, user_id):
        user = self.get_or_create_user(user_id)
        self.cursor.execute('SELECT COUNT(*) + 1 FROM users WHERE best_score > ?', (user['best_score'],))
        rank = self.cursor.fetchone()[0]
        return {'best_score': user['best_score'], 'games_played': user['games_played'], 'total_score': user['total_score'], 'rank': rank}
    
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
game_timers = {}

async def cancel_timer(user_id):
    if user_id in game_timers:
        game_timers[user_id].cancel()
        del game_timers[user_id]

async def game_timeout(user_id, chat_id, message_id):
    await asyncio.sleep(QUESTION_TIME_LIMIT)
    if user_id in user_games:
        game = user_games[user_id]
        lang = db.get_or_create_user(user_id)['language']
        correct_word = "ДА" if game['correct_answer'] else "НЕТ" if lang == 'ru' else "YES" if game['correct_answer'] else "NO"
        db.update_score(user_id, game['score'])
        if chat_id and chat_id < 0:
            db.update_group_score(chat_id, user_id, game['score'])
        del user_games[user_id]
        if user_id in game_timers:
            del game_timers[user_id]
        try:
            keyboard = [[InlineKeyboardButton(get_text(user_id, 'play_again'), callback_data="new_game")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.edit_message_text(get_text(user_id, 'timeout', correct_word, game['score']), chat_id=chat_id, message_id=message_id, parse_mode="Markdown", reply_markup=reply_markup)
        except:
            pass

# ========== ОБРАБОТЧИКИ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    keyboard = [[InlineKeyboardButton(get_text(user.id, 'new_game'), callback_data="new_game")],
                [InlineKeyboardButton(get_text(user.id, 'leaderboard'), callback_data="leaderboard")],
                [InlineKeyboardButton(get_text(user.id, 'language'), callback_data="language")]]
    if update.effective_chat and update.effective_chat.type in ['group', 'supergroup']:
        keyboard.insert(1, [InlineKeyboardButton(get_text(user.id, 'group_leaderboard'), callback_data="group_leaderboard")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(get_text(user.id, 'welcome', QUESTION_TIME_LIMIT), parse_mode="Markdown", reply_markup=reply_markup)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    keyboard = [[InlineKeyboardButton(get_text(user_id, 'new_game'), callback_data="new_game")],
                [InlineKeyboardButton(get_text(user_id, 'leaderboard'), callback_data="leaderboard")],
                [InlineKeyboardButton(get_text(user_id, 'language'), callback_data="language")]]
    chat_id = update.effective_chat.id
    if chat_id < 0:
        keyboard.insert(1, [InlineKeyboardButton(get_text(user_id, 'group_leaderboard'), callback_data="group_leaderboard")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(get_text(user_id, 'main_menu'), parse_mode="Markdown", reply_markup=reply_markup)

async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    keyboard = [[InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"), InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
                [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("🌐 Выбери язык / Choose language:", reply_markup=reply_markup)

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    db.set_language(user_id, lang)
    await main_menu(update, context)

async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    top_players = db.get_leaderboard(10)
    if not top_players:
        text = get_text(user_id, 'leaderboard_title') + get_text(user_id, 'no_players')
    else:
        text = get_text(user_id, 'leaderboard_title')
        for i, (username, first_name, best_score, games_played, total_score) in enumerate(top_players, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            name = first_name or username or "Игрок"
            if len(name) > 20:
                name = name[:17] + "..."
            text += f"{medal} *{name}*\n   🏆 {best_score} очков | 🎮 {games_played} игр\n\n"
    keyboard = [[InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def show_group_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if chat_id > 0:
        await query.edit_message_text("❌ Эта команда только для групп!")
        return
    group_top = db.get_group_leaderboard(chat_id, 10)
    text = get_text(user_id, 'group_leaderboard_title')
    if not group_top:
        text += get_text(user_id, 'no_players')
    else:
        for i, (uid, best_score, games_played, total_points) in enumerate(group_top, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            try:
                user = await context.bot.get_chat(uid)
                name = user.first_name or str(uid)
            except:
                name = str(uid)
            if len(name) > 20:
                name = name[:17] + "..."
            text += f"{medal} *{name}*\n   🏆 {best_score} очков | 🎮 {games_played} игр\n\n"
    keyboard = [[InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang = db.get_or_create_user(user_id)['language']
    await cancel_timer(user_id)
    question, correct_answer = question_manager.get_unique_question(user_id, lang)
    user_games[user_id] = {'score': 0, 'correct_answer': correct_answer, 'current_question': question}
    keyboard = [[InlineKeyboardButton(get_text(user_id, 'yes'), callback_data="answer_yes"), InlineKeyboardButton(get_text(user_id, 'no'), callback_data="answer_no")],
                [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    sent_message = await query.edit_message_text(get_text(user_id, 'game_start', question, QUESTION_TIME_LIMIT), parse_mode="Markdown", reply_markup=reply_markup)
    timer_task = asyncio.create_task(game_timeout(user_id, chat_id, sent_message.message_id))
    game_timers[user_id] = timer_task

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang = db.get_or_create_user(user_id)['language']
    await cancel_timer(user_id)
    is_yes = query.data == "answer_yes"
    game = user_games.get(user_id)
    if not game:
        await query.edit_message_text("Ошибка! Начни игру заново.")
        return
    correct_answer = game['correct_answer']
    current_score = game['score']
    if is_yes == correct_answer:
        current_score += 1
        question, new_correct = question_manager.get_unique_question(user_id, lang)
        user_games[user_id] = {'score': current_score, 'correct_answer': new_correct, 'current_question': question}
        keyboard = [[InlineKeyboardButton(get_text(user_id, 'yes'), callback_data="answer_yes"), InlineKeyboardButton(get_text(user_id, 'no'), callback_data="answer_no")],
                    [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        sent_message = await query.edit_message_text(get_text(user_id, 'correct', question, QUESTION_TIME_LIMIT, current_score), parse_mode="Markdown", reply_markup=reply_markup)
        timer_task = asyncio.create_task(game_timeout(user_id, chat_id, sent_message.message_id))
        game_timers[user_id] = timer_task
    else:
        correct_word = "ДА" if correct_answer else "НЕТ" if lang == 'ru' else "YES" if correct_answer else "NO"
        is_record = db.update_score(user_id, current_score)
        if chat_id < 0:
            user = update.effective_user
            db.update_group_score(chat_id, user_id, current_score, user.first_name)
        stats = db.get_user_stats(user_id)
        del user_games[user_id]
        keyboard = [[InlineKeyboardButton(get_text(user_id, 'play_again'), callback_data="new_game")],
                    [InlineKeyboardButton(get_text(user_id, 'leaderboard'), callback_data="leaderboard")],
                    [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = get_text(user_id, 'game_over', correct_word, current_score, stats['best_score'])
        if is_record and current_score > 0:
            message += "\n\n🎉 *НОВЫЙ РЕКОРД!* 🎉"
        message += f"\n\n📊 *Твоё место: {stats['rank']}*"
        await query.edit_message_text(message, parse_mode="Markdown", reply_markup=reply_markup)

async def group_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if chat_id > 0:
        await update.message.reply_text("❌ Эта команда только для групп!")
        return
    group_top = db.get_group_leaderboard(chat_id, 10)
    lang = db.get_or_create_user(user_id)['language']
    if not group_top:
        text = get_text(user_id, 'no_players')
    else:
        text = "🏆 *ТОП ГРУППЫ* 🏆\n\n"
        for i, (uid, best_score, games_played, total_points) in enumerate(group_top, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            try:
                user = await context.bot.get_chat(uid)
                name = user.first_name or str(uid)
            except:
                name = str(uid)
            if len(name) > 20:
                name = name[:17] + "..."
            text += f"{medal} *{name}*\n   🏆 {best_score} очков | 🎮 {games_played} игр\n\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def welcome_new_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            await update.message.reply_text(TRANSLATIONS['ru']['welcome_group'].format(QUESTION_TIME_LIMIT), parse_mode="Markdown")
            return

async def cmd_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang = db.get_or_create_user(user_id)['language']
    await cancel_timer(user_id)
    question, correct_answer = question_manager.get_unique_question(user_id, lang)
    user_games[user_id] = {'score': 0, 'correct_answer': correct_answer, 'current_question': question}
    keyboard = [[InlineKeyboardButton(get_text(user_id, 'yes'), callback_data="answer_yes"), InlineKeyboardButton(get_text(user_id, 'no'), callback_data="answer_no")],
                [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    sent_message = await update.message.reply_text(get_text(user_id, 'game_start', question, QUESTION_TIME_LIMIT), parse_mode="Markdown", reply_markup=reply_markup, reply_to_message_id=update.message.message_id)
    timer_task = asyncio.create_task(game_timeout(user_id, chat_id, sent_message.message_id))
    game_timers[user_id] = timer_task

# ========== ЗАПУСК ==========
def main():
    import os
    TOKEN = os.environ.get("Yes_0r_No_Bot")
    if not TOKEN:
        print("❌ Ошибка: BOT_TOKEN не найден!")
        return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", cmd_play))
    app.add_handler(CommandHandler("grouptop", group_top))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_bot))
    app.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(choose_language, pattern="^language$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_language(u,c,'ru'), pattern="^lang_ru$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_language(u,c,'en'), pattern="^lang_en$"))
    app.add_handler(CallbackQueryHandler(new_game, pattern="^new_game$"))
    app.add_handler(CallbackQueryHandler(show_leaderboard, pattern="^leaderboard$"))
    app.add_handler(CallbackQueryHandler(show_group_leaderboard, pattern="^group_leaderboard$"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^answer_yes$"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^answer_no$"))
    print("🤖 Бот успешно запущен!")
    print("✅ Добавлена система предотвращения повторов вопросов (история 10 вопросов)")
    app.run_polling()

if __name__ == "__main__":
    main()