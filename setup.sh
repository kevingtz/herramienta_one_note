#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.zulunity.onenote-todo-sync.plist"
LOG_DIR="$HOME/Library/Logs/OneNoteTodoSync"
DATA_DIR="$HOME/.onenote-todo-sync"

echo "=== OneNote + To Do Sync - Setup ==="
echo ""

# 1. Check Python version
echo "[1/8] Checking Python version..."
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
if [ "$MAJOR" -lt 3 ] || { [ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 9 ]; }; then
    echo "ERROR: Python >= 3.9 required. Found $PYTHON_VERSION"
    exit 1
fi
echo "  Python $PYTHON_VERSION OK"

# 2. Check .env file
echo "[2/8] Checking .env file..."
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "ERROR: .env file not found. Create it with CLIENT_ID, CLIENT_SECRET, TENANT_ID"
    exit 1
fi
echo "  .env found"

# 3. Check Azure CLI (optional, for adding Calendar permission)
echo "[3/8] Checking Azure CLI..."
if command -v az &> /dev/null; then
    echo "  Azure CLI found"

    # Check if logged in
    if az account show &> /dev/null; then
        echo "  Azure CLI authenticated"

        # Load CLIENT_ID from .env
        CLIENT_ID=$(grep CLIENT_ID "$PROJECT_DIR/.env" | cut -d= -f2)
        if [ -n "$CLIENT_ID" ]; then
            echo "  Adding Calendars.ReadWrite permission..."
            # Microsoft Graph app ID: 00000003-0000-0000-c000-000000000000
            # Calendars.ReadWrite delegated permission ID: 1ec239c2-d7c9-4623-a91a-a9775856bb36
            az ad app permission add \
                --id "$CLIENT_ID" \
                --api 00000003-0000-0000-c000-000000000000 \
                --api-permissions 1ec239c2-d7c9-4623-a91a-a9775856bb36=Scope 2>&1 || true
            echo "  NOTE: You may need to grant admin consent in the Azure portal"
        fi
    else
        echo "  WARNING: Azure CLI not logged in. Skipping permission setup."
        echo "  Run 'az login' and re-run setup to add Calendars.ReadWrite permission."
    fi
else
    echo "  WARNING: Azure CLI not installed. Skipping permission setup."
    echo "  Install with: brew install azure-cli"
fi

# 4. Create virtual environment & install dependencies
echo "[4/8] Setting up virtual environment..."
cd "$PROJECT_DIR"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt
echo "  Dependencies installed"

# 5. Create directories
echo "[5/8] Creating directories..."
mkdir -p "$LOG_DIR"
mkdir -p "$DATA_DIR"
mkdir -p "$PROJECT_DIR/logs"
echo "  Directories created"

# 6. Authenticate (device code flow)
echo "[6/8] Running authentication..."
echo ""
python3 src/main.py --auth
echo ""

# 7. Run tests
echo "[7/8] Running tests..."
python3 -m pytest tests/ -v
echo ""

# 8. Install launchd service
echo "[8/8] Installing launchd service..."
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS_DIR"

# Unload if already loaded
if launchctl list | grep -q "$PLIST_NAME" 2>/dev/null; then
    launchctl unload "$LAUNCH_AGENTS_DIR/$PLIST_NAME" 2>/dev/null || true
fi

cp "$PROJECT_DIR/$PLIST_NAME" "$LAUNCH_AGENTS_DIR/"
launchctl load "$LAUNCH_AGENTS_DIR/$PLIST_NAME"
echo "  Service installed and started"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "The sync daemon is now running."
echo ""
echo "Useful commands:"
echo "  Check status:  launchctl list | grep onenote-todo-sync"
echo "  View logs:     tail -f ~/Library/Logs/OneNoteTodoSync/sync.log"
echo "  Stop service:  launchctl unload ~/Library/LaunchAgents/$PLIST_NAME"
echo "  Start service: launchctl load ~/Library/LaunchAgents/$PLIST_NAME"
echo "  Run once:      source venv/bin/activate && python src/main.py --once"
