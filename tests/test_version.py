"""Tests for src.utils.version — git-tag-based version resolution."""

import subprocess
from unittest.mock import patch

import pytest

from src.utils.version import (
    _strip_v_prefix,
    format_version_short,
    get_version,
)


# ---------------------------------------------------------------------------
# format_version_short
# ---------------------------------------------------------------------------


class TestFormatVersionShort:
    """Unit tests for the LCD display formatter."""

    def test_clean_tag(self) -> None:
        assert format_version_short("1.0.0") == "1.0.0"

    def test_tag_with_commits_ahead(self) -> None:
        assert format_version_short("1.0.0-3-gabcdef") == "1.0.0+3"

    def test_hash_only_fallback(self) -> None:
        assert format_version_short("abcdef1") == "abcdef1"

    def test_two_digit_patch(self) -> None:
        assert format_version_short("1.2.10-15-g1234567") == "1.2.10+15"

    def test_truncation(self) -> None:
        result = format_version_short("1.0.0-100-gabcdef1", max_length=10)
        assert len(result) <= 10

    def test_unknown(self) -> None:
        assert format_version_short("unknown") == "unknown"


# ---------------------------------------------------------------------------
# _strip_v_prefix
# ---------------------------------------------------------------------------


class TestStripVPrefix:
    """Unit tests for the v-prefix stripper."""

    def test_lowercase_v(self) -> None:
        assert _strip_v_prefix("v1.0.0") == "1.0.0"

    def test_uppercase_v(self) -> None:
        assert _strip_v_prefix("V1.0.0") == "1.0.0"

    def test_no_prefix(self) -> None:
        assert _strip_v_prefix("1.0.0") == "1.0.0"

    def test_empty(self) -> None:
        assert _strip_v_prefix("") == ""


# ---------------------------------------------------------------------------
# get_version (integration — runs in the real repo)
# ---------------------------------------------------------------------------


class TestGetVersion:
    """Integration test: get_version() should work in this git repo."""

    def test_returns_non_empty_string(self) -> None:
        # Reset the cache so we get a fresh resolution.
        import src.utils.version as mod
        mod._cached_version = None

        version = get_version()
        assert isinstance(version, str)
        assert len(version) > 0
        assert version != "unknown"

    def test_no_leading_v(self) -> None:
        import src.utils.version as mod
        mod._cached_version = None

        version = get_version()
        assert not version.startswith("v")
        assert not version.startswith("V")

    def test_caching(self) -> None:
        import src.utils.version as mod
        mod._cached_version = "cached-test-value"

        assert get_version() == "cached-test-value"

        # Clean up
        mod._cached_version = None
