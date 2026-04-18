# Airsoft Prop

A Raspberry Pi Zero WH-based game prop for Airsoft and Milsim events. Features multiple game modes, a 20×4 LCD display, USB numpad input, and audio feedback.

---

## License

This project is **source-available** and licensed for **private, non-commercial use only**.

Any derived work must be published publicly and must clearly reference this
original repository.

Commercial use requires explicit written permission from the author.
See the LICENSE file for details.

## Disclaimer

This project is a **non-functional prop** for airsoft and milsim games. It contains no explosives, pyrotechnics, or any dangerous materials. It is a Raspberry Pi running software that displays a countdown timer on an LCD screen and plays sounds through a speaker.

- **This is NOT a weapon or explosive device.**
- Do NOT add pyrotechnics, smoke generators, or any hazardous materials.
- Intended exclusively for private airsoft/milsim events on designated playing fields.
- **Do not use in public spaces.** In many jurisdictions (including Germany), carrying or displaying realistic-looking imitation explosive devices in public is illegal and may result in criminal prosecution.
- Users are solely responsible for compliance with all applicable local, state, and national laws and regulations.
- The authors accept no liability for misuse of this project.

### Haftungsausschluss (DE)

Dieses Projekt ist ein **funktionsloses Requisit** (Prop) für Airsoft- und Milsim-Spiele. Es enthält keine Sprengstoffe, Pyrotechnik oder gefährliche Materialien. Es handelt sich um einen Raspberry Pi mit Software, die einen Countdown-Timer auf einem LCD-Display anzeigt und Töne über einen Lautsprecher abspielt.

- Dies ist **keine Waffe und kein Sprengkörper**.
- Fügen Sie **keine** Pyrotechnik, Raucherzeuger oder gefährliche Materialien hinzu.
- Ausschließlich für private Airsoft-/Milsim-Veranstaltungen auf dafür vorgesehenen Spielfeldern bestimmt.
- **Nicht im öffentlichen Raum verwenden.** Das Mitführen oder Zeigen von täuschend echt aussehenden Sprengkörper-Attrappen ist in Deutschland nach §§ 145d, 126 StGB strafbar und kann zu polizeilichen Maßnahmen führen.
- Nutzer sind allein für die Einhaltung aller geltenden Gesetze verantwortlich.
- Die Autoren übernehmen keine Haftung für Missbrauch dieses Projekts.

---

## Features

- **5 Game Modes**: Random Code, Set Code, Random Code+, Set Code+, USB Key Cracker
- **20×4 LCD Display** with custom icons (WiFi, battery, lock)
- **USB Numpad** for intuitive input
- **Audio + LED feedback**: beeps with synchronized LED, planted/defused/explosion sounds, looping siren on detonation
- **Tournament Mode**: lock the device to a single game mode — players can only start the configured game, no access to settings or menus
- **USB Key Security**: cryptographic token validation for defuse keys
- **Captive Portal**: when no known WiFi is available, the Pi creates its own access point and redirects phones to the web interface automatically
- **Web interface**: mobile-first UI on port 8080 for WiFi, settings, tournament mode, battery status, logs, and updates
- **Battery monitoring**: PiSugar S UPS HAT integration with runtime estimation, charge level, and charging status
- **Auto-updater**: update directly from the device menu or web interface

---

## Hardware (Bill of Materials)

| Component | Description | Approx. Price |
|-----------|-------------|---------------|
| Raspberry Pi Zero WH or Zero 2 W | Main controller (with pre-soldered headers) | ~€20-30 |
| 20×4 LCD HD44780 + I2C Backpack + Logic Level Converter TXS0108E| Display (PCF8574, address 0x27) | ~€13 |
| USB Numpad | Player input | ~€9 |
| USB Speaker | Portable audio output (small, 2–5W) | ~€13 |
| LED + 330Ω Resistor | Beep indicator LED (optional) | ~€1 |
| Micro-USB OTG Adapter | Connect USB numpad to Pi Zero | ~€4 |
| Micro-SD Card (16 GB+) | OS storage | ~€11 |
| PiSugar S UPS HAT (optional) | Battery (1200 mAh, USB-C charging, ~2–3 h runtime) | ~€35 |
| Ammo Box or Pelican Case | Enclosure | ~€18 |
| **Total** | | **~€89-131** |

---

## Wiring

All GPIO numbers use BCM numbering.

```
LCD Display (Software I2C via i2c-gpio overlay):
  Pi Pin 29 (GPIO5/SDA)  ──→  LCD SDA
  Pi Pin 31 (GPIO6/SCL)  ──→  LCD SCL
  Pi Pin 2  (5V)         ──→  LCD VCC
  Pi Pin 6  (GND)        ──→  LCD GND

USB Peripherals (via USB Hub + Micro-USB OTG):
  USB Numpad             ──→  USB Hub
  USB Speaker            ──→  USB Hub
  USB Hub                ──→  Pi Micro-USB OTG Port

Beep Indicator LED (optional):
  Pi Pin 18 (GPIO24)     ──→  Resistor (330Ω) ──→ LED ──→ GND
```

---

## Battery (PiSugar S)

The prop uses a **PiSugar S** UPS HAT for portable power. It attaches underneath the Pi Zero via pogo pins — no soldering required, and the GPIO header remains free for other connections.

The PiSugar S is chosen over the PiSugar 3 because it can send a Power-ON signal to the Pi via GPIO3 — allowing the device to boot without pressing a hardware button. The LCD display therefore uses **Software I2C on GPIO5/GPIO6** (Pin 29/31) to keep GPIO3 free.

| Spec | Value |
|------|-------|
| Battery | 1200 mAh LiPo (3.7 V) |
| Output | 5 V / 2.4 A |
| Charging | USB-C (charges while running) |
| Runtime | ~2–3 hours under load |
| Features | Power-ON signal (GPIO3), RTC, soft shutdown |

**Setup on Raspberry Pi:**

1. Add the Software I2C overlay for the LCD to `/boot/firmware/config.txt`:

```ini
# Software I2C for LCD display (GPIO5=SDA/Pin29, GPIO6=SCL/Pin31)
dtoverlay=i2c-gpio,bus=4,i2c_gpio_sda=5,i2c_gpio_scl=6
```

2. Install the PiSugar power manager daemon:

```bash
curl -O http://cdn.pisugar.com/release/pisugar-power-manager.sh
chmod +x ./pisugar-power-manager.sh
sudo ./pisugar-power-manager.sh
```

3. Edit `config/hardware.yaml` and set `hal.battery: "pisugar"`.

4. Reboot and verify:

```bash
ls /dev/i2c-*        # i2c-4 must appear
i2cdetect -y 4       # LCD at 0x27 must be visible
i2cdetect -y 1       # PiSugar S at 0x57 must be visible
```

Battery information is shown in three places:

- **LCD status screen** (press **8** in the menu) — charge level bar, voltage, estimated runtime
- **LCD menu footer** — battery icon (full/low) next to the WiFi icon
- **Web interface** `/battery` page — full detail with charging status and current draw

**Without PiSugar:** set `hal.battery: "none"` in `config/hardware.yaml`. All battery UI elements hide automatically.

**Extended runtime:** for longer Milsim games (6+ hours), connect a USB-C power bank to the PiSugar. It handles power switching automatically.

---

## Installation

### On Raspberry Pi (recommended)

Start with a freshly flashed **Raspberry Pi OS Lite** (Bookworm) with internet access. Then run the install script:

```bash
curl -fsSL https://raw.githubusercontent.com/xxdarkxx2609/airsoft-prop/main/install.sh -o install.sh
chmod +x install.sh
sudo ./install.sh
```

Or with `wget`:

```bash
wget -qO install.sh https://raw.githubusercontent.com/xxdarkxx2609/airsoft-prop/main/install.sh
chmod +x install.sh
sudo ./install.sh
```

If you want to review the script before running it:

```bash
git clone https://github.com/xxdarkxx2609/airsoft-prop.git
cd airsoft-prop
# Review install.sh, then:
sudo bash install.sh
```

The installer will:

1. Install system packages (Python, I2C tools, SDL2, hostapd, dnsmasq, etc.)
2. Enable I2C and PWM audio in `/boot/firmware/config.txt`
3. Create a Python virtual environment and install all dependencies
4. Configure the system for WiFi management and captive portal
5. Set up a systemd service so the prop starts automatically on boot
6. **Reboot required** to apply hardware changes

### Standalone Windows Build (for testing without hardware)

Download the latest `AirsoftProp-vX.X.X-windows.zip` from [GitHub Releases](https://github.com/xxdarkxx2609/RPi-Airsoft-Prop/releases), extract it, and double-click `AirsoftProp.exe`. No Python installation required.

The Windows build runs in mock mode — the game is fully playable in a terminal window with keyboard input and real audio. Useful for testing game settings or demonstrating modes before an event.

- Use **Windows Terminal** or **PowerShell** for correct display
- Antivirus software may flag PyInstaller executables as false positives — the source code is publicly available for inspection

---

## First-Time Setup

After installation, connect to the prop's WiFi or use your phone as a hotspot.

### Connecting via smartphone hotspot

The easiest way to reach the web interface on the field:

1. Create a hotspot on your phone with the SSID and password configured in `config/network.yaml` (defaults: SSID `AirsoftProp`, password `defuse1337`)
2. Start the hotspot — the Pi connects automatically on boot
3. Press **8** on the numpad to open the status screen — page 1 shows the current IP address
4. Open `http://<pi-ip>:8080` in your phone's browser (e.g. `http://192.168.43.2:8080`)

> **Tip:** Android hotspots typically use `192.168.43.x`, iPhone hotspots use `172.20.10.x`. The IP can change when the hotspot is restarted — always check the status screen. Use `http`, not `https`.

### Captive Portal (no phone hotspot available)

When the Pi cannot connect to any known WiFi network, it automatically creates its own access point named `airsoft-prop`. Connect your phone to it — most phones will redirect you to the web interface automatically (captive portal). If not, navigate to the IP shown on the LCD status screen.

---

## Usage

### Controls (USB Numpad)

| Key | Action |
|-----|--------|
| **8** | Navigate up |
| **2** | Navigate down |
| **4** | Decrease value |
| **6** | Increase value |
| **Enter** | Confirm / next page |
| **Backspace** | Back / cancel / delete digit |
| **0–9** | Digit input |
| **+** | Quick +5 min (timer) / +10 (other values) |
| **−** | Quick −5 min (timer) / −10 (other values) |
| **\*** | Open status screen (network, battery, system info) |
| **/** | Open update screen |

### Game Flow

```
Normal:     BOOT → MAIN MENU → SETUP → PLANTING → ARMED → DEFUSED / DETONATED → MAIN MENU
Tournament: BOOT → TOURNAMENT SCREEN → PLANTING → ARMED → DEFUSED / DETONATED → TOURNAMENT SCREEN
```

The **planting phase** requires the player to actively arm the device before the countdown starts (inspired by Counter-Strike bomb planting):

- **Code modes** (Random Code, Set Code, and their Plus variants): the player must enter a numeric code on the numpad
- **USB Key Cracker**: the player must hold Enter for a set duration — releasing it cancels

### LCD Screens

**Main Menu:**
```
+--------------------+
|▸ Random Code       |
|  Set Code          |
|  USB Key Cracker   |
|* Status / Upd  ▣⊕ |
+--------------------+
```
*(▣ = battery icon, ⊕ = WiFi icon — battery icon only shown when PiSugar HAT is present)*

**Setup:**
```
+--------------------+
|   Random Code      |
|▸ Timer:    05:00   |
|  Digits:   6       |
|<- Back   Ent Start |
+--------------------+
```

**Planting — code entry:**
```
+--------------------+
| PLANTING PROP...   |
|Enter code to arm:  |
|     847291         |
|     847___         |
+--------------------+
```

**Planting — hold Enter:**
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

**Armed — last 10 seconds:**
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
The siren loops until the player presses Enter to return to the menu.

---

## Game Modes

### Random Code

A random numeric code is displayed. The player must enter the exact code to defuse.

- **Setup**: Timer (00:30 – 99:59), Digits (4–20)
- **Planting**: enter the displayed code to arm
- **Gameplay**: code shown on LCD, type matching digits to defuse

### Set Code

The organizer sets a secret code during setup. Players must discover it.

- **Setup**: Timer (00:30 – 99:59), Code (1–10 digits, entered by organizer)
- **Planting**: enter a random 10-digit activation code to arm
- **Gameplay**: secret code is NOT shown on the LCD

### USB Key Cracker

Defuse by inserting a USB stick containing a `DEFUSE.KEY` file.

- **Setup**: Timer (00:30 – 99:59), Digits (4–12, determines cracking duration)
- **Planting**: hold Enter for 10 seconds to arm (releasing cancels)
- **Gameplay**: insert USB stick to start cracking animation; remove it to cancel progress
- **Defuse**: all digits cracked after `digits × 2.5 s` (e.g. 8 digits = 20 s)

### Random Code+

Harder variant of Random Code. Each digit is verified immediately as it is entered.

- **Correct digit**: locks into place, cursor moves to the next position
- **Wrong digit**: rejected with a time penalty (default −10 s) and error sound
- No backspace — every keystroke counts

### Set Code+

Harder variant of Set Code. Each digit is checked immediately, but the code remains hidden.

- **Correct digit**: shown as `*`, cursor advances
- **Wrong digit**: rejected with a time penalty and error sound
- The code is never revealed on the LCD

> **Penalty seconds** can be configured in the web interface under Settings → Plus Modes (default: 10 s per wrong digit).

### Cut the Wire *(draft)*

> This mode is currently in draft status and not available in the menu. It will be released in a future update.

Three physical wires have randomly assigned roles (Defuse / Explode / Halve Timer). Cut the right one.

---

## Tournament Mode

Tournament Mode locks the device to a single game mode with fixed settings. Players can only start the configured game — they have no access to menus, settings, or other modes. Ideal for organized events where game parameters must be controlled by the organizer.

The tournament setting persists across reboots. Players cannot exit tournament mode by restarting the device.

### Setup

1. Open `http://<pi-ip>:8080/tournament` in a browser
2. Select a game mode
3. Configure mode-specific settings (timer, digits, etc.)
4. Set a 4-digit emergency PIN (default: `0000`)
5. Enable Tournament Mode and click **Save Settings**

The device immediately switches to the Tournament Screen:

```
+--------------------+
|##Tournament-Mode##|
| Game: Random Code  |
| > Start Game       |
|##Tournament-Mode##|
+--------------------+
```

After each round, the device returns to this screen for the next round — not to the main menu.

### Exiting Tournament Mode (Organizer Only)

| Method | How |
|--------|-----|
| **Web interface** | Navigate to `/tournament` and disable Tournament Mode |
| **USB stick** | Insert a USB stick with a `TOURNAMENT.KEY` file (authorized via `/usb-keys`) |
| **PIN entry** | Press **Backspace 5 times** within 3 seconds → enter the 4-digit PIN |

---

## Web Interface

Accessible at `http://<pi-ip>:8080` from any device on the same network.

| Page | URL | Description |
|------|-----|-------------|
| WiFi | `/wifi` | Scan for networks, connect, manage saved networks |
| Tournament | `/tournament` | Enable/disable Tournament Mode, select game mode, configure settings, set exit PIN |
| USB Keys | `/usb-keys` | Generate and authorize USB keys for defusing and tournament exit |
| Settings | `/config` | Timer defaults, digits, penalty seconds, volume, backlight, log level |
| System | `/system` | Version, CPU temperature, RAM, uptime |
| Battery | `/battery` | Charge level, estimated runtime, voltage, current, charging status |
| Logs | `/logs` | Browse and view session log files |
| Update | `/update` | Check for and install updates |

Settings changed via the web interface are saved to `config/user.yaml` and take priority over the shipped defaults. Volume, backlight, and log level changes take effect immediately without a restart. Use **Reset to Defaults** on the Settings page to clear all customizations.

**Disabling the web interface:** set `web.enabled: false` in `config/network.yaml`.

---

## USB Key Security

Defuse keys (`DEFUSE.KEY`) and tournament exit keys (`TOURNAMENT.KEY`) use cryptographic token validation. The web interface at `/usb-keys` generates a UUID token, writes it to the USB stick, and stores its SHA-256 hash on the device. Only USB sticks that were authorized this way are accepted — players cannot create their own keys.

The `DEFUSE.KEY` and `TOURNAMENT.KEY` files are completely independent. You can use separate sticks or put both files on the same stick.

---

## Configuration Files

| File | Purpose |
|------|---------|
| `config/default.yaml` | Shipped defaults — do not edit manually; use the web interface instead |
| `config/user.yaml` | Your overrides — auto-created by the web interface, gitignored, survives `git pull` |
| `config/usb_keys.yaml` | Authorized USB key hashes — gitignored, never deleted by Reset to Defaults |
| `config/hardware.yaml` | HAL selection, I2C address, GPIO pin assignments |
| `config/network.yaml` | WiFi hotspot SSID/password, web interface port |

---

## Updating

### From the device menu

Press **/** in the main menu to open the update screen, then follow the on-screen prompt.

### Manually via SSH

```bash
cd /home/pi/airsoft-prop
sudo bash update.sh
```

---

## Service Management (SSH)

```bash
# Check status
sudo systemctl status airsoft-prop

# Restart
sudo systemctl restart airsoft-prop

# Stop
sudo systemctl stop airsoft-prop

# View live application log
tail -f /home/pi/airsoft-prop/logs/prop.log
```

---

## Troubleshooting

**No display output:** Check I2C wiring (GPIO5=SDA/Pin29, GPIO6=SCL/Pin31). Verify the `i2c-gpio` overlay is active in `/boot/firmware/config.txt` and that `/dev/i2c-4` exists after reboot. Check the I2C address with `i2cdetect -y 4` (default: `0x27`).

**No audio:** Check that the USB speaker is connected via the USB hub and recognized by the system. Test with `aplay -l` or `pactl list short sinks` on the Pi.

**Cannot connect to web interface:** Press **8** on the numpad to view the current IP address on the status screen. Make sure your phone and the Pi are on the same network.

**Device not starting automatically:** Check the service: `sudo systemctl status airsoft-prop`. View logs with `journalctl -u airsoft-prop -n 50`.

**Wrong digit penalty too harsh / too lenient:** Adjust penalty seconds in the web interface under Settings → Plus Modes.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## For Developers

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for architecture overview, code conventions, mock mode setup, and instructions for adding new game modes.
