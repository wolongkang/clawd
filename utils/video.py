import logging
import os
import subprocess
import json
import requests

logger = logging.getLogger(__name__)

TMP = "/tmp/videobot"


def _ensure_tmp():
    os.makedirs(TMP, exist_ok=True)


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


def _download_clips(urls: list[str]) -> list[str]:
    """Download multiple clips, return list of local paths."""
    paths = []
    for i, url in enumerate(urls):
        path = os.path.join(TMP, f"clip_{i}.mp4")
        if _download(url, path):
            paths.append(path)
    return paths


def _concat_clips(clip_paths: list[str], target_duration: float, output_path: str) -> bool:
    """Concatenate and loop clips to fill target_duration."""
    if not clip_paths:
        return False

    # Get total duration of all clips
    durations = [get_duration(p) for p in clip_paths]
    total = sum(durations)

    if total <= 0:
        logger.error("All clips have zero duration")
        return False

    # Build concat list, repeating clips until we exceed target duration
    concat_file = os.path.join(TMP, "concat.txt")
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

    # Concatenate all clips
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
    2. Overlay avatar as picture-in-picture (looped, bottom-right corner)
    3. Mix in audio track
    """
    _ensure_tmp()

    # Get audio duration — this is the master length
    audio_dur = get_duration(audio_path)
    if audio_dur <= 0:
        logger.error("Audio has zero duration, cannot composite")
        return False
    logger.info(f"Master audio duration: {audio_dur:.1f}s ({audio_dur / 60:.1f} min)")

    # Download and concatenate background clips
    clip_paths = _download_clips(background_urls)
    if not clip_paths:
        logger.error("No background clips downloaded")
        return False

    bg_full = os.path.join(TMP, "bg_full.mp4")
    if not _concat_clips(clip_paths, audio_dur, bg_full):
        logger.error("Background concatenation failed")
        return False

    # Download avatar
    av_file = os.path.join(TMP, "avatar.mp4")
    if not _download(avatar_url, av_file):
        logger.error("Avatar download failed")
        return False

    avatar_dur = get_duration(av_file)
    logger.info(f"Avatar clip: {avatar_dur:.1f}s (will loop as PIP)")

    # Final composite:
    # - Background fills the full duration (already trimmed to audio length)
    # - Avatar loops as PIP in bottom-right corner (scaled to 25% of frame)
    # - Audio is the master track
    # - Avatar fades in/out every cycle for polish
    cmd = [
        "ffmpeg", "-y",
        "-i", bg_full,                     # input 0: background (full duration)
        "-stream_loop", "-1", "-i", av_file, # input 1: avatar (looped infinitely)
        "-i", audio_path,                   # input 2: audio
        "-filter_complex",
        (
            # Scale avatar to PIP size (320x180) and add slight transparency
            "[1:v]scale=320:180,format=yuva420p,colorchannelmixer=aa=0.9[pip];"
            # Overlay PIP on background, bottom-right with 20px margin
            "[0:v][pip]overlay=W-w-20:H-h-20:shortest=1[outv]"
        ),
        "-map", "[outv]",                  # use composited video
        "-map", "2:a",                     # use audio from input 2
        "-t", str(audio_dur),              # trim to audio duration
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]

    success = _run_ffmpeg(cmd, timeout=900)  # 15 min timeout for long videos
    if success:
        final_dur = get_duration(output_path)
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"Final video: {final_dur:.1f}s ({final_dur / 60:.1f} min), {size_mb:.1f} MB")
    return success
