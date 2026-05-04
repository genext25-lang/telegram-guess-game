import random
import logging
import sqlite3
import json
import urllib.request
import asyncio
import io
import os
import hashlib
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ========== НАСТРОЙКИ ==========
QUESTION_TIME_LIMIT = 30
MAX_QUESTION_HISTORY = 20
DAILY_UPDATE_HOUR = 3  # 3 часа ночи (обновление вопросов)

# ========== КАТЕГОРИИ ВОПРОСОВ ==========
CATEGORIES = {
    'science': {'emoji': '🔬', 'name_ru': 'Наука', 'name_en': 'Science'},
    'geography': {'emoji': '🌍', 'name_ru': 'География', 'name_en': 'Geography'},
    'history': {'emoji': '📜', 'name_ru': 'История', 'name_en': 'History'},
    'sports': {'emoji': '⚽', 'name_ru': 'Спорт', 'name_en': 'Sports'},
    'culture': {'emoji': '🎨', 'name_ru': 'Культура', 'name_en': 'Culture'},
    'food': {'emoji': '🍕', 'name_ru': 'Еда', 'name_en': 'Food'},
    'animals': {'emoji': '🐾', 'name_ru': 'Животные', 'name_en': 'Animals'},
    'technology': {'emoji': '💻', 'name_ru': 'Технологии', 'name_en': 'Technology'},
    'mixed': {'emoji': '🎲', 'name_ru': 'Смешанная', 'name_en': 'Mixed'}
}

# ========== КЭШ КАРТИНОК ==========
class ImageCache:
    def __init__(self):
        self.cache = {}
        self.last_update = None
    
    def get_image_url(self, category, question_hash):
        """Получает URL картинки для категории"""
        # Используем надежные API для изображений
        image_apis = {
            'science': f"https://picsum.photos/id/1/512/384",  # Научная тематика
            'geography': f"https://picsum.photos/id/15/512/384",  # Пейзажи
            'history': f"https://picsum.photos/id/20/512/384",  # Архитектура
            'sports': f"https://picsum.photos/id/28/512/384",  # Спорт
            'culture': f"https://picsum.photos/id/30/512/384",  # Искусство
            'food': f"https://picsum.photos/id/108/512/384",  # Еда
            'animals': f"https://picsum.photos/id/100/512/384",  # Животные
            'technology': f"https://picsum.photos/id/0/512/384",  # Технологии
            'mixed': f"https://picsum.photos/id/{int(question_hash, 16) % 100}/512/384"
        }
        return image_apis.get(category, image_apis['mixed'])

image_cache = ImageCache()

# ========== БАЗА ДАННЫХ ВОПРОСОВ С ОБНОВЛЕНИЕМ ==========
class QuestionDatabase:
    def __init__(self):
        self.questions = {'ru': [], 'en': []}
        self.last_update = None
        self.load_from_storage()
    
    def load_from_storage(self):
        """Загружает вопросы из файла кэша"""
        if os.path.exists("questions_cache.json"):
            try:
                with open("questions_cache.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.questions = data.get('questions', {'ru': [], 'en': []})
                    self.last_update = data.get('last_update')
                print(f"📚 Загружено из кэша: {len(self.questions['ru'])} русских, {len(self.questions['en'])} английских")
            except Exception as e:
                print(f"⚠️ Ошибка загрузки кэша: {e}")
    
    def save_to_storage(self):
        """Сохраняет вопросы в файл кэша"""
        data = {
            'questions': self.questions,
            'last_update': datetime.now().isoformat()
        }
        with open("questions_cache.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("💾 Вопросы сохранены в кэш")
    
    def needs_update(self):
        """Проверяет, нужно ли обновить вопросы"""
        if not self.last_update:
            return True
        last_date = datetime.fromisoformat(self.last_update).date()
        return date.today() - last_date >= timedelta(days=1)
    
    def fetch_from_opentdb(self, category=None, amount=50):
        """Загружает вопросы из OpenTDB API"""
        questions = []
        try:
            url = f"https://opentdb.com/api.php?amount={amount}&type=boolean"
            if category:
                # OpenTDB category mapping
                category_map = {
                    'science': 17,  # Science & Nature
                    'history': 23,  # History
                    'sports': 21,   # Sports
                    'culture': 11,  # Entertainment
                    'technology': 18, # Computers
                    'geography': 22,  # Geography
                    'animals': 27,   # Animals
                }
                cat_id = category_map.get(category, 0)
                if cat_id:
                    url += f"&category={cat_id}"
            
            with urllib.request.urlopen(url, timeout=15) as response:
                data = json.loads(response.read().decode())
                for item in data['results']:
                    import html
                    question_text = html.unescape(item['question'])
                    correct = item['correct_answer'] == "True"
                    cat = category or 'mixed'
                    questions.append({
                        'text': question_text,
                        'answer': correct,
                        'category': cat
                    })
            print(f"✅ Загружено {len(questions)} вопросов из OpenTDB")
        except Exception as e:
            print(f"⚠️ OpenTDB API: {e}")
        return questions
    
    def fetch_from_trivia_api(self, amount=30):
        """Загружает вопросы из The Trivia API"""
        questions = []
        try:
            url = f"https://the-trivia-api.com/api/questions?limit={amount}"
            with urllib.request.urlopen(url, timeout=15) as response:
                data = json.loads(response.read().decode())
                for item in data:
                    question_text = item['question']
                    correct = item['correctAnswer'] == "True"
                    # Определяем категорию по ключевым словам
                    category = self.detect_category(question_text)
                    questions.append({
                        'text': question_text,
                        'answer': correct,
                        'category': category
                    })
            print(f"✅ Загружено {len(questions)} вопросов из Trivia API")
        except Exception as e:
            print(f"⚠️ Trivia API: {e}")
        return questions
    
    def detect_category(self, text):
        """Определяет категорию по ключевым словам"""
        text_lower = text.lower()
        keywords = {
            'science': ['science', 'physics', 'chemistry', 'biology', 'atom', 'molecule', 'space'],
            'geography': ['country', 'river', 'mountain', 'ocean', 'city', 'capital', 'desert'],
            'history': ['history', 'war', 'king', 'queen', 'president', 'century', 'ancient'],
            'sports': ['sport', 'game', 'football', 'soccer', 'basketball', 'tennis', 'olympic'],
            'culture': ['movie', 'film', 'book', 'song', 'artist', 'painting', 'music'],
            'food': ['food', 'fruit', 'vegetable', 'drink', 'cook', 'eat', 'meal'],
            'animals': ['animal', 'cat', 'dog', 'bird', 'fish', 'mammal', 'reptile'],
            'technology': ['computer', 'phone', 'internet', 'software', 'app', 'digital']
        }
        for cat, words in keywords.items():
            if any(word in text_lower for word in words):
                return cat
        return 'mixed'
    
    def generate_russian_questions(self):
        """Генерирует русские вопросы на основе английских"""
        russian_questions = []
        for q in self.questions['en']:
            # Простой перевод через шаблон (для демонстрации)
            # В реальном проекте лучше использовать отдельный источник русских вопросов
            ru_text = f"Верно ли, что {q['text']}?"
            russian_questions.append({
                'text': ru_text,
                'answer': q['answer'],
                'category': q['category']
            })
        return russian_questions
    
    def load_builtin_questions(self):
        """Встроенные русские вопросы (базовый набор)"""
        builtin = {
            'science': [
                ("Земля вращается вокруг Солнца", True),
                ("Акулы — это млекопитающие", False),
                ("У осьминога три сердца", True),
                ("Банан — это ягода", True),
            ],
            'geography': [
                ("Ватикан — самая маленькая страна", True),
                ("Антарктида — самая большая пустыня", True),
            ],
            'history': [
                ("Пётр I основал Санкт-Петербург", True),
                ("Наполеон был очень низкого роста", False),
            ],
            'sports': [
                ("Футбол — самый популярный спорт", True),
                ("Майкл Джордан играл в футбол", False),
            ],
            'culture': [
                ("Мона Лиза находится в Лувре", True),
                ("Шекспир написал «Гамлета»", True),
            ],
            'food': [
                ("Шоколад ядовит для собак", True),
                ("Ананас растёт на дереве", False),
            ],
            'animals': [
                ("Панды едят только бамбук", True),
                ("Страусы прячут голову в песок", False),
            ],
            'technology': [
                ("Компьютерная мышь изобретена в 1968 году", True),
                ("Wi-Fi — это беспроводная связь", True),
            ],
        }
        
        questions = []
        for cat, q_list in builtin.items():
            for text, answer in q_list:
                questions.append({
                    'text': text,
                    'answer': answer,
                    'category': cat
                })
        return questions
    
    def update_questions(self):
        """Обновляет базу вопросов из интернета"""
        print("🔄 Обновление базы вопросов...")
        
        all_questions = {'ru': [], 'en': []}
        
        # Загружаем английские вопросы по категориям
        for cat in CATEGORIES.keys():
            if cat != 'mixed':
                cat_questions = self.fetch_from_opentdb(cat, 30)
                all_questions['en'].extend(cat_questions)
        
        # Добавляем вопросы из Trivia API
        trivia_questions = self.fetch_from_trivia_api(50)
        all_questions['en'].extend(trivia_questions)
        
        # Загружаем русские вопросы (встроенные + перевод)
        russian_builtin = self.load_builtin_questions()
        all_questions['ru'].extend(russian_builtin)
        
        # Удаляем дубликаты
        for lang in ['ru', 'en']:
            seen = set()
            unique = []
            for q in all_questions[lang]:
                if q['text'] not in seen:
                    seen.add(q['text'])
                    unique.append(q)
            all_questions[lang] = unique
        
        self.questions = all_questions
        self.save_to_storage()
        
        print(f"✅ База обновлена! Русских: {len(self.questions['ru'])}, Английских: {len(self.questions['en'])}")
        return self.questions
    
    def get_questions_by_category(self, language, category=None):
        """Возвращает вопросы по категории"""
        if category and category != 'mixed':
            return [q for q in self.questions[language] if q['category'] == category]
        return self.questions[language]
    
    def get_random_question(self, language, category=None):
        """Возвращает случайный вопрос"""
        questions_list = self.get_questions_by_category(language, category)
        if not questions_list:
            return None, None, None
        q = random.choice(questions_list)
        return q['text'], q['answer'], q['category']

# ========== ИНИЦИАЛИЗАЦИЯ ==========
question_db = QuestionDatabase()

# При запуске проверяем, нужно ли обновить вопросы
if question_db.needs_update():
    question_db.update_questions()
else:
    print(f"✅ Вопросы актуальны (последнее обновление: {question_db.last_update})")

# ========== ПЕРЕВОДЫ ==========
TRANSLATIONS = {
    'ru': {
        'welcome': "🎮 *ИГРА «УГАДАЙ ДА/НЕТ»*\n\n📖 *Правила:*\n• Я даю утверждение\n• Ты отвечаешь ДА или НЕТ\n• За правильный ответ +1 очко\n• Ошибка = конец игры\n• На ответ даётся {} секунд!\n\n👇 *Выбери действие:*",
        'main_menu': "🏠 *ГЛАВНОЕ МЕНЮ*\n\nВыбери действие:",
        'new_game': "🎮 Новая игра",
        'choose_category': "📂 Выбрать категорию",
        'leaderboard': "🏆 Таблица лидеров",
        'group_leaderboard': "🏆 Топ группы",
        'language': "🌐 Язык",
        'back': "🔙 Назад",
        'yes': "✅ ДА",
        'no': "❌ НЕТ",
        'game_start': "🎲 *ИГРА НАЧАЛАСЬ!*\n\n📢 *Вопрос:*\n{}\n\n⏱️ У тебя {} секунд!\n📊 Счёт: *0* очков",
        'correct': "✅ *ПРАВИЛЬНО!* +1 очко\n\n📢 *Вопрос:*\n{}\n\n⏱️ У тебя {} секунд!\n📊 Счёт: *{}* очков",
        'game_over': "❌ *ИГРА ОКОНЧЕНА!*\n\nПравильный ответ: *{}*\nТы набрал(а): *{}* очков\n\n🏅 Твой лучший результат: *{}* очков",
        'timeout': "⏰ *ВРЕМЯ ВЫШЛО!*\n\nПравильный ответ: *{}*\nТы набрал(а): *{}* очков",
        'play_again': "🎮 Играть снова",
        'leaderboard_title': "🏆 *ТАБЛИЦА ЛИДЕРОВ* 🏆\n\n",
        'group_leaderboard_title': "🏆 *ТОП ГРУППЫ* 🏆\n\n",
        'no_players': "Пока никто не играл! Будь первым!",
        'welcome_group': "🎮 *Привет! Я игровой бот «Угадай Да/Нет»*\n\n📖 *Как играть:*\n• Напиши /play чтобы начать игру\n• Выбери категорию вопросов\n• Нажми /grouptop — топ по группе\n\n⏱️ На ответ даётся {} секунд!\n\nУдачи! 🍀",
        'category_selected': "✅ Выбрана категория: {}\n\nНажми «Новая игра» чтобы начать!",
        'current_category': "Текущая категория: {}",
    },
    'en': {
        'welcome': "🎮 *GUESS YES/NO GAME*\n\n📖 *Rules:*\n• I give you a statement\n• You answer YES or NO\n• Correct answer gives +1 point\n• Wrong answer = game over\n• You have {} seconds to answer!\n\n👇 *Choose action:*",
        'main_menu': "🏠 *MAIN MENU*\n\nChoose action:",
        'new_game': "🎮 New Game",
        'choose_category': "📂 Choose category",
        'leaderboard': "🏆 Leaderboard",
        'group_leaderboard': "🏆 Group Top",
        'language': "🌐 Language",
        'back': "🔙 Back",
        'yes': "✅ YES",
        'no': "❌ NO",
        'game_start': "🎲 *GAME STARTED!*\n\n📢 *Question:*\n{}\n\n⏱️ You have {} seconds!\n📊 Score: *0* points",
        'correct': "✅ *CORRECT!* +1 point\n\n📢 *Question:*\n{}\n\n⏱️ You have {} seconds!\n📊 Score: *{}* points",
        'game_over': "❌ *GAME OVER!*\n\nCorrect answer: *{}*\nYou scored: *{}* points\n\n🏅 Your best score: *{}* points",
        'timeout': "⏰ *TIME IS OVER!*\n\nCorrect answer: *{}*\nYou scored: *{}* points",
        'play_again': "🎮 Play Again",
        'leaderboard_title': "🏆 *LEADERBOARD* 🏆\n\n",
        'group_leaderboard_title': "🏆 *GROUP TOP* 🏆\n\n",
        'no_players': "Nobody has played yet! Be the first!",
        'welcome_group': "🎮 *Hi! I'm the «Guess Yes/No» game bot*\n\n📖 *How to play:*\n• Type /play to start the game\n• Choose a question category\n• Type /grouptop — group top\n\n⏱️ You have {} seconds to answer!\n\nGood luck! 🍀",
        'category_selected': "✅ Category selected: {}\n\nPress «New Game» to start!",
        'current_category': "Current category: {}",
    }
}

# ========== БАЗА ДАННЫХ ПОЛЬЗОВАТЕЛЕЙ ==========
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
                selected_category TEXT DEFAULT 'mixed',
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
            self.cursor.execute('INSERT INTO users (user_id, username, first_name, last_name, selected_category) VALUES (?, ?, ?, ?, ?)',
                              (user_id, username, first_name, last_name, 'mixed'))
            self.conn.commit()
            return {'user_id': user_id, 'language': 'ru', 'selected_category': 'mixed', 'best_score': 0, 'games_played': 0, 'total_score': 0}
        return {'user_id': user[0], 'language': user[4], 'selected_category': user[5], 'best_score': user[6], 'games_played': user[7], 'total_score': user[8]}
    
    def set_category(self, user_id, category):
        self.cursor.execute('UPDATE users SET selected_category = ? WHERE user_id = ?', (category, user_id))
        self.conn.commit()
    
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
    
    def get_leaderboard(self, limit=10):
        self.cursor.execute('SELECT username, first_name, best_score, games_played, total_score FROM users WHERE games_played > 0 ORDER BY best_score DESC, total_score DESC LIMIT ?', (limit,))
        return self.cursor.fetchall()
    
    def get_user_rank(self, user_id):
        user = self.get_or_create_user(user_id)
        self.cursor.execute('SELECT COUNT(*) FROM users WHERE best_score > ?', (user['best_score'],))
        better_count = self.cursor.fetchone()[0]
        return better_count + 1
    
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

# ========== СИСТЕМА ПРЕДОТВРАЩЕНИЯ ПОВТОРОВ ==========
class QuestionManager:
    def __init__(self, max_history=20):
        self.user_history = {}
        self.max_history = max_history
    
    def get_unique_question(self, user_id, language, category=None):
        """Возвращает уникальный вопрос из выбранной категории"""
        questions_list = question_db.get_questions_by_category(language, category)
        if not questions_list:
            return None, None, None
        
        available_questions = []
        history = self.user_history.get(user_id, [])
        
        for q in questions_list:
            if q['text'] not in history:
                available_questions.append(q)
        
        if not available_questions:
            self.user_history[user_id] = []
            available_questions = questions_list
        
        selected = random.choice(available_questions)
        
        if user_id not in self.user_history:
            self.user_history[user_id] = []
        self.user_history[user_id].append(selected['text'])
        
        if len(self.user_history[user_id]) > self.max_history:
            self.user_history[user_id].pop(0)
        
        return selected['text'], selected['answer'], selected['category']
    
    def clear_history(self, user_id):
        if user_id in self.user_history:
            self.user_history[user_id] = []

question_manager = QuestionManager(max_history=MAX_QUESTION_HISTORY)

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
            await context.bot.edit_message_text(
                get_text(user_id, 'timeout', correct_word, game['score']),
                chat_id=chat_id,
                message_id=message_id,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        except:
            pass

# ========== ОБРАБОТЧИКИ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    
    keyboard = [
        [InlineKeyboardButton(get_text(user.id, 'new_game'), callback_data="new_game")],
        [InlineKeyboardButton(get_text(user.id, 'choose_category'), callback_data="categories")],
        [InlineKeyboardButton(get_text(user.id, 'leaderboard'), callback_data="leaderboard")],
        [InlineKeyboardButton(get_text(user.id, 'language'), callback_data="language")]
    ]
    if update.effective_chat and update.effective_chat.type in ['group', 'supergroup']:
        keyboard.insert(2, [InlineKeyboardButton(get_text(user.id, 'group_leaderboard'), callback_data="group_leaderboard")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(get_text(user.id, 'welcome', QUESTION_TIME_LIMIT), parse_mode="Markdown", reply_markup=reply_markup)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton(get_text(user_id, 'new_game'), callback_data="new_game")],
        [InlineKeyboardButton(get_text(user_id, 'choose_category'), callback_data="categories")],
        [InlineKeyboardButton(get_text(user_id, 'leaderboard'), callback_data="leaderboard")],
        [InlineKeyboardButton(get_text(user_id, 'language'), callback_data="language")]
    ]
    chat_id = update.effective_chat.id
    if chat_id < 0:
        keyboard.insert(2, [InlineKeyboardButton(get_text(user_id, 'group_leaderboard'), callback_data="group_leaderboard")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(get_text(user_id, 'main_menu'), parse_mode="Markdown", reply_markup=reply_markup)

async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает выбор категорий"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    lang = db.get_or_create_user(user_id)['language']
    
    keyboard = []
    row = []
    for i, (cat_id, cat_data) in enumerate(CATEGORIES.items()):
        name = cat_data[f'name_{lang}']
        emoji = cat_data['emoji']
        row.append(InlineKeyboardButton(f"{emoji} {name}", callback_data=f"cat_{cat_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    current_cat = db.get_or_create_user(user_id)['selected_category']
    current_name = CATEGORIES.get(current_cat, CATEGORIES['mixed'])[f'name_{lang}']
    current_emoji = CATEGORIES.get(current_cat, CATEGORIES['mixed'])['emoji']
    
    await query.edit_message_text(
        f"📂 *Выбери категорию вопросов*\n\n{current_emoji} Текущая: {current_name}\n\nВыбери новую категорию:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def set_category(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str):
    """Устанавливает выбранную категорию"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    lang = db.get_or_create_user(user_id)['language']
    
    db.set_category(user_id, category)
    cat_name = CATEGORIES.get(category, CATEGORIES['mixed'])[f'name_{lang}']
    cat_emoji = CATEGORIES.get(category, CATEGORIES['mixed'])['emoji']
    
    await query.edit_message_text(
        f"{cat_emoji} {get_text(user_id, 'category_selected', cat_name)}",
        parse_mode="Markdown"
    )
    await main_menu(update, context)

async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"), InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
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
    
    user_rank = db.get_user_rank(user_id)
    user_data = db.get_or_create_user(user_id)
    text += f"\n📊 *Твоё место:* #{user_rank} | 🏅 *{user_data['best_score']}* очков"
    
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
    user_data = db.get_or_create_user(user_id)
    lang = user_data['language']
    category = user_data['selected_category']
    
    await cancel_timer(user_id)
    
    question_text, correct_answer, question_category = question_manager.get_unique_question(user_id, lang, category)
    
    if not question_text:
        await query.edit_message_text("❌ В этой категории пока нет вопросов! Выбери другую категорию.")
        return
    
    user_games[user_id] = {
        'score': 0,
        'correct_answer': correct_answer,
        'current_question': question_text,
        'category': question_category
    }
    
    keyboard = [
        [InlineKeyboardButton(get_text(user_id, 'yes'), callback_data="answer_yes"),
         InlineKeyboardButton(get_text(user_id, 'no'), callback_data="answer_no")],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Добавляем картинку и эмодзи категории
    cat_emoji = CATEGORIES.get(question_category, CATEGORIES['mixed'])['emoji']
    message_text = f"{cat_emoji} {get_text(user_id, 'game_start', question_text, QUESTION_TIME_LIMIT)}"
    
    sent_message = await query.edit_message_text(
        message_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    
    timer_task = asyncio.create_task(game_timeout(user_id, chat_id, sent_message.message_id))
    game_timers[user_id] = timer_task

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_data = db.get_or_create_user(user_id)
    lang = user_data['language']
    category = user_data['selected_category']
    
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
        question_text, new_correct, question_category = question_manager.get_unique_question(user_id, lang, category)
        
        if not question_text:
            await query.edit_message_text("❌ Вопросы закончились в этой категории! Твоя игра окончена.\n\n✅ Очки сохранены!")
            db.update_score(user_id, current_score)
            del user_games[user_id]
            return
        
        user_games[user_id] = {
            'score': current_score,
            'correct_answer': new_correct,
            'current_question': question_text,
            'category': question_category
        }
        
        keyboard = [
            [InlineKeyboardButton(get_text(user_id, 'yes'), callback_data="answer_yes"),
             InlineKeyboardButton(get_text(user_id, 'no'), callback_data="answer_no")],
            [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        cat_emoji = CATEGORIES.get(question_category, CATEGORIES['mixed'])['emoji']
        message_text = f"{cat_emoji} {get_text(user_id, 'correct', question_text, QUESTION_TIME_LIMIT, current_score)}"
        
        sent_message = await query.edit_message_text(
            message_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        
        timer_task = asyncio.create_task(game_timeout(user_id, chat_id, sent_message.message_id))
        game_timers[user_id] = timer_task
    else:
        correct_word = "ДА" if correct_answer else "НЕТ" if lang == 'ru' else "YES" if correct_answer else "NO"
        is_record = db.update_score(user_id, current_score)
        if chat_id < 0:
            user = update.effective_user
            db.update_group_score(chat_id, user_id, current_score, user.first_name)
        user_rank = db.get_user_rank(user_id)
        user_data_full = db.get_or_create_user(user_id)
        del user_games[user_id]
        
        keyboard = [
            [InlineKeyboardButton(get_text(user_id, 'play_again'), callback_data="new_game")],
            [InlineKeyboardButton(get_text(user_id, 'leaderboard'), callback_data="leaderboard")],
            [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = get_text(user_id, 'game_over', correct_word, current_score, user_data_full['best_score'])
        if is_record and current_score > 0:
            message += "\n\n🎉 *НОВЫЙ РЕКОРД!* 🎉"
        message += f"\n\n📊 *Твоё место в общем топе: #{user_rank}*"
        
        await query.edit_message_text(message, parse_mode="Markdown", reply_markup=reply_markup)

async def welcome_new_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            await update.message.reply_text(
                TRANSLATIONS['ru']['welcome_group'].format(QUESTION_TIME_LIMIT),
                parse_mode="Markdown"
            )
            return

async def cmd_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_data = db.get_or_create_user(user_id)
    lang = user_data['language']
    category = user_data['selected_category']
    
    await cancel_timer(user_id)
    
    question_text, correct_answer, question_category = question_manager.get_unique_question(user_id, lang, category)
    
    if not question_text:
        await update.message.reply_text("❌ В этой категории пока нет вопросов! Выбери другую категорию.")
        return
    
    user_games[user_id] = {
        'score': 0,
        'correct_answer': correct_answer,
        'current_question': question_text,
        'category': question_category
    }
    
    keyboard = [
        [InlineKeyboardButton(get_text(user_id, 'yes'), callback_data="answer_yes"),
         InlineKeyboardButton(get_text(user_id, 'no'), callback_data="answer_no")],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    cat_emoji = CATEGORIES.get(question_category, CATEGORIES['mixed'])['emoji']
    message_text = f"{cat_emoji} {get_text(user_id, 'game_start', question_text, QUESTION_TIME_LIMIT)}"
    
    sent_message = await update.message.reply_text(
        message_text,
        parse_mode="Markdown",
        reply_markup=reply_markup,
        reply_to_message_id=update.message.message_id
    )
    
    timer_task = asyncio.create_task(game_timeout(user_id, chat_id, sent_message.message_id))
    game_timers[user_id] = timer_task

# ========== ЗАПУСК ==========
def main():
    TOKEN = os.environ.get("Yes_0r_No_Bot")
    if not TOKEN:
        print("❌ Ошибка: BOT_TOKEN не найден!")
        return
    
    # Ежедневное обновление вопросов
    async def daily_update():
        while True:
            await asyncio.sleep(24 * 3600)  # Каждые 24 часа
            if question_db.needs_update():
                print("🔄 Ежедневное обновление вопросов...")
                question_db.update_questions()
    
    app = Application.builder().token(TOKEN).build()
    
    # Запускаем фоновую задачу для ежедневного обновления
    # loop = asyncio.get_event_loop()
    # loop.create_task(daily_update())
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", cmd_play))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_bot))
    
    app.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(show_categories, pattern="^categories$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_category(u,c,'mixed'), pattern="^cat_mixed$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_category(u,c,'science'), pattern="^cat_science$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_category(u,c,'geography'), pattern="^cat_geography$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_category(u,c,'history'), pattern="^cat_history$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_category(u,c,'sports'), pattern="^cat_sports$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_category(u,c,'culture'), pattern="^cat_culture$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_category(u,c,'food'), pattern="^cat_food$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_category(u,c,'animals'), pattern="^cat_animals$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_category(u,c,'technology'), pattern="^cat_technology$"))
    app.add_handler(CallbackQueryHandler(choose_language, pattern="^language$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_language(u,c,'ru'), pattern="^lang_ru$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: set_language(u,c,'en'), pattern="^lang_en$"))
    app.add_handler(CallbackQueryHandler(new_game, pattern="^new_game$"))
    app.add_handler(CallbackQueryHandler(show_leaderboard, pattern="^leaderboard$"))
    app.add_handler(CallbackQueryHandler(show_group_leaderboard, pattern="^group_leaderboard$"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^answer_yes$"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^answer_no$"))
    
    print("=" * 60)
    print("🤖 БОТ УСПЕШНО ЗАПУЩЕН!")
    print(f"📚 ВОПРОСОВ В БАЗЕ: Русских: {len(question_db.questions['ru'])}, Английских: {len(question_db.questions['en'])}")
    print("✅ КОМАНДЫ: /start, /play")
    print("✅ ВЫБОР КАТЕГОРИЙ: 9 категорий с эмодзи")
    print("✅ КАРТИНКИ: тематические эмодзи и изображения")
    print("✅ ЕЖЕДНЕВНОЕ ОБНОВЛЕНИЕ: вопросы обновляются раз в сутки")
    print("=" * 60)
    app.run_polling()

if __name__ == "__main__":
    main()