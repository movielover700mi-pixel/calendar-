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

# লগিং সেটআপ
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

# দিনের লিস্ট
DAYS = ['সোমবার', 'মঙ্গলবার', 'বুধবার', 'বৃহস্পতিবার', 'শুক্রবার', 'শনিবার', 'রবিবার']

# ইমোজি ম্যাপিং
EMOJI = {
    'সোমবার': '📅',
    'মঙ্গলবার': '📅',
    'বুধবার': '📅',
    'বৃহস্পতিবার': '📅',
    'শুক্রবার': '📅',
    'শনিবার': '🎉',
    'রবিবার': '😴'
}

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ কিছু একটা সমস্যা হয়েছে! পরে আবার চেষ্টা করুন।"
            )
    except:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    try:
        keyboard = [
            [InlineKeyboardButton("📅 পুরো শিডিউল", callback_data='full_schedule')],
            [InlineKeyboardButton("📋 আজকের অ্যানিমি", callback_data='today')],
            [InlineKeyboardButton("➕ অ্যানিমি অ্যাড", callback_data='add_info')],
            [InlineKeyboardButton("❌ অ্যানিমি রিমুভ", callback_data='remove_info')],
            [InlineKeyboardButton("📊 সাপ্তাহিক রিপোর্ট", callback_data='weekly_report')],
            [InlineKeyboardButton("ℹ️ হেল্প", callback_data='help_info')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🎬 *Anime Schedule Manager Bot*\n\n"
            "স্বাগতম! আমি আপনার অ্যানিমি শিডিউল ম্যানেজ করবো।\n\n"
            "📌 *প্রধান কমান্ডসমূহ:*\n"
            "• /add [দিন] [অ্যানিমি] - অ্যানিমি অ্যাড\n"
            "• /add\\_group [দিন] [অ্যানিমি১, অ্যানিমি২] - একাধিক অ্যাড\n"
            "• /remove [দিন] [অ্যানিমি] - রিমুভ\n"
            "• /schedule - পুরো শিডিউল\n"
            "• /today - আজকের লিস্ট\n"
            "• /report - সাপ্তাহিক রিপোর্ট\n\n"
            "⏰ প্রতিদিন সকাল ৮টায় অটো নোটিফিকেশন পাবেন!",
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
                "❌ *ভুল ব্যবহার!*\n\n"
                "সঠিক নিয়ম:\n"
                "`/add সোমবার নারুতো`\n\n"
                "দিন হতে হবে: সোমবার, মঙ্গলবার, বুধবার, বৃহস্পতিবার, শুক্রবার, শনিবার, রবিবার",
                parse_mode='Markdown'
            )
            return
        
        day = context.args[0]
        anime_name = ' '.join(context.args[1:])
        
        if day not in DAYS:
            await update.message.reply_text(
                f"❌ ভুল দিন! সঠিক দিন: {', '.join(DAYS)}"
            )
            return
        
        if db.add_anime(user_id, anime_name, day):
            await update.message.reply_text(
                f"✅ *{anime_name}* - {day} তে অ্যাড করা হয়েছে! {EMOJI.get(day, '📺')}",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"⚠️ *{anime_name}* ইতিমধ্যে {day} তে আছে!",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Error in add_anime: {e}")
        await update.message.reply_text("❌ অ্যানিমি অ্যাড করতে সমস্যা হয়েছে!")

async def add_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add multiple anime at once"""
    try:
        user_id = update.effective_user.id
        
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ *ভুল ব্যবহার!*\n\n"
                "সঠিক নিয়ম:\n"
                "`/add_group সোমবার নারুতো, ওয়ানপিস, ডেমন স্লেয়ার`\n\n"
                "কমা দিয়ে অ্যানিমির নাম আলাদা করুন",
                parse_mode='Markdown'
            )
            return
        
        day = context.args[0]
        anime_text = ' '.join(context.args[1:])
        anime_list = [name.strip() for name in anime_text.split(',') if name.strip()]
        
        if not anime_list:
            await update.message.reply_text("❌ কোনো অ্যানিমির নাম পাওয়া যায়নি!")
            return
        
        if day not in DAYS:
            await update.message.reply_text(f"❌ ভুল দিন! সঠিক দিন: {', '.join(DAYS)}")
            return
        
        added = db.add_multiple_anime(user_id, anime_list, day)
        
        await update.message.reply_text(
            f"✅ {added}/{len(anime_list)}টি অ্যানিমি {day} তে অ্যাড করা হয়েছে!\n"
            f"📺 {', '.join(anime_list)}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in add_group: {e}")
        await update.message.reply_text("❌ অ্যানিমি অ্যাড করতে সমস্যা হয়েছে!")

async def remove_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove anime from schedule"""
    try:
        user_id = update.effective_user.id
        
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ *ভুল ব্যবহার!*\n\n"
                "সঠিক নিয়ম: `/remove সোমবার নারুতো`",
                parse_mode='Markdown'
            )
            return
        
        day = context.args[0]
        anime_name = ' '.join(context.args[1:])
        
        if db.remove_anime(user_id, anime_name, day):
            await update.message.reply_text(
                f"✅ *{anime_name}* {day} থেকে রিমুভ করা হয়েছে!",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ *{anime_name}* {day} তে পাওয়া যায়নি!",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Error in remove_anime: {e}")
        await update.message.reply_text("❌ রিমুভ করতে সমস্যা হয়েছে!")

async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show full week schedule"""
    try:
        user_id = update.effective_user.id
        full_schedule = db.get_full_schedule(user_id)
        
        message = "📅 *সাপ্তাহিক অ্যানিমি শিডিউল*\n\n"
        has_anime = False
        
        for day, anime_list in full_schedule.items():
            if anime_list:
                has_anime = True
                message += f"*{EMOJI.get(day, '📺')} {day}:*\n"
                for idx, anime in enumerate(anime_list, 1):
                    message += f"  {idx}. {anime}\n"
                message += "\n"
        
        if not has_anime:
            message = "❌ *এখনো কোনো অ্যানিমি অ্যাড করা হয়নি!*\n\n"
            message += "অ্যানিমি অ্যাড করতে:\n"
            message += "`/add সোমবার নারুতো`"
        
        # মেসেজ পাঠান (update টাইপ চেক করে)
        if update.callback_query:
            await update.callback_query.message.reply_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error in show_schedule: {e}")
        error_msg = "❌ শিডিউল দেখাতে সমস্যা হয়েছে!"
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
                f"📋 *আজ ({today_name}) এর অ্যানিমি* {EMOJI.get(today_name, '📺')}\n\n"
                "স্ট্যাটাস আপডেট করতে বাটনে ক্লিক করুন 👇"
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
            message = f"🎉 আজ ({today_name}) কোনো অ্যানিমি শিডিউল নেই! {EMOJI.get(today_name, '😊')}"
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
        
        message = "📊 *সাপ্তাহিক রিপোর্ট (গত ৭ দিন)*\n\n"
        
        if total > 0:
            completion_rate = (total_done / total) * 100
            message += f"✅ Done: *{total_done}* টি\n"
            message += f"❌ Skipped: *{total_skip}* টি\n"
            message += f"📈 কমপ্লিশন রেট: *{completion_rate:.1f}%*\n\n"
            
            if completion_rate == 100:
                message += "🎉 অসাধারণ! সব অ্যানিমি দেখা শেষ!"
            elif completion_rate >= 70:
                message += "👍 ভালোই চলছে! চালিয়ে যান!"
            elif completion_rate >= 40:
                message += "😐 মোটামুটি, আরও উন্নতি করতে হবে!"
            else:
                message += "💪 আগামী সপ্তাহে আরও ভালো করার চেষ্টা করুন!"
        else:
            message += "❌ *এই সপ্তাহে কোনো ডেটা নেই!*\n\n"
            message += "অ্যানিমি দেখার পর ✅ Done বা ❌ Skip বাটনে ক্লিক করুন।"
        
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
                "➕ *অ্যানিমি অ্যাড করার নিয়ম:*\n\n"
                "*একটি অ্যানিমি:*\n"
                "`/add সোমবার নারুতো`\n\n"
                "*একাধিক অ্যানিমি:*\n"
                "`/add_group সোমবার নারুতো, ওয়ানপিস, ডেমন স্লেয়ার`\n\n"
                "*দিনের তালিকা:*\n"
                "সোমবার, মঙ্গলবার, বুধবার, বৃহস্পতিবার, শুক্রবার, শনিবার, রবিবার",
                parse_mode='Markdown'
            )
        
        elif query.data == 'remove_info':
            await query.message.reply_text(
                "❌ *অ্যানিমি রিমুভ করার নিয়ম:*\n\n"
                "`/remove সোমবার নারুতো`\n\n"
                "শিডিউল দেখতে: /schedule",
                parse_mode='Markdown'
            )
        
        elif query.data == 'help_info':
            await query.message.reply_text(
                "ℹ️ *হেল্প মেনু*\n\n"
                "*প্রধান কমান্ড:*\n"
                "• /start - মেইন মেনু\n"
                "• /add [দিন] [নাম] - অ্যানিমি অ্যাড\n"
                "• /add_group [দিন] [নামগুলো] - একাধিক অ্যাড\n"
                "• /remove [দিন] [নাম] - রিমুভ\n"
                "• /schedule - সাপ্তাহিক শিডিউল\n"
                "• /today - আজকের তালিকা\n"
                "• /report - সাপ্তাহিক রিপোর্ট\n\n"
                "⏰ প্রতিদিন সকাল ৮টায় অটো নোটিফিকেশন\n"
                "📊 প্রতি রবিবার রাত ১০টায় সাপ্তাহিক রিপোর্ট",
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
        await query.edit_message_text("❌ কোনো সমস্যা হয়েছে! আবার চেষ্টা করুন।")

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
                        f"⏰ *সুপ্রভাত! শুভ {today_name}*\n\n"
                        f"📺 *আজকের অ্যানিমি লিস্ট:*\n"
                    )
                    
                    for idx, anime in enumerate(anime_list, 1):
                        message += f"{idx}. {anime}\n"
                        keyboard.append([
                            InlineKeyboardButton(f"✅ {anime}", callback_data=f'done_{anime}'),
                            InlineKeyboardButton(f"❌ {anime}", callback_data=f'skip_{anime}')
                        ])
                    
                    message += "\nস্ট্যাটাস আপডেট করতে বাটনে ক্লিক করুন 👇"
                    
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
                        "📊 *সাপ্তাহিক রিপোর্ট*\n\n"
                        f"✅ Done: *{total_done}*\n"
                        f"❌ Skipped: *{total_skip}*\n"
                        f"📈 রেট: *{completion_rate:.1f}%*\n\n"
                    )
                    
                    if completion_rate == 100:
                        message += "🎉 অসাধারণ! সব অ্যানিমি দেখা শেষ!"
                    elif completion_rate >= 70:
                        message += "👍 ভালোই চলছে!"
                    else:
                        message += "💪 আগামী সপ্তাহে আরও ভালো করবেন!"
                    
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
