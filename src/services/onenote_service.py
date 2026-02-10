from __future__ import annotations

import logging

logger = logging.getLogger("onenote_todo_sync")

PAGE_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
</head>
<body>
    <h1>{title}</h1>
    <div>
        <h2>Objetivo</h2>
        <p>{objective}</p>
    </div>
    <div>
        <h2>Notas</h2>
        <p></p>
    </div>
    <div>
        <h2>Próximas Acciones</h2>
        <ul>
            <li></li>
        </ul>
    </div>
    <div>
        <p style="font-size:small;color:gray">
            Lista: {list_name} | Creado desde To Do Sync
        </p>
    </div>
</body>
</html>"""


class OneNoteService:
    """Operations for OneNote via Graph API."""

    def __init__(self, graph_client):
        self.client = graph_client

    def get_notebook(self, name: str) -> dict | None:
        """Find a notebook by name (filtered locally — OneNote API doesn't support $filter)."""
        notebooks = self.client.get_all("/me/onenote/notebooks")
        for nb in notebooks:
            if nb.get("displayName") == name:
                return nb
        return None

    def get_sections(self, notebook_id: str) -> list[dict]:
        """Get all sections in a notebook."""
        return self.client.get_all(
            f"/me/onenote/notebooks/{notebook_id}/sections"
        )

    def ensure_section(self, notebook_id: str, name: str) -> dict:
        """Get a section by name, creating it if it doesn't exist."""
        sections = self.get_sections(notebook_id)
        for section in sections:
            if section.get("displayName") == name:
                return section

        logger.info("Creating OneNote section: %s", name)
        return self.client.post(
            f"/me/onenote/notebooks/{notebook_id}/sections",
            json={"displayName": name},
        )

    def create_page(
        self, section_id: str, title: str, list_name: str, objective: str = ""
    ) -> dict:
        """Create a new page in a section using the task template."""
        html = PAGE_TEMPLATE.format(
            title=title,
            objective=objective or title,
            list_name=list_name,
        )
        resp = self.client.post(
            f"/me/onenote/sections/{section_id}/pages",
            data=html.encode("utf-8"),
            headers={"Content-Type": "application/xhtml+xml"},
        )
        return resp

    def get_page_link(self, page_id: str) -> str:
        """Get the web URL for a OneNote page."""
        page = self.client.get(
            f"/me/onenote/pages/{page_id}",
            params={"$select": "links"},
        )
        links = page.get("links", {})
        return links.get("oneNoteWebUrl", {}).get("href", "")
