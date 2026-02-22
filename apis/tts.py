import io
import os
import logging
from gtts import gTTS

logger = logging.getLogger(__name__)


async def generate_speech(text: str, target_minutes: int = 0) -> bytes:
    """Generate TTS audio. Returns bytes and logs duration vs target."""
    try:
        tts = gTTS(text=text, lang="en", slow=False)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        data = fp.getvalue()
        logger.info(f"TTS: {len(data)} bytes generated")

        # Estimate duration from word count (~150 wpm at normal gTTS speed)
        word_count = len(text.split())
        est_minutes = word_count / 150
        logger.info(f"TTS estimate: {word_count} words, ~{est_minutes:.1f} min")

        if target_minutes > 0:
            ratio = est_minutes / target_minutes
            if ratio < 0.5:
                logger.warning(f"TTS audio likely much shorter than {target_minutes}m target")
            elif ratio > 1.5:
                logger.warning(f"TTS audio likely much longer than {target_minutes}m target")

        return data
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return None
