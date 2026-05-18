import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
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

# Flask App for Render Health Check
app = Flask(__name__)

@app.route('/')
def home():
    return "Anime Scheduler Bot is Running! 🎬"

@app.route('/health')
def health():
    return {"status": "healthy"}, 200

# Database Initialize
db = Database()

# Days list
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

# Emoji mapping
EMOJI = {
    'Monday': '📅',
    'Tuesday': '📅',
    'Wednesday': '📅',
    'Thursday': '📅',
    'Friday': '📅',
    'Saturday': '🎉',
    'Sunday': '😴'
}

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ Something went wrong! Please try again later."
            )
    except:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    try:
        keyboard = [
            [InlineKeyboardButton("📅 Full Schedule", callback_data='full_schedule')],
            [InlineKeyboardButton("📋 Today's Anime", callback_data='today')],
            [InlineKeyboardButton("➕ Add Anime", callback_data='add_info')],
            [InlineKeyboardButton("❌ Remove Anime", callback_data='remove_info')],
            [InlineKeyboardButton("📊 Weekly Report", callback_data='weekly_report')],
            [InlineKeyboardButton("ℹ️ Help", callback_data='help_info')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🎬 *Anime Schedule Manager Bot*\n\n"
            "Welcome! I'll manage your anime schedule.\n\n"
            "📌 *Main Commands:*\n"
            "• /add [day] [anime] - Add anime\n"
            "• /add\\_group [day] [anime1, anime2] - Add multiple\n"
            "• /remove [day] [anime] - Remove anime\n"
            "• /schedule - Full schedule\n"
            "• /today - Today's list\n"
            "• /report - Weekly report\n\n"
            "⏰ Daily notification at 8:00 AM!",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in start: {e}")

async def add_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add single anime"""
    try:
        user_id = update.effective_user.id
        
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ *Wrong usage!*\n\n"
                "Correct format:\n"
                "`/add Monday Naruto`\n\n"
                "Days: Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday",
                parse_mode='Markdown'
            )
            return
        
        day = context.args[0].capitalize()
        anime_name = ' '.join(context.args[1:])
        
        if day not in DAYS:
            await update.message.reply_text(
                f"❌ Invalid day! Valid days: {', '.join(DAYS)}"
            )
            return
        
        if db.add_anime(user_id, anime_name, day):
            await update.message.reply_text(
                f"✅ *{anime_name}* added to {day}! {EMOJI.get(day, '📺')}",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"⚠️ *{anime_name}* is already in {day}!",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Error in add_anime: {e}")
        await update.message.reply_text("❌ Failed to add anime!")

async def add_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add multiple anime at once"""
    try:
        user_id = update.effective_user.id
        
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ *Wrong usage!*\n\n"
                "Correct format:\n"
                "`/add_group Saturday Naruto, One Piece, Demon Slayer`\n\n"
                "Separate anime names with comma",
                parse_mode='Markdown'
            )
            return
        
        day = context.args[0].capitalize()
        anime_text = ' '.join(context.args[1:])
        anime_list = [name.strip() for name in anime_text.split(',') if name.strip()]
        
        if not anime_list:
            await update.message.reply_text("❌ No anime names found!")
            return
        
        if day not in DAYS:
            await update.message.reply_text(f"❌ Invalid day! Valid days: {', '.join(DAYS)}")
            return
        
        added = db.add_multiple_anime(user_id, anime_list, day)
        
        await update.message.reply_text(
            f"✅ {added}/{len(anime_list)} anime added to {day}!\n"
            f"📺 {', '.join(anime_list)}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in add_group: {e}")
        await update.message.reply_text("❌ Failed to add anime!")

async def remove_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove anime from schedule"""
    try:
        user_id = update.effective_user.id
        
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ *Wrong usage!*\n\n"
                "Correct format: `/remove Monday Naruto`",
                parse_mode='Markdown'
            )
            return
        
        day = context.args[0].capitalize()
        anime_name = ' '.join(context.args[1:])
        
        if db.remove_anime(user_id, anime_name, day):
            await update.message.reply_text(
                f"✅ *{anime_name}* removed from {day}!",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ *{anime_name}* not found in {day}!",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Error in remove_anime: {e}")
        await update.message.reply_text("❌ Failed to remove anime!")

async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show full week schedule"""
    try:
        user_id = update.effective_user.id
        full_schedule = db.get_full_schedule(user_id)
        
        message = "📅 *Weekly Anime Schedule*\n\n"
        has_anime = False
        
        for day, anime_list in full_schedule.items():
            if anime_list:
                has_anime = True
                message += f"*{EMOJI.get(day, '📺')} {day}:*\n"
                for idx, anime in enumerate(anime_list, 1):
                    message += f"  {idx}. {anime}\n"
                message += "\n"
        
        if not has_anime:
            message = "❌ *No anime added yet!*\n\n"
            message += "To add anime:\n"
            message += "`/add Monday Naruto`"
        
        if update.callback_query:
            await update.callback_query.message.reply_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error in show_schedule: {e}")
        error_msg = "❌ Failed to show schedule!"
        if update.callback_query:
            await update.callback_query.message.reply_text(error_msg)
        else:
            await update.message.reply_text(error_msg)

async def show_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show today's anime list with action buttons"""
    try:
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
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            message = (
                f"📋 *Today's Anime ({today_name})* {EMOJI.get(today_name, '📺')}\n\n"
                "Click buttons to update status 👇"
            )
            
            if update.callback_query:
                await update.callback_query.message.reply_text(
                    message, reply_markup=reply_markup, parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    message, reply_markup=reply_markup, parse_mode='Markdown'
                )
        else:
            message = f"🎉 No anime scheduled for today ({today_name})! {EMOJI.get(today_name, '😊')}"
            if update.callback_query:
                await update.callback_query.message.reply_text(message)
            else:
                await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error in show_today: {e}")

async def weekly_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show weekly report"""
    try:
        user_id = update.effective_user.id
        stats = db.get_weekly_stats(user_id)
        
        total_done = stats.get('done', 0)
        total_skip = stats.get('skipped', 0)
        total = total_done + total_skip
        
        message = "📊 *Weekly Report (Last 7 Days)*\n\n"
        
        if total > 0:
            completion_rate = (total_done / total) * 100
            message += f"✅ Done: *{total_done}*\n"
            message += f"❌ Skipped: *{total_skip}*\n"
            message += f"📈 Completion Rate: *{completion_rate:.1f}%*\n\n"
            
            if completion_rate == 100:
                message += "🎉 Perfect! All anime watched!"
            elif completion_rate >= 70:
                message += "👍 Good job! Keep it up!"
            elif completion_rate >= 40:
                message += "😐 Not bad, try to improve!"
            else:
                message += "💪 Try to do better next week!"
        else:
            message += "❌ *No data this week!*\n\n"
            message += "Click ✅ Done or ❌ Skip after watching anime."
        
        if update.callback_query:
            await update.callback_query.message.reply_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in weekly_report: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all button callbacks"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    try:
        if query.data == 'full_schedule':
            await show_schedule(update, context)
        
        elif query.data == 'today':
            await show_today(update, context)
        
        elif query.data == 'weekly_report':
            await weekly_report(update, context)
        
        elif query.data == 'add_info':
            await query.message.reply_text(
                "➕ *How to Add Anime:*\n\n"
                "*Single Anime:*\n"
                "`/add Monday Naruto`\n\n"
                "*Multiple Anime:*\n"
                "`/add_group Saturday Naruto, One Piece, Demon Slayer`\n\n"
                "*Valid Days:*\n"
                "Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday",
                parse_mode='Markdown'
            )
        
        elif query.data == 'remove_info':
            await query.message.reply_text(
                "❌ *How to Remove Anime:*\n\n"
                "`/remove Monday Naruto`\n\n"
                "View schedule: /schedule",
                parse_mode='Markdown'
            )
        
        elif query.data == 'help_info':
            await query.message.reply_text(
                "ℹ️ *Help Menu*\n\n"
                "*Main Commands:*\n"
                "• /start - Main menu\n"
                "• /add [day] [name] - Add anime\n"
                "• /add_group [day] [names] - Add multiple\n"
                "• /remove [day] [name] - Remove anime\n"
                "• /schedule - Weekly schedule\n"
                "• /today - Today's list\n"
                "• /report - Weekly report\n\n"
                "⏰ Daily notification at 8:00 AM\n"
                "📊 Weekly report every Sunday 10:00 PM",
                parse_mode='Markdown'
            )
        
        elif query.data.startswith('done_'):
            anime_name = query.data[5:]
            today_bd = datetime.now(pytz.timezone(TIMEZONE))
            today_name = DAYS[today_bd.weekday()]
            db.add_tracking(user_id, anime_name, today_name, 'done')
            await query.edit_message_text(f"✅ *{anime_name}* - Done! 🎉", parse_mode='Markdown')
        
        elif query.data.startswith('skip_'):
            anime_name = query.data[5:]
            today_bd = datetime.now(pytz.timezone(TIMEZONE))
            today_name = DAYS[today_bd.weekday()]
            db.add_tracking(user_id, anime_name, today_name, 'skipped')
            await query.edit_message_text(f"❌ *{anime_name}* - Skipped!", parse_mode='Markdown')
    
    except Exception as e:
        logger.error(f"Error in button_handler: {e}")
        await query.edit_message_text("❌ Something went wrong! Please try again.")

async def send_daily_notification(context: ContextTypes.DEFAULT_TYPE):
    """Send daily morning notification to all users"""
    try:
        today_bd = datetime.now(pytz.timezone(TIMEZONE))
        today_name = DAYS[today_bd.weekday()]
        
        users = db.get_all_users()
        
        for user_id in users:
            try:
                today_anime = db.get_schedule(user_id, today_name)
                
                if today_anime:
                    keyboard = []
                    anime_list = [anime[0] for anime in today_anime]
                    
                    message = (
                        f"⏰ *Good Morning! Happy {today_name}*\n\n"
                        f"📺 *Today's Anime List:*\n"
                    )
                    
                    for idx, anime in enumerate(anime_list, 1):
                        message += f"{idx}. {anime}\n"
                        keyboard.append([
                            InlineKeyboardButton(f"✅ {anime}", callback_data=f'done_{anime}'),
                            InlineKeyboardButton(f"❌ {anime}", callback_data=f'skip_{anime}')
                        ])
                    
                    message += "\nClick buttons to update status 👇"
                    
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                    logger.info(f"Notification sent to user {user_id}")
                    
            except TelegramError as te:
                logger.warning(f"Telegram error for user {user_id}: {te}")
            except Exception as e:
                logger.error(f"Error sending notification to user {user_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error in daily notification: {e}")

async def send_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    """Send weekly report to all users"""
    try:
        users = db.get_all_users()
        
        for user_id in users:
            try:
                stats = db.get_weekly_stats(user_id)
                
                total_done = stats.get('done', 0)
                total_skip = stats.get('skipped', 0)
                total = total_done + total_skip
                
                if total > 0:
                    completion_rate = (total_done / total) * 100
                    message = (
                        "📊 *Weekly Report*\n\n"
                        f"✅ Done: *{total_done}*\n"
                        f"❌ Skipped: *{total_skip}*\n"
                        f"📈 Rate: *{completion_rate:.1f}%*\n\n"
                    )
                    
                    if completion_rate == 100:
                        message += "🎉 Excellent! All anime watched!"
                    elif completion_rate >= 70:
                        message += "👍 Good job!"
                    else:
                        message += "💪 Try to do better next week!"
                    
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode='Markdown'
                    )
                    logger.info(f"Weekly report sent to user {user_id}")
                    
            except Exception as e:
                logger.error(f"Error sending weekly report to user {user_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error in weekly report: {e}")

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    """Cleanup old tracking data"""
    try:
        db.cleanup_old_tracking()
        logger.info("Old tracking data cleaned up")
    except Exception as e:
        logger.error(f"Error in cleanup: {e}")

def run_flask():
    """Run Flask server for health checks"""
    try:
        app.run(host='0.0.0.0', port=10000)
    except Exception as e:
        logger.error(f"Flask server error: {e}")

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("Shutting down bot...")
    sys.exit(0)

def main():
    """Main function to run the bot"""
    try:
        # Signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start Flask in a separate thread
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        logger.info("Flask server started")
        
        # Bot Application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", start))
        application.add_handler(CommandHandler("add", add_anime))
        application.add_handler(CommandHandler("add_group", add_group))
        application.add_handler(CommandHandler("remove", remove_anime))
        application.add_handler(CommandHandler("schedule", show_schedule))
        application.add_handler(CommandHandler("today", show_today))
        application.add_handler(CommandHandler("report", weekly_report))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_error_handler(error_handler)
        
        # Setup scheduler
        scheduler = AsyncIOScheduler(timezone=pytz.timezone(TIMEZONE))
        
        # Daily morning notification (8:00 AM)
        scheduler.add_job(
            send_daily_notification,
            'cron',
            hour=NOTIFICATION_HOUR,
            minute=NOTIFICATION_MINUTE,
            args=[application]
        )
        
        # Weekly report (Sunday 10:00 PM)
        scheduler.add_job(
            send_weekly_report,
            'cron',
            day_of_week='sun',
            hour=22,
            minute=0,
            args=[application]
        )
        
        # Monthly cleanup
        scheduler.add_job(
            cleanup_job,
            'cron',
            day=1,
            hour=3,
            minute=0,
            args=[application]
        )
        
        scheduler.start()
        logger.info("Scheduler started")
        
        # Start the bot
        logger.info("Bot is running...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Critical error in main: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
