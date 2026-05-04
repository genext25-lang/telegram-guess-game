import random
import logging
import sqlite3
import json
import urllib.request
import asyncio
import io
import os
import hashlib
import re
import html
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ========== НАСТРОЙКИ ==========
QUESTION_TIME_LIMIT = 30
MAX_QUESTION_HISTORY = 100  # Увеличено до 100
DAILY_UPDATE_HOUR = 3

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
        image_apis = {
            'science': f"https://picsum.photos/id/1/512/384",
            'geography': f"https://picsum.photos/id/15/512/384",
            'history': f"https://picsum.photos/id/20/512/384",
            'sports': f"https://picsum.photos/id/28/512/384",
            'culture': f"https://picsum.photos/id/30/512/384",
            'food': f"https://picsum.photos/id/108/512/384",
            'animals': f"https://picsum.photos/id/100/512/384",
            'technology': f"https://picsum.photos/id/0/512/384",
            'mixed': f"https://picsum.photos/id/{int(question_hash, 16) % 100}/512/384"
        }
        return image_apis.get(category, image_apis['mixed'])

image_cache = ImageCache()

# ========== БАЗА ДАННЫХ ВОПРОСОВ ==========
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
                self.load_builtin_questions_all()
    
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
                category_map = {
                    'science': 17,
                    'history': 23,
                    'sports': 21,
                    'culture': 11,
                    'technology': 18,
                    'geography': 22,
                    'animals': 27,
                }
                cat_id = category_map.get(category, 0)
                if cat_id:
                    url += f"&category={cat_id}"
            
            with urllib.request.urlopen(url, timeout=15) as response:
                data = json.loads(response.read().decode())
                for item in data['results']:
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
            'science': ['science', 'physics', 'chemistry', 'biology', 'atom', 'molecule', 'space', 'planet', 'star', 'galaxy'],
            'geography': ['country', 'river', 'mountain', 'ocean', 'city', 'capital', 'desert', 'island', 'continent'],
            'history': ['history', 'war', 'king', 'queen', 'president', 'century', 'ancient', 'empire', 'revolution'],
            'sports': ['sport', 'game', 'football', 'soccer', 'basketball', 'tennis', 'olympic', 'championship'],
            'culture': ['movie', 'film', 'book', 'song', 'artist', 'painting', 'music', 'theater', 'novel'],
            'food': ['food', 'fruit', 'vegetable', 'drink', 'cook', 'eat', 'meal', 'recipe', 'cuisine'],
            'animals': ['animal', 'cat', 'dog', 'bird', 'fish', 'mammal', 'reptile', 'insect', 'species'],
            'technology': ['computer', 'phone', 'internet', 'software', 'app', 'digital', 'robot', 'network']
        }
        for cat, words in keywords.items():
            if any(word in text_lower for word in words):
                return cat
        return 'mixed'
    
    def load_builtin_questions_all(self):
        """Загружает все встроенные вопросы"""
        builtin = {
            'science': [
                ("Земля вращается вокруг Солнца", True),
                ("Акулы — это млекопитающие", False),
                ("У осьминога три сердца", True),
                ("Банан — это ягода", True),
                ("Солнце — это звезда", True),
                ("Алмазы состоят из углерода", True),
                ("Вода кипит при 90 градусах Цельсия", False),
                ("У человека 206 костей", True),
                ("Луна больше Земли", False),
                ("Вирусы — это живые организмы", False),
            ],
            'geography': [
                ("Ватикан — самая маленькая страна", True),
                ("Антарктида — самая большая пустыня", True),
                ("Нил — самая длинная река в мире", True),
                ("Австралия — это самый большой остров", True),
                ("Гренландия — независимая страна", False),
                ("Китай граничит с 14 странами", True),
                ("Монако больше Сан-Марино", False),
                ("В мире 7 континентов", True),
            ],
            'history': [
                ("Пётр I основал Санкт-Петербург", True),
                ("Наполеон был очень низкого роста", False),
                ("Вторая мировая война началась в 1939 году", True),
                ("Юлий Цезарь был императором Рима", False),
                ("Египетские пирамиды построили рабы", False),
                ("Колумб открыл Америку в 1492 году", True),
                ("Викинги носили рогатые шлемы", False),
                ("СССР распался в 1991 году", True),
            ],
            'sports': [
                ("Футбол — самый популярный спорт", True),
                ("Майкл Джордан играл в футбол", False),
                ("В теннисе счёт 0 называется «love»", True),
                ("Олимпийские игры проводятся каждые 4 года", True),
                ("В покере 52 карты", True),
                ("Усэйн Болт — пловец", False),
                ("В шахматах белые ходят первыми", True),
                ("Марафонская дистанция — 42 км 195 м", True),
            ],
            'culture': [
                ("Мона Лиза находится в Лувре", True),
                ("Шекспир написал «Гамлета»", True),
                ("Ван Гог отрезал себе ухо", True),
                ("«Звёздные войны» снял Стивен Спилберг", False),
                ("Пикассо — испанский художник", True),
                ("Битлз — британская группа", True),
                ("Гарри Поттер учился в Хогвартсе", True),
                ("Моцарт был глухим", False),
            ],
            'food': [
                ("Шоколад ядовит для собак", True),
                ("Ананас растёт на дереве", False),
                ("Помидор — это фрукт", True),
                ("Картофель родом из Европы", False),
                ("Мёд никогда не портится", True),
                ("Арахис — это орех", False),
                ("Клубника — это ягода", True),
                ("Авокадо — это фрукт", True),
            ],
            'animals': [
                ("Панды едят только бамбук", True),
                ("Страусы прячут голову в песок", False),
                ("Дельфины спят с одним открытым глазом", True),
                ("Слоны — единственные животные, которые не могут прыгать", True),
                ("У жирафа 7 шейных позвонков (как у человека)", True),
                ("Крокодилы могут высовывать язык", False),
                ("Пчёлы умирают после укуса", True),
                ("Ленивцы спят до 20 часов в сутки", True),
            ],
            'technology': [
                ("Компьютерная мышь изобретена в 1968 году", True),
                ("Wi-Fi — это Wireless Fidelity", False),
                ("Первый iPhone вышел в 2007 году", True),
                ("Bluetooth назван в честь короля викингов", True),
                ("CAPTCHA расшифровывается как Completely Automated Public Turing test", True),
                ("QR-код изобрели в Японии", True),
                ("Билл Гейтс основал Apple", False),
                ("YouTube был создан в 2005 году", True),
            ],
            'mixed': [
                ("Самый большой океан — Тихий", True),
                ("Человек использует только 10% мозга", False),
                ("Золото добывают только в шахтах", False),
                ("Молния бьёт только в высокие объекты", False),
            ]
        }
        
        questions = []
        for cat, q_list in builtin.items():
            for text, answer in q_list:
                questions.append({
                    'text': text,
                    'answer': answer,
                    'category': cat
                })
        
        self.questions['ru'] = questions
        self.questions['en'] = []
        print(f"✅ Загружено {len(questions)} встроенных вопросов")
    
    def update_questions(self):
        """Обновляет базу вопросов"""
        print("🔄 Обновление базы вопросов...")
        
        all_questions = {'ru': [], 'en': []}
        
        # Загружаем английские вопросы
        for cat in CATEGORIES.keys():
            if cat != 'mixed':
                cat_questions = self.fetch_from_opentdb(cat, 30)
                all_questions['en'].extend(cat_questions)
        
        trivia_questions = self.fetch_from_trivia_api(50)
        all_questions['en'].extend(trivia_questions)
        
        # Загружаем русские вопросы
        if not self.questions['ru']:
            self.load_builtin_questions_all()
        all_questions['ru'] = self.questions['ru']
        
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
        if not self.questions[language]:
            self.load_builtin_questions_all()
        if category and category != 'mixed':
            return [q for q in self.questions[language] if q['category'] == category]
        return self.questions[language]

question_db = QuestionDatabase()

if question_db.needs_update():
    question_db.update_questions()

# ========== СИСТЕМА ПРЕДОТВРАЩЕНИЯ ПОВТОРОВ ==========
class QuestionManager:
    def __init__(self, max_history=100):
        self.user_history = {}
        self.max_history = max_history
    
    def get_unique_question(self, user_id, language, category=None):
        """Возвращает уникальный вопрос"""
        questions_list = question_db.get_questions_by_category(language, category)
        if not questions_list:
            return None, None, None
        
        history = set(self.user_history.get(user_id, []))
        
        # Фильтруем вопросы
        available_questions = []
        for q in questions_list:
            question_key = self._get_question_key(q['text'], language)
            if question_key not in history and not self._is_similar_to_history(question_key, history):
                available_questions.append(q)
        
        # Если мало вопросов, очищаем часть истории
        if len(available_questions) < 10 and len(questions_list) > len(history):
            self._clean_old_entries(user_id, keep_last=50)
            history = set(self.user_history.get(user_id, []))
            available_questions = [q for q in questions_list 
                                 if self._get_question_key(q['text'], language) not in history]
        
        # Если всё равно нет доступных, сбрасываем историю
        if not available_questions:
            self.clear_history(user_id)
            history = set()
            available_questions = questions_list
        
        selected = random.choice(available_questions)
        question_key = self._get_question_key(selected['text'], language)
        self._add_to_history(user_id, question_key)
        
        return selected['text'], selected['answer'], selected['category']
    
    def _get_question_key(self, question_text, language):
        """Создает ключ для вопроса"""
        normalized = question_text.lower().strip()
        normalized = re.sub(r'[^\w\s]', '', normalized)
        normalized = ' '.join(normalized.split())
        return f"{language}:{normalized}"
    
    def _is_similar_to_history(self, question_key, history, threshold=0.7):
        """Проверяет схожесть вопросов"""
        question_words = set(question_key.split())
        if len(question_words) < 3:
            return False
        
        recent = list(history)[-30:]
        for hist_key in recent:
            hist_words = set(hist_key.split())
            if len(hist_words) < 3:
                continue
            intersection = question_words & hist_words
            union = question_words | hist_words
            if union and len(intersection) / len(union) > threshold:
                return True
        return False
    
    def _add_to_history(self, user_id, question_key):
        """Добавляет в историю"""
        if user_id not in self.user_history:
            self.user_history[user_id] = []
        self.user_history[user_id].append(question_key)
        while len(self.user_history[user_id]) > self.max_history:
            self.user_history[user_id].pop(0)
    
    def _clean_old_entries(self, user_id, keep_last=50):
        """Очищает старые записи"""
        if user_id in self.user_history:
            if len(self.user_history[user_id]) > keep_last:
                self.user_history[user_id] = self.user_history[user_id][-keep_last:]
    
    def clear_history(self, user_id):
        """Очищает историю"""
        if user_id in self.user_history:
            self.user_history[user_id] = []
    
    def get_history_stats(self, user_id):
        """Статистика истории"""
        if user_id not in self.user_history:
            return {'total_asked': 0, 'remaining': self.max_history}
        history = self.user_history[user_id]
        return {
            'total_asked': len(history),
            'unique': len(set(history)),
            'remaining': max(0, self.max_history - len(history))
        }

question_manager = QuestionManager(max_history=MAX_QUESTION_HISTORY)

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
        'stats': "📊 Статистика",
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
    },
    'en': {
        'welcome': "🎮 *GUESS YES/NO GAME*\n\n📖 *Rules:*\n• I give you a statement\n• You answer YES or NO\n• Correct answer gives +1 point\n• Wrong answer = game over\n• You have {} seconds to answer!\n\n👇 *Choose action:*",
        'main_menu': "🏠 *MAIN MENU*\n\nChoose action:",
        'new_game': "🎮 New Game",
        'choose_category': "📂 Choose category",
        'leaderboard': "🏆 Leaderboard",
        'group_leaderboard': "🏆 Group Top",
        'language': "🌐 Language",
        'stats': "📊 Statistics",
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
            self.cursor.execute('''UPDATE group_stats SET 
                total_players = ?, total_games = total_games + 1, 
                total_points = total_points + ?, record_score = ?, 
                record_holder = ? WHERE group_id = ?''',
                (new_total_players, score, new_record, record_holder, group_id))
        else:
            self.cursor.execute('''INSERT INTO group_stats 
                (group_id, total_players, total_games, total_points, record_score, record_holder) 
                VALUES (?, 1, 1, ?, ?, ?)''',
                (group_id, score, score, username or str(user_id)))
        self.conn.commit()
    
    def get_group_leaderboard(self, group_id, limit=10):
        self.cursor.execute('''SELECT user_id, best_score, games_played, total_points 
                             FROM group_scores WHERE group_id = ? AND games_played > 0 
                             ORDER BY best_score DESC LIMIT ?''', (group_id, limit))
        return self.cursor.fetchall()
    
    def get_leaderboard(self, limit=10):
        self.cursor.execute('''SELECT username, first_name, best_score, games_played, total_score 
                             FROM users WHERE games_played > 0 
                             ORDER BY best_score DESC LIMIT ?''', (limit,))
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

# ========== ХРАНЕНИЕ СОСТОЯНИЙ ИГР ==========
user_games = {}
game_timers = {}

async def cancel_timer(user_id):
    if user_id in game_timers:
        game_timers[user_id].cancel()
        del game_timers[user_id]

async def game_timeout(user_id, chat_id, message_id, context):
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
        except Exception as e:
            logging.error(f"Error in timeout: {e}")

# ========== ОБРАБОТЧИКИ КОМАНД ==========
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
        [InlineKeyboardButton(get_text(user_id, 'stats'), callback_data="question_stats")],
        [InlineKeyboardButton(get_text(user_id, 'language'), callback_data="language")]
    ]
    if update.effective_chat.id < 0:
        keyboard.insert(2, [InlineKeyboardButton(get_text(user_id, 'group_leaderboard'), callback_data="group_leaderboard")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(get_text(user_id, 'main_menu'), parse_mode="Markdown", reply_markup=reply_markup)

async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    lang = db.get_or_create_user(user_id)['language']
    
    keyboard = []
    row = []
    for cat_id, cat_data in CATEGORIES.items():
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
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    lang = db.get_or_create_user(user_id)['language']
    
    db.set_category(user_id, category)
    cat_name = CATEGORIES.get(category, CATEGORIES['mixed'])[f'name_{lang}']
    cat_emoji = CATEGORIES.get(category, CATEGORIES['mixed'])['emoji']
    
    await query.edit_message_text(
        f"{cat_emoji} ✅ Выбрана категория: {cat_name}\n\nНажми «Новая игра» чтобы начать!",
        parse_mode="Markdown"
    )
    await asyncio.sleep(1)
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

async def show_question_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику вопросов"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user_data = db.get_or_create_user(user_id)
    lang = user_data['language']
    
    stats = question_manager.get_history_stats(user_id)
    category = user_data['selected_category']
    questions_list = question_db.get_questions_by_category(lang, category)
    history = set(question_manager.user_history.get(user_id, []))
    
    available = sum(1 for q in questions_list if question_manager._get_question_key(q['text'], lang) not in history)
    
    cat_name = CATEGORIES.get(category, CATEGORIES['mixed'])[f'name_{lang}']
    cat_emoji = CATEGORIES.get(category, CATEGORIES['mixed'])['emoji']
    
    if lang == 'ru':
        text = (
            f"📊 *СТАТИСТИКА ВОПРОСОВ*\n\n"
            f"📝 Всего задано: *{stats['total_asked']}*\n"
            f"🔢 Уникальных: *{stats['unique']}*\n"
            f"📋 Осталось мест: *{stats['remaining']}/{question_manager.max_history}*\n\n"
            f"📂 *Категория:* {cat_emoji} {cat_name}\n"
            f"📚 Всего в категории: *{len(questions_list)}*\n"
            f"✅ Доступно: *{available}*\n"
            f"🚫 В истории: *{len(questions_list) - available}*\n\n"
            f"ℹ️ Вопросы не повторяются в течение {question_manager.max_history} игр!"
        )
    else:
        text = (
            f"📊 *QUESTION STATISTICS*\n\n"
            f"📝 Total asked: *{stats['total_asked']}*\n"
            f"🔢 Unique: *{stats['unique']}*\n"
            f"📋 Remaining: *{stats['remaining']}/{question_manager.max_history}*\n\n"
            f"📂 *Category:* {cat_emoji} {cat_name}\n"
            f"📚 Total in category: *{len(questions_list)}*\n"
            f"✅ Available: *{available}*\n"
            f"🚫 In history: *{len(questions_list) - available}*\n\n"
            f"ℹ️ Questions don't repeat for {question_manager.max_history} games!"
        )
    
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
    
    cat_emoji = CATEGORIES.get(question_category, CATEGORIES['mixed'])['emoji']
    message_text = f"{cat_emoji} {get_text(user_id, 'game_start', question_text, QUESTION_TIME_LIMIT)}"
    
    sent_message = await query.edit_message_text(
        message_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    
    timer_task = asyncio.create_task(game_timeout(user_id, chat_id, sent_message.message_id, context))
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
            await query.edit_message_text("❌ Вопросы закончились! Игра окончена.\n\n✅ Очки сохранены!")
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
        
        timer_task = asyncio.create_task(game_timeout(user_id, chat_id, sent_message.message_id, context))
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
                f"🎮 *Привет! Я игровой бот «Угадай Да/Нет»*\n\n📖 *Как играть:*\n• Напиши /play чтобы начать игру\n• Выбери категорию вопросов\n• Нажми /grouptop — топ по группе\n\n⏱️ На ответ даётся {QUESTION_TIME_LIMIT} секунд!\n\nУдачи! 🍀",
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
    
    timer_task = asyncio.create_task(game_timeout(user_id, chat_id, sent_message.message_id, context))
    game_timers[user_id] = timer_task

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику вопросов через команду"""
    user_id = update.effective_user.id
    user_data = db.get_or_create_user(user_id)
    lang = user_data['language']
    
    stats = question_manager.get_history_stats(user_id)
    category = user_data['selected_category']
    questions_list = question_db.get_questions_by_category(lang, category)
    history = set(question_manager.user_history.get(user_id, []))
    
    available = sum(1 for q in questions_list if question_manager._get_question_key(q['text'], lang) not in history)
    
    cat_name = CATEGORIES.get(category, CATEGORIES['mixed'])[f'name_{lang}']
    cat_emoji = CATEGORIES.get(category, CATEGORIES['mixed'])['emoji']
    
    if lang == 'ru':
        text = (
            f"📊 *СТАТИСТИКА ВОПРОСОВ*\n\n"
            f"📝 Всего задано: *{stats['total_asked']}*\n"
            f"🔢 Уникальных: *{stats['unique']}*\n"
            f"📋 Осталось мест: *{stats['remaining']}/{question_manager.max_history}*\n\n"
            f"📂 *Категория:* {cat_emoji} {cat_name}\n"
            f"📚 Всего в категории: *{len(questions_list)}*\n"
            f"✅ Доступно: *{available}*\n"
            f"🚫 В истории: *{len(questions_list) - available}*\n\n"
            f"ℹ️ Вопросы не повторяются в течение {question_manager.max_history} игр!"
        )
    else:
        text = (
            f"📊 *QUESTION STATISTICS*\n\n"
            f"📝 Total asked: *{stats['total_asked']}*\n"
            f"🔢 Unique: *{stats['unique']}*\n"
            f"📋 Remaining: *{stats['remaining']}/{question_manager.max_history}*\n\n"
            f"📂 *Category:* {cat_emoji} {cat_name}\n"
            f"📚 Total in category: *{len(questions_list)}*\n"
            f"✅ Available: *{available}*\n"
            f"🚫 In history: *{len(questions_list) - available}*\n\n"
            f"ℹ️ Questions don't repeat for {question_manager.max_history} games!"
        )
    
    await update.message.reply_text(text, parse_mode="Markdown")

# ========== ЗАПУСК ==========
def main():
    TOKEN = os.environ.get("Yes_0r_No_Bot")
    if not TOKEN:
        print("❌ Ошибка: BOT_TOKEN не найден! Добавь BOT_TOKEN")
        print("Пример: export BOT_TOKEN='ваш_токен_бота'")
        return
    
    app = Application.builder().token(TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", cmd_play))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_bot))
    
    # Callback handlers
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
    app.add_handler(CallbackQueryHandler(show_question_stats, pattern="^question_stats$"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^answer_yes$"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^answer_no$"))
    
    print("=" * 60)
    print("🤖 БОТ УСПЕШНО ЗАПУЩЕН!")
    print(f"📚 Русских вопросов: {len(question_db.questions['ru'])}")
    print(f"📚 Английских вопросов: {len(question_db.questions['en'])}")
    print(f"🔄 Повтор вопросов через: {MAX_QUESTION_HISTORY} игр")
    print(f"⏱️ Время на ответ: {QUESTION_TIME_LIMIT} сек")
    print("✅ /start - Главное меню")
    print("✅ /play - Быстрый старт игры")
    print("✅ /stats - Статистика вопросов")
    print("=" * 60)
    
    app.run_polling()

if __name__ == "__main__":
    main()