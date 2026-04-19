#!/usr/bin/env bash
# ============================================================================
# Airsoft Prop — Update Script
# Pulls latest code from git and restarts the service.
# ============================================================================
set -euo pipefail

INSTALL_DIR="/home/pi/airsoft-prop"
VENV_DIR="$INSTALL_DIR/venv"
SERVICE_NAME="airsoft-prop"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

if [[ ! -d "$INSTALL_DIR/.git" ]]; then
    error "No git repository found at $INSTALL_DIR. Run install.sh first."
fi

cd "$INSTALL_DIR"

# ---------------------------------------------------------------------------
# Check for updates
# ---------------------------------------------------------------------------

info "Fetching latest changes..."
git fetch --tags origin

LOCAL=$(git describe --tags --always 2>/dev/null || git rev-parse --short HEAD)
REMOTE=$(git describe --tags --always origin/main 2>/dev/null || git describe --tags --always origin/master 2>/dev/null)

if [[ "$LOCAL" == "$REMOTE" ]]; then
    info "Already up to date!"
    exit 0
fi

BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null || git rev-list --count HEAD..origin/master 2>/dev/null || echo "?")
info "Update available: $BEHIND commit(s) behind"

# ---------------------------------------------------------------------------
# Apply update
# ---------------------------------------------------------------------------

info "Pulling latest code..."
git pull origin main 2>/dev/null || git pull origin master

# Write VERSION file so the app can display the installed version
# without relying on git describe at runtime (which may fail in systemd's PATH).
git describe --tags --always 2>/dev/null | sed 's/^[vV]//' > "$INSTALL_DIR/VERSION" || true

info "Updating Python dependencies..."
"$VENV_DIR/bin/pip" install --no-cache-dir --quiet -r requirements.txt

# Update Pi-specific packages if requirements-pi.txt exists
if [[ -f "$INSTALL_DIR/requirements-pi.txt" ]]; then
    info "Updating Pi-specific Python packages..."
    "$VENV_DIR/bin/pip" install --no-cache-dir --quiet -r requirements-pi.txt
fi

# ---------------------------------------------------------------------------
# Restart service
# ---------------------------------------------------------------------------

info "Restarting service..."
if systemctl is-active --quiet "$SERVICE_NAME"; then
    sudo systemctl restart "$SERVICE_NAME"
    info "Service restarted"
else
    warn "Service not running. Start it with: sudo systemctl start $SERVICE_NAME"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

NEW_VERSION=$(git describe --tags --always 2>/dev/null || git rev-parse --short HEAD)
echo ""
echo -e "${GREEN}Update complete!${NC} Now at: $NEW_VERSION"
echo ""
