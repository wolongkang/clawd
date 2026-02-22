import logging
import requests
from telegram import Update
from telegram.ext import ContextTypes
from apis import openai_api, kling

logger = logging.getLogger(__name__)


async def handle(query, context: ContextTypes.DEFAULT_TYPE, duration: int):
    topic = context.user_data.get("topic", "")

    status = await query.edit_message_text(text="Writing narrative...")
    narrative = await openai_api.generate_narrative_short(topic)
    if not narrative:
        await status.edit_text("Failed to generate narrative.")
        return

    await status.edit_text("Creating video...")
    task_id = await kling.create_video(narrative, duration)
    if not task_id:
        await status.edit_text("Failed to start video generation.")
        return

    await status.edit_text("Rendering video...")
    video_url = await kling.poll_video(task_id, status)

    if video_url:
        await status.edit_text("Downloading...")
        video = requests.get(video_url, timeout=60).content
        await query.message.reply_video(video=video, caption=f"{duration}s video ready!")
        await status.delete()
    else:
        await status.edit_text("Video generation failed.")

    context.user_data["mode"] = None
