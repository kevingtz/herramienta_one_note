"""Azure Functions entry point — Timer Trigger (every 1 minute)."""

import logging
import os

import azure.functions as func
import yaml

from src.auth import create_auth_azure
from src.cache.table_cache import TableSyncCache
from src.graph_client import GraphClient
from src.rules.evaluator import TaskEvaluator
from src.services.calendar_service import CalendarService
from src.services.onenote_service import OneNoteService
from src.services.sync_engine import SyncEngine
from src.services.todo_service import TodoService
from src.utils.logger import setup_logger

app = func.FunctionApp()

logger = logging.getLogger("onenote_todo_sync")


def _load_config(config_file: str = "config.yaml") -> dict:
    config_path = os.path.join(os.path.dirname(__file__), config_file)
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


@app.timer_trigger(
    schedule="0 */1 * * * *",
    arg_name="timer",
    run_on_startup=False,
)
def sync_trigger(timer: func.TimerRequest) -> None:
    """Run one sync cycle every minute."""
    if timer.past_due:
        logger.warning("Timer trigger is past due — running anyway")

    cache = None
    try:
        client_id = os.environ["CLIENT_ID"]
        connection_string = os.environ["AzureWebJobsStorage"]
        authority = os.environ.get("AUTHORITY", "https://login.microsoftonline.com/consumers")
        blob_name = os.environ.get("TOKEN_BLOB_NAME", "token_cache.json")
        table_prefix = os.environ.get("TABLE_PREFIX", "")
        config_file = os.environ.get("CONFIG_FILE", "config.yaml")

        config = _load_config(config_file)
        setup_logger(config)

        auth = create_auth_azure(client_id, connection_string, authority=authority, blob_name=blob_name)
        graph = GraphClient(auth)
        cache = TableSyncCache(connection_string, table_prefix=table_prefix)
        evaluator = TaskEvaluator(config.get("rules", {}))
        todo = TodoService(graph)
        onenote = OneNoteService(graph)
        calendar = CalendarService(graph)

        engine = SyncEngine(
            todo_service=todo,
            onenote_service=onenote,
            calendar_service=calendar,
            evaluator=evaluator,
            cache=cache,
            config=config,
        )

        engine.run_once()
        logger.info("Sync cycle completed successfully")

    except Exception:
        logger.exception("Sync cycle failed")
        raise
    finally:
        if cache is not None:
            cache.close()
