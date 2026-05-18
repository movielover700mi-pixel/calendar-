import sqlite3
from datetime import datetime, date
import os

class Database:
    def __init__(self):
        # ডেটা ডিরেক্টরি চেক
        os.makedirs('data', exist_ok=True)
        
        self.db_path = 'data/anime_schedule.db'
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
    
    def create_tables(self):
        # অ্যানিমি শিডিউল টেবিল
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                anime_name TEXT NOT NULL,
                day TEXT NOT NULL,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, anime_name, day)
            )
        ''')
        
        # ডেইলি ট্র্যাকিং টেবিল
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                anime_name TEXT NOT NULL,
                day TEXT NOT NULL,
                status TEXT NOT NULL,
                track_date DATE NOT NULL,
                tracked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # ইনডেক্স তৈরি
        self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_schedules_user_day 
            ON schedules(user_id, day)
        ''')
        
        self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_tracking_user_date 
            ON daily_tracking(user_id, track_date)
        ''')
        
        self.conn.commit()
    
    def add_anime(self, user_id, anime_name, day):
        try:
            self.cursor.execute(
                'INSERT INTO schedules (user_id, anime_name, day) VALUES (?, ?, ?)',
                (user_id, anime_name.strip(), day)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Already exists
    
    def add_multiple_anime(self, user_id, anime_list, day):
        added = 0
        for anime in anime_list:
            if self.add_anime(user_id, anime.strip(), day):
                added += 1
        return added
    
    def remove_anime(self, user_id, anime_name, day):
        self.cursor.execute(
            'DELETE FROM schedules WHERE user_id=? AND anime_name=? AND day=?',
            (user_id, anime_name.strip(), day)
        )
        self.conn.commit()
        return self.cursor.rowcount > 0
    
    def get_schedule(self, user_id, day=None):
        if day:
            self.cursor.execute(
                'SELECT anime_name FROM schedules WHERE user_id=? AND day=? ORDER BY added_date',
                (user_id, day)
            )
        else:
            self.cursor.execute(
                'SELECT day, anime_name FROM schedules WHERE user_id=? ORDER BY day, added_date',
                (user_id,)
            )
        return self.cursor.fetchall()
    
    def get_full_schedule(self, user_id):
        days = ['সোমবার', 'মঙ্গলবার', 'বুধবার', 'বৃহস্পতিবার', 'শুক্রবার', 'শনিবার', 'রবিবার']
        schedule = {}
        for day in days:
            anime_list = self.get_schedule(user_id, day)
            schedule[day] = [anime[0] for anime in anime_list]
        return schedule
    
    def clear_schedule(self, user_id):
        self.cursor.execute('DELETE FROM schedules WHERE user_id=?', (user_id,))
        self.conn.commit()
    
    def add_tracking(self, user_id, anime_name, day, status):
        today = date.today()
        self.cursor.execute(
            '''INSERT INTO daily_tracking (user_id, anime_name, day, status, track_date) 
               VALUES (?, ?, ?, ?, ?)''',
            (user_id, anime_name.strip(), day, status, today)
        )
        self.conn.commit()
    
    def get_weekly_stats(self, user_id):
        week_ago = date.today() - timedelta(days=7)
        self.cursor.execute(
            '''SELECT status, COUNT(*) as count FROM daily_tracking 
               WHERE user_id=? AND track_date >= ? 
               GROUP BY status''',
            (user_id, week_ago)
        )
        return dict(self.cursor.fetchall())
    
    def get_all_users(self):
        self.cursor.execute('SELECT DISTINCT user_id FROM schedules')
        return [user[0] for user in self.cursor.fetchall()]
    
    def cleanup_old_tracking(self):
        """৩০ দিনের পুরনো ট্র্যাকিং ডিলিট"""
        old_date = date.today() - timedelta(days=30)
        self.cursor.execute('DELETE FROM daily_tracking WHERE track_date < ?', (old_date,))
        self.conn.commit()
