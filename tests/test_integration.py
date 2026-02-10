"""End-to-end integration test simulating a full sync cycle with mocked Graph API."""

from unittest.mock import MagicMock

import pytest

from src.cache.local_cache import SyncCache
from src.rules.evaluator import TaskEvaluator
from src.services.calendar_service import CalendarService
from src.services.onenote_service import OneNoteService
from src.services.sync_engine import SyncEngine
from src.services.todo_service import TodoService
from tests.mocks.graph_responses import (
    NOTEBOOKS, SECTIONS, CREATED_SECTION, CREATED_PAGE,
    TODO_LISTS, CREATED_EVENT, WEEKLY_REVIEW_EVENT,
)


@pytest.fixture
def mock_graph():
    return MagicMock()


@pytest.fixture
def full_engine(config, temp_db, mock_graph):
    """Build a full engine stack with mocked Graph client."""
    todo = TodoService(mock_graph)
    onenote = OneNoteService(mock_graph)
    calendar = CalendarService(mock_graph)
    evaluator = TaskEvaluator(config["rules"])
    cache = SyncCache(db_path=temp_db)

    engine = SyncEngine(
        todo_service=todo,
        onenote_service=onenote,
        calendar_service=calendar,
        evaluator=evaluator,
        cache=cache,
        config=config,
    )
    yield engine, mock_graph, cache
    cache.close()


class TestIntegration:
    def test_full_sync_cycle(self, full_engine):
        engine, graph, cache = full_engine

        # Mock: notebook lookup
        graph.get_all.side_effect = self._graph_get_all_handler

        # Mock: list lookup - find_list_by_name calls get_all
        # We need to handle all get_all calls properly
        graph.get.side_effect = self._graph_get_handler

        # Mock: section creation
        graph.post.return_value = CREATED_PAGE

        # Initialize engine
        engine._initialize()

        assert engine._notebook_id == "nb-123"
        assert len(engine._list_ids) == 3

        # Now mock task fetching for sync cycle
        tasks_by_list = {
            "list-hoy": [
                {
                    "id": "int-task-1",
                    "title": "Pagar teléfono",
                    "status": "notStarted",
                    "body": {"contentType": "text", "content": ""},
                    "dueDateTime": None,
                    "lastModifiedDateTime": "2025-01-15T10:00:00Z",
                },
                {
                    "id": "int-task-2",
                    "title": "Investigar frameworks para el proyecto de automatización",
                    "status": "notStarted",
                    "body": {"contentType": "text", "content": "Ver FastAPI vs Django"},
                    "dueDateTime": {
                        "dateTime": "2025-01-22T00:00:00.0000000",
                        "timeZone": "UTC",
                    },
                    "lastModifiedDateTime": "2025-01-15T10:00:00Z",
                },
            ],
            "list-semana": [],
            "list-espera": [],
        }

        # Override get_all for task fetching
        def get_all_for_tasks(url, params=None):
            for list_id, tasks in tasks_by_list.items():
                if list_id in url:
                    return tasks
            return self._graph_get_all_handler(url, params)

        graph.get_all.side_effect = get_all_for_tasks
        graph.post.return_value = CREATED_PAGE
        graph.get.side_effect = lambda url, params=None: {
            "id": "page-123",
            "links": {"oneNoteWebUrl": {"href": "https://onenote.com/page-123"}},
        }
        graph.patch.return_value = {}

        # Run one sync cycle
        engine._sync_cycle()

        # Verify: simple task cached but no OneNote page
        simple = cache.get_task("int-task-1")
        assert simple is not None
        assert simple["needs_onenote"] == 0

        # Verify: complex task got OneNote page + calendar event
        complex_task = cache.get_task("int-task-2")
        assert complex_task is not None
        assert complex_task["needs_onenote"] == 1
        assert complex_task["onenote_page_id"] == "page-123"

        # Verify sync log
        rows = cache.conn.execute("SELECT * FROM sync_log").fetchall()
        assert len(rows) > 0

    @staticmethod
    def _graph_get_all_handler(url, params=None):
        if "notebooks" in url:
            return NOTEBOOKS["value"]
        if "sections" in url:
            return SECTIONS["value"]
        if "todo/lists" in url and "tasks" not in url:
            return TODO_LISTS["value"]
        return []

    @staticmethod
    def _graph_get_handler(url, params=None):
        return {}
