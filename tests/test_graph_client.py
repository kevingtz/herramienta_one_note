from unittest.mock import MagicMock, patch

import pytest
import requests

from src.graph_client import GraphClient, BASE_URL


class TestGraphClient:
    def setup_method(self):
        self.auth = MagicMock()
        self.auth.get_token.return_value = "test-token"
        self.client = GraphClient(self.auth, timeout=5, max_retries=2)

    @patch.object(requests.Session, "request")
    def test_get_request(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"value": "test"}'
        mock_resp.json.return_value = {"value": "test"}
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        result = self.client.get("/me/todo/lists")

        assert result == {"value": "test"}
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0] == ("GET", f"{BASE_URL}/me/todo/lists")
        assert "Authorization" in call_args[1]["headers"]

    @patch.object(requests.Session, "request")
    def test_get_all_with_pagination(self, mock_request):
        page1 = MagicMock()
        page1.status_code = 200
        page1.content = b'test'
        page1.json.return_value = {
            "value": [{"id": "1"}],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/next",
        }
        page1.raise_for_status = MagicMock()

        page2 = MagicMock()
        page2.status_code = 200
        page2.content = b'test'
        page2.json.return_value = {"value": [{"id": "2"}]}
        page2.raise_for_status = MagicMock()

        mock_request.side_effect = [page1, page2]

        result = self.client.get_all("/me/todo/lists")

        assert len(result) == 2
        assert result[0]["id"] == "1"
        assert result[1]["id"] == "2"

    @patch("time.sleep")
    @patch.object(requests.Session, "request")
    def test_retry_on_server_error(self, mock_request, mock_sleep):
        error_resp = MagicMock()
        error_resp.status_code = 500
        error_resp.headers = {}
        error_resp.raise_for_status = MagicMock()

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.content = b'{"ok": true}'
        success_resp.json.return_value = {"ok": True}
        success_resp.raise_for_status = MagicMock()

        mock_request.side_effect = [error_resp, success_resp]

        result = self.client.get("/me")
        assert result == {"ok": True}
        assert mock_request.call_count == 2

    @patch("time.sleep")
    @patch.object(requests.Session, "request")
    def test_rate_limit_handling(self, mock_request, mock_sleep):
        rate_resp = MagicMock()
        rate_resp.status_code = 429
        rate_resp.headers = {"Retry-After": "2"}

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.content = b'{"ok": true}'
        success_resp.json.return_value = {"ok": True}
        success_resp.raise_for_status = MagicMock()

        mock_request.side_effect = [rate_resp, success_resp]

        result = self.client.get("/me")
        assert result == {"ok": True}
        mock_sleep.assert_called_with(2)

    @patch.object(requests.Session, "request")
    def test_post_request(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.content = b'{"id": "new-123"}'
        mock_resp.json.return_value = {"id": "new-123"}
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        result = self.client.post("/me/events", json={"subject": "Test"})
        assert result["id"] == "new-123"

    @patch.object(requests.Session, "request")
    def test_delete_request(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.content = b''
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        self.client.delete("/me/events/event-123")
        mock_request.assert_called_once()

    @patch("time.sleep")
    @patch.object(requests.Session, "request")
    def test_max_retries_exceeded(self, mock_request, mock_sleep):
        error_resp = MagicMock()
        error_resp.status_code = 500
        error_resp.headers = {}
        error_resp.raise_for_status = MagicMock()
        mock_request.return_value = error_resp

        with pytest.raises(requests.HTTPError, match="failed after 2 retries"):
            self.client.get("/me")

    @patch.object(requests.Session, "request")
    def test_401_local_removes_account(self, mock_request):
        """In local mode, 401 should remove MSAL account and retry."""
        unauth_resp = MagicMock()
        unauth_resp.status_code = 401
        unauth_resp.text = "Unauthorized"

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.content = b'{"ok": true}'
        success_resp.json.return_value = {"ok": True}
        success_resp.raise_for_status = MagicMock()

        mock_request.side_effect = [unauth_resp, success_resp]

        import os
        os.environ.pop("AZURE_FUNCTIONS_ENVIRONMENT", None)

        result = self.client.get("/me")
        assert result == {"ok": True}
        self.auth.app.remove_account.assert_called_once()

    @patch.object(requests.Session, "request")
    def test_401_azure_does_not_remove_account(self, mock_request):
        """In Azure Functions, 401 should NOT remove MSAL account."""
        unauth_resp = MagicMock()
        unauth_resp.status_code = 401
        unauth_resp.text = "Unauthorized"

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.content = b'{"ok": true}'
        success_resp.json.return_value = {"ok": True}
        success_resp.raise_for_status = MagicMock()

        mock_request.side_effect = [unauth_resp, success_resp]

        import os
        os.environ["AZURE_FUNCTIONS_ENVIRONMENT"] = "Production"
        try:
            result = self.client.get("/me")
            assert result == {"ok": True}
            self.auth.app.remove_account.assert_not_called()
        finally:
            os.environ.pop("AZURE_FUNCTIONS_ENVIRONMENT", None)
