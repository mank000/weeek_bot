import logging


def setup_logger(name: str = "TelegramBot"):
    logger = logging.getLogger(name)
    if not logger.hasHandlers():  # чтобы не дублировать хендлеры
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


# сразу создаём объект
logger = setup_logger()
