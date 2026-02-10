from __future__ import annotations

import logging
import random
import string
import time
from datetime import datetime, timezone

from azure.data.tables import TableServiceClient

logger = logging.getLogger("onenote_todo_sync")

# Mapping from Azure Table PascalCase to local snake_case
_TASK_FIELD_MAP = {
    "PartitionKey": "list_name",
    "RowKey": "task_id",
    "ListId": "list_id",
    "Title": "title",
    "OnenotePageId": "onenote_page_id",
    "OnenoteLink": "onenote_link",
    "CalendarEventId": "calendar_event_id",
    "Status": "status",
    "DueDate": "due_date",
    "LastModifiedTodo": "last_modified_todo",
    "LastModifiedLocal": "last_modified_local",
    "NeedsOnenote": "needs_onenote",
    "CreatedAt": "created_at",
    "UpdatedAt": "updated_at",
}

# Reverse mapping: snake_case -> PascalCase
_TASK_REVERSE_MAP = {v: k for k, v in _TASK_FIELD_MAP.items()}


class TableSyncCache:
    """Azure Table Storage-backed cache for tracking synchronization state."""

    def __init__(self, connection_string: str, table_prefix: str = ""):
        self.service = TableServiceClient.from_connection_string(connection_string)
        self.TASKS_TABLE = f"{table_prefix}SyncedTasks"
        self.LOG_TABLE = f"{table_prefix}SyncLog"
        self.REVIEWS_TABLE = f"{table_prefix}WeeklyReviews"
        self._ensure_tables()
        self.tasks_client = self.service.get_table_client(self.TASKS_TABLE)
        self.log_client = self.service.get_table_client(self.LOG_TABLE)
        self.reviews_client = self.service.get_table_client(self.REVIEWS_TABLE)

    def _ensure_tables(self):
        for name in (self.TASKS_TABLE, self.LOG_TABLE, self.REVIEWS_TABLE):
            try:
                self.service.create_table(name)
            except Exception:
                # Table already exists
                pass

    @staticmethod
    def _entity_to_task(entity: dict) -> dict:
        """Map Azure Table entity (PascalCase) to the dict format SyncEngine expects."""
        task = {}
        for azure_key, local_key in _TASK_FIELD_MAP.items():
            value = entity.get(azure_key)
            # Azure Table stores None as missing keys; normalise to None
            task[local_key] = value if value != "" else None
        return task

    @staticmethod
    def _task_to_entity(task_data: dict) -> dict:
        """Map local snake_case dict to Azure Table entity."""
        entity = {
            "PartitionKey": task_data.get("list_name", ""),
            "RowKey": task_data["task_id"],
        }
        skip = {"task_id", "list_name"}
        for local_key, azure_key in _TASK_REVERSE_MAP.items():
            if local_key in skip:
                continue
            value = task_data.get(local_key)
            entity[azure_key] = value if value is not None else ""
        return entity

    def get_task(self, task_id: str) -> dict | None:
        # task_id is the RowKey; PartitionKey is unknown, so we query
        entities = list(
            self.tasks_client.query_entities(f"RowKey eq '{task_id}'")
        )
        if not entities:
            return None
        return self._entity_to_task(entities[0])

    def get_all_tasks(self) -> list[dict]:
        entities = list(self.tasks_client.list_entities())
        return [self._entity_to_task(e) for e in entities]

    def get_tasks_by_list(self, list_name: str) -> list[dict]:
        entities = list(
            self.tasks_client.query_entities(f"PartitionKey eq '{list_name}'")
        )
        return [self._entity_to_task(e) for e in entities]

    def upsert_task(self, task_data: dict):
        now = datetime.now(timezone.utc).isoformat()

        existing = self.get_task(task_data["task_id"])
        if existing:
            # Merge: keep old values for missing keys
            merged = dict(existing)
            merged.update({k: v for k, v in task_data.items() if v is not None})
            merged["last_modified_local"] = now
            merged["updated_at"] = now
            entity = self._task_to_entity(merged)
        else:
            task_data.setdefault("created_at", now)
            task_data["updated_at"] = now
            task_data["last_modified_local"] = now
            entity = self._task_to_entity(task_data)

        self.tasks_client.upsert_entity(entity)

    def delete_task(self, task_id: str):
        # Need partition key to delete; look it up first
        existing = self.get_task(task_id)
        if existing:
            self.tasks_client.delete_entity(
                partition_key=existing["list_name"],
                row_key=task_id,
            )

    def log_action(self, action: str, task_id: str = None, details: str = None, success: bool = True):
        now = datetime.now(timezone.utc)
        # Reverse timestamp for newest-first ordering
        reverse_ts = str(9999999999 - int(now.timestamp()))
        suffix = "".join(random.choices(string.ascii_lowercase, k=4))
        entity = {
            "PartitionKey": "log",
            "RowKey": f"{reverse_ts}-{suffix}",
            "LogTimestamp": now.isoformat(),
            "Action": action,
            "TaskId": task_id or "",
            "Details": details or "",
            "Success": success,
        }
        self.log_client.upsert_entity(entity)

    def get_weekly_review(self, week_start: str) -> dict | None:
        try:
            entity = self.reviews_client.get_entity(
                partition_key="review",
                row_key=week_start,
            )
            return {
                "event_id": entity["EventId"],
                "week_start": entity["RowKey"],
                "created_at": entity.get("CreatedAt", ""),
            }
        except Exception:
            return None

    def save_weekly_review(self, event_id: str, week_start: str):
        now = datetime.now(timezone.utc).isoformat()
        entity = {
            "PartitionKey": "review",
            "RowKey": week_start,
            "EventId": event_id,
            "CreatedAt": now,
        }
        self.reviews_client.upsert_entity(entity)

    def close(self):
        # No persistent connection to close for Table Storage
        pass
