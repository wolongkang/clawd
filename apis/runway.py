import logging
import asyncio
import requests
from config import RUNWAY_API_KEY

logger = logging.getLogger(__name__)

HEADERS = {
    "Authorization": f"Bearer {RUNWAY_API_KEY}",
    "Content-Type": "application/json",
    "X-Runway-Version": "2024-11-06",
}
POLL_HEADERS = {
    "Authorization": f"Bearer {RUNWAY_API_KEY}",
    "X-Runway-Version": "2024-11-06",
}


async def create_avatar(topic: str) -> str:
    """Generate a short presenter avatar clip (10s) for PIP overlay."""
    try:
        prompt = (
            f"A professional, friendly video presenter standing in a modern studio, "
            f"talking directly to the camera about {topic[:100]}. "
            f"Well-lit, clean background, natural gestures, educational tone."
        )
        payload = {
            "model": "gen3a_turbo",
            "promptText": prompt,
            "ratio": "1280:720",
            "duration": 10,
        }
        response = requests.post(
            "https://api.dev.runwayml.com/v1/text_to_video",
            headers=HEADERS,
            json=payload,
            timeout=30,
        )
        if response.status_code == 200:
            task_id = response.json().get("id")
            logger.info(f"Avatar task created: {task_id}")
            return task_id
        logger.error(f"Runway create failed: {response.status_code} {response.text}")
        return None
    except Exception as e:
        logger.error(f"Runway create error: {e}")
        return None


async def poll_avatar(task_id: str) -> str:
    """Poll Runway until avatar video is ready."""
    for attempt in range(120):
        try:
            response = requests.get(
                f"https://api.dev.runwayml.com/v1/tasks/{task_id}",
                headers=POLL_HEADERS,
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                logger.info(f"Avatar poll #{attempt}: {status}")

                if status == "SUCCEEDED":
                    output = data.get("output")
                    logger.info(f"Avatar output (raw): {output}")

                    # Runway returns output as a list of URL strings
                    if isinstance(output, list) and output:
                        url = output[0]
                        if isinstance(url, str):
                            return url
                        if isinstance(url, dict):
                            return url.get("url")
                    elif isinstance(output, str):
                        return output

                    logger.error(f"Avatar SUCCEEDED but no usable URL: {output}")
                    return None
                elif status in ("FAILED", "ERROR"):
                    logger.error(f"Avatar failed: {data}")
                    return None
            else:
                logger.error(f"Avatar poll HTTP {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Avatar poll error: {e}")

        await asyncio.sleep(5)

    logger.error("Avatar poll timed out after 120 attempts")
    return None
