import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "").strip()
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "").strip()

# Deployment settings
PORT = int(os.getenv("PORT", "8080"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip().rstrip("/")
SECRET_TOKEN = os.getenv("TELEGRAM_SECRET_TOKEN", "pixel_fraction_secret_2026")

# Thresholds
PASS_THRESHOLD = float(os.getenv("PASS_THRESHOLD", "15.0"))  # Min 15% pixels of color
BONUS_THRESHOLD = float(os.getenv("BONUS_THRESHOLD", "40.0")) # 40%+ pixels of color
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.85")) # Anti-cheat threshold
