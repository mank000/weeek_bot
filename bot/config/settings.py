import os
import sys

from requests import get

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000/api/bot-token")


def fetch_token(name: str) -> str:
    """
    Достаём настройку с backend.
    Если не удалось — сразу завершаем работу.
    """
    try:
        response = get(BACKEND_URL, timeout=5)
        response.raise_for_status()
        data = response.json()
        if name not in data:
            print(
                f"[ERROR] Ключ '{name}' не найден в ответе от {BACKEND_URL}",
                file=sys.stderr,
            )
            sys.exit(1)
        return data[name]
    except Exception as e:
        print(
            f"[ERROR] Не удалось получить '{name}' с {BACKEND_URL}: {e}",
            file=sys.stderr,
        )
        sys.exit(1)


TELEGRAM_TOKEN = fetch_token("api_key")
WEEK_TOKEN = fetch_token("week_key")
