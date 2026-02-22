import logging
import os
import subprocess
import json
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


def get_duration(file_path: str) -> float:
    """Get duration of a media file in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                file_path,
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            info = json.loads(result.stdout)
            duration = float(info.get("format", {}).get("duration", 0))
            logger.info(f"Duration of {os.path.basename(file_path)}: {duration:.1f}s")
            return duration
    except Exception as e:
        logger.error(f"ffprobe error for {file_path}: {e}")
    return 0.0


def _run_ffmpeg(cmd: list, timeout: int = 600) -> bool:
    """Run an ffmpeg command and log errors."""
    try:
        logger.info(f"ffmpeg: {' '.join(cmd[:6])}...")
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if result.returncode == 0:
            return True
        logger.error(f"ffmpeg error: {result.stderr.decode()[-500:]}")
        return False
    except Exception as e:
        logger.error(f"ffmpeg exception: {e}")
        return False


def _download_clips(urls: list[str], work_dir: str) -> list[str]:
    """Download multiple clips, return list of local paths."""
    paths = []
    for i, url in enumerate(urls):
        path = os.path.join(work_dir, f"clip_{i}.mp4")
        if _download(url, path):
            paths.append(path)
    return paths


def _concat_clips(clip_paths: list[str], target_duration: float, output_path: str, work_dir: str) -> bool:
    """Concatenate and loop clips to fill target_duration."""
    if not clip_paths:
        return False

    durations = [get_duration(p) for p in clip_paths]
    total = sum(durations)

    if total <= 0:
        logger.error("All clips have zero duration")
        return False

    concat_file = os.path.join(work_dir, "concat.txt")
    accumulated = 0.0
    with open(concat_file, "w") as f:
        while accumulated < target_duration:
            for path, dur in zip(clip_paths, durations):
                if dur <= 0:
                    continue
                f.write(f"file '{path}'\n")
                accumulated += dur
                if accumulated >= target_duration:
                    break

    logger.info(f"Concat list: {accumulated:.1f}s of clips to fill {target_duration:.1f}s target")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_file,
        "-t", str(target_duration),
        "-c:v", "libx264", "-preset", "fast",
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
        "-r", "30",
        "-an",
        output_path,
    ]
    return _run_ffmpeg(cmd)


def composite_video(
    background_urls: list[str],
    avatar_url: str,
    audio_path: str,
    output_path: str,
) -> bool:
    """
    Composite a full YouTube video:
    1. Concatenate background clips to match audio duration
    2. Mix in audio track
    """
    # Use output_path's directory as work dir
    work_dir = os.path.dirname(output_path)
    os.makedirs(work_dir, exist_ok=True)

    # Get audio duration — this is the master length
    audio_dur = get_duration(audio_path)
    if audio_dur <= 0:
        logger.error("Audio has zero duration, cannot composite")
        return False
    logger.info(f"Master audio duration: {audio_dur:.1f}s ({audio_dur / 60:.1f} min)")

    # Download and concatenate background clips
    clip_paths = _download_clips(background_urls, work_dir)
    if not clip_paths:
        logger.error("No background clips downloaded")
        return False

    bg_full = os.path.join(work_dir, "bg_full.mp4")
    if not _concat_clips(clip_paths, audio_dur, bg_full, work_dir):
        logger.error("Background concatenation failed")
        return False

    # Background + audio only
    cmd = [
        "ffmpeg", "-y",
        "-i", bg_full,
        "-i", audio_path,
        "-map", "0:v",
        "-map", "1:a",
        "-t", str(audio_dur),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]

    success = _run_ffmpeg(cmd, timeout=900)
    if success:
        final_dur = get_duration(output_path)
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"Final video: {final_dur:.1f}s ({final_dur / 60:.1f} min), {size_mb:.1f} MB")
    return success
