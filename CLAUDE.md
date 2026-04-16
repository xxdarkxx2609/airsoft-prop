# CLAUDE.md — Airsoft Prop

## Projektuebersicht

Airsoft Prop — ein Raspberry Pi Zero WH-basiertes Spielgeraet fuer Airsoft/Milsim mit mehreren Spielmodi, 20x4 LCD-Display, USB-Numpad-Steuerung und Audioausgabe. Kein Sprengstoff, reines Spielgeraet.

## Technologie-Stack

- **OS**: Raspberry Pi OS Lite (Bookworm / Debian 12 LTS)
- **Python**: 3.11 auf Pi (System-Python), 3.13 auf Entwicklungs-Desktop — **keine 3.12+ Features verwenden**
- **Audio**: `pygame-ce` (Community Edition, kompatibel mit Python 3.11-3.13; **NICHT** das alte `pygame` — funktioniert nicht mit Python 3.13+)
- **Paketmanagement**: `venv` + `pip` mit `>=`-Versionen in `requirements.txt`
- **Konfiguration**: YAML (`config/default.yaml` + `custom/user.yaml` fuer User-Overrides, `config/hardware.yaml`)
- **Web-Interface**: Flask (Captive Portal & Konfiguration, Port 8080)
- **Display**: RPLCD via I2C (20x4 HD44780)
- **GPIO**: RPi.GPIO oder gpiozero
- **Autostart**: systemd Service (`systemd/airsoft-prop.service`)
- **Standalone-Build**: PyInstaller → Windows .exe, GitHub Actions Release

## Architektur

### Hardware Abstraction Layer (HAL)
Jede Hardware-Komponente hat eine abstrakte Basisklasse in `src/hal/base.py` mit konkreten Implementierungen und Mock-Varianten. Auswahl ueber `config/hardware.yaml`. Custom-HAL in `custom/hal/` per `custom:module.Class` Syntax.
→ **Details: [docs/claude/hal.md](docs/claude/hal.md)**

### Plugin-System fuer Spielmodi
Jeder Modus ist eine Datei in `src/modes/` (erbt von `BaseMode`). Auto-Discovery via `pkgutil`. Custom-Modi in `custom/modes/`.
→ **Details: [docs/claude/modes.md](docs/claude/modes.md)**

### State Machine
```
Normal:     BOOT → MAIN_MENU → SETUP → [PLANTING →] ARMED → DEFUSED|DETONATED → MAIN_MENU
Tournament: BOOT → TOURNAMENT → [PLANTING →] ARMED → DEFUSED|DETONATED → TOURNAMENT
Extras:     MAIN_MENU → STATUS_SCREEN (*) | UPDATE_SCREEN (/)
```
PLANTING-Phase nur wenn Modus kein `PlantingType.INSTANT` hat. State-Management in `src/app.py`.

### Screen-System
Jeder Screen erbt von `BaseScreen` (`src/ui/base_screen.py`): `render()`, `handle_input()`, `on_enter()`, `on_exit()`. Wechsel ueber `ScreenManager`.
→ **Details: [docs/claude/display.md](docs/claude/display.md)**

### Tournament Mode
Sperrt das Geraet auf einen konfigurierten Spielmodus. Config: `tournament.*` in YAML.

Exit-Mechanismen (fuer Organisator):
1. **Web-Interface** (`/tournament`) — Ein-/Ausschalten, Modus, PIN
2. **USB-Stick** mit `TOURNAMENT.KEY` — deaktiviert Tournament
3. **PIN-Eingabe** — 5x Backspace in 3s → PIN-Prompt → 4-stellige PIN

Cross-Thread Events via `App._event_queue` (`queue.Queue`): `tournament_activate`, `tournament_deactivate`, `audio_volume_changed`, `display_backlight_changed`, `logging_level_changed`.

Bei aktivem Spiel wird das Speichern der **Tournament-Settings** im WebUI blockiert (HTTP 409). Allgemeine Config-Aenderungen sind jederzeit moeglich.

### Logging-System
Zentrales Logging ueber `src/utils/logger.py`. Alle Module: `get_logger(__name__)`. Automatische Session-Rotation, Archiv-Bereinigung. Erfasst: Uncaught Exceptions (alle Threads), Python Warnings, stray stderr, Startup-Diagnostik. Log-Level zur Laufzeit aenderbar (Web-Interface Event). Main-Loop: innerer try/except, nach 10 aufeinanderfolgenden Fehlern → sauberer Shutdown.

## Code-Stil & Konventionen

- **Python 3.11 kompatibel**, keine 3.12+ Features
- **Type Hints** fuer alle Funktions-Signaturen (Parameter + Return-Type), Klassen-Attribute und Module-Level-Variablen. Nicht noetig fuer lokale Variablen wo der Typ offensichtlich ist.
- **Google-Style Docstrings** fuer alle oeffentlichen Klassen und Methoden. Einzeilig wenn selbsterklaerend, mehrzeilig mit Args/Returns bei komplexerer Signatur.
- **Logging statt print()**: `get_logger(__name__)` verwenden, kein `print()` im Code.
- **Fehlerbehandlung**: Hardware-Fehler loggen (WARNING/ERROR), None oder Fallback-Wert zurueckgeben, keine unbehandelten Exceptions nach oben durchlassen. HAL-Methoden duerfen nie den Main-Loop crashen. Bei wiederholtem Versagen: Zustand merken, nicht endlos retrien.
- **Konfiguration**: Benutzer-konfigurierbare Werte immer aus YAML laden (Timer, Digits, Volume, Pins, I2C-Adressen). Technische Konstanten (LCD-Breite=20, HOLD_TIMEOUT=0.6s, Beep-Intervalle) duerfen als benannte Konstanten im Code stehen.
- **Sprache**: Code, Kommentare, Docstrings, LCD-Texte, Web-UI: Englisch. Projekt-Dokumentation (CLAUDE.md, docs/claude/): Deutsch.
- **Web-Frontend**: Kein CSS-Framework (Bootstrap etc.), kein JS-Framework (React etc.). CSS Custom Properties, Flexbox und Grid sind erlaubt. Kein Frontend-Build-Step. Eine CSS-Datei (`style.css`), eine JS-Datei (`app.js`).

## Wichtige Fallstricke ("Gotchas")

Diese Regeln gelten bei **jeder** Aenderung:

1. **pygame-ce, NICHT pygame**: Das alte `pygame` funktioniert nicht mit Python 3.13+ (entferntes `distutils`). Immer `pygame-ce` verwenden.

2. **Neue Sounds an 2 Stellen registrieren**:
   - `config/default.yaml` → `audio.sounds` (Name → Dateipfad)
   - `src/hal/audio_mock.py` → `MockAudio.init()` → `self._sounds` Dict (hardcoded, liest NICHT aus Config)

3. **Neue Modi an 2 Stellen registrieren** (fuer Standalone-Build):
   - `_KNOWN_MODES` in `src/modes/__init__.py`
   - `hiddenimports` in `build/airsoft_prop.spec`

4. **device_name max 7 Zeichen**: Engste Stelle `** {name} ARMED **` auf 20-Spalten-LCD. Validierung in Web-Interface + Config-Laden.

5. **Config zweistufig**: `default.yaml` (Git-getrackt) + `custom/user.yaml` (nur Overrides, gitignored). Reset loescht nur `user.yaml`, nicht `custom/usb_keys.yaml`.

6. **Main-Loop Resilienz**: `src/app.py` hat inneren try/except — ein einzelner Fehler crasht nicht die App. Nach 10 aufeinanderfolgenden Fehlern → sauberer Shutdown.

## Detail-Dokumentation

Fuer bereichsspezifische Aenderungen die entsprechende Referenzdatei konsultieren:

| Bereich | Datei | Wann relevant |
|---------|-------|---------------|
| Hardware & HAL | [docs/claude/hal.md](docs/claude/hal.md) | HAL-Module, GPIO, Audio, PiSugar, USB-Detector |
| Spielmodi | [docs/claude/modes.md](docs/claude/modes.md) | Modi, Planting, Penalty-System, Plugin-Discovery |
| LCD & UI | [docs/claude/display.md](docs/claude/display.md) | Screen-Layouts, Numpad, device_name, Custom Chars |
| Web & Netzwerk | [docs/claude/web.md](docs/claude/web.md) | Flask, API, Config, Captive Portal, WiFi, USB-Keys |
| Build & Deploy | [docs/claude/build.md](docs/claude/build.md) | PyInstaller, CI/CD, Versionierung, Installer |
| Mock-Modus | [docs/claude/mock.md](docs/claude/mock.md) | Desktop-Entwicklung, alle Mock-Implementierungen |
