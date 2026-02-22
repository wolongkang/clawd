import logging
import requests
from config import PEXELS_API_KEY

logger = logging.getLogger(__name__)


async def get_footage(keyword: str, count: int = 3) -> list:
    """Fetch stock video clips from Pexels."""
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


async def get_footage_for_script(keywords: list[str], clips_per_keyword: int = 2) -> list:
    """Fetch multiple clips using multiple keywords extracted from the script."""
    all_urls = []
    seen = set()
    for kw in keywords:
        urls = await get_footage(kw, count=clips_per_keyword)
        for url in urls:
            if url not in seen:
                seen.add(url)
                all_urls.append(url)
    logger.info(f"Pexels total: {len(all_urls)} unique clips from {len(keywords)} keywords")
    return all_urls
