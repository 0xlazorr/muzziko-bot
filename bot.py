import os
import sys
import html
import time
import socket
import logging
from collections import OrderedDict
from typing import Dict, Any

# Force IPv4 resolution to eliminate broken IPv6 route timeouts on Linux
orig_getaddrinfo = socket.getaddrinfo
def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = getaddrinfo_ipv4

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.request import HTTPXRequest
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    InlineQueryHandler,
    ContextTypes,
    filters,
)

from config import (
    BOT_TOKEN,
    BOT_USERNAME,
    MAX_SEARCH_RESULTS,
    PAGE_SIZE,
    MAX_FILE_SIZE_BYTES,
)
from downloader import MusicDownloader
from spotify_helper import SpotifyHelper
from lyrics import LyricsFinder

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Bounded session cache for search queries and track metadata
class SessionCache(OrderedDict):
    def __init__(self, maxsize=500, *args, **kwargs):
        self.maxsize = maxsize
        super().__init__(*args, **kwargs)

    def __setitem__(self, key, value):
        if len(self) >= self.maxsize:
            self.popitem(last=False)
        super().__setitem__(key, value)

SEARCH_CACHE = SessionCache(maxsize=500)
TRACK_METADATA_CACHE = SessionCache(maxsize=1000)


def create_search_keyboard(search_id: str, page: int, total_items: int) -> InlineKeyboardMarkup:
    """Builds inline keyboard for search result pagination and song selection"""
    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_items)
    total_pages = (total_items + PAGE_SIZE - 1) // PAGE_SIZE

    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    # Song selection buttons (e.g. [ 1️⃣ ] [ 2️⃣ ] [ 3️⃣ ] ...)
    select_row = []
    for idx in range(start_idx, end_idx):
        emoji = number_emojis[idx] if idx < len(number_emojis) else str(idx + 1)
        select_row.append(
            InlineKeyboardButton(emoji, callback_data=f"dl:{search_id}:{idx}")
        )

    keyboard = [select_row]

    # Navigation row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"pg:{search_id}:{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"pg:{search_id}:{page+1}"))

    if nav_row:
        keyboard.append(nav_row)

    # Action row (Lyrics & Close)
    action_row = [
        InlineKeyboardButton("📄 Lyrics", callback_data=f"lyr_list:{search_id}:{page}"),
        InlineKeyboardButton("❌ Close", callback_data="close"),
    ]
    keyboard.append(action_row)

    return InlineKeyboardMarkup(keyboard)


def format_search_text(query: str, tracks: list, page: int) -> str:
    """Formats the track listing text for the user with escaped HTML"""
    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, len(tracks))
    total_pages = (len(tracks) + PAGE_SIZE - 1) // PAGE_SIZE

    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    lines = [f"🔍 <b>Search Results for:</b> <i>{html.escape(query)}</i>\n"]
    for idx in range(start_idx, end_idx):
        t = tracks[idx]
        emoji = number_emojis[idx] if idx < len(number_emojis) else f"[{idx+1}]"
        clean_title = html.escape(t.get("title", "Unknown"))
        clean_artist = html.escape(t.get("artist", "Unknown"))
        lines.append(f"{emoji} <b>{clean_title}</b>")
        lines.append(f"   👤 {clean_artist} | ⏱ {t['duration_str']}\n")

    lines.append(f"📄 Page {page + 1}/{total_pages} • <i>Select a number below to download:</i>")
    return "\n".join(lines)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start command including deep-linking"""
    # Check for deep link argument (e.g. /start dl_<id>)
    if context.args and len(context.args) > 0:
        arg = context.args[0]
        if arg.startswith("dl_"):
            video_id = arg[3:]
            status_msg = await update.message.reply_text(
                "⏳ <i>Fetching requested song...</i>",
                parse_mode=ParseMode.HTML
            )
            track_info = await MusicDownloader.download_track_async(video_id)
            if track_info:
                await send_downloaded_track(update.effective_chat.id, context, track_info, status_msg=status_msg)
            else:
                await status_msg.edit_text("❌ Failed to download requested track.")
            return

    welcome_text = (
        "🎵 <b>Universal Music Downloader Bot</b>\n\n"
        "Welcome! I can find and download virtually <b>any song in the world</b> "
        "in studio-quality (320 kbps MP3) with embedded album art and full metadata!\n\n"
        "✨ <b>How to Use:</b>\n"
        "• Send any <b>Song Name</b> or <b>Artist</b> (e.g. <code>Coldplay Yellow</code>)\n"
        "• Send <b>Lyrics</b> you remember (e.g. <code>is this the real life is this just fantasy</code>)\n"
        "• Paste a <b>Spotify</b>, <b>YouTube</b>, or <b>SoundCloud</b> link directly!\n"
        "• Use <code>/song &lt;title&gt;</code> for instant 1-step download\n"
        "• Use <code>/lyrics &lt;title&gt;</code> to read song lyrics\n\n"
        "🎧 <i>Just type a song name or paste a link below to get started!</i>"
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /help command"""
    username = BOT_USERNAME or (context.bot.username if context.bot else "bot")
    help_text = (
        "📖 <b>Universal Music Bot Help</b>\n\n"
        "<b>Commands:</b>\n"
        "• <code>/start</code> - Welcome message and instructions\n"
        "• <code>/song &lt;name&gt;</code> - Instantly download top matching song\n"
        "• <code>/lyrics &lt;name or lyrics&gt;</code> - Find full lyrics for a song\n"
        "• <code>/search &lt;query&gt;</code> - Search and display interactive list\n\n"
        "<b>Features:</b>\n"
        "💎 <b>Studio Quality:</b> 320 kbps MP3 with ID3 tags & album art\n"
        "🔍 <b>Universal Coverage:</b> YouTube, YouTube Music, Spotify & SoundCloud\n"
        "📝 <b>Lyrics Search:</b> Find songs even if you only remember a line of lyrics\n"
        f"⚡ <b>Inline Mode:</b> Type <code>@{username} &lt;song&gt;</code> anywhere on Telegram!\n"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


async def send_downloaded_track(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    track_info: dict,
    status_msg = None
):
    """Sends the downloaded and tagged MP3 file to user"""
    audio_path = track_info["audio_path"]
    thumb_path = track_info.get("thumb_path")
    task_id = track_info["task_id"]

    try:
        # Check Telegram 50MB file size limit
        file_size = track_info["file_size"]
        if file_size > MAX_FILE_SIZE_BYTES:
            err_msg = (
                f"⚠️ The track <b>{html.escape(track_info['title'])}</b> is too large ({file_size // (1024*1024)} MB). "
                "Telegram bots have a 50 MB upload limit."
            )
            if status_msg:
                await status_msg.edit_text(err_msg, parse_mode=ParseMode.HTML)
            else:
                await context.bot.send_message(chat_id=chat_id, text=err_msg, parse_mode=ParseMode.HTML)
            return

        # Show uploading status
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_VOICE)

        title_clean = html.escape(track_info["title"])
        artist_clean = html.escape(track_info["artist"])

        caption = (
            f"🎵 <b>{title_clean}</b>\n"
            f"👤 <b>Artist:</b> {artist_clean}\n"
            f"⏱ <b>Duration:</b> {track_info['duration_str']} | 🎧 <b>Quality:</b> 320 kbps"
        )

        # Save metadata to cache for safe callback querying
        TRACK_METADATA_CACHE[task_id] = {
            "title": track_info["title"],
            "artist": track_info["artist"],
        }

        # Inline button to view lyrics
        lyrics_btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 View Lyrics", callback_data=f"lyr_tid:{task_id}")]
        ])

        with open(audio_path, "rb") as audio_file:
            thumb_file = open(thumb_path, "rb") if thumb_path and os.path.exists(thumb_path) else None
            try:
                await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=audio_file,
                    title=track_info["title"],
                    performer=track_info["artist"],
                    duration=track_info["duration"],
                    thumbnail=thumb_file,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=lyrics_btn,
                )
            finally:
                if thumb_file:
                    thumb_file.close()

        # Delete progress message if exists
        if status_msg:
            try:
                await status_msg.delete()
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Error sending track: {e}")
        err_msg = "❌ An error occurred while uploading the track. Please try again."
        if status_msg:
            await status_msg.edit_text(err_msg)
        else:
            await context.bot.send_message(chat_id=chat_id, text=err_msg)

    finally:
        # Always clean up downloaded files
        MusicDownloader.cleanup(task_id)


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Handles direct URL downloads (Spotify, YouTube, SoundCloud)"""
    chat_id = update.effective_chat.id

    # Check for Spotify collections (album/playlist)
    if SpotifyHelper.is_spotify_collection(url):
        await update.message.reply_text(
            "💡 <i>You pasted a Spotify album or playlist link.</i>\n\n"
            "To download songs, please send a specific <b>track link</b> or search by the <b>song/artist name</b>!",
            parse_mode=ParseMode.HTML
        )
        return

    status_msg = await update.message.reply_text(
        "🔎 <i>Analyzing link and preparing download...</i>",
        parse_mode=ParseMode.HTML
    )

    custom_meta = None
    target = url

    # Handle Spotify Track URL
    if SpotifyHelper.is_spotify_url(url):
        await status_msg.edit_text("🟢 <i>Fetching Spotify track metadata...</i>", parse_mode=ParseMode.HTML)
        spotify_info = SpotifyHelper.get_track_info(url)
        if spotify_info:
            custom_meta = spotify_info
            target = f"ytsearch1:{spotify_info['search_query']}"
            song_label = html.escape(f"{spotify_info['title']} - {spotify_info['artist']}")
            await status_msg.edit_text(
                f"⏳ Downloading: <b>{song_label}</b>...",
                parse_mode=ParseMode.HTML
            )
        else:
            await status_msg.edit_text("❌ Could not resolve Spotify link. Please try searching by song name.")
            return
    else:
        await status_msg.edit_text("⏳ <i>Downloading audio and converting to 320 kbps MP3...</i>", parse_mode=ParseMode.HTML)

    # Perform download
    track_info = await MusicDownloader.download_track_async(target, custom_metadata=custom_meta)
    if not track_info:
        await status_msg.edit_text("❌ Failed to download audio from this link. It might be region-restricted or private.")
        return

    await send_downloaded_track(chat_id, context, track_info, status_msg=status_msg)


async def song_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct instant download of the #1 match without extra clicks"""
    if not context.args:
        await update.message.reply_text("Usage: <code>/song &lt;song name or artist&gt;</code>", parse_mode=ParseMode.HTML)
        return

    query = " ".join(context.args).strip()
    clean_q = html.escape(query)
    status_msg = await update.message.reply_text(f"🔍 <i>Searching and downloading:</i> <b>{clean_q}</b>...", parse_mode=ParseMode.HTML)

    target = f"ytsearch1:{query}"
    track_info = await MusicDownloader.download_track_async(target)

    if not track_info:
        await status_msg.edit_text(f"❌ No music found for: <b>{clean_q}</b>", parse_mode=ParseMode.HTML)
        return

    await send_downloaded_track(update.effective_chat.id, context, track_info, status_msg=status_msg)


async def lyrics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Searches lyrics for a given song or lyrics snippet"""
    if not context.args:
        await update.message.reply_text("Usage: <code>/lyrics &lt;song name, artist, or lyrics&gt;</code>", parse_mode=ParseMode.HTML)
        return

    query = " ".join(context.args).strip()
    clean_q = html.escape(query)
    status_msg = await update.message.reply_text(f"🔎 <i>Searching lyrics for:</i> <b>{clean_q}</b>...", parse_mode=ParseMode.HTML)

    # Try exact or snippet lookup
    data = LyricsFinder.get_lyrics(query) or LyricsFinder.search_by_lyrics(query)

    if not data or not data.get("lyrics"):
        # Fallback: find song title via YouTube search first, then fetch lyrics
        search_res = await MusicDownloader.search_async(query, limit=1)
        if search_res:
            top = search_res[0]
            data = LyricsFinder.get_lyrics(top["title"], top["artist"])

    if not data or not data.get("lyrics"):
        await status_msg.edit_text(f"❌ Could not find lyrics for: <b>{clean_q}</b>", parse_mode=ParseMode.HTML)
        return

    track_name = data.get("track_name", query)
    artist_name = data.get("artist_name", "")
    lyrics_text = data["lyrics"]

    # Truncate if exceeds Telegram limit
    if len(lyrics_text) > 3500:
        lyrics_text = lyrics_text[:3500] + "\n\n... [Lyrics truncated]"

    track_name_esc = html.escape(track_name)
    artist_name_esc = html.escape(artist_name)
    lyrics_text_esc = html.escape(lyrics_text)

    msg_text = (
        f"📄 <b>Lyrics:</b> <b>{track_name_esc}</b>"
        + (f" by <i>{artist_name_esc}</i>\n\n" if artist_name else "\n\n")
        + f"{lyrics_text_esc}"
    )

    # Save to metadata cache for download button
    task_key = str(int(time.time() * 1000))[-8:]
    TRACK_METADATA_CACHE[task_key] = {"title": track_name, "artist": artist_name}

    download_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬇️ Download This Song", callback_data=f"dl_cached:{task_key}")]
    ])

    await status_msg.edit_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=download_btn)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes incoming user text: URLs, lyrics queries, or song searches"""
    text = update.message.text.strip()
    if not text:
        return

    # 1. Check if user sent a URL
    if text.startswith("http://") or text.startswith("https://"):
        await handle_url(update, context, text)
        return

    # Check for Spotify link inside text
    spotify_url = SpotifyHelper.extract_spotify_url(text)
    if spotify_url:
        await handle_url(update, context, spotify_url)
        return

    # 2. Check for lyrics prefix
    if text.lower().startswith("lyrics:") or text.lower().startswith("lyric:"):
        lyrics_query = text.split(":", 1)[1].strip()
        context.args = lyrics_query.split()
        await lyrics_command(update, context)
        return

    # 3. Interactive Multi-Search
    status_msg = await update.message.reply_text("🔍 <i>Searching music catalog...</i>", parse_mode=ParseMode.HTML)

    tracks = await MusicDownloader.search_async(text, limit=MAX_SEARCH_RESULTS)
    if not tracks:
        clean_text = html.escape(text)
        await status_msg.edit_text(
            f"❌ No tracks found for <b>{clean_text}</b>. Try checking the spelling or searching by artist name.",
            parse_mode=ParseMode.HTML
        )
        return

    # Store in session cache
    search_id = str(int(time.time() * 1000))[-8:]
    SEARCH_CACHE[search_id] = {
        "query": text,
        "tracks": tracks,
    }

    formatted_text = format_search_text(text, tracks, page=0)
    keyboard = create_search_keyboard(search_id, page=0, total_items=len(tracks))

    await status_msg.edit_text(formatted_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles interactive button clicks (song download, pagination, lyrics)"""
    query = update.callback_query
    await query.answer()

    data = query.data
    chat_id = update.effective_chat.id

    # 1. Close menu
    if data == "close":
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    # 2. Pagination: pg:<search_id>:<page>
    if data.startswith("pg:"):
        _, search_id, page_str = data.split(":", 2)
        page = int(page_str)
        session = SEARCH_CACHE.get(search_id)
        if not session:
            await query.edit_message_text("⚠️ This search session expired. Please search again!")
            return

        tracks = session["tracks"]
        new_text = format_search_text(session["query"], tracks, page=page)
        keyboard = create_search_keyboard(search_id, page=page, total_items=len(tracks))
        await query.edit_message_text(new_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        return

    # 3. Download selected track: dl:<search_id>:<index>
    if data.startswith("dl:"):
        _, search_id, idx_str = data.split(":", 2)
        idx = int(idx_str)
        session = SEARCH_CACHE.get(search_id)
        if not session or idx >= len(session["tracks"]):
            await query.edit_message_text("⚠️ This search session expired. Please search again!")
            return

        track = session["tracks"][idx]
        title_esc = html.escape(track['title'])
        artist_esc = html.escape(track['artist'])
        progress_text = (
            f"⏳ <b>Downloading:</b> {title_esc}\n"
            f"👤 <b>Artist:</b> {artist_esc}\n"
            "🎧 <i>Extracting 320 kbps studio audio & embedding album art...</i>"
        )
        status_msg = await query.message.reply_text(progress_text, parse_mode=ParseMode.HTML)

        track_info = await MusicDownloader.download_track_async(track["url"])
        if not track_info:
            await status_msg.edit_text("❌ Failed to download this track. Please select another result.")
            return

        await send_downloaded_track(chat_id, context, track_info, status_msg=status_msg)
        return

    # 4. Download from cached metadata: dl_cached:<task_key>
    if data.startswith("dl_cached:"):
        task_key = data.split(":", 1)[1]
        cached = TRACK_METADATA_CACHE.get(task_key)
        if not cached:
            await query.message.reply_text("⚠️ Download session expired. Please search again.")
            return

        query_str = f"{cached['title']} {cached['artist']}".strip()
        status_msg = await query.message.reply_text(f"⏳ Downloading <b>{html.escape(query_str)}</b>...", parse_mode=ParseMode.HTML)
        track_info = await MusicDownloader.download_track_async(f"ytsearch1:{query_str}")
        if not track_info:
            await status_msg.edit_text("❌ Failed to download track.")
            return
        await send_downloaded_track(chat_id, context, track_info, status_msg=status_msg)
        return

    # 5. Lyrics for track from audio message: lyr_tid:<task_id>
    if data.startswith("lyr_tid:"):
        task_id = data.split(":", 1)[1]
        cached = TRACK_METADATA_CACHE.get(task_id)
        if not cached:
            await query.message.reply_text("⚠️ Lyrics request expired. Use /lyrics <song> to read lyrics.")
            return

        title = cached["title"]
        artist = cached["artist"]
        status_msg = await query.message.reply_text(f"📄 Fetching lyrics for <b>{html.escape(title)}</b>...", parse_mode=ParseMode.HTML)
        lyr_data = LyricsFinder.get_lyrics(title, artist)

        if not lyr_data or not lyr_data.get("lyrics"):
            await status_msg.edit_text(f"❌ Lyrics not found for <b>{html.escape(title)}</b>.", parse_mode=ParseMode.HTML)
            return

        lyrics_body = lyr_data["lyrics"]
        if len(lyrics_body) > 3500:
            lyrics_body = lyrics_body[:3500] + "\n\n... [Lyrics truncated]"

        await status_msg.edit_text(
            f"📄 <b>Lyrics:</b> <b>{html.escape(title)}</b> - {html.escape(artist)}\n\n{html.escape(lyrics_body)}",
            parse_mode=ParseMode.HTML
        )
        return

    # 6. Lyrics selection from search list: lyr_list:<search_id>:<page>
    if data.startswith("lyr_list:"):
        _, search_id, page_str = data.split(":", 2)
        session = SEARCH_CACHE.get(search_id)
        if not session:
            await query.edit_message_text("⚠️ This search session expired. Please search again!")
            return

        # Fetch lyrics for the top track of current page
        page = int(page_str)
        start_idx = page * PAGE_SIZE
        if start_idx < len(session["tracks"]):
            t = session["tracks"][start_idx]
            status_msg = await query.message.reply_text(f"📄 Fetching lyrics for <b>{html.escape(t['title'])}</b>...", parse_mode=ParseMode.HTML)
            lyr_data = LyricsFinder.get_lyrics(t["title"], t["artist"])
            if lyr_data and lyr_data.get("lyrics"):
                lyrics_body = lyr_data["lyrics"]
                if len(lyrics_body) > 3500:
                    lyrics_body = lyrics_body[:3500] + "\n\n... [Lyrics truncated]"
                await status_msg.edit_text(
                    f"📄 <b>Lyrics:</b> <b>{html.escape(t['title'])}</b> - {html.escape(t['artist'])}\n\n{html.escape(lyrics_body)}",
                    parse_mode=ParseMode.HTML
                )
            else:
                await status_msg.edit_text(f"❌ Lyrics not found for <b>{html.escape(t['title'])}</b>.", parse_mode=ParseMode.HTML)


async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows searching directly from any Telegram chat using @BotUsername <query>"""
    inline_query = update.inline_query
    query_text = inline_query.query.strip()

    if not query_text:
        return

    results = []
    try:
        tracks = await MusicDownloader.search_async(query_text, limit=5)
        for idx, t in enumerate(tracks):
            bot_user = BOT_USERNAME or (context.bot.username if context.bot else "")
            results.append(
                InlineQueryResultArticle(
                    id=f"{t['id']}_{idx}",
                    title=t["title"],
                    description=f"{t['artist']} • {t['duration_str']}",
                    thumbnail_url=t["thumbnail"] or None,
                    input_message_content=InputTextMessageContent(
                        message_text=(
                            f"🎵 <b>{html.escape(t['title'])}</b>\n"
                            f"👤 <i>{html.escape(t['artist'])}</i>\n"
                            f"⏱ Duration: {t['duration_str']}\n\n"
                            f"🔗 {t['url']}"
                        ),
                        parse_mode=ParseMode.HTML,
                    ),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("⬇️ Download Audio", url=f"https://t.me/{bot_user}?start=dl_{t['id']}" if bot_user else t["url"])]
                    ]),
                )
            )
    except Exception as e:
        logger.error(f"Error in inline query: {e}")

    await inline_query.answer(results, cache_time=300)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Logs unexpected exceptions without stopping the bot"""
    logger.error("Exception while handling an update:", exc_info=context.error)


def main():
    """Main application runner"""
    if not BOT_TOKEN:
        print("\n" + "=" * 60)
        print("❌ ERROR: TELEGRAM_BOT_TOKEN is not configured!")
        print("Please edit /home/lazorr/music_downloader_bot/.env and set:")
        print("BOT_TOKEN=your_bot_token_from_botfather")
        print("=" * 60 + "\n")
        sys.exit(1)

async def post_init(application: Application):
    """Callback executed once the bot successfully connects to Telegram"""
    me = application.bot
    print(f"✅ Universal Music Downloader Bot is live! Logged in as: {me.first_name} (@{me.username})")


def main():
    """Main application runner"""
    if not BOT_TOKEN:
        print("\n" + "=" * 60)
        print("❌ ERROR: TELEGRAM_BOT_TOKEN is not configured!")
        print("Please edit /home/lazorr/music_downloader_bot/.env and set:")
        print("BOT_TOKEN=your_bot_token_from_botfather")
        print("=" * 60 + "\n")
        sys.exit(1)

    print("🚀 Initializing Universal Music Downloader Bot...")
    request = HTTPXRequest(
        connection_pool_size=16,
        connect_timeout=30.0,
        read_timeout=60.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .post_init(post_init)
        .build()
    )

    # Command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("song", song_command))
    app.add_handler(CommandHandler("music", song_command))
    app.add_handler(CommandHandler("dl", song_command))
    app.add_handler(CommandHandler("lyrics", lyrics_command))
    app.add_handler(CommandHandler("search", handle_text_message))

    # Text message handler (URLs and text searches)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # Callback query handler (buttons)
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # Inline query handler
    app.add_handler(InlineQueryHandler(handle_inline_query))

    # Global error handler
    app.add_error_handler(error_handler)

    print("📡 Connecting to Telegram network...")
    app.run_polling(
        drop_pending_updates=True,
        bootstrap_retries=-1,
        timeout=20,
        poll_interval=1.0,
    )


if __name__ == "__main__":
    main()
