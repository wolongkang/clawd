import io
import logging
import requests
from config import ELEVENLABS_API_KEY

logger = logging.getLogger(__name__)

# ElevenLabs voice IDs
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # "Rachel" — clear, professional female voice
# Other options: "ErXwobaYiN019PkySvjV" (Antoni - male), "EXAVITQu4vr4xnSDxMaL" (Bella)


async def generate_speech(text: str, target_minutes: int = 0) -> bytes:
    """Generate TTS audio using ElevenLabs."""
    word_count = len(text.split())
    est_minutes = word_count / 150
    logger.info(f"ElevenLabs: {word_count} words, ~{est_minutes:.1f} min estimated")

    if target_minutes > 0:
        ratio = est_minutes / target_minutes
        if ratio < 0.5:
            logger.warning(f"Audio likely much shorter than {target_minutes}m target")
        elif ratio > 1.5:
            logger.warning(f"Audio likely much longer than {target_minutes}m target")

    try:
        chunks = _split_text(text, max_chars=4500)
        all_audio = io.BytesIO()

        for i, chunk in enumerate(chunks):
            logger.info(f"ElevenLabs: chunk {i + 1}/{len(chunks)} ({len(chunk)} chars)")
            response = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
                headers={
                    "xi-api-key": ELEVENLABS_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "text": chunk,
                    "model_id": "eleven_monolingual_v1",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                    },
                },
                timeout=120,
            )

            if response.status_code == 200:
                all_audio.write(response.content)
            else:
                logger.error(f"ElevenLabs error: {response.status_code} {response.text[:200]}")
                return None

        data = all_audio.getvalue()
        logger.info(f"ElevenLabs: {len(data)} bytes total from {len(chunks)} chunks")
        return data

    except Exception as e:
        logger.error(f"ElevenLabs error: {e}")
        return None


def _split_text(text: str, max_chars: int = 4500) -> list[str]:
    """Split text into chunks at sentence boundaries."""
    sentences = text.replace("\n", " ").split(". ")
    chunks = []
    current = ""

    for sentence in sentences:
        candidate = f"{current}. {sentence}" if current else sentence
        if len(candidate) > max_chars and current:
            chunks.append(current.strip())
            current = sentence
        else:
            current = candidate

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [text[:max_chars]]
