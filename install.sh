#!/usr/bin/env bash
# ============================================================================
# Airsoft Prop — One-Click Installer
# Tested on: Raspberry Pi OS Lite (Bookworm / Debian 12)
# ============================================================================
set -euo pipefail

# Disable output buffering to ensure all logs are captured immediately
export PYTHONUNBUFFERED=1
export APT_LISTCHANGES_FRONTEND=none

INSTALL_DIR="/home/pi/airsoft-prop"
VENV_DIR="$INSTALL_DIR/venv"
SERVICE_NAME="airsoft-prop"
REPO_URL="https://github.com/xxdarkxx2609/airsoft-prop.git"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# Progress tracking
STEP=0
TOTAL_STEPS=8
LOGFILE="$(pwd)/install.log"
# Track whether hardware config changed (needs reboot)
NEEDS_REBOOT=false

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

info()  { echo -e "       ${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "       ${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "       ${RED}[ERROR]${NC} $1"; exit 1; }

# Print a step header with counter: [1/7] Description...
step() {
    STEP=$((STEP + 1))
    echo ""
    echo -e "${BOLD}${BLUE}[${STEP}/${TOTAL_STEPS}]${NC}${BOLD} $1${NC}"
}

# Run a command, streaming output live to both terminal and log file.
# Usage: run_logged "Description" command arg1 arg2 ...
run_logged() {
    local description="$1"
    shift
    echo -e "       ${description}..."
    echo "=== $(date '+%H:%M:%S') $description ===" >> "$LOGFILE"

    # Run in a subshell with set -e disabled so we can capture the real exit code.
    # tee streams output simultaneously to the terminal and the log file.
    # || true prevents set -e from firing on the pipeline itself.
    ( set +e; "$@" ) 2>&1 | tee -a "$LOGFILE" || true
    local exit_code=${PIPESTATUS[0]}

    if [[ $exit_code -eq 0 ]]; then
        echo -e "       ${GREEN}✓${NC} ${description} done"
        echo "=== $(date '+%H:%M:%S') SUCCESS ===" >> "$LOGFILE"
    else
        echo "" >> "$LOGFILE"
        echo "=== $(date '+%H:%M:%S') FAILED (exit code: $exit_code) ===" >> "$LOGFILE"
        if [[ $exit_code -eq 124 ]]; then
            echo -e "       ${RED}✗ TIMEOUT: ${description}${NC}"
        else
            echo -e "       ${RED}✗ FAILED (exit $exit_code): ${description}${NC}"
        fi
        exit "$exit_code"
    fi
}


# ---------------------------------------------------------------------------
# Cleanup trap — kill spinner on exit, show log hint on error
# ---------------------------------------------------------------------------

cleanup_on_exit() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        echo ""
        echo -e "${RED}============================================${NC}"
        echo -e "${RED}  Installation failed!${NC}"
        echo -e "${RED}============================================${NC}"
        echo ""
        echo -e "  Check the log file for details:"
        echo -e "  ${BOLD}${LOGFILE}${NC}"
        echo ""
    fi
}
trap cleanup_on_exit EXIT
trap 'exit 130' INT

# ---------------------------------------------------------------------------
# Pre-flight checks (interactive — before logging starts)
# ---------------------------------------------------------------------------

echo ""
echo -e "${BOLD}╔════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   Airsoft Prop — Installer                 ║${NC}"
echo -e "${BOLD}╚════════════════════════════════════════════╝${NC}"
echo ""

if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root (use: sudo bash install.sh)"
fi

# Check OS version
if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    info "Detected OS: $PRETTY_NAME"
    if [[ "$VERSION_CODENAME" != "bookworm" ]]; then
        warn "This installer is tested on Debian 12 (Bookworm)."
        warn "Your system ($VERSION_CODENAME) may work but is not officially supported."
        read -rp "       Continue anyway? [y/N] " confirm
        [[ "$confirm" =~ ^[Yy]$ ]] || exit 0
    fi
else
    warn "Cannot determine OS version. Proceeding anyway."
fi

# ---------------------------------------------------------------------------
# Initialize log file
# ---------------------------------------------------------------------------

> "$LOGFILE"
echo "Airsoft Prop — Install Log" >> "$LOGFILE"
echo "Started: $(date)" >> "$LOGFILE"
echo "========================================" >> "$LOGFILE"
echo ""
info "Logging verbose output to ${LOGFILE}"

# ---------------------------------------------------------------------------
# Step 1: System packages
# ---------------------------------------------------------------------------

step "Installing system packages"

# Attempt apt-get update with timeout and retry
run_logged "Updating package lists" \
    bash -c '
        for attempt in 1 2 3; do
            echo "[ATTEMPT $attempt/3] apt-get update..."
            if DEBIAN_FRONTEND=noninteractive timeout 120 apt-get update \
                -o APT::Acquire::Timeout=30 \
                -o APT::Acquire::ForceIPv4=true \
                -o APT::Acquire::http::Timeout=30 \
                -o Acquire::ForceIPv4=true; then
                echo "[SUCCESS] Package lists updated"
                exit 0
            fi
            echo "[TIMEOUT/FAILED] Attempt $attempt, retrying in 5 seconds..."
            sleep 5
        done
        echo "[FAILED] apt-get update failed after 3 attempts"
        exit 1
    '

run_logged "Installing Python runtime (1/5)" \
    bash -c "DEBIAN_FRONTEND=noninteractive timeout 600 apt-get install -y \
        --no-install-recommends --no-show-upgraded \
        -o APT::Acquire::Timeout=30 -o APT::Acquire::ForceIPv4=true \
        -o APT::Acquire::http::Timeout=30 -o Acquire::ForceIPv4=true \
        python3 python3-venv python3-pip python3-dev"

run_logged "Installing audio libraries — SDL2 (2/5)" \
    bash -c "DEBIAN_FRONTEND=noninteractive timeout 600 apt-get install -y \
        --no-install-recommends --no-show-upgraded \
        -o APT::Acquire::Timeout=30 -o APT::Acquire::ForceIPv4=true \
        -o APT::Acquire::http::Timeout=30 -o Acquire::ForceIPv4=true \
        libsdl2-2.0-0 libsdl2-mixer-2.0-0"

run_logged "Installing hardware interface libraries (3/5)" \
    bash -c "DEBIAN_FRONTEND=noninteractive timeout 600 apt-get install -y \
        --no-install-recommends --no-show-upgraded \
        -o APT::Acquire::Timeout=30 -o APT::Acquire::ForceIPv4=true \
        -o APT::Acquire::http::Timeout=30 -o Acquire::ForceIPv4=true \
        i2c-tools libevdev-dev"

run_logged "Installing network services — hostapd, dnsmasq, NetworkManager (4/5)" \
    bash -c "DEBIAN_FRONTEND=noninteractive timeout 600 apt-get install -y \
        --no-install-recommends --no-show-upgraded \
        -o APT::Acquire::Timeout=30 -o APT::Acquire::ForceIPv4=true \
        -o APT::Acquire::http::Timeout=30 -o Acquire::ForceIPv4=true \
        hostapd dnsmasq network-manager"

run_logged "Installing git (5/5)" \
    bash -c "DEBIAN_FRONTEND=noninteractive timeout 600 apt-get install -y \
        --no-install-recommends --no-show-upgraded \
        -o APT::Acquire::Timeout=30 -o APT::Acquire::ForceIPv4=true \
        -o APT::Acquire::http::Timeout=30 -o Acquire::ForceIPv4=true \
        git"

# Disable hostapd/dnsmasq system services — the application manages them
# directly as subprocesses with custom config files.
run_logged "Disabling hostapd/dnsmasq system services" \
    bash -c '
        systemctl stop hostapd || true
        systemctl disable hostapd || true
        systemctl mask hostapd
        systemctl stop dnsmasq || true
        systemctl disable dnsmasq || true
        systemctl mask dnsmasq
    '

# ---------------------------------------------------------------------------
# Step 2: Enable I2C
# ---------------------------------------------------------------------------

step "Enabling I2C interface"

run_logged "Configuring I2C" \
    bash -c '
        if ! grep -q "^dtparam=i2c_arm=on" /boot/firmware/config.txt 2>/dev/null; then
            echo "dtparam=i2c_arm=on" >> /boot/firmware/config.txt
            echo "[INFO] I2C enabled in /boot/firmware/config.txt"
            echo "NEEDS_REBOOT" > /tmp/airsoft-install-reboot-flag
        else
            echo "[INFO] I2C already enabled"
        fi
if ! lsmod | grep -q i2c_dev; then
            modprobe i2c-dev || true
        fi
        if ! grep -q "i2c-dev" /etc/modules; then
            echo "i2c-dev" >> /etc/modules
        fi
    '
# Check if the I2C step flagged a reboot
if [[ -f /tmp/airsoft-install-reboot-flag ]]; then
    NEEDS_REBOOT=true
    rm -f /tmp/airsoft-install-reboot-flag
fi

# ---------------------------------------------------------------------------
# Step 3: Audio output configuration
# ---------------------------------------------------------------------------

# Detect audio output type from hardware.yaml (default: usb)
AUDIO_OUTPUT="usb"
if [[ -f "$INSTALL_DIR/config/hardware.yaml" ]]; then
    _detected=$(grep -oP '^\s*output:\s*"\K[^"]+' "$INSTALL_DIR/config/hardware.yaml" 2>/dev/null || true)
    if [[ -n "$_detected" ]]; then
        AUDIO_OUTPUT="$_detected"
    fi
fi

if [[ "$AUDIO_OUTPUT" == "pwm" ]]; then
    step "Configuring audio output (PWM on GPIO18)"

    run_logged "Configuring PWM audio overlay" \
        bash -c '
            if ! grep -q "^dtoverlay=pwm" /boot/firmware/config.txt 2>/dev/null; then
                echo "dtoverlay=pwm,pin=18,func=2" >> /boot/firmware/config.txt
                echo "[INFO] PWM audio overlay added"
                echo "NEEDS_REBOOT" > /tmp/airsoft-install-reboot-flag2
            else
                echo "[INFO] PWM audio overlay already configured"
            fi
        '
    # Check if the audio step flagged a reboot
    if [[ -f /tmp/airsoft-install-reboot-flag2 ]]; then
        NEEDS_REBOOT=true
        rm -f /tmp/airsoft-install-reboot-flag2
    fi
else
    step "Configuring audio output (USB speaker)"

    # Remove PWM overlay if previously configured (avoids conflicts)
    run_logged "Removing PWM audio overlay (if present)" \
        bash -c '
            if grep -q "^dtoverlay=pwm" /boot/firmware/config.txt 2>/dev/null; then
                sed -i "/^dtoverlay=pwm/d" /boot/firmware/config.txt
                echo "[INFO] PWM audio overlay removed"
                echo "NEEDS_REBOOT" > /tmp/airsoft-install-reboot-flag2
            else
                echo "[INFO] No PWM audio overlay to remove"
            fi
        '
    if [[ -f /tmp/airsoft-install-reboot-flag2 ]]; then
        NEEDS_REBOOT=true
        rm -f /tmp/airsoft-install-reboot-flag2
    fi

    # Create ALSA config to set USB audio as default output device.
    # Auto-detect USB card number; fall back to card 0 if not found.
    run_logged "Configuring USB audio as default (ALSA)" \
        bash -c '
            USB_CARD=$(aplay -l 2>/dev/null | grep -i usb | head -1 | grep -oP "card \K\d+" || echo "0")
            ASOUNDRC="/home/pi/.asoundrc"
            cat > "$ASOUNDRC" <<ALSAEOF
# USB speaker as default audio device (set by airsoft-prop installer)
defaults.pcm.card ${USB_CARD}
defaults.ctl.card ${USB_CARD}
ALSAEOF
            chown pi:pi "$ASOUNDRC"
            echo "[INFO] ALSA configured for USB audio (card ${USB_CARD})"
        '
fi

# ---------------------------------------------------------------------------
# Step 4: Clone or update repository
# ---------------------------------------------------------------------------

step "Setting up project repository"

# Ensure git trusts the install directory (avoids safe.directory errors
# when running git commands as user pi from a root shell).
git config --global --add safe.directory "$INSTALL_DIR" >> "$LOGFILE" 2>&1

if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Existing installation found, updating..."
    cd "$INSTALL_DIR"
    run_logged "Pulling latest changes" \
        timeout 120 sudo -u pi git \
            -c http.connectTimeout=30 \
            -c http.lowSpeedLimit=1024 \
            -c http.lowSpeedTime=30 \
            pull origin main || warn "Git pull failed, continuing with existing code"
else
    run_logged "Cloning repository to ${INSTALL_DIR}" \
        timeout 180 sudo -u pi git \
            -c http.connectTimeout=30 \
            -c http.lowSpeedLimit=1024 \
            -c http.lowSpeedTime=30 \
            clone "$REPO_URL" "$INSTALL_DIR" || {
        warn "Git clone failed. Please copy the project files to $INSTALL_DIR manually."
        mkdir -p "$INSTALL_DIR"
    }
fi

cd "$INSTALL_DIR"

# Write VERSION file so the app can display the installed version
# without relying on git describe at runtime (which may fail in systemd's PATH).
# Run the full pipeline as pi so the file is owned by pi and writable by the app.
sudo -u pi bash -c "git -C '$INSTALL_DIR' describe --tags --always 2>/dev/null \
    | sed 's/^[vV]//' > '$INSTALL_DIR/VERSION'" || true

# ---------------------------------------------------------------------------
# Step 5: Python virtual environment
# ---------------------------------------------------------------------------

step "Installing Python dependencies"

if [[ ! -d "$VENV_DIR" ]]; then
    run_logged "Creating virtual environment" \
        sudo -u pi python3 -m venv "$VENV_DIR"
fi

run_logged "Upgrading pip" \
    timeout 120 sudo -u pi "$VENV_DIR/bin/pip" \
        --default-timeout=30 \
        install --no-cache-dir --upgrade pip

run_logged "Installing Python packages (requirements.txt)" \
    timeout 300 sudo -u pi "$VENV_DIR/bin/pip" \
        --default-timeout=30 \
        install --no-cache-dir -r requirements.txt

run_logged "Installing Pi-specific packages (LCD, GPIO, I2C, evdev)" \
    timeout 300 sudo -u pi "$VENV_DIR/bin/pip" \
        --default-timeout=30 \
        install --no-cache-dir -r requirements-pi.txt

# ---------------------------------------------------------------------------
# Step 6: User groups
# ---------------------------------------------------------------------------

step "Configuring user permissions"

run_logged "Adding pi user to hardware groups (i2c, gpio, audio, input)" \
    bash -c '
        usermod -aG i2c pi || true
        usermod -aG gpio pi || true
        usermod -aG audio pi || true
        usermod -aG input pi || true
    '

# Allow pi user to trigger WiFi rescans without a password.
# NetworkManager requires root/PolicyKit for rescan operations.
SUDOERS_FILE="/etc/sudoers.d/airsoft-prop-wifi"
run_logged "Configuring passwordless nmcli for pi user" \
    bash -c "
        cat > '$SUDOERS_FILE' <<'SUDOEOF'
pi ALL=(root) NOPASSWD: /usr/bin/nmcli device wifi rescan
pi ALL=(root) NOPASSWD: /usr/bin/nmcli device wifi connect *
pi ALL=(root) NOPASSWD: /usr/bin/nmcli device disconnect wlan0
pi ALL=(root) NOPASSWD: /usr/bin/nmcli connection delete *
pi ALL=(root) NOPASSWD: /usr/bin/nmcli device set wlan0 managed yes
pi ALL=(root) NOPASSWD: /usr/bin/nmcli device set wlan0 managed no
pi ALL=(root) NOPASSWD: /usr/sbin/ip addr * dev wlan0
pi ALL=(root) NOPASSWD: /usr/sbin/ip link set wlan0 *
pi ALL=(root) NOPASSWD: /usr/sbin/hostapd *
pi ALL=(root) NOPASSWD: /usr/sbin/dnsmasq *
pi ALL=(root) NOPASSWD: /usr/sbin/nft add table ip airsoft_nat
pi ALL=(root) NOPASSWD: /usr/sbin/nft add chain ip airsoft_nat prerouting *
pi ALL=(root) NOPASSWD: /usr/sbin/nft add rule ip airsoft_nat prerouting *
pi ALL=(root) NOPASSWD: /usr/sbin/nft delete table ip airsoft_nat
pi ALL=(root) NOPASSWD: /usr/bin/systemctl restart airsoft-prop
pi ALL=(root) NOPASSWD: /usr/bin/systemctl stop airsoft-prop
SUDOEOF
        chmod 0440 '$SUDOERS_FILE'
    "

# ---------------------------------------------------------------------------
# Step 7: USB automount setup
# ---------------------------------------------------------------------------

step "Configuring USB automount for key files"

# usbmount does not work on Raspberry Pi OS Bookworm (Debian 12) because
# udev workers run in a restricted mount namespace and cannot call mount(8)
# directly.  Instead we use a dedicated systemd template service triggered
# by a udev rule — the service runs outside the udev worker context.

run_logged "Removing usbmount (incompatible with Bookworm)" \
    bash -c '
        if dpkg -l usbmount 2>/dev/null | grep -q "^ii"; then
            DEBIAN_FRONTEND=noninteractive apt-get remove -y usbmount
            echo "[INFO] usbmount removed"
        else
            echo "[INFO] usbmount not installed, nothing to remove"
        fi
    '

run_logged "Creating USB mount point /media/usb" \
    bash -c '
        mkdir -p /media/usb
        echo "[INFO] /media/usb created"
    '

run_logged "Installing USB mount helper script" \
    bash -c '
        # Determine the UID/GID of the pi user (fall back to 1000)
        PI_UID=$(id -u pi 2>/dev/null || echo 1000)
        PI_GID=$(id -g pi 2>/dev/null || echo 1000)

        cat > /usr/local/bin/airsoft-usb-mount <<SCRIPT
#!/bin/bash
# airsoft-usb-mount <device> <mountpoint>
# Mounts the device with write access for the pi user.
# FAT/exFAT: uid/gid/umask options give the pi user ownership.
# ext4/others: mounted normally, then chowned so pi user can write.
DEVICE=\$1
MOUNTPOINT=\$2

mkdir -p "\$MOUNTPOINT"

# Detect filesystem type
FSTYPE=\$(blkid -o value -s TYPE "\$DEVICE" 2>/dev/null || echo "")

case "\$FSTYPE" in
    vfat|fat|fat32|fat16|msdos|exfat)
        mount "\$DEVICE" "\$MOUNTPOINT" -o noexec,nodev,noatime,nodiratime,uid=${PI_UID},gid=${PI_GID},umask=0022
        ;;
    *)
        # ext4, ntfs, or unknown — mount normally then ensure pi user can write
        mount "\$DEVICE" "\$MOUNTPOINT" -o noexec,nodev,noatime,nodiratime
        chown ${PI_UID}:${PI_GID} "\$MOUNTPOINT"
        ;;
esac
SCRIPT
        chmod +x /usr/local/bin/airsoft-usb-mount
        echo "[INFO] airsoft-usb-mount helper installed"
    '

run_logged "Installing usb-mount systemd template service" \
    bash -c '
        cat > /etc/systemd/system/usb-mount@.service <<EOF
[Unit]
Description=Mount USB stick %i
BindsTo=dev-%i.device
After=dev-%i.device

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/airsoft-usb-mount /dev/%i /media/usb
ExecStop=/bin/umount /media/usb

[Install]
WantedBy=dev-%i.device
EOF
        systemctl daemon-reload
        echo "[INFO] usb-mount@.service installed"
    '

run_logged "Installing udev rule for USB key detection" \
    bash -c '
        cat > /etc/udev/rules.d/99-airsoft-usb.rules <<EOF
# Airsoft Prop: auto-mount first USB mass storage partition for key files.
KERNEL=="sda1", SUBSYSTEMS=="usb", ACTION=="add", TAG+="systemd", ENV{SYSTEMD_WANTS}="usb-mount@sda1.service"
KERNEL=="sda1", ACTION=="remove", RUN+="/bin/systemctl stop usb-mount@sda1.service"
EOF
        udevadm control --reload-rules
        echo "[INFO] udev rule installed"
    '

# ---------------------------------------------------------------------------
# Step 8: Systemd service
# ---------------------------------------------------------------------------

step "Installing systemd service"

run_logged "Setting up ${SERVICE_NAME} service" \
    bash -c "
        sed -e 's|__INSTALL_DIR__|${INSTALL_DIR}|g' \
            -e 's|__VENV_DIR__|${VENV_DIR}|g' \
            \"${INSTALL_DIR}/systemd/airsoft-prop.service\" \
            > /etc/systemd/system/airsoft-prop.service
        systemctl daemon-reload
        systemctl enable \"$SERVICE_NAME\"
    "

# Only start the service if no reboot is pending.
# I2C and PWM overlay changes require a reboot before hardware works.
if [[ "$NEEDS_REBOOT" == "false" ]]; then
    run_logged "Starting service" \
        systemctl start "$SERVICE_NAME"
else
    info "Service NOT started — reboot required first"
fi

# ---------------------------------------------------------------------------
# Done!
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Done!
# ---------------------------------------------------------------------------

# Diagnostic: Check logfile integrity
check_log_integrity() {
    local logsize=$(stat -f%z "$LOGFILE" 2>/dev/null || stat -c%s "$LOGFILE" 2>/dev/null || echo "0")
    local error_count=$(grep -c "FAILED\|ERROR\|Timeout\|error" "$LOGFILE" 2>/dev/null || echo "0")
    local success_count=$(grep -c "SUCCESS\|done\|installed\|✓" "$LOGFILE" 2>/dev/null || echo "0")
    
    echo "Installation log diagnostics:" >> "$LOGFILE"
    echo "  - Log file size: $logsize bytes" >> "$LOGFILE"
    echo "  - Lines with [SUCCESS/done]: $success_count" >> "$LOGFILE"
    echo "  - Lines with [FAILED/ERROR]: $error_count" >> "$LOGFILE"
    
    # Warn if log is suspiciously small
    if [[ $logsize -lt 10000 ]]; then
        echo "[WARNING] Log file is very small ($logsize bytes) - possible logging issue" >> "$LOGFILE"
        warn "Log file seems small (${logsize} bytes). Check for network issues."
    fi
}
check_log_integrity

echo ""
echo "========================================" >> "$LOGFILE"
echo "Install completed: $(date)" >> "$LOGFILE"

echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Airsoft Prop installed successfully!       ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
echo ""
echo "  Installation directory: $INSTALL_DIR"
echo "  Service status: systemctl status $SERVICE_NAME"
echo "  View logs:      journalctl -u $SERVICE_NAME -f"
echo "  Install log:    $LOGFILE"
echo ""
if [[ "$NEEDS_REBOOT" == "true" ]]; then
    echo -e "  ${YELLOW}A reboot is REQUIRED to activate I2C and/or audio changes:${NC}"
    echo "    sudo reboot"
else
    echo "  The service is running. A reboot is recommended but not required."
fi
echo ""
