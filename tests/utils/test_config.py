"""Tests for src.utils.config — YAML loader, merge, validation.

Covers Gotcha #4 layer 1 (device_name 7-char truncation in config load)
and Gotcha #5 (reset_user_config preserves usb_keys.yaml / web.yaml /
branding.yaml).
"""

import yaml

from src.utils.config import Config, _deep_merge


# ---------------------------------------------------------------------------
# _deep_merge
# ---------------------------------------------------------------------------


class TestDeepMerge:
    """Unit tests for the dict-merge helper."""

    def test_nested_dict_merge(self) -> None:
        base = {"a": {"b": 1, "c": 2}}
        override = {"a": {"b": 10}}
        result = _deep_merge(base, override)
        assert result == {"a": {"b": 10, "c": 2}}

    def test_list_is_replaced_not_appended(self) -> None:
        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}
        result = _deep_merge(base, override)
        assert result == {"items": [4, 5]}

    def test_none_override(self) -> None:
        base = {"key": "value"}
        override = {"key": None}
        result = _deep_merge(base, override)
        assert result == {"key": None}


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


class TestConfigLoad:
    """Tests for the full Config loading + override behaviour."""

    def test_defaults_load_cleanly_without_user_yaml(self, mock_config) -> None:
        assert mock_config.get("audio", "volume") == 0.5
        assert mock_config.get("game", "default_timer") == 300
        assert mock_config.get("game", "device_name") == "Prop"

    def test_user_yaml_overrides_defaults(self, tmp_project_root) -> None:
        user_yaml = tmp_project_root / "custom" / "user.yaml"
        user_yaml.write_text(
            yaml.dump({"audio": {"volume": 0.9}}),
            encoding="utf-8",
        )
        config = Config()
        assert config.get("audio", "volume") == 0.9
        # Unrelated default keys still present.
        assert config.get("game", "default_timer") == 300

    def test_device_name_over_seven_chars_truncated(
        self, tmp_project_root, caplog
    ) -> None:
        user_yaml = tmp_project_root / "custom" / "user.yaml"
        user_yaml.write_text(
            yaml.dump({"game": {"device_name": "VeryLongName"}}),
            encoding="utf-8",
        )
        with caplog.at_level("WARNING"):
            config = Config()
        assert config.get("game", "device_name") == "VeryLon"
        assert any("device_name" in r.message for r in caplog.records)

    def test_get_with_default_for_missing_key(self, mock_config) -> None:
        assert mock_config.get("nonexistent", default="fallback") == "fallback"
        assert mock_config.get("audio", "missing", default=42) == 42

    def test_get_hal_type_defaults_to_mock(self, mock_config) -> None:
        # hardware.yaml is not seeded in tmp_project_root, so all
        # components fall back to the default "mock" string.
        assert mock_config.get_hal_type("display") == "mock"
        assert mock_config.get_hal_type("audio") == "mock"

    def test_tournament_helpers_roundtrip(self, tmp_project_root) -> None:
        user_yaml = tmp_project_root / "custom" / "user.yaml"
        user_yaml.write_text(
            yaml.dump(
                {"tournament": {"enabled": True, "mode": "cut_the_wire"}}
            ),
            encoding="utf-8",
        )
        config = Config()
        assert config.is_tournament_enabled() is True
        assert config.get_tournament_mode() == "cut_the_wire"

    def test_version_is_injected_not_read_from_yaml(
        self, tmp_project_root
    ) -> None:
        # Even if user.yaml claims a fake version, the loader overrides it
        # with the git-derived value (which is a non-empty string).
        user_yaml = tmp_project_root / "custom" / "user.yaml"
        user_yaml.write_text(
            yaml.dump({"version": "FAKE-DO-NOT-USE"}),
            encoding="utf-8",
        )
        config = Config()
        assert config.get("version") != "FAKE-DO-NOT-USE"
        assert isinstance(config.get("version"), str)
        assert config.get("version")  # non-empty


# ---------------------------------------------------------------------------
# save_user_config
# ---------------------------------------------------------------------------


class TestSaveUserConfig:
    """Tests for the diff-and-persist user override writer."""

    def test_only_keys_differing_from_defaults_are_written(
        self, mock_config, tmp_project_root
    ) -> None:
        mock_config.save_user_config({"audio.volume": 0.7})
        user_yaml = tmp_project_root / "custom" / "user.yaml"
        assert user_yaml.exists()
        data = yaml.safe_load(user_yaml.read_text(encoding="utf-8"))
        # Only the changed key — not the entire defaults tree.
        assert data == {"audio": {"volume": 0.7}}

    def test_writing_values_matching_defaults_removes_user_yaml(
        self, mock_config, tmp_project_root
    ) -> None:
        # First create a user override file.
        mock_config.save_user_config({"audio.volume": 0.7})
        assert (tmp_project_root / "custom" / "user.yaml").exists()
        # Then revert to the default — file should be removed.
        mock_config.save_user_config({"audio.volume": 0.5})
        assert not (tmp_project_root / "custom" / "user.yaml").exists()

    def test_reset_user_config_preserves_usb_keys_and_branding(
        self, mock_config, tmp_project_root
    ) -> None:
        """Gotcha #5: reset deletes user.yaml only."""
        mock_config.save_user_config({"audio.volume": 0.7})
        mock_config.save_usb_keys({"defuse_keys": [{"id": "k1"}], "tournament_keys": []})
        mock_config.save_branding({"team_name": "Alpha", "logo_file": None})

        mock_config.reset_user_config()

        assert not (tmp_project_root / "custom" / "user.yaml").exists()
        assert (tmp_project_root / "custom" / "usb_keys.yaml").exists()
        assert (tmp_project_root / "custom" / "branding.yaml").exists()
