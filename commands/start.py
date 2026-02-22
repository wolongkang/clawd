from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("ANIMATED SHORT (Veo 3.1)", callback_data="menu_animated")],
        [InlineKeyboardButton("YOUTUBE VIDEO (long-form)", callback_data="menu_youtube")],
    ]

    await update.message.reply_text(
        "OpenClaw Video Bot\n\nChoose a mode:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    mode_map = {
        "menu_animated": "animated",
        "menu_youtube": "youtube",
    }

    mode = mode_map.get(query.data)
    if mode:
        context.user_data["mode"] = mode
        await query.edit_message_text("What topic?")
