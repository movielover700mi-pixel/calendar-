#!/bin/bash

# Flask ব্যাকগ্রাউন্ডে চালু
gunicorn bot:app --bind 0.0.0.0:10000 --daemon

# বট চালু
python bot.py
