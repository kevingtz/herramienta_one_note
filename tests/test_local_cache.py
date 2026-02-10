import pytest

from src.cache.local_cache import SyncCache


class TestSyncCache:
    @pytest.fixture(autouse=True)
    def setup_cache(self, temp_db):
        self.cache = SyncCache(db_path=temp_db)
        yield
        self.cache.close()

    def test_upsert_and_get_task(self):
        task_data = {
            "task_id": "t1",
            "list_id": "list-1",
            "list_name": "Hoy",
            "title": "Test task",
            "status": "notStarted",
        }
        self.cache.upsert_task(task_data)
        result = self.cache.get_task("t1")
        assert result is not None
        assert result["title"] == "Test task"
        assert result["status"] == "notStarted"
        assert result["created_at"] is not None

    def test_upsert_update_existing(self):
        task_data = {
            "task_id": "t1",
            "list_id": "list-1",
            "list_name": "Hoy",
            "title": "Test task",
            "status": "notStarted",
        }
        self.cache.upsert_task(task_data)
        task_data["status"] = "completed"
        task_data["onenote_page_id"] = "page-1"
        self.cache.upsert_task(task_data)
        result = self.cache.get_task("t1")
        assert result["status"] == "completed"
        assert result["onenote_page_id"] == "page-1"

    def test_get_task_not_found(self):
        assert self.cache.get_task("nonexistent") is None

    def test_get_all_tasks(self):
        for i in range(3):
            self.cache.upsert_task({
                "task_id": f"t{i}",
                "list_id": "list-1",
                "list_name": "Hoy",
                "title": f"Task {i}",
                "status": "notStarted",
            })
        result = self.cache.get_all_tasks()
        assert len(result) == 3

    def test_get_tasks_by_list(self):
        self.cache.upsert_task({
            "task_id": "t1", "list_id": "l1", "list_name": "Hoy",
            "title": "A", "status": "notStarted",
        })
        self.cache.upsert_task({
            "task_id": "t2", "list_id": "l2", "list_name": "Esta semana",
            "title": "B", "status": "notStarted",
        })
        result = self.cache.get_tasks_by_list("Hoy")
        assert len(result) == 1
        assert result[0]["task_id"] == "t1"

    def test_delete_task(self):
        self.cache.upsert_task({
            "task_id": "t1", "list_id": "l1", "list_name": "Hoy",
            "title": "A", "status": "notStarted",
        })
        self.cache.delete_task("t1")
        assert self.cache.get_task("t1") is None

    def test_log_action(self):
        self.cache.log_action("create_page", task_id="t1", details="Test")
        rows = self.cache.conn.execute("SELECT * FROM sync_log").fetchall()
        assert len(rows) == 1
        assert dict(rows[0])["action"] == "create_page"

    def test_log_action_failure(self):
        self.cache.log_action("create_page", task_id="t1", success=False)
        row = dict(self.cache.conn.execute("SELECT * FROM sync_log").fetchone())
        assert row["success"] == 0

    def test_weekly_review(self):
        self.cache.save_weekly_review("evt-1", "2025-01-13")
        result = self.cache.get_weekly_review("2025-01-13")
        assert result is not None
        assert result["event_id"] == "evt-1"

    def test_weekly_review_not_found(self):
        assert self.cache.get_weekly_review("2099-01-01") is None
