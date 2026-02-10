from __future__ import annotations

import logging
import signal
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("onenote_todo_sync")


class SyncEngine:
    """Orchestrates synchronization between To Do, OneNote, and Calendar."""

    def __init__(
        self,
        todo_service,
        onenote_service,
        calendar_service,
        evaluator,
        cache,
        config: dict,
    ):
        self.todo = todo_service
        self.onenote = onenote_service
        self.calendar = calendar_service
        self.evaluator = evaluator
        self.cache = cache
        self.config = config
        self.interval = config.get("polling_interval_seconds", 30)
        self.monitored_lists = config.get("monitored_lists", [])
        self.section_map = config.get("list_to_section_map", {})
        self.weekly_config = config.get("weekly_review", {})
        self._running = True
        self._notebook_id = None
        self._sections_cache = {}
        self._list_ids = {}

    def run(self):
        """Start the polling loop. Blocks until SIGTERM/SIGINT."""
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        logger.info("Sync engine starting (interval=%ds)", self.interval)
        self._initialize()

        while self._running:
            try:
                self._sync_cycle()
            except Exception:
                logger.exception("Error in sync cycle")
                self.cache.log_action("sync_cycle_error", success=False)

            if self._running:
                time.sleep(self.interval)

        logger.info("Sync engine stopped")

    def run_once(self):
        """Execute a single sync cycle (for testing)."""
        self._initialize()
        self._sync_cycle()

    def _handle_signal(self, signum, frame):
        logger.info("Received signal %d, shutting down...", signum)
        self._running = False

    def _initialize(self):
        """Discover notebook, sections, and list IDs."""
        notebook_name = self.config.get("notebook_name", "My Notebook")
        notebook = self.onenote.get_notebook(notebook_name)
        if not notebook:
            raise RuntimeError(f"Notebook '{notebook_name}' not found")
        self._notebook_id = notebook["id"]
        logger.info("Found notebook: %s (%s)", notebook_name, self._notebook_id)

        # Ensure sections exist for each monitored list
        for list_name in self.monitored_lists:
            section_name = self.section_map.get(list_name, list_name)
            section = self.onenote.ensure_section(self._notebook_id, section_name)
            self._sections_cache[list_name] = section
            logger.info("Section '%s' ready (id=%s)", section_name, section["id"])

        # Find To Do list IDs
        for list_name in self.monitored_lists:
            todo_list = self.todo.find_list_by_name(list_name)
            if todo_list:
                self._list_ids[list_name] = todo_list["id"]
                logger.info("Found To Do list: %s (%s)", list_name, todo_list["id"])
            else:
                logger.warning("To Do list '%s' not found", list_name)

    def _sync_cycle(self):
        """Execute one full sync cycle across all monitored lists."""
        logger.debug("Starting sync cycle")

        for list_name, list_id in self._list_ids.items():
            try:
                self._sync_list(list_name, list_id)
            except Exception:
                logger.exception("Error syncing list '%s'", list_name)

        self._check_weekly_review()
        logger.debug("Sync cycle complete")

    def _sync_list(self, list_name: str, list_id: str):
        """Sync a single To Do list."""
        tasks = self.todo.get_tasks(list_id)
        remote_task_ids = set()

        for task in tasks:
            task_id = task["id"]
            remote_task_ids.add(task_id)
            cached = self.cache.get_task(task_id)
            last_modified = task.get("lastModifiedDateTime", "")

            if cached is None:
                self._handle_new_task(task, list_name, list_id)
            elif cached.get("last_modified_todo") != last_modified:
                self._handle_modified_task(task, cached, list_name, list_id)

        # Detect tasks removed from To Do
        cached_tasks = self.cache.get_tasks_by_list(list_name)
        for ct in cached_tasks:
            if ct["task_id"] not in remote_task_ids:
                self._handle_removed_task(ct)

    def _handle_new_task(self, task: dict, list_name: str, list_id: str):
        """Process a newly discovered task."""
        title = task.get("title", "")
        task_id = task["id"]
        logger.info("New task found: '%s' in list '%s'", title, list_name)

        needs_onenote = self.evaluator.needs_onenote(task)

        cache_data = {
            "task_id": task_id,
            "list_id": list_id,
            "list_name": list_name,
            "title": title,
            "status": task.get("status", "notStarted"),
            "due_date": self._extract_due_date(task),
            "last_modified_todo": task.get("lastModifiedDateTime", ""),
            "needs_onenote": 1 if needs_onenote else 0,
        }

        if needs_onenote:
            self._create_onenote_page(task, list_name, list_id, cache_data)

        due_date = self._extract_due_date(task)
        if due_date:
            self._sync_calendar_event(task, cache_data)

        self.cache.upsert_task(cache_data)
        self.cache.log_action("new_task_synced", task_id=task_id, details=title)

    def _handle_modified_task(
        self, task: dict, cached: dict, list_name: str, list_id: str
    ):
        """Process a task that has been modified since last sync."""
        title = task.get("title", "")
        task_id = task["id"]
        logger.info("Modified task: '%s'", title)

        new_status = task.get("status", "notStarted")
        cache_data = {
            "task_id": task_id,
            "list_id": list_id,
            "list_name": list_name,
            "title": title,
            "status": new_status,
            "due_date": self._extract_due_date(task),
            "last_modified_todo": task.get("lastModifiedDateTime", ""),
            "onenote_page_id": cached.get("onenote_page_id"),
            "onenote_link": cached.get("onenote_link"),
            "calendar_event_id": cached.get("calendar_event_id"),
            "needs_onenote": cached.get("needs_onenote", 0),
        }

        # If task was completed, update calendar event
        if new_status == "completed" and cached.get("status") != "completed":
            if cached.get("calendar_event_id"):
                try:
                    self.calendar.update_event(
                        cached["calendar_event_id"],
                        {"subject": f"[Completada] {title}"},
                    )
                    logger.info("Marked calendar event as completed for: %s", title)
                except Exception:
                    logger.exception("Failed to update calendar event")

        # Sync due date changes to calendar
        new_due = self._extract_due_date(task)
        old_due = cached.get("due_date")
        if new_due and new_due != old_due:
            self._sync_calendar_event(task, cache_data)

        self.cache.upsert_task(cache_data)
        self.cache.log_action("task_updated", task_id=task_id, details=title)

    def _handle_removed_task(self, cached: dict):
        """Handle a task that no longer exists in To Do."""
        task_id = cached["task_id"]
        title = cached.get("title", "")
        logger.info("Task removed from To Do: '%s'", title)

        if cached.get("calendar_event_id"):
            try:
                self.calendar.delete_event(cached["calendar_event_id"])
            except Exception:
                logger.exception("Failed to delete calendar event for removed task")

        self.cache.delete_task(task_id)
        self.cache.log_action("task_removed", task_id=task_id, details=title)

    def _create_onenote_page(
        self, task: dict, list_name: str, list_id: str, cache_data: dict
    ):
        """Create a OneNote page for a task and link it back."""
        title = task.get("title", "")
        section = self._sections_cache.get(list_name)
        if not section:
            logger.warning("No section cached for list '%s'", list_name)
            return

        try:
            body = task.get("body", {})
            objective = ""
            if isinstance(body, dict):
                objective = body.get("content", "")

            page = self.onenote.create_page(
                section_id=section["id"],
                title=title,
                list_name=list_name,
                objective=objective,
            )
            page_id = page.get("id", "")
            link = self.onenote.get_page_link(page_id) if page_id else ""

            cache_data["onenote_page_id"] = page_id
            cache_data["onenote_link"] = link

            if link:
                existing_body = task.get("body", {})
                existing_content = ""
                if isinstance(existing_body, dict):
                    existing_content = existing_body.get("content", "")
                new_content = f"{existing_content}\n\nOneNote: {link}".strip()
                self.todo.update_task_body(list_id, task["id"], new_content)

            logger.info("Created OneNote page for: %s", title)
            self.cache.log_action(
                "create_page", task_id=task["id"], details=title
            )
        except Exception:
            logger.exception("Failed to create OneNote page for: %s", title)
            self.cache.log_action(
                "create_page", task_id=task["id"], details=title, success=False
            )

    def _sync_calendar_event(self, task: dict, cache_data: dict):
        """Create or update a calendar event for a task with a due date."""
        title = task.get("title", "")
        due_date_str = self._extract_due_date(task)
        if not due_date_str:
            return

        try:
            # Truncate fractional seconds to 6 digits for Python 3.9 compat
            clean = due_date_str.replace("Z", "+00:00")
            if "." in clean:
                base, frac_and_rest = clean.split(".", 1)
                # Separate fractional digits from timezone suffix
                frac_digits = ""
                rest = ""
                for i, ch in enumerate(frac_and_rest):
                    if ch.isdigit():
                        frac_digits += ch
                    else:
                        rest = frac_and_rest[i:]
                        break
                clean = f"{base}.{frac_digits[:6]}{rest}"
            due_dt = datetime.fromisoformat(clean)
            start = due_dt.replace(hour=9, minute=0, second=0)

            existing_event_id = cache_data.get("calendar_event_id")
            if existing_event_id:
                self.calendar.update_event(
                    existing_event_id,
                    {
                        "subject": f"[To Do] {title}",
                        "start": {
                            "dateTime": start.isoformat(),
                            "timeZone": "America/Mexico_City",
                        },
                        "end": {
                            "dateTime": (start + timedelta(hours=1)).isoformat(),
                            "timeZone": "America/Mexico_City",
                        },
                    },
                )
            else:
                event = self.calendar.create_event(
                    subject=f"[To Do] {title}",
                    start=start,
                    body=f"Tarea de lista: {cache_data.get('list_name', '')}",
                )
                cache_data["calendar_event_id"] = event.get("id", "")

            self.cache.log_action(
                "sync_calendar", task_id=task["id"], details=title
            )
        except Exception:
            logger.exception("Failed to sync calendar for: %s", title)

    def _check_weekly_review(self):
        """Create weekly review event if configured and not yet created this week."""
        if not self.weekly_config.get("enabled", False):
            return

        now = datetime.now(timezone.utc)
        target_day = self.weekly_config.get("day", "sunday").lower()
        days = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6,
        }
        target_weekday = days.get(target_day, 6)

        # Calculate next occurrence of target day
        days_ahead = target_weekday - now.weekday()
        if days_ahead < 0:
            days_ahead += 7
        next_date = now.date() + timedelta(days=days_ahead)
        week_start = str(next_date - timedelta(days=next_date.weekday()))

        if self.cache.get_weekly_review(week_start):
            return

        try:
            time_parts = self.weekly_config.get("time", "18:00").split(":")
            hour, minute = int(time_parts[0]), int(time_parts[1])
            start = datetime(
                next_date.year, next_date.month, next_date.day, hour, minute,
            )

            # Build summary of pending tasks
            all_tasks = self.cache.get_all_tasks()
            pending = [t for t in all_tasks if t["status"] != "completed"]
            summary_lines = []
            for t in pending:
                summary_lines.append(f"- [{t['list_name']}] {t['title']}")
            summary = "\n".join(summary_lines) if summary_lines else "No hay tareas pendientes."

            duration = self.weekly_config.get("duration_minutes", 30)
            event = self.calendar.create_weekly_review(start, duration, summary)
            self.cache.save_weekly_review(event.get("id", ""), week_start)
            self.cache.log_action("create_weekly_review", details=week_start)
            logger.info("Created weekly review event for week of %s", week_start)
        except Exception:
            logger.exception("Failed to create weekly review")

    @staticmethod
    def _extract_due_date(task: dict) -> str | None:
        """Extract due date string from a task."""
        due = task.get("dueDateTime")
        if due and isinstance(due, dict):
            return due.get("dateTime")
        return None
