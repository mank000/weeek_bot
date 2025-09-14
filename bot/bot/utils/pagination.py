from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def build_paginated_keyboard(
    items, page, per_page=5, inline=False, prefix="item_"
):
    """
    items: список строк (названия проектов/досок/и т.п.)
    page: номер страницы (начиная с 0)
    per_page: сколько элементов на страницу
    inline: True -> InlineKeyboardMarkup, False -> ReplyKeyboardMarkup
    prefix: префикс для callback_data (только для inline)
    """
    start = page * per_page
    end = start + per_page
    page_items = items[start:end]

    keyboard = []
    for item in page_items:
        if inline:
            keyboard.append(
                [InlineKeyboardButton(item, callback_data=f"{prefix}{item}")]
            )
        else:
            keyboard.append([KeyboardButton(item)])

    # Добавляем кнопки навигации
    nav_buttons = []
    if page > 0:
        if inline:
            nav_buttons.append(
                InlineKeyboardButton(
                    "⬅ Назад", callback_data=f"{prefix}page_{page-1}"
                )
            )
        else:
            nav_buttons.append(KeyboardButton("⬅ Назад"))
    if end < len(items):
        if inline:
            nav_buttons.append(
                InlineKeyboardButton(
                    "Вперёд ➡", callback_data=f"{prefix}page_{page+1}"
                )
            )
        else:
            nav_buttons.append(KeyboardButton("Вперёд ➡"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    if inline:
        return InlineKeyboardMarkup(keyboard)
    else:
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
