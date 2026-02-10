import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.auth import AuthManager, SCOPES, create_auth


class TestAuthManager:
    @patch("src.auth.msal.PublicClientApplication")
    def test_silent_token_acquisition(self, mock_app_cls):
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_app.get_accounts.return_value = [{"username": "test@test.com"}]
        mock_app.acquire_token_silent.return_value = {
            "access_token": "test-token-123"
        }

        auth = AuthManager(
            client_id="test-id",
            authority="https://login.microsoftonline.com/consumers",
            scopes=SCOPES,
            cache_path="/tmp/test_cache.json",
            label="test",
        )
        token = auth.get_token()

        assert token == "test-token-123"
        mock_app.acquire_token_silent.assert_called_once_with(
            SCOPES, account={"username": "test@test.com"}
        )

    @patch("src.auth.msal.PublicClientApplication")
    def test_device_code_flow_when_no_accounts(self, mock_app_cls):
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_app.get_accounts.return_value = []
        mock_app.initiate_device_flow.return_value = {
            "user_code": "ABC123",
            "message": "Go to https://microsoft.com/devicelogin",
        }
        mock_app.acquire_token_by_device_flow.return_value = {
            "access_token": "new-token-456"
        }

        auth = AuthManager(
            client_id="test-id",
            authority="https://login.microsoftonline.com/consumers",
            scopes=SCOPES,
            cache_path="/tmp/test_cache.json",
            label="test",
        )
        token = auth.get_token()

        assert token == "new-token-456"
        mock_app.initiate_device_flow.assert_called_once()

    @patch("src.auth.msal.PublicClientApplication")
    def test_device_code_flow_failure(self, mock_app_cls):
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_app.get_accounts.return_value = []
        mock_app.initiate_device_flow.return_value = {
            "error": "authorization_pending"
        }

        auth = AuthManager(
            client_id="test-id",
            authority="https://login.microsoftonline.com/consumers",
            scopes=SCOPES,
            cache_path="/tmp/test_cache.json",
            label="test",
        )

        with pytest.raises(RuntimeError, match="Failed to create device flow"):
            auth.get_token()

    @patch("src.auth.msal.PublicClientApplication")
    def test_silent_fails_then_device_code(self, mock_app_cls):
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_app.get_accounts.return_value = [{"username": "test@test.com"}]
        mock_app.acquire_token_silent.return_value = {
            "error": "interaction_required",
            "error_description": "Need to re-authenticate",
        }
        mock_app.initiate_device_flow.return_value = {
            "user_code": "XYZ789",
            "message": "Go to https://microsoft.com/devicelogin",
        }
        mock_app.acquire_token_by_device_flow.return_value = {
            "access_token": "refreshed-token"
        }

        auth = AuthManager(
            client_id="test-id",
            authority="https://login.microsoftonline.com/consumers",
            scopes=SCOPES,
            cache_path="/tmp/test_cache.json",
            label="test",
        )
        token = auth.get_token()

        assert token == "refreshed-token"

    @patch("src.auth.requests.get")
    @patch("src.auth.msal.PublicClientApplication")
    def test_verify_connection(self, mock_app_cls, mock_get):
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_app.get_accounts.return_value = [{"username": "test@test.com"}]
        mock_app.acquire_token_silent.return_value = {
            "access_token": "test-token"
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "displayName": "Kevin",
            "mail": "kevin@test.com",
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        auth = AuthManager(
            client_id="test-id",
            authority="https://login.microsoftonline.com/consumers",
            scopes=SCOPES,
            cache_path="/tmp/test_cache.json",
            label="test",
        )
        user = auth.verify_connection()

        assert user["displayName"] == "Kevin"
        mock_get.assert_called_once()


class TestAuthFactory:
    @patch("src.auth.msal.PublicClientApplication")
    def test_create_auth(self, mock_app_cls):
        auth = create_auth("client-123")
        assert auth.label == "personal"
        assert "consumers" in auth.authority
        assert auth.scopes == SCOPES
