import logging
import os
import fal_client
from config import FAL_KEY

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
            # Use edit endpoint for character consistency
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


async def animate_scene(image_url: str, prompt: str, duration: str = "8s") -> str:
    """Animate a scene image with Veo 3.1 Fast. Returns video URL."""
    if not FAL_KEY:
        return None

    try:
        logger.info(f"Animating scene with veo3.1/fast ({duration})...")
        result = fal_client.subscribe(
            "fal-ai/veo3.1/fast/image-to-video",
            arguments={
                "prompt": prompt,
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
        logger.error(f"Animation error: {e}")
        return None
