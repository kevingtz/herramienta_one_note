from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.auth import BlobTokenCacheBackend, create_auth_azure
from src.cache.table_cache import TableSyncCache


class TestMultiAccountParametrization:
    """Tests that verify parametrization for multi-account support."""

    @patch("azure.storage.blob.BlobServiceClient")
    def test_blob_backend_custom_blob_name(self, mock_blob_cls):
        """BlobTokenCacheBackend with custom blob_name reads/writes the correct blob."""
        mock_container = MagicMock()
        mock_blob_client = MagicMock()
        mock_blob_client.download_blob.return_value.readall.return_value = b'{"token": "x"}'
        mock_container.get_blob_client.return_value = mock_blob_client
        mock_blob_cls.from_connection_string.return_value.get_container_client.return_value = mock_container

        backend = BlobTokenCacheBackend("conn_str", blob_name="token_cache_work.json")
        assert backend.blob_name == "token_cache_work.json"

        cache = MagicMock()
        backend.load(cache)
        mock_container.get_blob_client.assert_called_with("token_cache_work.json")

    @patch("azure.storage.blob.BlobServiceClient")
    def test_blob_backend_default_blob_name(self, mock_blob_cls):
        """BlobTokenCacheBackend defaults to token_cache.json."""
        mock_container = MagicMock()
        mock_blob_cls.from_connection_string.return_value.get_container_client.return_value = mock_container

        backend = BlobTokenCacheBackend("conn_str")
        assert backend.blob_name == "token_cache.json"

    @patch("msal.PublicClientApplication")
    @patch("azure.storage.blob.BlobServiceClient")
    def test_create_auth_azure_custom_authority(self, mock_blob_cls, mock_msal):
        """create_auth_azure passes custom authority to MSAL app."""
        mock_container = MagicMock()
        mock_blob_cls.from_connection_string.return_value.get_container_client.return_value = mock_container

        manager = create_auth_azure(
            "client-id", "conn_str",
            authority="https://login.microsoftonline.com/organizations",
            blob_name="token_cache_work.json",
        )

        assert manager.authority == "https://login.microsoftonline.com/organizations"
        assert manager.blob_backend.blob_name == "token_cache_work.json"
        mock_msal.assert_called_once_with(
            client_id="client-id",
            authority="https://login.microsoftonline.com/organizations",
            token_cache=manager.cache,
        )

    @patch("msal.PublicClientApplication")
    @patch("azure.storage.blob.BlobServiceClient")
    def test_create_auth_azure_defaults(self, mock_blob_cls, mock_msal):
        """create_auth_azure defaults are backward-compatible (consumers, token_cache.json)."""
        mock_container = MagicMock()
        mock_blob_cls.from_connection_string.return_value.get_container_client.return_value = mock_container

        manager = create_auth_azure("client-id", "conn_str")

        assert manager.authority == "https://login.microsoftonline.com/consumers"
        assert manager.blob_backend.blob_name == "token_cache.json"

    def test_table_cache_with_prefix(self):
        """TableSyncCache with table_prefix creates prefixed table names."""
        with patch("src.cache.table_cache.TableServiceClient") as mock_ts:
            mock_service = MagicMock()
            mock_ts.from_connection_string.return_value = mock_service

            cache = TableSyncCache("conn_str", table_prefix="Work")

            assert cache.TASKS_TABLE == "WorkSyncedTasks"
            assert cache.LOG_TABLE == "WorkSyncLog"
            assert cache.REVIEWS_TABLE == "WorkWeeklyReviews"

            # Verify create_table was called with prefixed names
            create_calls = [c[0][0] for c in mock_service.create_table.call_args_list]
            assert "WorkSyncedTasks" in create_calls
            assert "WorkSyncLog" in create_calls
            assert "WorkWeeklyReviews" in create_calls

    def test_table_cache_without_prefix(self):
        """TableSyncCache without prefix uses default table names."""
        with patch("src.cache.table_cache.TableServiceClient") as mock_ts:
            mock_service = MagicMock()
            mock_ts.from_connection_string.return_value = mock_service

            cache = TableSyncCache("conn_str")

            assert cache.TASKS_TABLE == "SyncedTasks"
            assert cache.LOG_TABLE == "SyncLog"
            assert cache.REVIEWS_TABLE == "WeeklyReviews"
