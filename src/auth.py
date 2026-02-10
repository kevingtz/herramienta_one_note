from __future__ import annotations

import json
import logging
import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import msal
import requests

logger = logging.getLogger("onenote_todo_sync")

SCOPES = [
    "https://graph.microsoft.com/Tasks.ReadWrite",
    "https://graph.microsoft.com/Notes.ReadWrite",
    "https://graph.microsoft.com/Calendars.ReadWrite",
    "https://graph.microsoft.com/User.Read",
]

TOKEN_CACHE_DIR = os.path.expanduser("~/.onenote-todo-sync")
TOKEN_CACHE_PATH = os.path.join(TOKEN_CACHE_DIR, "token_cache.json")


class AuthManager:
    """Handles MSAL device code flow authentication with persistent token cache."""

    def __init__(self, client_id: str, authority: str, scopes: list, cache_path: str,
                 label: str = "", auth_flow: str = "device_code"):
        self.client_id = client_id
        self.authority = authority
        self.scopes = scopes
        self.cache_path = cache_path
        self.label = label or authority
        self.auth_flow = auth_flow
        self.cache = msal.SerializableTokenCache()
        self._load_cache()
        self.app = msal.PublicClientApplication(
            client_id=self.client_id,
            authority=self.authority,
            token_cache=self.cache,
        )

    def _load_cache(self):
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        if os.path.exists(self.cache_path):
            with open(self.cache_path, "r") as f:
                self.cache.deserialize(f.read())
            logger.debug("Token cache loaded from disk (%s)", self.label)

    def _save_cache(self):
        if self.cache.has_state_changed:
            with open(self.cache_path, "w") as f:
                f.write(self.cache.serialize())
            logger.debug("Token cache saved to disk (%s)", self.label)

    def get_token(self) -> str:
        """Get a valid access token, using silent auth first, then interactive flow."""
        accounts = self.app.get_accounts()
        if accounts:
            result = self.app.acquire_token_silent(self.scopes, account=accounts[0])
            if result and "access_token" in result:
                self._save_cache()
                logger.debug("Token acquired silently (%s)", self.label)
                return result["access_token"]
            if result and "error" in result:
                logger.warning(
                    "Silent token acquisition failed (%s): %s",
                    self.label, result.get("error_description"),
                )

        if self.auth_flow == "interactive":
            return self._interactive_flow()
        elif self.auth_flow == "manual":
            return self._manual_flow()
        return self._device_code_flow()

    def _device_code_flow(self) -> str:
        """Initiate device code flow for user authentication."""
        flow = self.app.initiate_device_flow(scopes=self.scopes)
        if "user_code" not in flow:
            raise RuntimeError(
                f"Failed to create device flow ({self.label}): {json.dumps(flow, indent=2)}"
            )

        msg = (
            "\n" + "=" * 60 + "\n"
            f"AUTHENTICATION REQUIRED — {self.label}\n"
            + "=" * 60 + "\n"
            + flow["message"] + "\n"
            + "=" * 60 + "\n"
        )
        print(msg)
        sys.stdout.flush()
        sys.stderr.flush()
        logger.info("Device code flow initiated (%s): %s", self.label, flow.get("message", ""))

        result = self.app.acquire_token_by_device_flow(flow)
        if "access_token" in result:
            self._save_cache()
            logger.info("Authentication successful via device code flow (%s)", self.label)
            return result["access_token"]

        error_msg = result.get("error_description", result.get("error", "Unknown error"))
        raise RuntimeError(f"Device code flow failed ({self.label}): {error_msg}")

    def _interactive_flow(self) -> str:
        """Initiate interactive browser flow for user authentication."""
        print(
            "\n" + "=" * 60 + "\n"
            f"AUTHENTICATION REQUIRED — {self.label}\n"
            + "=" * 60 + "\n"
            "A browser window will open for you to sign in.\n"
            + "=" * 60 + "\n"
        )
        sys.stdout.flush()
        logger.info("Interactive browser flow initiated (%s)", self.label)

        result = self.app.acquire_token_interactive(scopes=self.scopes)
        if "access_token" in result:
            self._save_cache()
            logger.info("Authentication successful via interactive flow (%s)", self.label)
            return result["access_token"]

        error_msg = result.get("error_description", result.get("error", "Unknown error"))
        raise RuntimeError(f"Interactive flow failed ({self.label}): {error_msg}")

    def _manual_flow(self) -> str:
        """Authorization code flow with a local HTTP server to capture the callback.

        Works with Conditional Access policies, MFA, and restrictive tenants
        because the user authenticates in their own browser.
        """
        redirect_uri = "http://localhost:8400"
        flow = self.app.initiate_auth_code_flow(
            scopes=self.scopes,
            redirect_uri=redirect_uri,
        )
        if "auth_uri" not in flow:
            raise RuntimeError(
                f"Failed to create auth code flow ({self.label}): {json.dumps(flow, indent=2)}"
            )

        print(
            "\n" + "=" * 60 + "\n"
            f"AUTHENTICATION REQUIRED — {self.label}\n"
            + "=" * 60 + "\n"
            "Open this URL in your browser to sign in:\n\n"
            f"  {flow['auth_uri']}\n\n"
            "Waiting for callback on http://localhost:8400 ...\n"
            + "=" * 60 + "\n"
        )
        sys.stdout.flush()
        logger.info("Manual auth flow initiated (%s)", self.label)

        # Capture the OAuth callback via a one-shot HTTP server
        auth_response = self._wait_for_callback(port=8400)

        result = self.app.acquire_token_by_auth_code_flow(flow, auth_response)
        if "access_token" in result:
            self._save_cache()
            logger.info("Authentication successful via manual flow (%s)", self.label)
            return result["access_token"]

        error_msg = result.get("error_description", result.get("error", "Unknown error"))
        raise RuntimeError(f"Manual auth flow failed ({self.label}): {error_msg}")

    @staticmethod
    def _wait_for_callback(port: int) -> dict:
        """Start an HTTP server and wait for the OAuth redirect callback."""
        auth_response = {}

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                qs = parse_qs(urlparse(self.path).query)
                # Flatten single-value lists for MSAL compatibility
                for key, value in qs.items():
                    auth_response[key] = value[0] if len(value) == 1 else value
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h2>Authentication complete.</h2>"
                    b"<p>You can close this tab.</p></body></html>"
                )

            def log_message(self, format, *args):
                # Suppress default HTTP log output
                pass

        server = HTTPServer(("localhost", port), CallbackHandler)
        server.handle_request()  # serve exactly one request
        server.server_close()

        if not auth_response:
            raise RuntimeError("No auth response received from callback")
        return auth_response

    def verify_connection(self) -> dict:
        """Verify the token works by calling /me endpoint."""
        token = self.get_token()
        resp = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        user = resp.json()
        logger.info("Connected as (%s): %s (%s)",
                     self.label, user.get("displayName"), user.get("mail"))
        return user


def create_auth(client_id: str,
                authority: str = "https://login.microsoftonline.com/consumers",
                auth_flow: str = "device_code",
                cache_path: str | None = None,
                label: str = "personal") -> AuthManager:
    """Create AuthManager for a Microsoft account."""
    return AuthManager(
        client_id=client_id,
        authority=authority,
        scopes=SCOPES,
        cache_path=cache_path or TOKEN_CACHE_PATH,
        label=label,
        auth_flow=auth_flow,
    )


# ---------------------------------------------------------------------------
# Azure Functions support: Blob-backed token cache + silent-only auth
# ---------------------------------------------------------------------------

class BlobTokenCacheBackend:
    """Read/write MSAL SerializableTokenCache to Azure Blob Storage."""

    CONTAINER = "sync-data"

    def __init__(self, connection_string: str, blob_name: str = "token_cache.json"):
        from azure.storage.blob import BlobServiceClient

        self.blob_name = blob_name
        self.blob_service = BlobServiceClient.from_connection_string(connection_string)
        self.container_client = self.blob_service.get_container_client(self.CONTAINER)
        try:
            self.container_client.create_container()
        except Exception:
            pass  # already exists

    def load(self, cache: msal.SerializableTokenCache):
        try:
            blob_client = self.container_client.get_blob_client(self.blob_name)
            data = blob_client.download_blob().readall().decode("utf-8")
            cache.deserialize(data)
            logger.debug("Token cache loaded from Blob Storage")
        except Exception as exc:
            logger.warning("Could not load token cache from Blob: %s", exc)

    def save(self, cache: msal.SerializableTokenCache):
        if cache.has_state_changed:
            blob_client = self.container_client.get_blob_client(self.blob_name)
            blob_client.upload_blob(cache.serialize(), overwrite=True)
            logger.debug("Token cache saved to Blob Storage")


class AzureAuthManager:
    """Auth manager for Azure Functions — silent token only, no device code flow.

    If acquire_token_silent() fails, raises RuntimeError instead of prompting
    for device code (which would hang in a serverless environment).
    """

    def __init__(self, client_id: str, authority: str, scopes: list,
                 blob_backend: BlobTokenCacheBackend, label: str = ""):
        self.client_id = client_id
        self.authority = authority
        self.scopes = scopes
        self.blob_backend = blob_backend
        self.label = label or authority
        self.cache = msal.SerializableTokenCache()
        self.blob_backend.load(self.cache)
        self.app = msal.PublicClientApplication(
            client_id=self.client_id,
            authority=self.authority,
            token_cache=self.cache,
        )

    def get_token(self) -> str:
        """Get a valid access token using silent auth only."""
        accounts = self.app.get_accounts()
        if accounts:
            result = self.app.acquire_token_silent(self.scopes, account=accounts[0])
            if result and "access_token" in result:
                self.blob_backend.save(self.cache)
                logger.debug("Token acquired silently (%s)", self.label)
                return result["access_token"]
            error = result.get("error_description", "unknown") if result else "no result"
            raise RuntimeError(
                f"Silent token acquisition failed ({self.label}): {error}. "
                "Re-upload token_cache.json with a fresh refresh token."
            )

        raise RuntimeError(
            f"No accounts in MSAL cache ({self.label}). "
            "Run scripts/upload_token_cache.py to upload a valid token cache."
        )

    def verify_connection(self) -> dict:
        """Verify the token works by calling /me endpoint."""
        token = self.get_token()
        resp = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()


def create_auth_azure(client_id: str, connection_string: str,
                      authority: str = "https://login.microsoftonline.com/consumers",
                      blob_name: str = "token_cache.json") -> AzureAuthManager:
    """Create AzureAuthManager with Blob Storage-backed token cache."""
    blob_backend = BlobTokenCacheBackend(connection_string, blob_name=blob_name)
    return AzureAuthManager(
        client_id=client_id,
        authority=authority,
        scopes=SCOPES,
        blob_backend=blob_backend,
        label="azure",
    )
