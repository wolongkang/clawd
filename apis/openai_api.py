import logging
from openai import OpenAI
from config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)

WORDS_PER_MINUTE = 150


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
    """Generate a YouTube script targeting a specific duration."""
    target_words = minutes * WORDS_PER_MINUTE
    try:
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
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=min(4000, target_words + 500),
        )
        script = response.choices[0].message.content
        word_count = len(script.split())
        logger.info(f"Script: {word_count} words (target: {target_words}, ~{word_count / WORDS_PER_MINUTE:.1f} min)")

        # If way too short, try once more
        if word_count < target_words * 0.6:
            logger.warning(f"Script too short ({word_count}/{target_words}), retrying...")
            remaining = target_words - word_count
            response2 = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": f"Continue this script with {remaining} more words:\n\n{script[-500:]}"}],
                max_tokens=min(4000, remaining + 200),
            )
            script += "\n\n" + response2.choices[0].message.content
            word_count = len(script.split())
            logger.info(f"Script after extension: {word_count} words (~{word_count / WORDS_PER_MINUTE:.1f} min)")

        return script
    except Exception as e:
        logger.error(f"OpenAI script error: {e}")
        return None


async def extract_video_keywords(script: str, count: int = 6) -> list[str]:
    """Extract visual search keywords from the script for stock footage."""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{
                "role": "user",
                "content": (
                    f"Extract {count} visual search keywords from this script for finding stock footage. "
                    f"Return ONLY the keywords, one per line, no numbers or bullets.\n\n"
                    f"{script[:2000]}"
                ),
            }],
            max_tokens=100,
        )
        keywords = [kw.strip() for kw in response.choices[0].message.content.strip().split("\n") if kw.strip()]
        logger.info(f"Extracted keywords: {keywords}")
        return keywords[:count]
    except Exception as e:
        logger.error(f"Keyword extraction error: {e}")
        return []
