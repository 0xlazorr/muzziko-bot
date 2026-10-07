# 🎵 Universal Music Downloader Telegram Bot

A fast, lightweight, and modern Telegram Music Bot built in Python. Designed to search and download virtually **every song ever recorded** in studio-quality **320 kbps MP3** with embedded high-resolution album art and ID3 metadata tags.

---

## ✨ Features

- 🌍 **Universal Music Catalog**: Powered by YouTube & YouTube Music search indexing — covers official releases, indie tracks, remixes, covers, live performances, and unreleased versions.
- ⚡ **Direct Link Support**:
  - **Spotify** (resolves tracks, fetches 640x640 album artwork, downloads high-fidelity audio)
  - **YouTube / YouTube Music** (`youtu.be`, `youtube.com`, `music.youtube.com`)
  - **SoundCloud**
- 🎧 **Studio-Grade Quality**: Audio extracted at **320 kbps MP3** via FFmpeg with ID3 tags (Title, Artist, Album, Cover Art) rendered natively in Telegram's player.
- 🔍 **Multiple Search Modes**:
  - **Song Title / Artist**: Type `Shape of You` or `The Weeknd`
  - **Lyrics Search**: Type lyrics snippets (e.g., `is this the real life is this just fantasy` or `lyrics: somebody that I used to know`)
  - **Instant Download**: `/song <name>` downloads the #1 match immediately in one step.
  - **Interactive Search Card**: Numbered buttons `[ 1️⃣ ] [ 2️⃣ ] [ 3️⃣ ] [ 4️⃣ ] [ 5️⃣ ]` and pagination `[ ⬅️ Prev ] [ Next ➡️ ]`.
  - **Inline Search**: Type `@YourBotName <song>` in *any* Telegram chat or group.
- 📄 **Lyrics Viewer**: Read full synchronized or plain lyrics directly inside Telegram.
- 🧹 **Auto-Cleanup**: Automatically wipes downloaded files from disk right after delivery to keep storage minimal.

---

## 🚀 Quick Setup (2 Minutes)

### 1. Create a Bot Token
1. Open Telegram and message [@BotFather](https://t.me/BotFather).
2. Send `/newbot`, choose a name and username (e.g. `MyMusicBot`).
3. Copy the HTTP API token provided by BotFather.
4. *(Optional for Inline Mode)*: Send `/setinline` to `@BotFather`, select your bot, and enter placeholder text (e.g. `Search music...`).

### 2. Configure the Bot
Open the `.env` file in `/home/lazorr/music_downloader_bot/.env` and paste your token:

```env
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
BOT_USERNAME=YourBotUsernameWithoutAt
AUDIO_QUALITY=320
MAX_SEARCH_RESULTS=10
```

### 3. Run the Bot

```bash
cd /home/lazorr/music_downloader_bot
./start.sh
```

---

## 📱 Bot Commands & Usage

| Command / Input | Description |
|---|---|
| `Any song title` | Searches the catalog and presents an interactive numbered selection card. |
| `Any artist name` | Returns the artist's most popular tracks to choose from. |
| `Lyrics snippet` | Finds the song matching those exact lyrics. |
| `/song <title>` | Downloads and delivers the top match in a single step without clicking buttons. |
| `/lyrics <query>` | Displays full song lyrics with an instant `[ ⬇️ Download This Song ]` button. |
| `Paste any URL` | Pasting a Spotify, YouTube, or SoundCloud link triggers an immediate download. |
| `@BotName <query>` | Inline mode: search and share music in any Telegram chat or group! |

---

## 🛠 Running 24/7 as a Background Service (systemd)

To ensure the bot restarts automatically on server reboots:

```bash
# 1. Copy service file
sudo cp /home/lazorr/music_downloader_bot/musicbot.service /etc/systemd/system/

# 2. Reload systemd daemon
sudo systemctl daemon-reload

# 3. Enable and start service
sudo systemctl enable --now musicbot

# 4. Check status
sudo systemctl status musicbot
```

To view live logs:
```bash
journalctl -u musicbot -f
```

---

## 📂 Project Architecture

```
/home/lazorr/music_downloader_bot/
├── bot.py                # Main Telegram Bot logic, interactive UI, and handlers
├── downloader.py         # yt-dlp audio extraction, 320kbps MP3 conversion & ID3 tagging
├── spotify_helper.py     # Spotify metadata and artwork resolver (no API keys needed)
├── lyrics.py             # LRCLIB lyrics lookup and search engine
├── config.py             # Environment configurations and limits
├── start.sh              # Quick executable launch script
├── requirements.txt      # Dependency specifications
├── musicbot.service      # Linux systemd 24/7 service unit template
├── .env                  # Configuration with Telegram Bot Token
└── downloads/            # Temporary scratch directory (auto-cleaned)
```
