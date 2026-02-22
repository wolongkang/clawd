import logging
import os
import re
import json
import subprocess
import requests
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import XAI_API_KEY
from apis import fal_api, youtube_upload
from apis.haiku import _call_haiku

logger = logging.getLogger(__name__)

TMP_BASE = "/tmp/videobot/tweet"

# Grok client (xAI API — OpenAI-compatible, has native X/Twitter access)
grok_client = OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1") if XAI_API_KEY else None


def is_tweet_url(text: str) -> bool:
    """Check if text contains a tweet/X URL."""
    pattern = r'(https?://)?(www\.)?(twitter\.com|x\.com)/\w+/status/\d+'
    return bool(re.search(pattern, text.strip()))


def _get_work_dir(user_id: int) -> str:
    path = os.path.join(TMP_BASE, str(user_id))
    os.makedirs(path, exist_ok=True)
    return path


def _cleanup(work_dir: str, keep_final: str = None):
    try:
        for f in os.listdir(work_dir):
            fpath = os.path.join(work_dir, f)
            if keep_final and os.path.abspath(fpath) == os.path.abspath(keep_final):
                continue
            if os.path.isfile(fpath):
                os.remove(fpath)
        logger.info(f"Cleaned up {work_dir}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")


def _download(url: str, path: str) -> bool:
    try:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(resp.content)
        return True
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return False


async def _analyze_tweet_with_grok(tweet_text: str) -> str:
    """Use Grok (xAI) to analyze tweet and search X for related context.
    Grok has native real-time X/Twitter data access."""
    if not grok_client:
        logger.error("Grok client not available (no XAI_API_KEY)")
        return None

    try:
        prompt = f"""Analyze this tweet/post and search X (Twitter) for related context:

{tweet_text}

Provide a comprehensive analysis:
1. TOPIC: What is this tweet about? (1 sentence)
2. KEY POINTS: The main claims or ideas (3-5 bullet points)
3. X CONTEXT: What are people saying about this topic on X right now? Include related posts, replies, counter-arguments, trending takes
4. TRENDING ANGLE: What's the most engaging/viral angle for a short video about this?
5. VISUAL IDEAS: What kind of visual scenes would make this compelling as a 30-45 second animated video?

Be specific and detailed. This will be used to write a video screenplay."""

        response = grok_client.chat.completions.create(
            model="grok-3",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
        )
        analysis = response.choices[0].message.content
        logger.info(f"Grok analysis: {len(analysis)} chars")
        return analysis

    except Exception as e:
        logger.error(f"Grok analysis error: {e}")
        return None


async def _generate_scenes_from_tweet(tweet: str, grok_analysis: str, scene_count: int) -> list[dict]:
    """Use Haiku to generate scene prompts based on tweet + Grok's X context."""
    prompt = f"""You are creating a viral short-form animated video (TikTok/Reels/Shorts style) based on a tweet and its context from X.

ORIGINAL TWEET:
{tweet}

CONTEXT FROM X (related posts, opinions, trending takes):
{grok_analysis}

Generate exactly {scene_count} scenes that tell a compelling story about this topic. For each scene, provide:
1. "name" - short scene name (1-2 words)
2. "image_prompt" - Hyper-detailed prompt for 3D Pixar-style character image generation:
   - 3D Pixar-style anthropomorphic character with face embedded in surface
   - Large glossy Disney eyes with specular highlights, thick expressive eyebrows
   - NO arms NO legs
   - Character's appearance should match the tweet's topic/emotion
   - Specific texture, lighting, environment
   - 9:16 vertical, shallow DOF, centered
3. "animation_prompt" - Prompt for video animation with spoken dialogue:
   - Character speaks in FIRST PERSON, reacting to/discussing the tweet's topic
   - Include spoken dialogue in quotes (make it punchy, engaging, viral-worthy)
   - Describe visual TRANSFORMATION (something changes/happens)
   - Reference real points from the X context to make it feel current and informed
   - End with: Do not display any text, captions, subtitles, or words on screen
   - The voice will be generated natively from the dialogue
4. "duration" - "8s" for dialogue scenes, "4s" for quick transitions

Make it feel like a reaction/commentary video — opinionated, entertaining, shareable.

Return ONLY valid JSON array. No markdown, no explanation. Example format:
[
  {{
    "name": "intro",
    "image_prompt": "3D Pixar-style anthropomorphic...",
    "animation_prompt": "A shocked character speaks: \\"Did you see what just happened?!\\" As it speaks...",
    "duration": "8s"
  }}
]"""

    result = _call_haiku(prompt, max_tokens=3000)
    if not result:
        return None

    try:
        result = result.strip()
        if result.startswith("```"):
            result = result.split("```")[1]
            if result.startswith("json"):
                result = result[4:]
        scenes = json.loads(result)
        if isinstance(scenes, list) and len(scenes) > 0:
            logger.info(f"Generated {len(scenes)} tweet scene prompts")
            return scenes
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse tweet scene JSON: {e}\nRaw: {result[:500]}")

    return None


async def handle(query, context: ContextTypes.DEFAULT_TYPE, scene_count: int):
    """Handle tweet-to-video generation pipeline."""
    tweet_text = context.user_data.get("topic", "")
    user_id = query.from_user.id
    work_dir = _get_work_dir(user_id)

    # 1. Grok: analyze tweet + search X
    await query.edit_message_text(f"[1/5] Grok analyzing tweet + searching X...")
    grok_analysis = await _analyze_tweet_with_grok(tweet_text)
    if not grok_analysis:
        await query.edit_message_text("Failed to analyze tweet. Check XAI_API_KEY.")
        context.user_data["mode"] = None
        return

    await query.edit_message_text(f"[1/5] X context gathered!")

    # 2. Haiku: generate scene prompts from tweet + context
    await query.edit_message_text(f"[2/5] Writing {scene_count} scene screenplay...")
    scenes = await _generate_scenes_from_tweet(tweet_text, grok_analysis, scene_count)
    if not scenes:
        await query.edit_message_text("Failed to generate screenplay.")
        context.user_data["mode"] = None
        return

    await query.edit_message_text(
        f"[2/5] Got {len(scenes)} scenes: {', '.join(s.get('name', '?') for s in scenes)}"
    )

    # 3. Nano Banana Pro: generate character images
    await query.edit_message_text(f"[3/5] Generating {len(scenes)} character images...")
    image_urls = []
    ref_url = None

    for i, scene in enumerate(scenes):
        await query.edit_message_text(
            f"[3/5] Generating image {i+1}/{len(scenes)}: {scene.get('name', '')}..."
        )
        url = await fal_api.generate_image(scene["image_prompt"], ref_url)
        if not url:
            await query.edit_message_text(f"Image generation failed at scene {i+1}.")
            context.user_data["mode"] = None
            return
        image_urls.append(url)
        if i == 0:
            ref_url = url

    await query.edit_message_text(f"[3/5] All {len(image_urls)} images generated!")

    # 4. Veo 3.1: animate scenes
    await query.edit_message_text(f"[4/5] Animating {len(scenes)} scenes with Veo 3.1...")
    video_urls = []

    for i, scene in enumerate(scenes):
        dur = scene.get("duration", "8s")
        await query.edit_message_text(
            f"[4/5] Animating scene {i+1}/{len(scenes)}: {scene.get('name', '')} ({dur})..."
        )
        url = await fal_api.animate_scene(image_urls[i], scene["animation_prompt"], dur)
        if not url:
            await query.edit_message_text(f"Animation failed at scene {i+1}.")
            context.user_data["mode"] = None
            return
        video_urls.append(url)

    await query.edit_message_text(f"[4/5] All {len(video_urls)} animations complete!")

    # 5. FFmpeg: download, trim, assemble
    await query.edit_message_text("[5/5] Assembling final video...")

    clip_paths = []
    for i, url in enumerate(video_urls):
        path = os.path.join(work_dir, f"raw_{i:02d}.mp4")
        if _download(url, path):
            clip_paths.append(path)
        else:
            await query.edit_message_text(f"Failed to download clip {i+1}.")
            context.user_data["mode"] = None
            _cleanup(work_dir)
            return

    # Trim each clip (remove last second to avoid AI artifacts)
    trimmed_paths = []
    for i, path in enumerate(clip_paths):
        dur = scenes[i].get("duration", "8s")
        trim_seconds = int(dur.replace("s", "")) - 1
        trim_path = os.path.join(work_dir, f"trim_{i:02d}.mp4")
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-t", str(trim_seconds),
             "-c:v", "libx264", "-c:a", "aac", trim_path],
            capture_output=True, timeout=60,
        )
        if result.returncode == 0:
            trimmed_paths.append(trim_path)
        else:
            logger.error(f"Trim failed for clip {i}: {result.stderr.decode()[-300:]}")
            trimmed_paths.append(path)

    # Concatenate
    concat_file = os.path.join(work_dir, "concat.txt")
    with open(concat_file, "w") as f:
        for p in trimmed_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    output_path = os.path.join(work_dir, "final.mp4")
    result = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
         "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", output_path],
        capture_output=True, timeout=120,
    )

    if result.returncode != 0 or not os.path.exists(output_path):
        logger.error(f"Concat failed: {result.stderr.decode()[-300:]}")
        await query.edit_message_text("Video assembly failed.")
        context.user_data["mode"] = None
        _cleanup(work_dir)
        return

    file_size = os.path.getsize(output_path)
    size_mb = file_size / (1024 * 1024)
    await query.edit_message_text(f"Uploading {size_mb:.1f}MB video...")

    # Build caption from tweet (truncated)
    tweet_short = tweet_text[:100] + "..." if len(tweet_text) > 100 else tweet_text
    context.user_data["last_video_path"] = output_path
    context.user_data["last_video_topic"] = tweet_short

    chat_id = query.message.chat_id

    if file_size <= 50 * 1024 * 1024:
        with open(output_path, "rb") as f:
            await context.bot.send_video(
                chat_id=chat_id,
                video=f.read(),
                caption=f"Tweet Video — {tweet_short}",
            )
        await query.delete_message()
    else:
        await query.edit_message_text(
            f"Video is {size_mb:.0f}MB — exceeds Telegram's 50MB limit.\n"
            f"Saved on server: {output_path}"
        )

    # Clean up temp files (keep final for YouTube upload)
    _cleanup(work_dir, keep_final=output_path)

    # Offer YouTube upload
    if youtube_upload.is_available():
        keyboard = [
            [InlineKeyboardButton("Public", callback_data="ytup_public"),
             InlineKeyboardButton("Unlisted", callback_data="ytup_unlisted"),
             InlineKeyboardButton("Private", callback_data="ytup_private")],
            [InlineKeyboardButton("Skip", callback_data="ytup_skip")],
        ]
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Upload to YouTube?\n({size_mb:.0f}MB)",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    context.user_data["mode"] = None
