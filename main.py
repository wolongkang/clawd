import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes
from config import TELEGRAM_BOT_TOKEN
from commands.start import cmd_start, handle_menu
from commands import short_video, youtube_video

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")

    if not mode:
        await cmd_start(update, context)
        return

    context.user_data["topic"] = update.message.text

    if mode == "short":
        keyboard = [
            [InlineKeyboardButton("5s", callback_data="short_5")],
            [InlineKeyboardButton("10s", callback_data="short_10")],
        ]
        await update.message.reply_text("Duration?", reply_markup=InlineKeyboardMarkup(keyboard))

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

    if data.startswith("short_"):
        duration = int(data.split("_")[1])
        await short_video.handle(query, context, duration)

    elif data.startswith("yt_"):
        minutes = int(data.split("_")[1])
        await youtube_video.handle(query, context, minutes)


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_menu, pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(handle_button, pattern="^(short_|yt_)"))
    logger.info("OpenClaw Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
