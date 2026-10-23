import os
from dotenv import load_dotenv

# Load variables from .env file if available
load_dotenv()

# Telegram Bot Credentials
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Default Scraping Source
DEFAULT_BASE_URL = "https://www.investorgain.com/report/ipo-subscription-live/333/"
DEFAULT_TAB = "open"  # 'open', 'all', 'closing-today', 'sme', 'ipo'

# Default Columns to display/send
# Available: name, category, status, gmp, total, total_time, qib, shni, bhni, nii, rii, anchor, size, price, pe, closing_date, rii_lot_size, shni_lot_size, link
DEFAULT_COLUMNS = ["name", "category", "total", "rii", "qib", "nii", "gmp", "closing_date"]


# Automated Hosting / Broadcast Settings
# Morning delivery time: 06:00 AM
MORNING_HOUR = int(os.getenv("MORNING_HOUR", "6"))
MORNING_MINUTE = int(os.getenv("MORNING_MINUTE", "0"))

# Evening delivery time: 06:00 PM (18:00)
EVENING_HOUR = int(os.getenv("EVENING_HOUR", "18"))
EVENING_MINUTE = int(os.getenv("EVENING_MINUTE", "0"))

