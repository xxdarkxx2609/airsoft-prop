"""Tests for src.hal.usb_detector_mock — permissive and strict modes."""

import hashlib

from src.hal.usb_detector_mock import MockUsbDetector


class TestPermissiveMode:
    """With no allowlist, the mock returns the raw inserted flag."""

    def test_is_key_present_reflects_inserted_flag(self) -> None:
        det = MockUsbDetector()
        det.init()
        assert det.is_key_present() is False
        det.key_inserted = True
        assert det.is_key_present() is True

    def test_defuse_and_tournament_are_independent(self) -> None:
        det = MockUsbDetector()
        det.init()
        det.key_inserted = True
        det.tournament_key_inserted = False
        assert det.is_key_present() is True
        assert det.is_tournament_key_present() is False

        det.key_inserted = False
        det.tournament_key_inserted = True
        assert det.is_key_present() is False
        assert det.is_tournament_key_present() is True


class TestStrictMode:
    """With an allowlist, the in-memory token's SHA-256 must match."""

    def test_valid_token_passes_validation(self) -> None:
        det = MockUsbDetector()
        det.init()
        det.set_valid_defuse_token("the-real-token")
        det.key_inserted = True
        assert det.is_key_present() is True

    def test_wrong_token_fails_validation(self) -> None:
        det = MockUsbDetector()
        det.init()
        # Register the allowlist for one token, but put a DIFFERENT
        # token on the simulated stick.
        valid_hash = hashlib.sha256(b"correct-token").hexdigest()
        det.reload_allowlists(
            defuse_hashes=frozenset({valid_hash}),
            tournament_hashes=frozenset(),
        )
        det._defuse_token = "wrong-token"
        det.key_inserted = True
        assert det.is_key_present() is False


class TestReloadAllowlists:
    """``reload_allowlists`` swaps in new hashes without a restart."""

    def test_reload_replaces_existing_allowlist(self) -> None:
        det = MockUsbDetector()
        det.init()
        det.set_valid_defuse_token("first-token")
        det.key_inserted = True
        assert det.is_key_present() is True

        # Revoke "first-token" by reloading with an unrelated allowlist.
        new_hash = hashlib.sha256(b"new-token").hexdigest()
        det.reload_allowlists(
            defuse_hashes=frozenset({new_hash}),
            tournament_hashes=frozenset(),
        )
        # The mock stick still carries "first-token" which is no longer valid.
        assert det.is_key_present() is False
