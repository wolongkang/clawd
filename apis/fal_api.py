import logging
import os
import fal_client
from config import FAL_KEY
from apis.haiku import _call_haiku

logger = logging.getLogger(__name__)

# Set the FAL_KEY environment variable for the fal_client library
os.environ["FAL_KEY"] = FAL_KEY


def is_available() -> bool:
    return bool(FAL_KEY)


async def generate_image(prompt: str, ref_url: str = None) -> str:
    """Generate a scene image with Nano Banana Pro. Returns image URL."""
    if not FAL_KEY:
        return None

    try:
        if ref_url:
            logger.info(f"Generating image (with ref) via nano-banana-pro/edit...")
            result = fal_client.subscribe(
                "fal-ai/nano-banana-pro/edit",
                arguments={
                    "prompt": prompt,
                    "image_urls": [ref_url],
                    "image_size": {"width": 768, "height": 1344},
                },
            )
        else:
            logger.info(f"Generating image via nano-banana-pro...")
            result = fal_client.subscribe(
                "fal-ai/nano-banana-pro",
                arguments={
                    "prompt": prompt,
                    "image_size": {"width": 768, "height": 1344},
                },
            )

        if result and "images" in result and result["images"]:
            url = result["images"][0]["url"]
            logger.info(f"Image generated: {url[:80]}...")
            return url

        logger.error(f"No image in result: {result}")
        return None

    except Exception as e:
        logger.error(f"Image generation error: {e}")
        return None


async def generate_slide(prompt: str) -> str:
    """Generate a 16:9 landscape slide image for YouTube video. Returns image URL."""
    if not FAL_KEY:
        return None

    try:
        logger.info(f"Generating slide (1280x720) via nano-banana-pro...")
        result = fal_client.subscribe(
            "fal-ai/nano-banana-pro",
            arguments={
                "prompt": prompt,
                "image_size": {"width": 1280, "height": 720},
            },
        )

        if result and "images" in result and result["images"]:
            url = result["images"][0]["url"]
            logger.info(f"Slide generated: {url[:80]}...")
            return url

        logger.error(f"No image in slide result: {result}")
        return None

    except Exception as e:
        logger.error(f"Slide generation error: {e}")
        return None


def _sanitize_prompt(prompt: str) -> str:
    """Use Haiku to rewrite a prompt that was flagged by content moderation."""
    sanitized = _call_haiku(
        f"Rewrite this animation prompt to be completely safe and family-friendly, "
        f"while keeping the same visual action and character movement. "
        f"Remove anything that could be flagged by content moderation. "
        f"Keep it short (under 200 words). Keep the instruction: "
        f"'Do not display any text, captions, subtitles, or words on screen'\n\n"
        f"Original prompt:\n{prompt}",
        max_tokens=300,
    )
    if sanitized:
        logger.info(f"Sanitized prompt: {sanitized[:100]}...")
        return sanitized
    return prompt


async def animate_scene(image_url: str, prompt: str, duration: str = "8s") -> str:
    """Animate a scene image with Veo 3.1 Fast. Returns video URL.
    Auto-retries with sanitized prompt if content policy violation occurs."""
    if not FAL_KEY:
        return None

    for attempt in range(2):
        try:
            current_prompt = prompt if attempt == 0 else _sanitize_prompt(prompt)
            logger.info(f"Animating scene with veo3.1/fast ({duration}), attempt {attempt + 1}...")
            result = fal_client.subscribe(
                "fal-ai/veo3.1/fast/image-to-video",
                arguments={
                    "prompt": current_prompt,
                    "image_url": image_url,
                    "duration": duration,
                    "aspect_ratio": "9:16",
                },
            )

            if result and "video" in result:
                url = result["video"]["url"]
                logger.info(f"Animation generated: {url[:80]}...")
                return url

            logger.error(f"No video in result: {result}")
            return None

        except Exception as e:
            error_str = str(e)
            if "content_policy_violation" in error_str and attempt == 0:
                logger.warning(f"Content policy violation, retrying with sanitized prompt...")
                continue
            logger.error(f"Animation error: {e}")
            return None

    return None
