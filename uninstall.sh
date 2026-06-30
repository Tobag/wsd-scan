#!/bin/bash
# uninstall.sh — remove the wsd-scan install footprint
#
# Reads .install-record (written by install.sh) to know exactly what to
# remove, then undoes it:
#   - stops + disables the systemd service, removes the unit, daemon-reload
#   - pip-uninstalls the package from the project venv
#
# Leaves intact: repo, .venv dir, scans, profiles.
# No ~/.local/bin wrapper removal — handle that manually.

set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECORD="$REPO_DIR/.install-record"

if [[ ! -f "$RECORD" ]]; then
    echo "ERROR: $RECORD not found." >&2
    echo "Either wsd-scan was not installed via install.sh, or the record was deleted." >&2
    echo "To remove manually: systemctl stop/disable wsd-scan, rm the unit, pip uninstall wsd-scan." >&2
    exit 1
fi

source "$RECORD"

echo "=== wsd-scan uninstaller ==="
echo "Mode:     $INSTALL_MODE"
echo "Service:  $SERVICE_NAME"
echo "Unit:     $UNIT_PATH"
echo "Venv:     $VENV_PATH"
echo

removed=()

# Build the systemctl prefix for this mode
if [[ "$INSTALL_MODE" == "user" ]]; then
    SCTL="systemctl --user"
else
    SCTL="sudo systemctl"
fi

# 1. systemd service
if $SCTL list-unit-files 2>/dev/null | grep -q "$SERVICE_NAME"; then
    echo "[1/2] Stopping + disabling service..."
    $SCTL stop "$SERVICE_NAME" 2>/dev/null || true
    $SCTL disable "$SERVICE_NAME" 2>/dev/null || true
    removed+=("service (stopped + disabled)")
else
    echo "[1/2] Service not registered."
fi

if [[ -f "$UNIT_PATH" ]]; then
    echo "      Removing unit: $UNIT_PATH"
    if [[ "$INSTALL_MODE" == "user" ]]; then
        rm -f "$UNIT_PATH"
    else
        sudo rm -f "$UNIT_PATH"
    fi
    $SCTL daemon-reload
    $SCTL reset-failed "$SERVICE_NAME" 2>/dev/null || true
    removed+=("unit file removed + daemon-reload")
fi

# 2. pip package
if [[ -d "$VENV_PATH" ]] && "$VENV_PATH/bin/pip" show "$PACKAGE_NAME" >/dev/null 2>&1; then
    echo "[2/2] Uninstalling pip package..."
    "$VENV_PATH/bin/pip" uninstall -y "$PACKAGE_NAME" -q
    removed+=("pip package $PACKAGE_NAME (from $VENV_PATH)")
else
    echo "[2/2] No pip package in venv."
fi

# Summary
echo
if [[ ${#removed[@]} -eq 0 ]]; then
    echo "=== Nothing to remove — already clean. ==="
else
    echo "=== Removed ==="
    for r in "${removed[@]}"; do
        echo "  - $r"
    done
fi
echo
echo "=== Left intact ==="
echo "  - repo:     $REPO_DIR"
echo "  - venv dir: $VENV_PATH  (rm -rf to purge)"
echo "  - scans:    $SCAN_DIR"
echo "  - profiles: $REPO_DIR/wsd_scan/profiles/"

# Remove the record itself
rm -f "$RECORD"
echo "  - removed .install-record"
