#!/bin/bash
# install.sh — reproducible install of wsd-scan
#
# Default: system-wide install (sudo for systemd parts, unit in /etc/systemd/system/).
# --user:  user-level install (unit in ~/.config/systemd/user/, no sudo).
#
# If -t is not provided, auto-discovers WSD scanners on the network after
# installing the package. If -s is not provided, auto-detects the local IP
# from the default route. So a bare `./install.sh` works if there's one
# scanner on the network.
#
# Fills the wsd-scan.service template with runtime values, creates a project
# venv, pip-installs the package, enables + starts the service, and writes
# .install-record (read by uninstall.sh to undo exactly this install).
#
# No ~/.local/bin wrapper is created — set that up manually if wanted.

set -uo pipefail
# NOTE: no `set -e` — we handle errors explicitly so discovery failures
# fall back to prompting instead of aborting.

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_DIR/.venv"
RECORD="$REPO_DIR/.install-record"
TEMPLATE="$REPO_DIR/wsd-scan.service"
SERVICE="wsd-scan"
PACKAGE="wsd-scan"

# Defaults
MODE="system"
TARGET=""
SELF_IP=""
PORT=6666
SCAN_DIR=""
DISCOVERY_TIMEOUT=5

usage() {
    cat <<EOF
Usage: install.sh [OPTIONS]

Options:
  --user            User-level install (default: system-wide)
  -t, --target      Scanner WSD endpoint URL (default: auto-discover)
  -s, --self        Local IP the scanner can reach (default: auto-detect)
  -p, --port        HTTP listener port (default: $PORT)
  --scan-dir        Scan output directory (default: ~/Pictures/scans)
  --timeout         Discovery timeout in seconds (default: $DISCOVERY_TIMEOUT)
  --no-discover     Skip auto-discovery, prompt for target instead
  -h, --help        Show this help
EOF
}

NO_DISCOVER=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --user)         MODE="user"; shift ;;
        -t|--target)    TARGET="$2"; shift 2 ;;
        -s|--self)      SELF_IP="$2"; shift 2 ;;
        -p|--port)      PORT="$2"; shift 2 ;;
        --scan-dir)     SCAN_DIR="$2"; shift 2 ;;
        --timeout)      DISCOVERY_TIMEOUT="$2"; shift 2 ;;
        --no-discover)  NO_DISCOVER=1; shift ;;
        -h|--help)      usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
    esac
done

# Mode-specific paths
if [[ "$MODE" == "system" ]]; then
    UNIT_DST="/etc/systemd/system/$SERVICE.service"
    SERVICE_USER="$USER"
    WANTED_BY="multi-user.target"
else
    UNIT_DST="$HOME/.config/systemd/user/$SERVICE.service"
    SERVICE_USER=""
    WANTED_BY="default.target"
fi

[[ -z "$SCAN_DIR" ]] && SCAN_DIR="$HOME/Pictures/scans"
EXEC="$VENV_DIR/bin/$SERVICE"

echo "=== wsd-scan installer ($MODE mode) ==="
echo "Repo:     $REPO_DIR"
echo "Venv:     $VENV_DIR"
echo "Port:     $PORT"
echo "Scan dir: $SCAN_DIR"
echo "Unit:     $UNIT_DST"
[[ -n "$SERVICE_USER" ]] && echo "Run as:   $SERVICE_USER"
echo

# 1. venv + editable install
if [[ ! -d "$VENV_DIR" ]]; then
    echo "[1/4] Creating project venv..."
    python3 -m venv "$VENV_DIR"
else
    echo "[1/4] Project venv exists."
fi
echo "[2/4] Installing package (editable) into venv..."
"$VENV_DIR/bin/pip" install -e "$REPO_DIR" -q

# 2. Resolve target URL (auto-discover or prompt)
if [[ -z "$TARGET" ]]; then
    if [[ $NO_DISCOVER -eq 1 ]]; then
        read -rp "Scanner WSD endpoint URL: " TARGET
        if [[ -z "$TARGET" ]]; then
            echo "ERROR: target URL is required." >&2
            exit 1
        fi
    else
        echo "[3/4] Auto-discovering WSD scanners (${DISCOVERY_TIMEOUT}s timeout)..."
        # Inline Python: multicast probe (UDP only, fast), filter for /wsd endpoints
        DISCOVERED=$("$VENV_DIR/bin/python" -c "
from wsd_scan.wsd_discovery__operations import wsd_multicast_probe
devices = wsd_multicast_probe(timeout=$DISCOVERY_TIMEOUT)
for s in devices:
    for xaddr in s.xaddrs:
        if '/wsd' in xaddr:
            print(xaddr)
            break
" 2>/dev/null)

        if [[ -z "$DISCOVERED" ]]; then
            echo "      No scanners found via multicast."
            read -rp "      Enter scanner WSD endpoint URL manually: " TARGET
            if [[ -z "$TARGET" ]]; then
                echo "ERROR: target URL is required." >&2
                exit 1
            fi
        elif [[ $(echo "$DISCOVERED" | wc -l) -eq 1 ]]; then
            TARGET="$DISCOVERED"
            echo "      Found: $TARGET"
        else
            echo "      Found multiple scanners:"
            mapfile -t SCANNERS <<< "$DISCOVERED"
            for i in "${!SCANNERS[@]}"; do
                echo "        [$i] ${SCANNERS[$i]}"
            done
            read -rp "      Select scanner number [0]: " PICK
            PICK="${PICK:-0}"
            TARGET="${SCANNERS[$PICK]}"
            echo "      Using: $TARGET"
        fi
    fi
else
    echo "[3/4] Target specified: $TARGET"
fi

# 3. Resolve self IP (auto-detect or prompt)
if [[ -z "$SELF_IP" ]]; then
    DETECTED_IP=$(ip -4 route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[\d.]+')
    if [[ -n "$DETECTED_IP" ]]; then
        read -rp "Local IP the scanner can reach [$DETECTED_IP]: " SELF_IP
        SELF_IP="${SELF_IP:-$DETECTED_IP}"
    else
        read -rp "Local IP the scanner can reach: " SELF_IP
    fi
    if [[ -z "$SELF_IP" ]]; then
        echo "ERROR: self IP is required." >&2
        exit 1
    fi
fi

echo
echo "Target:   $TARGET"
echo "Self IP:  $SELF_IP"
echo

# 4. Fill template and install unit
echo "[4/4] Installing systemd unit..."

# Lines prefixed with #@SYSTEM are system-mode only.
# System mode: strip the prefix (keep the directive).
# User mode:   delete the line entirely.
if [[ "$MODE" == "system" ]]; then
    SYS_FILTER='s|^#@SYSTEM ||'
else
    SYS_FILTER='/^#@SYSTEM/d'
fi

TMPUNIT="$(mktemp)"
sed \
    -e "s|__EXEC__|$EXEC|g" \
    -e "s|__TARGET__|$TARGET|g" \
    -e "s|__SELF_IP__|$SELF_IP|g" \
    -e "s|__PORT__|$PORT|g" \
    -e "s|__SCAN_DIR__|$SCAN_DIR|g" \
    -e "s|__USER__|$SERVICE_USER|g" \
    -e "s|__WANTED_BY__|$WANTED_BY|g" \
    -e "$SYS_FILTER" \
    "$TEMPLATE" > "$TMPUNIT"

mkdir -p "$(dirname "$UNIT_DST")"
if [[ "$MODE" == "system" ]]; then
    sudo cp "$TMPUNIT" "$UNIT_DST"
    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE"
    if systemctl is-active --quiet "$SERVICE"; then
        echo "      Service running — restarting."
        sudo systemctl restart "$SERVICE"
    else
        sudo systemctl start "$SERVICE"
    fi
else
    cp "$TMPUNIT" "$UNIT_DST"
    systemctl --user daemon-reload
    systemctl --user enable "$SERVICE"
    if systemctl --user is-active --quiet "$SERVICE"; then
        echo "      Service running — restarting."
        systemctl --user restart "$SERVICE"
    else
        systemctl --user start "$SERVICE"
    fi
    # Survive logout
    loginctl enable-linger "$USER" 2>/dev/null || true
fi
rm -f "$TMPUNIT"

# Ensure scan dir exists (ReadWritePaths target)
mkdir -p "$SCAN_DIR"

# Write install record for uninstall.sh
cat > "$RECORD" <<EOF
# wsd-scan install record — generated by install.sh, used by uninstall.sh
# Do not edit manually. Delete to make uninstall.sh refuse to run.
INSTALL_MODE=$MODE
SERVICE_NAME=$SERVICE
PACKAGE_NAME=$PACKAGE
UNIT_PATH=$UNIT_DST
VENV_PATH=$VENV_DIR
REPO_DIR=$REPO_DIR
SCAN_DIR=$SCAN_DIR
SERVICE_USER=$SERVICE_USER
TARGET=$TARGET
SELF_IP=$SELF_IP
PORT=$PORT
EOF

echo
echo "=== Install complete ==="
if [[ "$MODE" == "system" ]]; then
    echo "Service:  $(systemctl is-enabled "$SERVICE") / $(systemctl is-active "$SERVICE")"
    echo "Logs:     journalctl -u $SERVICE -f"
else
    echo "Service:  $(systemctl --user is-enabled "$SERVICE") / $(systemctl --user is-active "$SERVICE")"
    echo "Logs:     journalctl --user -u $SERVICE -f"
fi
echo "Exec:     $EXEC"
echo "Record:   $RECORD"
echo
echo "To uninstall:  ./uninstall.sh"
