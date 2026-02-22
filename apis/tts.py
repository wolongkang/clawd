import io
import logging
from gtts import gTTS

logger = logging.getLogger(__name__)


async def generate_speech(text: str) -> bytes:
    try:
        tts = gTTS(text=text, lang="en", slow=False)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        data = fp.getvalue()
        logger.info(f"TTS: {len(data)} bytes")
        return data
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return None
