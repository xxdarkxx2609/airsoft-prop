"""Captive portal and access point management.

When no known WiFi network is available, the Pi creates its own access
point using hostapd and dnsmasq.  All DNS queries are redirected to the
Pi's IP, triggering captive portal detection on phones — the Flask web
interface opens automatically so the user can configure WiFi.

A background monitor thread periodically checks WiFi connectivity and
re-enables the AP if the connection drops at runtime.
"""

from __future__ import annotations

import ipaddress
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from typing import Optional

from src.utils.config import Config
from src.utils.logger import get_logger

logger = get_logger(__name__)

# How often the monitor thread checks connectivity (seconds).
_MONITOR_INTERVAL: float = 15.0

# Grace period after stopping AP before checking connectivity (seconds).
# Gives NetworkManager time to reconnect after AP teardown.
_RECONNECT_GRACE: float = 10.0

# Config file paths (written at runtime, not persistent).
_HOSTAPD_CONF = "/tmp/airsoft-hostapd.conf"
_DNSMASQ_CONF = "/tmp/airsoft-dnsmasq.conf"


class CaptivePortalBase(ABC):
    """Abstract base for captive portal / AP management."""

    @abstractmethod
    def is_wifi_connected(self) -> bool:
        """Check if wlan0 is connected to an infrastructure WiFi network."""

    @abstractmethod
    def start_ap(self) -> bool:
        """Start the access point.

        Returns:
            True if AP started successfully.
        """

    @abstractmethod
    def stop_ap(self) -> bool:
        """Stop the access point and restore normal WiFi.

        Returns:
            True if AP stopped successfully.
        """

    @abstractmethod
    def is_active(self) -> bool:
        """Return True if the AP is currently running."""

    @abstractmethod
    def get_ap_info(self) -> dict:
        """Return AP status information.

        Returns:
            Dict with keys: active, ssid, password, ip.
        """

    @abstractmethod
    def start_monitor(self) -> None:
        """Start background connectivity monitor thread."""

    @abstractmethod
    def stop_monitor(self) -> None:
        """Stop background connectivity monitor thread."""

    @abstractmethod
    def shutdown(self) -> None:
        """Full cleanup: stop monitor and AP."""


class CaptivePortal(CaptivePortalBase):
    """Real captive portal using hostapd + dnsmasq.

    Manages the full AP lifecycle: interface configuration, hostapd for
    the WiFi access point, and dnsmasq for DHCP + DNS redirection.
    """

    def __init__(self, config: Config) -> None:
        self._ssid: str = config.get(
            "access_point", "ssid", default="AirsoftProp-Setup"
        )
        self._password: str = config.get(
            "access_point", "password", default="defuse1337"
        )
        self._channel: int = config.get("access_point", "channel", default=6)
        self._ip: str = config.get(
            "access_point", "ip", default="192.168.4.1"
        )
        self._netmask: str = config.get(
            "access_point", "netmask", default="255.255.255.0"
        )
        self._dhcp_start: str = config.get(
            "access_point", "dhcp_range_start", default="192.168.4.10"
        )
        self._dhcp_end: str = config.get(
            "access_point", "dhcp_range_end", default="192.168.4.50"
        )

        self._ap_active = False
        self._hostapd_proc: Optional[subprocess.Popen] = None
        self._dnsmasq_proc: Optional[subprocess.Popen] = None

        # Monitor thread
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_stop = threading.Event()

        # Lock for AP start/stop to avoid races between monitor and web UI.
        self._lock = threading.Lock()

    # -- connectivity check --------------------------------------------------

    def is_wifi_connected(self) -> bool:
        """Check if wlan0 is connected to a WiFi network via nmcli."""
        if self._ap_active:
            return False
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "GENERAL.STATE", "device", "show", "wlan0"],
                capture_output=True, text=True, timeout=10,
            )
            # Connected states contain "(connected)" in the output.
            return "connected" in result.stdout.lower() and result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.warning("WiFi connectivity check failed: %s", exc)
            return False

    # -- AP lifecycle --------------------------------------------------------

    def start_ap(self) -> bool:
        """Start the access point (hostapd + dnsmasq)."""
        with self._lock:
            if self._ap_active:
                logger.debug("AP already active, skipping start")
                return True

            logger.info(
                "Starting AP: SSID=%s, IP=%s, Channel=%d",
                self._ssid, self._ip, self._channel,
            )

            try:
                # 1. Take wlan0 away from NetworkManager
                self._run_cmd(["sudo", "nmcli", "device", "set", "wlan0", "managed", "no"])

                # 2. Configure interface with static IP
                prefix = ipaddress.IPv4Network(
                    f"0.0.0.0/{self._netmask}", strict=False
                ).prefixlen
                self._run_cmd(["sudo", "ip", "addr", "flush", "dev", "wlan0"])
                self._run_cmd(
                    ["sudo", "ip", "addr", "add", f"{self._ip}/{prefix}", "dev", "wlan0"]
                )
                self._run_cmd(["sudo", "ip", "link", "set", "wlan0", "up"])

                # 3. Write config files
                self._write_hostapd_conf()
                self._write_dnsmasq_conf()

                # 4. Start hostapd
                self._hostapd_proc = subprocess.Popen(
                    ["sudo", "hostapd", _HOSTAPD_CONF],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                # Brief pause so hostapd can claim the interface.
                time.sleep(1.0)
                if self._hostapd_proc.poll() is not None:
                    stderr = self._hostapd_proc.stderr.read().decode(errors="replace")
                    logger.error("hostapd exited immediately: %s", stderr)
                    self._cleanup_failed_start()
                    return False

                # 5. Start dnsmasq
                self._dnsmasq_proc = subprocess.Popen(
                    ["sudo", "dnsmasq", "-C", _DNSMASQ_CONF, "--no-daemon", "--log-queries"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                time.sleep(0.5)
                if self._dnsmasq_proc.poll() is not None:
                    stderr = self._dnsmasq_proc.stderr.read().decode(errors="replace")
                    logger.error("dnsmasq exited immediately: %s", stderr)
                    self._cleanup_failed_start()
                    return False

                self._ap_active = True
                logger.info("AP started successfully")
                return True

            except Exception:
                logger.exception("Failed to start AP")
                self._cleanup_failed_start()
                return False

    def stop_ap(self) -> bool:
        """Stop the access point and hand wlan0 back to NetworkManager."""
        with self._lock:
            if not self._ap_active:
                logger.debug("AP not active, skipping stop")
                return True

            logger.info("Stopping AP...")

            # 1. Kill processes
            self._kill_process(self._hostapd_proc, "hostapd")
            self._kill_process(self._dnsmasq_proc, "dnsmasq")
            self._hostapd_proc = None
            self._dnsmasq_proc = None

            # 2. Clean up interface
            try:
                self._run_cmd(["sudo", "ip", "addr", "flush", "dev", "wlan0"])
            except Exception:
                logger.warning("Failed to flush wlan0 addresses")

            # 3. Return wlan0 to NetworkManager
            try:
                self._run_cmd(["sudo", "nmcli", "device", "set", "wlan0", "managed", "yes"])
            except Exception:
                logger.warning("Failed to re-enable NM management of wlan0")

            self._ap_active = False
            logger.info("AP stopped")
            return True

    def is_active(self) -> bool:
        return self._ap_active

    def get_ap_info(self) -> dict:
        return {
            "active": self._ap_active,
            "ssid": self._ssid,
            "password": self._password,
            "ip": self._ip,
        }

    # -- background monitor --------------------------------------------------

    def start_monitor(self) -> None:
        """Start a daemon thread that re-enables AP when WiFi drops."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._monitor_stop.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="captive-portal-monitor",
            daemon=True,
        )
        self._monitor_thread.start()
        logger.info("Captive portal monitor started (interval=%ss)", _MONITOR_INTERVAL)

    def stop_monitor(self) -> None:
        """Signal the monitor thread to stop.

        Times out after 2 seconds (monitor loop checks every 15s, but stop event
        causes immediate wake-up). During shutdown, if monitor doesn't exit in 2s,
        it will be killed as a daemon thread.
        """
        self._monitor_stop.set()
        if self._monitor_thread:
            # Short timeout (2s) during shutdown — monitor should wake immediately
            # when stop event is set via wait()
            self._monitor_thread.join(timeout=2.0)
            if self._monitor_thread.is_alive():
                logger.debug("Monitor thread still running after stop signal (will be killed)")
            self._monitor_thread = None
        logger.info("Captive portal monitor stopped")

    def shutdown(self) -> None:
        """Full shutdown: stop monitor, then stop AP if active."""
        self.stop_monitor()
        self.stop_ap()
        logger.info("Captive portal shut down")

    # -- internal helpers ----------------------------------------------------

    def _monitor_loop(self) -> None:
        """Background loop: check WiFi every _MONITOR_INTERVAL seconds.

        On first detection of a dropped connection, waits _RECONNECT_GRACE
        seconds so NetworkManager can auto-reconnect before enabling the AP.
        A second check confirms the loss is real before starting the AP.
        """
        while not self._monitor_stop.is_set():
            self._monitor_stop.wait(_MONITOR_INTERVAL)
            if self._monitor_stop.is_set():
                break

            try:
                if self._ap_active or self.is_wifi_connected():
                    continue

                logger.warning(
                    "WiFi connection lost — waiting %.0fs for NM to reconnect",
                    _RECONNECT_GRACE,
                )
                # Give NetworkManager a chance to auto-reconnect.
                self._monitor_stop.wait(_RECONNECT_GRACE)
                if self._monitor_stop.is_set():
                    break

                # Confirm the loss is still present before starting AP.
                if not self._ap_active and not self.is_wifi_connected():
                    logger.warning("WiFi still gone after grace period — starting AP")
                    self.start_ap()
            except Exception:
                logger.exception("Error in captive portal monitor")

    def _write_hostapd_conf(self) -> None:
        """Generate hostapd configuration file."""
        conf = (
            f"interface=wlan0\n"
            f"driver=nl80211\n"
            f"ssid={self._ssid}\n"
            f"hw_mode=g\n"
            f"channel={self._channel}\n"
            f"wmm_enabled=0\n"
            f"macaddr_acl=0\n"
            f"auth_algs=1\n"
            f"wpa=2\n"
            f"wpa_passphrase={self._password}\n"
            f"wpa_key_mgmt=WPA-PSK\n"
            f"rsn_pairwise=CCMP\n"
        )
        with open(_HOSTAPD_CONF, "w", encoding="utf-8") as f:
            f.write(conf)
        logger.debug("Wrote %s", _HOSTAPD_CONF)

    def _write_dnsmasq_conf(self) -> None:
        """Generate dnsmasq configuration file (DHCP + DNS redirect)."""
        conf = (
            f"interface=wlan0\n"
            f"bind-interfaces\n"
            f"dhcp-range={self._dhcp_start},{self._dhcp_end},"
            f"{self._netmask},24h\n"
            f"address=/#/{self._ip}\n"
        )
        with open(_DNSMASQ_CONF, "w", encoding="utf-8") as f:
            f.write(conf)
        logger.debug("Wrote %s", _DNSMASQ_CONF)

    @staticmethod
    def _run_cmd(cmd: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
        """Run a shell command, log on failure."""
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            logger.warning(
                "Command %s failed (rc=%d): %s",
                cmd, result.returncode, result.stderr.strip(),
            )
        return result

    @staticmethod
    def _kill_process(proc: Optional[subprocess.Popen], name: str) -> None:
        """Terminate a subprocess, escalate to kill if needed."""
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=5)
            logger.debug("%s terminated", name)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
            logger.warning("%s killed (did not terminate gracefully)", name)
        except Exception:
            logger.warning("Failed to stop %s", name, exc_info=True)

    def _cleanup_failed_start(self) -> None:
        """Best-effort cleanup after a failed AP start."""
        self._kill_process(self._hostapd_proc, "hostapd")
        self._kill_process(self._dnsmasq_proc, "dnsmasq")
        self._hostapd_proc = None
        self._dnsmasq_proc = None
        try:
            self._run_cmd(["sudo", "ip", "addr", "flush", "dev", "wlan0"])
            self._run_cmd(["sudo", "nmcli", "device", "set", "wlan0", "managed", "yes"])
        except Exception:
            pass
        self._ap_active = False


class MockCaptivePortal(CaptivePortalBase):
    """Mock captive portal for desktop testing.

    Simulates AP mode without starting real services.
    """

    def __init__(self) -> None:
        self._ap_active = False

    def is_wifi_connected(self) -> bool:
        # In mock mode, pretend WiFi is connected (no AP needed).
        return True

    def start_ap(self) -> bool:
        self._ap_active = True
        logger.info("Mock AP started (SSID=AirsoftProp-Setup)")
        return True

    def stop_ap(self) -> bool:
        self._ap_active = False
        logger.info("Mock AP stopped")
        return True

    def is_active(self) -> bool:
        return self._ap_active

    def get_ap_info(self) -> dict:
        return {
            "active": self._ap_active,
            "ssid": "AirsoftProp-Setup",
            "password": "defuse1337",
            "ip": "192.168.4.1",
        }

    def start_monitor(self) -> None:
        logger.debug("Mock captive portal monitor (no-op)")

    def stop_monitor(self) -> None:
        pass

    def shutdown(self) -> None:
        self._ap_active = False
        logger.debug("Mock captive portal shut down")


def create_captive_portal(
    config: Config, mock: bool = False
) -> CaptivePortalBase:
    """Factory function to create the appropriate captive portal.

    Args:
        config: Application config instance.
        mock: If True, return a MockCaptivePortal.
    """
    if mock:
        return MockCaptivePortal()
    return CaptivePortal(config)
