"""Tests for src.hal.audio_mock — MockAudio behaviour + Gotcha #2 guard.

Gotcha #2: new sounds must be registered in BOTH
``config/default.yaml > audio.sounds`` AND ``MockAudio._sounds``.
The mock's sound dict is hardcoded, not loaded from config — so the
two diverge silently if one is updated without the other.
"""

from pathlib import Path

import yaml

from src.hal.audio_mock import MockAudio


def _config_sounds() -> dict[str, str]:
    """Read ``audio.sounds`` from the real default.yaml."""
    project_root = Path(__file__).resolve().parent.parent.parent
    data = yaml.safe_load(
        (project_root / "config" / "default.yaml").read_text(encoding="utf-8")
    )
    return data["audio"]["sounds"]


class TestSoundRegistrationParity:
    """Gotcha #2: config defaults and mock dict must list the same sounds."""

    def test_every_config_sound_is_in_mock_sounds(self) -> None:
        config_sounds = _config_sounds()
        mock = MockAudio()
        mock.init()
        missing = set(config_sounds) - set(mock._sounds)
        assert not missing, (
            f"Sounds defined in config/default.yaml but not in "
            f"MockAudio._sounds: {missing}. "
            f"Update src/hal/audio_mock.py::MockAudio.init()."
        )

    def test_every_mock_sound_is_in_config(self) -> None:
        config_sounds = _config_sounds()
        mock = MockAudio()
        mock.init()
        missing = set(mock._sounds) - set(config_sounds)
        assert not missing, (
            f"Sounds in MockAudio._sounds but not in config/default.yaml: "
            f"{missing}. Either register them in default.yaml or remove "
            f"from the mock."
        )


class TestSetVolume:
    """``set_volume`` clamps to [0.0, 1.0]."""

    def test_volume_clamped_to_unit_interval(self) -> None:
        mock = MockAudio()
        mock.set_volume(1.5)
        assert mock._volume == 1.0
        mock.set_volume(-0.3)
        assert mock._volume == 0.0
        mock.set_volume(0.42)
        assert mock._volume == 0.42


class TestUnknownSound:
    """Playing an unknown sound name logs a warning instead of raising."""

    def test_play_unknown_sound_does_not_raise(self, caplog) -> None:
        mock = MockAudio()
        mock.init()
        with caplog.at_level("WARNING"):
            mock.play("nonexistent-sound")
        assert any(
            "unknown sound" in r.message.lower() for r in caplog.records
        )


class TestShutdown:
    """``shutdown`` is idempotent — safe to call when never init'd or twice."""

    def test_shutdown_twice_is_safe(self) -> None:
        mock = MockAudio()
        mock.init()
        mock.shutdown()
        mock.shutdown()  # must not raise
