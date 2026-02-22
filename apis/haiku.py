import logging
import requests
from config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

WORDS_PER_MINUTE = 150


def is_available() -> bool:
    return bool(ANTHROPIC_API_KEY)


def _call_haiku(prompt: str, max_tokens: int = 4000) -> str:
    """Call Claude Haiku via the Anthropic API."""
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-3-5-haiku-latest",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    if response.status_code == 200:
        return response.json()["content"][0]["text"]
    logger.error(f"Haiku API error: {response.status_code} {response.text[:200]}")
    return None


async def generate_narrative_short(topic: str) -> str:
    if not ANTHROPIC_API_KEY:
        return None
    try:
        return _call_haiku(f"Write a vivid video narrative: {topic}", max_tokens=150)
    except Exception as e:
        logger.error(f"Haiku narrative error: {e}")
        return None


async def generate_youtube_script(topic: str, minutes: int) -> str:
    if not ANTHROPIC_API_KEY:
        return None
    try:
        target_words = minutes * WORDS_PER_MINUTE
        prompt = (
            f"Write a detailed {minutes}-minute YouTube script about: {topic}\n"
            f"Requirements:\n"
            f"- Professional educational tone\n"
            f"- Include specific facts and examples\n"
            f"- EXACTLY approximately {target_words} words (this is critical)\n"
            f"- Natural speaking pace\n"
            f"- Structure: Hook, Introduction, Main Content, Conclusion\n"
            f"- Do NOT include stage directions, just the spoken words"
        )
        script = _call_haiku(prompt, max_tokens=min(4000, target_words + 500))
        if not script:
            return None

        word_count = len(script.split())
        logger.info(f"Haiku script: {word_count} words (target: {target_words}, ~{word_count / WORDS_PER_MINUTE:.1f} min)")

        if word_count < target_words * 0.6:
            logger.warning(f"Script too short ({word_count}/{target_words}), extending...")
            remaining = target_words - word_count
            extension = _call_haiku(
                f"Continue this script with {remaining} more words:\n\n{script[-500:]}",
                max_tokens=min(4000, remaining + 200),
            )
            if extension:
                script += "\n\n" + extension
                word_count = len(script.split())
                logger.info(f"Haiku script extended: {word_count} words (~{word_count / WORDS_PER_MINUTE:.1f} min)")

        return script
    except Exception as e:
        logger.error(f"Haiku script error: {e}")
        return None
