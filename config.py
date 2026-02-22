import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
KLINGAI_ACCESS_KEY = os.environ["KLINGAI_ACCESS_KEY"]
KLINGAI_SECRET_KEY = os.environ["KLINGAI_SECRET_KEY"]
PEXELS_API_KEY = os.environ["PEXELS_API_KEY"]
RUNWAY_API_KEY = os.environ["RUNWAY_API_KEY"]
XAI_API_KEY = os.environ.get("XAI_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
