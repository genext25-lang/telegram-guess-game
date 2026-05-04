```python
import random
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Включи логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# ========== ПЕРЕВОДЫ ==========
TRANSLATIONS = {
    'ru': {
        'welcome': "🎮 *ИГРА «УГАДАЙ ДА/НЕТ» v2.0*\n\n📖 *Правила:*\n• Я даю утверждение\n• Ты отвечаешь ✅ ДА или ❌ НЕТ\n• За правильный ответ +1 или +2 очка (зависит от сложности)\n• Ошибка = конец игры (счёт сохраняется!)\n• Можно выбрать сложность: ЛЁГКИЕ или СЛОЖНЫЕ вопросы\n• Серия правильных ответов открывает ДОСТИЖЕНИЯ!\n• Каждый день получай БОНУСНЫЕ очки!\n\n👇 *Выбери действие:*",
        'main_menu': "🏠 *ГЛАВНОЕ МЕНЮ*\n\nВыбери действие:",
        'new_game': "🎮 Новая игра",
        'daily_bonus': "💰 Ежедневный бонус",
        'leaderboard': "🏆 Таблица лидеров",
        'stats': "📊 Моя статистика",
        'achievements': "🏅 Мои достижения",
        'language': "🌐 Язык / Language",
        'choose_difficulty': "🎲 *ВЫБЕРИ СЛОЖНОСТЬ*\n\n🌱 *Лёгкие вопросы* — простые факты, +1 очко за ответ\n⚡ *Сложные вопросы* — каверзные вопросы, +2 очка за ответ\n\nКакую сложность выберешь?",
        'difficulty_easy': "🌱 ЛЁГКИЕ (+1 очко)",
        'difficulty_hard': "⚡ СЛОЖНЫЕ (+2 очка)",
        'game_start': "{} *ИГРА НАЧАЛАСЬ!*\nСложность: *{}* (+{} очков за ответ)\n\n📢 *Вопрос:*\n{}\n\n📊 Счёт: *0* очков\n⭐ Серия: *0* ответов\n\n✅ ДА или ❌ НЕТ?",
        'correct': "✅ *ПРАВИЛЬНО!* +{} очков\n🔥 Серия: *{}* ответов подряд!\n\n",
        'new_achievement': "{} *НОВОЕ ДОСТИЖЕНИЕ!*\n*{}*\n{}\n\n",
        'next_question': "📢 *Следующий вопрос:*\n{}\n\n📊 Счёт: *{}* очков\n⭐ Серия: *{}*\n✅ ДА или ❌ НЕТ?",
        'game_over': "❌ *ИГРА ОКОНЧЕНА!*\n\nПравильный ответ: *{}*\nТы набрал(а): *{}* очков\nМаксимальная серия: *{}* ответов подряд\n\n🏅 Твой лучший результат: *{}* очков\n🎯 Всего сыграно игр: *{}*\n\n💪 Не сдавайся! Попробуй ещё раз!",
        'play_again': "🎮 Играть снова",
        'back': "🔙 Назад",
        'yes': "✅ ДА",
        'no': "❌ НЕТ",
        'daily_bonus_title': "💰 *ЕЖЕДНЕВНЫЙ БОНУС!*\n\nТы получил(а) *+{}* очков!\nЗаходи завтра снова!\n\nТвой общий счёт: *{}* очков",
        'daily_bonus_already': "⏰ *БОНУС УЖЕ ПОЛУЧЕН!*\n\nТы уже получал бонус сегодня.\nВозвращайся завтра! 🌟",
        'achievements_title': "🏅 *МОИ ДОСТИЖЕНИЯ* 🏅\n\n",
        'no_achievements': "Пока нет достижений. Играй и открывай новые!\n\n",
        'available_achievements': "\n*Доступные достижения:*\n",
        'leaderboard_title': "🏆 *ТАБЛИЦА ЛИДЕРОВ TOP-10* 🏆\n\n",
        'no_players': "Пока никто не играл! Будь первым! 🎮",
        'stats_title': "📊 *ТВОЯ СТАТИСТИКА*\n\n",
        'best_score': "🏆 Лучший результат: *{}* очков",
        'games_played': "🎮 Сыграно игр: *{}*",
        'total_score': "⭐ Всего очков: *{}*",
        'total_correct': "🎯 Правильных ответов: *{}*",
        'average_score': "📈 Средний результат: *{}* очков",
        'achievements_count': "🏅 Получено достижений: *{}/{}*",
        'continue_playing': "\n\n💪 Продолжай играть, чтобы улучшить рекорд!",
        'language_changed': "🌐 *Язык изменён на: {}*\n\nLanguage changed to: {}",
        'select_language': "🌐 *ВЫБЕРИ ЯЗЫК / SELECT LANGUAGE*\n\nРусский или English?",
        'russian': "🇷🇺 Русский",
        'english': "🇬🇧 English"
    },
    'en': {
        'welcome': "🎮 *GUESS YES/NO GAME v2.0*\n\n📖 *Rules:*\n• I give you a statement\n• You answer ✅ YES or ❌ NO\n• Correct answer gives +1 or +2 points (depends on difficulty)\n• Wrong answer = game over (score is saved!)\n• Choose difficulty: EASY or HARD questions\n• Streak of correct answers unlocks ACHIEVEMENTS!\n• Get BONUS points every day!\n\n👇 *Choose action:*",
        'main_menu': "🏠 *MAIN MENU*\n\nChoose action:",
        'new_game': "🎮 New Game",
        'daily_bonus': "💰 Daily Bonus",
        'leaderboard': "🏆 Leaderboard",
        'stats': "📊 My Stats",
        'achievements': "🏅 My Achievements",
        'language': "🌐 Language",
        'choose_difficulty': "🎲 *CHOOSE DIFFICULTY*\n\n🌱 *Easy questions* — simple facts, +1 point per answer\n⚡ *Hard questions* — tricky questions, +2 points per answer\n\nWhat difficulty do you choose?",
        'difficulty_easy': "🌱 EASY (+1 point)",
        'difficulty_hard': "⚡ HARD (+2 points)",
        'game_start': "{} *GAME STARTED!*\nDifficulty: *{}* (+{} points per answer)\n\n📢 *Question:*\n{}\n\n📊 Score: *0* points\n⭐ Streak: *0* answers\n\n✅ YES or ❌ NO?",
        'correct': "✅ *CORRECT!* +{} points\n🔥 Streak: *{}* answers in a row!\n\n",
        'new_achievement': "{} *NEW ACHIEVEMENT!*\n*{}*\n{}\n\n",
        'next_question': "📢 *Next question:*\n{}\n\n📊 Score: *{}* points\n⭐ Streak: *{}*\n✅ YES or ❌ NO?",
        'game_over': "❌ *GAME OVER!*\n\nCorrect answer: *{}*\nYou scored: *{}* points\nMax streak: *{}* answers in a row\n\n🏅 Your best score: *{}* points\n🎯 Games played: *{}*\n\n💪 Don't give up! Try again!",
        'play_again': "🎮 Play Again",
        'back': "🔙 Back",
        'yes': "✅ YES",
        'no': "❌ NO",
        'daily_bonus_title': "💰 *DAILY BONUS!*\n\nYou received *+{}* points!\nCome back tomorrow!\n\nYour total score: *{}* points",
        'daily_bonus_already': "⏰ *BONUS ALREADY CLAIMED!*\n\nYou've already claimed your daily bonus today.\nCome back tomorrow! 🌟",
        'achievements_title': "🏅 *MY ACHIEVEMENTS* 🏅\n\n",
        'no_achievements': "No achievements yet. Play and unlock new ones!\n\n",
        'available_achievements': "\n*Available achievements:*\n",
        'leaderboard_title': "🏆 *LEADERBOARD TOP-10* 🏆\n\n",
        'no_players': "Nobody has played yet! Be the first! 🎮",
        'stats_title': "📊 *YOUR STATISTICS*\n\n",
        'best_score': "🏆 Best score: *{}* points",
        'games_played': "🎮 Games played: *{}*",
        'total_score': "⭐ Total points: *{}*",
        'total_correct': "🎯 Correct answers: *{}*",
        'average_score': "📈 Average score: *{}* points",
        'achievements_count': "🏅 Achievements earned: *{}/{}*",
        'continue_playing': "\n\n💪 Keep playing to improve your record!",
        'language_changed': "🌐 *Language changed to: {}*\n\nЯзык изменён на: {}",
        'select_language': "🌐 *SELECT LANGUAGE*\n\nРусский or English?",
        'russian': "🇷🇺 Русский",
        'english': "🇬🇧 English"
    }
}

# ========== ВОПРОСЫ НА ДВУХ ЯЗЫКАХ ==========
QUESTIONS = {
    'easy': {
        'ru': [
            ("Земля вращается вокруг Солнца", True),
            ("Рыбы умеют дышать под водой", True),
            ("У собак 4 лапы", True),
            ("Вода мокрая", True),
            ("Снег белого цвета", True),
            ("Птицы умеют летать", True),
            ("Яблоко - это фрукт", True),
            ("Ночью темно, потому что солнце садится", True),
            ("Коровы дают молоко", True),
            ("Лёд - это замёрзшая вода", True),
            ("Человек имеет 2 руки и 2 ноги", True),
            ("Солнце встаёт на востоке", True),
            ("Автомобили ездят по дорогам", True),
            ("Книги можно читать", True),
            ("Компьютеры работают от электричества", True),
        ],
        'en': [
            ("The Earth revolves around the Sun", True),
            ("Fish can breathe underwater", True),
            ("Dogs have 4 legs", True),
            ("Water is wet", True),
            ("Snow is white", True),
            ("Birds can fly", True),
            ("Apple is a fruit", True),
            ("It's dark at night because the sun sets", True),
            ("Cows give milk", True),
            ("Ice is frozen water", True),
            ("Humans have 2 arms and 2 legs", True),
            ("The sun rises in the east", True),
            ("Cars drive on roads", True),
            ("Books can be read", True),
            ("Computers work on electricity", True),
        ]
    },
    'hard': {
        'ru': [
            ("Общая протяжённость кровеносных сосудов в теле человека составляет около 100 000 км", True),
            ("У осьминога три сердца", True),
            ("Банан — это ягода", True),
            ("Страусы прячут голову в песок, когда пугаются", False),
            ("Человек и банан имеют примерно 50% общих генов", True),
            ("Антарктида — самая большая пустыня в мире", True),
            ("Великая Китайская стена видна из космоса", False),
            ("Клеопатра жила ближе к изобретению iPhone, чем к строительству пирамид", True),
            ("У кошек более 100 различных звуков в арсенале", True),
            ("Молния может ударить в одно место дважды", True),
            ("Ватикан — самая маленькая страна в мире", True),
            ("Бетховен был глухим, когда написал свою знаменитую Симфонию №9", True),
            ("У картофеля больше хромосом, чем у человека", False),
            ("Ананас растёт на дереве", False),
            ("Сердце креветки находится в голове", True),
            ("Улитки могут спать 3 года", True),
            ("Венера — единственная планета, вращающаяся по часовой стрелке", True),
            ("Носороги имеют кости из чистого кальция", False),
        ],
        'en': [
            ("The total length of blood vessels in the human body is about 100,000 km", True),
            ("Octopuses have three hearts", True),
            ("Banana is a berry", True),
            ("Ostriches bury their heads in the sand when scared", False),
            ("Humans and bananas share about 50% of their genes", True),
            ("Antarctica is the largest desert in the world", True),
            ("The Great Wall of China is visible from space", False),
            ("Cleopatra lived closer to the invention of the iPhone than to the building of the pyramids", True),
            ("Cats have over 100 different sounds in their arsenal", True),
            ("Lightning can strike the same place twice", True),
            ("Vatican City is the smallest country in the world", True),
            ("Beethoven was deaf when he wrote his famous Symphony No. 9", True),
            ("Potatoes have more chromosomes than humans", False),
            ("Pineapples grow on trees", False),
            ("A shrimp's heart is in its head", True),
            ("Snails can sleep for 3 years", True),
            ("Venus is the only planet that rotates clockwise", True),
            ("Rhinos have bones made of pure calcium", False),
        ]
    }
}

# ========== ДОСТИЖЕНИЯ ==========
ACHIEVEMENTS = {
    5: {"name_ru": "🌟 НОВИЧОК", "name_en": "🌟 BEGINNER", "description_ru": "5 правильных ответов подряд", "description_en": "5 correct answers in a row", "emoji": "🌱"},
    10: {"name_ru": "⚡ ЭКСПЕРТ", "name_en": "⚡ EXPERT", "description_ru": "10 правильных ответов подряд", "description_en": "10 correct answers in a row", "emoji": "⚡"},
    15: {"name_ru": "🔥 МАСТЕР", "name_en": "🔥 MASTER", "description_ru": "15 правильных ответов подряд", "description_en": "15 correct answers in a row", "emoji": "🔥"},
    20: {"name_ru": "🏆 ЛЕГЕНДА", "name_en": "🏆 LEGEND", "description_ru": "20 правильных ответов подряд", "description_en": "20 correct answers in a row", "emoji": "🏆"},
    30: {"name_ru": "👑 БОГ", "name_en": "👑 GOD", "description_ru": "30 правильных ответов подряд", "description_en": "30 correct answers in a row", "emoji": "👑"},
    50: {"name_ru": "💎 НЕПОБЕДИМЫЙ", "name_en": "💎 INVINCIBLE", "description_ru": "50 правильных ответов подряд", "description_en": "50 correct answers in a row", "emoji": "💎"},
}

# ========== БАЗА ДАННЫХ (SQLite) ==========
class Database:
    def __init__(self, db_name="game_bot.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_tables()
    
    def _create_tables(self):
        """Создаём таблицы, если их нет"""
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
                daily_bonus_date TEXT,
                daily_bonus_claimed INTEGER DEFAULT 0
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
    
    def get_or_create_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> Dict:
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = self.cursor.fetchone()
        
        if not user:
            self.cursor.execute('''
                INSERT INTO users (user_id, username, first_name, last_name, language, total_score, games_played, best_score, total_correct, last_played, daily_bonus_claimed)
                VALUES (?, ?, ?, ?, 'ru', 0, 0, 0, 0, ?, 0)
            ''', (user_id, username, first_name, last_name, datetime.now()))
            self.conn.commit()
            return {
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'last_name': last_name,
                'language': 'ru',
                'total_score': 0,
                'games_played': 0,
                'best_score': 0,
                'total_correct': 0,
                'last_played': datetime.now(),
                'daily_bonus_claimed': 0
            }
        
        return {
            'user_id': user[0],
            'username': user[1],
            'first_name': user[2],
            'last_name': user[3],
            'language': user[4],
            'total_score': user[5],
            'games_played': user[6],
            'best_score': user[7],
            'total_correct': user[8],
            'last_played': user[9],
            'daily_bonus_date': user[10] if len(user) > 10 else None,
            'daily_bonus_claimed': user[11] if len(user) > 11 else 0
        }
    
    def set_language(self, user_id: int, language: str):
        self.cursor.execute('UPDATE users SET language = ? WHERE user_id = ?', (language, user_id))
        self.conn.commit()
    
    def update_user_stats(self, user_id: int, score: int, correct_count: int = 0):
        self.cursor.execute('''
            UPDATE users 
            SET total_score = total_score + ?,
                games_played = games_played + 1,
                best_score = MAX(best_score, ?),
                total_correct = total_correct + ?,
                last_played = ?
            WHERE user_id = ?
        ''', (score, score, correct_count, datetime.now(), user_id))
        self.conn.commit()
    
    def claim_daily_bonus(self, user_id: int) -> int:
        today = datetime.now().date().isoformat()
        self.cursor.execute('SELECT daily_bonus_date FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        
        if result and result[0] == today:
            return 0
        
        bonus = random.randint(5, 15)
        self.cursor.execute('''
            UPDATE users 
            SET daily_bonus_date = ?, daily_bonus_claimed = 1,
                total_score = total_score + ?
            WHERE user_id = ?
        ''', (today, bonus, user_id))
        self.conn.commit()
        return bonus
    
    def check_daily_bonus_available(self, user_id: int) -> bool:
        self.cursor.execute('SELECT daily_bonus_date FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return not result or result[0] != datetime.now().date().isoformat()
    
    def unlock_achievement(self, user_id: int, streak: int) -> Optional[Dict]:
        if streak in ACHIEVEMENTS:
            self.cursor.execute('SELECT 1 FROM user_achievements WHERE user_id = ? AND achievement_id = ?', 
                              (user_id, streak))
            if not self.cursor.fetchone():
                self.cursor.execute('''
                    INSERT INTO user_achievements (user_id, achievement_id, achieved_at)
                    VALUES (?, ?, ?)
                ''', (user_id, streak, datetime.now()))
                self.conn.commit()
                return ACHIEVEMENTS[streak]
        return None
    
    def get_user_achievements(self, user_id: int) -> List[Dict]:
        self.cursor.execute('SELECT achievement_id, achieved_at FROM user_achievements WHERE user_id = ? ORDER BY achievement_id', (user_id,))
        achievements = []
        for achievement_id, achieved_at in self.cursor.fetchall():
            if achievement_id in ACHIEVEMENTS:
                achievements.append({
                    'id': achievement_id,
                    'data': ACHIEVEMENTS[achievement_id],
                    'achieved_at': achieved_at
                })
        return achievements
    
    def get_top_players(self, limit: int = 10) -> List[Tuple]:
        self.cursor.execute('''
            SELECT username, first_name, best_score, games_played, total_correct 
            FROM users 
            WHERE games_played > 0
            ORDER BY best_score DESC, total_correct DESC
            LIMIT ?
        ''', (limit,))
        return self.cursor.fetchall()
    
    def save_game_state(self, user_id: int, score: int, difficulty: str, streak: int, question: str, correct_answer: bool):
        self.cursor.execute('''
            INSERT OR REPLACE INTO active_games (user_id, current_score, difficulty, streak, question, correct_answer, started_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, score, difficulty, streak, question, correct_answer, datetime.now()))
        self.conn.commit()
    
    def load_game_state(self, user_id: int) -> Optional[Dict]:
        self.cursor.execute('SELECT * FROM active_games WHERE user_id = ?', (user_id,))
        game = self.cursor.fetchone()
        if game:
            return {
                'user_id': game[0],
                'current_score': game[1],
                'difficulty': game[2],
                'streak': game[3],
                'question': game[4],
                'correct_answer': bool(game[5]),
                'started_at': game[6]
            }
        return None
    
    def clear_game_state(self, user_id: int):
        self.cursor.execute('DELETE FROM active_games WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def close(self):
        self.conn.close()

# ========== ОСНОВНАЯ ЛОГИКА БОТА ==========
db = Database()

def get_text(user_id: int, key: str, *args) -> str:
    """Получить текст на языке пользователя"""
    user = db.get_or_create_user(user_id)
    lang = user.get('language', 'ru')
    text = TRANSLATIONS[lang].get(key, TRANSLATIONS['ru'][key])
    if args:
        return text.format(*args)
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    
    keyboard = [
        [InlineKeyboardButton(get_text(user.id, 'new_game'), callback_data="choose_difficulty")],
        [InlineKeyboardButton(get_text(user.id, 'daily_bonus'), callback_data="daily_bonus")],
        [InlineKeyboardButton(get_text(user.id, 'leaderboard'), callback_data="leaderboard")],
        [InlineKeyboardButton(get_text(user.id, 'stats'), callback_data="stats")],
        [InlineKeyboardButton(get_text(user.id, 'achievements'), callback_data="achievements")],
        [InlineKeyboardButton(get_text(user.id, 'language'), callback_data="language")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        get_text(user.id, 'welcome'),
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выбор языка"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton(get_text(user_id, 'russian'), callback_data="lang_ru")],
        [InlineKeyboardButton(get_text(user_id, 'english'), callback_data="lang_en")],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        get_text(user_id, 'select_language'),
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str) -> None:
    """Установить язык"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    db.set_language(user_id, lang)
    
    # Обновляем клавиатуру на новом языке
    keyboard = [
        [InlineKeyboardButton(get_text(user_id, 'new_game'), callback_data="choose_difficulty")],
        [InlineKeyboardButton(get_text(user_id, 'daily_bonus'), callback_data="daily_bonus")],
        [InlineKeyboardButton(get_text(user_id, 'leaderboard'), callback_data="leaderboard")],
        [InlineKeyboardButton(get_text(user_id, 'stats'), callback_data="stats")],
        [InlineKeyboardButton(get_text(user_id, 'achievements'), callback_data="achievements")],
        [InlineKeyboardButton(get_text(user_id, 'language'), callback_data="language")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    lang_name = "Russian" if lang == 'ru' else "English"
    await query.edit_message_text(
        get_text(user_id, 'language_changed').format(lang_name, lang_name),
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def choose_difficulty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выбор сложности"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton(get_text(user_id, 'difficulty_easy'), callback_data="difficulty_easy")],
        [InlineKeyboardButton(get_text(user_id, 'difficulty_hard'), callback_data="difficulty_hard")],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        get_text(user_id, 'choose_difficulty'),
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE, difficulty: str) -> None:
    """Начать игру"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    db.clear_game_state(user_id)
    context.user_data.clear()
    
    lang = db.get_or_create_user(user_id)['language']
    context.user_data['difficulty'] = difficulty
    context.user_data['current_score'] = 0
    context.user_data['streak'] = 0
    
    questions_list = QUESTIONS[difficulty][lang]
    question, correct_answer = random.choice(questions_list)
    context.user_data['current_question'] = question
    context.user_data['correct_answer'] = correct_answer
    
    db.save_game_state(user_id, 0, difficulty, 0, question, correct_answer)
    
    points_per_question = 1 if difficulty == 'easy' else 2
    difficulty_emoji = "🌱" if difficulty == 'easy' else "⚡"
    difficulty_name = get_text(user_id, 'difficulty_easy').split(" ")[1] if difficulty == 'easy' else get_text(user_id, 'difficulty_hard').split(" ")[1]
    
    keyboard = [
        [InlineKeyboardButton(get_text(user_id, 'yes'), callback_data="yes"), InlineKeyboardButton(get_text(user_id, 'no'), callback_data="no")],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        get_text(user_id, 'game_start').format(difficulty_emoji, difficulty_name, points_per_question, question),
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка ответа"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user_choice = query.data
    lang = db.get_or_create_user(user_id)['language']
    
    difficulty = context.user_data.get('difficulty')
    correct = context.user_data.get('correct_answer')
    current_score = context.user_data.get('current_score', 0)
    streak = context.user_data.get('streak', 0)
    
    if difficulty is None:
        saved_game = db.load_game_state(user_id)
        if saved_game:
            difficulty = saved_game['difficulty']
            current_score = saved_game['current_score']
            streak = saved_game['streak']
            correct = saved_game['correct_answer']
            context.user_data.update({
                'difficulty': difficulty,
                'current_score': current_score,
                'streak': streak,
                'correct_answer': correct
            })
    
    if not correct:
        await query.edit_message_text("❌ Error! Start a new game from the main menu.")
        return
    
    is_correct = (user_choice == 'yes' and correct is True) or (user_choice == 'no' and correct is False)
    points_per_question = 1 if difficulty == 'easy' else 2
    
    if is_correct:
        current_score += points_per_question
        streak += 1
        context.user_data['current_score'] = current_score
        context.user_data['streak'] = streak
        
        new_achievement = db.unlock_achievement(user_id, streak)
        
        questions_list = QUESTIONS[difficulty][lang]
        question, correct_answer = random.choice(questions_list)
        context.user_data['current_question'] = question
        context.user_data['correct_answer'] = correct_answer
        
        db.save_game_state(user_id, current_score, difficulty, streak, question, correct_answer)
        
        keyboard = [
            [InlineKeyboardButton(get_text(user_id, 'yes'), callback_data="yes"), InlineKeyboardButton(get_text(user_id, 'no'), callback_data="no")],
            [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = get_text(user_id, 'correct').format(points_per_question, streak)
        
        if new_achievement:
            ach_name = new_achievement[f'name_{lang}']
            ach_desc = new_achievement[f'description_{lang}']
            message += get_text(user_id, 'new_achievement').format(new_achievement['emoji'], ach_name, ach_desc)
        
        message += get_text(user_id, 'next_question').format(question, current_score, streak)
        
        await query.edit_message_text(message, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        db.update_user_stats(user_id, current_score, streak)
        db.clear_game_state(user_id)
        user_data = db.get_or_create_user(user_id)
        
        keyboard = [
            [InlineKeyboardButton(get_text(user_id, 'play_again'), callback_data="choose_difficulty")],
            [InlineKeyboardButton(get_text(user_id, 'leaderboard'), callback_data="leaderboard")],
            [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            get_text(user_id, 'game_over').format(
                'ДА' if correct else 'НЕТ' if lang == 'ru' else 'YES' if correct else 'NO',
                current_score, streak, user_data['best_score'], user_data['games_played'] + 1
            ),
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        context.user_data.clear()

async def daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ежедневный бонус"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if db.check_daily_bonus_available(user_id):
        bonus = db.claim_daily_bonus(user_id)
        user_data = db.get_or_create_user(user_id)
        keyboard = [[InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            get_text(user_id, 'daily_bonus_title').format(bonus, user_data['total_score']),
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        keyboard = [[InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            get_text(user_id, 'daily_bonus_already'),
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

async def show_achievements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать достижения"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    lang = db.get_or_create_user(user_id)['language']
    
    user_achievements = db.get_user_achievements(user_id)
    
    text = get_text(user_id, 'achievements_title')
    
    if not user_achievements:
        text += get_text(user_id, 'no_achievements')
    else:
        for ach in user_achievements:
            name = ach['data'][f'name_{lang}']
            desc = ach['data'][f'description_{lang}']
            text += f"{ach['data']['emoji']} *{name}*\n   {desc}\n   🎉 Получено: {ach['achieved_at'][:10]}\n\n"
    
    text += get_text(user_id, 'available_achievements')
    for streak, data in ACHIEVEMENTS.items():
        if streak not in [a['id'] for a in user_achievements]:
            name = data[f'name_{lang}']
            desc = data[f'description_{lang}']
            text += f"{data['emoji']} {name} — {desc}\n"
    
    keyboard = [[InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Таблица лидеров"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    top_players = db.get_top_players(10)
    
    if not top_players:
        text = f"🏆 *{get_text(user_id, 'leaderboard_title')}*{get_text(user_id, 'no_players')}"
    else:
        text = get_text(user_id, 'leaderboard_title')
        for i, (username, first_name, best_score, games_played, total_correct) in enumerate(top_players, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            name = first_name or username or "Anonymous"
            if len(name) > 20:
                name = name[:17] + "..."
            text += f"{medal} *{name}* — {best_score} points (🎯 {total_correct} correct, 🎮 {games_played} games)\n"
    
    keyboard = [[InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать статистику"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    user_data = db.get_or_create_user(user_id)
    achievements_count = len(db.get_user_achievements(user_id))
    
    text = (
        f"{get_text(user_id, 'stats_title')}"
        f"{get_text(user_id, 'best_score').format(user_data['best_score'])}\n"
        f"{get_text(user_id, 'games_played').format(user_data['games_played'])}\n"
        f"{get_text(user_id, 'total_score').format(user_data['total_score'])}\n"
        f"{get_text(user_id, 'total_correct').format(user_data['total_correct'])}\n"
        f"{get_text(user_id, 'average_score').format(user_data['total_score'] // user_data['games_played'] if user_data['games_played'] > 0 else 0)}\n"
        f"{get_text(user_id, 'achievements_count').format(achievements_count, len(ACHIEVEMENTS))}"
        f"{get_text(user_id, 'continue_playing')}"
    )
    
    keyboard = [[InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Главное меню"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton(get_text(user_id, 'new_game'), callback_data="choose_difficulty")],
        [InlineKeyboardButton(get_text(user_id, 'daily_bonus'), callback_data="daily_bonus")],
        [InlineKeyboardButton(get_text(user_id, 'leaderboard'), callback_data="leaderboard")],
        [InlineKeyboardButton(get_text(user_id, 'stats'), callback_data="stats")],
        [InlineKeyboardButton(get_text(user_id, 'achievements'), callback_data="achievements")],
        [InlineKeyboardButton(get_text(user_id, 'language'), callback_data="language")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        get_text(user_id, 'main_menu'),
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def cmd_play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /play"""
    await start(update, context)

def main():
    import os
    TOKEN = os.environ.get("Yes_0r_No_Bot")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", cmd_play))
    
    app.add_handler(CallbackQueryHandler(choose_language, pattern="^language$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_language(u,c,'ru'), pattern="^lang_ru$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_language(u,c,'en'), pattern="^lang_en$"))
    app.add_handler(CallbackQueryHandler(choose_difficulty, pattern="^choose_difficulty$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: start_game(u,c,'easy'), pattern="^difficulty_easy$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: start_game(u,c,'hard'), pattern="^difficulty_hard$"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^(yes|no)$"))
    app.add_handler(CallbackQueryHandler(daily_bonus, pattern="^daily_bonus$"))
    app.add_handler(CallbackQueryHandler(show_achievements, pattern="^achievements$"))
    app.add_handler(CallbackQueryHandler(leaderboard, pattern="^leaderboard$"))
    app.add_handler(CallbackQueryHandler(show_stats, pattern="^stats$"))
    app.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    
    print("🤖 БОТ ЗАПУЩЕН! (Русский / English)")
    print("✅ Добавлена поддержка двух языков")
    
    app.run_polling()

if __name__ == "__main__":
    main()
```

🌐 Что добавлено:

1. Полная поддержка двух языков

· Русский и английский
· Все тексты интерфейса переведены
· Вопросы полностью на выбранном языке
· Названия достижений на обоих языках

2. Переключение языка

· Кнопка "🌐 Язык / Language" в главном меню
· Выбор языка сохраняется в базе данных
· После смены языка весь интерфейс обновляется

3. Двуязычная база вопросов

· Лёгкие вопросы на русском и английском
· Сложные вопросы на русском и английском
· Автоматический выбор языка при игре

4. Локализованные достижения

· Названия и описания на обоих языках
· Эмодзи остаются универсальными

🚀 Как это работает:

1. Пользователь выбирает язык в меню
2. Язык сохраняется в БД для каждого пользователя
3. Все сообщения автоматически показываются на выбранном языке
4. Вопросы берутся из соответствующего языкового раздела

📝 Команды:

· /start — главное меню на текущем языке
· /play — начать игру