from __future__ import annotations

import logging

logger = logging.getLogger("onenote_todo_sync")


class TodoService:
    """Operations for Microsoft To Do via Graph API."""

    def __init__(self, graph_client):
        self.client = graph_client

    def get_lists(self) -> list[dict]:
        """Get all To Do task lists."""
        return self.client.get_all("/me/todo/lists")

    def find_list_by_name(self, name: str) -> dict | None:
        """Find a specific list by display name."""
        lists = self.get_lists()
        for lst in lists:
            if lst.get("displayName") == name:
                return lst
        return None

    def get_tasks(
        self,
        list_id: str,
        status_filter: str = None,
    ) -> list[dict]:
        """Get tasks from a list with optional status filter."""
        params = {}
        if status_filter:
            params["$filter"] = f"status eq '{status_filter}'"
        return self.client.get_all(f"/me/todo/lists/{list_id}/tasks", params=params or None)

    def get_task(self, list_id: str, task_id: str) -> dict:
        """Get a single task by ID."""
        return self.client.get(f"/me/todo/lists/{list_id}/tasks/{task_id}")

    def update_task_body(self, list_id: str, task_id: str, body_content: str):
        """Update the body/notes of a task (used to add OneNote link)."""
        return self.client.patch(
            f"/me/todo/lists/{list_id}/tasks/{task_id}",
            json={
                "body": {
                    "contentType": "text",
                    "content": body_content,
                }
            },
        )

    def mark_task_completed(self, list_id: str, task_id: str):
        """Mark a task as completed."""
        return self.client.patch(
            f"/me/todo/lists/{list_id}/tasks/{task_id}",
            json={"status": "completed"},
        )
