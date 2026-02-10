from unittest.mock import MagicMock

from src.services.onenote_service import OneNoteService
from tests.mocks.graph_responses import (
    NOTEBOOKS, SECTIONS, CREATED_SECTION, CREATED_PAGE, PAGE_WITH_LINK,
)


class TestOneNoteService:
    def setup_method(self):
        self.graph = MagicMock()
        self.service = OneNoteService(self.graph)

    def test_get_notebook_found(self):
        self.graph.get_all.return_value = NOTEBOOKS["value"]
        result = self.service.get_notebook("My Notebook")
        assert result is not None
        assert result["id"] == "nb-123"

    def test_get_notebook_not_found(self):
        self.graph.get_all.return_value = []
        result = self.service.get_notebook("Missing")
        assert result is None

    def test_get_sections(self):
        self.graph.get_all.return_value = SECTIONS["value"]
        sections = self.service.get_sections("nb-123")
        assert len(sections) == 2

    def test_ensure_section_existing(self):
        self.graph.get_all.return_value = SECTIONS["value"]
        section = self.service.ensure_section("nb-123", "Hoy")
        assert section["id"] == "sec-hoy"
        self.graph.post.assert_not_called()

    def test_ensure_section_creates_new(self):
        self.graph.get_all.return_value = SECTIONS["value"]
        self.graph.post.return_value = CREATED_SECTION
        section = self.service.ensure_section("nb-123", "En espera")
        assert section["id"] == "sec-espera-new"
        self.graph.post.assert_called_once()

    def test_create_page(self):
        self.graph.post.return_value = CREATED_PAGE
        page = self.service.create_page(
            section_id="sec-hoy",
            title="Test Task",
            list_name="Hoy",
            objective="Do the thing",
        )
        assert page["id"] == "page-123"
        call_args = self.graph.post.call_args
        assert "application/xhtml+xml" in str(call_args)

    def test_get_page_link(self):
        self.graph.get.return_value = PAGE_WITH_LINK
        link = self.service.get_page_link("page-123")
        assert link == "https://onenote.com/page-123"

    def test_get_page_link_missing(self):
        self.graph.get.return_value = {"id": "page-123", "links": {}}
        link = self.service.get_page_link("page-123")
        assert link == ""
