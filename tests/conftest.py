"""Shared pytest fixtures for the airsoft-prop test suite.

Fixtures here are visible to every test under ``tests/``. Keep them
small and side-effect-free — anything that touches global state must
clean up via ``monkeypatch`` or a yield-fixture.
"""

from pathlib import Path

import pytest


@pytest.fixture
def tmp_project_root(tmp_path, monkeypatch):
    """Redirect the config loader's paths to a clean temp directory.

    Creates ``<tmp>/config/`` and ``<tmp>/custom/``, seeds the temp
    config dir with the real ``default.yaml`` so ``Config()`` can load,
    and monkeypatches the module-level constants in
    :mod:`src.utils.config` so all subsequent loads/writes target the
    temp tree instead of the real project.

    Yields:
        Path to the temp root containing ``config/`` and ``custom/``.
    """
    config_dir = tmp_path / "config"
    custom_dir = tmp_path / "custom"
    config_dir.mkdir()
    custom_dir.mkdir()

    project_root = Path(__file__).resolve().parent.parent
    src_default = project_root / "config" / "default.yaml"
    (config_dir / "default.yaml").write_bytes(src_default.read_bytes())

    from src.utils import config as cfg_module

    monkeypatch.setattr(cfg_module, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cfg_module, "_CONFIG_DIR", config_dir)
    monkeypatch.setattr(cfg_module, "_CUSTOM_DIR", custom_dir)

    return tmp_path


@pytest.fixture
def mock_config(tmp_project_root):
    """A fresh :class:`Config` loaded from the temp project root."""
    from src.utils.config import Config
    return Config()


@pytest.fixture
def mock_app(tmp_project_root):
    """A minimally-wired :class:`App` with every HAL slot filled by a mock.

    ``App.init()`` is NOT called — we attach the HAL instances directly so
    the daemon threads / pygame windows / web server stay out of the test.
    Tests that need screens should register them explicitly.
    """
    from src.app import App
    from src.hal.audio_mock import MockAudio
    from src.hal.battery_none import NoBattery
    from src.hal.display_mock import MockDisplay
    from src.hal.input_mock import MockInput
    from src.hal.led_mock import MockLed
    from src.hal.usb_detector_mock import MockUsbDetector
    from src.hal.wires_mock import MockWires

    app = App(mock=True)
    app.audio = MockAudio()
    app.display = MockDisplay()
    app.input = MockInput()  # NOT init'd — would spawn a stdin reader thread
    app.wires = MockWires()
    app.battery = NoBattery()
    app.usb_detector = MockUsbDetector()
    app.led = MockLed()
    return app
