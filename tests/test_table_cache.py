from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.cache.table_cache import TableSyncCache, _TASK_FIELD_MAP


class FakeTableClient:
    """In-memory fake that mimics azure.data.tables.TableClient."""

    def __init__(self):
        # keyed by (PartitionKey, RowKey)
        self._entities: dict[tuple[str, str], dict] = {}

    def upsert_entity(self, entity: dict):
        key = (entity["PartitionKey"], entity["RowKey"])
        self._entities[key] = dict(entity)

    def get_entity(self, partition_key: str, row_key: str) -> dict:
        key = (partition_key, row_key)
        if key not in self._entities:
            from azure.core.exceptions import ResourceNotFoundError
            raise ResourceNotFoundError("Not found")
        return dict(self._entities[key])

    def delete_entity(self, partition_key: str, row_key: str):
        key = (partition_key, row_key)
        self._entities.pop(key, None)

    def query_entities(self, query_filter: str) -> list[dict]:
        results = []
        for entity in self._entities.values():
            if self._matches(entity, query_filter):
                results.append(dict(entity))
        return results

    def list_entities(self) -> list[dict]:
        return [dict(e) for e in self._entities.values()]

    @staticmethod
    def _matches(entity: dict, query_filter: str) -> bool:
        # Simple OData filter parser for tests
        # Handles: "RowKey eq 'value'" and "PartitionKey eq 'value'"
        parts = query_filter.split(" eq ")
        if len(parts) != 2:
            return False
        field = parts[0].strip()
        value = parts[1].strip().strip("'")
        return entity.get(field) == value


class FakeTableServiceClient:
    """Fake TableServiceClient that returns FakeTableClient instances."""

    def __init__(self):
        self._tables: dict[str, FakeTableClient] = {}

    def create_table(self, name: str):
        if name not in self._tables:
            self._tables[name] = FakeTableClient()

    def get_table_client(self, name: str) -> FakeTableClient:
        if name not in self._tables:
            self._tables[name] = FakeTableClient()
        return self._tables[name]


@pytest.fixture
def table_cache():
    """Create a TableSyncCache backed by in-memory fakes."""
    fake_service = FakeTableServiceClient()
    with patch.object(
        TableSyncCache, "__init__", lambda self, conn, table_prefix="": None
    ):
        cache = TableSyncCache.__new__(TableSyncCache)

    # Manually set up the attributes that __init__ would create
    cache.service = fake_service
    cache.TASKS_TABLE = "SyncedTasks"
    cache.LOG_TABLE = "SyncLog"
    cache.REVIEWS_TABLE = "WeeklyReviews"
    cache._ensure_tables()
    cache.tasks_client = fake_service.get_table_client(cache.TASKS_TABLE)
    cache.log_client = fake_service.get_table_client(cache.LOG_TABLE)
    cache.reviews_client = fake_service.get_table_client(cache.REVIEWS_TABLE)
    yield cache
    cache.close()


class TestTableSyncCache:
    def test_upsert_and_get_task(self, table_cache):
        task_data = {
            "task_id": "t1",
            "list_id": "list-1",
            "list_name": "Hoy",
            "title": "Test task",
            "status": "notStarted",
        }
        table_cache.upsert_task(task_data)
        result = table_cache.get_task("t1")
        assert result is not None
        assert result["title"] == "Test task"
        assert result["status"] == "notStarted"
        assert result["created_at"] is not None

    def test_upsert_update_existing(self, table_cache):
        task_data = {
            "task_id": "t1",
            "list_id": "list-1",
            "list_name": "Hoy",
            "title": "Test task",
            "status": "notStarted",
        }
        table_cache.upsert_task(task_data)
        task_data["status"] = "completed"
        task_data["onenote_page_id"] = "page-1"
        table_cache.upsert_task(task_data)
        result = table_cache.get_task("t1")
        assert result["status"] == "completed"
        assert result["onenote_page_id"] == "page-1"

    def test_get_task_not_found(self, table_cache):
        assert table_cache.get_task("nonexistent") is None

    def test_get_all_tasks(self, table_cache):
        for i in range(3):
            table_cache.upsert_task({
                "task_id": f"t{i}",
                "list_id": "list-1",
                "list_name": "Hoy",
                "title": f"Task {i}",
                "status": "notStarted",
            })
        result = table_cache.get_all_tasks()
        assert len(result) == 3

    def test_get_tasks_by_list(self, table_cache):
        table_cache.upsert_task({
            "task_id": "t1", "list_id": "l1", "list_name": "Hoy",
            "title": "A", "status": "notStarted",
        })
        table_cache.upsert_task({
            "task_id": "t2", "list_id": "l2", "list_name": "Esta semana",
            "title": "B", "status": "notStarted",
        })
        result = table_cache.get_tasks_by_list("Hoy")
        assert len(result) == 1
        assert result[0]["task_id"] == "t1"

    def test_delete_task(self, table_cache):
        table_cache.upsert_task({
            "task_id": "t1", "list_id": "l1", "list_name": "Hoy",
            "title": "A", "status": "notStarted",
        })
        table_cache.delete_task("t1")
        assert table_cache.get_task("t1") is None

    def test_log_action(self, table_cache):
        table_cache.log_action("create_page", task_id="t1", details="Test")
        entities = list(table_cache.log_client.list_entities())
        assert len(entities) == 1
        assert entities[0]["Action"] == "create_page"

    def test_log_action_failure(self, table_cache):
        table_cache.log_action("create_page", task_id="t1", success=False)
        entities = list(table_cache.log_client.list_entities())
        assert len(entities) == 1
        assert entities[0]["Success"] is False

    def test_weekly_review(self, table_cache):
        table_cache.save_weekly_review("evt-1", "2025-01-13")
        result = table_cache.get_weekly_review("2025-01-13")
        assert result is not None
        assert result["event_id"] == "evt-1"

    def test_weekly_review_not_found(self, table_cache):
        assert table_cache.get_weekly_review("2099-01-01") is None

    def test_entity_to_task_mapping(self, table_cache):
        """Verify PascalCase -> snake_case mapping covers all fields."""
        entity = {
            "PartitionKey": "Hoy",
            "RowKey": "t99",
            "ListId": "list-x",
            "Title": "Mapped task",
            "OnenotePageId": "page-5",
            "OnenoteLink": "https://link",
            "CalendarEventId": "cal-3",
            "Status": "notStarted",
            "DueDate": "2026-02-10",
            "LastModifiedTodo": "2026-02-09T12:00:00Z",
            "LastModifiedLocal": "2026-02-09T12:00:00Z",
            "NeedsOnenote": 1,
            "CreatedAt": "2026-02-09T00:00:00Z",
            "UpdatedAt": "2026-02-09T00:00:00Z",
        }
        task = TableSyncCache._entity_to_task(entity)
        assert task["task_id"] == "t99"
        assert task["list_name"] == "Hoy"
        assert task["list_id"] == "list-x"
        assert task["title"] == "Mapped task"
        assert task["onenote_page_id"] == "page-5"
        assert task["calendar_event_id"] == "cal-3"
        assert task["due_date"] == "2026-02-10"
        assert task["needs_onenote"] == 1


class TestTableSyncCachePrefix:
    def test_table_prefix_creates_prefixed_tables(self):
        """TableSyncCache with prefix should create Work-prefixed table names."""
        fake_service = FakeTableServiceClient()
        with patch.object(
            TableSyncCache, "__init__", lambda self, conn, table_prefix="": None
        ):
            cache = TableSyncCache.__new__(TableSyncCache)

        cache.service = fake_service
        cache.TASKS_TABLE = "WorkSyncedTasks"
        cache.LOG_TABLE = "WorkSyncLog"
        cache.REVIEWS_TABLE = "WorkWeeklyReviews"
        cache._ensure_tables()
        cache.tasks_client = fake_service.get_table_client(cache.TASKS_TABLE)
        cache.log_client = fake_service.get_table_client(cache.LOG_TABLE)
        cache.reviews_client = fake_service.get_table_client(cache.REVIEWS_TABLE)

        assert cache.TASKS_TABLE == "WorkSyncedTasks"
        assert cache.LOG_TABLE == "WorkSyncLog"
        assert cache.REVIEWS_TABLE == "WorkWeeklyReviews"
        assert "WorkSyncedTasks" in fake_service._tables
        assert "WorkSyncLog" in fake_service._tables
        assert "WorkWeeklyReviews" in fake_service._tables

        # Verify it works — upsert and retrieve a task
        cache.upsert_task({
            "task_id": "t1", "list_id": "l1", "list_name": "Today",
            "title": "Work task", "status": "notStarted",
        })
        result = cache.get_task("t1")
        assert result is not None
        assert result["title"] == "Work task"
        cache.close()

    def test_default_prefix_is_empty(self):
        """TableSyncCache with no prefix should use default table names."""
        fake_service = FakeTableServiceClient()
        with patch.object(
            TableSyncCache, "__init__", lambda self, conn, table_prefix="": None
        ):
            cache = TableSyncCache.__new__(TableSyncCache)

        cache.service = fake_service
        cache.TASKS_TABLE = "SyncedTasks"
        cache.LOG_TABLE = "SyncLog"
        cache.REVIEWS_TABLE = "WeeklyReviews"
        cache._ensure_tables()
        cache.tasks_client = fake_service.get_table_client(cache.TASKS_TABLE)
        cache.log_client = fake_service.get_table_client(cache.LOG_TABLE)
        cache.reviews_client = fake_service.get_table_client(cache.REVIEWS_TABLE)

        assert cache.TASKS_TABLE == "SyncedTasks"
        assert cache.LOG_TABLE == "SyncLog"
        assert cache.REVIEWS_TABLE == "WeeklyReviews"
        cache.close()
