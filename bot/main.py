from config.settings import TELEGRAM_TOKEN
from telegram import Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler

from bot.handlers.callbacks import show_task_callback
from bot.handlers.commands import (
    change_board,
    change_project,
    choose_sort_column,
    handle_pagination,
    handle_sorting,
    show_task,
    start_conv,
)
from bot.handlers.errors import error_handler
from bot.handlers.messages import handle_message
from bot.utils.logger import logger


def main():

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(start_conv)
    application.add_error_handler(error_handler)
    application.add_handler(
        CallbackQueryHandler(show_task_callback, pattern="^show_task_")
    )
    application.add_handler(
        CallbackQueryHandler(change_project, pattern="^change_project$")
    )
    application.add_handler(
        CallbackQueryHandler(change_board, pattern="^change_board$")
    )

    application.add_handler(start_conv)
    application.add_handler(
        CallbackQueryHandler(handle_sorting, pattern="^sort_")
    )
    application.add_handler(
        CallbackQueryHandler(show_task, pattern="^show_task_")
    )

    application.add_handler(
        CallbackQueryHandler(choose_sort_column, pattern="^column_"),
    )
    application.add_handler(
        CallbackQueryHandler(handle_pagination, pattern="^page_"),
    )

    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
