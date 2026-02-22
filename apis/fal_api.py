import logging
import os
import requests
import time
from config import FAL_KEY

logger = logging.getLogger(__name__)

FAL_BASE = "https://queue.fal.run"
HEADERS = {
    "Authorization": f"Key {FAL_KEY}",
    "Content-Type": "application/json",
}


def is_available() -> bool:
    return bool(FAL_KEY)


def _submit(endpoint: str, payload: dict) -> str:
    """Submit a task to fal.ai queue, return request_id."""
    url = f"{FAL_BASE}/{endpoint}"
    resp = requests.post(url, json=payload, headers=HEADERS, timeout=60)
    if resp.status_code == 200:
        data = resp.json()
        req_id = data.get("request_id")
        logger.info(f"fal.ai submitted {endpoint}: {req_id}")
        return req_id
    logger.error(f"fal.ai submit error: {resp.status_code} {resp.text[:300]}")
    return None


def _poll(endpoint: str, request_id: str, timeout: int = 300) -> dict:
    """Poll fal.ai queue for result."""
    status_url = f"https://queue.fal.run/{endpoint}/requests/{request_id}/status"
    result_url = f"https://queue.fal.run/{endpoint}/requests/{request_id}"
    start = time.time()
    poll_count = 0

    while time.time() - start < timeout:
        try:
            resp = requests.get(status_url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status")
                logger.info(f"fal.ai poll #{poll_count}: {status}")

                if status == "COMPLETED":
                    # Fetch the actual result
                    result_resp = requests.get(result_url, headers=HEADERS, timeout=30)
                    if result_resp.status_code == 200:
                        return result_resp.json()
                    logger.error(f"fal.ai result fetch error: {result_resp.status_code}")
                    return None
                elif status in ("FAILED", "CANCELLED"):
                    logger.error(f"fal.ai task {status}: {data}")
                    return None
            else:
                logger.warning(f"fal.ai status check error: {resp.status_code}")
        except Exception as e:
            logger.error(f"fal.ai poll error: {e}")

        poll_count += 1
        time.sleep(5)

    logger.error(f"fal.ai timeout after {timeout}s")
    return None


async def generate_image(prompt: str, ref_url: str = None) -> str:
    """Generate a scene image with Nano Banana Pro. Returns image URL."""
    if not FAL_KEY:
        return None

    try:
        if ref_url:
            # Use edit endpoint for character consistency
            endpoint = "fal-ai/nano-banana-pro/edit"
            payload = {
                "prompt": prompt,
                "image_urls": [ref_url],
                "image_size": {"width": 768, "height": 1344},
            }
        else:
            endpoint = "fal-ai/nano-banana-pro"
            payload = {
                "prompt": prompt,
                "image_size": {"width": 768, "height": 1344},
            }

        req_id = _submit(endpoint, payload)
        if not req_id:
            return None

        result = _poll(endpoint, req_id, timeout=120)
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
        endpoint = "fal-ai/veo3.1/fast/image-to-video"
        payload = {
            "prompt": prompt,
            "image_url": image_url,
            "duration": duration,
            "aspect_ratio": "9:16",
        }

        req_id = _submit(endpoint, payload)
        if not req_id:
            return None

        # Animation takes longer — 5 min timeout
        result = _poll(endpoint, req_id, timeout=300)
        if result and "video" in result:
            url = result["video"]["url"]
            logger.info(f"Animation generated: {url[:80]}...")
            return url

        logger.error(f"No video in result: {result}")
        return None

    except Exception as e:
        logger.error(f"Animation error: {e}")
        return None
