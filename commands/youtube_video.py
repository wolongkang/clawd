import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from apis import haiku, openai_api, pexels, tts, youtube_upload
from utils.video import composite_video

logger = logging.getLogger(__name__)

TMP_BASE = "/tmp/videobot/youtube"


def _get_work_dir(user_id: int) -> str:
    """Get a unique working directory per user to avoid file conflicts."""
    path = os.path.join(TMP_BASE, str(user_id))
    os.makedirs(path, exist_ok=True)
    return path


def _cleanup(work_dir: str, keep_final: str = None):
    """Clean up temp files after upload. Keep final video if YouTube upload pending."""
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


async def handle(query, context: ContextTypes.DEFAULT_TYPE, minutes: int):
    topic = context.user_data.get("topic", "")
    user_id = query.from_user.id
    work_dir = _get_work_dir(user_id)

    # 1. Script (Haiku only)
    await query.edit_message_text(text=f"[1/4] Writing {minutes}m script (Haiku)...")
    script = await haiku.generate_youtube_script(topic, minutes)
    if not script:
        await query.edit_message_text("Script generation failed.")
        context.user_data["mode"] = None
        return

    word_count = len(script.split())
    await query.edit_message_text(f"[1/4] Script ready: {word_count} words (~{word_count // 150}m)")

    # 2. Audio (ElevenLabs)
    await query.edit_message_text(f"[2/4] Generating audio (ElevenLabs)...")
    audio = await tts.generate_speech(script, target_minutes=minutes)
    if not audio:
        await query.edit_message_text("Audio generation failed.")
        context.user_data["mode"] = None
        return

    audio_path = os.path.join(work_dir, "audio.mp3")
    with open(audio_path, "wb") as f:
        f.write(audio)

    # 3. Background footage (keywords extracted via OpenAI — cheap for this)
    await query.edit_message_text("[3/4] Finding background footage...")
    keywords = await openai_api.extract_video_keywords(script, count=6)
    if not keywords:
        keywords = [topic]

    footage_urls = await pexels.get_footage_for_script(keywords, clips_per_keyword=2)
    if not footage_urls:
        footage_urls = await pexels.get_footage(topic, count=5)
    if not footage_urls:
        await query.edit_message_text("Could not find background footage.")
        context.user_data["mode"] = None
        _cleanup(work_dir)
        return

    await query.edit_message_text(f"[3/4] Got {len(footage_urls)} background clips")

    # 4. Composite (footage + audio, no avatar)
    await query.edit_message_text("[4/4] Compositing video (this takes a while)...")

    output_path = os.path.join(work_dir, "final_video.mp4")
    success = composite_video(footage_urls, None, audio_path, output_path)

    if not success or not os.path.exists(output_path):
        await query.edit_message_text("Video composition failed.")
        context.user_data["mode"] = None
        _cleanup(work_dir)
        return

    # Store video info for YouTube upload
    context.user_data["last_video_path"] = output_path
    context.user_data["last_video_topic"] = topic
    context.user_data["last_video_script"] = script

    file_size = os.path.getsize(output_path)
    size_mb = file_size / (1024 * 1024)

    chat_id = query.message.chat_id

    # Send to Telegram first
    if file_size <= 50 * 1024 * 1024:
        await query.edit_message_text(f"Uploading {size_mb:.0f}MB to Telegram...")
        with open(output_path, "rb") as f:
            await context.bot.send_video(
                chat_id=chat_id,
                video=f.read(),
                caption=f"{minutes}m YouTube Video - {topic}",
            )
        await query.delete()
    else:
        await query.edit_message_text(
            f"Video is {size_mb:.0f}MB (exceeds Telegram 50MB limit).\n"
            f"Saved at: {output_path}"
        )

    # Clean up temp files (keep final for YouTube upload)
    _cleanup(work_dir, keep_final=output_path)

    # Offer YouTube upload if configured
    if youtube_upload.is_available():
        keyboard = [
            [InlineKeyboardButton("Public", callback_data="ytup_public"),
             InlineKeyboardButton("Unlisted", callback_data="ytup_unlisted"),
             InlineKeyboardButton("Private", callback_data="ytup_private")],
            [InlineKeyboardButton("Skip", callback_data="ytup_skip")],
        ]
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Upload to YouTube?\n({size_mb:.0f}MB, {topic})",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="YouTube upload not configured. Run youtube_auth.py to set it up.",
        )

    context.user_data["mode"] = None
