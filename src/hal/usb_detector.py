"""Real USB key detector — scans mounted media for key files.

Polls common mount points (``/media/``, ``/mnt/``) on Linux for
removable storage containing a specific key file. When a USB key
registry has been configured (via the web interface), each found file's
content is validated against stored SHA-256 hashes. Without any
registered keys the detector operates in permissive mode and accepts
any file with the correct name (backward-compatible with existing
deployments).
"""

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from src.hal.base import UsbDetectorBase
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.utils.config import Config

logger = get_logger(__name__)

# Direct mount points used by the airsoft-prop udev/systemd setup.
# On Raspberry Pi OS Lite (no desktop automounter), the custom
# usb-mount@.service mounts USB sticks directly to /media/usb.
_DIRECT_MOUNTS: list[str] = ["/media/usb"]

# Parent directories whose subdirectories are scanned as mount points.
# Covers udisks2-based mounts (/media/pi/<LABEL>) and legacy setups.
_MEDIA_DIRS: list[str] = ["/media", "/mnt"]


class UsbDetector(UsbDetectorBase):
    """Detect USB sticks containing specific key files.

    First checks the direct mount point /media/usb (used by the
    airsoft-prop udev/systemd setup on Raspberry Pi OS Lite), then
    falls back to scanning subdirectories of /media and /mnt for
    udisks2-style mounts (e.g. /media/pi/<LABEL>).

    When a USB key registry exists (``config/usb_keys.yaml`` has at
    least one entry), the file content is read and its SHA-256 hash is
    compared against the stored allowlist. An empty allowlist means
    permissive mode: any file with the correct name is accepted.

    Allowlists are held as frozensets in memory after ``init()`` for
    O(1) lookup during gameplay. The web server can push updated hashes
    at runtime via ``reload_allowlists()`` without restarting the
    service. frozenset replacement is atomic in CPython (GIL ensures
    single-instruction name binding), so no explicit lock is required
    on the single-core Pi Zero.
    """

    def __init__(self, config: Optional["Config"] = None) -> None:
        """Initialise the detector and load allowlists from config.

        Args:
            config: Application config instance. If provided, the USB
                key registry is loaded from ``usb_keys.yaml`` at
                construction time.
        """
        self._defuse_allowlist: frozenset[str] = frozenset()
        self._tournament_allowlist: frozenset[str] = frozenset()
        if config is not None:
            self._load_allowlists_from_config(config)

    def _load_allowlists_from_config(self, config: "Config") -> None:
        """Read usb_keys.yaml via config and populate in-memory sets."""
        keys = config.load_usb_keys()
        self._defuse_allowlist = frozenset(
            k["token_hash"] for k in keys.get("defuse_keys", []) if "token_hash" in k
        )
        self._tournament_allowlist = frozenset(
            k["token_hash"]
            for k in keys.get("tournament_keys", [])
            if "token_hash" in k
        )

    def init(self) -> None:
        """Log initialisation."""
        logger.info(
            "USB detector initialized (direct=%s, scan=%s, "
            "defuse_keys=%d, tournament_keys=%d)",
            _DIRECT_MOUNTS,
            _MEDIA_DIRS,
            len(self._defuse_allowlist),
            len(self._tournament_allowlist),
        )

    def reload_allowlists(
        self,
        defuse_hashes: frozenset[str],
        tournament_hashes: frozenset[str],
    ) -> None:
        """Hot-reload the in-memory token allowlists.

        Called by the web server after a new key is generated or revoked,
        so the running game loop picks up the change without a restart.

        Args:
            defuse_hashes: SHA-256 hex digests of valid DEFUSE.KEY tokens.
            tournament_hashes: SHA-256 hex digests of valid TOURNAMENT.KEY tokens.
        """
        self._defuse_allowlist = defuse_hashes
        self._tournament_allowlist = tournament_hashes
        logger.info(
            "USB allowlists reloaded: defuse=%d, tournament=%d",
            len(defuse_hashes),
            len(tournament_hashes),
        )

    @staticmethod
    def _hash_key_file(path: Path) -> Optional[str]:
        """Read a key file and return its SHA-256 hex digest.

        The file content is stripped of leading/trailing whitespace
        before hashing so that a trailing newline (written by the key
        generator) does not affect the comparison.

        Args:
            path: Path to the key file.

        Returns:
            Hex digest string, or None if the file cannot be read.
        """
        try:
            content = path.read_text(encoding="utf-8", errors="replace").strip()
            if not content:
                return None
            return hashlib.sha256(content.encode()).hexdigest()
        except OSError:
            return None

    def _scan_for_valid_key(self, filename: str, allowlist: frozenset[str]) -> bool:
        """Scan media mount points for a file with a valid token.

        When ``allowlist`` is empty the detector operates in permissive
        mode: any file with the correct name is accepted (backward
        compatibility for installations that have not yet registered any
        keys via the web interface).

        When ``allowlist`` is non-empty the file content is read and its
        SHA-256 hash must match one of the stored hashes.

        Args:
            filename: The file to search for (e.g. ``DEFUSE.KEY``).
            allowlist: Set of valid SHA-256 hex digests. Empty means
                permissive mode.

        Returns:
            True if a valid key file is found on any mounted device.
        """
        permissive = not allowlist

        # Check direct mount points first (/media/usb)
        for direct in _DIRECT_MOUNTS:
            try:
                key_file = Path(direct) / filename
                if key_file.is_file():
                    if permissive:
                        return True
                    digest = self._hash_key_file(key_file)
                    if digest and digest in allowlist:
                        return True
            except OSError:
                pass

        # Fall back to scanning subdirectories (udisks2 / legacy)
        for base in _MEDIA_DIRS:
            base_path = Path(base)
            if not base_path.is_dir():
                continue
            try:
                mounts = list(base_path.iterdir())
            except OSError:
                continue
            for mount in mounts:
                if not mount.is_dir():
                    continue
                try:
                    key_file = mount / filename
                    if key_file.is_file():
                        if permissive:
                            return True
                        digest = self._hash_key_file(key_file)
                        if digest and digest in allowlist:
                            return True
                    # Also check sub-mounts (e.g. /media/pi/USBSTICK/)
                    for sub in mount.iterdir():
                        if sub.is_dir():
                            try:
                                sub_file = sub / filename
                                if sub_file.is_file():
                                    if permissive:
                                        return True
                                    digest = self._hash_key_file(sub_file)
                                    if digest and digest in allowlist:
                                        return True
                            except OSError:
                                continue
                except OSError:
                    continue
        return False

    def is_key_present(self) -> bool:
        """Scan media mount points for a valid DEFUSE.KEY."""
        return self._scan_for_valid_key("DEFUSE.KEY", self._defuse_allowlist)

    def is_tournament_key_present(self) -> bool:
        """Scan media mount points for a valid TOURNAMENT.KEY."""
        return self._scan_for_valid_key("TOURNAMENT.KEY", self._tournament_allowlist)

    def shutdown(self) -> None:
        """No resources to release."""
        logger.debug("USB detector shut down")
