import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.error import TelegramError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, date, timedelta
import pytz
from config import BOT_TOKEN, NOTIFICATION_HOUR, NOTIFICATION_MINUTE, TIMEZONE
from database import Database
from flask import Flask
import threading
import os
import signal
import sys

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask App
app = Flask(__name__)

@app.route('/')
def home():
    return "Anime Scheduler Bot is Running! 🎬"

@app.route('/health')
def health():
    return {"status": "healthy"}, 200

# Database
db = Database()

# Days
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

# Store user states temporarily
user_states = {}

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    keyboard = [
        [InlineKeyboardButton("➕ Add Anime", callback_data='menu_add')],
        [InlineKeyboardButton("❌ Remove Anime", callback_data='menu_remove')],
        [InlineKeyboardButton("📅 Full Schedule", callback_data='full_schedule')],
        [InlineKeyboardButton("📋 Today's Anime", callback_data='today')],
        [InlineKeyboardButton("📊 Weekly Report", callback_data='weekly_report')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎬 *Anime Schedule Manager*\n\n"
        "Welcome! Manage your anime schedule easily.\n\n"
        "• Click *Add Anime* to add new anime\n"
        "• Click *Remove Anime* to remove anime\n"
        "• Get daily notifications at 8:00 AM",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show day selection for adding anime"""
    keyboard = []
    for day in DAYS:
        keyboard.append([InlineKeyboardButton(f"📅 {day}", callback_data=f'add_day_{day}')])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='back_main')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "➕ *Add Anime*\n\nSelect the day:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show day selection for removing anime"""
    keyboard = []
    for day in DAYS:
        keyboard.append([InlineKeyboardButton(f"📅 {day}", callback_data=f'remove_day_{day}')])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='back_main')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "❌ *Remove Anime*\n\nSelect the day:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all button clicks"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    try:
        # Main Menu
        if data == 'menu_add':
            await query.message.delete()
            await add_command(update, context)
        
        elif data == 'menu_remove':
            await query.message.delete()
            await remove_command(update, context)
        
        elif data == 'back_main':
            await query.message.delete()
            await start(update, context)
        
        elif data == 'full_schedule':
            await show_schedule(update, context)
        
        elif data == 'today':
            await show_today(update, context)
        
        elif data == 'weekly_report':
            await weekly_report(update, context)
        
        # Add anime - day selected
        elif data.startswith('add_day_'):
            day = data.replace('add_day_', '')
            user_states[user_id] = {'action': 'add', 'day': day}
            await query.message.delete()
            await query.message.reply_text(
                f"📝 *Adding anime to {day}*\n\n"
                "Send me the anime name.\n"
                "For multiple anime, send: Anime1, Anime2, Anime3\n\n"
                "Example: Naruto, One Piece, Demon Slayer\n\n"
                "Send /cancel to cancel",
                parse_mode='Markdown'
            )
        
        # Remove anime - day selected
        elif data.startswith('remove_day_'):
            day = data.replace('remove_day_', '')
            anime_list = db.get_schedule(user_id, day)
            
            if anime_list:
                keyboard = []
                for anime in anime_list:
                    anime_name = anime[0]
                    keyboard.append([InlineKeyboardButton(f"❌ {anime_name}", callback_data=f'remove_anime_{day}_{anime_name}')])
                keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='menu_remove')])
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.message.delete()
                await query.message.reply_text(
                    f"❌ *Remove from {day}*\n\nSelect anime to remove:",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await query.message.delete()
                await query.message.reply_text(
                    f"❌ No anime found in {day}!\n\nUse /add to add anime first."
                )
        
        # Remove specific anime
        elif data.startswith('remove_anime_'):
            parts = data.replace('remove_anime_', '').split('_', 1)
            day = parts[0]
            anime_name = parts[1]
            
            if db.remove_anime(user_id, anime_name, day):
                await query.message.delete()
                await query.message.reply_text(
                    f"✅ *{anime_name}* removed from {day}!",
                    parse_mode='Markdown'
                )
            else:
                await query.message.delete()
                await query.message.reply_text("❌ Failed to remove anime!")
        
        # Done/Skip tracking
        elif data.startswith('done_'):
            anime_name = data[5:]
            today_bd = datetime.now(pytz.timezone(TIMEZONE))
            today_name = DAYS[today_bd.weekday()]
            db.add_tracking(user_id, anime_name, today_name, 'done')
            await query.edit_message_text(f"✅ *{anime_name}* - Done! 🎉", parse_mode='Markdown')
        
        elif data.startswith('skip_'):
            anime_name = data[5:]
            today_bd = datetime.now(pytz.timezone(TIMEZONE))
            today_name = DAYS[today_bd.weekday()]
            db.add_tracking(user_id, anime_name, today_name, 'skipped')
            await query.edit_message_text(f"❌ *{anime_name}* - Skipped!", parse_mode='Markdown')
    
    except Exception as e:
        logger.error(f"Error in button_handler: {e}")
        await query.edit_message_text("❌ Something went wrong!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages for adding anime"""
    user_id = update.effective_user.id
    text = update.message.text
    
    # Check if user is in add mode
    if user_id in user_states and user_states[user_id]['action'] == 'add':
        day = user_states[user_id]['day']
        
        # Check for multiple anime (comma separated)
        if ',' in text:
            anime_list = [name.strip() for name in text.split(',') if name.strip()]
            added = db.add_multiple_anime(user_id, anime_list, day)
            await update.message.reply_text(
                f"✅ {added}/{len(anime_list)} anime added to {day}!\n"
                f"📺 {', '.join(anime_list)}"
            )
        else:
            # Single anime
            if db.add_anime(user_id, text.strip(), day):
                await update.message.reply_text(f"✅ *{text.strip()}* added to {day}!", parse_mode='Markdown')
            else:
                await update.message.reply_text(f"⚠️ *{text.strip()}* already exists in {day}!", parse_mode='Markdown')
        
        # Clear user state
        del user_states[user_id]

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation"""
    user_id = update.effective_user.id
    if user_id in user_states:
        del user_states[user_id]
    await update.message.reply_text("✅ Operation cancelled!")

async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show full schedule"""
    user_id = update.effective_user.id
    full_schedule = db.get_full_schedule(user_id)
    
    message = "📅 *Weekly Anime Schedule*\n\n"
    has_anime = False
    
    for day, anime_list in full_schedule.items():
        if anime_list:
            has_anime = True
            message += f"*{day}:*\n"
            for idx, anime in enumerate(anime_list, 1):
                message += f"  {idx}. {anime}\n"
            message += "\n"
    
    if not has_anime:
        message = "❌ No anime added yet!\n\nClick *Add Anime* to start."
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query_or_message(update, message, reply_markup)

async def show_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show today's anime"""
    user_id = update.effective_user.id
    today_bd = datetime.now(pytz.timezone(TIMEZONE))
    today_name = DAYS[today_bd.weekday()]
    
    today_anime = db.get_schedule(user_id, today_name)
    
    if today_anime:
        keyboard = []
        for anime_tuple in today_anime:
            anime = anime_tuple[0]
            keyboard.append([
                InlineKeyboardButton(f"✅ {anime}", callback_data=f'done_{anime}'),
                InlineKeyboardButton(f"❌ {anime}", callback_data=f'skip_{anime}')
            ])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='back_main')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = f"📋 *Today's Anime ({today_name})*\n\nClick to update status:"
        await query_or_message(update, message, reply_markup)
    else:
        message = f"🎉 No anime scheduled for {today_name}!"
        await query_or_message(update, message)

async def weekly_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Weekly report"""
    user_id = update.effective_user.id
    stats = db.get_weekly_stats(user_id)
    
    total_done = stats.get('done', 0)
    total_skip = stats.get('skipped', 0)
    total = total_done + total_skip
    
    message = "📊 *Weekly Report*\n\n"
    
    if total > 0:
        completion_rate = (total_done / total) * 100
        message += f"✅ Done: *{total_done}*\n"
        message += f"❌ Skipped: *{total_skip}*\n"
        message += f"📈 Rate: *{completion_rate:.1f}%*\n"
    else:
        message += "No data this week!"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='back_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query_or_message(update, message, reply_markup)

async def query_or_message(update: Update, message, reply_markup=None):
    """Helper function to send message"""
    try:
        if update.callback_query:
            await update.callback_query.message.delete()
            await update.callback_query.message.reply_text(
                message, reply_markup=reply_markup, parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                message, reply_markup=reply_markup, parse_mode='Markdown'
            )
    except:
        pass

async def send_daily_notification(context: ContextTypes.DEFAULT_TYPE):
    """Daily morning notification"""
    try:
        today_bd = datetime.now(pytz.timezone(TIMEZONE))
        today_name = DAYS[today_bd.weekday()]
        users = db.get_all_users()
        
        for user_id in users:
            try:
                today_anime = db.get_schedule(user_id, today_name)
                
                if today_anime:
                    keyboard = []
                    message = f"⏰ *Good Morning!*\n\n📺 *{today_name}'s Anime:*\n"
                    
                    for idx, anime_tuple in enumerate(today_anime, 1):
                        anime = anime_tuple[0]
                        message += f"{idx}. {anime}\n"
                        keyboard.append([
                            InlineKeyboardButton(f"✅ {anime}", callback_data=f'done_{anime}'),
                            InlineKeyboardButton(f"❌ {anime}", callback_data=f'skip_{anime}')
                        ])
                    
                    message += "\nUpdate status 👇"
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
            except:
                pass
    except Exception as e:
        logger.error(f"Notification error: {e}")

async def send_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    """Weekly report"""
    try:
        users = db.get_all_users()
        for user_id in users:
            try:
                stats = db.get_weekly_stats(user_id)
                total_done = stats.get('done', 0)
                total_skip = stats.get('skipped', 0)
                total = total_done + total_skip
                
                if total > 0:
                    rate = (total_done / total) * 100
                    message = f"📊 *Weekly Report*\n\n✅ Done: {total_done}\n❌ Skipped: {total_skip}\n📈 Rate: {rate:.1f}%"
                    await context.bot.send_message(chat_id=user_id, text=message, parse_mode='Markdown')
            except:
                pass
    except Exception as e:
        logger.error(f"Weekly report error: {e}")

def run_flask():
    app.run(host='0.0.0.0', port=10000)

def main():
    try:
        signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
        signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
        
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        application = Application.builder().token(BOT_TOKEN).build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("add", add_command))
        application.add_handler(CommandHandler("remove", remove_command))
        application.add_handler(CommandHandler("schedule", show_schedule))
        application.add_handler(CommandHandler("today", show_today))
        application.add_handler(CommandHandler("report", weekly_report))
        application.add_handler(CommandHandler("cancel", cancel_command))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_error_handler(error_handler)
        
        scheduler = AsyncIOScheduler(timezone=pytz.timezone(TIMEZONE))
        scheduler.add_job(send_daily_notification, 'cron', hour=8, minute=0, args=[application])
        scheduler.add_job(send_weekly_report, 'cron', day_of_week='sun', hour=22, minute=0, args=[application])
        scheduler.start()
        
        logger.info("Bot is running...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Critical error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
