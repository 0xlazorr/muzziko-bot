FROM python:3.12-slim

# Install system dependencies (ffmpeg is essential for audio extraction/conversion)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code (secrets in .env are excluded by .dockerignore and .gitignore)
COPY . .

# Run the Telegram bot
CMD ["python", "bot.py"]
