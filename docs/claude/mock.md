# Mock-Modus

## Start

```bash
python -m src.main --mock
```

Startet die Anwendung auf jedem Desktop ohne Raspberry Pi Hardware.

## Mock-Implementierungen

### Display (`MockDisplay` -- `src/hal/display_mock.py`)
Rendert einen 20x4 ASCII-Rahmen im Terminal via ANSI Escape Codes (in-place, kein Scrollen). `write_line()` schreibt nur in den Buffer, `flush()` rendert einmal pro Frame. Nutzt Snapshot-Vergleich -- nur bei Aenderungen wird neu gezeichnet.

### Audio (`MockAudio` -- `src/hal/audio_mock.py`)
Spielt WAV-Dateien ueber `pygame-ce` ab. Fehlende Dateien oder fehlendes pygame fuehren zu einem stillen Fallback, kein Crash. **Wichtig:** Es muss `pygame-ce` verwendet werden, NICHT das alte `pygame` (funktioniert nicht mit Python 3.13+ wegen entferntem `distutils`).

### Input (`MockInput` -- `src/hal/input_mock.py`)
Liest Tastatureingaben ueber einen Background-Thread. Windows: `msvcrt`, Unix: `termios` Raw-Mode. Taste `.` toggelt den Mock-USB-Key.

### USB-Detector (`MockUsbDetector` -- `src/hal/usb_detector_mock.py`)
Simuliert USB-Stick Einstecken/Entfernen. Toggle ueber `.`-Taste oder direkt ueber `toggle()`-Methode. Unterstuetzt Token-Validierung fuer Tests: `set_valid_defuse_token(token)` registriert ein Token, sodass `is_key_present()` im Strict Mode `True` zurueckgibt. `reload_allowlists()` wird vom Web-Server nach Key-Aenderungen aufgerufen.

### Battery (`MockBattery` -- `src/hal/battery_mock.py`)
Simuliert eine sich entladende Batterie (startet bei 85%, entlaedt ~0.05%/s). Zeigt simulierte Werte auf dem Status Screen und im Web-Interface.

### LED (`MockLed` -- `src/hal/led_mock.py`)
Loggt `blink_once()` und `set_enabled()` Aufrufe auf DEBUG-Level. Kein Hardware-Zugriff.

### Captive Portal (`MockCaptivePortal` -- `src/web/captive_portal.py`)
Simuliert den AP-Modus ohne echte Prozesse. `is_wifi_connected()` gibt `True` zurueck (kein AP noetig im Mock). Der Monitor-Thread ist ein No-Op.

### WiFi (`MockWifiManager` -- `src/web/wifi_manager.py`)
Simuliert 5 Netzwerke (AirsoftProp, HomeNetwork etc.) mit In-Memory Connect/Disconnect.

## Web-Interface im Mock

- Startet automatisch auf `http://localhost:8080`
- WiFi-Seite zeigt simulierte Netzwerke
- Einstellungen werden in `custom/user.yaml` gespeichert (nur Abweichungen von Defaults)
- Update-Seite zeigt ein simuliertes Update
- Log-Viewer zeigt echte Logfiles
- Battery-Seite zeigt MockBattery-Werte

## Logging im Mock

- Logs gehen immer nach `logs/prop.log` (sowohl Mock als auch Pi), damit das Terminal-Display sauber bleibt
- Pro Session wird ein neues Logfile erstellt, alte werden automatisch archiviert und bereinigt
- `--no-log-file` schaltet File-Logging ab (nur stderr)
- `--debug` erzwingt DEBUG-Level unabhaengig von der YAML-Konfiguration
