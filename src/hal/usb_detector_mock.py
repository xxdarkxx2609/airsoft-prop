"""Mock USB key detector for desktop testing.

Simulates USB stick insertion/removal via toggleable flags.  The flags
are controlled externally (e.g. by a key press in MockInput or by the
USB Key Cracker mode's on_input handler).

When a token allowlist is loaded (via ``reload_allowlists`` or
``set_valid_defuse_token``), the mock validates the in-memory token
against the allowlist — mirroring the real detector's strict-mode
behaviour for integration tests.  Without any registered tokens the
mock operates in permissive mode (any file/flag is accepted), matching
the real detector's backward-compatibility behaviour.
"""

import hashlib
from typing import Optional

from src.hal.base import UsbDetectorBase
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MockUsbDetector(UsbDetectorBase):
    """Mock USB detector that stores key-present state in memory.

    Call ``toggle()`` or set ``key_inserted`` directly to simulate
    plugging/unplugging a USB stick with DEFUSE.KEY.
    Call ``toggle_tournament()`` or set ``tournament_key_inserted``
    to simulate a TOURNAMENT.KEY stick.

    For validated-mode tests use ``set_valid_defuse_token()`` /
    ``set_valid_tournament_token()`` to register a token before toggling
    insertion, then the mock will only return ``True`` when that token's
    hash matches the allowlist.
    """

    def __init__(self) -> None:
        self.key_inserted: bool = False
        self.tournament_key_inserted: bool = False

        # In-memory allowlists (frozenset of SHA-256 hex digests)
        self._defuse_allowlist: frozenset[str] = frozenset()
        self._tournament_allowlist: frozenset[str] = frozenset()

        # The token "on the mock USB stick" (used for hash comparison)
        self._defuse_token: Optional[str] = None
        self._tournament_token: Optional[str] = None

    def init(self) -> None:
        """Log initialisation."""
        self.key_inserted = False
        self.tournament_key_inserted = False
        logger.info("Mock USB detector initialized (press '.' to toggle)")

    # ------------------------------------------------------------------
    # Token helpers for testing validated mode
    # ------------------------------------------------------------------

    def set_valid_defuse_token(self, token: str) -> None:
        """Register a defuse token so that strict-mode validation passes.

        Computes the SHA-256 hash and stores it in the allowlist.  The
        token is also stored as the simulated file content of the mock
        USB stick.

        Args:
            token: The raw token string (e.g. a UUID4).
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        self._defuse_token = token
        self._defuse_allowlist = frozenset({token_hash})

    def set_valid_tournament_token(self, token: str) -> None:
        """Register a tournament token so that strict-mode validation passes.

        Args:
            token: The raw token string (e.g. a UUID4).
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        self._tournament_token = token
        self._tournament_allowlist = frozenset({token_hash})

    # ------------------------------------------------------------------
    # UsbDetectorBase interface
    # ------------------------------------------------------------------

    def reload_allowlists(
        self,
        defuse_hashes: frozenset[str],
        tournament_hashes: frozenset[str],
    ) -> None:
        """Hot-reload the in-memory token allowlists.

        Args:
            defuse_hashes: SHA-256 hex digests of valid DEFUSE.KEY tokens.
            tournament_hashes: SHA-256 hex digests of valid TOURNAMENT.KEY tokens.
        """
        self._defuse_allowlist = defuse_hashes
        self._tournament_allowlist = tournament_hashes
        logger.debug(
            "Mock USB allowlists reloaded: defuse=%d, tournament=%d",
            len(defuse_hashes),
            len(tournament_hashes),
        )

    def is_key_present(self) -> bool:
        """Return the simulated DEFUSE.KEY state.

        In permissive mode (no allowlist): returns ``key_inserted``.
        In strict mode (allowlist set): additionally validates the
        in-memory token against the allowlist.
        """
        if not self.key_inserted:
            return False
        if not self._defuse_allowlist:
            # Permissive mode — no keys registered yet
            return True
        if self._defuse_token is None:
            # Allowlist exists but no token on the mock stick → reject
            return False
        digest = hashlib.sha256(self._defuse_token.encode()).hexdigest()
        return digest in self._defuse_allowlist

    def is_tournament_key_present(self) -> bool:
        """Return the simulated TOURNAMENT.KEY state.

        In permissive mode (no allowlist): returns ``tournament_key_inserted``.
        In strict mode (allowlist set): additionally validates the
        in-memory token against the allowlist.
        """
        if not self.tournament_key_inserted:
            return False
        if not self._tournament_allowlist:
            return True
        if self._tournament_token is None:
            return False
        digest = hashlib.sha256(self._tournament_token.encode()).hexdigest()
        return digest in self._tournament_allowlist

    # ------------------------------------------------------------------
    # Toggle helpers
    # ------------------------------------------------------------------

    def toggle(self) -> None:
        """Toggle the simulated DEFUSE.KEY insertion state."""
        self.key_inserted = not self.key_inserted
        state = "inserted" if self.key_inserted else "removed"
        logger.info("Mock USB key (DEFUSE) %s", state)

    def toggle_tournament(self) -> None:
        """Toggle the simulated TOURNAMENT.KEY insertion state."""
        self.tournament_key_inserted = not self.tournament_key_inserted
        state = "inserted" if self.tournament_key_inserted else "removed"
        logger.info("Mock USB key (TOURNAMENT) %s", state)

    def shutdown(self) -> None:
        """Reset state."""
        self.key_inserted = False
        self.tournament_key_inserted = False
        logger.debug("Mock USB detector shut down")
