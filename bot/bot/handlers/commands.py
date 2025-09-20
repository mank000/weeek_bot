import asyncio
import re
from datetime import datetime

import pytz
import requests
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.utils import api, logger

vladivostok_tz = pytz.timezone("Asia/Vladivostok")

DJANGO_API_URL = "http://backend:8000/"

(
    CHOOSING_PROJECT,
    CHOOSING_BOARD,
    CHOOSING_SORT_COLUMN,
    CHOOSING_COLUMN,
    ENTER_TITLE,
    ENTER_DESCRIPTION,
    CHOOSING_ASSIGNEE,
    ENTER_DUE_DATE,
    CHOOSING_TYPE,
) = range(9)


def remove_html_tags(text):
    """Удаляет все HTML-теги из текста"""
    if text is None:
        return "Без описания"
    clean = re.compile("<.*?>")
    return re.sub(clean, "", str(text))


async def stop_polling(context: ContextTypes.DEFAULT_TYPE):
    """Останавливаем фоновую задачу, если есть."""
    task: asyncio.Task = context.user_data.get("poll_task")
    if task and not task.done():
        logger.logger.info("Stopping existing poll task")
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        context.user_data["poll_task"] = None
    else:
        logger.logger.info("No active poll task to stop")


async def show_projects_page(
    update: Update, context: ContextTypes.DEFAULT_TYPE, page=1, query=None
):
    project_data = context.user_data.get("projects", [])
    per_page = 5
    total = len(project_data)
    start = (page - 1) * per_page
    end = min(start + per_page, total)
    current = project_data[start:end]

    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"select_proj_{pid}")]
        for name, pid in current
    ]

    pagination_row = []
    if page > 1:
        pagination_row.append(
            InlineKeyboardButton(
                "⬅️ Назад", callback_data=f"page_proj_{page-1}"
            )
        )
    if end < total:
        pagination_row.append(
            InlineKeyboardButton(
                "➡️ Далее", callback_data=f"page_proj_{page+1}"
            )
        )

    if pagination_row:
        keyboard.append(pagination_row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "Выберите проект:"

    if query:
        await query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)


async def show_boards_page(
    update: Update, context: ContextTypes.DEFAULT_TYPE, page=1, query=None
):
    boards_data = context.user_data.get("boards", [])
    per_page = 5
    total = len(boards_data)
    start = (page - 1) * per_page
    end = min(start + per_page, total)
    current = boards_data[start:end]

    keyboard = [
        [
            InlineKeyboardButton(
                board.get("name", "Unnamed"),
                callback_data=f"select_board_{board.get('id')}",
            )
        ]
        for board in current
    ]

    pagination_row = []
    if page > 1:
        pagination_row.append(
            InlineKeyboardButton(
                "⬅️ Назад", callback_data=f"page_board_{page-1}"
            )
        )
    if end < total:
        pagination_row.append(
            InlineKeyboardButton(
                "➡️ Далее", callback_data=f"page_board_{page+1}"
            )
        )

    if pagination_row:
        keyboard.append(pagination_row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "Выберите доску:"

    if query:
        await query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)


async def change_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stop_polling(context)
    context.user_data.pop("selected_project", None)
    context.user_data.pop("selected_board", None)

    projects_response = api.get_projects()
    if not projects_response or "projects" not in projects_response:
        await update.message.reply_text(
            "Не удалось загрузить список проектов."
        )
        return ConversationHandler.END

    projects: list = projects_response["projects"]
    project_data = [
        (p.get("name"), p.get("id")) for p in projects if "name" in p
    ]

    if not project_data:
        await update.message.reply_text("Проекты не найдены.")
        return ConversationHandler.END

    context.user_data["projects"] = project_data
    await show_projects_page(update, context)
    return CHOOSING_PROJECT


async def change_board(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stop_polling(context)
    await update.message.reply_text("🔄 Вы решили поменять доску.")

    project = context.user_data.get("selected_project")
    if not project:
        await update.message.reply_text("Сначала выберите проект.")
        await start(update, context)
        return CHOOSING_PROJECT

    project_id = project["id"]
    boards_response = api.get_boards(project_id=project_id)

    if boards_response.get("success") and "boards" in boards_response:
        boards_data = boards_response["boards"]
        context.user_data["boards"] = boards_data
        await show_boards_page(update, context)
        return CHOOSING_BOARD
    else:
        await update.message.reply_text("Ошибка при получении списка досок.")
        return ConversationHandler.END


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    projects_response = api.get_projects()
    if not projects_response or "projects" not in projects_response:
        await update.message.reply_text(
            "Не удалось загрузить список проектов."
        )
        return ConversationHandler.END

    projects: list = projects_response["projects"]
    project_data = [
        (p.get("name"), p.get("id")) for p in projects if "name" in p
    ]

    if not project_data:
        await update.message.reply_text("Проекты не найдены.")
        return ConversationHandler.END

    context.user_data["projects"] = project_data
    await show_projects_page(update, context)
    return CHOOSING_PROJECT


async def handle_project_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    pid = query.data.replace("select_proj_", "")
    projects = context.user_data.get("projects", [])
    name = next((n for n, p in projects if str(p) == pid), None)

    if not name:
        await query.message.reply_text("Проект не найден.")
        return CHOOSING_PROJECT

    context.user_data["selected_project"] = {
        "name": name,
        "id": pid,
    }

    boards_response = api.get_boards(project_id=pid)

    if boards_response.get("success") and "boards" in boards_response:
        boards_data = boards_response["boards"]
        context.user_data["boards"] = boards_data
        await show_boards_page(update, context, query=query)
        return CHOOSING_BOARD
    else:
        error_message = boards_response.get("message", "Неизвестная ошибка")
        await query.message.reply_text(
            f"Ошибка при получении списка досок: {error_message}"
        )
        return ConversationHandler.END


async def handle_project_pagination(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    page = int(query.data.replace("page_proj_", ""))
    await show_projects_page(update, context, page=page, query=query)
    return CHOOSING_PROJECT


async def handle_board_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    bid = query.data.replace("select_board_", "")
    boards = context.user_data.get("boards", [])
    name = next(
        (b.get("name") for b in boards if str(b.get("id")) == bid), None
    )

    if not name:
        await query.message.reply_text("Доска не найдена.")
        return CHOOSING_BOARD

    context.user_data["selected_board"] = {"name": name, "id": bid}
    project_id = context.user_data["selected_project"]["id"]
    chat_id = update.effective_chat.id

    # Останавливаем старый polling
    await stop_polling(context)

    # Кнопки под клавиатурой
    keyboard = ReplyKeyboardMarkup(
        [
            ["🔄 Поменять проект", "🔄 Поменять доску"],
            ["Добавить задачу", "📋 Показать задачи"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

    await query.edit_message_text(
        f"✅ Вы выбрали доску: {name} (ID: {bid})",
    )
    await query.message.reply_text("Выберите действие:", reply_markup=keyboard)

    # Запускаем новую фоновую задачу
    task = context.application.create_task(
        poll_board_updates(chat_id, project_id, bid, context)
    )
    context.user_data["poll_task"] = task

    await query.message.reply_text(f"Запускаем таск для доски {bid}...")
    return ConversationHandler.END


async def handle_board_pagination(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    page = int(query.data.replace("page_board_", ""))
    await show_boards_page(update, context, page=page, query=query)
    return CHOOSING_BOARD


async def choose_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    project_name = update.message.text
    projects = context.user_data.get("projects", [])

    project_id = None
    for name, pid in projects:
        if name == project_name:
            project_id = pid
            break

    if project_id is None:
        await update.message.reply_text(
            "Проект не найден. Попробуйте еще раз."
        )
        return CHOOSING_PROJECT

    context.user_data["selected_project"] = {
        "name": project_name,
        "id": project_id,
    }
    logger.logger.info(project_id)
    boards_response = api.get_boards(project_id=project_id)

    if boards_response.get("success") and "boards" in boards_response:
        boards_data = boards_response["boards"]
        context.user_data["boards"] = boards_data

        board_names = [
            str(board.get("name", "Unnamed")) for board in boards_data
        ]

        keyboard = [[KeyboardButton(name)] for name in board_names]

        reply_markup = ReplyKeyboardMarkup(
            keyboard, one_time_keyboard=True, resize_keyboard=True
        )

        await update.message.reply_text(
            f"Вы выбрали проект: {project_name}\nТеперь выберите доску:",
            reply_markup=reply_markup,
        )
    else:
        error_message = boards_response.get("message", "Неизвестная ошибка")
        await update.message.reply_text(
            f"Ошибка при получении списка досок: {error_message}"
        )
        return ConversationHandler.END

    return CHOOSING_BOARD


async def poll_board_updates(chat_id, project_id, board_id, context):
    """Фоновая задача: отслеживаем новые задачи и изменения с кнопкой 'Посмотреть полностью'."""
    tasks_state = {}  # task_id -> snapshot
    column_names = {}  # id -> название колонки

    # Загружаем список пользователей для маппинга ID к именам
    assignees_response = api.get_assignees(board_id)
    id_to_name = {}
    if assignees_response.get("success") and "members" in assignees_response:
        id_to_name = {
            member[
                "id"
            ]: f"{member.get('firstName', '')} {member.get('lastName', '')}".strip()
            for member in assignees_response["members"]
        }

    # Инициализация: загружаем текущее состояние без уведомлений
    try:
        columns_response = api.get_boardColumn_list(board_id)
        if (
            columns_response.get("success")
            and "boardColumns" in columns_response
        ):
            column_names = {
                col["id"]: col["name"]
                for col in columns_response["boardColumns"]
            }

        response = api.get_tasks(projectId=project_id, boardId=board_id)
        if response.get("success") and "tasks" in response:
            tasks = response["tasks"]
            now = datetime.now(vladivostok_tz)
            for task in tasks:
                task_id = task["id"]
                col_id = task.get("boardColumnId")
                col_name = column_names.get(col_id, f"Колонка {col_id}")
                assignees_ids = task.get("assignees", [])
                assignees_names = (
                    ", ".join(
                        id_to_name.get(aid, str(aid)) for aid in assignees_ids
                    )
                    or "Не назначен"
                )
                snapshot = {
                    "title": task.get("title"),
                    "description": task.get("description"),
                    "boardColumn": col_name,
                    "isCompleted": task.get("isCompleted"),
                    "isDeleted": task.get("isDeleted"),
                    "assignee": assignees_names,
                    "assignees_ids": assignees_ids,  # Храним IDs для сравнения
                    "column_enter_time": now,
                }
                tasks_state[task_id] = snapshot
            context.user_data["tasks_state"] = tasks_state
            logger.logger.info(
                "Initialized tasks_state with current tasks without notifications."
            )
    except Exception as e:
        logger.logger.error(f"Initialization error in poll_board_updates: {e}")
        await context.bot.send_message(
            chat_id=chat_id, text=f"Ошибка инициализации: {e}"
        )
        return

    while True:
        try:
            columns_response = api.get_boardColumn_list(board_id)
            if (
                columns_response.get("success")
                and "boardColumns" in columns_response
            ):
                column_names = {
                    col["id"]: col["name"]
                    for col in columns_response["boardColumns"]
                }

            response = api.get_tasks(projectId=project_id, boardId=board_id)
            if response.get("success") and "tasks" in response:
                tasks = response["tasks"]
                current_ids = set()

                for task in tasks:
                    task_id = task["id"]
                    current_ids.add(task_id)

                    col_id = task.get("boardColumnId")
                    col_name = column_names.get(col_id, f"Колонка {col_id}")
                    assignees_ids = task.get("assignees", [])
                    assignees_names = (
                        ", ".join(
                            id_to_name.get(aid, str(aid))
                            for aid in assignees_ids
                        )
                        or "Не назначен"
                    )

                    # Создаем базовый snapshot без column_enter_time
                    temp_snapshot = {
                        "title": task.get("title"),
                        "description": task.get("description"),
                        "boardColumn": col_name,
                        "isCompleted": task.get("isCompleted"),
                        "isDeleted": task.get("isDeleted"),
                        "assignee": assignees_names,
                        "assignees_ids": assignees_ids,
                    }

                    # Создаём inline-кнопку для просмотра полной информации
                    keyboard = InlineKeyboardMarkup.from_button(
                        InlineKeyboardButton(
                            "Посмотреть полностью",
                            callback_data=f"show_task_{task_id}",
                        )
                    )

                    if task_id not in tasks_state:
                        # Новая задача
                        now = datetime.now(vladivostok_tz)
                        snapshot = {**temp_snapshot, "column_enter_time": now}
                        tasks_state[task_id] = snapshot
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"🆕 Новая задача: {snapshot['title']}\nКолонка: {snapshot['boardColumn']}, "
                            f"Статус: {'Выполнена' if snapshot['isCompleted'] else 'Активна'}",
                            reply_markup=keyboard,
                        )
                    else:
                        old = tasks_state[task_id]
                        # Копируем старое время входа в колонку
                        snapshot = {
                            **temp_snapshot,
                            "column_enter_time": old["column_enter_time"],
                        }
                        changes = []
                        if old["title"] != snapshot["title"]:
                            changes.append(
                                f"✏️ Название: {old['title']} → {snapshot['title']}"
                            )
                        if old["assignees_ids"] != snapshot["assignees_ids"]:
                            changes.append(
                                f"👤 Исполнитель: {old['assignee']} → {snapshot['assignee']}"
                            )
                        if old["boardColumn"] != snapshot["boardColumn"]:
                            now = datetime.now(vladivostok_tz)
                            logger.logger.info(old["column_enter_time"])
                            time_spent = (
                                now - old["column_enter_time"]
                            ).total_seconds()
                            changes.append(
                                f"📂 Колонка: {old['boardColumn']} → {snapshot['boardColumn']}"
                            )
                            # Отправка на бэкенд для каждого исполнителя
                            if old["assignees_ids"]:
                                for aid in old["assignees_ids"]:
                                    user = aid
                                    user_name = id_to_name.get(aid, str(aid))
                                    try:
                                        backend_response = requests.post(
                                            f"{DJANGO_API_URL}log_move/",
                                            json={
                                                "task_title": snapshot[
                                                    "title"
                                                ],
                                                "task_id": task_id,
                                                "from_column": old[
                                                    "boardColumn"
                                                ],
                                                "to_column": snapshot[
                                                    "boardColumn"
                                                ],
                                                "user_name": user_name,
                                                "move_time": now.isoformat(),
                                                "time_spent": time_spent,
                                                "board_name": context.user_data[
                                                    "selected_board"
                                                ][
                                                    "name"
                                                ],
                                            },
                                        )
                                        if backend_response.status_code != 201:
                                            logger.logger.error(
                                                f"Ошибка отправки на бэкенд: {backend_response.text}"
                                            )
                                    except Exception as req_err:
                                        logger.logger.error(
                                            f"Ошибка requests: {req_err}"
                                        )
                            else:
                                # Если нет исполнителей
                                try:
                                    backend_response = requests.post(
                                        f"{DJANGO_API_URL}log_move/",
                                        json={
                                            "task_title": snapshot["title"],
                                            "task_id": task_id,
                                            "from_column": old["boardColumn"],
                                            "to_column": snapshot[
                                                "boardColumn"
                                            ],
                                            "user_name": "Не назначен",
                                            "move_time": now.isoformat(),
                                            "time_spent": time_spent,
                                            "board_name": context.user_data[
                                                "selected_board"
                                            ]["name"],
                                        },
                                    )
                                    if backend_response.status_code != 200:
                                        logger.logger.error(
                                            f"Ошибка отправки на бэкенд: {backend_response.text}"
                                        )
                                except Exception as req_err:
                                    logger.logger.error(
                                        f"Ошибка requests: {req_err}"
                                    )
                            # Обновляем время входа в новую колонку
                            snapshot["column_enter_time"] = now
                        if old["isCompleted"] != snapshot["isCompleted"]:
                            changes.append(
                                f"⚡ Статус: {'Выполнена' if old['isCompleted'] else 'Активна'} → "
                                f"{'Выполнена' if snapshot['isCompleted'] else 'Активна'}"
                            )
                        if (
                            old["isDeleted"] != snapshot["isDeleted"]
                            and snapshot["isDeleted"]
                        ):
                            changes.append("❌ Задача удалена")

                        if changes:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=f"🔔 Обновление задачи {snapshot['title']}:\n"
                                + "\n".join(changes),
                                reply_markup=keyboard,
                            )
                        tasks_state[task_id] = snapshot

                context.user_data["tasks_state"] = tasks_state

                removed_ids = set(tasks_state.keys()) - current_ids
                for rid in removed_ids:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ Задача {tasks_state[rid]['title']} удалена или скрыта",
                    )
                    del tasks_state[rid]

            await asyncio.sleep(1)

        except Exception as e:
            logger.logger.error(f"Ошибка в poll_board_updates: {e}")
            await context.bot.send_message(
                chat_id=chat_id, text=f"Ошибка при получении задач: {e}"
            )
            break


async def choose_board(update: Update, context: ContextTypes.DEFAULT_TYPE):
    board_name = update.message.text
    boards = context.user_data.get("boards", [])
    logger.logger.info(f"choose_board called with board_name: {board_name}")

    board_id = None
    for board in boards:
        if board.get("name") == board_name:
            board_id = board.get("id")
            break

    if board_id is None:
        await update.message.reply_text(
            "Доска не найдена. Попробуйте еще раз."
        )
        return CHOOSING_BOARD

    context.user_data["selected_board"] = {"name": board_name, "id": board_id}
    project_id = context.user_data["selected_project"]["id"]
    chat_id = update.effective_chat.id
    logger.logger.info(
        f"Selected board: {board_name} (ID: {board_id}), chat_id: {chat_id}"
    )

    # Останавливаем старый polling
    await stop_polling(context)

    # Кнопки под клавиатурой
    keyboard = ReplyKeyboardMarkup(
        [
            ["🔄 Поменять проект", "🔄 Поменять доску"],
            ["Добавить задачу", "📋 Показать задачи"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

    await update.message.reply_text(
        f"✅ Вы выбрали доску: {board_name} (ID: {board_id})",
        reply_markup=keyboard,
    )

    # Запускаем новую фоновую задачу
    task = context.application.create_task(
        poll_board_updates(chat_id, project_id, board_id, context)
    )
    context.user_data["poll_task"] = task
    logger.logger.info(f"Started poll task for board_id: {board_id}")

    await update.message.reply_text(f"Запускаем таск для доски {board_id}...")
    return ConversationHandler.END


async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Опционально: остановить polling, если создание задачи несовместимо с ним
    # await stop_polling(context)

    project = context.user_data.get("selected_project")
    board = context.user_data.get("selected_board")
    if not project or not board:
        await update.message.reply_text("Сначала выберите проект и доску.")
        await start(update, context)
        return CHOOSING_PROJECT

    board_id = board["id"]
    columns_response = api.get_boardColumn_list(board_id)

    if columns_response.get("success") and "boardColumns" in columns_response:
        columns_data = columns_response["boardColumns"]
        context.user_data["columns"] = columns_data

        column_names = [
            str(column.get("name", "Unnamed")) for column in columns_data
        ]
        if not column_names:
            await update.message.reply_text(
                "Колонки не найдены для этой доски."
            )
            return ConversationHandler.END

        keyboard = [[KeyboardButton(name)] for name in column_names]

        reply_markup = ReplyKeyboardMarkup(
            keyboard, one_time_keyboard=True, resize_keyboard=True
        )

        await update.message.reply_text(
            f"Выберите колонку для новой задачи в доске {board['name']}:",
            reply_markup=reply_markup,
        )
        return CHOOSING_COLUMN
    else:
        await update.message.reply_text("Ошибка при получении списка колонок.")
        return ConversationHandler.END


async def choose_column(update: Update, context: ContextTypes.DEFAULT_TYPE):
    column_name = update.message.text
    columns = context.user_data.get("columns", [])

    column_id = None
    for column in columns:
        if column.get("name") == column_name:
            column_id = column.get("id")
            break

    if column_id is None:
        await update.message.reply_text(
            "Колонка не найдена. Попробуйте еще раз."
        )
        return CHOOSING_COLUMN

    context.user_data["selected_column"] = {
        "name": column_name,
        "id": column_id,
    }

    # Убираем клавиатуру для ввода текста
    reply_markup = ReplyKeyboardMarkup(
        [], resize_keyboard=True
    )  # Пустая клавиатура

    await update.message.reply_text(
        f"Вы выбрали колонку: {column_name}\nВведите заголовок задачи:",
        reply_markup=reply_markup,
    )
    return ENTER_TITLE


async def enter_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text(
            "Заголовок не может быть пустым. Попробуйте еще раз."
        )
        return ENTER_TITLE

    context.user_data["task_title"] = title

    await update.message.reply_text(
        "Введите описание задачи (или отправьте '.' для пустого описания):"
    )
    return ENTER_DESCRIPTION


async def enter_description(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    description = update.message.text.strip()
    if description == ".":
        description = ""

    context.user_data["task_description"] = description

    project_id = context.user_data["selected_project"]["id"]
    board_id = context.user_data["selected_board"]["id"]
    column_id = context.user_data["selected_column"]["id"]
    title = context.user_data["task_title"]

    # Здесь вставьте ваш POST-запрос для создания задачи
    create_response = api.create_task(
        project_id=project_id,
        column_id=column_id,
        title=title,
        description=description,
    )
    logger.logger.info(create_response)
    if create_response.get("success"):
        await update.message.reply_text(f"Задача '{title}' успешно создана!")
    else:
        await update.message.reply_text(
            f"Ошибка при создании задачи: {create_response.get('message', 'Неизвестная ошибка')}"
        )

    # Очистка временных данных
    context.user_data.pop("task_title", None)
    context.user_data.pop("task_description", None)
    context.user_data.pop("selected_column", None)
    context.user_data.pop("columns", None)

    # Возвращаем persistent клавиатуру с кнопками
    keyboard = ReplyKeyboardMarkup(
        [
            ["🔄 Поменять проект", "🔄 Поменять доску"],
            ["Добавить задачу", "📋 Показать задачи"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
    await update.message.reply_text("Диалог завершен.", reply_markup=keyboard)

    return ConversationHandler.END


async def show_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    task_id = query.data.replace("show_task_", "")
    project_id = context.user_data["selected_project"]["id"]
    board_id = context.user_data["selected_board"]["id"]

    # Загружаем список пользователей для маппинга ID к именам
    assignees_response = api.get_assignees(board_id)
    id_to_name = {}
    if assignees_response.get("success") and "members" in assignees_response:
        id_to_name = {
            member[
                "id"
            ]: f"{member.get('firstName', '')} {member.get('lastName', '')}".strip()
            for member in assignees_response["members"]
        }

    # Получаем информацию о задаче
    task_response = api.get_task(
        task_id
    )  # Предполагается, что есть метод get_task
    if not task_response.get("success") or "task" not in task_response:
        await query.message.reply_text("Ошибка при получении задачи.")
        return

    task = task_response["task"]
    col_id = task.get("boardColumnId")
    columns_response = api.get_boardColumn_list(board_id)
    column_names = {
        col["id"]: col["name"]
        for col in columns_response.get("boardColumns", [])
    }
    col_name = column_names.get(col_id, f"Колонка {col_id}")
    assignees_ids = task.get("assignees", [])
    assignees_names = (
        ", ".join(id_to_name.get(aid, str(aid)) for aid in assignees_ids)
        or "Не назначен"
    )

    message = (
        f"📌 {task.get('title', 'Без названия')}\n"
        f"Описание: {remove_html_tags(task.get('description', 'Без описания'))}\n"
        f"Колонка: {col_name}\n"
        f"Исполнитель: {assignees_names}\n"
        f"Дедлайн: {task.get('dueDate', 'Без дедлайна')}\n"
        f"Тип: {task.get('type', 'Не указан')}\n"
        f"Статус: {'Выполнена' if task.get('isCompleted') else 'Активна'}\n"
        f"Ссылка: https://app.weeek.net/ws/{api.WORKSPACE_ID}/task/{task.get('id', 0)}\n"
    )

    await query.message.reply_text(message)


async def display_tasks(
    update: Update, context: ContextTypes.DEFAULT_TYPE, query=None
):
    if query:
        reply_func = query.message.reply_text
    else:
        reply_func = update.message.reply_text

    project_id = context.user_data["selected_project"]["id"]
    board_id = context.user_data["selected_board"]["id"]
    selected_column = context.user_data.get("selected_sort_column")
    sort_field = context.user_data.get("sort_field")
    filter_field = context.user_data.get("filter_field")
    filter_value = context.user_data.get("filter_value")

    # Загружаем список пользователей для маппинга ID к именам
    assignees_response = api.get_assignees(board_id)
    id_to_name = {}
    if assignees_response.get("success") and "members" in assignees_response:
        id_to_name = {
            member[
                "id"
            ]: f"{member.get('firstName', '')} {member.get('lastName', '')}".strip()
            for member in assignees_response["members"]
        }

    # Получаем список колонок для названий
    try:
        columns_response = api.get_boardColumn_list(board_id)
        column_names = {}
        if (
            columns_response.get("success")
            and "boardColumns" in columns_response
        ):
            column_names = {
                col["id"]: col["name"]
                for col in columns_response["boardColumns"]
            }
        else:
            await reply_func("Ошибка при получении списка колонок.")
            return ConversationHandler.END
    except Exception as e:
        logger.logger.error(f"Ошибка при получении колонок: {e}")
        await reply_func("Ошибка при получении списка колонок.")
        return ConversationHandler.END

    # Получаем задачи
    page = context.user_data.get("page", 1)
    per_page = 5  # сколько задач показывать на одной странице
    offset = (page - 1) * per_page
    try:
        response = api.get_tasks(
            projectId=project_id,
            boardId=board_id,
            perPage=per_page,
            offset=offset,
        )

        if not response.get("success") or "tasks" not in response:
            await reply_func("Ошибка при получении задач.")
            return ConversationHandler.END
    except Exception as e:
        logger.logger.error(f"Ошибка при получении задач: {e}")
        await reply_func("Ошибка при получении задач.")
        return ConversationHandler.END

    tasks = response["tasks"]
    # Фильтруем по колонке, если указана
    if selected_column:
        tasks = [
            task
            for task in tasks
            if task.get("boardColumnId") == selected_column["id"]
        ]

    # Фильтруем по фильтру, если указан
    if filter_value is not None and filter_field:
        tasks = [
            task
            for task in tasks
            if filter_value in task.get(filter_field, [])
        ]

    # Сортировка
    reverse = sort_field == "createdAt"
    tasks.sort(key=lambda x: x.get(sort_field, "") or "", reverse=reverse)

    if not tasks:
        await reply_func("Задачи не найдены.")
    else:
        for task in tasks:
            col_id = task.get("boardColumnId")
            col_name = column_names.get(col_id, f"Колонка {col_id}")
            title = task.get("title", "Без названия")
            assignees_ids = task.get("assignees", [])
            assignee = (
                ", ".join(
                    id_to_name.get(aid, str(aid)) for aid in assignees_ids
                )
                or "Не назначен"
            )
            due_date = task.get("dueDate", "Без дедлайна")
            task_type = task.get("type", "Не указан")
            link = task.get("id", "0")
            status = "Выполнена" if task.get("isCompleted") else "Активна"

            message = (
                f"📌 {title}\n"
                f"Колонка: {col_name}\n"
                f"Исполнитель: {assignee}\n"
                f"Дедлайн: {due_date}\n"
                f"Тип: {task_type}\n"
                f"Статус: {status}\n"
                f"Ссылка: https://app.weeek.net/ws/{api.WORKSPACE_ID}/task/{link}\n"
                f"---\n"
            )

            keyboard = InlineKeyboardMarkup.from_button(
                InlineKeyboardButton(
                    "Посмотреть полностью",
                    callback_data=f"show_task_{task['id']}",
                )
            )

            await reply_func(message, reply_markup=keyboard)

    # Очистка
    context.user_data.pop("sort_field", None)
    context.user_data.pop("filter_field", None)
    context.user_data.pop("filter_value", None)
    context.user_data.pop("selected_sort_column", None)

    # Возвращаем persistent клавиатуру
    # Пагинация
    pagination_buttons = []
    if page > 1:
        pagination_buttons.append(
            InlineKeyboardButton("⬅️ Назад", callback_data=f"page_{page-1}")
        )
    if len(tasks) == per_page:  # значит, может быть следующая страница
        pagination_buttons.append(
            InlineKeyboardButton("➡️ Далее", callback_data=f"page_{page+1}")
        )

    if pagination_buttons:
        await reply_func(
            f"Страница {page}",
            reply_markup=InlineKeyboardMarkup([pagination_buttons]),
        )

    keyboard = ReplyKeyboardMarkup(
        [
            ["🔄 Поменять проект", "🔄 Поменять доску"],
            ["Добавить задачу", "📋 Показать задачи"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
    await reply_func("Выберите действие:", reply_markup=keyboard)
    return ConversationHandler.END


async def handle_pagination(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    page = int(query.data.replace("page_", ""))
    context.user_data["page"] = page
    return await display_tasks(update, context, query=query)


async def handle_sorting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.logger.info(
        f"handle_sorting called with data: {query.data}"
    )  # Отладка

    sort_type = query.data
    board_id = context.user_data["selected_board"]["id"]

    sort_field_map = {
        "sort_date": "createdAt",
        "sort_assignee": "assignees",
        "sort_dueDate": "dueDate",
        "sort_type": "type",
    }
    context.user_data["sort_field"] = sort_field_map[sort_type]
    if sort_type == "sort_date":
        context.user_data["filter_field"] = None
        context.user_data["filter_value"] = None
        return await display_tasks(update, context, query=query)
    else:
        context.user_data["filter_field"] = sort_field_map[sort_type]

    if sort_type == "sort_assignee":
        # Получаем список исполнителей
        assignees_response = api.get_assignees(board_id)
        if (
            assignees_response.get("success")
            and "members" in assignees_response
        ):
            assignees = assignees_response["members"]
            id_to_name = {
                assignee[
                    "id"
                ]: f"{assignee.get('firstName','')} {assignee.get('lastName','')}".strip()
                for assignee in assignees
            }
            context.user_data["id_to_name"] = id_to_name
            keyboard = []
            for assignee in assignees:
                name = id_to_name[assignee["id"]]
                user_id = assignee["id"]
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            name, callback_data=f"assignee_{user_id}"
                        )
                    ]
                )
            keyboard.append(
                [InlineKeyboardButton("Все", callback_data="assignee_all")]
            )
            await query.message.reply_text(
                "Выберите исполнителя:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return CHOOSING_ASSIGNEE
        else:
            await query.message.reply_text(
                "Ошибка при получении списка исполнителей."
            )
            return ConversationHandler.END

    elif sort_type == "sort_dueDate":
        await query.message.reply_text(
            "Введите дату (YYYY-MM-DD) или '.' для всех:"
        )
        return ENTER_DUE_DATE
    elif sort_type == "sort_type":
        keyboard = [
            [
                InlineKeyboardButton("Действие", callback_data="type_action"),
                InlineKeyboardButton("Встреча", callback_data="type_meet"),
            ],
            [
                InlineKeyboardButton("Звонок", callback_data="type_call"),
                InlineKeyboardButton("Все", callback_data="type_all"),
            ],
        ]
        await query.message.reply_text(
            "Выберите тип:", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CHOOSING_TYPE


async def choose_assignee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    assignee_data = query.data.replace("assignee_", "")
    if assignee_data == "all":
        context.user_data["filter_value"] = None
    else:
        context.user_data["filter_value"] = str(
            assignee_data
        )  # Преобразуем в int

    # Теперь фильтрация будет по task["assignees"]
    context.user_data["filter_field"] = "assignees"

    return await display_tasks(update, context, query=query)


async def enter_due_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date = update.message.text.strip()
    if date == ".":
        context.user_data["filter_value"] = None
    else:
        context.user_data["filter_value"] = date

    return await display_tasks(update, context)


async def choose_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    type_data = query.data.replace("type_", "")
    if type_data == "all":
        context.user_data["filter_value"] = None
    else:
        context.user_data["filter_value"] = type_data

    return await display_tasks(update, context, query=query)


async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.logger.info("show_tasks called")  # Отладка
    project = context.user_data.get("selected_project")
    board = context.user_data.get("selected_board")
    if not project or not board:
        await update.message.reply_text("Сначала выберите проект и доску.")
        await start(update, context)
        return CHOOSING_PROJECT

    board_id = board["id"]
    columns_response = api.get_boardColumn_list(board_id)

    if columns_response.get("success") and "boardColumns" in columns_response:
        columns_data = columns_response["boardColumns"]
        context.user_data["columns"] = columns_data

        column_names = [
            str(column.get("name", "Unnamed")) for column in columns_data
        ]
        if not column_names:
            await update.message.reply_text(
                "Колонки не найдены для этой доски."
            )
            return ConversationHandler.END

        # Добавляем опцию "Все колонки"
        column_names.append("Все колонки")
        keyboard = [
            [InlineKeyboardButton(name, callback_data=f"column_{name}")]
            for name in column_names
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"Выберите колонку для фильтрации задач (или 'Все колонки'):",
            reply_markup=reply_markup,
        )
        return CHOOSING_SORT_COLUMN
    else:
        await update.message.reply_text("Ошибка при получении списка колонок.")
        return ConversationHandler.END


async def choose_sort_column(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    logger.logger.info(
        f"choose_sort_column called with data: {query.data}"
    )  # Отладка

    column_name = query.data.replace("column_", "")
    columns = context.user_data.get("columns", [])

    # Если выбрано "Все колонки", не фильтруем по колонке
    if column_name == "Все колонки":
        context.user_data["selected_sort_column"] = None
    else:
        column_id = None
        for column in columns:
            if column.get("name") == column_name:
                column_id = column.get("id")
                break
        if column_id is None:
            await query.message.reply_text(
                "Колонка не найдена. Попробуйте еще раз."
            )
            return CHOOSING_SORT_COLUMN
        context.user_data["selected_sort_column"] = {
            "name": column_name,
            "id": column_id,
        }

    # Клавиатура для выбора сортировки
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("По дате", callback_data="sort_date"),
                InlineKeyboardButton(
                    "По исполнителю", callback_data="sort_assignee"
                ),
            ],
            [
                InlineKeyboardButton(
                    "По дедлайну", callback_data="sort_dueDate"
                ),
                InlineKeyboardButton("По типу", callback_data="sort_type"),
            ],
        ]
    )

    await query.message.reply_text(
        "Выберите тип сортировки задач:", reply_markup=keyboard
    )
    return CHOOSING_SORT_COLUMN


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Диалог отменен.")
    return ConversationHandler.END


# Конфигурируем ConversationHandler
start_conv = ConversationHandler(
    entry_points=[
        CommandHandler("start", start),
        MessageHandler(filters.Regex("^🔄 Поменять проект$"), change_project),
        MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
        MessageHandler(filters.Regex("^Добавить задачу$"), add_task),
        MessageHandler(filters.Regex("^📋 Показать задачи$"), show_tasks),
    ],
    states={
        CHOOSING_PROJECT: [
            CallbackQueryHandler(
                handle_project_selection, pattern="^select_proj_"
            ),
            CallbackQueryHandler(
                handle_project_pagination, pattern="^page_proj_"
            ),
            MessageHandler(
                filters.Regex("^🔄 Поменять проект$"), change_project
            ),
            MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
            MessageHandler(filters.Regex("^Добавить задачу$"), add_task),
            MessageHandler(filters.Regex("^📋 Показать задачи$"), show_tasks),
        ],
        CHOOSING_BOARD: [
            CallbackQueryHandler(
                handle_board_selection, pattern="^select_board_"
            ),
            CallbackQueryHandler(
                handle_board_pagination, pattern="^page_board_"
            ),
            MessageHandler(
                filters.Regex("^🔄 Поменять проект$"), change_project
            ),
            MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
            MessageHandler(filters.Regex("^Добавить задача$"), add_task),
            MessageHandler(filters.Regex("^📋 Показать задачи$"), show_tasks),
        ],
        CHOOSING_SORT_COLUMN: [
            CallbackQueryHandler(choose_sort_column, pattern="^column_"),
            CallbackQueryHandler(handle_sorting, pattern="^sort_"),
            MessageHandler(filters.Regex("^📋 Показать задачи$"), show_tasks),
            MessageHandler(
                filters.Regex("^🔄 Поменять проект$"), change_project
            ),
            MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
            MessageHandler(filters.Regex("^Добавить задача$"), add_task),
        ],
        CHOOSING_COLUMN: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, choose_column),
            MessageHandler(
                filters.Regex("^🔄 Поменять проект$"), change_project
            ),
            MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
            MessageHandler(filters.Regex("^Добавить задача$"), add_task),
            MessageHandler(filters.Regex("^📋 Показать задачи$"), show_tasks),
        ],
        ENTER_TITLE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, enter_title),
            MessageHandler(
                filters.Regex("^🔄 Поменять проект$"), change_project
            ),
            MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
            MessageHandler(filters.Regex("^Добавить задача$"), add_task),
            MessageHandler(filters.Regex("^📋 Показать задачи$"), show_tasks),
        ],
        ENTER_DESCRIPTION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, enter_description),
            MessageHandler(
                filters.Regex("^🔄 Поменять проект$"), change_project
            ),
            MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
            MessageHandler(filters.Regex("^Добавить задача$"), add_task),
            MessageHandler(filters.Regex("^📋 Показать задачи$"), show_tasks),
        ],
        CHOOSING_ASSIGNEE: [
            CallbackQueryHandler(choose_assignee, pattern="^assignee_"),
            MessageHandler(
                filters.Regex("^🔄 Поменять проект$"), change_project
            ),
            MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
            MessageHandler(filters.Regex("^Добавить задача$"), add_task),
            MessageHandler(filters.Regex("^📋 Показать задачи$"), show_tasks),
        ],
        ENTER_DUE_DATE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, enter_due_date),
            MessageHandler(
                filters.Regex("^🔄 Поменять проект$"), change_project
            ),
            MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
            MessageHandler(filters.Regex("^Добавить задача$"), add_task),
            MessageHandler(filters.Regex("^📋 Показать задачи$"), show_tasks),
        ],
        CHOOSING_TYPE: [
            CallbackQueryHandler(choose_type, pattern="^type_"),
            MessageHandler(
                filters.Regex("^🔄 Поменять проект$"), change_project
            ),
            MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
            MessageHandler(filters.Regex("^Добавить задача$"), add_task),
            MessageHandler(filters.Regex("^📋 Показать задачи$"), show_tasks),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
