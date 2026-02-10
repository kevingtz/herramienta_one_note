#!/usr/bin/env python3
"""OneNote + To Do + Outlook Calendar Sync Daemon."""

import argparse
import os
import sys

import yaml
from dotenv import load_dotenv

# Add project root to path so 'src' package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.auth import create_auth
from src.cache.local_cache import SyncCache
from src.graph_client import GraphClient
from src.rules.evaluator import TaskEvaluator
from src.services.calendar_service import CalendarService
from src.services.onenote_service import OneNoteService
from src.services.sync_engine import SyncEngine
from src.services.todo_service import TodoService
from src.utils.logger import setup_logger


def load_config(config_path: str) -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="OneNote + To Do Sync Daemon")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single sync cycle and exit",
    )
    parser.add_argument(
        "--auth",
        action="store_true",
        help="Only authenticate and verify connection",
    )
    parser.add_argument(
        "--account",
        choices=["personal", "work"],
        default="personal",
        help="Account to use (default: personal)",
    )
    parser.add_argument(
        "--auth-flow",
        choices=["device_code", "interactive", "manual"],
        default="device_code",
        help="Auth flow to use (default: device_code, use manual for restrictive tenants)",
    )
    args = parser.parse_args()

    # Load environment
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
    )
    load_dotenv(env_path)

    client_id = os.getenv("CLIENT_ID")
    if not client_id:
        print("ERROR: CLIENT_ID must be set in .env")
        sys.exit(1)

    # Determine defaults based on --account
    data_dir = os.path.expanduser("~/.onenote-todo-sync")
    if args.account == "work":
        default_config = "config_work.yaml"
        authority = "https://login.microsoftonline.com/organizations"
        token_cache_path = os.path.join(data_dir, "token_cache_work.json")
        db_path = os.path.join(data_dir, "sync_cache_work.db")
        label = "work"
    else:
        default_config = "config.yaml"
        authority = "https://login.microsoftonline.com/consumers"
        token_cache_path = None  # use default
        db_path = None  # use default
        label = "personal"

    # Load config (--config overrides the account-based default)
    config_path = args.config if args.config != "config.yaml" else default_config
    if not os.path.isabs(config_path):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            config_path,
        )
    config = load_config(config_path)

    # Setup logging
    logger = setup_logger(config)
    logger.info("Starting OneNote-ToDo Sync (%s account)", args.account)

    auth = create_auth(client_id, authority=authority, auth_flow=args.auth_flow,
                       cache_path=token_cache_path, label=label)

    if args.auth:
        user = auth.verify_connection()
        print(f"Authenticated as: {user.get('displayName')} ({user.get('mail')})")
        return

    # All services share the same GraphClient
    graph = GraphClient(auth)
    cache = SyncCache(db_path) if db_path else SyncCache()
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

    try:
        if args.once:
            logger.info("Running single sync cycle")
            engine.run_once()
            logger.info("Single cycle complete")
        else:
            engine.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)
    finally:
        cache.close()


if __name__ == "__main__":
    main()
