from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.auth import AzureAuthManager, BlobTokenCacheBackend, SCOPES


class TestBlobTokenCacheBackend:
    @patch("azure.storage.blob.BlobServiceClient")
    def test_load_success(self, mock_blob_cls):
        mock_blob_client = MagicMock()
        mock_blob_client.download_blob.return_value.readall.return_value = b'{"token": "data"}'
        mock_container = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob_client
        mock_blob_cls.from_connection_string.return_value.get_container_client.return_value = mock_container

        backend = BlobTokenCacheBackend("DefaultEndpointsProtocol=https;AccountName=test")
        cache = MagicMock()
        backend.load(cache)

        cache.deserialize.assert_called_once_with('{"token": "data"}')

    @patch("azure.storage.blob.BlobServiceClient")
    def test_load_blob_not_found(self, mock_blob_cls):
        mock_container = MagicMock()
        mock_container.get_blob_client.return_value.download_blob.side_effect = Exception("Not found")
        mock_blob_cls.from_connection_string.return_value.get_container_client.return_value = mock_container

        backend = BlobTokenCacheBackend("DefaultEndpointsProtocol=https;AccountName=test")
        cache = MagicMock()
        backend.load(cache)

        cache.deserialize.assert_not_called()

    @patch("azure.storage.blob.BlobServiceClient")
    def test_save_when_changed(self, mock_blob_cls):
        mock_blob_client = MagicMock()
        mock_container = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob_client
        mock_blob_cls.from_connection_string.return_value.get_container_client.return_value = mock_container

        backend = BlobTokenCacheBackend("DefaultEndpointsProtocol=https;AccountName=test")
        cache = MagicMock()
        cache.has_state_changed = True
        cache.serialize.return_value = '{"new": "data"}'
        backend.save(cache)

        mock_blob_client.upload_blob.assert_called_once_with('{"new": "data"}', overwrite=True)

    @patch("azure.storage.blob.BlobServiceClient")
    def test_save_when_not_changed(self, mock_blob_cls):
        mock_blob_client = MagicMock()
        mock_container = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob_client
        mock_blob_cls.from_connection_string.return_value.get_container_client.return_value = mock_container

        backend = BlobTokenCacheBackend("DefaultEndpointsProtocol=https;AccountName=test")
        cache = MagicMock()
        cache.has_state_changed = False
        backend.save(cache)

        mock_blob_client.upload_blob.assert_not_called()


    @patch("azure.storage.blob.BlobServiceClient")
    def test_custom_blob_name(self, mock_blob_cls):
        mock_blob_client = MagicMock()
        mock_blob_client.download_blob.return_value.readall.return_value = b'{"token": "data"}'
        mock_container = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob_client
        mock_blob_cls.from_connection_string.return_value.get_container_client.return_value = mock_container

        backend = BlobTokenCacheBackend(
            "DefaultEndpointsProtocol=https;AccountName=test",
            blob_name="token_cache_work.json",
        )
        assert backend.blob_name == "token_cache_work.json"

        cache = MagicMock()
        backend.load(cache)
        mock_container.get_blob_client.assert_called_with("token_cache_work.json")

        cache.has_state_changed = True
        cache.serialize.return_value = '{"new": "data"}'
        backend.save(cache)
        # The last call should also be with the custom blob name
        mock_container.get_blob_client.assert_called_with("token_cache_work.json")

    @patch("azure.storage.blob.BlobServiceClient")
    def test_default_blob_name(self, mock_blob_cls):
        mock_container = MagicMock()
        mock_blob_cls.from_connection_string.return_value.get_container_client.return_value = mock_container

        backend = BlobTokenCacheBackend("DefaultEndpointsProtocol=https;AccountName=test")
        assert backend.blob_name == "token_cache.json"


class TestAzureAuthManager:
    def _make_manager(self):
        blob_backend = MagicMock()
        with patch("msal.PublicClientApplication") as mock_app_cls:
            mock_app = MagicMock()
            mock_app_cls.return_value = mock_app
            manager = AzureAuthManager(
                client_id="test-client-id",
                authority="https://login.microsoftonline.com/consumers",
                scopes=SCOPES,
                blob_backend=blob_backend,
                label="test",
            )
        return manager, mock_app, blob_backend

    def test_get_token_silent_success(self):
        manager, mock_app, blob_backend = self._make_manager()
        mock_app.get_accounts.return_value = [{"username": "user@test.com"}]
        mock_app.acquire_token_silent.return_value = {"access_token": "abc123"}

        token = manager.get_token()

        assert token == "abc123"
        blob_backend.save.assert_called_once()

    def test_get_token_no_accounts_raises(self):
        manager, mock_app, blob_backend = self._make_manager()
        mock_app.get_accounts.return_value = []

        with pytest.raises(RuntimeError, match="No accounts in MSAL cache"):
            manager.get_token()

    def test_get_token_silent_fails_raises(self):
        manager, mock_app, blob_backend = self._make_manager()
        mock_app.get_accounts.return_value = [{"username": "user@test.com"}]
        mock_app.acquire_token_silent.return_value = {
            "error": "invalid_grant",
            "error_description": "Token expired",
        }

        with pytest.raises(RuntimeError, match="Silent token acquisition failed"):
            manager.get_token()

    def test_get_token_silent_none_result_raises(self):
        manager, mock_app, blob_backend = self._make_manager()
        mock_app.get_accounts.return_value = [{"username": "user@test.com"}]
        mock_app.acquire_token_silent.return_value = None

        with pytest.raises(RuntimeError, match="Silent token acquisition failed"):
            manager.get_token()

    @patch("src.auth.requests.get")
    def test_verify_connection(self, mock_get):
        manager, mock_app, blob_backend = self._make_manager()
        mock_app.get_accounts.return_value = [{"username": "user@test.com"}]
        mock_app.acquire_token_silent.return_value = {"access_token": "abc123"}

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"displayName": "Test User", "mail": "test@test.com"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        user = manager.verify_connection()
        assert user["displayName"] == "Test User"
