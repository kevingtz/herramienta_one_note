from __future__ import annotations

import logging
from datetime import datetime, timedelta

logger = logging.getLogger("onenote_todo_sync")


class CalendarService:
    """Operations for Outlook Calendar via Graph API."""

    def __init__(self, graph_client):
        self.client = graph_client

    def create_event(
        self,
        subject: str,
        start: datetime,
        end: datetime = None,
        body: str = "",
    ) -> dict:
        """Create a calendar event."""
        if end is None:
            end = start + timedelta(hours=1)

        event = {
            "subject": subject,
            "start": {
                "dateTime": start.isoformat(),
                "timeZone": "America/Mexico_City",
            },
            "end": {
                "dateTime": end.isoformat(),
                "timeZone": "America/Mexico_City",
            },
            "body": {
                "contentType": "text",
                "content": body,
            },
        }
        result = self.client.post("/me/events", json=event)
        logger.info("Created calendar event: %s", subject)
        return result

    def update_event(self, event_id: str, updates: dict) -> dict:
        """Update an existing calendar event."""
        return self.client.patch(f"/me/events/{event_id}", json=updates)

    def delete_event(self, event_id: str):
        """Delete a calendar event."""
        self.client.delete(f"/me/events/{event_id}")
        logger.info("Deleted calendar event: %s", event_id)

    def find_event_by_subject(self, subject: str) -> dict | None:
        """Find an event by exact subject match in upcoming events."""
        events = self.client.get_all(
            "/me/events",
            params={
                "$filter": f"subject eq '{subject}'",
                "$select": "id,subject,start,end",
                "$top": "1",
            },
        )
        return events[0] if events else None

    def create_weekly_review(
        self,
        start: datetime,
        duration_minutes: int,
        pending_tasks_summary: str,
    ) -> dict:
        """Create a weekly review event."""
        end = start + timedelta(minutes=duration_minutes)
        body = f"Revisión semanal de tareas pendientes:\n\n{pending_tasks_summary}"
        return self.create_event(
            subject="Revisión Semanal - Tareas",
            start=start,
            end=end,
            body=body,
        )
