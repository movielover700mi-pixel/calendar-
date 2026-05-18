FROM python:3.11-slim

WORKDIR /app

# সিস্টেম ডিপেন্ডেন্সি
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python ডিপেন্ডেন্সি
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# অ্যাপ ফাইল কপি
COPY . .

# পোর্ট এক্সপোজ
EXPOSE 10000

# বট এবং Flask একসাথে চালানোর স্ক্রিপ্ট
COPY start.sh /start.sh
RUN chmod +x /start.sh

CMD ["/start.sh"]
