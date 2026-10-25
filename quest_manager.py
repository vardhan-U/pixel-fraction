import json
import random
import logging
from datetime import datetime, timezone
from pathlib import Path
import requests

from config import DATA_DIR, UNSPLASH_ACCESS_KEY
from color_engine import COLOR_DEFINITIONS, compute_dhash

logger = logging.getLogger(__name__)

QUEST_FILE = DATA_DIR / "current_quest.json"

# Curated Fallbacks if Unsplash network/rate-limit occurs
FALLBACK_QUESTS = {
    "red": {
        "color_key": "red",
        "color_name": "Ruby Red",
        "emoji": "🔴",
        "photo_url": "https://images.unsplash.com/photo-1518895949257-7621c3c786d7?w=800",
        "photographer": "Arun Sharma",
        "photographer_url": "https://unsplash.com/@arunsharma",
        "description": "Find something strikingly red around you!",
    },
    "green": {
        "color_key": "green",
        "color_name": "Emerald Green",
        "emoji": "🟢",
        "photo_url": "https://images.unsplash.com/photo-1518531933037-91b2f5f229cc?w=800",
        "photographer": "Luca Bravo",
        "photographer_url": "https://unsplash.com/@lucabravo",
        "description": "Capture fresh greenery or vibrant green objects!",
    },
    "blue": {
        "color_key": "blue",
        "color_name": "Ocean Blue",
        "emoji": "🔵",
        "photo_url": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=800",
        "photographer": "Sean Oulashin",
        "photographer_url": "https://unsplash.com/@oulashin",
        "description": "Find calm waters, open sky, or blue gadgets!",
    },
    "yellow": {
        "color_key": "yellow",
        "color_name": "Golden Yellow",
        "emoji": "🟡",
        "photo_url": "https://images.unsplash.com/photo-1470240731273-7821a6eeb6bd?w=800",
        "photographer": "Brigitte Tohm",
        "photographer_url": "https://unsplash.com/@brigittetohm",
        "description": "Spot bright sunny yellow in your room or outdoors!",
    },
    "orange": {
        "color_key": "orange",
        "color_name": "Amber Orange",
        "emoji": "🟠",
        "photo_url": "https://images.unsplash.com/photo-1508746829417-e6f548d8d6ed?w=800",
        "photographer": "Eberhard Grossgasteiger",
        "photographer_url": "https://unsplash.com/@eberhardgross",
        "description": "Seek warm amber and orange tones!",
    },
}


class QuestManager:
    def __init__(self):
        self.current_quest = self._load_cached_quest()

    def _get_today_str(self) -> str:
        # Returns current UTC date string YYYY-MM-DD
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load_cached_quest(self) -> dict | None:
        if QUEST_FILE.exists():
            try:
                with open(QUEST_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("date") == self._get_today_str():
                        return data
            except Exception as e:
                logger.warning(f"Failed to read cached quest: {e}")
        return None

    def _save_quest(self, quest: dict):
        try:
            with open(QUEST_FILE, "w", encoding="utf-8") as f:
                json.dump(quest, f, indent=2)
            self.current_quest = quest
        except Exception as e:
            logger.error(f"Failed to save quest to file: {e}")

    def fetch_new_quest(self, preferred_color: str | None = None) -> dict:
        """
        Fetches an inspiring photo from Unsplash for today's color quest.
        Falls back smoothly if API fails or quota runs out.
        """
        color_keys = list(COLOR_DEFINITIONS.keys())
        today_date = self._get_today_str()

        if preferred_color and preferred_color.lower() in COLOR_DEFINITIONS:
            chosen_color_key = preferred_color.lower()
        else:
            # Deterministic color rotation based on day of year, or random
            day_of_year = datetime.now(timezone.utc).timetuple().tm_yday
            chosen_color_key = color_keys[day_of_year % len(color_keys)]

        color_info = COLOR_DEFINITIONS[chosen_color_key]
        search_query = color_info["search_term"]

        photo_data = None
        photo_bytes = None

        if UNSPLASH_ACCESS_KEY:
            try:
                url = "https://api.unsplash.com/photos/random"
                headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
                params = {"query": search_query, "orientation": "landscape"}
                resp = requests.get(url, headers=headers, params=params, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    image_url = data.get("urls", {}).get("regular") or data.get("urls", {}).get("small")
                    user_data = data.get("user", {})
                    photographer = user_data.get("name", "Unknown Photographer")
                    photographer_url = user_data.get("links", {}).get("html", "https://unsplash.com")

                    # Download small version for dHash anti-cheat
                    img_resp = requests.get(image_url, timeout=10)
                    if img_resp.status_code == 200:
                        photo_bytes = img_resp.content

                    photo_data = {
                        "date": today_date,
                        "color_key": chosen_color_key,
                        "color_name": color_info["name"],
                        "emoji": color_info["emoji"],
                        "photo_url": image_url,
                        "photographer": photographer,
                        "photographer_url": photographer_url,
                        "description": f"Today's Quest: Capture {color_info['name']} {color_info['emoji']} in your surroundings!",
                        "dhash": compute_dhash(photo_bytes) if photo_bytes else None,
                        "source": "unsplash",
                    }
                else:
                    logger.warning(f"Unsplash API returned {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.error(f"Error querying Unsplash API: {e}")

        # Fallback if Unsplash was not reachable
        if not photo_data:
            fallback = FALLBACK_QUESTS.get(chosen_color_key, FALLBACK_QUESTS["green"])
            # Attempt to hash fallback image if reachable
            dhash_val = None
            try:
                img_resp = requests.get(fallback["photo_url"], timeout=8)
                if img_resp.status_code == 200:
                    dhash_val = compute_dhash(img_resp.content)
            except Exception:
                dhash_val = None

            photo_data = {
                "date": today_date,
                "color_key": chosen_color_key,
                "color_name": color_info["name"],
                "emoji": color_info["emoji"],
                "photo_url": fallback["photo_url"],
                "photographer": fallback["photographer"],
                "photographer_url": fallback["photographer_url"],
                "description": fallback["description"],
                "dhash": dhash_val,
                "source": "fallback",
            }

        self._save_quest(photo_data)
        return photo_data

    def get_todays_quest(self, force: bool = False) -> dict:
        """
        Returns cached quest for today, or generates a new one.
        """
        if force or not self.current_quest or self.current_quest.get("date") != self._get_today_str():
            return self.fetch_new_quest()
        return self.current_quest
