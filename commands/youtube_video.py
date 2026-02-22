import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from apis import haiku, openai_api, pexels, tts, youtube_upload
from utils.video import composite_video

logger = logging.getLogger(__name__)


async def handle(query, context: ContextTypes.DEFAULT_TYPE, minutes: int):
    topic = context.user_data.get("topic", "")

    # 1. Script (Haiku only)
    await query.edit_message_text(text=f"[1/4] Writing {minutes}m script (Haiku)...")
    script = await haiku.generate_youtube_script(topic, minutes)
    if not script:
        await query.edit_message_text("Script generation failed.")
        return

    word_count = len(script.split())
    await query.edit_message_text(f"[1/4] Script ready: {word_count} words (~{word_count // 150}m)")

    # 2. Audio (ElevenLabs)
    await query.edit_message_text(f"[2/4] Generating audio (ElevenLabs)...")
    audio = await tts.generate_speech(script, target_minutes=minutes)
    if not audio:
        await query.edit_message_text("Audio generation failed.")
        return

    # Save audio to disk (needed for ffmpeg)
    audio_path = "/tmp/videobot/audio.mp3"
    os.makedirs("/tmp/videobot", exist_ok=True)
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
        return

    await query.edit_message_text(f"[3/4] Got {len(footage_urls)} background clips")

    # 4. Composite (footage + audio, no avatar)
    await query.edit_message_text("[4/4] Compositing video (this takes a while)...")

    output_path = "/tmp/videobot/final_video.mp4"
    success = composite_video(footage_urls, None, audio_path, output_path)

    if not success or not os.path.exists(output_path):
        await query.edit_message_text("Video composition failed.")
        context.user_data["mode"] = None
        return

    # Store video info for YouTube upload
    context.user_data["last_video_path"] = output_path
    context.user_data["last_video_topic"] = topic
    context.user_data["last_video_script"] = script

    file_size = os.path.getsize(output_path)
    size_mb = file_size / (1024 * 1024)

    # Send to Telegram first
    if file_size <= 50 * 1024 * 1024:
        await query.edit_message_text(f"Uploading {size_mb:.0f}MB to Telegram...")
        with open(output_path, "rb") as f:
            await query.message.reply_video(
                video=f.read(),
                caption=f"{minutes}m YouTube Video - {topic}",
            )
        await query.delete()
    else:
        await query.edit_message_text(
            f"Video is {size_mb:.0f}MB (exceeds Telegram 50MB limit).\n"
            f"Saved at: {output_path}"
        )

    # Offer YouTube upload if configured
    if youtube_upload.is_available():
        keyboard = [
            [
                InlineKeyboardButton("Upload to YouTube (private)", callback_data="ytup_private"),
                InlineKeyboardButton("Upload (unlisted)", callback_data="ytup_unlisted"),
            ],
            [InlineKeyboardButton("Skip YouTube upload", callback_data="ytup_skip")],
        ]
        await query.message.reply_text(
            f"Upload to YouTube?\n({size_mb:.0f}MB, {topic})",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await query.message.reply_text(
            "YouTube upload not configured. Run youtube_auth.py to set it up."
        )

    context.user_data["mode"] = None
