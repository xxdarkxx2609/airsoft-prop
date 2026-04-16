"""Configuration loader for Airsoft Prop.

Loads YAML configuration files with default fallbacks.
User overrides are stored separately in user.yaml to survive updates.
"""

import copy
from pathlib import Path
from typing import Any

import yaml

from src.utils.logger import get_logger
from src.utils.paths import get_project_root

logger = get_logger(__name__)

_PROJECT_ROOT = get_project_root()
_CONFIG_DIR = _PROJECT_ROOT / "config"
_CUSTOM_DIR = _PROJECT_ROOT / "custom"


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override dict into base dict.

    Args:
        base: Base dictionary (modified in place).
        override: Dictionary with overriding values.

    Returns:
        Merged dictionary.
    """
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def load_yaml(filename: str) -> dict[str, Any]:
    """Load a YAML file from the config directory.

    Args:
        filename: Name of the YAML file (e.g. 'default.yaml').

    Returns:
        Parsed dictionary. Empty dict if file not found.
    """
    path = _CONFIG_DIR / filename
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _load_custom_yaml(filename: str) -> dict[str, Any]:
    """Load a YAML file from the custom/ directory.

    Args:
        filename: Name of the YAML file (e.g. 'user.yaml').

    Returns:
        Parsed dictionary. Empty dict if file not found.
    """
    path = _CUSTOM_DIR / filename
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _ensure_custom_dir() -> None:
    """Create the custom/ directory if it doesn't exist."""
    _CUSTOM_DIR.mkdir(parents=True, exist_ok=True)


def _migrate_config_to_custom() -> None:
    """One-time migration of user.yaml and usb_keys.yaml from config/ to custom/.

    Moves files only if they exist in config/ and do NOT yet exist in custom/.
    """
    _ensure_custom_dir()
    for filename in ("user.yaml", "usb_keys.yaml"):
        old_path = _CONFIG_DIR / filename
        new_path = _CUSTOM_DIR / filename
        if old_path.exists() and not new_path.exists():
            old_path.rename(new_path)
            logger.info("Migrated %s from config/ to custom/", filename)


class Config:
    """Application configuration container.

    Loads and merges all config files, provides nested key access.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._defaults: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load all configuration files.

        Load order: default.yaml → custom/user.yaml → hardware.yaml →
        custom/hardware.yaml → network.yaml.
        User overrides win over defaults but are stored separately in custom/.
        custom/hardware.yaml overrides config/hardware.yaml for HAL selection.
        """
        # Migrate legacy config/user.yaml → custom/user.yaml on first load.
        _migrate_config_to_custom()

        base = load_yaml("default.yaml")
        self._defaults = copy.deepcopy(base)
        self._data = base

        user = _load_custom_yaml("user.yaml")
        if user:
            _deep_merge(self._data, user)

        hardware = load_yaml("hardware.yaml")
        network = load_yaml("network.yaml")
        _deep_merge(self._data, hardware)

        custom_hardware = _load_custom_yaml("hardware.yaml")
        if custom_hardware:
            _deep_merge(self._data, custom_hardware)

        _deep_merge(self._data, network)

        # Enforce device_name length limit (max 7 chars for 20-col LCD).
        game = self._data.get("game", {})
        dn = game.get("device_name", "Prop")
        if isinstance(dn, str) and len(dn) > 7:
            logger.warning("device_name '%s' exceeds 7 chars, truncating", dn)
            game["device_name"] = dn[:7]

        # Inject version derived from git tags (overrides any stale YAML value).
        from src.utils.version import get_version
        self._data["version"] = get_version()

        logger.info("Configuration loaded from %s", _CONFIG_DIR)

    def get(self, *keys: str, default: Any = None) -> Any:
        """Get a nested config value using dot-separated keys.

        Args:
            *keys: Key path (e.g. 'game', 'default_timer').
            default: Default value if key not found.

        Returns:
            Config value or default.

        Example:
            config.get('game', 'default_timer', default=300)
            config.get('hal', 'display', default='mock')
        """
        current = self._data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current

    def get_hal_type(self, component: str) -> str:
        """Get the HAL implementation type for a component.

        Args:
            component: HAL component name ('display', 'audio', 'input', 'wires', 'battery').

        Returns:
            Implementation type string (e.g. 'mock', 'lcd', 'gpio').
        """
        return self.get("hal", component, default="mock")

    # -- Tournament helpers ---------------------------------------------------

    def is_tournament_enabled(self) -> bool:
        """Check if tournament mode is active."""
        return self.get("tournament", "enabled", default=False)

    def get_tournament_mode(self) -> str:
        """Get the configured tournament game mode module name."""
        return self.get("tournament", "mode", default="random_code")

    def get_tournament_pin(self) -> str:
        """Get the 4-digit tournament exit PIN."""
        return str(self.get("tournament", "pin", default="0000"))

    def get_tournament_settings(self) -> dict[str, Any]:
        """Get the tournament mode-specific settings."""
        return self.get("tournament", "settings", default={})

    @property
    def data(self) -> dict[str, Any]:
        """Access the raw config dictionary."""
        return self._data

    @property
    def project_root(self) -> Path:
        """Get the project root directory."""
        return _PROJECT_ROOT

    def save_user_config(self, flat_overrides: dict[str, Any]) -> None:
        """Save user overrides to user.yaml (only keys differing from defaults).

        Args:
            flat_overrides: Flat dict with dot-separated keys,
                e.g. {"audio.volume": 0.7, "game.default_timer": 600}.
        """
        # Build nested dict from flat dot-separated keys
        nested: dict[str, Any] = {}
        for dotted_key, value in flat_overrides.items():
            keys = dotted_key.split(".")
            target = nested
            for k in keys[:-1]:
                target = target.setdefault(k, {})
            target[keys[-1]] = value

        # Keep only keys that differ from defaults
        user_overrides = self._diff_from_defaults(nested, self._defaults)

        _ensure_custom_dir()
        config_path = _CUSTOM_DIR / "user.yaml"
        if user_overrides:
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(user_overrides, f, default_flow_style=False, allow_unicode=True)
            logger.info("User config saved to %s", config_path)
        else:
            # All values match defaults — remove user.yaml
            if config_path.exists():
                config_path.unlink()
                logger.info("User config removed (all values match defaults)")

        self._load()

    def reset_user_config(self) -> None:
        """Delete user.yaml and reload defaults."""
        config_path = _CUSTOM_DIR / "user.yaml"
        if config_path.exists():
            config_path.unlink()
        self._load()

    def load_usb_keys(self) -> dict[str, list]:
        """Load USB key registry from usb_keys.yaml.

        Returns:
            Dict with ``defuse_keys`` and ``tournament_keys`` lists.
            Each entry is a dict with ``id``, ``label``, ``token_hash``,
            and ``created_at``. Returns empty lists if the file does not
            exist.
        """
        data = _load_custom_yaml("usb_keys.yaml")
        return {
            "defuse_keys": data.get("defuse_keys", []) if data else [],
            "tournament_keys": data.get("tournament_keys", []) if data else [],
        }

    def save_usb_keys(self, usb_keys: dict[str, list]) -> None:
        """Write USB key registry to usb_keys.yaml.

        This file is intentionally separate from user.yaml so that
        ``reset_user_config()`` never deletes registered keys.

        Args:
            usb_keys: Dict with ``defuse_keys`` and ``tournament_keys`` lists.
        """
        _ensure_custom_dir()
        config_path = _CUSTOM_DIR / "usb_keys.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(usb_keys, f, default_flow_style=False, allow_unicode=True)
        logger.info("USB keys saved to %s", config_path)

    def save_hardware_config(self, hal_overrides: dict[str, str]) -> None:
        """Save HAL module selections to custom/hardware.yaml.

        Writes only the ``hal`` block to ``custom/hardware.yaml``.  This file
        takes priority over ``config/hardware.yaml`` so that user selections
        survive firmware updates without modifying the versioned defaults.

        Args:
            hal_overrides: Flat dict mapping component names to HAL type strings,
                e.g. ``{"display": "lcd", "audio": "custom:my_audio.MyAudio"}``.
        """
        _ensure_custom_dir()
        config_path = _CUSTOM_DIR / "hardware.yaml"
        data: dict[str, Any] = {"hal": hal_overrides}
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        logger.info("Custom hardware config saved to %s", config_path)
        self._load()

    # Built-in HAL options per component (must match src/hal/ implementations).
    _BUILTIN_HAL_OPTIONS: dict[str, list[str]] = {
        "display": ["lcd", "mock"],
        "audio": ["pygame", "mock"],
        "input": ["numpad", "mock"],
        "wires": ["gpio", "mock"],
        "battery": ["pisugar", "none", "mock"],
        "usb_detector": ["usb_detector", "mock"],
        "led": ["gpio", "mock"],
    }

    def get_available_hal_modules(self, component: str) -> list[str]:
        """Return available HAL implementations for a component.

        Combines built-in type strings with ``custom:module.Class`` entries
        discovered from ``custom/hal/*.py``.

        Args:
            component: HAL component name (e.g. ``"display"``).

        Returns:
            List of type strings, built-ins first, then custom entries sorted
            alphabetically.
        """
        import ast

        builtin = list(self._BUILTIN_HAL_OPTIONS.get(component, []))
        custom_hal_dir = _CUSTOM_DIR / "hal"
        custom_entries: list[str] = []

        if custom_hal_dir.is_dir():
            for py_file in sorted(custom_hal_dir.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                try:
                    source = py_file.read_text(encoding="utf-8")
                    tree = ast.parse(source, filename=str(py_file))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            custom_entries.append(
                                f"custom:{py_file.stem}.{node.name}"
                            )
                except Exception:
                    logger.warning(
                        "Could not parse custom HAL file %s", py_file, exc_info=True
                    )

        return builtin + custom_entries

    def get_all_available_hal_modules(self) -> dict[str, list[str]]:
        """Return available HAL implementations for all components.

        Returns:
            Dict mapping component names to lists of available type strings.
        """
        return {
            component: self.get_available_hal_modules(component)
            for component in self._BUILTIN_HAL_OPTIONS
        }

    def get_customized_keys(self) -> set[str]:
        """Return dot-separated keys that have user overrides."""
        user = _load_custom_yaml("user.yaml")
        if not user:
            return set()
        return self._flatten_keys(user)

    @staticmethod
    def _diff_from_defaults(override: dict, defaults: dict) -> dict:
        """Return only keys from override whose values differ from defaults."""
        diff: dict[str, Any] = {}
        for key, value in override.items():
            if key not in defaults:
                diff[key] = value
            elif isinstance(value, dict) and isinstance(defaults[key], dict):
                sub_diff = Config._diff_from_defaults(value, defaults[key])
                if sub_diff:
                    diff[key] = sub_diff
            elif value != defaults[key]:
                diff[key] = value
        return diff

    @staticmethod
    def _flatten_keys(d: dict, prefix: str = "") -> set[str]:
        """Flatten a nested dict into dot-separated key paths."""
        keys: set[str] = set()
        for k, v in d.items():
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                keys.update(Config._flatten_keys(v, full_key))
            else:
                keys.add(full_key)
        return keys
