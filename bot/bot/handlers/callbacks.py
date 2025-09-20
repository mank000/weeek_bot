from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.commands import remove_html_tags
from bot.utils import api, logger


async def show_task_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    task_id = query.data.replace("show_task_", "")
    tasks_state = context.user_data.get("tasks_state", {})

    task = tasks_state.get(int(task_id)) or tasks_state.get(task_id)
    if not task:
        await query.message.reply_text("⚠️ Задача не найдена.")
        return
    text = (
        f"📌 *{task['title']}*\n"
        f"📝 {remove_html_tags(task['description']) or '—'}\n"
        f"📂 Колонка: {task['boardColumn']}\n"
        f"⚡ Статус: {'Выполнена' if task['isCompleted'] else 'Активна'}\n"
        f"Ссылка: https://app.weeek.net/ws/{api.WORKSPACE_ID}/task/{task_id}\n"
    )

    await query.message.reply_text(text, parse_mode="Markdown")
