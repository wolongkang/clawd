import os
from dotenv import load_dotenv

load_dotenv()

# Required
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# Active APIs
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
FAL_KEY = os.environ.get("FAL_KEY", "")
XAI_API_KEY = os.environ.get("XAI_API_KEY", "")

# Unused (kept for .env compatibility)
KLINGAI_ACCESS_KEY = os.environ.get("KLINGAI_ACCESS_KEY", "")
KLINGAI_SECRET_KEY = os.environ.get("KLINGAI_SECRET_KEY", "")
RUNWAY_API_KEY = os.environ.get("RUNWAY_API_KEY", "")
