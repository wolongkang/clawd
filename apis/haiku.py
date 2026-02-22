import json
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
            "model": "claude-haiku-4-5-20251001",
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


async def generate_youtube_script_structured(topic: str, minutes: int) -> dict:
    """Generate a structured script with chapters, each having narration + visual description.

    Returns: {"chapters": [{"title": "...", "narration": "...", "visual": "..."}]}
    """
    if not ANTHROPIC_API_KEY:
        return None

    # Scale chapters with video length
    chapter_count = max(4, min(16, minutes * 2 - 2))
    target_words = minutes * WORDS_PER_MINUTE
    words_per_chapter = target_words // chapter_count

    try:
        prompt = (
            f"Write a {minutes}-minute YouTube video script about: {topic}\n\n"
            f"Structure it as exactly {chapter_count} chapters. "
            f"Each chapter should have approximately {words_per_chapter} words of narration.\n\n"
            f"For each chapter, provide:\n"
            f"1. \"title\" - short chapter title (2-5 words)\n"
            f"2. \"narration\" - the spoken narration text (~{words_per_chapter} words). "
            f"Professional educational tone, specific facts, natural speaking pace. "
            f"No stage directions, just spoken words.\n"
            f"3. \"visual\" - a detailed image generation prompt for this chapter's visual slide. "
            f"Describe a vivid, cinematic 16:9 scene that illustrates the chapter's topic. "
            f"Include: subject, setting, lighting, mood, camera angle. "
            f"Style: photorealistic, high detail, professional cinematography.\n\n"
            f"Return ONLY valid JSON. No markdown, no explanation. Format:\n"
            f'{{"chapters": [\n'
            f'  {{"title": "The Hook", "narration": "Did you know that...", '
            f'"visual": "A dramatic close-up of..."}}\n'
            f"]}}"
        )

        result = _call_haiku(prompt, max_tokens=min(8000, target_words + 2000))
        if not result:
            return None

        # Parse JSON
        result = result.strip()
        if result.startswith("```"):
            result = result.split("```")[1]
            if result.startswith("json"):
                result = result[4:]
        data = json.loads(result)

        if not isinstance(data, dict) or "chapters" not in data:
            logger.error(f"Invalid structured script format: {str(data)[:200]}")
            return None

        chapters = data["chapters"]
        total_words = sum(len(ch.get("narration", "").split()) for ch in chapters)
        logger.info(
            f"Structured script: {len(chapters)} chapters, "
            f"{total_words} words (~{total_words / WORDS_PER_MINUTE:.1f} min)"
        )

        # If way too short, extend with a follow-up call
        if total_words < target_words * 0.6:
            logger.warning(f"Script too short ({total_words}/{target_words}), extending chapters...")
            remaining = target_words - total_words
            ext_prompt = (
                f"The following script chapters are too short (total {total_words} words, "
                f"need {target_words}). Add {remaining} more words by expanding each chapter's "
                f"narration with more detail, examples, and facts. "
                f"Return the complete updated JSON in the same format.\n\n{result}"
            )
            ext_result = _call_haiku(ext_prompt, max_tokens=min(8000, remaining + 2000))
            if ext_result:
                ext_result = ext_result.strip()
                if ext_result.startswith("```"):
                    ext_result = ext_result.split("```")[1]
                    if ext_result.startswith("json"):
                        ext_result = ext_result[4:]
                try:
                    ext_data = json.loads(ext_result)
                    if isinstance(ext_data, dict) and "chapters" in ext_data:
                        data = ext_data
                        total_words = sum(len(ch.get("narration", "").split()) for ch in data["chapters"])
                        logger.info(f"Extended script: {total_words} words (~{total_words / WORDS_PER_MINUTE:.1f} min)")
                except json.JSONDecodeError:
                    logger.warning("Failed to parse extended script, using original")

        return data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse structured script JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Structured script error: {e}")
        return None
