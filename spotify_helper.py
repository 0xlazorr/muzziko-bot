import re
import urllib.parse
import requests
from typing import Optional, Dict

class SpotifyHelper:
    SPOTIFY_TRACK_REGEX = re.compile(
        r"(https?://(?:open\.spotify\.com(?:/intl-[a-zA-Z]+)?/track/|spotify\.link/)[a-zA-Z0-9]+)"
    )
    SPOTIFY_COLLECTION_REGEX = re.compile(
        r"https?://open\.spotify\.com(?:/intl-[a-zA-Z]+)?/(album|playlist|artist)/([a-zA-Z0-9]+)"
    )

    @classmethod
    def is_spotify_url(cls, url: str) -> bool:
        return bool(cls.SPOTIFY_TRACK_REGEX.search(url) or cls.SPOTIFY_COLLECTION_REGEX.search(url))

    @classmethod
    def is_spotify_collection(cls, url: str) -> bool:
        return bool(cls.SPOTIFY_COLLECTION_REGEX.search(url))

    @classmethod
    def extract_spotify_url(cls, text: str) -> Optional[str]:
        match = cls.SPOTIFY_TRACK_REGEX.search(text)
        if match:
            return match.group(1)
        col_match = cls.SPOTIFY_COLLECTION_REGEX.search(text)
        return col_match.group(0) if col_match else None

    @classmethod
    def get_track_info(cls, url: str) -> Optional[Dict[str, str]]:
        """
        Extracts song title, artist, album, and thumbnail from a Spotify URL
        without requiring any Spotify Developer API keys.
        """
        try:
            # 1. Follow any redirects using TelegramBot user agent so Spotify renders full OG tags
            headers = {
                "User-Agent": "TelegramBot (like TwitterBot)"
            }
            res = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
            if res.status_code != 200:
                return None
            
            final_url = res.url
            html = res.text

            # Extract title and description regardless of attribute order
            title_match = (
                re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE) or
                re.search(r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:title["\']', html, re.IGNORECASE) or
                re.search(r'<title>(.*?) \| Spotify</title>', html, re.IGNORECASE)
            )
            desc_match = (
                re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE) or
                re.search(r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:description["\']', html, re.IGNORECASE)
            )
            image_match = (
                re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE) or
                re.search(r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:image["\']', html, re.IGNORECASE)
            )

            title = title_match.group(1).strip() if title_match else ""
            desc = desc_match.group(1).strip() if desc_match else ""
            image_url = image_match.group(1).strip() if image_match else ""

            artist = ""
            album = ""

            if desc:
                # Description formats:
                # "Rick Astley · Whenever You Need Somebody · Song · 1987"
                # "Listen to Song on Spotify. Song · Rick Astley · 1987"
                parts = [p.strip() for p in re.split(r"[·•|]", desc)]
                clean_parts = [p for p in parts if p and "song" not in p.lower() and not p.isdigit() and "listen to" not in p.lower()]
                if clean_parts:
                    artist = clean_parts[0]
                if len(clean_parts) > 1:
                    album = clean_parts[1]

            # If still missing, check JSON-LD
            if not artist or not title:
                ld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
                if ld_match:
                    try:
                        import json
                        data = json.loads(ld_match.group(1))
                        if not title:
                            title = data.get("name", "")
                        desc_text = data.get("description", "")
                        if not artist and desc_text:
                            for part in desc_text.split("·"):
                                part = part.strip()
                                if part and "song" not in part.lower() and not part.isdigit():
                                    artist = part
                                    break
                    except Exception:
                        pass

            # Fallback to oEmbed endpoint if needed
            if not title:
                oembed_url = f"https://open.spotify.com/oembed?url={urllib.parse.quote(final_url)}"
                oembed_res = requests.get(oembed_url, headers=headers, timeout=10)
                if oembed_res.status_code == 200:
                    data = oembed_res.json()
                    title = data.get("title", "")
                    if not image_url:
                        image_url = data.get("thumbnail_url", "")

            if not title:
                return None

            search_query = f"{artist} - {title}" if artist else title
            return {
                "title": title,
                "artist": artist,
                "album": album,
                "image_url": image_url,
                "search_query": search_query,
            }

        except Exception as e:
            print(f"Error resolving Spotify track: {e}")
            return None
