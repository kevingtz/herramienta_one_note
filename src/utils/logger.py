import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logger(config: dict) -> logging.Logger:
    """Configure and return the application logger."""
    log_config = config.get("logging", {})
    level = getattr(logging, log_config.get("level", "INFO").upper(), logging.INFO)

    logger = logging.getLogger("onenote_todo_sync")
    logger.setLevel(level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    is_azure = os.environ.get("AZURE_FUNCTIONS_ENVIRONMENT")

    if not is_azure:
        # Local: write to rotating log file
        file_path = os.path.expanduser(
            log_config.get("file_path", "~/Library/Logs/OneNoteTodoSync/sync.log")
        )
        max_bytes = log_config.get("max_file_size_mb", 10) * 1024 * 1024
        backup_count = log_config.get("backup_count", 5)

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        file_handler = RotatingFileHandler(
            file_path, maxBytes=max_bytes, backupCount=backup_count
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
