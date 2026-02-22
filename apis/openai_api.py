import logging
from openai import OpenAI
from config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)


async def generate_narrative_short(topic: str) -> str:
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": f"Write a vivid video narrative: {topic}"}],
            max_tokens=150,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI narrative error: {e}")
        return None


async def generate_youtube_script(topic: str, minutes: int) -> str:
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
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=min(4000, words + 500),
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI script error: {e}")
        return None
