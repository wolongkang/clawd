from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("SHORT VIDEO (5-10s)", callback_data="menu_short")],
        [InlineKeyboardButton("YOUTUBE VIDEO (avatar+footage)", callback_data="menu_youtube")],
    ]

    await update.message.reply_text(
        "OpenClaw Video Bot\n\nChoose a mode:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    mode_map = {
        "menu_short": "short",
        "menu_youtube": "youtube",
    }

    mode = mode_map.get(query.data)
    if mode:
        context.user_data["mode"] = mode
        await query.edit_message_text("What topic?")
