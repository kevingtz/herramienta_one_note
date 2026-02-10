#!/usr/bin/env python3
"""Migrate data from local SQLite cache to Azure Table Storage.

Usage:
    python scripts/migrate_sqlite_to_table.py

Requires:
    - AZURE_STORAGE_CONNECTION_STRING env var or .env file
    - Existing SQLite cache at ~/.onenote-todo-sync/sync_cache.db
"""

import argparse
import os
import sys

from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cache.local_cache import SyncCache
from src.cache.table_cache import TableSyncCache


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite cache to Azure Table Storage")
    parser.add_argument(
        "--table-prefix", default="",
        help="Table name prefix (e.g. 'Work' for WorkSyncedTasks)",
    )
    args = parser.parse_args()

    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not connection_string:
        print("ERROR: Set AZURE_STORAGE_CONNECTION_STRING in .env or environment")
        sys.exit(1)

    db_path = os.path.expanduser("~/.onenote-todo-sync/sync_cache.db")
    if not os.path.exists(db_path):
        print(f"ERROR: SQLite database not found at {db_path}")
        sys.exit(1)

    print("Connecting to local SQLite cache...")
    local = SyncCache(db_path=db_path)

    print("Connecting to Azure Table Storage...")
    table = TableSyncCache(connection_string, table_prefix=args.table_prefix)

    # Migrate tasks
    tasks = local.get_all_tasks()
    print(f"Found {len(tasks)} tasks to migrate")
    for task in tasks:
        table.upsert_task(task)
        print(f"  Migrated task: {task['title'][:50]}")

    # Migrate weekly reviews
    rows = local.conn.execute("SELECT * FROM weekly_reviews").fetchall()
    reviews = [dict(r) for r in rows]
    print(f"Found {len(reviews)} weekly reviews to migrate")
    for review in reviews:
        table.save_weekly_review(review["event_id"], review["week_start"])
        print(f"  Migrated review: week_start={review['week_start']}")

    local.close()
    table.close()

    print(f"\nMigration complete: {len(tasks)} tasks, {len(reviews)} reviews")


if __name__ == "__main__":
    main()
