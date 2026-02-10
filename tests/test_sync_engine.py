from unittest.mock import MagicMock, patch

import pytest

from src.cache.local_cache import SyncCache
from src.rules.evaluator import TaskEvaluator
from src.services.sync_engine import SyncEngine
from tests.mocks.graph_responses import (
    NOTEBOOKS, SECTIONS, CREATED_SECTION, CREATED_PAGE, PAGE_WITH_LINK,
    TODO_LISTS, TASKS_HOY, TASKS_SEMANA, TASKS_ESPERA, CREATED_EVENT,
)


@pytest.fixture
def mock_services():
    todo = MagicMock()
    onenote = MagicMock()
    calendar = MagicMock()
    return todo, onenote, calendar


@pytest.fixture
def engine(config, temp_db, mock_services):
    todo, onenote, calendar = mock_services
    evaluator = TaskEvaluator(config["rules"])
    cache = SyncCache(db_path=temp_db)

    # Setup mock responses for initialization
    onenote.get_notebook.return_value = NOTEBOOKS["value"][0]
    onenote.ensure_section.side_effect = lambda nb_id, name: (
        next(
            (s for s in SECTIONS["value"] if s["displayName"] == name),
            CREATED_SECTION,
        )
    )
    todo.find_list_by_name.side_effect = lambda name: next(
        (l for l in TODO_LISTS["value"] if l["displayName"] == name), None
    )

    eng = SyncEngine(
        todo_service=todo,
        onenote_service=onenote,
        calendar_service=calendar,
        evaluator=evaluator,
        cache=cache,
        config=config,
    )
    yield eng
    cache.close()


class TestSyncEngine:
    def test_initialize(self, engine, mock_services):
        _, onenote, _ = mock_services
        engine._initialize()
        assert engine._notebook_id == "nb-123"
        assert len(engine._list_ids) == 3
        assert "Hoy" in engine._sections_cache

    def test_initialize_notebook_not_found(self, engine, mock_services):
        _, onenote, _ = mock_services
        onenote.get_notebook.return_value = None
        with pytest.raises(RuntimeError, match="not found"):
            engine._initialize()

    def test_sync_cycle_new_simple_task(self, engine, mock_services):
        todo, onenote, calendar = mock_services
        engine._initialize()

        # Return only the simple task
        simple_task = TASKS_HOY["value"][0]  # "Pagar luz"
        todo.get_tasks.return_value = [simple_task]

        engine._sync_cycle()

        # Simple task should NOT create a OneNote page
        onenote.create_page.assert_not_called()
        cached = engine.cache.get_task("task-simple-1")
        assert cached is not None
        assert cached["needs_onenote"] == 0

    def test_sync_cycle_new_complex_task(self, engine, mock_services):
        todo, onenote, calendar = mock_services
        engine._initialize()

        # Return only the complex task
        complex_task = TASKS_HOY["value"][1]  # "Investigar opciones..."
        todo.get_tasks.return_value = [complex_task]
        onenote.create_page.return_value = CREATED_PAGE
        onenote.get_page_link.return_value = "https://onenote.com/page-123"
        calendar.create_event.return_value = CREATED_EVENT

        engine._sync_cycle()

        # Complex task should create OneNote page
        onenote.create_page.assert_called_once()
        # Task has due date, should create calendar event
        calendar.create_event.assert_called_once()
        # Should update task body with OneNote link
        todo.update_task_body.assert_called_once()

        cached = engine.cache.get_task("task-complex-1")
        assert cached["needs_onenote"] == 1
        assert cached["onenote_page_id"] == "page-123"
        assert cached["calendar_event_id"] == "event-123"

    def test_sync_cycle_force_onenote_task(self, engine, mock_services):
        todo, onenote, calendar = mock_services
        engine._initialize()

        force_task = TASKS_HOY["value"][2]  # "#onenote Revisar notas"
        todo.get_tasks.return_value = [force_task]
        onenote.create_page.return_value = CREATED_PAGE
        onenote.get_page_link.return_value = "https://onenote.com/page-123"

        engine._sync_cycle()

        onenote.create_page.assert_called_once()

    def test_sync_cycle_task_completed(self, engine, mock_services):
        todo, onenote, calendar = mock_services
        engine._initialize()

        # First cycle: create task
        task = TASKS_HOY["value"][1].copy()
        todo.get_tasks.return_value = [task]
        onenote.create_page.return_value = CREATED_PAGE
        onenote.get_page_link.return_value = "https://onenote.com/page-123"
        calendar.create_event.return_value = CREATED_EVENT
        engine._sync_cycle()

        # Second cycle: task is completed
        task["status"] = "completed"
        task["lastModifiedDateTime"] = "2025-01-16T10:00:00Z"
        todo.get_tasks.return_value = [task]
        engine._sync_cycle()

        # Should update calendar event with [Completada] prefix
        calendar.update_event.assert_called()
        call_args = calendar.update_event.call_args
        assert "[Completada]" in call_args[0][1]["subject"]

    def test_sync_cycle_task_removed(self, engine, mock_services):
        todo, onenote, calendar = mock_services
        engine._initialize()

        # First cycle: add a simple task
        task = TASKS_HOY["value"][0].copy()
        task["id"] = "task-will-be-removed"
        todo.get_tasks.return_value = [task]
        engine._sync_cycle()

        assert engine.cache.get_task("task-will-be-removed") is not None

        # Second cycle: task is gone from To Do
        todo.get_tasks.return_value = []
        engine._sync_cycle()

        assert engine.cache.get_task("task-will-be-removed") is None

    def test_sync_cycle_no_changes(self, engine, mock_services):
        todo, onenote, calendar = mock_services
        engine._initialize()

        task = TASKS_HOY["value"][0].copy()
        todo.get_tasks.return_value = [task]

        # First cycle
        engine._sync_cycle()
        onenote.create_page.reset_mock()

        # Second cycle with same data - should not create anything new
        engine._sync_cycle()
        onenote.create_page.assert_not_called()

    def test_handle_signal(self, engine):
        engine._running = True
        engine._handle_signal(15, None)
        assert engine._running is False

    def test_extract_due_date(self):
        task = {"dueDateTime": {"dateTime": "2025-01-20T00:00:00.0000000", "timeZone": "UTC"}}
        assert SyncEngine._extract_due_date(task) == "2025-01-20T00:00:00.0000000"

    def test_extract_due_date_none(self):
        assert SyncEngine._extract_due_date({"dueDateTime": None}) is None
        assert SyncEngine._extract_due_date({}) is None
