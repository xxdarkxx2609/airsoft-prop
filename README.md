# Airsoft Prop

A Raspberry Pi Zero WH-based game prop for Airsoft and Milsim events. Features multiple game modes, a 20x4 LCD display, USB numpad input, and audio feedback.

---

## Disclaimer

This project is a **non-functional prop** for airsoft and milsim games. It contains
no explosives, pyrotechnics, or any dangerous materials. It is a Raspberry Pi running
software that displays a countdown timer on an LCD screen and plays sounds through a
speaker.

- **This is NOT a weapon or explosive device.**
- Do NOT add pyrotechnics, smoke generators, or any hazardous materials.
- Intended exclusively for private airsoft/milsim events on designated playing fields.
- **Do not use in public spaces.** In many jurisdictions (including Germany), carrying
  or displaying realistic-looking imitation explosive devices in public is illegal and
  may result in criminal prosecution.
- Users are solely responsible for compliance with all applicable local, state, and
  national laws and regulations.
- The authors accept no liability for misuse of this project.

### Haftungsausschluss (DE)

Dieses Projekt ist ein **funktionsloses Requisit** (Prop) für Airsoft- und
Milsim-Spiele. Es enthält keine Sprengstoffe, Pyrotechnik oder gefährliche
Materialien. Es handelt sich um einen Raspberry Pi mit Software, die einen
Countdown-Timer auf einem LCD-Display anzeigt und Töne über einen Lautsprecher
abspielt.

- Dies ist **keine Waffe und kein Sprengkörper**.
- Fügen Sie **keine** Pyrotechnik, Raucherzeuger oder gefährliche Materialien hinzu.
- Ausschließlich für private Airsoft-/Milsim-Veranstaltungen auf dafür vorgesehenen
  Spielfeldern bestimmt.
- **Nicht im öffentlichen Raum verwenden.** Das Mitführen oder Zeigen von
  täuschend echt aussehenden Sprengkörper-Attrappen ist in Deutschland nach
  §§ 145d, 126 StGB strafbar und kann zu polizeilichen Maßnahmen führen.
- Nutzer sind allein für die Einhaltung aller geltenden Gesetze verantwortlich.
- Die Autoren übernehmen keine Haftung für Missbrauch dieses Projekts.

---

## Features

- **5 Game Modes**: Random Code, Set Code, Random Code+, Set Code+, USB Key Cracker (+ Cut the Wire in draft)
- **20x4 LCD Display** with custom characters (WiFi, battery, cursor, lock icons)
- **USB Numpad** for intuitive input
- **Audio + LED feedback**: Beeps with synchronized LED blink, planted/defused/explosion/wrong-digit sounds + looping siren on detonation
- **Plugin system**: Add new game modes by dropping a single Python file
- **Desktop testing**: Full mock HAL with in-place terminal display and real audio via pygame-ce
- **Battery monitoring**: PiSugar 3 UPS HAT integration with charge level, runtime estimation, voltage, current draw, and external power detection — on LCD status screen, menu footer icon, and dedicated web page
- **Tournament Mode**: Lock the device to a single game mode configured by the organizer — players can only start the pre-configured game, no access to menus or settings. Exit via web interface, USB stick with `TOURNAMENT.KEY`, or secret PIN. Persistent across reboots.
- **USB Key Security**: Cryptographic token validation for USB keys — organizers generate keys via the web interface, which writes a UUID4 token to the USB stick and stores its SHA-256 hash. The device only accepts USB sticks it has authorized, preventing players from creating their own keys.
- **Captive Portal**: Automatic WiFi AP fallback — when no known network is available, the Pi creates its own access point and phones are redirected to the web interface via captive portal detection
- **Web interface**: Mobile-first Flask UI on port 8080 for WiFi config, game settings, tournament mode, battery status, system info, and updates — with full mock support for desktop testing
- **Debug logging**: Per-session log files with automatic rotation, retention cleanup, uncaught exception capture, and remote log viewer via web interface
- **Auto-updater**: Update from git directly from the device menu or web interface, with tag-based version display
- **Standalone Windows build**: Download a pre-built `.exe` from GitHub Releases — no Python installation required

## Hardware (BOM)

| Component | Description | Approx. Price |
|-----------|-------------|---------------|
| Raspberry Pi Zero WH | Main controller (with headers) | ~€15 |
| 20x4 LCD HD44780 + I2C Backpack | Display (PCF8574, address 0x27) | ~€6 |
| USB Numpad | User input device | ~€8 |
| PAM8403 Amplifier | Audio amplifier module | ~€2 |
| Small Speaker (8Ω, 2W) | Audio output | ~€3 |
| 3x Toggle Switches or Banana Plugs | "Wires" for Cut the Wire mode | ~€5 |
| 3x 10kΩ Resistors | Pull-down resistors for wire GPIOs | ~€1 |
| LED + 330Ω Resistor | Beep indicator LED (optional) | ~€1 |
| Micro-USB OTG Adapter | Connect USB numpad to Pi Zero | ~€3 |
| Micro-SD Card (16GB+) | OS storage | ~€8 |
| PiSugar 3 UPS HAT | Battery (1200mAh, USB-C charging, ~2-3h runtime) | ~€35-40 |
| Ammo Box or Pelican Case | Enclosure | ~€10-20 |
| **Total** | | **~€85-110** |

## Wiring Diagram

```
Raspberry Pi Zero WH GPIO (BCM numbering)
==========================================

LCD Display (I2C):
  Pi Pin 3  (GPIO2/SDA)  ──→  LCD SDA
  Pi Pin 5  (GPIO3/SCL)  ──→  LCD SCL
  Pi Pin 2  (5V)         ──→  LCD VCC
  Pi Pin 6  (GND)        ──→  LCD GND

Audio Output (PWM):
  Pi Pin 12 (GPIO18)     ──→  PAM8403 Input
  PAM8403 Output         ──→  Speaker (8Ω)
  Pi Pin 6  (GND)        ──→  PAM8403 GND
  Pi Pin 2  (5V)         ──→  PAM8403 VCC

Wire 1 — Defuse (Red):
  Pi Pin 11 (GPIO17)     ──→  Switch ──→ 3.3V (Pin 1)
                         └──→ 10kΩ  ──→ GND (Pin 9)

Wire 2 — Explode (Blue):
  Pi Pin 13 (GPIO27)     ──→  Switch ──→ 3.3V (Pin 1)
                         └──→ 10kΩ  ──→ GND (Pin 9)

Wire 3 — Halve Timer (Green):
  Pi Pin 15 (GPIO22)     ──→  Switch ──→ 3.3V (Pin 1)
                         └──→ 10kΩ  ──→ GND (Pin 14)

Beep Indicator LED:
  Pi Pin 18 (GPIO24)     ──→  Resistor (330Ω) ──→ LED ──→ GND

Wire Logic: Cable inserted = HIGH (intact), Cable pulled = LOW (cut)
```

## Battery (PiSugar 3)

The prop uses a **PiSugar 3** UPS HAT for portable power. It mounts underneath the Pi Zero via pogo pins (no soldering, GPIO header stays free).

| Spec | Value |
|------|-------|
| Battery | 1200 mAh LiPo (3.7V) |
| Output | 5V / 3A |
| Charging | USB-C (charges while running) |
| Runtime | ~2-3 hours under load |
| Features | RTC, watchdog, anti-accidental-touch switch, soft shutdown |

**Setup on Raspberry Pi:**

```bash
# Install the PiSugar power manager daemon
curl http://cdn.pisugar.com/release/pisugar-power-manager.sh | sudo bash

# Enable PiSugar in the config
# Edit config/hardware.yaml and set:
#   hal.battery: "pisugar"
```

The battery HAL communicates with the `pisugar-power-manager` daemon via TCP socket (port 8423). Battery data is displayed on:

- **LCD**: Status screen (press **8** in menu) — shows level with bar, voltage, and estimated runtime
- **LCD menu footer**: Battery icon (full/low) next to the WiFi icon
- **Web interface**: Dedicated `/battery` page with level bar, runtime, voltage, current, charging status, and external power status

**Without PiSugar:** Set `hal.battery: "none"` in `config/hardware.yaml`. All battery UI elements gracefully hide.

**Extended runtime:** For longer Milsim games (6+ hours), connect an external USB-C power bank to the PiSugar. It handles seamless power switching automatically.

## Installation

### On Raspberry Pi (One-Click)

On a freshly installed Raspberry Pi OS Lite with internet access, run this single command:

```bash
curl -fsSL https://raw.githubusercontent.com/xxdarkxx2609/RPi-Airsoft-Prop/main/install.sh | sudo bash
```

Or with `wget` if you prefer:

```bash
wget -qO- https://raw.githubusercontent.com/xxdarkxx2609/RPi-Airsoft-Prop/main/install.sh | sudo bash
```

Both `curl` and `wget` are pre-installed on Raspberry Pi OS Lite. The script will clone the repository automatically and run the full installation.

If you prefer to inspect the script first before running it:

```bash
# Clone the repository manually
git clone https://github.com/xxdarkxx2609/airsoft-prop.git
cd RPi-Airsoft-Prop

# Review install.sh, then run it
sudo bash install.sh
```

The installer will:
1. Install system packages (Python, I2C tools, SDL2, hostapd, dnsmasq, etc.)
2. Enable I2C and PWM audio in `/boot/firmware/config.txt`
3. Create a Python virtual environment and install dependencies (including Pi-specific packages from `requirements-pi.txt`)
4. Mask hostapd/dnsmasq system services (the app manages them directly)
5. Add the `pi` user to required groups (i2c, gpio, audio, input)
6. Configure passwordless `sudo` for WiFi management (`nmcli` commands)
7. Set up a systemd service for auto-start on boot
8. Reboot required to apply hardware changes

### Standalone Windows Build (Easiest)

Download the latest `AirsoftProp-vX.X.X-windows.zip` from [GitHub Releases](https://github.com/xxdarkxx2609/RPi-Airsoft-Prop/releases), extract it, and double-click `AirsoftProp.exe`. No Python installation required.

- Runs in mock mode automatically (terminal display, keyboard input, real audio)
- Settings can be adjusted via the web interface or in `config/default.yaml` next to the exe
- Recommended: use **Windows Terminal** or **PowerShell** for correct ANSI display
- Note: Antivirus software may flag PyInstaller executables as false positives — the source code is publicly available

### Desktop Testing (From Source)

```bash
# Clone the repository
git clone https://github.com/xxdarkxx2609/airsoft-prop.git
cd RPi-Airsoft-Prop

# Create virtual environment
python3 -m venv venv
source venv/bin/activate    # Linux/macOS
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run with mock HAL
python -m src.main --mock
```

**Mock mode features:**
- **Display**: Renders a 20x4 ASCII frame in the terminal, updated in-place using ANSI escape codes (no scrolling)
- **Audio**: Plays real WAV sounds via pygame-ce if sound files are present in `assets/sounds/` — silent fallback if missing
- **Input**: Reads keyboard input (digits, Enter, Backspace, arrow keys, +/-). Press `.` to toggle simulated USB key insertion
- **USB detector**: `MockUsbDetector` simulates USB stick insertion/removal via `.` key press. In mock mode the `/usb-keys` web page generates tokens and writes them to `config/usb_keys.yaml` without touching the filesystem (no real USB stick needed for testing)
- **LED**: `MockLed` logs blink events at DEBUG level — no hardware required
- **Battery**: `MockBattery` simulates a discharging battery (starts at 85%, slowly drains) — visible on status screen, menu footer, and web interface
- **Web interface**: Starts automatically on `http://localhost:8080` with simulated WiFi networks, battery data, and mock data
- **Logging**: All log output goes to `logs/prop.log` instead of the terminal to keep the display clean. Previous session logs are archived as `prop.YYYY-MM-DD_HH-MM-SS.log`

> **Note:** Requires Python 3.11+. Uses `pygame-ce` (community edition) instead of `pygame` for Python 3.13 compatibility.

## Usage

### Controls (USB Numpad)

```
8 = ▲ (Up)          Navigate up / Scroll
2 = ▼ (Down)        Navigate down / Scroll
4 = ◄ (Left)        Decrease value
6 = ► (Right)       Increase value
Enter               Confirm / Next page
Backspace           Back / Cancel / Delete digit
0-9                 Digit input (for codes)
+                   Quick +5 min (timer) / +10 (values)
-                   Quick -5 min (timer) / -10 (values)
```

### Menu Shortcuts

- "*" — Status screen (network, system, battery info)
- "/" — Update screen (check & install updates)

### Game Flow

```
Normal:     BOOT → MAIN MENU → SETUP → PLANTING → ARMED → DEFUSED / DETONATED → MAIN MENU
Tournament: BOOT → TOURNAMENT → PLANTING → ARMED → DEFUSED / DETONATED → TOURNAMENT
```

In **Tournament Mode**, the device boots directly into a locked screen showing only the configured game mode and a "Start Game" option. After each round, it returns to the tournament screen — not the main menu.

The **planting phase** requires active effort to arm the device (inspired by Counter-Strike):
- **Code modes** (Random Code, Set Code, and their Plus variants): Player must enter an activation code
- **Timed modes** (USB Key Cracker): Player must hold Enter for a set duration — releasing cancels

### LCD Screen Previews

**Boot Screen:**
```
+--------------------+
|   AIRSOFT  PROP    |
|   PROP v1.0.0      |
|                    |
|    Booting...      |
+--------------------+
```

**Main Menu:**
```
+--------------------+
|▸ Random Code       |
|  Set Code          |
|  USB Key Cracker   |
|* Status / Upd  ▣⊕ |
+--------------------+
```
*(▣ = battery icon, ⊕ = WiFi icon — battery icon only shown when UPS HAT is present)*

**Setup (Random Code):**
```
+--------------------+
|   Random Code      |
|▸ Timer:    05:00   |
|  Digits:   6       |
|<- Back   Ent Start |
+--------------------+
```

**Tournament Mode:**
```
+--------------------+
|##Tournament-Mode##|
| Game: Random Code  |
| > Start Game       |
|##Tournament-Mode##|
+--------------------+
```
*Players can only press Enter to start the configured game. 5× Backspace triggers a PIN prompt for organizer exit.*

**Planting (Code Entry):**
```
+--------------------+
| PLANTING PROP...   |
|Enter code to arm:  |
|     847291         |
|     847___         |
+--------------------+
```

**Planting (Hold Enter):**
```
+--------------------+
| PLANTING PROP...   |
|                    |
|[====>             ]|
|  Hold ENTER   7s   |
+--------------------+
```

**Armed (Random Code):**
```
+--------------------+
|** PROP ARMED **    |
|     04:37          |
|     385291         |
|     ______         |
+--------------------+
```

**Armed (Set Code):**
```
+--------------------+
|** PROP ARMED **    |
|     02:15          |
|   Enter Code:      |
|   > 42__           |
+--------------------+
```

**Armed (Random Code+ — wrong digit):**
```
+--------------------+
|** PROP ARMED **    |
|     04:27          |
|     385291         |
|    WRONG! -10s     |
+--------------------+
```

**Armed (Set Code+ — progress):**
```
+--------------------+
|** PROP ARMED **    |
|     02:05          |
|   Enter Code:      |
|     > ***___       |
+--------------------+
```

**Armed (USB Key Cracker — waiting):**
```
+--------------------+
|** PROP ARMED **    |
|     03:42          |
|                    |
| Insert USB Key...  |
+--------------------+
```

**Armed (USB Key Cracker — cracking):**
```
+--------------------+
|** PROP ARMED **    |
| Cracking...   12s  |
| [####........] 35% |
|  7 3 * * * * * *   |
+--------------------+
```

**Last 10 Seconds:**
```
+--------------------+
|!! 00:07 !! ARMED !!|
|                    |
|     385291         |
|     385___         |
+--------------------+
```

**Defused:**
```
+--------------------+
|                    |
|   PROP DEFUSED!    |
|  Time left: 02:43  |
|   Ent -> Menu      |
+--------------------+
```

**Detonated:**
```
+--------------------+
|********************|
|  PROP EXPLODED!    |
|    GAME OVER!      |
|********************|
+--------------------+
```
The siren sound loops continuously after detonation until the player presses Enter to return to the menu.

## Game Modes

### 1. Random Code

A random numeric code is displayed. The player must enter the exact code to defuse.

- **Setup**: Timer (00:30 – 99:59), Digits (4–20)
- **Planting**: Player must type the generated code to arm the device
- **Gameplay**: Code shown on LCD, type matching digits
- **Defuse**: Enter the correct code before time runs out

### 2. Set Code

The game organizer sets a secret code during setup. Players must discover the code through gameplay.

- **Setup**: Timer (00:30 – 99:59), Code (1–10 digits, entered by organizer)
- **Planting**: Player must type a random 10-digit activation code to arm
- **Gameplay**: Code is NOT shown on LCD
- **Defuse**: Enter the correct secret code

### 3. USB Key Cracker

The device can only be defused by inserting a USB stick containing a `DEFUSE.KEY` file.

- **Setup**: Timer (00:30 – 99:59), Digits (4–12, determines cracking duration)
- **Planting**: Hold Enter for 10 seconds to arm the device (releasing cancels)
- **Gameplay**: Insert USB stick with `DEFUSE.KEY` to start cracking animation
- **Defuse**: All digits cracked after `digits × 2.5s` (e.g. 8 digits = 20s)
- **Animation**: Digits cycle randomly and lock into correct values one by one
- **USB removal**: Pulling the USB stick during cracking cancels progress

### 4. Random Code+

A harder variant of Random Code. Each digit is checked immediately as it's entered.

- **Setup**: Timer (00:30 – 99:59), Digits (4–20)
- **Planting**: Same as Random Code (enter the generated code)
- **Gameplay**: Code shown on LCD, each digit is verified instantly
  - **Correct digit**: stays in place, next position
  - **Wrong digit**: rejected, time penalty deducted (default 10s), error sound + visual flash
- **Defuse**: Enter all digits correctly before time runs out
- **No backspace**: Every digit counts — mistyping costs time

### 5. Set Code+

A harder variant of Set Code. Each digit is checked immediately, but the code remains hidden.

- **Setup**: Timer (00:30 – 99:59), Code (1–10 digits, entered by organizer)
- **Planting**: Same as Set Code (enter a random 10-digit activation code)
- **Gameplay**: Code is NOT shown; confirmed digits appear as `*`
  - **Correct digit**: shown as `*`, next position
  - **Wrong digit**: rejected, time penalty deducted, error sound + visual flash
- **Defuse**: Enter all digits correctly before time runs out

> **Penalty seconds** can be configured via the web interface under Settings → Plus Modes (default: 10s per wrong digit).

### Cut the Wire (Draft)

> **Note:** This mode is currently in draft status (`src/modes/_drafts/`) and not available in the menu. It will be redesigned in a future update.

Three physical wires (colored cables) have randomly assigned roles (Defuse, Explode, Halve Timer).

## Tournament Mode

Tournament Mode locks the device to a single game mode with pre-configured settings. Ideal for organized Airsoft/Milsim events where players should not be able to change game parameters or switch modes.

### Setup (via Web Interface)

1. Open `http://<pi-ip>:8080/tournament` on your phone or laptop
2. Select a game mode from the dropdown
3. Adjust mode-specific settings (timer, digits, etc.)
4. Set a 4-digit emergency PIN (default: `0000`)
5. Enable Tournament Mode and click **Save Settings**

The device immediately switches to the Tournament Screen. On next reboot, it will boot directly into Tournament Mode — players cannot exit by restarting the device.

### What Players See

The LCD shows only:
- The configured game mode name
- A "Start Game" option (Enter key)
- No access to menu, settings, status, or update screens

After each game (defused or detonated), the device returns to the Tournament Screen for the next round.

### Exit Mechanisms (Organizer Only)

| Method | How |
|--------|-----|
| **Web Interface** | Navigate to `/tournament` and disable Tournament Mode |
| **USB Stick** | Insert a USB stick containing a `TOURNAMENT.KEY` file (separate from the `DEFUSE.KEY` used in-game). If USB key security is enabled, the key must have been authorized via the web interface. |
| **PIN Entry** | Press **Backspace 5 times rapidly** (within 3 seconds) on the Tournament Screen → enter the 4-digit PIN |

All three methods show a "Leaving Tournament Mode" transition screen and return to the normal main menu.

> **Tip:** The `TOURNAMENT.KEY` and `DEFUSE.KEY` files are completely separate. You can use different USB sticks, or even put both files on the same stick — they won't interfere with each other. Use the `/usb-keys` web page to prepare authorized USB sticks for both key types.

## Adding New Game Modes

The system uses auto-discovery. To add a new mode:

1. Create a new file in `src/modes/` (e.g. `my_mode.py`)
2. Inherit from `BaseMode` and implement all abstract methods
3. Set `name`, `description`, and `menu_key` class attributes
4. The mode will appear automatically in the menu
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
        # Initialize your mode state
        pass

    def on_input(self, key: str, context: GameContext) -> ModeResult:
        # Handle player input
        return ModeResult.CONTINUE

    def on_tick(self, remaining_seconds: int, context: GameContext) -> ModeResult:
        # Called every second
        return ModeResult.CONTINUE

    def render(self, display, remaining_seconds: int, context: GameContext) -> None:
        # Render your mode on the LCD
        pass

    def render_last_10s(self, display, remaining_seconds: int, context: GameContext) -> None:
        # Render during last 10 seconds
        pass
```

## Configuration

Configuration files are in `config/`:

- **default.yaml** — Shipped defaults (timer, audio volume, beep intervals, tournament mode, logging). Tracked by git — do not edit manually, use the web interface instead.
- **user.yaml** — User overrides (auto-created when settings are changed via web interface). Only contains values that differ from defaults. Gitignored — survives `git pull` updates.
- **usb_keys.yaml** — USB key registry (SHA-256 hashes of authorized keys). Gitignored. Created automatically when the first key is generated via the web interface. **Never deleted by "Reset to Defaults"** — registered keys always survive a settings reset.
- **hardware.yaml** — HAL selection, I2C address, GPIO pins
- **network.yaml** — WiFi hotspot, access point, and web interface settings

Settings changed via the web interface are stored in `user.yaml`, which always takes priority over `default.yaml`. Use the "Reset to Defaults" button on the Settings page to clear all customizations. Volume, display backlight, and log level changes take effect immediately without a restart.

## Web Interface

The prop runs a mobile-first web interface on port 8080 (configurable in `config/network.yaml`). It starts automatically alongside the main game loop in a background thread.

**Pages:**

| Page | URL | Description |
|------|-----|-------------|
| WiFi | `/wifi` | Scan for networks, connect, manage saved networks |
| Tournament | `/tournament` | Enable/disable Tournament Mode, select game mode, configure settings, set exit PIN |
| USB Keys | `/usb-keys` | Manage authorized USB keys — generate cryptographic tokens, write them to USB sticks, view registered keys, revoke keys |
| Settings | `/config` | Timer defaults, digits, Plus mode penalty seconds, volume, backlight, log level, max log files, reset to defaults |
| System | `/system` | View version, CPU temp, RAM, uptime, platform info |
| Battery | `/battery` | Battery level with visual bar, estimated runtime, voltage, current, charging status, external power status (auto-refreshes every 10s) |
| Logs | `/logs` | Browse and view log files with filtering and syntax highlighting |
| Update | `/update` | Check for git updates and install them |

**On Raspberry Pi:**
- Accessible at `http://<pi-ip>:8080` from any device on the same network
- **Captive Portal**: When no known WiFi is available, the Pi creates an AP named `airsoft-prop` (configurable in `config/network.yaml`). Connecting to it automatically opens the web interface via captive portal detection (Android, iOS, Windows). A background monitor re-enables the AP if WiFi drops at runtime.
- WiFi management uses NetworkManager (`nmcli`) under the hood. Network-modifying commands (scan, connect, disconnect, forget) run via `sudo` — the installer creates `/etc/sudoers.d/airsoft-prop-wifi` for passwordless access.
- Settings are saved to `config/user.yaml` (only values that differ from defaults)

**In Mock Mode (Desktop):**
- Accessible at `http://localhost:8080`
- WiFi page shows 5 simulated networks (connect/disconnect works)
- System page shows your desktop's platform info
- Battery page shows simulated battery data (discharging from 85%)
- Update page simulates an available update
- Settings can be changed and are saved to `config/user.yaml`

**Disabling the web interface:**
Set `web.enabled: false` in `config/network.yaml`.

**Accessing the web interface via smartphone hotspot:**

When the Pi is connected to your smartphone's hotspot (Variant 1 in `config/network.yaml`), you can access the web interface directly from the same smartphone:

1. **Configure the hotspot** on your smartphone with the SSID and password from `config/network.yaml` (default: SSID `AirsoftProp`, password `defuse1337`)
2. **Start the hotspot** — the Pi will connect automatically on boot
3. **Find the Pi's IP address** — press **8** on the numpad to open the status screen (page 1 shows the WiFi name and IP address)
4. **Open a browser** on your smartphone and navigate to `http://<pi-ip>:8080` (e.g. `http://192.168.43.2:8080`)

> **Tip:** Typical hotspot subnets are `192.168.43.x` (Android) or `172.20.10.x` (iPhone). The IP can change when the hotspot is restarted — always check the status screen for the current address. Use `http`, not `https`.

**API endpoints** (JSON):

```
GET  /api/wifi/status       — Current WiFi connection status
GET  /api/wifi/scan         — Scan for available networks
POST /api/wifi/connect      — Connect to a network {ssid, password}
POST /api/wifi/disconnect   — Disconnect from current network
GET  /api/wifi/saved        — List saved/known networks
POST /api/wifi/forget       — Remove a saved network {ssid}
GET  /api/wifi/ap-status    — Get access point status (active, ssid, password, ip)
GET  /api/tournament        — Get tournament config + available modes with setup options
POST /api/tournament        — Save tournament config {enabled, mode, pin, settings}
GET  /api/config            — Get current configuration (includes customized keys)
POST /api/config            — Update config {"dotted.key": value} (saves to user.yaml)
POST /api/config/reset      — Reset all settings to defaults (deletes user.yaml)
GET  /api/system            — Get system information
GET  /api/battery           — Get battery status (level, voltage, current, charging, runtime)
GET  /api/logs              — List available log files
GET  /api/logs/<filename>   — View log file content (?lines=200)
GET  /api/update/check      — Check for available updates
POST /api/update/install    — Install available updates
GET  /api/usb-keys          — List registered USB keys and current security mode (permissive/strict)
GET  /api/usb-keys/usb-sticks — Enumerate currently mounted USB sticks
POST /api/usb-keys/generate — Generate a token, write it to USB stick, store hash {key_type, mount_point, label}
DELETE /api/usb-keys/<type>/<id> — Revoke a registered key
```

## Versioning

The application version is automatically derived from **git tags** using `git describe --tags`. No manual version maintenance needed.

- **Boot screen** and **status screen** display the version (e.g. `PROP v1.0.0`)
- **Update screen** shows tag-based comparisons (e.g. `1.0.0 -> 1.0.1` instead of commit hashes)
- **Standalone builds** read a `VERSION` file generated during CI from the git tag

**To release a new version:**
```bash
git tag v1.0.1
git push origin v1.0.1
```

## Updating

### From the device menu
Press **9** in the main menu to check for and install updates.

### Manually
```bash
cd /home/pi/airsoft-prop
sudo bash update.sh
```

## Logging

The application writes detailed log files to the `logs/` directory. A new log file is created on each program start, and old logs are automatically cleaned up.

**Configuration** (`config/default.yaml`):
```yaml
logging:
  level: INFO        # DEBUG / INFO / WARNING / ERROR
  log_dir: logs      # Directory for log files
  log_file: prop.log # Current session log file name
  max_files: 10      # Max archived log files to keep
```

- `prop.log` — always the current session
- `prop.2026-04-06_14-30-22.log` — archived previous sessions (timestamped)
- Set `level: DEBUG` for maximum detail when debugging hardware issues
- Log level can be changed from the web interface under Settings and takes effect immediately (no restart required)
- Max files changes take effect on next restart

**What gets logged:**
- All application events (120+ log points across all modules)
- Uncaught exceptions (main thread + all background threads)
- Python warnings
- Stray stderr output from third-party libraries
- Startup diagnostics (Python version, platform, active HAL classes, config snapshot)

**Remote log viewing:**
- Browse and view logs from your phone via `http://<pi-ip>:8080/logs`
- Filter by keyword (e.g. "ERROR", "HAL"), with color-coded log levels

**CLI flags:**
- `--debug` — Force DEBUG log level (overrides config)
- `--log-file PATH` — Override log file name
- `--no-log-file` — Disable file logging, output to stderr only

## Service Management

```bash
# Check status
sudo systemctl status airsoft-prop

# View logs (systemd journal — backup, primary logs are in logs/)
journalctl -u airsoft-prop -f

# View application logs directly
tail -f logs/prop.log

# Restart
sudo systemctl restart airsoft-prop

# Stop
sudo systemctl stop airsoft-prop
```

## Project Structure

```
airsoft-prop/
├── CLAUDE.md                    # Architecture documentation
├── README.md                    # This file
├── .gitignore                   # Ignores logs/, __pycache__/, venv/, config/user.yaml, config/usb_keys.yaml
├── install.sh                   # One-click installer
├── update.sh                    # Git-based updater
├── requirements.txt             # Python dependencies
├── requirements-pi.txt          # Pi-specific dependencies (RPLCD, GPIO, evdev)
├── build/
│   ├── airsoft_prop.spec        # PyInstaller build spec
│   └── hook-runtime-mock.py     # Runtime hook (forces --mock)
├── .github/workflows/
│   └── build-release.yml        # Automated Windows release build
├── config/
│   ├── default.yaml             # Shipped defaults (game & logging settings)
│   ├── user.yaml                # User overrides (gitignored, auto-created)
│   ├── usb_keys.yaml            # USB key registry (gitignored, survives Reset to Defaults)
│   ├── hardware.yaml            # HAL & pin configuration
│   └── network.yaml             # WiFi settings
├── assets/sounds/               # WAV sound files
├── logs/                        # Log files (auto-created, gitignored)
│   ├── prop.log                 # Current session log
│   └── prop.*.log               # Archived session logs
├── src/
│   ├── main.py                  # Entry point
│   ├── app.py                   # State machine & main loop
│   ├── hal/                     # Hardware Abstraction Layer
│   │   ├── base.py              # Abstract base classes
│   │   ├── display_mock.py      # Terminal mock display
│   │   ├── audio_mock.py        # Mock audio (plays via pygame-ce)
│   │   ├── input_mock.py        # Keyboard mock input
│   │   ├── wires_mock.py        # Simulated wire GPIO
│   │   ├── usb_detector.py      # USB key detection (real, token validation)
│   │   ├── usb_detector_mock.py # USB key detection (mock, token validation support)
│   │   ├── battery_pisugar.py   # PiSugar 3 battery (TCP socket)
│   │   ├── battery_mock.py      # Simulated battery for desktop
│   │   ├── battery_none.py      # No-UPS stub
│   │   ├── led.py               # Beep indicator LED (GPIO via gpiozero)
│   │   └── led_mock.py          # Mock LED (logs blink events)
│   ├── modes/                   # Game modes (auto-discovered)
│   │   ├── base_mode.py         # BaseMode + PlantingConfig
│   │   ├── random_code.py       # Random Code mode
│   │   ├── random_code_plus.py  # Random Code+ mode (digit-by-digit with penalty)
│   │   ├── set_code.py          # Set Code mode
│   │   ├── set_code_plus.py     # Set Code+ mode (digit-by-digit with penalty)
│   │   ├── usb_key_cracker.py   # USB Key Cracker mode
│   │   └── _drafts/             # Shelved modes (not discovered)
│   │       └── cut_the_wire.py  # Cut the Wire (draft)
│   ├── ui/                      # Screen framework
│   │   ├── base_screen.py       # BaseScreen ABC
│   │   ├── screen_manager.py    # Screen transitions
│   │   ├── planting_screen.py   # Planting phase screen
│   │   ├── tournament_screen.py # Tournament mode lobby screen
│   │   ├── tournament_transition_screen.py  # Mode switch transition
│   │   ├── lcd_helpers.py       # Display utilities
│   │   └── *_screen.py          # Individual screens
│   ├── utils/                   # Utilities
│   │   ├── paths.py             # Frozen-aware project root resolution
│   │   ├── config.py            # YAML config with default/user override system
│   │   ├── version.py           # Git-tag-based version resolution
│   │   ├── logger.py            # Logging with rotation & exception capture
│   │   └── updater.py           # Git update system
│   └── web/                     # Web interface (Flask)
│       ├── server.py            # Flask app, routes, WebServer thread
│       ├── wifi_manager.py      # WiFi abstraction (real + mock)
│       ├── captive_portal.py    # AP management + captive portal (hostapd/dnsmasq)
│       ├── templates/           # Jinja2 HTML templates
│       │   ├── base.html        # Base layout with nav
│       │   ├── wifi.html        # WiFi configuration
│       │   ├── config.html      # Game & logging settings
│       │   ├── tournament.html  # Tournament mode config
│       │   ├── usb_keys.html    # USB key management
│       │   ├── battery.html     # Battery status
│       │   ├── logs.html        # Log file viewer
│       │   ├── system.html      # System info
│       │   └── update.html      # Software updates
│       └── static/              # CSS + JavaScript
├── systemd/
│   └── airsoft-prop.service     # Systemd unit file
└── tests/                       # Test files
    └── test_version.py          # Version resolution tests
```

## License

MIT License — see [LICENSE](LICENSE) for details.
