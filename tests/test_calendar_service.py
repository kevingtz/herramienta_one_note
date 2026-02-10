from datetime import datetime
from unittest.mock import MagicMock

from src.services.calendar_service import CalendarService
from tests.mocks.graph_responses import CREATED_EVENT, WEEKLY_REVIEW_EVENT


class TestCalendarService:
    def setup_method(self):
        self.graph = MagicMock()
        self.service = CalendarService(self.graph)

    def test_create_event(self):
        self.graph.post.return_value = CREATED_EVENT
        start = datetime(2025, 1, 20, 9, 0)
        result = self.service.create_event(
            subject="Test Event",
            start=start,
        )
        assert result["id"] == "event-123"
        call_json = self.graph.post.call_args[1]["json"]
        assert call_json["subject"] == "Test Event"
        assert "America/Mexico_City" in call_json["start"]["timeZone"]

    def test_create_event_with_end(self):
        self.graph.post.return_value = CREATED_EVENT
        start = datetime(2025, 1, 20, 9, 0)
        end = datetime(2025, 1, 20, 10, 30)
        self.service.create_event(subject="Test", start=start, end=end)
        call_json = self.graph.post.call_args[1]["json"]
        assert "10:30" in call_json["end"]["dateTime"]

    def test_update_event(self):
        self.graph.patch.return_value = {}
        self.service.update_event("event-123", {"subject": "Updated"})
        self.graph.patch.assert_called_once_with(
            "/me/events/event-123", json={"subject": "Updated"}
        )

    def test_delete_event(self):
        self.service.delete_event("event-123")
        self.graph.delete.assert_called_once_with("/me/events/event-123")

    def test_find_event_by_subject_found(self):
        self.graph.get_all.return_value = [CREATED_EVENT]
        result = self.service.find_event_by_subject("[To Do] Test Task")
        assert result["id"] == "event-123"

    def test_find_event_by_subject_not_found(self):
        self.graph.get_all.return_value = []
        result = self.service.find_event_by_subject("Nonexistent")
        assert result is None

    def test_create_weekly_review(self):
        self.graph.post.return_value = WEEKLY_REVIEW_EVENT
        start = datetime(2025, 1, 19, 18, 0)
        result = self.service.create_weekly_review(
            start=start,
            duration_minutes=30,
            pending_tasks_summary="- Task 1\n- Task 2",
        )
        assert result["id"] == "event-weekly-123"
        call_json = self.graph.post.call_args[1]["json"]
        assert call_json["subject"] == "Revisión Semanal - Tareas"
        assert "Task 1" in call_json["body"]["content"]
