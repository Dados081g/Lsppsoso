import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Optional
import random
import string

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, 
    ConversationHandler, MessageHandler, Filters, CallbackContext
)
from telegram.utils.helpers import escape_markdown

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
ADMIN_BALANCE, ADMIN_BAN, ADMIN_UNBAN = range(3)

# Токен бота (замените на свой)
TOKEN = '8052146904:AAFi3NVytf2BcmHxoxree31HG6s2ndQoK5o'
ADMIN_IDS = [8349566778]  # Замените на свой Telegram ID

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
    
    def create_tables(self):
        # Таблица пользователей
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                registered_date TEXT
            )
        ''')
        
        # Таблица ключей
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_value TEXT UNIQUE,
                product_name TEXT,
                duration INTEGER,
                is_sold INTEGER DEFAULT 0,
                buyer_id INTEGER,
                purchase_date TEXT,
                FOREIGN KEY (buyer_id) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица покупок
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_name TEXT,
                key_value TEXT,
                price INTEGER,
                purchase_date TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        self.conn.commit()
    
    def add_user(self, user_id, username):
        self.cursor.execute(
            'INSERT OR IGNORE INTO users (user_id, username, registered_date) VALUES (?, ?, ?)',
            (user_id, username, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        self.conn.commit()
    
    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return self.cursor.fetchone()
    
    def update_balance(self, user_id, amount):
        self.cursor.execute(
            'UPDATE users SET balance = balance + ? WHERE user_id = ?',
            (amount, user_id)
        )
        self.conn.commit()
    
    def ban_user(self, user_id):
        self.cursor.execute(
            'UPDATE users SET is_banned = 1 WHERE user_id = ?',
            (user_id,)
        )
        self.conn.commit()
    
    def unban_user(self, user_id):
        self.cursor.execute(
            'UPDATE users SET is_banned = 0 WHERE user_id = ?',
            (user_id,)
        )
        self.conn.commit()
    
    def add_key(self, key_value, product_name, duration):
        self.cursor.execute(
            'INSERT INTO keys (key_value, product_name, duration) VALUES (?, ?, ?)',
            (key_value, product_name, duration)
        )
        self.conn.commit()
    
    def get_available_key(self, product_name, duration):
        self.cursor.execute(
            'SELECT * FROM keys WHERE product_name = ? AND duration = ? AND is_sold = 0 LIMIT 1',
            (product_name, duration)
        )
        return self.cursor.fetchone()
    
    def sell_key(self, key_id, buyer_id):
        self.cursor.execute(
            'UPDATE keys SET is_sold = 1, buyer_id = ?, purchase_date = ? WHERE id = ?',
            (buyer_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), key_id)
        )
        self.conn.commit()
    
    def add_purchase(self, user_id, product_name, key_value, price):
        self.cursor.execute(
            'INSERT INTO purchases (user_id, product_name, key_value, price, purchase_date) VALUES (?, ?, ?, ?, ?)',
            (user_id, product_name, key_value, price, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        self.conn.commit()
    
    def get_user_purchases_count(self, user_id):
        self.cursor.execute(
            'SELECT COUNT(*) FROM purchases WHERE user_id = ?',
            (user_id,)
        )
        return self.cursor.fetchone()[0]
    
    def get_all_users(self):
        self.cursor.execute('SELECT * FROM users')
        return self.cursor.fetchall()

# Инициализация базы данных
db = Database()

# Генерация ключей (для примера)
def generate_sample_keys():
    products = [
        ('ZOLO1D', 'Zolo', 1),
        ('ZOLO3D', 'Zolo', 3)
    ]
    
    for product_name, key_product, duration in products:
        for i in range(10):  # Генерируем по 10 ключей каждого типа
            key = f"{key_product}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}"
            db.add_key(key, key_product, duration)

# Раскомментируйте для генерации тестовых ключей
# generate_sample_keys()

def start(update: Update, context: CallbackContext):
    user = update.effective_user
    db.add_user(user.id, user.username)
    
    # Проверка на бан
    user_data = db.get_user(user.id)
    if user_data and user_data[3] == 1:
        update.message.reply_text("❌ Вы забанены в боте.")
        return
    
    keyboard = [
        [InlineKeyboardButton("👤 Профиль", callback_data='profile')],
        [InlineKeyboardButton("📱 Android", callback_data='category_android')],
        [InlineKeyboardButton("🛒 Мои покупки", callback_data='my_purchases')],
    ]
    
    # Добавляем кнопку админ-панели для администраторов
    if user.id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("⚙️ Админ панель", callback_data='admin_panel')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        "🌟 *Добро пожаловать в магазин ключей!* 🌟\n\n"
        "Здесь вы можете приобрести ключи для различных сервисов.\n"
        "Используйте кнопки ниже для навигации."
    )
    
    update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    
    # Проверка на бан
    user_data = db.get_user(user_id)
    if user_data and user_data[3] == 1:
        query.edit_message_text("❌ Вы забанены в боте.")
        return
    
    data = query.data
    
    if data == 'profile':
        show_profile(query, user_id)
    
    elif data == 'category_android':
        show_android_category(query)
    
    elif data == 'zolo_products':
        show_zolo_products(query)
    
    elif data.startswith('buy_zolo_'):
        parts = data.split('_')
        duration = int(parts[2])
        price = 170 if duration == 1 else 300
        process_purchase(query, user_id, 'Zolo', duration, price)
    
    elif data == 'my_purchases':
        show_purchases(query, user_id)
    
    elif data == 'admin_panel' and user_id in ADMIN_IDS:
        show_admin_panel(query)
    
    elif data == 'admin_balance' and user_id in ADMIN_IDS:
        query.edit_message_text(
            "💰 *Пополнение баланса*\n\n"
            "Введите ID пользователя и сумму через пробел.\n"
            "Пример: `123456789 500`",
            parse_mode=ParseMode.MARKDOWN
        )
        return ADMIN_BALANCE
    
    elif data == 'admin_ban' and user_id in ADMIN_IDS:
        query.edit_message_text(
            "🔨 *Бан пользователя*\n\n"
            "Введите ID пользователя для бана.\n"
            "Пример: `123456789`",
            parse_mode=ParseMode.MARKDOWN
        )
        return ADMIN_BAN
    
    elif data == 'admin_unban' and user_id in ADMIN_IDS:
        query.edit_message_text(
            "✅ *Разбан пользователя*\n\n"
            "Введите ID пользователя для разбана.\n"
            "Пример: `123456789`",
            parse_mode=ParseMode.MARKDOWN
        )
        return ADMIN_UNBAN
    
    elif data == 'admin_stats' and user_id in ADMIN_IDS:
        show_admin_stats(query)

def show_profile(query, user_id):
    user_data = db.get_user(user_id)
    if not user_data:
        return
    
    purchases_count = db.get_user_purchases_count(user_id)
    
    profile_text = (
        "👤 *Ваш профиль*\n\n"
        f"🆔 ID: `{user_data[0]}`\n"
        f"👤 Username: @{user_data[1] if user_data[1] else 'не указан'}\n"
        f"💰 Баланс: *{user_data[2]} руб.*\n"
        f"🔑 Куплено ключей: *{purchases_count}*\n"
        f"📅 Зарегистрирован: {user_data[4]}"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        profile_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

def show_android_category(query):
    keyboard = [
        [InlineKeyboardButton("📱 Zolo", callback_data='zolo_products')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        "📱 *Android категория*\n\nВыберите продукт:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

def show_zolo_products(query):
    keyboard = [
        [
            InlineKeyboardButton("🔑 Zolo 1D - 170₽", callback_data='buy_zolo_1'),
            InlineKeyboardButton("🔑 Zolo 3D - 300₽", callback_data='buy_zolo_3')
        ],
        [InlineKeyboardButton("🔙 Назад", callback_data='category_android')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        "📱 *Zolo*\n\n"
        "Выберите тариф:\n\n"
        "🔹 *1 день* - 170 руб.\n"
        "🔹 *3 дня* - 300 руб.",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

def process_purchase(query, user_id, product_name, duration, price):
    user_data = db.get_user(user_id)
    
    # Проверка баланса
    if user_data[2] < price:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='zolo_products')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            "❌ *Недостаточно средств!*\n\n"
            f"Ваш баланс: {user_data[2]} руб.\n"
            f"Стоимость: {price} руб.\n\n"
            "Пополните баланс у администратора.",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Поиск доступного ключа
    key = db.get_available_key(product_name, duration)
    
    if not key:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='zolo_products')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            "❌ *Ключи временно закончились!*\n\n"
            "Пожалуйста, попробуйте позже или свяжитесь с администратором.",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Списание средств и продажа ключа
    db.update_balance(user_id, -price)
    db.sell_key(key[0], user_id)
    db.add_purchase(user_id, product_name, key[1], price)
    
    # Красивое отображение ключа
    success_text = (
        "✅ *Покупка успешно завершена!*\n\n"
        f"🎁 *Ваш ключ:*\n"
        f"```\n{key[1]}\n```\n\n"
        f"📦 Товар: {product_name}\n"
        f"⏱ Длительность: {duration} дн.\n"
        f"💰 Цена: {price} руб.\n"
        f"💳 Новый баланс: {user_data[2] - price} руб.\n\n"
        "Спасибо за покупку! 🌟"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        success_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

def show_purchases(query, user_id):
    db.cursor.execute(
        'SELECT product_name, key_value, price, purchase_date FROM purchases WHERE user_id = ? ORDER BY purchase_date DESC LIMIT 10',
        (user_id,)
    )
    purchases = db.cursor.fetchall()
    
    if not purchases:
        text = "📭 *У вас пока нет покупок*"
    else:
        text = "🛒 *Последние покупки:*\n\n"
        for p in purchases:
            text += f"🔹 *{p[0]}*\n"
            text += f"   Ключ: `{p[1]}`\n"
            text += f"   Цена: {p[2]} руб.\n"
            text += f"   Дата: {p[3]}\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

def show_admin_panel(query):
    keyboard = [
        [InlineKeyboardButton("💰 Пополнить баланс", callback_data='admin_balance')],
        [InlineKeyboardButton("🔨 Бан пользователя", callback_data='admin_ban')],
        [InlineKeyboardButton("✅ Разбан пользователя", callback_data='admin_unban')],
        [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        "⚙️ *Админ панель*\n\nВыберите действие:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

def show_admin_stats(query):
    users = db.get_all_users()
    total_users = len(users)
    banned_users = sum(1 for u in users if u[3] == 1)
    
    db.cursor.execute('SELECT COUNT(*) FROM purchases')
    total_purchases = db.cursor.fetchone()[0]
    
    db.cursor.execute('SELECT SUM(price) FROM purchases')
    total_revenue = db.cursor.fetchone()[0] or 0
    
    stats_text = (
        "📊 *Статистика бота*\n\n"
        f"👥 Всего пользователей: *{total_users}*\n"
        f"🚫 Забанено: *{banned_users}*\n"
        f"🛒 Всего покупок: *{total_purchases}*\n"
        f"💰 Общий доход: *{total_revenue} руб.*\n"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_panel')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        stats_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

def handle_admin_input(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_IDS:
        return ConversationHandler.END
    
    state = context.user_data.get('state')
    
    if state == ADMIN_BALANCE:
        try:
            target_id, amount = update.message.text.split()
            target_id = int(target_id)
            amount = int(amount)
            
            db.update_balance(target_id, amount)
            
            update.message.reply_text(
                f"✅ Баланс пользователя {target_id} пополнен на {amount} руб.",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Уведомление пользователя
            try:
                context.bot.send_message(
                    target_id,
                    f"💰 *Ваш баланс пополнен!*\n\nСумма: +{amount} руб.",
                    parse_mode=ParseMode.MARKDOWN
                )
            except:
                pass
            
        except Exception as e:
            update.message.reply_text("❌ Ошибка! Используйте формат: ID СУММА")
    
    elif state == ADMIN_BAN:
        try:
            target_id = int(update.message.text)
            db.ban_user(target_id)
            
            update.message.reply_text(f"✅ Пользователь {target_id} забанен.")
            
            # Уведомление пользователя
            try:
                context.bot.send_message(
                    target_id,
                    "❌ *Вы были забанены в боте*"
                )
            except:
                pass
                
        except:
            update.message.reply_text("❌ Ошибка! Введите корректный ID")
    
    elif state == ADMIN_UNBAN:
        try:
            target_id = int(update.message.text)
            db.unban_user(target_id)
            
            update.message.reply_text(f"✅ Пользователь {target_id} разбанен.")
            
        except:
            update.message.reply_text("❌ Ошибка! Введите корректный ID")
    
    # Возвращаем в админ-панель
    keyboard = [
        [InlineKeyboardButton("🔙 Вернуться в админ панель", callback_data='admin_panel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        "⚙️ Выберите следующее действие:",
        reply_markup=reply_markup
    )
    
    return ConversationHandler.END

def back_to_main(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    user = update.effective_user
    
    keyboard = [
        [InlineKeyboardButton("👤 Профиль", callback_data='profile')],
        [InlineKeyboardButton("📱 Android", callback_data='category_android')],
        [InlineKeyboardButton("🛒 Мои покупки", callback_data='my_purchases')],
    ]
    
    if user.id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("⚙️ Админ панель", callback_data='admin_panel')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        "🌟 *Главное меню*\n\nВыберите раздел:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Обработчики команд
    dp.add_handler(CommandHandler('start', start))
    
    # Обработчик кнопок
    dp.add_handler(CallbackQueryHandler(button_handler, pattern='^(?!admin_).*$'))
    dp.add_handler(CallbackQueryHandler(back_to_main, pattern='^back_to_main$'))
    
    # ConversationHandler для админ-панели
    admin_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_handler, pattern='^admin_balance$'),
            CallbackQueryHandler(button_handler, pattern='^admin_ban$'),
            CallbackQueryHandler(button_handler, pattern='^admin_unban$'),
        ],
        states={
            ADMIN_BALANCE: [MessageHandler(Filters.text & ~Filters.command, handle_admin_input)],
            ADMIN_BAN: [MessageHandler(Filters.text & ~Filters.command, handle_admin_input)],
            ADMIN_UNBAN: [MessageHandler(Filters.text & ~Filters.command, handle_admin_input)],
        },
        fallbacks=[CommandHandler('start', start)],
        per_message=False,
        per_chat=True
    )
    
    dp.add_handler(admin_conv_handler)
    
    # Запуск бота
    updater.start_polling()
    logger.info("Бот запущен!")
    updater.idle()

if __name__ == '__main__':
    main()