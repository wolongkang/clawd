import logging
from openai import OpenAI
from config import XAI_API_KEY

logger = logging.getLogger(__name__)

grok_client = OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1") if XAI_API_KEY else None


def is_available() -> bool:
    return grok_client is not None


async def generate_narrative_short(topic: str) -> str:
    if not grok_client:
        return None
    try:
        response = grok_client.chat.completions.create(
            model="grok-3",
            messages=[{"role": "user", "content": f"Write a vivid video narrative: {topic}"}],
            max_tokens=150,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Grok narrative error: {e}")
        return None


async def generate_youtube_script(topic: str, minutes: int) -> str:
    if not grok_client:
        return None
    try:
        words = minutes * 130
        prompt = (
            f"Write a detailed {minutes}-minute YouTube script about: {topic}\n"
            f"Requirements:\n"
            f"- Professional educational tone\n"
            f"- Include specific facts and examples\n"
            f"- Approximately {words} words\n"
            f"- Natural speaking pace\n"
            f"- Structure: Hook, Introduction, Main Content, Conclusion"
        )
        response = grok_client.chat.completions.create(
            model="grok-3",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=min(4000, words + 500),
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Grok script error: {e}")
        return None
