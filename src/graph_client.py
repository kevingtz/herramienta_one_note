import logging
import os
import random
import time

import requests

logger = logging.getLogger("onenote_todo_sync")

BASE_URL = "https://graph.microsoft.com/v1.0"


class GraphClient:
    """HTTP client for Microsoft Graph API with retry, rate limiting, and pagination."""

    def __init__(self, auth_manager, timeout: int = 60, max_retries: int = 3):
        self.auth = auth_manager
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()

    def _headers(self) -> dict:
        token = self.auth.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Execute an HTTP request with retry and rate-limit handling."""
        if not url.startswith("http"):
            url = f"{BASE_URL}{url}"

        kwargs.setdefault("timeout", self.timeout)
        extra_headers = kwargs.pop("headers", {})

        for attempt in range(self.max_retries):
            try:
                headers = self._headers()
                headers.update(extra_headers)
                resp = self.session.request(
                    method, url, headers=headers, **kwargs
                )

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 5))
                    logger.warning("Rate limited. Waiting %ds", retry_after)
                    time.sleep(retry_after)
                    continue

                if resp.status_code == 401:
                    logger.warning(
                        "401 Unauthorized: %s", resp.text[:300]
                    )
                    if not os.environ.get("AZURE_FUNCTIONS_ENVIRONMENT"):
                        # Local: force token refresh by clearing MSAL cache accounts
                        try:
                            accounts = self.auth.app.get_accounts()
                            if accounts:
                                self.auth.app.remove_account(accounts[0])
                        except Exception:
                            pass
                    # In Azure Functions: just retry without removing the account
                    continue

                if resp.status_code >= 500:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        "Server error %d, retrying in %.1fs", resp.status_code, wait
                    )
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                return resp

            except requests.ConnectionError as e:
                wait = (2 ** attempt) + random.uniform(0, 1)
                logger.warning("Connection error: %s. Retrying in %.1fs", e, wait)
                time.sleep(wait)

        raise requests.HTTPError(
            f"Request failed after {self.max_retries} retries: {method} {url}"
        )

    def get(self, url: str, params: dict = None) -> dict:
        resp = self._request("GET", url, params=params)
        return resp.json() if resp.content else {}

    def get_all(self, url: str, params: dict = None) -> list:
        """GET with automatic pagination — follows @odata.nextLink."""
        items = []
        resp = self.get(url, params=params)
        items.extend(resp.get("value", []))

        while "@odata.nextLink" in resp:
            resp = self.get(resp["@odata.nextLink"])
            items.extend(resp.get("value", []))

        return items

    def post(self, url: str, json: dict = None, **kwargs) -> dict:
        resp = self._request("POST", url, json=json, **kwargs)
        return resp.json() if resp.content else {}

    def patch(self, url: str, json: dict = None) -> dict:
        resp = self._request("PATCH", url, json=json)
        return resp.json() if resp.content else {}

    def delete(self, url: str) -> None:
        self._request("DELETE", url)
