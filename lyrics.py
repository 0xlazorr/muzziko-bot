import requests
from typing import Optional, Dict

class LyricsFinder:
    LRCLIB_BASE_URL = "https://lrclib.net/api"
    HEADERS = {
        "User-Agent": "UniversalMusicBot/1.0 (https://t.me/)"
    }

    @classmethod
    def get_lyrics(cls, track_name: str, artist_name: str = "") -> Optional[Dict[str, str]]:
        """
        Fetches plain lyrics, track name, and artist name from LRCLIB.
        """
        try:
            # 1. Try exact get if artist is provided
            if artist_name:
                params = {
                    "track_name": track_name,
                    "artist_name": artist_name,
                }
                res = requests.get(f"{cls.LRCLIB_BASE_URL}/get", params=params, headers=cls.HEADERS, timeout=8)
                if res.status_code == 200:
                    data = res.json()
                    lyrics = data.get("plainLyrics")
                    if lyrics:
                        return {
                            "track_name": data.get("trackName", track_name),
                            "artist_name": data.get("artistName", artist_name),
                            "album_name": data.get("albumName", ""),
                            "lyrics": lyrics.strip(),
                        }

            # 2. Try search endpoint
            query = f"{artist_name} {track_name}".strip() if artist_name else track_name
            params = {"q": query}
            res = requests.get(f"{cls.LRCLIB_BASE_URL}/search", params=params, headers=cls.HEADERS, timeout=8)
            if res.status_code == 200:
                results = res.json()
                if isinstance(results, list) and results:
                    # Pick first result that has plainLyrics
                    for item in results:
                        lyrics = item.get("plainLyrics")
                        if lyrics:
                            return {
                                "track_name": item.get("trackName", track_name),
                                "artist_name": item.get("artistName", artist_name),
                                "album_name": item.get("albumName", ""),
                                "lyrics": lyrics.strip(),
                            }

        except Exception as e:
            print(f"Error fetching lyrics: {e}")

        return None

    @classmethod
    def search_by_lyrics(cls, lyrics_snippet: str) -> Optional[Dict[str, str]]:
        """
        Attempts to identify a song from a snippet of lyrics.
        """
        try:
            params = {"q": lyrics_snippet}
            res = requests.get(f"{cls.LRCLIB_BASE_URL}/search", params=params, headers=cls.HEADERS, timeout=8)
            if res.status_code == 200:
                results = res.json()
                if isinstance(results, list) and results:
                    for item in results:
                        lyrics = item.get("plainLyrics", "")
                        if lyrics:
                            return {
                                "track_name": item.get("trackName", ""),
                                "artist_name": item.get("artistName", ""),
                                "album_name": item.get("albumName", ""),
                                "lyrics": lyrics.strip(),
                            }
        except Exception as e:
            print(f"Error searching by lyrics: {e}")

        return None
