import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).resolve().parent

# Load environment variables
load_dotenv(BASE_DIR / ".env")

# Telegram Bot Token (from @BotFather)
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Bot username (optional, without @)
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip()

# Audio download directory
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Maximum search results to fetch
MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", "10"))

# Page size for interactive search buttons
PAGE_SIZE = int(os.getenv("PAGE_SIZE", "5"))

# Audio quality: 320, 256, 192 (default 320 kbps for highest MP3 quality)
AUDIO_QUALITY = os.getenv("AUDIO_QUALITY", "320")

# Telegram bot file upload limit (in bytes, standard bot API limit is 50MB)
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024

# Timeout for network operations in seconds
REQUEST_TIMEOUT = 25
