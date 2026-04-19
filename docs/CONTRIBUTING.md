# Developer Guide

This document is aimed at developers who want to contribute to or extend the Airsoft Prop project.

For user-facing documentation, see the [README](../README.md).

---

## Technology Stack

- **OS**: Raspberry Pi OS Lite (Bookworm / Debian 12 LTS)
- **Python**: 3.11 on Pi (system Python), 3.13 on development desktop — **do not use 3.12+ features**
- **Audio**: `pygame-ce` (Community Edition, compatible with Python 3.11–3.13; **NOT** the old `pygame` — broken on Python 3.13+)
- **Package management**: `venv` + `pip` with `>=` versions in `requirements.txt`
- **Config**: YAML (`config/default.yaml` + `custom/user.yaml` for user overrides, `config/hardware.yaml`)
- **Web interface**: Flask (captive portal & configuration, port 8080)
- **Display**: RPLCD via I2C (20x4 HD44780)
- **GPIO**: RPi.GPIO or gpiozero
- **Autostart**: systemd service (`systemd/airsoft-prop.service`)
- **Standalone build**: PyInstaller → Windows .exe, GitHub Actions release

---

## Architecture Overview

### Hardware Abstraction Layer (HAL)

Each hardware component has an abstract base class in `src/hal/base.py` with concrete implementations and mock variants. Selection via `config/hardware.yaml`. Custom HAL in `custom/hal/` using the `custom:module.Class` syntax.

→ **Details: [docs/claude/hal.md](claude/hal.md)**

### Plugin System for Game Modes

Each mode is a single file in `src/modes/` (inheriting from `BaseMode`). Auto-discovery via `pkgutil`. Custom modes go in `custom/modes/`.

→ **Details: [docs/claude/modes.md](claude/modes.md)**

### State Machine

```
Normal:     BOOT → MAIN_MENU → SETUP → [PLANTING →] ARMED → DEFUSED|DETONATED → MAIN_MENU
Tournament: BOOT → TOURNAMENT → [PLANTING →] ARMED → DEFUSED|DETONATED → TOURNAMENT
Extras:     MAIN_MENU → STATUS_SCREEN (*) | UPDATE_SCREEN (/)
```

PLANTING phase only when the mode's `PlantingType` is not `INSTANT`. State management is in `src/app.py`.

### Screen System

Each screen inherits from `BaseScreen` (`src/ui/base_screen.py`): `render()`, `handle_input()`, `on_enter()`, `on_exit()`. Transitions via `ScreenManager`.

→ **Details: [docs/claude/display.md](claude/display.md)**

### Tournament Mode

Locks the device to a single configured game mode. Config: `tournament.*` in YAML.

Exit mechanisms (organizer only):
1. **Web interface** (`/tournament`) — enable/disable, mode, PIN
2. **USB stick** with `TOURNAMENT.KEY` — deactivates tournament mode
3. **PIN entry** — 5× Backspace in 3s → PIN prompt → 4-digit PIN

Cross-thread events via `App._event_queue` (`queue.Queue`): `tournament_activate`, `tournament_deactivate`, `audio_volume_changed`, `display_backlight_changed`, `logging_level_changed`.

While a game is running, saving **tournament settings** in the web UI is blocked (HTTP 409). General config changes are always possible.

### Logging

Central logging via `src/utils/logger.py`. All modules: `get_logger(__name__)`. Automatic session rotation, archive cleanup. Captures: uncaught exceptions (all threads), Python warnings, stray stderr, startup diagnostics. Main loop: inner try/except, after 10 consecutive errors → clean shutdown.

---

## Code Style & Conventions

- **Python 3.11 compatible** — no 3.12+ features
- **Type hints** for all function signatures (parameters + return type), class attributes, and module-level variables. Not required for local variables where the type is obvious.
- **Google-style docstrings** for all public classes and methods. One-liner if self-explanatory, multi-line with Args/Returns for complex signatures.
- **Logging instead of print()**: use `get_logger(__name__)`, no `print()` in production code.
- **Error handling**: log hardware errors (WARNING/ERROR), return `None` or a fallback value, do not let unhandled exceptions propagate. HAL methods must never crash the main loop. On repeated failure: record the state, do not retry endlessly.
- **Configuration**: all user-configurable values must be loaded from YAML (timers, digits, volume, pins, I2C addresses). Technical constants (LCD width = 20, HOLD_TIMEOUT = 0.6s, beep intervals) may be defined as named constants in code.
- **Language**: code, comments, docstrings, LCD text, web UI — English. Project documentation (CLAUDE.md, docs/claude/) — German.
- **Web frontend**: no CSS framework (Bootstrap etc.), no JS framework (React etc.). CSS Custom Properties, Flexbox, and Grid are allowed. No frontend build step. One CSS file (`style.css`), one JS file (`app.js`).

---

## Gotchas — Read Before Touching Anything

These rules apply to **every** change:

### 1. `pygame-ce`, NOT `pygame`

The old `pygame` does not work with Python 3.13+ (removed `distutils`). Always use `pygame-ce`.

### 2. New sounds must be registered in two places

- `config/default.yaml` → `audio.sounds` (name → file path)
- `src/hal/audio_mock.py` → `MockAudio.init()` → `self._sounds` dict (hardcoded, does NOT read from config)

### 3. New game modes must be registered in two places (standalone build)

- `_KNOWN_MODES` in `src/modes/__init__.py`
- `hiddenimports` in `build/airsoft_prop.spec`

### 4. `device_name` max 7 characters

Tightest spot: `** {name} ARMED **` on a 20-column LCD. Validation in web interface + config loading.

### 5. Two-tier config

`default.yaml` (git-tracked) + `custom/user.yaml` (overrides only, gitignored). Reset deletes only `user.yaml`, not `custom/usb_keys.yaml`.

### 6. Main loop resilience

`src/app.py` has an inner try/except — a single error does not crash the app. After 10 consecutive errors → clean shutdown.

---

## Desktop Testing (Mock Mode)

```bash
git clone https://github.com/xxdarkxx2609/airsoft-prop.git
cd airsoft-prop

python3 -m venv venv
source venv/bin/activate    # Linux/macOS
# or: venv\Scripts\activate  # Windows

pip install -r requirements.txt
python -m src.main --mock
```

**What mock mode simulates:**

| Component | Behavior |
|-----------|----------|
| Display | 20×4 ASCII frame rendered in-place in the terminal (ANSI escape codes) |
| Audio | Plays real WAV files via `pygame-ce` if present in `assets/sounds/`; silent fallback |
| Input | Keyboard: digits, Enter, Backspace, arrow keys, +/−. Press `.` to toggle simulated USB key |
| USB detector | Simulated insertion/removal via `.` key; `/usb-keys` web page works without a real stick |
| LED | Logs blink events at DEBUG level |
| Battery | Starts at 85%, slowly discharges |
| Web interface | Starts on `http://localhost:8080` with simulated networks and battery data |
| Logging | Output goes to `logs/prop.log`; previous sessions archived with timestamp |

---

## Adding a New Game Mode

1. Create a new file in `src/modes/` (e.g. `my_mode.py`)
2. Inherit from `BaseMode` and implement all abstract methods
3. Set `name`, `description`, and `menu_key` class attributes
4. The mode is discovered automatically at runtime
5. For standalone builds: add the module name to `_KNOWN_MODES` in `src/modes/__init__.py` and to `hiddenimports` in `build/airsoft_prop.spec`

```python
from src.modes.base_mode import (
    BaseMode, GameContext, ModeResult, SetupOption, SetupOptionType,
)

class MyMode(BaseMode):
    name = "My Mode"
    description = "A custom game mode"
    menu_key = "6"

    def get_setup_options(self) -> list[SetupOption]:
        return [
            SetupOption(
                key="timer", label="Timer",
                option_type=SetupOptionType.RANGE,
                default=300, min_val=30, max_val=5999,
                step=30, large_step=300,
            ),
        ]

    def on_armed(self, context: GameContext) -> None:
        pass

    def on_input(self, key: str, context: GameContext) -> ModeResult:
        return ModeResult.CONTINUE

    def on_tick(self, remaining_seconds: int, context: GameContext) -> ModeResult:
        return ModeResult.CONTINUE

    def render(self, display, remaining_seconds: int, context: GameContext) -> None:
        pass

    def render_last_10s(self, display, remaining_seconds: int, context: GameContext) -> None:
        pass
```

→ See [docs/claude/modes.md](claude/modes.md) for the full API reference.

---

## Writing a Custom Game Mode (local, not upstreamed)

If you want to run a mode only on your own device without modifying the project source, place it in `custom/modes/` instead of `src/modes/`. The auto-discovery mechanism scans both directories at startup.

**Steps:**

1. Create `custom/modes/my_mode.py` (same skeleton as above)
2. Start the app — the mode appears in the main menu automatically
3. No registration needed; `custom/modes/` is gitignored, so updates will not overwrite it

```
custom/
└── modes/
    └── my_mode.py      # Your custom game mode
```

---

## Writing a Custom HAL Module

You can replace any hardware component (display, audio, input, wires, battery, USB detector, LED) with your own implementation. Custom modules live in `custom/hal/` and are selected via the web interface.

### Directory layout

```
custom/
└── hal/
    └── my_display.py   # Your custom HAL module
```

### Step-by-step

1. **Create the file** — place a `.py` file in `custom/hal/`. The filename becomes part of the selector string.
2. **Inherit from the correct base class** — import from `src/hal/base.py`:

   | Component | Base class |
   |-----------|------------|
   | display | `DisplayBase` |
   | audio | `AudioBase` |
   | input | `InputBase` |
   | wires | `WiresBase` |
   | battery | `BatteryBase` |
   | usb_detector | `UsbDetectorBase` |
   | led | `LedBase` |

3. **Implement all abstract methods** of the chosen base class.
4. **Select it in the web interface** — open `http://<prop-ip>:8080/hardware`, choose your module from the dropdown (it shows as `custom:my_display.MyDisplay`), and save.
5. **Restart the device** — HAL changes require a restart.

The web interface only lists classes it finds by statically scanning your files. If your class does not appear, check that the file is in `custom/hal/` and that the class definition is at module level (not nested inside a function or `if` block).

### Minimal example — custom display

```python
# custom/hal/my_display.py
from src.hal.base import DisplayBase

class MyDisplay(DisplayBase):
    def init(self) -> None:
        # Called once at startup — initialise your hardware here
        pass

    def write_line(self, row: int, text: str) -> None:
        print(f"[{row}] {text}")

    def write_at(self, row: int, col: int, text: str) -> None:
        pass

    def clear(self) -> None:
        pass

    def set_backlight(self, on: bool) -> None:
        pass

    def create_custom_char(self, slot: int, pattern: list[int]) -> None:
        pass

    def shutdown(self, clear_display: bool = True) -> None:
        pass

    def flush(self) -> None:
        pass
```

After placing this file in `custom/hal/`, open the web interface at `/hardware`. The option `custom:my_display.MyDisplay` will appear in the **Display** dropdown.

### Notes

- `custom/hal/` is gitignored — firmware updates will never delete your files.
- If a custom module fails to load (import error, missing dependency), the app logs a WARNING and falls back to the mock implementation so the device remains usable.
- You can read values from `config/hardware.yaml` or `custom/hardware.yaml` in your `__init__` by accepting a `Config` object — look at `src/hal/display_lcd.py` for an example.

---

## Adding Hardware for a Completely New Component Type

The HAL system covers the seven components the app knows about (`display`, `audio`, `input`, `wires`, `battery`, `usb_detector`, `led`). If you want to drive hardware that does not fit any of those slots — a smoke machine, a door lock, a second LED strip — the web interface cannot help you, because there is no slot in `App` that would call it.

**The right approach: instantiate your hardware directly inside a custom game mode.**

```python
# custom/modes/my_mode.py
from src.modes.base_mode import BaseMode, GameContext, ModeResult

class MyMode(BaseMode):
    name = "My Mode"
    description = "Uses a smoke machine"
    menu_key = "7"

    def __init__(self) -> None:
        super().__init__()
        # Import and initialise your device here.
        # Wrap everything in try/except so a missing dependency
        # does not prevent the mode from loading on other hardware.
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(23, GPIO.OUT, initial=GPIO.LOW)
            self._gpio = GPIO
        except Exception:
            self._gpio = None

    def _trigger_smoke(self) -> None:
        if self._gpio is not None:
            self._gpio.output(23, self._gpio.HIGH)

    # ... implement the rest of BaseMode ...
```

**Trade-offs vs. a proper HAL module:**

| | Custom HAL module | Direct in game mode |
|---|---|---|
| Web UI selection | Yes | No |
| Mock fallback on error | Yes (app substitutes mock) | You write it yourself |
| Reusable across modes | Yes | No — duplicated if needed in another mode |
| Suitable for | Replacing an existing component | New, mode-specific hardware |

If you find yourself reusing the same device in several modes, extract it into a helper class in `custom/hal/` anyway — you just won't get a dropdown for it. Import it directly from the mode file with a relative path or by adding `custom/` to `sys.path`.

---

## Project Structure

```
airsoft-prop/
├── CLAUDE.md                    # Architecture documentation (AI assistant context)
├── README.md                    # User-facing documentation
├── install.sh                   # One-click installer
├── update.sh                    # Git-based updater
├── requirements.txt             # Python dependencies
├── requirements-pi.txt          # Pi-specific dependencies (RPLCD, GPIO, evdev)
├── build/
│   ├── airsoft_prop.spec        # PyInstaller build spec
│   └── hook-runtime-mock.py     # Runtime hook (forces --mock on Windows builds)
├── .github/workflows/
│   └── build-release.yml        # Automated Windows release build
├── config/
│   ├── default.yaml             # Shipped defaults (game & logging settings)
│   ├── hardware.yaml            # HAL & pin configuration (shipped defaults)
│   └── network.yaml             # WiFi & web interface settings
├── custom/                      # User-local overrides (gitignored, survives updates)
│   ├── user.yaml                # Game/UI setting overrides (auto-created by web UI)
│   ├── hardware.yaml            # HAL selection overrides (managed via /hardware page)
│   ├── usb_keys.yaml            # USB key registry
│   ├── hal/                     # Custom HAL modules (custom:module.Class syntax)
│   ├── modes/                   # Custom game modes (auto-discovered)
│   └── sounds/                  # Sound file overrides (same filename = override)
├── assets/sounds/               # WAV sound files
├── logs/                        # Log files (auto-created, gitignored)
├── src/
│   ├── main.py                  # Entry point
│   ├── app.py                   # State machine & main loop
│   ├── hal/                     # Hardware Abstraction Layer
│   ├── modes/                   # Game modes (auto-discovered)
│   ├── ui/                      # Screen framework
│   ├── utils/                   # Config, logging, versioning, updater
│   └── web/                     # Flask web interface
├── systemd/
│   └── airsoft-prop.service     # Systemd unit file
└── tests/
    └── test_version.py
```

---

## Versioning & Releases

Version is derived from git tags via `git describe --tags`. No manual version file needed.

```bash
# Create a new release
git tag v1.0.1
git push origin v1.0.1
```

GitHub Actions will automatically build and publish a Windows `.exe` release.

---

## Detailed Reference

| Topic | File |
|-------|------|
| Hardware & HAL | [docs/claude/hal.md](claude/hal.md) |
| Game modes | [docs/claude/modes.md](claude/modes.md) |
| LCD & UI | [docs/claude/display.md](claude/display.md) |
| Web & networking | [docs/claude/web.md](claude/web.md) |
| Build & deploy | [docs/claude/build.md](claude/build.md) |
| Mock mode | [docs/claude/mock.md](claude/mock.md) |
