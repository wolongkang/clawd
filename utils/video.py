import logging
import subprocess
import requests

logger = logging.getLogger(__name__)


def _download(url: str, path: str) -> bool:
    try:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(resp.content)
        logger.info(f"Downloaded {len(resp.content)} bytes -> {path}")
        return True
    except Exception as e:
        logger.error(f"Download failed ({url}): {e}")
        return False


def composite_video(background_url: str, avatar_url: str, audio_path: str, output_path: str) -> bool:
    bg_file = "/tmp/background.mp4"
    av_file = "/tmp/avatar.mp4"

    if not _download(background_url, bg_file):
        return False
    if not _download(avatar_url, av_file):
        return False

    cmd = [
        "ffmpeg", "-y",
        "-i", bg_file,
        "-i", av_file,
        "-i", audio_path,
        "-filter_complex", "[1]scale=960:720[avatar];[0][avatar]overlay=(W-w)/2:(H-h)/2",
        "-c:v", "libx264",
        "-c:a", "aac",
        output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode == 0:
            logger.info("Video composite complete")
            return True
        logger.error(f"ffmpeg error: {result.stderr.decode()}")
        return False
    except Exception as e:
        logger.error(f"Composite error: {e}")
        return False
