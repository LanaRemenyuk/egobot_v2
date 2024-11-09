import os
import psycopg2
import time
import pandas as pd
from datetime import date, datetime
from dotenv import load_dotenv
import logging
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from links import links

load_dotenv()

buttons = ReplyKeyboardMarkup([['/book'], ['/rebook', '/feedback']], resize_keyboard=True)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


secret_token = os.getenv('SECRET_TOKEN')
admin_user_ids = os.getenv('ADMIN_USER_IDS').split(',')
admin_user_ids = [int(user_id) for user_id in admin_user_ids]
DB_PARAMS = {
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT'),
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
}

def create_db():
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            feedback TEXT,
            booked_class TEXT,
            visited_on TIMESTAMP,
            event TEXT,
            PRIMARY KEY (user_id, visited_on))''')
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error creating database or table: {e}")

def insert_user_data(user_id, username, first_name, last_name, feedback=None, booked_class=None, event=None):
    retries = 5
    for i in range(retries):
        try:
            conn = psycopg2.connect(**DB_PARAMS)
            cursor = conn.cursor()
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
            cursor.execute('''INSERT INTO users (user_id, username, first_name, last_name, feedback, booked_class, visited_on, event)
                              VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''', (user_id, username, first_name, last_name, feedback, booked_class, current_time, event))
            conn.commit()
            cursor.close()
            conn.close()
            break
        except psycopg2.IntegrityError as e:
            if 'duplicate key value violates unique constraint' in str(e):
                break
        except psycopg2.OperationalError as e:
            if 'could not connect to server' in str(e) and i < retries - 1:
                time.sleep(1)
                continue
            break

def export_to_excel():
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        df = pd.read_sql_query("SELECT * FROM users", conn)
        if not df.empty:
            df.to_excel("users_events_data.xlsx", index=False)
        conn.close()
    except Exception as e:
        print(f"Error exporting data to Excel: {e}")

async def start(update: Update, context: CallbackContext):
    chat = update.effective_chat
    buttn = ReplyKeyboardMarkup([['/start']], resize_keyboard=True)
    await context.bot.send_message(chat_id=chat.id, text='Please push the start button 🚀', reply_markup=buttn)

async def say_hi(update: Update, context: CallbackContext):
    name = update.message.chat.first_name
    await update.message.reply_text(f'Hi {name} 👋, I\'m EgoClub Bot! Please choose the right option', reply_markup=buttons)

async def send_schedule(update: Update, context: CallbackContext):
    user_name = update.message.chat.username
    user_id = update.message.chat.id
    today = date.today().strftime("%d.%m.%Y")
    insert_user_data(user_id, user_name, update.message.chat.first_name, update.message.chat.last_name, event="Pushed on book")
    export_to_excel()
    for admin_user_id in admin_user_ids:
        await context.bot.send_message(admin_user_id, f"User {user_name} (ID: {user_id}) tapped on a book button on {today}")
    await context.bot.send_message(update.effective_chat.id, links, parse_mode='Markdown')

async def get_feedback(update: Update, context: CallbackContext):
    await update.message.reply_text('I\'ll be glad to receive your feedback to get better 😸', reply_markup=ReplyKeyboardRemove())
    return 'get_feedback'

async def feedback_taken(update: Update, context: CallbackContext):
    feedback = update.message.text
    name = update.message.from_user.username
    user_id = update.message.from_user.id
    today = date.today().strftime("%d.%m.%Y")
    insert_user_data(user_id, name, update.message.from_user.first_name, update.message.from_user.last_name, feedback=feedback, event="Feedback")
    export_to_excel()
    for admin_user_id in admin_user_ids:
        await context.bot.send_message(admin_user_id, f"User {name} (ID: {user_id}) left feedback on {today}: {feedback}")

    await update.message.reply_text('Thanks for your feedback! 😸', reply_markup=buttons)
    return ConversationHandler.END

async def get_unbooked(update: Update, context: CallbackContext):
    await update.message.reply_text('Which of the booked classes would you like to rebook?')
    return 'get_unbooked'

async def unbooking_taken(update: Update, context: CallbackContext):
    booked_class = update.message.text
    name = update.message.from_user.username
    user_id = update.message.from_user.id
    today = date.today().strftime("%d.%m.%Y")
    insert_user_data(user_id, name, update.message.from_user.first_name, update.message.from_user.last_name, booked_class=booked_class, event="Rebook needed")
    export_to_excel()
    for admin_user_id in admin_user_ids:
        await context.bot.send_message(admin_user_id, f"User {name} (ID: {user_id}) rebooked a class on {today}: {booked_class}")
    await update.message.reply_text('Done ✅ Our manager will contact you!', reply_markup=buttons)
    return ConversationHandler.END

async def dontknow(update: Update, context: CallbackContext):
    await update.message.reply_text('I don\'t understand you, please type your answer!')

def main():
    create_db()
    application = Application.builder().token(secret_token).build()

    application.add_handler(CommandHandler('start', say_hi))
    application.add_handler(CommandHandler('book', send_schedule))

    feedback_handler = ConversationHandler(
        entry_points=[CommandHandler('feedback', get_feedback)],
        states={'get_feedback': [MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_taken)]},
        fallbacks=[MessageHandler(filters.VIDEO | filters.PHOTO | filters.Sticker.ALL, dontknow)]
    )
    application.add_handler(feedback_handler)

    rebook_handler = ConversationHandler(
        entry_points=[CommandHandler('rebook', get_unbooked)],
        states={'get_unbooked': [MessageHandler(filters.TEXT & ~filters.COMMAND, unbooking_taken)]},
        fallbacks=[MessageHandler(filters.VIDEO | filters.PHOTO | filters.Sticker.ALL, dontknow)]
    )
    application.add_handler(rebook_handler)

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, dontknow))

    application.run_polling()

if __name__ == '__main__':
    main()
