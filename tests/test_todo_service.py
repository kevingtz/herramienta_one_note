from unittest.mock import MagicMock

from src.services.todo_service import TodoService
from tests.mocks.graph_responses import TODO_LISTS, TASKS_HOY


class TestTodoService:
    def setup_method(self):
        self.graph = MagicMock()
        self.service = TodoService(self.graph)

    def test_get_lists(self):
        self.graph.get_all.return_value = TODO_LISTS["value"]
        lists = self.service.get_lists()
        assert len(lists) == 4
        self.graph.get_all.assert_called_once_with("/me/todo/lists")

    def test_find_list_by_name_found(self):
        self.graph.get_all.return_value = TODO_LISTS["value"]
        result = self.service.find_list_by_name("Hoy")
        assert result is not None
        assert result["id"] == "list-hoy"

    def test_find_list_by_name_not_found(self):
        self.graph.get_all.return_value = TODO_LISTS["value"]
        result = self.service.find_list_by_name("No existe")
        assert result is None

    def test_get_tasks(self):
        self.graph.get_all.return_value = TASKS_HOY["value"]
        tasks = self.service.get_tasks("list-hoy")
        assert len(tasks) == 3
        self.graph.get_all.assert_called_once()

    def test_get_tasks_with_filter(self):
        self.graph.get_all.return_value = []
        self.service.get_tasks("list-hoy", status_filter="notStarted")
        call_args = self.graph.get_all.call_args
        assert "$filter" in call_args[1]["params"]

    def test_get_task(self):
        self.graph.get.return_value = TASKS_HOY["value"][0]
        task = self.service.get_task("list-hoy", "task-simple-1")
        assert task["title"] == "Pagar luz"

    def test_update_task_body(self):
        self.graph.patch.return_value = {}
        self.service.update_task_body("list-hoy", "task-1", "Updated body")
        self.graph.patch.assert_called_once()
        call_json = self.graph.patch.call_args[1]["json"]
        assert call_json["body"]["content"] == "Updated body"

    def test_mark_task_completed(self):
        self.graph.patch.return_value = {}
        self.service.mark_task_completed("list-hoy", "task-1")
        call_json = self.graph.patch.call_args[1]["json"]
        assert call_json["status"] == "completed"
