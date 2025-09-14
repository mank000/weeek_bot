from telegram import Update
from telegram.ext import ContextTypes

from bot.utils.logger import logger


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update caused error {context.error}")
    if update and update.message:
        await update.message.reply_text(
            "An error occurred. Please try again later."
        )
