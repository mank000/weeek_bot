import asyncio

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


async def change_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stop_polling(context)
    context.user_data.pop("selected_project", None)
    context.user_data.pop("selected_board", None)

    # повторяем выбор проекта (как в start)
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
    project_names = [p[0] for p in project_data]

    keyboard = []
    row = []
    for i, name in enumerate(project_names, 1):
        row.append(KeyboardButton(str(name)))
        if i % 5 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    reply_markup = ReplyKeyboardMarkup(
        keyboard, one_time_keyboard=True, resize_keyboard=True
    )

    await update.message.reply_text(
        "Выберите проект:", reply_markup=reply_markup
    )
    return CHOOSING_PROJECT


async def change_board(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stop_polling(context)
    await update.message.reply_text("🔄 Вы решили поменять доску.")

    project = context.user_data.get("selected_project")
    if not project:
        await update.message.reply_text("Сначала выберите проект.")
        await start(update, context)
        return CHOOSING_PROJECT  # Измените на это, чтобы продолжить диалог после start

    project_id = project["id"]
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
            f"Выберите доску для проекта {project['name']}:",
            reply_markup=reply_markup,
        )
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
    project_names = [p[0] for p in project_data]
    keyboard = []
    row = []

    for i, name in enumerate(project_names, 1):
        row.append(KeyboardButton(str(name)))
        if i % 5 == 0:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    reply_markup = ReplyKeyboardMarkup(
        keyboard, one_time_keyboard=True, resize_keyboard=True
    )

    await update.message.reply_text(
        "Выберите проект:",
        reply_markup=reply_markup,
    )

    return CHOOSING_PROJECT


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
    """Фоновая задача: отслеживаем новые задачи и изменения."""
    tasks_state = {}
    column_names = {}

    while True:
        try:
            # Получаем колонки
            columns_response = api.get_boardColumn_list(board_id)
            if (
                columns_response.get("success")
                and "boardColumns" in columns_response
            ):
                column_names = {
                    col["id"]: col["name"]
                    for col in columns_response["boardColumns"]
                }

            # Получаем задачи
            response = api.get_tasks(projectId=project_id, boardId=board_id)
            if not response.get("success") or "tasks" not in response:
                await asyncio.sleep(2)
                continue

            tasks = response["tasks"]
            current_ids = set()

            for task in tasks:
                task_id = task["id"]
                current_ids.add(task_id)

                col_id = task.get("boardColumnId")
                col_name = column_names.get(col_id, f"Колонка {col_id}")

                snapshot = {
                    "title": task.get("title"),
                    "description": task.get("description"),
                    "boardColumn": col_name,
                    "isCompleted": task.get("isCompleted"),
                    "isDeleted": task.get("isDeleted"),
                }

                if task_id not in tasks_state:
                    tasks_state[task_id] = snapshot
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"🆕 Новая задача: {snapshot['title']} (в {snapshot['boardColumn']})",
                    )
                else:
                    old = tasks_state[task_id]
                    changes = []
                    if old["title"] != snapshot["title"]:
                        changes.append(
                            f"✏️ Название: {old['title']} → {snapshot['title']}"
                        )
                    if old["description"] != snapshot["description"]:
                        changes.append("📝 Описание изменилось")
                    if old["boardColumn"] != snapshot["boardColumn"]:
                        changes.append(
                            f"📂 Колонка: {old['boardColumn']} → {snapshot['boardColumn']}"
                        )
                    if old["isCompleted"] != snapshot["isCompleted"]:
                        changes.append(f"⚡ Статус изменился")
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
                        )
                        tasks_state[task_id] = snapshot

            # Удалённые задачи
            removed_ids = set(tasks_state.keys()) - current_ids
            for rid in removed_ids:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Задача {tasks_state[rid]['title']} исчезла",
                )
                del tasks_state[rid]

            await asyncio.sleep(2)

        except Exception as e:
            logger.logger.error(f"Ошибка в poll_board_updates: {e}")
            await context.bot.send_message(
                chat_id=chat_id, text=f"⚠️ Ошибка: {e}"
            )
            await asyncio.sleep(5)  # вместо break делаем паузу и продолжаем
            continue


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

    message = (
        f"📌 {task.get('title', 'Без названия')}\n"
        f"Описание: {task.get('description', 'Без описания')}\n"
        f"Колонка: {col_name}\n"
        f"Исполнитель: {task.get('assignee', 'Не назначен')}\n"
        f"Дедлайн: {task.get('dueDate', 'Без дедлайна')}\n"
        f"Тип: {task.get('type', 'Не указан')}\n"
        f"Статус: {'Выполнена' if task.get('isCompleted') else 'Активна'}\n"
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
            task for task in tasks if task.get(filter_field) == filter_value
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
            assignee = task.get("assignee", "Не назначен")
            due_date = task.get("dueDate", "Без дедлайна")
            task_type = task.get("type", "Не указан")
            status = "Выполнена" if task.get("isCompleted") else "Активна"

            message = (
                f"📌 {title}\n"
                f"Колонка: {col_name}\n"
                f"Исполнитель: {assignee}\n"
                f"Дедлайн: {due_date}\n"
                f"Тип: {task_type}\n"
                f"Статус: {status}\n"
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
        "sort_assignee": "assignee",
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
            keyboard = []
            for assignee in assignees:
                name = f"{assignee.get('firstName','')} {assignee.get('lastName','')}".strip()
                user_id = assignee.get("id")
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
                InlineKeyboardButton(
                    "Действие", callback_data="type_Действие"
                ),
                InlineKeyboardButton("Встреча", callback_data="type_Встреча"),
            ],
            [
                InlineKeyboardButton("Звонок", callback_data="type_Звонок"),
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
        context.user_data["filter_value"] = assignee_data  # user_id

    # Теперь фильтрация будет по task["assigneeId"]
    context.user_data["filter_field"] = "assigneeId"

    return await display_tasks(update, context, query=query)


async def enter_due_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date = update.message.text.strip()
    if date == ".":
        context.user_data["filter_value"] = None
    else:
        # Простая валидация, можно добавить больше
        context.user_data["filter_value"] = date

    return await display_tasks(update, context)


async def choose_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    type_data = query.data.replace("type_", "")
    if type_data == "all":
        context.user_data["filter_value"] = None
    else:
        context.user_data["filter_value"] = (
            type_data.lower()
        )  # Предполагаем, что типы в нижнем регистре в задачах

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
            MessageHandler(filters.TEXT & ~filters.COMMAND, choose_project),
            MessageHandler(
                filters.Regex("^🔄 Поменять проект$"), change_project
            ),
            MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
            MessageHandler(filters.Regex("^Добавить задачу$"), add_task),
            MessageHandler(filters.Regex("^📋 Показать задачи$"), show_tasks),
        ],
        CHOOSING_BOARD: [
            MessageHandler(
                filters.Regex("^🔄 Поменять проект$"), change_project
            ),
            MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
            MessageHandler(filters.Regex("^Добавить задачу$"), add_task),
            MessageHandler(filters.Regex("^📋 Показать задачи$"), show_tasks),
            MessageHandler(filters.TEXT & ~filters.COMMAND, choose_board),
        ],
        CHOOSING_SORT_COLUMN: [
            CallbackQueryHandler(choose_sort_column, pattern="^column_"),
            CallbackQueryHandler(handle_sorting, pattern="^sort_"),
            MessageHandler(
                filters.Regex("^📋 Показать задачи$"), show_tasks
            ),  # Добавляем обработку
            MessageHandler(
                filters.Regex("^🔄 Поменять проект$"), change_project
            ),
            MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
            MessageHandler(filters.Regex("^Добавить задачу$"), add_task),
            CallbackQueryHandler(handle_pagination, pattern="^page_"),
        ],
        CHOOSING_COLUMN: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, choose_column),
            MessageHandler(
                filters.Regex("^🔄 Поменять проект$"), change_project
            ),
            MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
            MessageHandler(filters.Regex("^Добавить задачу$"), add_task),
            MessageHandler(filters.Regex("^📋 Показать задачи$"), show_tasks),
        ],
        ENTER_TITLE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, enter_title),
            MessageHandler(
                filters.Regex("^🔄 Поменять проект$"), change_project
            ),
            MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
            MessageHandler(filters.Regex("^Добавить задачу$"), add_task),
            MessageHandler(filters.Regex("^📋 Показать задачи$"), show_tasks),
        ],
        ENTER_DESCRIPTION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, enter_description),
            MessageHandler(
                filters.Regex("^🔄 Поменять проект$"), change_project
            ),
            MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
            MessageHandler(filters.Regex("^Добавить задачу$"), add_task),
            MessageHandler(filters.Regex("^📋 Показать задачи$"), show_tasks),
        ],
        CHOOSING_ASSIGNEE: [
            CallbackQueryHandler(choose_assignee, pattern="^assignee_"),
            MessageHandler(
                filters.Regex("^🔄 Поменять проект$"), change_project
            ),
            MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
            MessageHandler(filters.Regex("^Добавить задачу$"), add_task),
            MessageHandler(filters.Regex("^📋 Показать задачи$"), show_tasks),
            CallbackQueryHandler(handle_pagination, pattern="^page_"),
        ],
        ENTER_DUE_DATE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, enter_due_date),
            MessageHandler(
                filters.Regex("^🔄 Поменять проект$"), change_project
            ),
            MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
            MessageHandler(filters.Regex("^Добавить задачу$"), add_task),
            MessageHandler(filters.Regex("^📋 Показать задачи$"), show_tasks),
            CallbackQueryHandler(handle_pagination, pattern="^page_"),
        ],
        CHOOSING_TYPE: [
            CallbackQueryHandler(choose_type, pattern="^type_"),
            MessageHandler(
                filters.Regex("^🔄 Поменять проект$"), change_project
            ),
            MessageHandler(filters.Regex("^🔄 Поменять доску$"), change_board),
            MessageHandler(filters.Regex("^Добавить задачу$"), add_task),
            MessageHandler(filters.Regex("^📋 Показать задачи$"), show_tasks),
            CallbackQueryHandler(handle_pagination, pattern="^page_"),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
