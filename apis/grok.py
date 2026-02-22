import logging
from openai import OpenAI
from config import XAI_API_KEY

logger = logging.getLogger(__name__)

grok_client = OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1") if XAI_API_KEY else None

WORDS_PER_MINUTE = 150


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
        response = grok_client.chat.completions.create(
            model="grok-3",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=min(4000, target_words + 500),
        )
        script = response.choices[0].message.content
        word_count = len(script.split())
        logger.info(f"Grok script: {word_count} words (target: {target_words}, ~{word_count / WORDS_PER_MINUTE:.1f} min)")

        # If way too short, try once more
        if word_count < target_words * 0.6:
            logger.warning(f"Script too short ({word_count}/{target_words}), retrying...")
            remaining = target_words - word_count
            response2 = grok_client.chat.completions.create(
                model="grok-3",
                messages=[{"role": "user", "content": f"Continue this script with {remaining} more words:\n\n{script[-500:]}"}],
                max_tokens=min(4000, remaining + 200),
            )
            script += "\n\n" + response2.choices[0].message.content
            word_count = len(script.split())
            logger.info(f"Grok script after extension: {word_count} words (~{word_count / WORDS_PER_MINUTE:.1f} min)")

        return script
    except Exception as e:
        logger.error(f"Grok script error: {e}")
        return None
