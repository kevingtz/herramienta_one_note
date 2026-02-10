from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestFunctionApp:
    @patch("function_app.SyncEngine")
    @patch("function_app.CalendarService")
    @patch("function_app.OneNoteService")
    @patch("function_app.TodoService")
    @patch("function_app.TaskEvaluator")
    @patch("function_app.TableSyncCache")
    @patch("function_app.GraphClient")
    @patch("function_app.create_auth_azure")
    @patch("function_app.setup_logger")
    @patch("function_app._load_config")
    @patch.dict("os.environ", {
        "CLIENT_ID": "test-client-id",
        "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    })
    def test_sync_trigger_calls_run_once(
        self,
        mock_load_config,
        mock_setup_logger,
        mock_create_auth,
        mock_graph,
        mock_table_cache,
        mock_evaluator,
        mock_todo,
        mock_onenote,
        mock_calendar,
        mock_engine_cls,
    ):
        from function_app import sync_trigger

        mock_load_config.return_value = {
            "rules": {},
            "logging": {"level": "INFO"},
        }
        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine

        timer = MagicMock()
        timer.past_due = False

        sync_trigger(timer)

        mock_create_auth.assert_called_once_with(
            "test-client-id", "UseDevelopmentStorage=true",
            authority="https://login.microsoftonline.com/consumers",
            blob_name="token_cache.json",
        )
        mock_table_cache.assert_called_once_with("UseDevelopmentStorage=true", table_prefix="")
        mock_load_config.assert_called_once_with("config.yaml")
        mock_engine.run_once.assert_called_once()

    @patch("function_app.SyncEngine")
    @patch("function_app.CalendarService")
    @patch("function_app.OneNoteService")
    @patch("function_app.TodoService")
    @patch("function_app.TaskEvaluator")
    @patch("function_app.TableSyncCache")
    @patch("function_app.GraphClient")
    @patch("function_app.create_auth_azure")
    @patch("function_app.setup_logger")
    @patch("function_app._load_config")
    @patch.dict("os.environ", {
        "CLIENT_ID": "test-client-id",
        "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    })
    def test_sync_trigger_past_due(
        self,
        mock_load_config,
        mock_setup_logger,
        mock_create_auth,
        mock_graph,
        mock_table_cache,
        mock_evaluator,
        mock_todo,
        mock_onenote,
        mock_calendar,
        mock_engine_cls,
    ):
        from function_app import sync_trigger

        mock_load_config.return_value = {
            "rules": {},
            "logging": {"level": "INFO"},
        }
        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine

        timer = MagicMock()
        timer.past_due = True

        sync_trigger(timer)

        mock_engine.run_once.assert_called_once()

    @patch("function_app.SyncEngine")
    @patch("function_app.CalendarService")
    @patch("function_app.OneNoteService")
    @patch("function_app.TodoService")
    @patch("function_app.TaskEvaluator")
    @patch("function_app.TableSyncCache")
    @patch("function_app.GraphClient")
    @patch("function_app.create_auth_azure")
    @patch("function_app.setup_logger")
    @patch("function_app._load_config")
    @patch.dict("os.environ", {
        "CLIENT_ID": "test-client-id",
        "AzureWebJobsStorage": "UseDevelopmentStorage=true",
        "AUTHORITY": "https://login.microsoftonline.com/organizations",
        "TOKEN_BLOB_NAME": "token_cache_work.json",
        "TABLE_PREFIX": "Work",
        "CONFIG_FILE": "config_work.yaml",
    })
    def test_sync_trigger_with_custom_env_vars(
        self,
        mock_load_config,
        mock_setup_logger,
        mock_create_auth,
        mock_graph,
        mock_table_cache,
        mock_evaluator,
        mock_todo,
        mock_onenote,
        mock_calendar,
        mock_engine_cls,
    ):
        from function_app import sync_trigger

        mock_load_config.return_value = {
            "rules": {},
            "logging": {"level": "INFO"},
        }
        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine

        timer = MagicMock()
        timer.past_due = False

        sync_trigger(timer)

        mock_create_auth.assert_called_once_with(
            "test-client-id", "UseDevelopmentStorage=true",
            authority="https://login.microsoftonline.com/organizations",
            blob_name="token_cache_work.json",
        )
        mock_table_cache.assert_called_once_with("UseDevelopmentStorage=true", table_prefix="Work")
        mock_load_config.assert_called_once_with("config_work.yaml")
        mock_engine.run_once.assert_called_once()

    @patch("function_app.setup_logger")
    @patch("function_app._load_config")
    @patch.dict("os.environ", {
        "CLIENT_ID": "test-client-id",
        "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    })
    def test_sync_trigger_propagates_exception(
        self,
        mock_load_config,
        mock_setup_logger,
    ):
        from function_app import sync_trigger

        mock_load_config.side_effect = RuntimeError("config error")

        timer = MagicMock()
        timer.past_due = False

        with pytest.raises(RuntimeError, match="config error"):
            sync_trigger(timer)
