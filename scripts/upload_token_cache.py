#!/usr/bin/env python3
"""Upload local MSAL token cache to Azure Blob Storage.

Usage:
    python scripts/upload_token_cache.py

Requires:
    - A valid token_cache.json at ~/.onenote-todo-sync/token_cache.json
      (run `python -m src.main --auth` first to generate it)
    - AZURE_STORAGE_CONNECTION_STRING env var or .env file
"""

import argparse
import os
import sys

from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONTAINER = "sync-data"
LOCAL_CACHE = os.path.expanduser("~/.onenote-todo-sync/token_cache.json")


def main():
    parser = argparse.ArgumentParser(description="Upload MSAL token cache to Azure Blob Storage")
    parser.add_argument(
        "--blob-name", default="token_cache.json",
        help="Blob name in sync-data container (default: token_cache.json)",
    )
    args = parser.parse_args()
    blob_name = args.blob_name

    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not connection_string:
        print("ERROR: Set AZURE_STORAGE_CONNECTION_STRING in .env or environment")
        sys.exit(1)

    if not os.path.exists(LOCAL_CACHE):
        print(f"ERROR: Token cache not found at {LOCAL_CACHE}")
        print("Run 'python -m src.main --auth' first to authenticate and create it.")
        sys.exit(1)

    from azure.storage.blob import BlobServiceClient

    blob_service = BlobServiceClient.from_connection_string(connection_string)
    container_client = blob_service.get_container_client(CONTAINER)

    try:
        container_client.create_container()
        print(f"Created container '{CONTAINER}'")
    except Exception:
        print(f"Container '{CONTAINER}' already exists")

    with open(LOCAL_CACHE, "r") as f:
        data = f.read()

    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(data, overwrite=True)

    print(f"Uploaded {LOCAL_CACHE} -> {CONTAINER}/{blob_name}")
    print("Token cache is now available for Azure Functions.")


if __name__ == "__main__":
    main()
