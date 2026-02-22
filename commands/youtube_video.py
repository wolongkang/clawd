import logging
import os
from telegram import Update
from telegram.ext import ContextTypes
from apis import openai_api, grok, runway, pexels, tts
from utils.video import composite_video

logger = logging.getLogger(__name__)


async def handle(query, context: ContextTypes.DEFAULT_TYPE, minutes: int, use_grok: bool = False):
    topic = context.user_data.get("topic", "")

    # 1. Script
    await query.edit_message_text(text="Writing script...")
    if use_grok and grok.is_available():
        script = await grok.generate_youtube_script(topic, minutes)
    else:
        script = await openai_api.generate_youtube_script(topic, minutes)
    if not script:
        await query.edit_message_text("Script generation failed.")
        return

    # 2. Audio
    await query.edit_message_text("Generating audio...")
    audio = await tts.generate_speech(script)
    if not audio:
        await query.edit_message_text("Audio generation failed.")
        return

    # 3. Avatar
    await query.edit_message_text("Creating avatar...")
    avatar_task = await runway.create_avatar(script)
    if not avatar_task:
        await query.edit_message_text("Avatar creation failed.")
        return

    await query.edit_message_text("Rendering avatar (this takes a few minutes)...")
    avatar_url = await runway.poll_avatar(avatar_task)
    if not avatar_url:
        await query.edit_message_text("Avatar rendering failed.")
        return

    # 4. Background footage
    await query.edit_message_text("Fetching background footage...")
    footage = await pexels.get_footage(topic, count=1)
    if not footage:
        await query.edit_message_text("Could not find background footage.")
        return

    # 5. Composite
    await query.edit_message_text("Compositing final video...")

    audio_path = "/tmp/audio.mp3"
    with open(audio_path, "wb") as f:
        f.write(audio)

    output_path = "/tmp/final_video.mp4"
    success = composite_video(footage[0], avatar_url, audio_path, output_path)

    if success and os.path.exists(output_path):
        await query.edit_message_text("Uploading...")
        with open(output_path, "rb") as f:
            await query.message.reply_video(
                video=f.read(),
                caption=f"{minutes}m YouTube Video - Ready to upload!",
            )
        await query.delete()
    else:
        await query.edit_message_text("Video composition failed.")

    context.user_data["mode"] = None
