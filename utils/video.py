import logging
import os
import random
import subprocess
import json
import requests

logger = logging.getLogger(__name__)

# Ken Burns effect presets (for zoompan filter)
KB_EFFECTS = [
    "zoom_in",
    "zoom_out",
    "pan_right",
    "pan_left",
]


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
        logger.info(f"ffmpeg: {' '.join(cmd[:8])}...")
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


# ---------------------------------------------------------------------------
# Ken Burns effect: create motion from a static image
# ---------------------------------------------------------------------------

def _ken_burns_clip(image_path: str, duration: float, output_path: str, effect: str = "zoom_in") -> bool:
    """Create a Ken Burns (zoom+pan) video clip from a static image.

    Effects: zoom_in, zoom_out, pan_right, pan_left
    """
    fps = 30
    total_frames = int(duration * fps)

    # zoompan parameters (d=total_frames, s=output size, fps)
    # zoom goes from 1.0 to 1.15 (subtle, professional)
    if effect == "zoom_in":
        zp = f"zoompan=z='1+0.15*on/{total_frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1280x720:fps={fps}"
    elif effect == "zoom_out":
        zp = f"zoompan=z='1.15-0.15*on/{total_frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1280x720:fps={fps}"
    elif effect == "pan_right":
        zp = f"zoompan=z='1.1':x='0.1*iw*on/{total_frames}':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1280x720:fps={fps}"
    elif effect == "pan_left":
        zp = f"zoompan=z='1.1':x='0.1*iw*(1-on/{total_frames})':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1280x720:fps={fps}"
    else:
        zp = f"zoompan=z='1+0.15*on/{total_frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1280x720:fps={fps}"

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", image_path,
        "-vf", zp,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-an",
        output_path,
    ]
    return _run_ffmpeg(cmd, timeout=120)


def create_ken_burns_clips(
    image_urls: list[str],
    durations: list[float],
    work_dir: str,
) -> list[str]:
    """Download slide images and create Ken Burns clips for each.

    Returns list of clip paths (one per chapter).
    """
    clip_paths = []
    for i, (url, dur) in enumerate(zip(image_urls, durations)):
        # Download image
        ext = ".jpg" if ".jpg" in url.lower() or ".jpeg" in url.lower() else ".png"
        img_path = os.path.join(work_dir, f"slide_{i:02d}{ext}")
        if not _download(url, img_path):
            logger.error(f"Failed to download slide {i}")
            return []

        # Pick alternating Ken Burns effect
        effect = KB_EFFECTS[i % len(KB_EFFECTS)]
        clip_path = os.path.join(work_dir, f"kb_{i:02d}.mp4")
        logger.info(f"Ken Burns clip {i}: {dur:.1f}s, effect={effect}")

        if not _ken_burns_clip(img_path, dur, clip_path, effect):
            logger.error(f"Ken Burns failed for slide {i}")
            return []

        clip_paths.append(clip_path)

    return clip_paths


# ---------------------------------------------------------------------------
# Crossfade concat
# ---------------------------------------------------------------------------

def _concat_with_crossfades(clip_paths: list[str], output_path: str, fade_dur: float = 0.5) -> bool:
    """Concatenate clips with crossfade transitions using xfade filter.

    For N clips, applies N-1 xfade transitions.
    """
    if not clip_paths:
        return False

    if len(clip_paths) == 1:
        # Just copy single clip
        cmd = ["ffmpeg", "-y", "-i", clip_paths[0], "-c", "copy", output_path]
        return _run_ffmpeg(cmd)

    # Get durations to calculate xfade offsets
    durations = [get_duration(p) for p in clip_paths]

    # Build xfade filter chain
    # For 3 clips: [0][1]xfade=offset=O1[v1]; [v1][2]xfade=offset=O2[v2]
    inputs = []
    for p in clip_paths:
        inputs.extend(["-i", p])

    filter_parts = []
    offset = durations[0] - fade_dur

    for i in range(1, len(clip_paths)):
        if i == 1:
            src = "[0:v][1:v]"
        else:
            src = f"[v{i-1}][{i}:v]"

        if i == len(clip_paths) - 1:
            dst = "[vout]"
        else:
            dst = f"[v{i}]"

        filter_parts.append(f"{src}xfade=transition=fade:duration={fade_dur}:offset={offset:.3f}{dst}")
        if i < len(clip_paths) - 1:
            offset += durations[i] - fade_dur

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-an",
        output_path,
    ]
    return _run_ffmpeg(cmd, timeout=900)


# ---------------------------------------------------------------------------
# Slide-based composite (new pipeline for long-form YouTube)
# ---------------------------------------------------------------------------

def composite_slides_video(
    slide_clip_paths: list[str],
    audio_path: str,
    output_path: str,
) -> bool:
    """Composite Ken Burns slide clips with crossfades + audio into final video.

    1. Crossfade concat all slide clips
    2. Mix with audio track in single final pass
    """
    work_dir = os.path.dirname(output_path)
    os.makedirs(work_dir, exist_ok=True)

    audio_dur = get_duration(audio_path)
    if audio_dur <= 0:
        logger.error("Audio has zero duration, cannot composite")
        return False
    logger.info(f"Master audio duration: {audio_dur:.1f}s ({audio_dur / 60:.1f} min)")

    # Crossfade concat all slide clips
    bg_path = os.path.join(work_dir, "slides_concat.mp4")
    if not _concat_with_crossfades(slide_clip_paths, bg_path):
        logger.error("Crossfade concat failed")
        return False

    # Final pass: video + audio
    cmd = [
        "ffmpeg", "-y",
        "-i", bg_path,
        "-i", audio_path,
        "-map", "0:v",
        "-map", "1:a",
        "-t", str(audio_dur),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-shortest",
        output_path,
    ]
    success = _run_ffmpeg(cmd, timeout=900)
    if success:
        final_dur = get_duration(output_path)
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"Final video: {final_dur:.1f}s ({final_dur / 60:.1f} min), {size_mb:.1f} MB")
    return success


# ---------------------------------------------------------------------------
# Legacy composite (stock footage based — kept for fallback)
# ---------------------------------------------------------------------------

def _concat_clips(clip_paths: list[str], target_duration: float, output_path: str, work_dir: str) -> bool:
    """Concatenate and loop clips to fill target_duration (shuffled to avoid pattern)."""
    if not clip_paths:
        return False

    durations = [get_duration(p) for p in clip_paths]
    total = sum(durations)

    if total <= 0:
        logger.error("All clips have zero duration")
        return False

    # Shuffle clip order when looping to avoid visible repetition
    indexed = list(zip(clip_paths, durations))

    concat_file = os.path.join(work_dir, "concat.txt")
    accumulated = 0.0
    with open(concat_file, "w") as f:
        while accumulated < target_duration:
            random.shuffle(indexed)
            for path, dur in indexed:
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
        "-c:v", "libx264", "-preset", "medium",
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
    Composite a full YouTube video (legacy stock footage path):
    1. Concatenate background clips to match audio duration
    2. Mix in audio track
    """
    work_dir = os.path.dirname(output_path)
    os.makedirs(work_dir, exist_ok=True)

    audio_dur = get_duration(audio_path)
    if audio_dur <= 0:
        logger.error("Audio has zero duration, cannot composite")
        return False
    logger.info(f"Master audio duration: {audio_dur:.1f}s ({audio_dur / 60:.1f} min)")

    clip_paths = _download_clips(background_urls, work_dir)
    if not clip_paths:
        logger.error("No background clips downloaded")
        return False

    bg_full = os.path.join(work_dir, "bg_full.mp4")
    if not _concat_clips(clip_paths, audio_dur, bg_full, work_dir):
        logger.error("Background concatenation failed")
        return False

    # Single-pass: background + audio
    cmd = [
        "ffmpeg", "-y",
        "-i", bg_full,
        "-i", audio_path,
        "-map", "0:v",
        "-map", "1:a",
        "-t", str(audio_dur),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output_path,
    ]

    success = _run_ffmpeg(cmd, timeout=900)
    if success:
        final_dur = get_duration(output_path)
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"Final video: {final_dur:.1f}s ({final_dur / 60:.1f} min), {size_mb:.1f} MB")
    return success
