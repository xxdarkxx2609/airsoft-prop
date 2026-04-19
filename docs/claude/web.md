# Web-Interface & Netzwerk

## Architektur

Das Web-Interface (`src/web/`) laeuft als Daemon-Thread neben dem Haupt-Game-Loop auf Port 8080.

**Komponenten:**
- `server.py` -- Flask-App mit allen Routes, `WebServer`-Klasse (startet Flask in Daemon-Thread)
- `wifi_manager.py` -- WiFi-Abstraktion (`RealWifiManager` / `MockWifiManager`)
- `captive_portal.py` -- AP-Management mit hostapd/dnsmasq, Background-Monitor

**Lifecycle:**
- `WebServer` wird lazy importiert (kein Top-Level-Import in `app.py`) -- Flask nur noetig bei `web.enabled: true`
- Fehlendes Flask (z.B. Standalone-Build) -> `ImportError`-Warnung geloggt, Server uebersprungen
- `App._init_network()` vor `_init_web_server()` -- initialisiert Captive Portal, startet AP bei Bedarf, startet Background-Monitor
- `App.shutdown()` -> `captive_portal.shutdown()` vor Web-Server-Stop
- Mock-Flag aus `App._mock` steuert Mock- vs. reale Implementierungen

## Seiten & API-Endpunkte

| Seite | Funktion |
|-------|----------|
| `/wifi` | WiFi-Status, Netzwerk-Scan, Verbinden/Trennen, gespeicherte Netzwerke |
| `/config` | Spieleinstellungen (Device Name, Timer, Digits, Penalty, Volume, Backlight), Logging (Level, Max Files), Reset |
| `/tournament` | Tournament Mode Ein-/Aus, Modus-Auswahl mit dynamischen Settings, PIN-Konfiguration |
| `/usb-keys` | USB Key Management: Security-Status (Permissive/Strict), Key-Generierung, Key-Liste mit Widerruf |
| `/system` | Systeminfo (Version, CPU-Temp, RAM, Uptime, Plattform) |
| `/battery` | Batterie-Status (Ladestand-Balken, Laufzeit, Spannung, Strom, Ladestatus), Auto-Refresh 10s |
| `/logs` | Log-Viewer: Dateiauswahl, Zeilenlimit, Textfilter mit Highlighting, farbkodierte Log-Level |
| `/update` | Git-basierte Updates pruefen und installieren |

Alle Daten werden ueber `/api/*` JSON-Endpunkte geladen (vanilla JS `fetch()`).

**Wichtige API-Endpunkte:**
- `/api/wifi/ap-status` -- AP-Status (active, ssid, password, ip)
- `/api/battery` -- Batterie-Daten; `{"available": false}` wenn kein HAT
- `/api/logs` -- Log-Dateiliste, `/api/logs/<filename>` -- letzte N Zeilen (Path-Traversal-Schutz)
- `/api/usb-keys` -- Registrierte Keys, `/api/usb-keys/usb-sticks` -- Erkannte USB-Sticks
- `/api/usb-keys/generate` [POST] -- Token generieren, auf USB schreiben, Hash speichern, Allowlist hot-reloaden
- `/api/usb-keys/<key_type>/<key_id>` [DELETE] -- Key widerrufen, Allowlist hot-reloaden

## Config-Persistierung

Zweistufiges System: `config/default.yaml` (Auslieferungs-Defaults, Git-getrackt) + `custom/user.yaml` (nur User-Overrides, gitignored).

- `POST /api/config` empfaengt flaches Dict mit Punkt-separierten Keys (z.B. `{"audio.volume": 0.5}`), filtert nur Abweichungen von Defaults, schreibt nach `custom/user.yaml`
- `POST /api/config/reset` loescht `custom/user.yaml` -- **`custom/usb_keys.yaml` wird NICHT geloescht**
- `GET /api/config` liefert zusaetzlich `"customized": [...]` mit ueberschriebenen Keys
- Ladeordnung: `default.yaml` -> `custom/user.yaml` -> `hardware.yaml` -> `network.yaml`
- Migration: Beim ersten Start nach Update verschiebt `Config._load()` ggf. `config/user.yaml` und `config/usb_keys.yaml` automatisch nach `custom/` (einmalig, mit Log-Meldung)

## Cross-Thread Events

WebUI-Aenderungen werden ueber `App._event_queue` (`queue.Queue`, thread-safe) an den Main Loop kommuniziert.

**Events:** `tournament_activate`, `tournament_deactivate`, `audio_volume_changed`, `display_backlight_changed`, `logging_level_changed`

**HTTP 409:** Blockiert nur das Speichern von Tournament-Settings waehrend eines laufenden Spiels (Armed/Planting). Allgemeine Config-Aenderungen ueber `/api/config` sind immer erlaubt.

## Captive Portal

- `CaptivePortalBase` (ABC): `start_ap()`, `stop_ap()`, `is_active()`, `get_ap_info()`, `start_monitor()`, `stop_monitor()`, `shutdown()`
- `CaptivePortal` (real): Nimmt wlan0 von NetworkManager, setzt statische IP, startet hostapd+dnsmasq als Subprozesse mit Configs in `/tmp/`
- DNS-Redirect: `address=/#/<AP-IP>` in dnsmasq -- alle DNS-Anfragen zeigen auf den Pi
- Background-Monitor-Thread: prueft WiFi-Status alle 60s, startet AP automatisch bei Verbindungsverlust (thread-safe via `threading.Lock`)
- `MockCaptivePortal`: Simuliert AP-Modus ohne echte Prozesse
- System-Services via `systemctl mask` deaktiviert -- App steuert hostapd/dnsmasq direkt

**`is_wifi_connected()` ist gecacht -- kein nmcli-Aufruf:**
`is_wifi_connected()` gibt nur den gecachten `_wifi_connected: bool` zurueck (kein Subprocess, kein dbus). Der echte nmcli-Aufruf steckt in `_check_wifi_connected()` und wird nur vom Monitor-Thread (alle 60s) und einmalig im `__init__` aufgerufen. **Wichtig:** Der Cache wird im `__init__` initialisiert (`_wifi_connected = self._check_wifi_connected()`), damit `app.py` den korrekten WiFi-Zustand liest, bevor `start_monitor()` aufgerufen wird. Wer diese Initialisierung entfernt oder verschiebt, riskiert, dass das Geraet beim Start faelschlicherweise in den AP-Modus wechselt.

**Captive Portal Detection:**
- `/generate_204`, `/gen_204` -- Android: 302-Redirect auf `/wifi` wenn AP aktiv, sonst 204
- `/hotspot-detect.html` -- Apple: Redirect wenn AP aktiv, sonst "Success"-HTML
- `/connecttest.txt` -- Windows: Redirect wenn AP aktiv, sonst "Microsoft Connect Test"
- 404 Catch-All: Unbekannte URLs -> `/wifi` wenn AP aktiv

## Netzwerk-Konzept

**Default-Hotspot:** Konfiguriert in `config/network.yaml`. Pi verbindet sich automatisch. Nutzer stellt Handy-Hotspot auf gleichen Namen/Passwort. Web-Interface erreichbar unter `http://<Pi-IP>:8080`.

**Captive Portal:** Kein bekanntes WLAN gefunden -> Pi startet eigenen AP (SSID: `airsoft-prop`, PW: `defuse1337`). AP-Config in `config/network.yaml`: ssid, password, channel, ip (`192.168.4.1`), netmask, DHCP-Range.

## WiFi-Manager

- **`RealWifiManager`:** Nutzt `nmcli` (NetworkManager). Netzwerk-aendernde Befehle laufen via `sudo` (Sudoers: `/etc/sudoers.d/airsoft-prop-wifi`). `nmcli -t` Output mit Escape-aware Parser (`_parse_nmcli_terse()`). WiFi-Scan: `sudo nmcli device wifi rescan` dann `nmcli device wifi list`. API-Responses erhalten `Cache-Control: no-store`.
- **`MockWifiManager`:** Simuliert 5 Netzwerke fuer Desktop-Tests.

## USB Key Security System

**Motivation:** Ohne Validierung akzeptiert das Geraet jeden USB-Stick mit passend benannter `.KEY`-Datei.

**Token-Generierung:** Web-Interface erzeugt UUID4-Token, schreibt ihn in `.KEY`-Datei auf USB-Stick, speichert SHA-256-Hash in `custom/usb_keys.yaml`. Auf dem Pi: Direkter Filesystem-Write. Im Mock: Kein Write, Token nur in `usb_keys.yaml`.

**Validierung:** Dateiinhalt lesen -> strip -> SHA-256 -> Vergleich gegen In-Memory-Allowlist (`frozenset[str]`). Leere Allowlist = Permissive Mode (Rueckwaertskompatibilitaet). Erster registrierter Key aktiviert Strict Mode.

**Datenspeicherung (`custom/usb_keys.yaml`):** Separate Datei (nicht `user.yaml`), ueberlebt "Reset to Defaults". Getrennte Listen fuer `defuse_keys` und `tournament_keys` (je mit id, label, token_hash, created_at). Einzige Zugriffspunkte: `Config.load_usb_keys()` und `Config.save_usb_keys()`.

**Tokens werden nie im Plaintext gespeichert.** Der rohe Token erscheint einmalig in der HTTP-Response und wird nicht erneut angezeigt.

**Web-Interface `/usb-keys`:** Drei Abschnitte -- Security Status, Generate New Key (mit USB-Stick-Auswahl), Existing Keys (mit Widerrufen-Button).
