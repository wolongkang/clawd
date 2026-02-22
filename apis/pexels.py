import logging
import requests
from config import PEXELS_API_KEY

logger = logging.getLogger(__name__)


async def get_footage(keyword: str, count: int = 3) -> list:
    try:
        response = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": keyword, "per_page": count, "page": 1},
            timeout=15,
        )
        if response.status_code == 200:
            videos = response.json().get("videos", [])
            urls = [v["video_files"][0]["link"] for v in videos if v.get("video_files")]
            logger.info(f"Pexels: got {len(urls)} clips for '{keyword}'")
            return urls
        logger.error(f"Pexels failed: {response.status_code}")
        return []
    except Exception as e:
        logger.error(f"Pexels error: {e}")
        return []
