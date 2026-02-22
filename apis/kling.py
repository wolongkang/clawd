import logging
import time
import asyncio
import jwt
import requests
from config import KLINGAI_ACCESS_KEY, KLINGAI_SECRET_KEY

logger = logging.getLogger(__name__)


def _get_token():
    now = int(time.time())
    payload = {"iss": KLINGAI_ACCESS_KEY, "exp": now + 3600, "iat": now, "nbf": now}
    return jwt.encode(payload, KLINGAI_SECRET_KEY, algorithm="HS256")


async def create_video(narrative: str, duration: int) -> str:
    try:
        headers = {"Authorization": f"Bearer {_get_token()}", "Content-Type": "application/json"}
        payload = {
            "model_name": "kling-v2-6",
            "prompt": narrative,
            "duration": str(duration),
            "mode": "pro",
            "sound": "on",
            "aspect_ratio": "16:9",
        }
        response = requests.post(
            "https://api-singapore.klingai.com/v1/videos/text2video",
            headers=headers,
            json=payload,
            timeout=30,
        )
        if response.status_code == 200:
            return response.json().get("data", {}).get("task_id")
        logger.error(f"Kling create failed: {response.status_code} {response.text}")
        return None
    except Exception as e:
        logger.error(f"Kling create error: {e}")
        return None


async def poll_video(task_id: str, status_msg) -> str:
    headers = {"Authorization": f"Bearer {_get_token()}", "Content-Type": "application/json"}

    for attempt in range(60):
        try:
            response = requests.get(
                f"https://api-singapore.klingai.com/v1/videos/text2video/{task_id}",
                headers=headers,
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                status = data.get("data", {}).get("task_status")

                if attempt % 3 == 0:
                    await status_msg.edit_text(f"Generating... {status} ({attempt * 10}s)")

                if status == "succeed":
                    videos = data.get("data", {}).get("task_result", {}).get("videos", [])
                    if videos:
                        return videos[0].get("url")
                    logger.error(f"Kling succeeded but no videos in response: {data}")
                    return None
                elif status == "failed":
                    logger.error(f"Kling task failed: {data}")
                    return None
        except Exception as e:
            logger.error(f"Kling poll error: {e}")

        await asyncio.sleep(10)
    return None
