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


    @patch("src.auth.AuthManager._wait_for_callback")
    @patch("src.auth.msal.PublicClientApplication")
    def test_manual_flow_success(self, mock_app_cls, mock_wait):
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_app.get_accounts.return_value = []
        mock_app.initiate_auth_code_flow.return_value = {
            "auth_uri": "https://login.microsoftonline.com/auth?code=abc",
            "state": "xyz",
        }
        mock_wait.return_value = {"code": "auth-code-123", "state": "xyz"}
        mock_app.acquire_token_by_auth_code_flow.return_value = {
            "access_token": "manual-token-789"
        }

        auth = AuthManager(
            client_id="test-id",
            authority="https://login.microsoftonline.com/organizations",
            scopes=SCOPES,
            cache_path="/tmp/test_cache.json",
            label="work",
            auth_flow="manual",
        )
        token = auth.get_token()

        assert token == "manual-token-789"
        mock_app.initiate_auth_code_flow.assert_called_once_with(
            scopes=SCOPES,
            redirect_uri="http://localhost:8400",
        )
        mock_app.acquire_token_by_auth_code_flow.assert_called_once()

    @patch("src.auth.AuthManager._wait_for_callback")
    @patch("src.auth.msal.PublicClientApplication")
    def test_manual_flow_initiate_failure(self, mock_app_cls, mock_wait):
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_app.get_accounts.return_value = []
        mock_app.initiate_auth_code_flow.return_value = {
            "error": "invalid_client",
        }

        auth = AuthManager(
            client_id="test-id",
            authority="https://login.microsoftonline.com/organizations",
            scopes=SCOPES,
            cache_path="/tmp/test_cache.json",
            label="work",
            auth_flow="manual",
        )

        with pytest.raises(RuntimeError, match="Failed to create auth code flow"):
            auth.get_token()

    @patch("src.auth.AuthManager._wait_for_callback")
    @patch("src.auth.msal.PublicClientApplication")
    def test_manual_flow_token_exchange_failure(self, mock_app_cls, mock_wait):
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_app.get_accounts.return_value = []
        mock_app.initiate_auth_code_flow.return_value = {
            "auth_uri": "https://login.microsoftonline.com/auth",
            "state": "xyz",
        }
        mock_wait.return_value = {"code": "auth-code-123", "state": "xyz"}
        mock_app.acquire_token_by_auth_code_flow.return_value = {
            "error": "invalid_grant",
            "error_description": "Code expired",
        }

        auth = AuthManager(
            client_id="test-id",
            authority="https://login.microsoftonline.com/organizations",
            scopes=SCOPES,
            cache_path="/tmp/test_cache.json",
            label="work",
            auth_flow="manual",
        )

        with pytest.raises(RuntimeError, match="Manual auth flow failed"):
            auth.get_token()


class TestAuthFactory:
    @patch("src.auth.msal.PublicClientApplication")
    def test_create_auth(self, mock_app_cls):
        auth = create_auth("client-123")
        assert auth.label == "personal"
        assert "consumers" in auth.authority
        assert auth.scopes == SCOPES

    @patch("src.auth.msal.PublicClientApplication")
    def test_create_auth_with_custom_cache_path(self, mock_app_cls):
        auth = create_auth("client-123", cache_path="/tmp/custom_cache.json",
                           label="work")
        assert auth.cache_path == "/tmp/custom_cache.json"
        assert auth.label == "work"

    @patch("src.auth.msal.PublicClientApplication")
    def test_create_auth_default_cache_path(self, mock_app_cls):
        from src.auth import TOKEN_CACHE_PATH
        auth = create_auth("client-123")
        assert auth.cache_path == TOKEN_CACHE_PATH
