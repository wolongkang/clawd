import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes
from config import TELEGRAM_BOT_TOKEN
from commands.start import cmd_start, handle_menu
from commands import animated_video, youtube_video, tweet_video
from commands.tweet_video import is_tweet_url
from apis import youtube_upload

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    mode = context.user_data.get("mode")

    # Auto-detect tweet URLs — skip menu, go straight to scene count
    if not mode and is_tweet_url(text):
        context.user_data["mode"] = "tweet"
        context.user_data["topic"] = text
        keyboard = [
            [
                InlineKeyboardButton("3 scenes (~21s)", callback_data="tweet_3"),
                InlineKeyboardButton("4 scenes (~28s)", callback_data="tweet_4"),
            ],
            [
                InlineKeyboardButton("5 scenes (~35s)", callback_data="tweet_5"),
                InlineKeyboardButton("6 scenes (~42s)", callback_data="tweet_6"),
            ],
        ]
        await update.message.reply_text(
            "Tweet detected! How many scenes?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if not mode:
        await cmd_start(update, context)
        return

    context.user_data["topic"] = text

    if mode == "animated":
        keyboard = [
            [
                InlineKeyboardButton("3 scenes (~21s)", callback_data="anim_3"),
                InlineKeyboardButton("4 scenes (~28s)", callback_data="anim_4"),
            ],
            [
                InlineKeyboardButton("5 scenes (~35s)", callback_data="anim_5"),
                InlineKeyboardButton("6 scenes (~42s)", callback_data="anim_6"),
            ],
        ]
        await update.message.reply_text("How many scenes?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif mode == "tweet":
        keyboard = [
            [
                InlineKeyboardButton("3 scenes (~21s)", callback_data="tweet_3"),
                InlineKeyboardButton("4 scenes (~28s)", callback_data="tweet_4"),
            ],
            [
                InlineKeyboardButton("5 scenes (~35s)", callback_data="tweet_5"),
                InlineKeyboardButton("6 scenes (~42s)", callback_data="tweet_6"),
            ],
        ]
        await update.message.reply_text("How many scenes?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif mode == "youtube":
        keyboard = [
            [
                InlineKeyboardButton("5 min", callback_data="yt_5"),
                InlineKeyboardButton("10 min", callback_data="yt_10"),
            ],
            [
                InlineKeyboardButton("15 min", callback_data="yt_15"),
                InlineKeyboardButton("20 min", callback_data="yt_20"),
            ],
        ]
        await update.message.reply_text("Duration?", reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("anim_"):
        scene_count = int(data.split("_")[1])
        await animated_video.handle(query, context, scene_count)

    elif data.startswith("tweet_"):
        scene_count = int(data.split("_")[1])
        await tweet_video.handle(query, context, scene_count)

    elif data.startswith("yt_"):
        minutes = int(data.split("_")[1])
        await youtube_video.handle(query, context, minutes)

    elif data.startswith("ytup_"):
        await handle_youtube_upload(query, context)


async def handle_youtube_upload(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle YouTube upload button press."""
    action = query.data.replace("ytup_", "")

    if action == "skip":
        await query.edit_message_text("YouTube upload skipped.")
        # Clean up final video file
        video_path = context.user_data.get("last_video_path")
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
            except Exception:
                pass
        return

    video_path = context.user_data.get("last_video_path")
    topic = context.user_data.get("last_video_topic", "Video")

    if not video_path or not os.path.exists(video_path):
        await query.edit_message_text("Video file not found. Generate a video first.")
        return

    privacy = action  # "public", "unlisted", or "private"
    await query.edit_message_text(f"Uploading to YouTube ({privacy})...")

    # Build title and description
    title = topic[:100]
    description = (
        f"{topic}\n\n"
        f"Generated with OpenClaw Video Bot\n"
        f"#shorts #ai #generated"
    )

    # Use script as description if available (for long-form)
    script = context.user_data.get("last_video_script")
    if script:
        # Use first 200 words of script as description
        words = script.split()[:200]
        description = (
            f"{topic}\n\n"
            f"{' '.join(words)}...\n\n"
            f"Generated with OpenClaw Video Bot"
        )

    tags = [t.strip() for t in topic.split() if len(t.strip()) > 2][:10]

    result = await youtube_upload.upload_video(
        file_path=video_path,
        title=title,
        description=description,
        tags=tags,
        privacy=privacy,
    )

    # Clean up final video file after upload attempt
    if video_path and os.path.exists(video_path):
        try:
            os.remove(video_path)
        except Exception:
            pass

    if result:
        await query.edit_message_text(
            f"Uploaded to YouTube!\n"
            f"{result['url']}\n"
            f"Status: {result['privacy']}"
        )
    else:
        await query.edit_message_text("YouTube upload failed. Check logs.")


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_menu, pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(handle_button, pattern="^(anim_|tweet_|yt_|ytup_)"))
    logger.info("OpenClaw Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
