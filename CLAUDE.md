# CLAUDE.md — Airsoft Prop

## Projektübersicht

Airsoft Prop — ein Raspberry Pi Zero WH-basiertes Spielgerät für Airsoft/Milsim mit mehreren Spielmodi, 20x4 LCD-Display, USB-Numpad-Steuerung und Audioausgabe. Kein Sprengstoff, reines Spielgerät.

## Technologie-Stack

- **OS**: Raspberry Pi OS Lite (Bookworm / Debian 12 LTS)
- **Python**: 3.11 auf Pi (System-Python aus Bookworm), 3.13 auf Entwicklungs-Desktop
- **Paketmanagement**: `venv` + `pip` mit `>=`-Versionen in `requirements.txt`
- **Konfiguration**: YAML (`config/default.yaml` + `custom/user.yaml` für User-Overrides, `config/hardware.yaml`), inkl. Logging-Konfiguration
- **Autostart**: systemd Service (`systemd/airsoft-prop.service`)
- **Web-Interface**: Flask (für Captive Portal & Konfiguration)
- **Audio**: `pygame-ce` (Community Edition, kompatibel mit Python 3.11–3.13; NICHT das alte `pygame`)
- **Display**: RPLCD via I2C
- **GPIO**: RPi.GPIO oder gpiozero
- **Standalone-Build**: PyInstaller (`build/airsoft_prop.spec`) → Windows .exe, GitHub Actions Release-Workflow

## Architektur-Prinzipien

### Hardware Abstraction Layer (HAL)
Jede Hardware-Komponente wird durch eine abstrakte Basisklasse in `src/hal/base.py` definiert. Konkrete Implementierungen und Mock-Varianten für Desktop-Tests existieren als separate Module. Die aktive Implementierung wird über `config/hardware.yaml` ausgewählt. Nutzer können eigene HAL-Implementierungen in `custom/hal/` ablegen und per `custom:module.Class` Syntax in `hardware.yaml` referenzieren.

**HAL-Module:**
- `DisplayBase` → `display_lcd.py` (20x4 HD44780 I2C) | `display_mock.py` (Terminal mit ANSI in-place Update)
- `AudioBase` → `audio.py` (pygame.mixer) | `audio_mock.py` (spielt Sounds via pygame-ce, stummer Fallback)
- `InputBase` → `input_numpad.py` (USB Numpad) | `input_mock.py` (Tastatur)
- `WiresBase` → `wires.py` (GPIO) | `wires_mock.py` (simuliert)
- `UsbDetectorBase` → `usb_detector.py` (pollt `/media/` nach `DEFUSE.KEY`, validiert Inhalt gegen Allowlist) | `usb_detector_mock.py` (Toggle per `.`-Taste, unterstützt Token-Validierung)
- `BatteryBase` → `battery_pisugar.py` (PiSugar 3 via TCP Socket) | `battery_ups_lite.py` | `battery_mock.py` (simuliert) | `battery_none.py`
- `LedBase` → `led.py` (GPIO via gpiozero) | `led_mock.py` (loggt Aufrufe, kein Hardware)

**Wichtige DisplayBase-Methoden:**
- `write_line(row, text)` — Schreibt eine Zeile in den Buffer (kein sofortiges Rendering bei Mock)
- `flush()` — Rendert den Buffer auf das Display (no-op bei echtem LCD, ANSI-Update bei Mock)
- Der Main Loop ruft `flush()` einmal pro Frame nach `render()` auf
- Mock-Display nutzt Snapshot-Vergleich und rendert nur bei Änderungen

**AudioBase-Interface:**
- `play(sound_name)` — Spielt einen Sound einmal ab
- `play_loop(sound_name)` — Spielt einen Sound in Endlosschleife (z.B. Sirene bei Detonation)
- `stop()` — Stoppt alle laufenden Sounds (auch Loops)

**LedBase-Interface:**
- `blink_once()` — Blinkt kurz einmal auf (~120ms on, non-blocking via gpiozero-Thread). Wird synchron mit dem Beep-Sound aufgerufen.
- `set_enabled(on: bool)` — Hält die LED dauerhaft an oder aus (z.B. für zukünftige Status-Anzeigen).
- `shutdown()` — Schaltet LED aus und gibt GPIO-Pin frei.

**BatteryBase-Interface:**
- `get_battery_level()` → `Optional[int]` — Ladestand 0-100% oder None
- `get_voltage()` → `Optional[float]` — Spannung in Volt oder None
- `is_charging()` → `Optional[bool]` — Lädt gerade?
- `get_current()` → `Optional[float]` — Stromverbrauch in mA oder None
- `is_power_plugged()` → `Optional[bool]` — Externe Stromversorgung angeschlossen?
- `get_runtime_minutes()` → `Optional[int]` — Geschätzte Restlaufzeit in Minuten oder None

Alle Methoden geben `None` zurück wenn kein UPS-HAT vorhanden ist. UI-Code muss immer auf `None` prüfen.

**UsbDetectorBase-Interface:**
- `init()` — Initialisiert den Detektor; lädt Allowlists aus `custom/usb_keys.yaml`
- `is_key_present()` → `bool` — Prüft ob `DEFUSE.KEY` auf einem gemounteten Medium vorhanden und gültig ist
- `is_tournament_key_present()` → `bool` — Prüft ob `TOURNAMENT.KEY` vorhanden und gültig ist
- `reload_allowlists(defuse_hashes, tournament_hashes)` — Hot-Reload der In-Memory-Allowlists (aufgerufen vom Web-Server nach Key-Generierung/-Widerruf, kein Neustart nötig)

Validierungslogik: Wenn die Allowlist leer ist → **Permissive Mode** (jede Datei mit korrektem Namen wird akzeptiert, Rückwärtskompatibilität). Sobald mindestens ein Key registriert ist → **Strict Mode**: Dateiinhalt wird gelesen, gestrippt, SHA-256-gehasht und gegen die Allowlist geprüft. Allowlists sind als `frozenset[str]` im RAM (O(1) Lookup). Kein Disk-I/O während Gameplay wenn kein USB-Stick eingesteckt.

**PiSugar 3 Kommunikation:**
- Nicht über Raw I2C, sondern über den `pisugar-power-manager` Daemon (TCP Socket auf `127.0.0.1:8423`)
- Voraussetzung: `curl http://cdn.pisugar.com/release/pisugar-power-manager.sh | sudo bash`
- Protokoll: `"get <key>\n"` senden → `"<key>: <value>\n"` empfangen
- Werte werden alle 5s gecacht, Reconnect-Versuch alle 30s bei Verbindungsverlust
- Bei fehlendem Daemon → graceful Fallback auf `None` für alle Werte

### Plugin-System für Spielmodi
Jeder Spielmodus ist eine eigene Datei in `src/modes/` und erbt von `BaseMode` (`src/modes/base_mode.py`). Modi werden beim Start automatisch entdeckt (Auto-Discovery via `pkgutil.iter_modules`). Ein neuer Modus = eine neue Datei, keine weiteren Änderungen nötig. Nutzer können eigene Modi in `custom/modes/` ablegen — diese werden ebenfalls automatisch entdeckt.

**Frozen-Build-Fallback:** In PyInstaller-Builds kann `pkgutil` das Dateisystem nicht scannen. Dann greift eine explizite Modulliste `_KNOWN_MODES` in `src/modes/__init__.py`. Bei neuen Modi muss diese Liste sowie `hiddenimports` in `build/airsoft_prop.spec` aktualisiert werden.

**Plus-Modi Penalty-System:** Die "+" Varianten (Random Code+, Set Code+) nutzen `context.custom_data["penalty_seconds"]` (gesetzt von `setup_screen.py` aus Config) und signalisieren Fehler über `context.custom_data["penalty_triggered"]` an `armed_screen.py`, das den Sound abspielt. So bleiben Modi vom Audio-HAL entkoppelt.

**BaseMode-Interface:**
```python
class BaseMode(ABC):
    name: str
    description: str
    menu_key: str  # Sortierungsschlüssel (historisch, nicht mehr im Menü angezeigt)

    def get_planting_config(self) -> PlantingConfig: ...  # Planting-Mechanik (default: INSTANT)
    def get_setup_options(self) -> list[SetupOption]: ...
    def on_armed(self, context: GameContext) -> None: ...
    def on_input(self, key: str, context: GameContext) -> ModeResult: ...
    def on_tick(self, remaining_seconds: int, context: GameContext) -> ModeResult: ...
    def render(self, display: DisplayBase, remaining_seconds: int, context: GameContext) -> None: ...
    def render_last_10s(self, display: DisplayBase, remaining_seconds: int, context: GameContext) -> None: ...
```

**Planting-System:**
```python
class PlantingType(Enum):
    INSTANT = "instant"        # Sofort (kein Planting-Screen)
    CODE_ENTRY = "code_entry"  # Spieler muss Code eingeben
    TIMED = "timed"            # Spieler muss Enter halten

@dataclass
class PlantingConfig:
    planting_type: PlantingType = PlantingType.INSTANT
    duration: int = 0       # Sekunden für TIMED (Enter halten)
    code_length: int = 0    # Ziffern für CODE_ENTRY (0 = aus Modus-Code ableiten)
```

Modi definieren ihre Planting-Mechanik über `get_planting_config()`:
- **Random Code**: `CODE_ENTRY` mit code_length=0 (nutzt den generierten Spielcode)
- **Set Code**: `CODE_ENTRY` mit code_length=10 (separater 10-Ziffern-Aktivierungscode)
- **USB Key Cracker**: `TIMED` mit duration=10 (10s Enter halten)

`HOLD_TIMEOUT = 0.6s` — Toleranz für Key-Hold-Erkennung. Wenn >600ms kein Enter-Event kommt, gilt die Taste als losgelassen (OS Key-Repeat-Delay ist ~500ms).

### State Machine
Normaler Programmfluss: `BOOT → MAIN_MENU → SETUP → PLANTING → ARMED → DEFUSED|DETONATED → MAIN_MENU`
Tournament-Programmfluss: `BOOT → TOURNAMENT → PLANTING → ARMED → DEFUSED|DETONATED → TOURNAMENT`
Zusätzlich von MAIN_MENU: `STATUS_SCREEN` (Taste *), `UPDATE_SCREEN` (Taste /).
State-Management liegt in `src/app.py`.

Die PLANTING-Phase wird nur durchlaufen wenn der Modus kein `PlantingType.INSTANT` hat. Bei INSTANT springt Setup/Tournament direkt zu ARMED. Abbruch (Backspace oder Enter loslassen) führt zurück zu SETUP bzw. TOURNAMENT.

Live-Wechsel zwischen Normal/Tournament über Cross-Thread Events (`App._event_queue`). Transition-Screen zeigt 3s Nachricht.

### Screen-System
Jeder Screen erbt von `BaseScreen` (`src/ui/base_screen.py`) und implementiert:
- `render(display)` — Zeichnet den Screen auf das Display
- `handle_input(key)` — Verarbeitet Tasteneingaben
- `on_enter()` / `on_exit()` — Lifecycle-Hooks

Screen-Wechsel über `ScreenManager` (`src/ui/screen_manager.py`).

### Tournament Mode
Vollständige Turniersperre: Sperrt das Gerät auf einen vom Organisator konfigurierten Spielmodus. Spieler sehen nur den Tournament Screen und können ausschließlich das konfigurierte Spiel starten. Kein Zugriff auf Menü, Setup, Status oder Update.

**Config-Namespace:** `tournament.*` in `config/default.yaml` / `custom/user.yaml`:
```yaml
tournament:
  enabled: false
  mode: random_code        # Python-Modulname des Modus
  pin: '0000'              # 4-stellige Notfall-PIN
  settings: {}             # Modus-spezifische Einstellungen (timer, digits, etc.)
```

**Tournament Screen (`src/ui/tournament_screen.py`):**
```
##Tournament-Mode##
Game: Random Code
> Start Game
##Tournament-Mode##
```
- Enter → Planting → Armed → Result → zurück zum Tournament Screen (Endlosschleife)
- Kein Zugriff auf Status (8), Update (9) oder andere Modi
- Bei Boot mit `tournament.enabled: true` → direkt zum Tournament Screen (Menü wird übersprungen)
- Spieler kann durch Neustart den Modus nicht verlassen

**Exit-Mechanismen (für Organisator):**
1. **Web-Interface:** Eigene Tournament-Seite (`/tournament`) zum Ein-/Ausschalten, Modus- und PIN-Konfiguration
2. **USB-Stick:** Stick mit `TOURNAMENT.KEY` Datei einstecken → Tournament Mode wird deaktiviert (separate Datei von `DEFUSE.KEY`)
3. **PIN-Eingabe:** 5x Backspace innerhalb von 3 Sekunden → PIN-Prompt erscheint → korrekte 4-stellige PIN → Exit. Timeout nach 10s ohne Eingabe.

**Cross-Thread Events:** WebUI-Änderungen werden über `App._event_queue` (thread-safe `queue.Queue`) an den Main Loop kommuniziert. Events:
- `tournament_activate`, `tournament_deactivate` — Tournament Mode umschalten
- `audio_volume_changed` — Lautstärke sofort anwenden (kein Neustart nötig)
- `display_backlight_changed` — Display-Helligkeit sofort anwenden
- `logging_level_changed` — Log-Level sofort anwenden via `set_log_level()`

Bei aktivem Spiel wird das Speichern im WebUI blockiert (HTTP 409).

**Transition Screens (`src/ui/tournament_transition_screen.py`):**
- "Switching to Tournament Mode" (3s) beim Aktivieren via WebUI
- "Leaving Tournament Mode" (3s) beim Deaktivieren via WebUI/PIN/USB
- Beim Boot: kein Transition Screen, direkt zum Tournament Screen

**Config-Defaults für Setup-Optionen:**
Die Modi haben hardcoded Defaults (`default=300` für Timer etc.). `SetupScreen._apply_config_defaults()` überschreibt diese nach `get_setup_options()` mit Werten aus der Config (`game.default_timer`, `modes.random_code.default_digits` etc.). Im Tournament Mode werden stattdessen die `tournament.settings.*` Werte verwendet.

## Hardware-Spezifikationen

### GPIO-Pinout
```
LCD I2C:     SDA=GPIO2(Pin3), SCL=GPIO3(Pin5), VCC=5V(Pin2), GND=Pin6
Audio:       USB Lautsprecher (default) oder PWM GPIO18(Pin12) → PAM8403
Wire 1 (Defuse):  GPIO17(Pin11) + 10kΩ Pull-Down
Wire 2 (Explode): GPIO27(Pin13) + 10kΩ Pull-Down
Wire 3 (Halve):   GPIO22(Pin15) + 10kΩ Pull-Down
LED (Beep):  GPIO24(Pin18) → Vorwiderstand → LED → GND
Wire-Prinzip: Kabel steckt=HIGH(intakt), Kabel gezogen=LOW(durchtrennt)
```

### LCD: 20x4 HD44780 mit I2C (PCF8574)
- I2C-Adresse: 0x27 (oder 0x3F, konfigurierbar in hardware.yaml)
- Custom Characters (8 Slots): WiFi-Icons(⊕/⊘), Batterie(voll/niedrig), Cursor(▸), Rahmenelemente(═/╔/╚), Lock(🔒)

### UPS-HAT: PiSugar 3
- 1200 mAh LiPo, 5V/3A Ausgang, USB-C Laden, Pogo-Pin-Montage unter Pi Zero
- I2C-Adresse: 0x57 (IP5312 Chip), RTC auf 0x68
- Kommunikation über `pisugar-power-manager` Daemon (TCP Socket Port 8423)
- Laufzeit: ~2-3h unter Last (LCD + Audio + WiFi + Numpad)
- Im Mock-Modus: `MockBattery` simuliert sich entladende Batterie (startet bei 85%)
- **Bekannter Bug:** PiSugar 3 mit pisugar-server v2.3.2 funktioniert NICHT auf armv6 (Pi Zero WH). Upgrade auf Pi Zero 2 WH (armv7/armv8) nötig für Batterie-Support. Bis dahin: `battery: "none"` in hardware.yaml.

## UI-Konzept (20x4 LCD)

### Designregeln
- **Im Spiel: Alle 4 Zeilen für Gameplay** — keine System-Info
- **Im Menü: Zeile 4 fixiert** — Shortcuts (*=Status, /=Update) + WiFi-Icon rechts
- **Status-Info: Eigener Screen** — Taste *, mehrseitig, Enter=weiter, <-=zurück
- **Modusliste scrollbar** — bei >3 Modi, Zeile 4 bleibt fixiert

### Numpad-Navigation
Das Delock USB-Numpad sendet IMMER Ziffern-Keycodes (KEY_KP0-KEY_KP9), unabhängig vom NumLock-Status. In Navigations-Screens werden 8/2/4/6 per `translate_digit_to_nav()` zu Up/Down/Left/Right übersetzt. In Digit-Screens (Armed, Planting, Code-Eingabe) bleiben Ziffern unverändert.

```
8=▲  2=▼  4=◄  6=►     Navigation (Menü, Setup)
0-9                     Zifferneingabe (Armed, Planting, Code-Entry)
Enter                   Bestätigen / Nächste Seite / Sub-Menü öffnen
<- (Backspace)          Zurück / Abbrechen / Ziffer löschen
+/-                     Schnell Wert +10/-10 (z.B. Timer +/- 5min)
*                       Status Screen (aus Menü)
/                       Update Screen (aus Menü)
```

### Screen-Layouts

**Boot:** Zeile 1-2: "AIRSOFT PROP / PROP v{version}", Zeile 4: "Booting...", 2-3 Sek. sichtbar

**Hauptmenü:** Zeile 1-3: Modusliste mit ▸ Cursor (Navigation per 8/2 = Up/Down, Enter = auswählen), Zeile 4: `* Status  / Upd  ⊕` (WiFi-Icon, optional Batterie-Icon). Keine Ziffern-Shortcuts für Modi.

**Setup (je Modus):** Zeile 1: Modusname, Zeile 2-3: Optionen (8/2=▲▼ wählen, 4/6=◄► ändern). Zeile 4: `<- Back  Ent Start` (RANGE) oder `<- Back  Ent Edit` (CODE_INPUT). Enter auf CODE_INPUT öffnet Code-Eingabe Sub-Screen.

**Setup — Code-Eingabe Sub-Screen:** Zeile 1: Modusname, Zeile 2: `Enter Code:`, Zeile 3: `> {eingabe}____`, Zeile 4: `<- Back   Ent Ok`. Ziffern 0-9 werden direkt eingegeben, Backspace löscht, Enter bestätigt.

**Tournament:** Zeile 1+4: `##Tournament-Mode##`, Zeile 2: `Game: <Modus>`, Zeile 3: `> Start Game`. Einzige Aktion: Enter → Spiel starten. 5x Backspace → PIN-Eingabe.

**Planting — Code Entry:** Zeile 1: `PLANTING {device_name}...`, Zeile 2: `Enter code to arm:`, Zeile 3: Aktivierungscode, Zeile 4: `> {eingabe}____` (Backspace löscht/bricht ab, korrekte Eingabe → ARMED)

**Planting — Timed (Enter halten):** Zeile 1: `PLANTING {device_name}...`, Zeile 2: leer, Zeile 3: Progressbar `[=====>          ]`, Zeile 4: `Hold ENTER  Xs` (Enter loslassen → Abbruch, Countdown=0 → ARMED)

**Armed — Random Code:** Zeile 1: `** {device_name} ARMED **`, Zeile 2: Timer, Zeile 3: Generierter Code (max 20 Zeichen, KEIN Label), Zeile 4: Eingabe als Underscores (gleiche Länge wie Code, <- löscht)

**Armed — Set Code:** Zeile 1: `** {device_name} ARMED **`, Zeile 2: Timer, Zeile 3: `Enter Code:`, Zeile 4: `> {eingabe}____` (Code NICHT sichtbar, max 10 Zeichen)

**Armed — Random Code+ / Set Code+:** Wie Basis-Modi, aber bei falscher Ziffer wird Zeile 4 kurz (~0.7s) durch `WRONG! -Xs` ersetzt (X = konfigurierte Penalty). Bei Set Code+ werden korrekte Ziffern als `*` angezeigt (z.B. `> ***___`). Kein Backspace — jede Ziffer wird sofort validiert.

**Armed — USB Key Cracker (wartend):** Zeile 1: `** {device_name} ARMED **`, Zeile 2: Timer, Zeile 3: leer, Zeile 4: `Insert USB Key...`

**Armed — USB Key Cracker (cracking):** Zeile 1: `** {device_name} ARMED **`, Zeile 2: `Cracking...  Xs`, Zeile 3: `[####........] XX%`, Zeile 4: `7 3 * * * * * *` (geknackte=fix, Rest=cycling)

**Letzte 30s:** Timer blinkt, Piepen beschleunigt (alle 2s statt 5s)

**Letzte 10s:** Timer wandert in Zeile 1 als `!! 00:07 !! ARMED !!` (blinkend). Restliche Zeilen bleiben modusspezifisch. Jeder Modus implementiert `render_last_10s()`:
- Random Code (≤10 Ziffern): Zeile 2 leer, Zeile 3 Code, Zeile 4 Eingabe
- Random Code (>10 Ziffern): Zeile 2 Code, Zeile 3 Eingabe, Zeile 4 leer
- Set Code: Zeile 2 leer, Zeile 3 `Enter Code:`, Zeile 4 Eingabe
- USB Key Cracker (wartend): Zeile 2 leer, Zeile 3 `INSERT USB KEY!!`, Zeile 4 leer
- USB Key Cracker (cracking): Zeile 2 Status, Zeile 3 Progressbar, Zeile 4 Digits
- Random Code+: Wie Random Code, aber Zeile 4 zeigt `WRONG! -Xs` bei Penalty-Flash
- Set Code+: Wie Set Code, aber Zeile 4 zeigt `> ***___` (korrekte=*, Rest=_) bzw. `WRONG! -Xs`

**Ergebnis — Defused:** `{device_name} DEFUSED!` + `Time left: MM:SS`, `Ent -> Menu`, Audio: defused.wav
**Ergebnis — Detonated:** Invertierter Rahmen `{device_name} EXPLODED! / GAME OVER!`, Audio: explosion.wav → siren.wav (Endlosschleife bis Enter)

**Status (Taste *, blätterbar):**
- Seite 1 Netzwerk: WLAN-Name + IP im Station-Mode, oder `AP: airsoft-prop / Pass: defuse1337 / -> Connect` wenn Captive Portal aktiv
- Seite 2 System: Version, CPU-Temp, RAM, Uptime
- Seite 3 Batterie: Status/Prozent/Spannung (oder "Kein UPS-HAT erkannt")
- Navigation: Enter=nächste Seite, <-=zurück zum Menü

**Update (Taste /):** Prüft Internet → zeigt Version → Enter=installieren, <-=abbrechen. Nach erfolgreichem Update: `Ent Restart <- Back` — Enter startet den Service neu (`sudo systemctl restart airsoft-prop`), im Mock-Modus wird die App beendet.

## Konfigurierbarer Gerätename (`device_name`)

Alle Gameplay-Strings auf dem LCD verwenden eine konfigurierbare Variable statt eines hardcoded Begriffs.

**Config (`config/default.yaml`):**
```yaml
game:
  device_name: Prop   # Max 7 Zeichen (LCD-Limit). Beispiele: "Prop", "Device"
```

**Zeichenlimit:** Max 7 Zeichen. Engste Stelle: `** {name} ARMED **` (13 Zeichen fest, 7 frei bei 20 Spalten). Validierung:
1. **Web-Interface:** `maxlength="7"` + serverseitige Validierung im POST `/api/config`
2. **Config-Laden:** Truncation-Fallback in `Config._load()` falls `custom/user.yaml` manuell editiert wurde

**Zugriff im Code:**
- **Modi** (haben `GameContext`): `context.custom_data.get("device_name", "Prop").upper()`
- **UI-Screens** (haben `self.app`): `self.app.config.get("game", "device_name", default="Prop").upper()`
- `device_name` wird beim Erstellen des `GameContext` in `setup_screen.py` und `tournament_screen.py` aus der Config in `custom_data` gesetzt.

## Spielmodi-Spezifikationen

### Random Code
- Setup: Timer (00:30–99:59, ◄► 30s-Schritte, +/- 5min), Digits (4–20)
- Planting: CODE_ENTRY — Spieler muss den generierten Spielcode eintippen um zu planten
- Armed: Zufälliger Zahlencode wird angezeigt, Spieler muss identischen Code eintippen
- Defuse: Code vollständig korrekt eingegeben
- Eingabe: <- löscht letzte Ziffer, falsche Komplettierung -> Eingabe löschen und neu

### Set Code
- Setup: Timer (00:30–99:59), Code (1–10 Ziffern, manuell eingeben)
- Planting: CODE_ENTRY — separater 10-Ziffern Zufalls-Aktivierungscode (NICHT der Geräte-Code)
- Armed: Code wird NICHT angezeigt, Spieler muss ihn anderweitig herausfinden
- Defuse: Korrekter Code eingegeben
- Eingabe: <- löscht letzte Ziffer, falsche Komplettierung -> Eingabe löschen und neu

### Random Code+
- Basiert auf Random Code, erbt von `RandomCodeMode`
- Setup: Timer (00:30–99:59), Digits (4–20) — identisch zu Random Code
- Planting: CODE_ENTRY — wie Random Code
- Armed: Zufälliger Zahlencode wird angezeigt, **jede Ziffer wird sofort geprüft**
  - Korrekte Ziffer: bleibt stehen, nächste Position
  - Falsche Ziffer: wird verworfen, Zeitstrafe wird abgezogen (default 10s, konfigurierbar)
  - Visuelles Feedback: "WRONG! -Xs" wird ~0.7s auf der Eingabezeile angezeigt
  - Audio: `wrong.wav` wird bei Fehler abgespielt
  - Kein Backspace — Ziffern werden sofort validiert
- Defuse: Alle Ziffern korrekt eingegeben
- Detonation: Timer läuft ab (auch durch Penalties möglich)
- Config: `game.penalty_seconds` (shared mit Set Code+, Web-Interface konfigurierbar)

### Set Code+
- Basiert auf Set Code, erbt von `SetCodeMode`
- Setup: Timer (00:30–99:59), Code (1–10 Ziffern) — identisch zu Set Code
- Planting: CODE_ENTRY — separater 10-Ziffern Aktivierungscode (wie Set Code)
- Armed: Code wird NICHT angezeigt, **jede Ziffer wird sofort geprüft**
  - Korrekte Ziffer: als `*` angezeigt (Code bleibt verborgen)
  - Falsche Ziffer: wird verworfen, Zeitstrafe (identisch zu Random Code+)
  - Visuelles Feedback und Audio wie Random Code+
  - Kein Backspace
- Defuse: Alle Ziffern korrekt eingegeben
- Display: `> ***___` (3 von 6 Ziffern korrekt)

### USB Key Cracker
- Setup: Timer (00:30–99:59), Digits (4–12, bestimmt Cracking-Dauer)
- Planting: TIMED — Enter 10 Sekunden halten (loslassen = Abbruch)
- Armed: Zeigt `Insert USB Key...`, wartet auf USB-Stick mit `DEFUSE.KEY`
- Defuse: USB-Stick einstecken → Cracking-Animation startet
  - Dauer: `digits × 2.5s` (z.B. 8 Ziffern = 20s)
  - Alle ~2.5s wird eine Ziffer in zufälliger Reihenfolge "geknackt"
  - Ungeknackte Ziffern: schnelles Cycling (0-9 zufällig, jeder Render-Frame)
  - Geknackte Ziffer: bleibt auf korrektem Wert stehen
  - USB-Stick ziehen → Cracking abgebrochen, Fortschritt verloren
  - Alle Ziffern geknackt → DEFUSED
- HAL: `UsbDetectorBase` — pollt `DEFUSE.KEY` auf gemounteten USB-Medien und validiert Dateiinhalt gegen Allowlist (siehe USB Key Security System)
- Mock: `.`-Taste togglet USB-Einstecken/Entfernen

## USB Key Security System

### Motivation
Ohne Validierung akzeptiert das Gerät jeden USB-Stick mit einer Datei namens `DEFUSE.KEY` oder `TOURNAMENT.KEY`. Spieler die das Repository kennen können sich selbst Keys erstellen und so Challenge-Modi umgehen oder Tournament-Sperren ohne Wissen des Veranstalters lösen. Das Security-System verhindert dies durch kryptografische Token-Validierung.

### Sicherheitsmodell
- **Token-Generierung**: Beim Erstellen eines Keys via Web-Interface wird ein UUID4-Token erzeugt und in die `.KEY`-Datei auf dem USB-Stick geschrieben. Der SHA-256-Hash des Tokens wird in `custom/usb_keys.yaml` gespeichert (nicht der rohe Token).
- **Validierung**: `UsbDetector._scan_for_valid_key()` liest den Dateiinhalt, strippt Whitespace, hasht mit SHA-256 und vergleicht gegen die In-Memory-Allowlist (`frozenset[str]`).
- **Permissive Mode**: Leere Allowlist → Rückwärtskompatibilität (alle `.KEY`-Dateien werden akzeptiert). Aktiviert sich automatisch sobald der erste Key registriert wird → **Strict Mode**.
- **Hot-Reload**: Nach Key-Generierung oder -Widerruf ruft der Web-Server `usb_detector.reload_allowlists()` auf. Der laufende Game-Loop übernimmt die neuen Hashes ohne Neustart. Assignment von `frozenset` ist atomar in CPython (GIL, Pi Zero Single-Core) — kein Lock nötig.
- **Dateistruktur**: Tokens werden nie im Plaintext gespeichert. Der rohe Token erscheint einmalig in der HTTP-Response der Generate-API und wird nicht erneut angezeigt.

### Datenspeicherung (`custom/usb_keys.yaml`)
Separate Datei, **nicht** `user.yaml`. Liegt im `custom/`-Verzeichnis, überlebt daher den "Reset to Defaults"-Button (der nur `user.yaml` löscht). Gitignored.

```yaml
defuse_keys:
  - id: "a1b2c3d4"           # Erste 8 Hex-Zeichen der UUID4 (nur Anzeige)
    label: "Red Team Key 1"
    token_hash: "e3b0c442..."  # SHA-256 des UUID4-Tokens
    created_at: "2026-04-12T14:30:00+00:00"
tournament_keys:
  - id: "f5e6d7c8"
    label: "Organizer Key"
    token_hash: "a665a459..."
    created_at: "2026-04-12T14:31:00+00:00"
```

`Config.load_usb_keys()` und `Config.save_usb_keys()` in `src/utils/config.py` sind die einzigen Zugriffspunkte.

### Web-Interface (`/usb-keys`)
Drei Abschnitte:
1. **Security Status**: Zeigt Permissive/Strict Mode für Defuse- und Tournament-Keys getrennt.
2. **Generate New Key**: Wählt Key-Typ (Defuse/Tournament), optionales Label, Ziel-USB-Stick (aus Scan von `/media/`, `/mnt/`). Nach Generierung: Token einmalig angezeigt mit Copy-Button und Hinweis dass er nicht erneut gezeigt wird.
3. **Existing Keys**: Liste aller registrierten Keys mit ID, Label, Datum und Widerrufen-Button.

Auf dem Pi: Schreibt direkt die `.KEY`-Datei auf den USB-Stick. Im Mock-Modus: kein Filesystem-Write, Token wird nur in `usb_keys.yaml` registriert.

### Cut the Wire (Draft — `src/modes/_drafts/`)
- **Status**: In Überarbeitung, nicht aktiv im Menü
- Wird von Auto-Discovery ignoriert (liegt in `_drafts/` Unterverzeichnis)
- Setup: Timer, Wire-Check (alle 3 Kabel müssen stecken vor Start)
- Armed: 3 farbige Kabel (R=Rot, B=Blau, G=Grün), Rollen zufällig zugewiesen
  - 1 Wire = Defuse (Gerät entschärft)
  - 1 Wire = Explode (sofortige Detonation)
  - 1 Wire = Halve (restliche Zeit halbiert)
- Erkennung: GPIO HIGH=Kabel steckt, GPIO LOW=Kabel gezogen

## Audio-System
- Sound-Dateien: WAV-Format in `assets/sounds/` (44100 Hz, 16-bit)
- Dateien: `beep.wav`, `planted.wav`, `explosion.wav`, `siren.wav`, `defused.wav`, `wrong.wav` (Fehler-Buzzer für Plus-Modi)
- Piep-Intervall: Normal=5s, <30s=2s, <10s=0.8s, <5s=0.5s (Intervalle >500ms wegen ~400ms Beep-Länge)
- Bei jedem Beep blinkt synchron die Status-LED (`app.led.blink_once()`)
- `siren.wav` wird nach Detonation als Endlosschleife (`play_loop`) abgespielt, bis Enter gedrückt wird
- Audio wird über HAL abgespielt; MockAudio spielt echte Sounds via pygame-ce (stummer Fallback wenn Dateien fehlen)
- **Audio-Ausgang:** Konfigurierbar in `hardware.yaml` unter `audio.output`: `"usb"` (USB Lautsprecher, default) oder `"pwm"` (GPIO18 PAM8403). USB nutzt 44100 Hz / 2048 Buffer, PWM nutzt 22050 Hz / 512 Buffer.
- **USB Audio:** Mixer-Init hat Retry-Logik (3 Versuche, 2s Pause) für USB-Geräte die nach Boot noch nicht enumerated sind. Systemd-Service wartet zusätzlich 3s vor Start (`ExecStartPre`). ALSA-Default wird über `~/.asoundrc` auf USB-Karte gesetzt.
- **Wichtig bei neuen Sounds:** Neue Sounds müssen an **zwei Stellen** registriert werden:
  1. `config/default.yaml` → `audio.sounds` (Name → Dateipfad-Mapping)
  2. `src/hal/audio_mock.py` → `MockAudio.init()` → `self._sounds` Dict (hardcoded Map, liest NICHT aus Config)
  
  Fehlt der Eintrag in `audio_mock.py`, wird `play("name")` im Mock-Modus als "unknown sound" ignoriert.

- **Custom Sound Overrides:** Nutzer können eigene WAV-Dateien in `custom/sounds/` ablegen. Beim Laden prüft das Audio-HAL (real und mock) zuerst `custom/sounds/<filename>`, dann den Default-Pfad aus `assets/sounds/`. Gleicher Dateiname = Override. Das `custom/`-Verzeichnis ist gitignored und überlebt Updates.

## Logging-System

### Architektur
Zentrales Logging über `src/utils/logger.py`. Alle Module verwenden `get_logger(__name__)`. Kein `print()` im Code.

### Log-Rotation
- Bei jedem Programmstart wird das bestehende `prop.log` zu `prop.YYYY-MM-DD_HH-MM-SS.log` archiviert (Timestamp = Modifikationszeit der Datei)
- Danach wird ein frisches `prop.log` erstellt
- Älteste Archive werden gelöscht wenn die Anzahl `max_files` überschreitet
- **Kein** `RotatingFileHandler` oder `TimedRotatingFileHandler` — manuelle Rotation pro Session

### Konfiguration (`config/default.yaml`)
```yaml
logging:
  level: INFO        # DEBUG / INFO / WARNING / ERROR
  log_dir: logs      # Verzeichnis für Logfiles (relativ zum Projekt-Root)
  log_file: prop.log # Name des aktuellen Logfiles
  max_files: 10      # Max archivierte Logfiles
```

CLI-Flags überschreiben YAML-Werte: `--debug` (erzwingt DEBUG), `--log-file PATH`, `--no-log-file` (nur stderr).

Beim Start werden `user.yaml`-Overrides für Logging bereits vor der vollen Config-Initialisierung geladen (`main.py`), sodass benutzerdefinierte Log-Level sofort ab der ersten Log-Zeile gelten.

Log-Level kann zur Laufzeit geändert werden (kein Neustart nötig): Web-Interface sendet Event `logging_level_changed` → `app.py` ruft `set_log_level()` aus `logger.py` auf. Max-Files-Änderungen wirken erst beim nächsten Programmstart.

### Was wird erfasst
- Alle Logger-Calls (120+ über 23 Module)
- **Uncaught Exceptions**: `sys.excepthook` (Main-Thread) + `threading.excepthook` (alle Threads inkl. Flask, MockInput)
- **Python Warnings**: `logging.captureWarnings(True)`
- **Stray stderr**: `sys.stderr` wird auf `_LoggerWriter` umgeleitet — fängt Output von Third-Party-Libraries
- **Startup-Diagnostik**: Python-Version, Platform, Architecture, aktive HAL-Klassen, Config-Snapshot

### Main-Loop-Resilienz
Der Main-Loop in `src/app.py` hat einen inneren try/except: Ein einzelner Render- oder Input-Fehler crasht nicht die App, sondern wird geloggt. Nach 10 aufeinanderfolgenden Fehlern → sauberer Shutdown.

### Remote-Zugriff
Logs können über das Web-Interface unter `/logs` eingesehen werden (Log-Viewer mit Dateiauswahl, Zeilenlimit, Textfilter und Syntax-Highlighting nach Log-Level).

## Netzwerk-Konzept

### Variante 1: Default-Hotspot (Fallback)
Konfiguriert in `config/network.yaml` (SSID + Passwort). Pi verbindet sich beim Boot automatisch. Nutzer stellt seinen Handy-Hotspot auf denselben Namen/Passwort. Das Web-Interface ist dann auch vom Smartphone selbst erreichbar unter `http://<Pi-IP>:8080` (IP über Status-Screen Taste * ablesen; typische Subnetze: Android `192.168.43.x`, iPhone `172.20.10.x`).

### Variante 2: Captive Portal + Web-Interface (Hauptlösung)
Wenn kein bekanntes WLAN gefunden: Pi startet eigenen AP (SSID: "airsoft-prop", PW: "defuse1337"). Handy verbindet sich → Captive Portal öffnet sich → Web-Interface für:
- WLAN-Konfiguration (scannen, verbinden)
- Spieleinstellungen (Device Name, Timer-Defaults, Lautstärke, LCD-Helligkeit)
- Updates (prüfen, installieren, Changelog)
- System-Info (IP, Temp, RAM, Uptime)

Web-Interface: Flask, mobile-first, minimales CSS (kein Framework), vanilla JS.
Läuft auch im Normalbetrieb auf Port 8080 weiter.

LCD zeigt im AP-Modus: `=== Network === / AP: airsoft-prop / Pass: defuse1337 / -> Connect phone`

Tech-Stack AP: hostapd + dnsmasq + Flask + NetworkManager.

**Captive Portal Implementierung (`src/web/captive_portal.py`):**
- `CaptivePortalBase` — ABC mit `start_ap()`, `stop_ap()`, `is_active()`, `get_ap_info()`, `start_monitor()`, `stop_monitor()`, `shutdown()`
- `CaptivePortal` — Reale Implementierung:
  - `start_ap()`: nimmt wlan0 von NM (`nmcli device set wlan0 managed no`), setzt statische IP, startet hostapd + dnsmasq als Subprozesse mit generierten Configs in `/tmp/`
  - `stop_ap()`: killt hostapd/dnsmasq, gibt wlan0 an NM zurück
  - DNS-Redirect: `address=/#/<AP-IP>` in dnsmasq → alle DNS-Anfragen zeigen auf den Pi
  - Background-Monitor-Thread: prüft alle 15s WiFi-Status, startet AP automatisch bei Verbindungsverlust
  - Thread-safe via `threading.Lock` (Schutz gegen Races zwischen Monitor und Web-UI)
- `MockCaptivePortal` — Simuliert AP-Modus für Desktop-Tests (keine echten Prozesse)
- `create_captive_portal(config, mock)` — Factory-Funktion

**Captive Portal Detection (in `server.py`):**
- `/generate_204`, `/gen_204` — Android/Chromebook: 302-Redirect auf `/wifi` wenn AP aktiv, sonst 204
- `/hotspot-detect.html` — Apple iOS/macOS: Redirect wenn AP aktiv, sonst "Success"-HTML
- `/connecttest.txt` — Windows: Redirect wenn AP aktiv, sonst "Microsoft Connect Test"
- `@app.errorhandler(404)` — Catch-All: alle unbekannten URLs → `/wifi` wenn AP aktiv
- `/api/wifi/connect` — stoppt AP vor WiFi-Verbindung, startet AP neu bei Connect-Fehler

**AP-Config aus `config/network.yaml`:**
```yaml
access_point:
  ssid: "airsoft-prop"       # (ehemals "rpi-bmb")
  password: "defuse1337"
  channel: 6
  ip: "192.168.4.1"
  netmask: "255.255.255.0"
  dhcp_range_start: "192.168.4.10"
  dhcp_range_end: "192.168.4.50"
```

**App-Lifecycle-Integration:**
- `App._init_network()` wird vor `_init_web_server()` aufgerufen
- Prüft WiFi-Status beim Start → startet AP wenn nötig
- Startet Background-Monitor für Runtime-Überwachung
- `App.shutdown()` → `captive_portal.shutdown()` (Monitor stoppen, AP stoppen)
- `App.captive_portal` — Attribut für Zugriff aus Screens und Web-Server

**hostapd/dnsmasq Management:**
- System-Services werden beim Install via `systemctl mask` deaktiviert
- App startet hostapd/dnsmasq direkt als Subprozesse mit Configs in `/tmp/airsoft-hostapd.conf` und `/tmp/airsoft-dnsmasq.conf`
- Prozesse werden per PID getrackt, sauber terminiert bei `stop_ap()` und `shutdown()`

### Web-Interface Architektur

Das Web-Interface (`src/web/`) läuft als Daemon-Thread neben dem Hauptspiel-Loop und ist unter Port 8080 erreichbar.

**Komponenten:**
- `server.py` — Flask-App mit allen Routes, `WebServer`-Klasse (startet Flask in `threading.Thread(daemon=True)`)
- `wifi_manager.py` — Abstraktion für WiFi-Management mit zwei Implementierungen:
  - `RealWifiManager` — nutzt `nmcli` (NetworkManager) auf dem Pi. Netzwerk-ändernde Befehle (rescan, connect, disconnect, forget) laufen über `sudo` wegen fehlender PolicyKit-Berechtigungen des `pi`-Users. Sudoers-Datei: `/etc/sudoers.d/airsoft-prop-wifi` (wird von `install.sh` angelegt). `nmcli -t` Output wird mit einem Escape-aware Parser (`_parse_nmcli_terse()`) verarbeitet, da `nmcli -t` Doppelpunkte in Feldwerten als `\:` escaped. `_run()` gibt `stderr` als Fallback zurück wenn `stdout` leer ist. MAC-Adresse wird aus `GENERAL.HWADDR` gelesen (Doppelpunkte dort NICHT escaped → Parts werden rekonkatiniert). WiFi-Scan: `sudo nmcli device wifi rescan` (separater Schritt), dann `nmcli ... device wifi list` (ohne --rescan). API-Responses erhalten `Cache-Control: no-store` via `after_request`-Hook.
  - `MockWifiManager` — simuliert 5 Netzwerke für Desktop-Tests
- `captive_portal.py` — AP-Management mit hostapd/dnsmasq, Captive Portal Detection, Background-Monitor (siehe Netzwerk-Konzept)

**Integration in App-Lifecycle:**
- `App._init_network()` wird nach Screen-Init aufgerufen — initialisiert Captive Portal, startet AP wenn kein WLAN, startet Background-Monitor
- `App._init_web_server()` wird danach aufgerufen — gibt `captive_portal`-Referenz an WebServer weiter
- `WebServer` wird **lazy importiert** (kein Top-Level-Import in `app.py`) — Flask ist nur nötig wenn `web.enabled: true`
- Bei fehlendem Flask (z.B. im Standalone-Build) wird eine `ImportError`-Warnung geloggt und der Server übersprungen
- `WebServer.start()` startet den Flask-Server als Daemon-Thread
- `WebServer.stop()` wird im `App.shutdown()` aufgerufen (Thread stirbt mit Hauptprozess)
- `App.shutdown()` → `captive_portal.shutdown()` vor Web-Server-Stop (Monitor stoppen, AP herunterfahren)
- Mock-Flag wird von `App._mock` durchgereicht → steuert `MockWifiManager`/`MockCaptivePortal` vs. reale Implementierungen

**Seiten & API:**
- `/wifi` — WiFi-Status, Netzwerk-Scan, Verbinden/Trennen, gespeicherte Netzwerke
- `/config` — Spieleinstellungen (Device Name, Timer, Digits, Plus-Modi Penalty Seconds, Volume, Backlight), Logging-Settings (Level, Max Files), Reset to Defaults, schreibt nach `custom/user.yaml`
- `/tournament` — Tournament Mode Ein-/Ausschalten, Modus-Auswahl mit dynamischen Settings, PIN-Konfiguration
- `/usb-keys` — USB Key Management: Security-Status (Permissive/Strict Mode), Key-Generierung (schreibt Token auf USB-Stick, speichert Hash in `usb_keys.yaml`), Key-Übersicht mit Widerrufen-Button
- `/system` — Systeminfo (Version, CPU-Temp, RAM, Uptime, Plattform)
- `/battery` — Batterie-Status (Ladestand mit Balken, Laufzeitschätzung, Spannung, Stromverbrauch, Ladestatus, Powerbank-Anschluss), Auto-Refresh alle 10s
- `/logs` — Log-Viewer: Dateiauswahl, konfigurierbare Zeilenanzahl, Textfilter mit Highlighting, farbkodierte Log-Level (ERROR=rot, WARNING=orange, DEBUG=grau, CRITICAL=fett rot)
- `/update` — Git-basierte Updates prüfen und installieren
- Alle Daten werden über `/api/*` JSON-Endpunkte geladen (vanilla JS `fetch()`)
- `/api/wifi/ap-status` — AP-Status (active, ssid, password, ip)
- `/api/battery` — Batterie-Daten (level, voltage, current_ma, charging, power_plugged, runtime_minutes); `{"available": false}` wenn kein HAT
- `/api/logs` — Liste aller Logfiles (Name, Größe, Datum), sortiert nach Datum (neuestes zuerst)
- `/api/logs/<filename>` — Letzte N Zeilen eines Logfiles (`?lines=200`), mit Path-Traversal-Schutz
- `/api/usb-keys` — Registrierte Keys (defuse_keys, tournament_keys, permissive_defuse, permissive_tournament)
- `/api/usb-keys/usb-sticks` — Erkannte USB-Sticks (mount_point, label) — selber Scan-Algorithmus wie `UsbDetector`
- `/api/usb-keys/generate` [POST] — Token generieren, auf USB-Stick schreiben, Hash in `usb_keys.yaml` speichern, Allowlist hot-reloaden; returns Token einmalig
- `/api/usb-keys/<key_type>/<key_id>` [DELETE] — Key widerrufen, Allowlist hot-reloaden

**Config-Persistierung:** Zweistufiges System — `default.yaml` enthält Auslieferungs-Defaults (Git-getrackt), `custom/user.yaml` enthält nur User-Overrides (gitignored, überlebt Updates). `POST /api/config` empfängt ein flaches Dict mit Punkt-separierten Keys (z.B. `{"audio.volume": 0.5}`), filtert nur Abweichungen von Defaults heraus und schreibt sie nach `custom/user.yaml`. `POST /api/config/reset` löscht `custom/user.yaml` und setzt alles auf Defaults zurück — **`custom/usb_keys.yaml` wird dabei NICHT gelöscht**. `GET /api/config` liefert zusätzlich `"customized": [...]` mit den Keys die User-Overrides haben. Ladeordnung: `default.yaml` → `custom/user.yaml` → `hardware.yaml` → `network.yaml`. USB-Key-Registry wird separat über `Config.load_usb_keys()` / `Config.save_usb_keys()` aus `custom/usb_keys.yaml` gelesen/geschrieben.

**Migration:** Beim ersten Start nach Update prüft `Config._load()` ob `config/user.yaml` oder `config/usb_keys.yaml` existieren und verschiebt sie automatisch nach `custom/` (einmalig, mit Log-Meldung).

**Mock-Modus:** Im Mock zeigt die WiFi-Seite simulierte Netzwerke (AirsoftProp, HomeNetwork etc.), Connect/Disconnect funktioniert in-memory, Update zeigt simuliertes Update. Desktop-Systeminfo wird real angezeigt (Platform, Python-Version etc.). Battery-Seite zeigt simulierte Mock-Werte (entlädt sich langsam von 85%).

## Versionierung

### Single Source of Truth: Git-Tags
Die Anwendungsversion wird automatisch aus Git-Tags abgeleitet (`git describe --tags --always`). Es gibt keine manuell gepflegte Versionsnummer in Config-Dateien.

**Zentrales Modul:** `src/utils/version.py`
- `get_version()` — Ermittelt die Version einmalig beim Start (gecacht)
- `format_version_short(version)` — Kürzt für 20-Zeichen-LCD (z.B. `1.0.0-3-gabcdef` → `1.0.0+3`)

**Auflösungs-Reihenfolge:**
1. **Frozen Build** (`sys.frozen`): Liest `VERSION`-Datei neben der .exe (wird im CI-Build aus dem Git-Tag generiert)
2. **Source-Betrieb**: `git describe --tags --always` im Projekt-Root
3. **Fallback**: `"unknown"`

**Injection in Config:** `Config._load()` ruft `get_version()` auf und setzt `self._data["version"]`. Alle bestehenden `config.get("version")`-Aufrufe funktionieren ohne Änderung, auch nach Config-Reload via Web UI.

**Update-Erkennung:** `updater.py` und `update.sh` nutzen `git describe --tags --always` statt `git rev-parse --short`. Der Update-Screen zeigt jetzt z.B. `1.0.0 -> 1.0.1` statt Git-Hashes. Tags werden explizit mit `git fetch --tags origin` geholt.

**Release-Workflow:**
1. Code committen + pushen
2. `git tag v1.0.1 && git push origin v1.0.1`
3. Fertig — Version erscheint automatisch auf Boot Screen, Status Screen, Web UI und im Update-Vergleich

## Repo-Struktur
```
airsoft-prop/
├── README.md
├── LICENSE
├── CLAUDE.md                    # Diese Datei
├── .gitignore                   # Ignoriert logs/, __pycache__/, venv/, custom/
├── install.sh                   # One-Click Installer
├── update.sh                    # Git-basiertes Update
├── requirements.txt             # Gepinnte Python-Abhängigkeiten
├── requirements-pi.txt          # Pi-spezifische Abhängigkeiten (RPLCD, GPIO, smbus2, evdev)
├── build/
│   ├── airsoft_prop.spec        # PyInstaller Spec (onedir, console)
│   └── hook-runtime-mock.py     # Runtime-Hook: erzwingt --mock im Standalone-Build
├── .github/
│   └── workflows/
│       └── build-release.yml    # GitHub Actions: Build + Release bei Tag v*
├── config/
│   ├── default.yaml             # Spiel- & Logging-Einstellungen (Auslieferungs-Defaults)
│   ├── hardware.yaml            # Pinout, I2C-Adresse, HAL-Auswahl
│   └── network.yaml             # WLAN-Konfiguration
├── custom/                      # User-spezifische Dateien (gitignored, komplett)
│   ├── user.yaml                # User-Overrides (auto-erstellt bei Änderung)
│   ├── usb_keys.yaml            # USB Key Registry (wird nie durch Reset gelöscht)
│   ├── sounds/                  # Custom Sound-Overrides (gleiche Dateinamen wie assets/sounds/)
│   ├── modes/                   # Eigene Spielmodi (.py, auto-discovered)
│   └── hal/                     # Eigene HAL-Implementierungen (via hardware.yaml)
├── assets/
│   └── sounds/                  # Standard-WAV-Dateien (Git-getrackt, lizenzfrei)
├── logs/                        # Logfiles (auto-erstellt, gitignored)
│   ├── prop.log                 # Aktuelle Session
│   └── prop.*.log               # Archivierte Sessions
├── src/
│   ├── __init__.py
│   ├── main.py                  # Entry Point
│   ├── app.py                   # State Machine, App-Lifecycle
│   ├── hal/
│   │   ├── __init__.py
│   │   ├── base.py              # Abstrakte Basisklassen (ABC)
│   │   ├── display_lcd.py
│   │   ├── display_mock.py
│   │   ├── audio.py
│   │   ├── audio_mock.py
│   │   ├── input_numpad.py
│   │   ├── input_mock.py
│   │   ├── wires.py
│   │   ├── wires_mock.py
│   │   ├── usb_detector.py      # USB-Key-Erkennung (real, Token-Validierung via SHA-256)
│   │   ├── usb_detector_mock.py # USB-Key-Erkennung (Mock, Toggle + Token-Validierung)
│   │   ├── battery_pisugar.py     # PiSugar 3 (TCP Socket zu pisugar-power-manager)
│   │   ├── battery_mock.py        # Simulierte Batterie für Desktop-Tests
│   │   ├── battery_ups_lite.py
│   │   ├── battery_none.py
│   │   ├── led.py               # Status-LED (GPIO via gpiozero)
│   │   └── led_mock.py          # Mock-LED (loggt Aufrufe)
│   ├── modes/
│   │   ├── __init__.py          # Auto-Discovery Logik
│   │   ├── base_mode.py         # BaseMode, PlantingType, PlantingConfig
│   │   ├── random_code.py
│   │   ├── random_code_plus.py  # Random Code+ (Ziffer-für-Ziffer mit Zeitstrafe)
│   │   ├── set_code.py
│   │   ├── set_code_plus.py     # Set Code+ (Ziffer-für-Ziffer mit Zeitstrafe)
│   │   ├── usb_key_cracker.py   # USB Key Cracker Modus
│   │   └── _drafts/             # Entwürfe (nicht auto-discovered)
│   │       └── cut_the_wire.py
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── screen_manager.py
│   │   ├── base_screen.py
│   │   ├── boot_screen.py
│   │   ├── menu_screen.py
│   │   ├── setup_screen.py
│   │   ├── planting_screen.py   # Planting-Phase (Code-Eingabe / Enter halten)
│   │   ├── armed_screen.py
│   │   ├── result_screen.py
│   │   ├── tournament_screen.py  # Tournament Mode Lobby (gesperrter Bildschirm)
│   │   ├── tournament_transition_screen.py  # 3s Übergangs-Screen
│   │   ├── status_screen.py
│   │   ├── update_screen.py
│   │   └── lcd_helpers.py       # Custom Chars, Blink, Progressbar
│   ├── web/
│   │   ├── __init__.py          # Public Exports (WebServer, CaptivePortal, create_app, etc.)
│   │   ├── server.py            # Flask-App, Routes, Captive Portal Detection, WebServer (Daemon-Thread)
│   │   ├── wifi_manager.py      # WiFi-Abstraktion (MockWifiManager / RealWifiManager)
│   │   ├── captive_portal.py    # AP-Management (hostapd/dnsmasq), Background-Monitor
│   │   ├── templates/
│   │   │   ├── base.html        # Base-Layout mit Nav + Footer
│   │   │   ├── wifi.html        # WiFi-Scan, Connect, Saved Networks
│   │   │   ├── config.html      # Spiel- & Logging-Einstellungen
│   │   │   ├── tournament.html  # Tournament Mode Konfiguration
│   │   │   ├── usb_keys.html    # USB Key Management (Security-Status, Generierung, Übersicht)
│   │   │   ├── logs.html        # Log-Viewer (Dateiauswahl, Filter, Highlighting)
│   │   │   ├── update.html      # Git-Update prüfen & installieren
│   │   │   ├── battery.html     # Batterie-Status (Ladestand, Laufzeit, Ladestatus)
│   │   │   └── system.html      # Systeminfo (Version, CPU, RAM)
│   │   └── static/
│   │       ├── style.css        # Dark-Theme, mobile-first
│   │       └── app.js           # Vanilla JS für alle API-Calls
│   └── utils/
│       ├── __init__.py
│       ├── paths.py             # Frozen-aware Pfadauflösung (PyInstaller-kompatibel)
│       ├── config.py            # YAML Config mit zweistufigem Default/User-Override-System + usb_keys.yaml-Helpers
│       ├── updater.py
│       ├── version.py           # Git-Tag-basierte Versionsauflösung
│       └── logger.py            # Logging mit Rotation, Exception-Hooks, stderr-Capture
├── systemd/
│   └── airsoft-prop.service
└── tests/
    ├── test_modes.py
    ├── test_timer.py
    ├── test_version.py          # Tests für Versionsauflösung
    └── test_wires.py
```

## Installer (install.sh)
One-Click: System-Pakete (inkl. `python3-dev`, `libevdev-dev`, `hostapd`, `dnsmasq`), I2C aktivieren, Audio-Overlay, Python venv, `pip install -r requirements.txt` + `pip install -r requirements-pi.txt` (RPLCD, RPi.GPIO, smbus2, evdev), User-Gruppen (i2c, gpio, audio, input), Sudoers-Datei für passwortloses `sudo nmcli` und `sudo systemctl` (`/etc/sudoers.d/airsoft-prop-wifi` — rescan, connect, disconnect, delete, restart/stop airsoft-prop), systemd Service. hostapd/dnsmasq System-Services werden via `systemctl mask` deaktiviert (App steuert sie direkt). Service wird nur gestartet wenn kein Reboot nötig. Prüft OS-Version und warnt bei nicht-getestetem OS. Installationsverzeichnis: `/home/pi/airsoft-prop`.

**USB-Automount:** Der Installer richtet einen udev-Trigger (`/etc/udev/rules.d/99-airsoft-usb.rules`) und einen systemd-Template-Service (`usb-mount@.service`) ein, die beim Einstecken eines USB-Sticks an `sda1` den Mount-Helper `/usr/local/bin/airsoft-usb-mount` aufrufen. Der Helper erkennt den Dateisystem-Typ via `blkid` und mountet entsprechend:
- **FAT/exFAT** (typische USB-Sticks): Mount mit `-o uid=<pi>,gid=<pi>,umask=0022` → `pi`-User hat Schreibrechte
- **ext4/andere**: normaler Mount + `chown` auf den Mount-Point-Root → `pi`-User kann schreiben

Ohne korrekte Eigentümerschaft würde der Flask-Server (läuft als `pi`) beim Schreiben von `.KEY`-Dateien auf den USB-Stick einen `PermissionError` erhalten. Die UID/GID des `pi`-Users werden beim Install einmalig ermittelt und fest in den Helper eingebettet.

**Pi-spezifische Abhängigkeiten** (`requirements-pi.txt`): Separate Datei für Pakete die nur auf dem Pi benötigt werden. Wird von `install.sh` und `update.sh` referenziert. Desktop/Mock-Entwicklung braucht nur `requirements.txt`.

## Update-System (update.sh)
`git fetch --tags origin` → Vergleich via `git describe --tags --always` (lokale vs. remote Version) → `git pull` → `pip install -r requirements.txt` + `pip install -r requirements-pi.txt` → `systemctl restart`. Aufrufbar aus dem Hauptmenü (Taste /) und dem Web-Interface. Update-Screen und -Script zeigen Tag-basierte Versionen (z.B. `1.0.0 -> 1.0.1`) statt Git-Hashes.

## Code-Stil & Konventionen
- Python 3.11 kompatibel, keine 3.12+ Features
- Type Hints überall verwenden
- Docstrings für alle öffentlichen Klassen und Methoden
- Logging über `src/utils/logger.py`, kein `print()`. Logger erfasst automatisch uncaught Exceptions, Warnings und stderr.
- Konfiguration nie hardcoden, immer aus YAML laden
- Fehlerbehandlung: Hardware-Fehler graceful abfangen, nie crashen
- Alle Texte auf dem LCD: Englisch (international verständlich auf Airsoft-Events)
- Kommentare im Code: Englisch

## Mock-Modus (`--mock`)
- Startet mit `python -m src.main --mock` auf jedem Desktop ohne Pi-Hardware
- **Display**: `MockDisplay` rendert 20x4 ASCII-Frame im Terminal via ANSI Escape Codes (in-place, kein Scrollen). `write_line()` buffert nur, `flush()` rendert einmal pro Frame. Nur bei Änderungen wird neu gezeichnet (Snapshot-Vergleich).
- **Audio**: `MockAudio` nutzt `pygame-ce` zum Abspielen von WAV-Dateien. Fehlen Dateien oder pygame → stiller Fallback, kein Crash.
- **Input**: `MockInput` liest Tastatur via Background-Thread. Windows: `msvcrt`, Unix: `termios` Raw-Mode. Taste `.` togglet Mock-USB-Key.
- **USB-Detector**: `MockUsbDetector` simuliert USB-Stick-Einstecken/Entfernen. Toggle per `.`-Taste oder direkt über `toggle()`-Methode. Unterstützt Token-Validierung für Tests: `set_valid_defuse_token(token)` registriert ein Token so dass `is_key_present()` im Strict Mode `True` zurückgibt. `reload_allowlists()` wird vom Web-Server nach Key-Änderungen aufgerufen.
- **LED**: `MockLed` loggt `blink_once()` und `set_enabled()` Aufrufe auf DEBUG-Level. Kein Hardware-Zugriff.
- **Battery**: `MockBattery` simuliert eine sich entladende Batterie (startet bei 85%, entlädt ~0.05%/s). Zeigt simulierte Werte auf Status Screen und Web-Interface.
- **Captive Portal**: `MockCaptivePortal` simuliert AP-Modus ohne echte Prozesse. `is_wifi_connected()` gibt `True` zurück (kein AP nötig im Mock). Monitor-Thread ist ein No-Op.
- **Web-Interface**: Startet automatisch auf `http://localhost:8080`. `MockWifiManager` simuliert 5 Netzwerke mit Connect/Disconnect. Settings werden in `custom/user.yaml` gespeichert (nur Abweichungen von Defaults). Update-Seite zeigt simuliertes Update. Log-Viewer zeigt echte Logfiles. Battery-Seite zeigt MockBattery-Werte.
- **Logging**: Logs gehen immer nach `logs/prop.log` (sowohl Mock als auch Pi), damit das Terminal-Display sauber bleibt. Pro Session wird ein neues Logfile erstellt, alte werden automatisch archiviert und bereinigt. `--no-log-file` schaltet File-Logging ab (nur stderr).
- **Wichtig**: `pygame-ce` verwenden (NICHT `pygame`). Das alte `pygame` funktioniert nicht mit Python 3.13+ wegen entferntem `distutils`.

## Standalone-Build & Release-System

### Überblick
Das Projekt kann als eigenständige Windows-.exe gebaut werden, die ohne Python-Installation läuft. Der Build nutzt PyInstaller im `--onedir`-Modus und wird über GitHub Actions automatisiert.

### Pfadauflösung (`src/utils/paths.py`)
Zentrales Modul für Projekt-Root-Erkennung. Alle Module nutzen `get_project_root()` statt `Path(__file__).parent.parent.parent`:
- **Source-Betrieb**: `Path(__file__).parent.parent.parent` (3 Ebenen hoch)
- **Frozen (PyInstaller)**: `Path(sys.executable).parent` (Ordner mit der .exe)

Nutzer von `get_project_root()`: `config.py`, `logger.py`, `audio_mock.py`, `version.py`.

### PyInstaller-Konfiguration (`build/airsoft_prop.spec`)
- **Modus**: `onedir` (nicht `onefile`) — Config-Dateien liegen editierbar neben der .exe
- **Console**: `True` — Terminal wird für Mock-Display benötigt
- **Runtime-Hook** (`build/hook-runtime-mock.py`): Injiziert `--mock` in `sys.argv`
- **Hidden Imports**: Alle Spielmodi (dynamisch importiert) + `pygame.mixer`
- **Excludes**: Flask, Werkzeug, Jinja2, RPi.GPIO, RPLCD, smbus2, gpiozero
- **Daten**: `config/*.yaml` und `assets/sounds/*.wav` werden neben die .exe kopiert (nicht in `_internal/`)

### GitHub Actions Workflow (`.github/workflows/build-release.yml`)
- **Trigger**: Push eines Tags `v*` (z.B. `git tag v1.0.0 && git push origin v1.0.0`)
- **Runner**: `windows-latest`, Python 3.11
- **Ablauf**: Checkout → pip install (PyInstaller, PyYAML, pygame-ce, KEIN Flask) → Config patchen (`web.enabled: false`) → `VERSION`-Datei aus Tag generieren → PyInstaller bauen → config/, assets/ & VERSION kopieren → ZIP erstellen → GitHub Release mit `softprops/action-gh-release@v2`
- **Ausgabe**: `AirsoftProp-vX.X.X-windows.zip` als Release-Asset
- **VERSION-Datei**: Wird aus dem Git-Tag erzeugt (ohne `v`-Prefix) und neben die .exe gelegt — `version.py` liest sie im Frozen Build

### Neuen Modus im Standalone-Build registrieren
Bei neuen **eingebauten** Spielmodi müssen zwei Stellen aktualisiert werden:
1. `_KNOWN_MODES`-Liste in `src/modes/__init__.py`
2. `hiddenimports`-Liste in `build/airsoft_prop.spec`

Für **custom** Modi in `custom/modes/` ist keine Registrierung nötig — sie werden dynamisch per `importlib.util.spec_from_file_location` geladen (funktioniert nicht im Frozen Build).

## Bekannte Plattform-Hinweise
- **Python 3.13**: `distutils` wurde entfernt → `pygame` (original) baut nicht. Lösung: `pygame-ce>=2.5.3`
- **PyYAML**: Version 6.0.1 baut nicht from source auf Python 3.13 → `>=6.0.1` als Pin damit pip 6.0.2+ wählt
- **requirements.txt**: Verwendet `>=` statt `==` Pins für Kompatibilität über Python-Versionen hinweg
