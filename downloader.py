import os
import re
import uuid
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import requests
from PIL import Image
import yt_dlp
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB

from config import DOWNLOAD_DIR, AUDIO_QUALITY, MAX_FILE_SIZE_BYTES

# Regex patterns for cleaning YouTube video titles
NOISE_PATTERNS = [
    r"\s*[\(\[]\s*official\s+video\s*[\)\]]",
    r"\s*[\(\[]\s*official\s+music\s+video\s*[\)\]]",
    r"\s*[\(\[]\s*official\s+audio\s*[\)\]]",
    r"\s*[\(\[]\s*official\s*[\)\]]",
    r"\s*[\(\[]\s*lyrics?\s*[\)\]]",
    r"\s*[\(\[]\s*lyric\s+video\s*[\)\]]",
    r"\s*[\(\[]\s*visualizer\s*[\)\]]",
    r"\s*[\(\[]\s*audio\s*[\)\]]",
    r"\s*[\(\[]\s*4k\s*[\)\]]",
    r"\s*[\(\[]\s*hd\s*[\)\]]",
    r"\s*[\(\[]\s*hq\s*[\)\]]",
    r"\s*[\(\[]\s*remastered\s*[\)\]]",
]


def clean_title_and_artist(raw_title: str, uploader: str = "") -> Tuple[str, str]:
    """
    Cleans junk from video titles and splits into (clean_title, artist).
    """
    cleaned = raw_title
    for pat in NOISE_PATTERNS:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" -|[]()")

    # Check for "Artist - Title" format
    if " - " in cleaned:
        parts = cleaned.split(" - ", 1)
        artist = parts[0].strip()
        title = parts[1].strip()
        return title, artist
    elif " – " in cleaned:  # en-dash
        parts = cleaned.split(" – ", 1)
        artist = parts[0].strip()
        title = parts[1].strip()
        return title, artist
    elif " — " in cleaned:  # em-dash
        parts = cleaned.split(" — ", 1)
        artist = parts[0].strip()
        title = parts[1].strip()
        return title, artist

    # Fallback: title is the cleaned text, artist is uploader
    return cleaned, uploader.replace(" - Topic", "").strip()


def format_duration(seconds: Optional[int]) -> str:
    """Formats duration in seconds to mm:ss or hh:mm:ss"""
    if not seconds:
        return "00:00"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def process_thumbnail(thumb_url_or_path: str, output_path: str) -> bool:
    """
    Downloads or converts any image (WEBP, PNG, JPG) to a standardized RGB JPEG.
    """
    try:
        if thumb_url_or_path.startswith("http://") or thumb_url_or_path.startswith("https://"):
            resp = requests.get(thumb_url_or_path, timeout=10)
            if resp.status_code == 200:
                with open(output_path + ".tmp", "wb") as f:
                    f.write(resp.content)
                img = Image.open(output_path + ".tmp")
            else:
                return False
        else:
            if not os.path.exists(thumb_url_or_path):
                return False
            img = Image.open(thumb_url_or_path)

        # Convert to RGB and resize to standard square cover art if desired
        rgb_img = img.convert("RGB")
        # Resize to max 600x600 keeping aspect ratio
        rgb_img.thumbnail((600, 600), Image.Resampling.LANCZOS)
        rgb_img.save(output_path, "JPEG", quality=90)

        if os.path.exists(output_path + ".tmp"):
            os.remove(output_path + ".tmp")
        return True
    except Exception as e:
        print(f"Error processing thumbnail: {e}")
        return False


class MusicDownloader:
    @staticmethod
    def search(query: str, limit: int = 10) -> List[Dict]:
        """
        Searches YouTube / YouTube Music for tracks matching query.
        Returns a list of track metadata dicts.
        """
        ydl_opts = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }

        # If query doesn't look like a URL, use ytsearch
        search_target = query
        if not (query.startswith("http://") or query.startswith("https://")):
            search_target = f"ytsearch{limit}:{query}"

        results = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_target, download=False)
                if not info:
                    return []

                entries = info.get("entries", []) if "entries" in info else [info]

                for entry in entries:
                    if not entry:
                        continue
                    
                    video_id = entry.get("id")
                    raw_title = entry.get("title", "Unknown Title")
                    uploader = entry.get("uploader", "") or entry.get("channel", "")
                    duration = entry.get("duration", 0)

                    # Skip ultra-long streams/videos (e.g. over 2 hours) to avoid overloading
                    if duration and duration > 7200:
                        continue

                    title, artist = clean_title_and_artist(raw_title, uploader)

                    # Extract best thumbnail
                    thumb = entry.get("thumbnail")
                    if not thumb and entry.get("thumbnails"):
                        thumb = entry["thumbnails"][-1].get("url")

                    results.append({
                        "id": video_id,
                        "title": title,
                        "artist": artist,
                        "raw_title": raw_title,
                        "duration": duration,
                        "duration_str": format_duration(duration),
                        "thumbnail": thumb or "",
                        "url": entry.get("url") or f"https://www.youtube.com/watch?v={video_id}",
                    })

                    if len(results) >= limit:
                        break

        except Exception as e:
            print(f"Error searching with yt-dlp: {e}")

        return results

    @staticmethod
    async def search_async(query: str, limit: int = 10) -> List[Dict]:
        """Runs search in a thread pool to prevent blocking asyncio loop"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, MusicDownloader.search, query, limit)

    @staticmethod
    def download_track(
        url_or_id: str,
        custom_metadata: Optional[Dict] = None,
        progress_hook = None
    ) -> Optional[Dict]:
        """
        Downloads the track, extracts high-quality MP3 (320kbps),
        embeds ID3 metadata and album art.
        """
        task_id = str(uuid.uuid4())[:8]
        output_template = str(DOWNLOAD_DIR / f"{task_id}_%(id)s.%(ext)s")
        target_mp3_pattern = str(DOWNLOAD_DIR / f"{task_id}_*.mp3")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "writethumbnail": True,
            "quiet": True,
            "no_warnings": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": AUDIO_QUALITY,
                }
            ],
        }

        if progress_hook:
            ydl_opts["progress_hooks"] = [progress_hook]

        try:
            target_url = url_or_id
            if not (target_url.startswith("http://") or target_url.startswith("https://")):
                target_url = f"https://www.youtube.com/watch?v={url_or_id}"

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target_url, download=True)
                if not info:
                    return None

                video_id = info.get("id")
                raw_title = info.get("title", "Unknown")
                uploader = info.get("uploader", "") or info.get("channel", "")
                duration = info.get("duration", 0)

                # Locate extracted MP3 file
                mp3_path = DOWNLOAD_DIR / f"{task_id}_{video_id}.mp3"
                if not mp3_path.exists():
                    # Check wildcard match in download dir
                    matches = list(DOWNLOAD_DIR.glob(f"{task_id}_*.mp3"))
                    if matches:
                        mp3_path = matches[0]
                    else:
                        print("MP3 file not found after extraction")
                        return None

                # Clean Title & Artist or use custom metadata (e.g. from Spotify)
                if custom_metadata:
                    title = custom_metadata.get("title") or raw_title
                    artist = custom_metadata.get("artist") or uploader
                    album = custom_metadata.get("album") or ""
                    thumb_source = custom_metadata.get("image_url") or info.get("thumbnail")
                else:
                    title, artist = clean_title_and_artist(raw_title, uploader)
                    album = info.get("album", "") or ""
                    thumb_source = info.get("thumbnail")

                # Prepare thumbnail
                thumb_path = DOWNLOAD_DIR / f"{task_id}_{video_id}_thumb.jpg"
                has_thumb = False
                if thumb_source:
                    has_thumb = process_thumbnail(thumb_source, str(thumb_path))

                # If remote thumbnail failed, check if yt-dlp saved one locally
                if not has_thumb:
                    for local_thumb in DOWNLOAD_DIR.glob(f"{task_id}_*"):
                        if local_thumb.suffix.lower() in [".webp", ".png", ".jpg", ".jpeg"] and local_thumb != thumb_path:
                            if process_thumbnail(str(local_thumb), str(thumb_path)):
                                has_thumb = True
                                break

                # Inject ID3 tags into MP3
                try:
                    audio = MP3(str(mp3_path), ID3=ID3)
                    try:
                        audio.add_tags()
                    except Exception:
                        pass

                    audio.tags.add(TIT2(encoding=3, text=title))
                    audio.tags.add(TPE1(encoding=3, text=artist))
                    if album:
                        audio.tags.add(TALB(encoding=3, text=album))

                    if has_thumb and thumb_path.exists():
                        with open(thumb_path, "rb") as tf:
                            audio.tags.add(
                                APIC(
                                    encoding=3,
                                    mime="image/jpeg",
                                    type=3,  # Cover front
                                    desc="Cover",
                                    data=tf.read()
                                )
                            )
                    audio.save()
                except Exception as tag_err:
                    print(f"Error tagging MP3: {tag_err}")

                file_size = mp3_path.stat().st_size

                return {
                    "audio_path": str(mp3_path),
                    "thumb_path": str(thumb_path) if has_thumb and thumb_path.exists() else None,
                    "title": title,
                    "artist": artist,
                    "album": album,
                    "duration": duration,
                    "duration_str": format_duration(duration),
                    "file_size": file_size,
                    "task_id": task_id,
                }

        except Exception as e:
            print(f"Error downloading track: {e}")
            return None

    @staticmethod
    async def download_track_async(
        url_or_id: str,
        custom_metadata: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Runs track download asynchronously in executor thread"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, MusicDownloader.download_track, url_or_id, custom_metadata
        )

    @staticmethod
    def cleanup(task_id: str):
        """Removes all temporary files generated for a download task"""
        try:
            for file_path in DOWNLOAD_DIR.glob(f"{task_id}_*"):
                try:
                    if file_path.is_file():
                        file_path.unlink()
                except Exception:
                    pass
        except Exception as e:
            print(f"Error cleaning up task {task_id}: {e}")
