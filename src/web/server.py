"""Flask web server for the Airsoft Prop.

Provides a mobile-first web interface for:
- WiFi configuration (scan, connect, manage saved networks)
- Game settings (timer defaults, volume, display)
- System info (IP, temperature, RAM, uptime)
- Software updates (check, install, restart service)

Runs in a daemon thread alongside the main game loop.
"""

from __future__ import annotations

import os
import platform
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from flask import Flask, jsonify, redirect, render_template, request

from src.hal.base import BatteryBase
from src.utils.config import Config
from src.utils.logger import get_logger
from src.web.wifi_manager import WifiManagerBase, create_wifi_manager

logger = get_logger(__name__)

_WEB_DIR = Path(__file__).parent
_TEMPLATE_DIR = _WEB_DIR / "templates"
_STATIC_DIR = _WEB_DIR / "static"


def _get_system_info() -> dict[str, Any]:
    """Gather system information."""
    info: dict[str, Any] = {
        "platform": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "hostname": platform.node(),
    }

    # CPU temperature (Raspberry Pi)
    try:
        temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
        if temp_path.exists():
            raw = temp_path.read_text().strip()
            info["cpu_temp"] = f"{int(raw) / 1000:.1f} °C"
        else:
            info["cpu_temp"] = "N/A"
    except Exception:
        info["cpu_temp"] = "N/A"

    # Uptime
    try:
        if platform.system() == "Linux":
            uptime_s = float(Path("/proc/uptime").read_text().split()[0])
            hours, remainder = divmod(int(uptime_s), 3600)
            minutes, seconds = divmod(remainder, 60)
            info["uptime"] = f"{hours}h {minutes}m {seconds}s"
        else:
            info["uptime"] = "N/A (not Linux)"
    except Exception:
        info["uptime"] = "N/A"

    # Memory
    try:
        if platform.system() == "Linux":
            meminfo = Path("/proc/meminfo").read_text()
            mem = {}
            for line in meminfo.splitlines():
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip().split()[0]
                    mem[key] = int(val)
            total = mem.get("MemTotal", 0)
            available = mem.get("MemAvailable", 0)
            used = total - available
            info["ram_total"] = f"{total // 1024} MB"
            info["ram_used"] = f"{used // 1024} MB"
            info["ram_percent"] = f"{used * 100 // total}%" if total else "N/A"
        else:
            info["ram_total"] = "N/A"
            info["ram_used"] = "N/A"
            info["ram_percent"] = "N/A"
    except Exception:
        info["ram_total"] = "N/A"
        info["ram_used"] = "N/A"
        info["ram_percent"] = "N/A"

    return info


def create_app(
    config: Config,
    mock: bool = False,
    battery: Optional[BatteryBase] = None,
    prop_app: Optional[Any] = None,
    captive_portal: Optional[Any] = None,
) -> Flask:
    """Create and configure the Flask application.

    Args:
        config: Application config instance.
        mock: If True, use mock WiFi manager.
        battery: Battery HAL instance for the /battery page.
        prop_app: The main App instance for cross-thread events.
        captive_portal: CaptivePortal instance for AP management.

    Returns:
        Configured Flask app.
    """
    app = Flask(
        __name__,
        template_folder=str(_TEMPLATE_DIR),
        static_folder=str(_STATIC_DIR),
    )
    app.config["SECRET_KEY"] = "airsoft-prop-secret"

    wifi = create_wifi_manager(mock=mock)

    # Store references for use in routes
    app.config["PROP_CONFIG"] = config
    app.config["WIFI_MANAGER"] = wifi
    app.config["MOCK_MODE"] = mock
    app.config["BATTERY"] = battery
    app.config["PROP_APP"] = prop_app
    app.config["CAPTIVE_PORTAL"] = captive_portal

    # Prevent browsers from caching API responses so that e.g. WiFi
    # scan results are always fetched fresh from nmcli.
    @app.after_request
    def _no_cache_api(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    @app.route("/")
    def index():
        """Redirect to WiFi page as main landing."""
        return render_template("wifi.html", active="wifi")

    @app.route("/wifi")
    def wifi_page():
        """WiFi configuration page."""
        return render_template("wifi.html", active="wifi")

    @app.route("/config")
    def config_page():
        """Game settings page."""
        return render_template("config.html", active="config", config=config)

    @app.route("/system")
    def system_page():
        """System information page."""
        return render_template("system.html", active="system")

    @app.route("/battery")
    def battery_page():
        """Battery information page."""
        return render_template("battery.html", active="battery")

    @app.route("/logs")
    def logs_page():
        """Log viewer page."""
        return render_template("logs.html", active="logs")

    @app.route("/tournament")
    def tournament_page():
        """Tournament mode configuration page."""
        return render_template("tournament.html", active="tournament")

    @app.route("/update")
    def update_page():
        """Software update page."""
        return render_template("update.html", active="update")

    @app.route("/hardware")
    def hardware_page():
        """Hardware module selection page."""
        return render_template("hardware.html", active="hardware")

    # ------------------------------------------------------------------
    # Hardware API
    # ------------------------------------------------------------------

    @app.route("/api/hardware", methods=["GET"])
    def api_hardware_get():
        """Return current HAL selections and available modules per component."""
        current_hal = config.get("hal", default={})
        available = config.get_all_available_hal_modules()
        return jsonify({
            "current": current_hal,
            "available": available,
        })

    @app.route("/api/hardware", methods=["POST"])
    def api_hardware_set():
        """Save HAL module selections to custom/hardware.yaml.

        Expects JSON with a flat dict mapping component names to HAL type
        strings, e.g. ``{"display": "lcd", "audio": "custom:my_audio.MyAudio"}``.
        Changes take effect after a restart.
        """
        data = request.get_json()
        if not data or not isinstance(data, dict):
            return jsonify({"success": False, "message": "No data"}), 400

        allowed_components = set(config._BUILTIN_HAL_OPTIONS.keys())
        hal_overrides: dict[str, str] = {}
        for component, value in data.items():
            if component not in allowed_components:
                return jsonify({
                    "success": False,
                    "message": f"Unknown HAL component: {component}",
                }), 400
            hal_overrides[component] = str(value)

        config.save_hardware_config(hal_overrides)
        logger.info("Hardware config updated via web interface: %s", hal_overrides)
        return jsonify({
            "success": True,
            "message": "Hardware settings saved. Restart required for changes to take effect.",
        })

    # ------------------------------------------------------------------
    # Captive portal detection
    # ------------------------------------------------------------------
    # When the Pi runs its own AP, dnsmasq redirects all DNS to the Pi.
    # Phones probe specific URLs to detect captive portals.  Returning a
    # redirect (instead of the expected response) triggers the OS to
    # open its captive-portal browser.

    def _portal_active() -> bool:
        portal = app.config.get("CAPTIVE_PORTAL")
        return portal is not None and portal.is_active()

    @app.route("/generate_204")
    @app.route("/gen_204")
    def captive_android():
        """Android / Chromebook connectivity check."""
        if _portal_active():
            return redirect("/wifi")
        return "", 204

    @app.route("/hotspot-detect.html")
    def captive_apple():
        """Apple iOS / macOS connectivity check."""
        if _portal_active():
            return redirect("/wifi")
        return (
            "<HTML><HEAD><TITLE>Success</TITLE></HEAD>"
            "<BODY>Success</BODY></HTML>"
        )

    @app.route("/connecttest.txt")
    def captive_windows():
        """Windows connectivity check."""
        if _portal_active():
            return redirect("/wifi")
        return "Microsoft Connect Test"

    @app.errorhandler(404)
    def handle_404(e):
        """Catch-all: redirect unknown URLs in AP mode (captive portal)."""
        if _portal_active():
            return redirect("/wifi")
        return "Not found", 404

    # ------------------------------------------------------------------
    # WiFi API
    # ------------------------------------------------------------------

    @app.route("/api/wifi/status")
    def api_wifi_status():
        """Get current WiFi status."""
        status = wifi.get_status()
        return jsonify({
            "connected": status.connected,
            "ssid": status.ssid,
            "ip_address": status.ip_address,
            "mac_address": status.mac_address,
            "signal": status.signal,
            "mode": status.mode,
        })

    @app.route("/api/wifi/scan")
    def api_wifi_scan():
        """Scan for available WiFi networks."""
        networks = wifi.scan()
        return jsonify([{
            "ssid": n.ssid,
            "signal": n.signal,
            "security": n.security,
            "connected": n.connected,
        } for n in networks])

    @app.route("/api/wifi/connect", methods=["POST"])
    def api_wifi_connect():
        """Connect to a WiFi network.

        If the AP is currently active, it is stopped first so that
        wlan0 can be used for the station-mode connection.
        """
        data = request.get_json()
        if not data or "ssid" not in data:
            return jsonify({"success": False, "message": "SSID required"}), 400
        ssid = data["ssid"]
        password = data.get("password", "")

        # Tear down AP before attempting station-mode connect.
        portal = app.config.get("CAPTIVE_PORTAL")
        if portal and portal.is_active():
            logger.info("Stopping AP before WiFi connect to '%s'", ssid)
            portal.stop_ap()
            # Brief pause so NM can reclaim wlan0.
            import time
            time.sleep(2)

        success, message = wifi.connect(ssid, password)

        # If connect failed and no WiFi, re-enable AP.
        if not success and portal and not portal.is_wifi_connected():
            logger.warning("WiFi connect failed — restarting AP")
            portal.start_ap()

        return jsonify({"success": success, "message": message})

    @app.route("/api/wifi/disconnect", methods=["POST"])
    def api_wifi_disconnect():
        """Disconnect from current WiFi."""
        success = wifi.disconnect()
        return jsonify({"success": success})

    @app.route("/api/wifi/saved")
    def api_wifi_saved():
        """Get saved networks."""
        return jsonify(wifi.get_saved_networks())

    @app.route("/api/wifi/forget", methods=["POST"])
    def api_wifi_forget():
        """Forget a saved network."""
        data = request.get_json()
        if not data or "ssid" not in data:
            return jsonify({"success": False}), 400
        success = wifi.forget_network(data["ssid"])
        return jsonify({"success": success})

    @app.route("/api/wifi/ap-status")
    def api_ap_status():
        """Get access point status."""
        portal = app.config.get("CAPTIVE_PORTAL")
        if portal:
            return jsonify(portal.get_ap_info())
        return jsonify({"active": False})

    # ------------------------------------------------------------------
    # Tournament API
    # ------------------------------------------------------------------

    @app.route("/api/tournament")
    def api_tournament_get():
        """Get tournament configuration and available modes."""
        ba = app.config.get("PROP_APP")

        available_modes = []
        if ba and hasattr(ba, "modes"):
            for mode in ba.modes:
                module_name = type(mode).__module__.split(".")[-1]
                # Serialize setup options
                options = []
                for opt in mode.get_setup_options():
                    options.append({
                        "key": opt.key,
                        "label": opt.label,
                        "type": opt.option_type.value,
                        "default": opt.default,
                        "min": opt.min_val,
                        "max": opt.max_val,
                        "step": opt.step,
                        "large_step": opt.large_step,
                    })
                available_modes.append({
                    "module": module_name,
                    "name": mode.name,
                    "options": options,
                })

        game_in_progress = False
        if ba and hasattr(ba, "is_game_in_progress"):
            game_in_progress = ba.is_game_in_progress()

        return jsonify({
            "enabled": config.is_tournament_enabled(),
            "mode": config.get_tournament_mode(),
            "pin": config.get_tournament_pin(),
            "settings": config.get_tournament_settings(),
            "available_modes": available_modes,
            "game_in_progress": game_in_progress,
        })

    @app.route("/api/tournament", methods=["POST"])
    def api_tournament_set():
        """Save tournament configuration."""
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data"}), 400

        ba = app.config.get("PROP_APP")

        # Block save if game is in progress
        if ba and hasattr(ba, "is_game_in_progress") and ba.is_game_in_progress():
            return jsonify({
                "success": False,
                "message": "Cannot change tournament settings while a game is in progress.",
            }), 409

        # Validate PIN
        pin = str(data.get("pin", "0000"))
        if not pin.isdigit() or len(pin) != 4:
            return jsonify({
                "success": False,
                "message": "PIN must be exactly 4 digits.",
            }), 400

        # Validate mode exists
        mode_module = data.get("mode", "random_code")
        mode_found = False
        if ba and hasattr(ba, "modes"):
            for mode in ba.modes:
                if type(mode).__module__.endswith(f".{mode_module}"):
                    mode_found = True
                    break
        if not mode_found:
            return jsonify({
                "success": False,
                "message": f"Mode '{mode_module}' not found.",
            }), 400

        # Validate code-type settings contain only digits
        settings = data.get("settings", {})
        if ba and hasattr(ba, "modes"):
            for mode in ba.modes:
                if type(mode).__module__.endswith(f".{mode_module}"):
                    for opt in mode.get_setup_options():
                        if opt.option_type.value == "code" and opt.key in settings:
                            val = str(settings[opt.key])
                            if val and not val.isdigit():
                                return jsonify({
                                    "success": False,
                                    "message": f"'{opt.label}' must contain only digits.",
                                }), 400
                    break

        # Capture current state before saving for change detection
        was_enabled = config.is_tournament_enabled()
        old_mode = config.get_tournament_mode()
        old_settings = config.get_tournament_settings()
        now_enabled = bool(data.get("enabled", False))

        overrides = {
            "tournament.enabled": now_enabled,
            "tournament.mode": mode_module,
            "tournament.pin": pin,
        }

        # Store mode-specific settings
        for key, value in settings.items():
            overrides[f"tournament.settings.{key}"] = value

        config.save_user_config(overrides)

        # Fire live transition events
        if now_enabled != was_enabled and ba:
            if now_enabled:
                logger.info("Tournament Mode ENABLED via web interface")
                ba.post_event({"type": "tournament_activate"})
            else:
                logger.info("Tournament Mode DISABLED via web interface")
                ba.post_event({"type": "tournament_deactivate"})
        elif now_enabled and was_enabled and ba:
            # Tournament already active — refresh if mode or settings changed
            if mode_module != old_mode or settings != old_settings:
                logger.info("Tournament settings changed, refreshing screen")
                ba.post_event({"type": "tournament_refresh"})

        return jsonify({"success": True, "message": "Tournament settings saved."})

    # ------------------------------------------------------------------
    # Config API
    # ------------------------------------------------------------------

    @app.route("/api/config")
    def api_config_get():
        """Get current configuration."""
        return jsonify({
            "game": {
                "default_timer": config.get("game", "default_timer", default=300),
                "min_timer": config.get("game", "min_timer", default=30),
                "max_timer": config.get("game", "max_timer", default=5999),
                "timer_step": config.get("game", "timer_step", default=30),
                "penalty_seconds": config.get("game", "penalty_seconds", default=10),
            },
            "modes": {
                "random_code": {
                    "default_digits": config.get("modes", "random_code", "default_digits", default=6),
                },
                "set_code": {
                    "max_code_length": config.get("modes", "set_code", "max_code_length", default=10),
                },
            },
            "audio": {
                "volume": config.get("audio", "volume", default=0.8),
            },
            "display": {
                "backlight": config.get("display", "backlight", default=True),
            },
            "logging": {
                "level": config.get("logging", "level", default="INFO"),
                "max_files": config.get("logging", "max_files", default=10),
            },
            "version": config.get("version", default="unknown"),
            "customized": list(config.get_customized_keys()),
        })

    @app.route("/api/config", methods=["POST"])
    def api_config_set():
        """Update configuration values.

        Expects JSON with a flat dict of dot-separated keys and values,
        e.g. {"audio.volume": 0.5, "game.default_timer": 600}
        Writes only user overrides (values differing from defaults) to user.yaml.
        """
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data"}), 400

        # Validate device_name length (max 7 chars for 20-col LCD).
        dn = data.get("game.device_name")
        if dn is not None:
            dn = str(dn).strip()
            if len(dn) > 7:
                return jsonify({
                    "success": False,
                    "message": "Device name must be 7 characters or less",
                }), 400
            if not dn:
                return jsonify({
                    "success": False,
                    "message": "Device name must not be empty",
                }), 400
            data["game.device_name"] = dn

        config.save_user_config(data)

        # Apply runtime-changeable settings immediately
        ba = app.config.get("PROP_APP")
        if ba:
            if "audio.volume" in data:
                ba.post_event({
                    "type": "audio_volume_changed",
                    "value": float(data["audio.volume"]),
                })
            if "display.backlight" in data:
                ba.post_event({
                    "type": "display_backlight_changed",
                    "value": bool(data["display.backlight"]),
                })
            if "logging.level" in data:
                ba.post_event({
                    "type": "logging_level_changed",
                    "value": str(data["logging.level"]),
                })

        logger.info("Configuration updated via web interface: %s", list(data.keys()))
        return jsonify({"success": True, "message": "Configuration saved"})

    @app.route("/api/config/reset", methods=["POST"])
    def api_config_reset():
        """Reset all settings to defaults by removing user.yaml."""
        config.reset_user_config()

        # Apply default volume and backlight immediately
        ba = app.config.get("PROP_APP")
        if ba:
            ba.post_event({
                "type": "audio_volume_changed",
                "value": config.get("audio", "volume", default=0.8),
            })
            ba.post_event({
                "type": "display_backlight_changed",
                "value": config.get("display", "backlight", default=True),
            })
            ba.post_event({
                "type": "logging_level_changed",
                "value": config.get("logging", "level", default="INFO"),
            })

        logger.info("Configuration reset to defaults via web interface")
        return jsonify({"success": True, "message": "Settings reset to defaults"})

    # ------------------------------------------------------------------
    # System API
    # ------------------------------------------------------------------

    @app.route("/api/system")
    def api_system_info():
        """Get system information."""
        info = _get_system_info()
        info["version"] = config.get("version", default="unknown")
        info["mock_mode"] = mock
        return jsonify(info)

    # ------------------------------------------------------------------
    # Battery API
    # ------------------------------------------------------------------

    @app.route("/api/battery")
    def api_battery_info():
        """Get battery status and metrics."""
        bat = app.config.get("BATTERY")
        if bat is None:
            return jsonify({"available": False})

        level = bat.get_battery_level()
        if level is None:
            return jsonify({"available": False})

        voltage = bat.get_voltage()
        current = bat.get_current()
        charging = bat.is_charging()
        plugged = bat.is_power_plugged()
        runtime = bat.get_runtime_minutes()

        return jsonify({
            "available": True,
            "level": level,
            "voltage": voltage,
            "current_ma": current,
            "charging": charging,
            "power_plugged": plugged,
            "runtime_minutes": runtime,
        })

    # ------------------------------------------------------------------
    # Logs API
    # ------------------------------------------------------------------

    @app.route("/api/logs")
    def api_logs_list():
        """List available log files (newest first)."""
        log_dir_name = config.get("logging", "log_dir", default="logs")
        log_dir = config.project_root / log_dir_name
        if not log_dir.exists():
            return jsonify([])

        files = sorted(
            log_dir.glob("prop*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return jsonify([{
            "name": f.name,
            "size": f.stat().st_size,
            "modified": f.stat().st_mtime,
        } for f in files])

    @app.route("/api/logs/<filename>")
    def api_logs_view(filename):
        """View last N lines of a log file.

        Query params:
            lines: Number of lines to return (default 200).
        """
        # Sanitize to prevent path traversal.
        if ".." in filename or "/" in filename or "\\" in filename:
            return jsonify({"error": "Invalid filename"}), 400

        log_dir_name = config.get("logging", "log_dir", default="logs")
        log_path = config.project_root / log_dir_name / filename
        if not log_path.exists():
            return jsonify({"error": "Not found"}), 404

        n_lines = int(request.args.get("lines", 200))
        try:
            content = log_path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            return jsonify({
                "filename": filename,
                "lines": lines[-n_lines:],
                "total_lines": len(lines),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ------------------------------------------------------------------
    # Update API
    # ------------------------------------------------------------------

    @app.route("/api/update/check")
    def api_update_check():
        """Check for available updates."""
        if mock:
            return jsonify({
                "available": True,
                "current_version": config.get("version", default="1.0.0"),
                "latest_version": "1.1.0",
                "message": "Mock: Update available",
            })

        import subprocess
        try:
            subprocess.run(["git", "fetch"], capture_output=True, timeout=15)
            result = subprocess.run(
                ["git", "log", "HEAD..origin/main", "--oneline"],
                capture_output=True, text=True, timeout=10,
            )
            commits = result.stdout.strip().splitlines() if result.stdout.strip() else []
            return jsonify({
                "available": len(commits) > 0,
                "current_version": config.get("version", default="unknown"),
                "commits_behind": len(commits),
                "changes": commits[:10],
                "message": f"{len(commits)} new commits available" if commits else "Up to date",
            })
        except Exception as e:
            return jsonify({"available": False, "message": str(e)}), 500

    @app.route("/api/update/install", methods=["POST"])
    def api_update_install():
        """Install available updates."""
        if mock:
            return jsonify({
                "success": True,
                "message": "Mock: Update installed successfully. Restart required.",
            })

        import subprocess
        try:
            result = subprocess.run(
                ["git", "pull", "origin", "main"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return jsonify({"success": False, "message": result.stderr}), 500

            # Reinstall dependencies
            subprocess.run(
                ["pip", "install", "-r", "requirements.txt"],
                capture_output=True, timeout=120,
            )

            return jsonify({
                "success": True,
                "message": "Update installed. Restart the application to apply.",
            })
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500

    # ------------------------------------------------------------------
    # USB Key Management
    # ------------------------------------------------------------------

    def _get_mount_map() -> dict[str, str]:
        """Return a mapping of resolved mount point path → device from /proc/mounts.

        Resolves symlinks so that e.g. ``/media/usb -> usb0`` and
        ``/media/usb0`` map to the same device.

        Returns:
            Dict of ``{resolved_mount_path: device}`` for all active mounts.
        """
        mount_map: dict[str, str] = {}
        try:
            with open("/proc/mounts", encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        device, mp = parts[0], parts[1]
                        # Unescape octal sequences in mount paths (e.g. \040 = space)
                        mp = mp.replace("\\040", " ").replace("\\011", "\t")
                        try:
                            resolved = str(Path(mp).resolve())
                        except OSError:
                            resolved = mp
                        mount_map[resolved] = device
        except OSError:
            pass
        return mount_map

    def _fmt_bytes(n: int) -> str:
        """Format a byte count as a human-readable string (e.g. '7.5 GB')."""
        value = float(n)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                if unit == "B":
                    return f"{int(value)} B"
                return f"{value:.1f} {unit}"
            value /= 1024
        return str(n)

    def _get_usb_size(mount_point: str) -> tuple[str, str]:
        """Return (size_total, size_free) for a mount point via statvfs.

        Args:
            mount_point: Resolved mount path, e.g. ``/media/usb0``.

        Returns:
            Tuple of formatted strings, e.g. ``('7.5 GB', '7.5 GB')``.
            Both strings are empty on error.
        """
        try:
            st = os.statvfs(mount_point)
            total = st.f_frsize * st.f_blocks
            free = st.f_frsize * st.f_bavail
            return _fmt_bytes(total), _fmt_bytes(free)
        except OSError:
            return "", ""

    def _get_fs_label(device: str) -> str:
        """Return the filesystem label for a block device via lsblk.

        Checks the partition itself and, if empty, its parent disk.

        Args:
            device: Block device path, e.g. ``/dev/sda1``.

        Returns:
            Label string, or empty string if not found / lsblk unavailable.
        """
        import json
        import subprocess

        # Query the partition directly for its label
        parent_device = device.rstrip("0123456789") if device.startswith("/dev/sd") else device
        try:
            result = subprocess.run(
                ["lsblk", "--json", "--output", "NAME,LABEL", parent_device],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode != 0:
                return ""
            data = json.loads(result.stdout)
            for dev in data.get("blockdevices", []):
                # Check partition children first
                for child in dev.get("children", []):
                    label = (child.get("label") or "").strip()
                    if label:
                        return label
                # Fallback to disk label
                label = (dev.get("label") or "").strip()
                if label:
                    return label
        except (OSError, subprocess.TimeoutExpired, ValueError, KeyError):
            pass
        return ""

    def _get_key_status(mount_point: str, known_hashes: set[str]) -> dict[str, str]:
        """Inspect a mount point for existing KEY files and their validity.

        Returns status for both DEFUSE.KEY and TOURNAMENT.KEY.

        For each key type the returned dict contains:
        - ``defuse_status``: ``"none"`` | ``"registered"`` | ``"permissive"``
        - ``defuse_label``: human label if registered, ``"PERMISSIVE KEY"`` if
          the file exists but the hash is not in known_hashes, or ``""``
        - same keys for ``tournament_*``

        Args:
            mount_point: Resolved path to the mount point.
            known_hashes: All known token hashes from usb_keys.yaml
                (defuse + tournament combined, keyed by hash → label).
        """
        import hashlib

        result: dict[str, str] = {
            "defuse_status": "none",
            "defuse_label": "",
            "tournament_status": "none",
            "tournament_label": "",
        }

        for key_type, filename, status_key, label_key in (
            ("defuse", "DEFUSE.KEY", "defuse_status", "defuse_label"),
            ("tournament", "TOURNAMENT.KEY", "tournament_status", "tournament_label"),
        ):
            key_file = Path(mount_point) / filename
            if not key_file.is_file():
                continue
            try:
                content = key_file.read_text(encoding="utf-8", errors="replace").strip()
                if content:
                    digest = hashlib.sha256(content.encode()).hexdigest()
                    if digest in known_hashes:
                        result[status_key] = "registered"
                        result[label_key] = known_hashes[digest]
                        continue
            except OSError:
                pass
            # File exists but hash not in known_hashes → permissive / self-made key
            result[status_key] = "permissive"
            result[label_key] = "PERMISSIVE KEY"

        return result

    def _enumerate_usb_sticks() -> list[dict]:
        """Return a list of currently mounted USB sticks with metadata.

        Reads ``/proc/mounts`` to find only directories that are
        actually mounted (not empty placeholder directories created by
        the installer).  Resolves symlinks to avoid duplicates.
        Enriches each entry with filesystem label, size, and key status.

        Returns:
            List of dicts with keys: ``mount_point``, ``display_name``,
            ``size_total``, ``size_free``, ``defuse_status``,
            ``defuse_label``, ``tournament_status``, ``tournament_label``.
        """
        if mock:
            return [{
                "mount_point": "/mock/usb",
                "display_name": "Mock USB Stick",
                "size_total": "8.0 GB",
                "size_free": "7.5 GB",
                "defuse_status": "registered",
                "defuse_label": "Mock Defuse Key",
                "tournament_status": "none",
                "tournament_label": "",
            }]

        # Build hash→label lookup from all registered keys
        all_keys = config.load_usb_keys()
        known_hashes: dict[str, str] = {}
        for k in all_keys.get("defuse_keys", []):
            if "token_hash" in k:
                known_hashes[k["token_hash"]] = k.get("label", "")
        for k in all_keys.get("tournament_keys", []):
            if "token_hash" in k:
                known_hashes[k["token_hash"]] = k.get("label", "")

        mount_map = _get_mount_map()
        sticks: list[dict] = []
        seen: set[str] = set()

        candidate_bases: list[str] = ["/media", "/mnt"]
        for base in candidate_bases:
            base_path = Path(base)
            if not base_path.is_dir():
                continue
            try:
                for entry in base_path.iterdir():
                    if not entry.is_dir():
                        continue
                    try:
                        resolved = str(entry.resolve())
                    except OSError:
                        resolved = str(entry)
                    if resolved in seen:
                        continue
                    if resolved not in mount_map:
                        continue
                    device = mount_map[resolved]
                    size_total, size_free = _get_usb_size(resolved)
                    fs_label = _get_fs_label(device)
                    key_status = _get_key_status(resolved, known_hashes)
                    sticks.append({
                        "mount_point": str(entry),
                        "display_name": fs_label or entry.name,
                        "size_total": size_total,
                        "size_free": size_free,
                        **key_status,
                    })
                    seen.add(resolved)
            except OSError:
                pass

        return sticks

    @app.route("/usb-keys")
    def usb_keys_page():
        """USB key management page."""
        return render_template("usb_keys.html", active="usb-keys")

    @app.route("/api/usb-keys")
    def api_usb_keys_list():
        """List all registered USB keys and current security mode."""
        keys = config.load_usb_keys()
        defuse_keys = keys.get("defuse_keys", [])
        tournament_keys = keys.get("tournament_keys", [])
        return jsonify({
            "defuse_keys": defuse_keys,
            "tournament_keys": tournament_keys,
            "permissive_defuse": len(defuse_keys) == 0,
            "permissive_tournament": len(tournament_keys) == 0,
        })

    @app.route("/api/usb-keys/usb-sticks")
    def api_usb_sticks():
        """List currently mounted USB sticks."""
        return jsonify({"sticks": _enumerate_usb_sticks()})

    @app.route("/api/usb-keys/generate", methods=["POST"])
    def api_usb_keys_generate():
        """Generate a new USB key token and write it to a USB stick.

        The raw UUID4 token is written to the selected mount point and
        its SHA-256 hash is stored in ``config/usb_keys.yaml``.  The
        token is returned exactly once in this response — it is never
        stored in plaintext.
        """
        import datetime
        import hashlib
        import uuid

        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No JSON body"}), 400

        key_type = data.get("key_type", "")
        if key_type not in ("defuse", "tournament"):
            return jsonify({
                "success": False,
                "message": "key_type must be 'defuse' or 'tournament'",
            }), 400

        mount_point = str(data.get("mount_point", "")).strip()
        label = str(data.get("label", "")).strip()[:64] or f"{key_type.title()} Key"

        # Security: validate mount_point is under /media or /mnt
        if not mock:
            if not any(mount_point.startswith(p) for p in ("/media/", "/mnt/")):
                return jsonify({
                    "success": False,
                    "message": "Invalid mount point — must be under /media/ or /mnt/",
                }), 400
            if not Path(mount_point).is_dir():
                return jsonify({
                    "success": False,
                    "message": f"Mount point not found: {mount_point}",
                }), 404

        filename = "DEFUSE.KEY" if key_type == "defuse" else "TOURNAMENT.KEY"

        # Generate token
        token = str(uuid.uuid4())
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        key_id = token.replace("-", "")[:8]

        # Write token to USB stick
        if not mock:
            try:
                key_file = Path(mount_point) / filename
                key_file.write_text(token + "\n", encoding="utf-8")
            except PermissionError:
                return jsonify({
                    "success": False,
                    "message": (
                        f"Permission denied writing to {mount_point}. "
                        "Ensure the USB stick is mounted with write access."
                    ),
                }), 500
            except OSError as e:
                return jsonify({
                    "success": False,
                    "message": f"Failed to write key file: {e}",
                }), 500

        record: dict[str, str] = {
            "id": key_id,
            "label": label,
            "token_hash": token_hash,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(
                timespec="seconds"
            ),
        }

        # Persist to usb_keys.yaml
        all_keys = config.load_usb_keys()
        list_name = "defuse_keys" if key_type == "defuse" else "tournament_keys"
        all_keys[list_name] = list(all_keys.get(list_name, [])) + [record]
        config.save_usb_keys(all_keys)

        # Hot-reload the running USB detector allowlists
        ba = app.config.get("PROP_APP")
        if ba and hasattr(ba, "usb_detector"):
            fresh = config.load_usb_keys()
            ba.usb_detector.reload_allowlists(
                frozenset(k["token_hash"] for k in fresh.get("defuse_keys", []) if "token_hash" in k),
                frozenset(k["token_hash"] for k in fresh.get("tournament_keys", []) if "token_hash" in k),
            )

        logger.info("Generated %s key id=%s label='%s'", key_type, key_id, label)
        return jsonify({
            "success": True,
            "token": token,
            "record": record,
            "message": (
                f"Key written to {mount_point}/{filename}"
                if not mock
                else "Key registered (mock mode — no file written)"
            ),
        })

    @app.route("/api/usb-keys/<key_type>/<key_id>", methods=["DELETE"])
    def api_usb_keys_delete(key_type: str, key_id: str):
        """Revoke a registered USB key by ID."""
        if key_type not in ("defuse", "tournament"):
            return jsonify({"success": False, "message": "Invalid key_type"}), 400

        all_keys = config.load_usb_keys()
        list_name = "defuse_keys" if key_type == "defuse" else "tournament_keys"
        keys_list = list(all_keys.get(list_name, []))

        original_len = len(keys_list)
        keys_list = [k for k in keys_list if k.get("id") != key_id]

        if len(keys_list) == original_len:
            return jsonify({"success": False, "message": "Key not found"}), 404

        all_keys[list_name] = keys_list
        config.save_usb_keys(all_keys)

        # Hot-reload allowlists
        ba = app.config.get("PROP_APP")
        if ba and hasattr(ba, "usb_detector"):
            fresh = config.load_usb_keys()
            ba.usb_detector.reload_allowlists(
                frozenset(k["token_hash"] for k in fresh.get("defuse_keys", []) if "token_hash" in k),
                frozenset(k["token_hash"] for k in fresh.get("tournament_keys", []) if "token_hash" in k),
            )

        logger.info("Revoked %s key id=%s", key_type, key_id)
        return jsonify({"success": True, "message": "Key revoked"})

    # ------------------------------------------------------------------
    # Custom Sounds API
    # ------------------------------------------------------------------

    @app.route("/sounds")
    def sounds_page():
        """Custom sound management page."""
        return render_template("sounds.html", active="sounds")

    @app.route("/api/sounds")
    def api_sounds_list():
        """List custom sound files in custom/sounds/.

        Returns a list of files with name, size, and whether the file
        overrides a built-in default sound.
        """
        custom_dir = config.project_root / "custom" / "sounds"

        # Build set of default filenames for override detection
        sound_paths: dict = config.get("audio", "sounds", default={})
        default_filenames = {Path(p).name for p in sound_paths.values()}

        sounds = []
        if custom_dir.is_dir():
            for f in sorted(custom_dir.iterdir()):
                if f.is_file() and f.suffix.lower() == ".wav":
                    sounds.append({
                        "filename": f.name,
                        "size": f.stat().st_size,
                        "overrides_default": f.name in default_filenames,
                    })

        return jsonify({"sounds": sounds})

    @app.route("/api/sounds/upload", methods=["POST"])
    def api_sounds_upload():
        """Upload a custom WAV sound file to custom/sounds/.

        Accepts multipart/form-data with:
        - file: the WAV file (original filename is preserved)
        """
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file provided"}), 400

        file = request.files["file"]
        if not file.filename:
            return jsonify({"success": False, "message": "No file selected"}), 400

        # Sanitize filename — prevent path traversal
        filename = Path(file.filename).name
        if not filename or ".." in filename:
            return jsonify({
                "success": False,
                "message": "Invalid filename.",
            }), 400

        # Ensure .wav extension
        if not filename.lower().endswith(".wav"):
            return jsonify({
                "success": False,
                "message": "Only WAV files are supported.",
            }), 400

        # Validate WAV header (first 4 bytes should be 'RIFF')
        header = file.read(4)
        file.seek(0)
        if header != b"RIFF":
            return jsonify({
                "success": False,
                "message": "File does not appear to be a valid WAV file.",
            }), 400

        custom_dir = config.project_root / "custom" / "sounds"
        custom_dir.mkdir(parents=True, exist_ok=True)

        dest = custom_dir / filename
        file.save(str(dest))

        logger.info("Custom sound uploaded: %s (%d bytes)", filename, dest.stat().st_size)
        return jsonify({
            "success": True,
            "message": f"Sound '{filename}' uploaded successfully.",
        })

    @app.route("/api/sounds/<filename>", methods=["DELETE"])
    def api_sounds_delete(filename: str):
        """Delete a custom sound file from custom/sounds/."""
        # Sanitize
        if ".." in filename or "/" in filename or "\\" in filename:
            return jsonify({"success": False, "message": "Invalid filename"}), 400

        custom_dir = config.project_root / "custom" / "sounds"
        target = custom_dir / filename

        if not target.exists():
            return jsonify({
                "success": False,
                "message": "Custom sound not found.",
            }), 404

        target.unlink()
        logger.info("Custom sound deleted: %s", filename)
        return jsonify({
            "success": True,
            "message": f"Sound '{filename}' deleted.",
        })

    @app.route("/api/sounds/preview/<filename>")
    def api_sounds_preview(filename: str):
        """Serve a custom sound file for browser playback."""
        if ".." in filename or "/" in filename or "\\" in filename:
            return "Invalid filename", 400

        custom_path = config.project_root / "custom" / "sounds" / filename
        if custom_path.exists():
            from flask import send_file
            return send_file(str(custom_path), mimetype="audio/wav")
        return "Sound not found", 404

    # ------------------------------------------------------------------
    # Service Restart API
    # ------------------------------------------------------------------

    @app.route("/api/service/restart", methods=["POST"])
    def api_service_restart():
        """Restart the systemd service.

        Uses a short shell delay so the HTTP response is fully sent
        before systemd terminates this process.
        """
        if mock:
            return jsonify({
                "success": True,
                "message": "Mock: Service restart simulated.",
            })

        import subprocess
        try:
            # Test if sudo works without password prompt
            result = subprocess.run(
                ["sudo", "-n", "systemctl", "status", "airsoft-prop"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                return jsonify({
                    "success": False,
                    "message": "Cannot restart service: sudo access denied or service not found.",
                }), 500

            # Delay the restart by 1 second so Flask can send the response
            # before systemd kills this process.
            subprocess.Popen(
                ["bash", "-c",
                 "sleep 1 && sudo systemctl restart airsoft-prop"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return jsonify({
                "success": True,
                "message": "Service is restarting...",
            })
        except subprocess.TimeoutExpired:
            return jsonify({"success": False, "message": "Timeout testing sudo access."}), 500
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500

    return app


class WebServer:
    """Manages the Flask web server in a daemon thread.

    Usage:
        server = WebServer(config, mock=True)
        server.start()   # Non-blocking, starts in background
        ...
        server.stop()
    """

    def __init__(
        self,
        config: Config,
        mock: bool = False,
        battery: Optional[BatteryBase] = None,
        app: Optional[Any] = None,
        captive_portal: Optional[Any] = None,
    ) -> None:
        self._config = config
        self._mock = mock
        self._battery = battery
        self._prop_app = app
        self._captive_portal = captive_portal
        self._app: Optional[Flask] = None
        self._thread: Optional[threading.Thread] = None
        self._port = config.get("web", "port", default=8080)

    def start(self) -> None:
        """Start the web server in a daemon thread."""
        if not self._config.get("web", "enabled", default=True):
            logger.info("Web interface disabled in config")
            return

        self._app = create_app(
            self._config,
            mock=self._mock,
            battery=self._battery,
            prop_app=self._prop_app,
            captive_portal=self._captive_portal,
        )
        self._thread = threading.Thread(
            target=self._run,
            name="web-server",
            daemon=True,
        )
        self._thread.start()
        logger.info("Web server started on port %s", self._port)

    def _run(self) -> None:
        """Run the Flask server (called in thread)."""
        # Suppress Flask/Werkzeug request logging in production
        import logging
        log = logging.getLogger("werkzeug")
        log.setLevel(logging.WARNING)

        self._app.run(
            host="0.0.0.0",
            port=self._port,
            debug=False,
            use_reloader=False,
        )

    def stop(self) -> None:
        """Stop the web server.

        Since we use a daemon thread, it will be killed
        when the main process exits. This method is a no-op
        but exists for symmetry with start().
        """
        logger.info("Web server stopping")
