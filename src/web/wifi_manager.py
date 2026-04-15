"""WiFi management abstraction with mock support.

Provides network scanning, connection management, and status info.
On a real Pi this uses NetworkManager (nmcli). In mock mode it returns
simulated data so the web interface can be tested on any desktop.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class WifiNetwork:
    """Represents a discovered WiFi network."""

    ssid: str
    signal: int  # Signal strength 0-100
    security: str  # e.g. "WPA2", "Open"
    connected: bool = False


@dataclass
class NetworkStatus:
    """Current network status information."""

    connected: bool = False
    ssid: Optional[str] = None
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    signal: int = 0
    mode: str = "unknown"  # "station", "ap", "disconnected"


class WifiManagerBase:
    """Base class for WiFi management."""

    def get_status(self) -> NetworkStatus:
        """Get current network status."""
        raise NotImplementedError

    def scan(self) -> list[WifiNetwork]:
        """Scan for available WiFi networks."""
        raise NotImplementedError

    def connect(self, ssid: str, password: str) -> tuple[bool, str]:
        """Connect to a WiFi network.

        Returns:
            Tuple of (success, message).
        """
        raise NotImplementedError

    def disconnect(self) -> bool:
        """Disconnect from current WiFi network."""
        raise NotImplementedError

    def get_saved_networks(self) -> list[str]:
        """Get list of saved/known network SSIDs."""
        raise NotImplementedError

    def forget_network(self, ssid: str) -> bool:
        """Remove a saved network."""
        raise NotImplementedError


class MockWifiManager(WifiManagerBase):
    """Mock WiFi manager for desktop testing.

    Returns simulated network data so the web interface
    can be fully tested without real WiFi hardware.
    """

    def __init__(self) -> None:
        self._connected_ssid: Optional[str] = None
        self._saved: list[str] = ["AirsoftProp", "HomeNetwork"]

    def get_status(self) -> NetworkStatus:
        if self._connected_ssid:
            return NetworkStatus(
                connected=True,
                ssid=self._connected_ssid,
                ip_address="192.168.1.42",
                mac_address="b8:27:eb:aa:bb:cc",
                signal=72,
                mode="station",
            )
        return NetworkStatus(
            connected=False,
            mac_address="b8:27:eb:aa:bb:cc",
            mode="disconnected",
        )

    def scan(self) -> list[WifiNetwork]:
        networks = [
            WifiNetwork(ssid="AirsoftProp", signal=85, security="WPA2"),
            WifiNetwork(ssid="HomeNetwork", signal=62, security="WPA2"),
            WifiNetwork(ssid="Neighbor_5G", signal=34, security="WPA2"),
            WifiNetwork(ssid="CoffeeShop", signal=28, security="Open"),
            WifiNetwork(ssid="IoT-Network", signal=45, security="WPA"),
        ]
        for net in networks:
            if net.ssid == self._connected_ssid:
                net.connected = True
        return networks

    def connect(self, ssid: str, password: str) -> tuple[bool, str]:
        known = {n.ssid for n in self.scan()}
        if ssid not in known:
            return False, f"Network '{ssid}' not found"
        # Simulate connection
        self._connected_ssid = ssid
        if ssid not in self._saved:
            self._saved.append(ssid)
        logger.info("Mock WiFi: connected to '%s'", ssid)
        return True, f"Connected to '{ssid}'"

    def disconnect(self) -> bool:
        if self._connected_ssid:
            logger.info("Mock WiFi: disconnected from '%s'", self._connected_ssid)
            self._connected_ssid = None
            return True
        return False

    def get_saved_networks(self) -> list[str]:
        return list(self._saved)

    def forget_network(self, ssid: str) -> bool:
        if ssid in self._saved:
            self._saved.remove(ssid)
            if self._connected_ssid == ssid:
                self._connected_ssid = None
            return True
        return False


class RealWifiManager(WifiManagerBase):
    """Real WiFi manager using NetworkManager (nmcli).

    For use on Raspberry Pi with NetworkManager installed.
    """

    def _run(self, cmd: list[str]) -> tuple[int, str]:
        """Run a shell command and return (returncode, output).

        Returns stdout when available, falls back to stderr so that
        error messages from nmcli (which writes to stderr) are not lost.
        """
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15
            )
            output = result.stdout.strip() or result.stderr.strip()
            return result.returncode, output
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error("Command failed: %s — %s", cmd, e)
            return 1, str(e)

    @staticmethod
    def _parse_nmcli_terse(line: str) -> list[str]:
        """Parse a single line of nmcli terse (-t) output into fields.

        nmcli -t escapes colons as ``\\:`` and backslashes as ``\\\\``
        inside field values.  A naive ``split(":")`` breaks on SSIDs
        like ``<:::::]=0`` which become ``<\\:\\:\\:\\:\\:]=0`` in terse
        output.
        """
        fields: list[str] = []
        current: list[str] = []
        i = 0
        while i < len(line):
            if line[i] == '\\' and i + 1 < len(line):
                # Escaped character — keep the literal value
                current.append(line[i + 1])
                i += 2
            elif line[i] == ':':
                # Unescaped colon — field separator
                fields.append(''.join(current))
                current = []
                i += 1
            else:
                current.append(line[i])
                i += 1
        fields.append(''.join(current))
        return fields

    def get_status(self) -> NetworkStatus:
        status = NetworkStatus()
        rc, out = self._run(["nmcli", "-t", "-f",
                             "GENERAL.STATE,GENERAL.CONNECTION,GENERAL.HWADDR",
                             "device", "show", "wlan0"])
        if rc != 0:
            return status

        for line in out.splitlines():
            parts = self._parse_nmcli_terse(line)
            if len(parts) < 2:
                continue
            key, val = parts[0], parts[1]
            if key == "GENERAL.CONNECTION" and val and val != "--":
                status.connected = True
                status.ssid = val
                status.mode = "station"
            elif parts[0] == "GENERAL.HWADDR" and len(parts) > 1:
                # HWADDR colons are NOT escaped by nmcli -t, so the
                # terse parser splits B8:27:EB:8C:7D:04 into 7 fields.
                # Rejoin everything after the key.
                status.mac_address = ":".join(parts[1:])

        # Get IP address
        rc, out = self._run(["hostname", "-I"])
        if rc == 0 and out:
            status.ip_address = out.split()[0]

        # Get signal strength from cached wifi list (no rescan)
        if status.connected:
            rc, out = self._run(["nmcli", "-t", "-f", "SIGNAL,ACTIVE",
                                 "device", "wifi", "list"])
            if rc == 0:
                for line in out.splitlines():
                    parts = self._parse_nmcli_terse(line)
                    if len(parts) >= 2 and parts[1].strip() == "yes":
                        signal = parts[0].strip()
                        if signal.isdigit():
                            status.signal = int(signal)
                        break

        return status

    def scan(self) -> list[WifiNetwork]:
        # Trigger a rescan via sudo — the pi user lacks PolicyKit
        # privileges for a real WiFi rescan, so this needs root.
        self._run(["sudo", "nmcli", "device", "wifi", "rescan"])
        rc, out = self._run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,ACTIVE",
                             "device", "wifi", "list"])
        if rc != 0:
            return []

        networks: list[WifiNetwork] = []
        seen: set[str] = set()
        for line in out.splitlines():
            parts = self._parse_nmcli_terse(line)
            if len(parts) >= 4:
                ssid = parts[0].strip()
                if not ssid or ssid in seen:
                    continue
                seen.add(ssid)
                networks.append(WifiNetwork(
                    ssid=ssid,
                    signal=int(parts[1]) if parts[1].isdigit() else 0,
                    security=parts[2] if parts[2] else "Open",
                    connected=parts[3].strip() == "yes",
                ))
        return sorted(networks, key=lambda n: n.signal, reverse=True)

    def connect(self, ssid: str, password: str) -> tuple[bool, str]:
        rc, out = self._run(["sudo", "nmcli", "device", "wifi", "connect", ssid,
                             "password", password])
        if rc == 0:
            logger.info("Connected to WiFi: %s", ssid)
            return True, f"Connected to '{ssid}'"
        logger.warning("WiFi connection failed: %s", out)
        return False, out or "Connection failed"

    def disconnect(self) -> bool:
        rc, _ = self._run(["sudo", "nmcli", "device", "disconnect", "wlan0"])
        return rc == 0

    def get_saved_networks(self) -> list[str]:
        rc, out = self._run(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"])
        if rc != 0:
            return []
        networks = []
        for line in out.splitlines():
            parts = self._parse_nmcli_terse(line)
            if len(parts) >= 2 and "wireless" in parts[1]:
                networks.append(parts[0])
        return networks

    def forget_network(self, ssid: str) -> bool:
        rc, _ = self._run(["sudo", "nmcli", "connection", "delete", ssid])
        return rc == 0


def create_wifi_manager(mock: bool = False) -> WifiManagerBase:
    """Factory function to create the appropriate WiFi manager.

    Args:
        mock: If True, return a MockWifiManager for desktop testing.
    """
    if mock:
        return MockWifiManager()
    return RealWifiManager()
