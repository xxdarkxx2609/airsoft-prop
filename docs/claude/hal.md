# HAL — Hardware Abstraction Layer
<!-- Referenzdokumentation fuer den HAL des Airsoft-Prop-Projekts.
     Methoden-Signaturen sind in src/hal/base.py mit vollstaendigen Docstrings dokumentiert.
     Dieses Dokument beschreibt nur nicht-offensichtlichen architektonischen Kontext. -->

## HAL-Module Uebersicht

Jede Hardware-Komponente wird durch eine abstrakte Basisklasse in `src/hal/base.py` definiert. Konkrete Implementierungen und Mock-Varianten fuer Desktop-Tests existieren als separate Module. Die aktive Implementierung wird ueber `config/hardware.yaml` ausgewaehlt. Eigene HAL-Implementierungen koennen in `custom/hal/` abgelegt und per `custom:module.Class` Syntax in `hardware.yaml` referenziert werden.

| Basisklasse       | Real                          | Mock / Alternativen                                |
|--------------------|-------------------------------|----------------------------------------------------|
| `DisplayBase`      | `display_lcd.py` (20x4 HD44780 I2C) | `display_mock.py` (Terminal, ANSI in-place)   |
| `AudioBase`        | `audio.py` (pygame-ce mixer)  | `audio_mock.py` (pygame-ce, stummer Fallback)      |
| `InputBase`        | `input_numpad.py` (USB Numpad)| `input_mock.py` (Tastatur)                         |
| `WiresBase`        | `wires.py` (GPIO)             | `wires_mock.py` (simuliert)                        |
| `UsbDetectorBase`  | `usb_detector.py` (pollt `/media/`, Token-Validierung) | `usb_detector_mock.py` (`.`-Taste Toggle) |
| `BatteryBase`      | `battery_pisugar.py` (TCP Socket) | `battery_ups_lite.py`, `battery_mock.py`, `battery_none.py` |
| `LedBase`          | `led.py` (GPIO via gpiozero)  | `led_mock.py` (loggt Aufrufe)                      |

## Display Rendering

- `write_line(row, text)` schreibt in den Buffer (kein sofortiges Rendering beim Mock).
- `flush()` rendert den Buffer auf das Display — no-op beim echten LCD, ANSI-Update beim Mock.
- Der Main Loop ruft `flush()` einmal pro Frame nach `render()` auf.
- Mock-Display nutzt Snapshot-Vergleich und zeichnet nur bei Aenderungen neu.

## LCD Hardware

- 20x4 HD44780 mit I2C (PCF8574), Adresse `0x27` (oder `0x3F`, konfigurierbar).
- Custom Characters (8 Slots): WiFi-Icons, Batterie, Cursor, Rahmenelemente, Lock.

## Audio-System

**Sound-Dateien:** WAV-Format in `assets/sounds/` (44100 Hz, 16-bit).
Dateien: `beep.wav`, `planted.wav`, `explosion.wav`, `siren.wav`, `defused.wav`, `wrong.wav`.

**Audio-Ausgang** (`hardware.yaml` → `audio.output`):
- `"usb"` (Default): USB-Lautsprecher, 44100 Hz / 2048 Buffer.
- `"pwm"`: GPIO18 PAM8403, 22050 Hz / 512 Buffer.

**USB Audio Retry:** Mixer-Init hat Retry-Logik (3 Versuche, 2s Pause) fuer USB-Geraete die nach Boot noch nicht enumeriert sind. Der systemd-Service wartet zusaetzlich 3s (`ExecStartPre`). ALSA-Default wird ueber `~/.asoundrc` auf die USB-Karte gesetzt.

**WICHTIG — Neue Sounds muessen an ZWEI Stellen registriert werden:**
1. `config/default.yaml` → `audio.sounds` (Name-zu-Dateipfad-Mapping)
2. `src/hal/audio_mock.py` → `MockAudio.init()` → `self._sounds` Dict (hardcoded, liest NICHT aus Config)

**Custom Sound Overrides:** Eigene WAV-Dateien in `custom/sounds/` ablegen. Das Audio-HAL (real und mock) prueft zuerst `custom/sounds/<dateiname>`, dann `assets/sounds/`. Gleicher Dateiname = Override.

**Beep-Intervalle:** Normal=5s, <30s=2s, <10s=0.8s, <5s=0.5s (Intervalle >=500ms wegen ~400ms Beep-Laenge). `siren.wav` wird nach Detonation als Endlosschleife abgespielt bis Enter gedrueckt wird.

## LED-Synchronisation

`blink_once()` wird synchron mit dem Beep-Sound aufgerufen (`app.led.blink_once()`). Non-blocking (~120ms on, via gpiozero-Thread).

## PiSugar S Batterie

Kommunikation ueber den `pisugar-power-manager` Daemon (TCP Socket `127.0.0.1:8423`), NICHT ueber Raw I2C.

- **Voraussetzung:** `curl http://cdn.pisugar.com/release/pisugar-power-manager.sh | sudo bash`
- **Protokoll:** `"get <key>\n"` senden → `"<key>: <value>\n"` empfangen
- Werte werden alle 5s gecacht, Reconnect-Versuch alle 30s bei Verbindungsverlust
- Fehlender Daemon → graceful Fallback auf `None` fuer alle Werte
- UI-Code muss immer auf `None` pruefen
- **Hardware:** 1200 mAh LiPo, 5V/2.4A Ausgang, USB-C Laden, I2C `0x57` (Bus 1 = GPIO2/GPIO3)
- **Laufzeit:** ~2-3h unter Last (LCD + Audio + WiFi + Numpad)
- **Power-ON Signal:** PiSugar S verwendet GPIO3 als Power-ON-Trigger beim Einschalten. Dies passiert vor der Linux-Kernel-Initialisierung — kein Konflikt mit dem I2C-Display, das denselben Pin als SCL nutzt.

## USB-Detector: Permissive/Strict Mode

- **Leere Allowlist** → Permissive Mode: jede Datei mit korrektem Namen wird akzeptiert (Rueckwaertskompatibilitaet).
- **Mindestens ein Key registriert** → Strict Mode: Dateiinhalt wird gelesen, gestrippt, SHA-256-gehasht und gegen die Allowlist geprueft.
- Allowlists als `frozenset[str]` im RAM (O(1) Lookup). Kein Disk-I/O waehrend Gameplay wenn kein USB-Stick eingesteckt.
- **Hot-Reload:** Nach Key-Generierung/-Widerruf ruft der Web-Server `usb_detector.reload_allowlists()` auf. `frozenset`-Assignment ist atomar in CPython (GIL, Pi Zero Single-Core) — kein Lock noetig.
- Token-Validierung und Key-Management → siehe `docs/claude/web.md` (USB Key Security System).

## GPIO-Pinout

```
LCD I2C:     SDA=GPIO2(Pin3), SCL=GPIO3(Pin5), VCC=5V(Pin2), GND=Pin6
PiSugar S:   I2C Bus 1 (GPIO2/GPIO3) — Daemon-Kommunikation geteilt mit Display
             GPIO3 Power-ON-Signal passiert vor Linux-Boot, kein Konflikt mit I2C
Audio:       USB Lautsprecher (default) oder PWM GPIO18(Pin12) → PAM8403
Wire 1 (Defuse):  GPIO17(Pin11) + 10kOhm Pull-Down
Wire 2 (Explode): GPIO27(Pin13) + 10kOhm Pull-Down
Wire 3 (Halve):   GPIO22(Pin15) + 10kOhm Pull-Down
LED (Beep):  GPIO24(Pin18) → Vorwiderstand → LED → GND
Wire-Prinzip: Kabel steckt=HIGH(intakt), Kabel gezogen=LOW(durchtrennt)
```
