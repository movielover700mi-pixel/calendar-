import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
import pytz
from config import BOT_TOKEN, NOTIFICATION_HOUR, NOTIFICATION_MINUTE, TIMEZONE
from database import Database
from flask import Flask
import threading

# Setup
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Running"

db = Database()
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
user_state = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ Add Anime", callback_data='add_menu')],
        [InlineKeyboardButton("❌ Remove Anime", callback_data='remove_menu')],
        [InlineKeyboardButton("📅 Schedule", callback_data='schedule')],
        [InlineKeyboardButton("📋 Today", callback_data='today')],
        [InlineKeyboardButton("📊 Report", callback_data='report')],
    ]
    await update.message.reply_text(
        "🎬 *Anime Scheduler Bot*\n\nSelect an option:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    
    if data == 'add_menu':
        keyboard = []
        for day in DAYS:
            keyboard.append([InlineKeyboardButton(day, callback_data=f'add_{day}')])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='start')])
        await query.edit_message_text(
            "➕ *Add Anime*\nSelect day:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif data == 'remove_menu':
        keyboard = []
        for day in DAYS:
            keyboard.append([InlineKeyboardButton(day, callback_data=f'remove_{day}')])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='start')])
        await query.edit_message_text(
            "❌ *Remove Anime*\nSelect day:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif data == 'start':
        keyboard = [
            [InlineKeyboardButton("➕ Add Anime", callback_data='add_menu')],
            [InlineKeyboardButton("❌ Remove Anime", callback_data='remove_menu')],
            [InlineKeyboardButton("📅 Schedule", callback_data='schedule')],
            [InlineKeyboardButton("📋 Today", callback_data='today')],
            [InlineKeyboardButton("📊 Report", callback_data='report')],
        ]
        await query.edit_message_text(
            "🎬 *Anime Scheduler Bot*\n\nSelect an option:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif data.startswith('add_'):
        day = data.replace('add_', '')
        user_state[user_id] = {'action': 'adding', 'day': day}
        await query.edit_message_text(
            f"📝 *Add to {day}*\n\nSend anime name.\nFor multiple: Anime1, Anime2, Anime3\n\nSend /cancel to cancel",
            parse_mode='Markdown'
        )
    
    elif data.startswith('remove_'):
        day = data.replace('remove_', '')
        anime_list = db.get_schedule(user_id, day)
        
        if anime_list:
            keyboard = []
            for anime in anime_list:
                name = anime[0]
                keyboard.append([InlineKeyboardButton(f"❌ {name}", callback_data=f'del_{day}_{name}')])
            keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='remove_menu')])
            await query.edit_message_text(
                f"Select anime to remove from {day}:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text(
                f"No anime in {day}!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='start')]])
            )
    
    elif data.startswith('del_'):
        parts = data.split('_', 2)
        day = parts[1]
        anime_name = parts[2]
        db.remove_anime(user_id, anime_name, day)
        await query.edit_message_text(f"✅ {anime_name} removed from {day}!")
    
    elif data == 'schedule':
        schedule = db.get_full_schedule(user_id)
        msg = "📅 *Schedule*\n\n"
        has = False
        for day, animes in schedule.items():
            if animes:
                has = True
                msg += f"*{day}:*\n"
                for a in animes:
                    msg += f"  • {a}\n"
                msg += "\n"
        if not has:
            msg = "No anime added yet!"
        await query.edit_message_text(
            msg,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='start')]])
        )
    
    elif data == 'today':
        today_name = DAYS[datetime.now(pytz.timezone(TIMEZONE)).weekday()]
        animes = db.get_schedule(user_id, today_name)
        if animes:
            keyboard = []
            for a in animes:
                name = a[0]
                keyboard.append([
                    InlineKeyboardButton(f"✅ {name}", callback_data=f'done_{name}'),
                    InlineKeyboardButton(f"❌ {name}", callback_data=f'skip_{name}')
                ])
            keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='start')])
            await query.edit_message_text(
                f"📋 *{today_name}'s Anime*",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                f"No anime for {today_name}!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='start')]])
            )
    
    elif data.startswith('done_'):
        name = data[5:]
        today_name = DAYS[datetime.now(pytz.timezone(TIMEZONE)).weekday()]
        db.add_tracking(user_id, name, today_name, 'done')
        await query.edit_message_text(f"✅ {name} - Done!")
    
    elif data.startswith('skip_'):
        name = data[5:]
        today_name = DAYS[datetime.now(pytz.timezone(TIMEZONE)).weekday()]
        db.add_tracking(user_id, name, today_name, 'skipped')
        await query.edit_message_text(f"❌ {name} - Skipped!")
    
    elif data == 'report':
        stats = db.get_weekly_stats(user_id)
        done = stats.get('done', 0)
        skip = stats.get('skipped', 0)
        total = done + skip
        if total > 0:
            rate = (done/total)*100
            msg = f"📊 *Weekly Report*\n\n✅ Done: {done}\n❌ Skipped: {skip}\n📈 Rate: {rate:.1f}%"
        else:
            msg = "No data this week!"
        await query.edit_message_text(
            msg,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='start')]])
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id in user_state and user_state[user_id]['action'] == 'adding':
        day = user_state[user_id]['day']
        
        if ',' in text:
            anime_list = [a.strip() for a in text.split(',') if a.strip()]
            added = db.add_multiple_anime(user_id, anime_list, day)
            await update.message.reply_text(f"✅ Added {added} anime to {day}!")
        else:
            if db.add_anime(user_id, text.strip(), day):
                await update.message.reply_text(f"✅ {text} added to {day}!")
            else:
                await update.message.reply_text(f"⚠️ {text} already exists!")
        
        del user_state[user_id]

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_state:
        del user_state[user_id]
    await update.message.reply_text("✅ Cancelled!")

async def daily_notify(context: ContextTypes.DEFAULT_TYPE):
    today_name = DAYS[datetime.now(pytz.timezone(TIMEZONE)).weekday()]
    users = db.get_all_users()
    for uid in users:
        try:
            animes = db.get_schedule(uid, today_name)
            if animes:
                keyboard = []
                msg = f"⏰ *Good Morning!*\n\n📺 *{today_name}'s Anime:*\n"
                for a in animes:
                    name = a[0]
                    msg += f"• {name}\n"
                    keyboard.append([
                        InlineKeyboardButton(f"✅ {name}", callback_data=f'done_{name}'),
                        InlineKeyboardButton(f"❌ {name}", callback_data=f'skip_{name}')
                    ])
                await context.bot.send_message(
                    uid, msg,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
        except:
            pass

def main():
    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=10000), daemon=True)
    flask_thread.start()
    
    app_bot = Application.builder().token(BOT_TOKEN).build()
    
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CallbackQueryHandler(button_click))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app_bot.add_handler(CommandHandler("cancel", cancel))
    
    scheduler = AsyncIOScheduler(timezone=pytz.timezone(TIMEZONE))
    scheduler.add_job(daily_notify, 'cron', hour=8, minute=0, args=[app_bot])
    scheduler.start()
    
    logger.info("Bot started!")
    app_bot.run_polling()

if __name__ == '__main__':
    main()
