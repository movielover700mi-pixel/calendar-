FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files
COPY . .

# Create data folder
RUN mkdir -p data

# Expose port
EXPOSE 10000

# Run both Flask and Bot together
CMD gunicorn bot:app --bind 0.0.0.0:10000 --daemon && python bot.py
