# Web-Interface & Netzwerk

## Architektur

Das Web-Interface (`src/web/`) laeuft als Daemon-Thread neben dem Haupt-Game-Loop auf Port 8080.

**Komponenten:**
- `server.py` — Flask-App mit allen Routes und `WebServer`-Klasse (startet Flask in Daemon-Thread)
- `wifi_manager.py` — WiFi-Abstraktion (`RealWifiManager` / `MockWifiManager`)
- `captive_portal.py` — AP-Management mit hostapd/dnsmasq, Background-Monitor
- `static/style.css` — Einzige CSS-Datei (kein Framework, Custom Properties + Flexbox + Grid)
- `static/app.js` — Geteilte Helpers (API-Wrapper, Theme, Sidebar, Steppers, WiFi-Chip)
- `static/pages/*.js` — Page-spezifisches JS, je eine Datei pro Seite

**Lifecycle:**
- `WebServer` wird lazy importiert — Flask nur noetig bei `web.enabled: true`
- Fehlendes Flask → `ImportError`-Warnung geloggt, Server uebersprungen
- `App._init_network()` vor `_init_web_server()` — initialisiert Captive Portal, startet AP bei Bedarf
- `App.shutdown()` → `captive_portal.shutdown()` vor Web-Server-Stop
- Mock-Flag aus `App._mock` steuert Mock- vs. reale Implementierungen

## Seiten & Routen

### HTML-Seiten (require_auth_page)

| Route | Template | Funktion |
|-------|----------|----------|
| `GET /` | `dashboard.html` | Haupt-Dashboard: Spielzustand, Stats, Recent Events, Quick Links |
| `GET /config` | `config.html` | Spieleinstellungen, Branding, Custom Sounds |
| `GET /tournament` | `tournament.html` | Tournament Mode Ein/Aus, Modus, PIN |
| `GET /wifi` | `wifi.html` | WiFi-Status, Scan, Verbinden, Gespeicherte Netze |
| `GET /security` | `security.html` | Passwort setzen/aendern/entfernen |
| `GET /system` | `system.html` | Systeminfo, Hardware-Module (HAL), Service/Reboot/Shutdown |
| `GET /battery` | `battery.html` | Batterie-Status mit Segmentbalken und Sparkline |
| `GET /logs` | `logs.html` | Log-Viewer mit Filter, Level-Auswahl, Download |
| `GET /update` | `update.html` | Git-Updates pruefen und installieren |
| `GET /hardware` | `hardware.html` | HAL-Modul-Auswahl pro Komponente |
| `GET /usb-keys` | `usb_keys.html` | USB Key Management, Strict/Permissive Mode |
| `GET /sounds` | `sounds.html` | Dedizierte Custom-Sounds-Seite |

### Auth-Routen

| Route | Methode | Funktion |
|-------|---------|----------|
| `/login` | GET | Login-Formular |
| `/login` | POST | Passwort pruefen, Session setzen, Redirect zu `next` |
| `/logout` | POST | Session leeren |

### API-Endpunkte (require_auth_api, ausser `/api/branding/logo`)

**Auth & Security:**
- `POST /api/security/password` — Passwort setzen/aendern (aktuelles PW + neues PW + Bestaetigung)
- `DELETE /api/security/password` — Passwort entfernen (aktuelles PW erforderlich, Session wird geloescht)

**Branding:**
- `GET /api/branding` — Aktuelles Branding (team_name, logo_url, has_logo)
- `POST /api/branding` — Team-Name und Logo hochladen (multipart, PNG/JPEG/WebP, max 512 KB)
- `DELETE /api/branding/logo` — Logo loeschen, Team-Name bleibt
- `GET /api/branding/logo` — Logo-Datei ausliefern (**kein Auth** — Login-Seite braucht es)

**Spielzustand:**
- `GET /api/game-state` — Aktueller Spielzustand-Snapshot fuer Dashboard (state, armed, recent_events)

**WiFi:**
- `GET /api/wifi/status` — Status (connected, ssid, ip_address, mac, signal, mode)
- `GET /api/wifi/scan` — Netzwerk-Scan
- `POST /api/wifi/connect` — Mit Netzwerk verbinden
- `POST /api/wifi/disconnect` — Verbindung trennen
- `GET /api/wifi/saved` — Gespeicherte Netzwerke
- `POST /api/wifi/forget` — Netzwerk vergessen
- `GET /api/wifi/ap-status` — AP-Status (active, ssid, password, ip)
- `GET/POST /api/wifi/force-ap` — Force-AP-Modus lesen/setzen

**Config:**
- `GET /api/config` — Aktuelle Konfiguration + `"customized": [...]` (ueberschriebene Keys)
- `POST /api/config` — Flaches Dict mit Punkt-Keys (`{"audio.volume": 0.5}`), nur Abweichungen werden gespeichert
- `POST /api/config/reset` — `custom/user.yaml` loeschen (USB-Keys bleiben erhalten)

**Tournament:**
- `GET /api/tournament` — Tournament-Config + verfuegbare Modi
- `POST /api/tournament` — Tournament-Einstellungen speichern (blockiert HTTP 409 waehrend laufendem Spiel)

**System:**
- `GET /api/system` — Plattform, Python-Version, Hostname, CPU-Temp, Uptime, RAM
- `GET /api/battery` — Batterie-Daten; `{"available": false}` wenn kein HAT
- `GET /api/hardware` — Aktuelle HAL-Auswahl + verfuegbare Module
- `POST /api/hardware` — HAL-Modul-Auswahl speichern

**Logs:**
- `GET /api/logs` — Liste der Log-Dateien
- `GET /api/logs/<filename>` — Letzte N Zeilen (Path-Traversal-Schutz)

**Update:**
- `GET /api/update/check` — `git fetch --tags`, Commits seit origin/main, neuestes Git-Tag als `latest_version`
- `POST /api/update/install` — `git pull` + `pip install -r requirements.txt`

**Custom Sounds:**
- `GET /api/sounds` — Liste: `{filename, size, overrides_default}` aus `custom/sounds/`
- `POST /api/sounds/upload` — WAV-Upload (RIFF-Header-Pruefung, kein Path-Traversal)
- `DELETE /api/sounds/<filename>` — Sound loeschen
- `GET /api/sounds/preview/<filename>` — Sound fuer Browser-Playback ausliefern

**Service-Steuerung:**
- `POST /api/service/restart` — Systemd-Service-Restart mit PID-Verifikation
- `POST /api/system/reboot` — Host-Neustart via `sudo reboot`
- `POST /api/system/shutdown` — Host-Shutdown via `sudo shutdown -h now`

**USB Keys:**
- `GET /api/usb-keys` — Registrierte Keys + Security-Status
- `GET /api/usb-keys/usb-sticks` — Gemountete USB-Sticks
- `POST /api/usb-keys/generate` — Token erzeugen, auf USB schreiben, Hash speichern
- `DELETE /api/usb-keys/<key_type>/<key_id>` — Key widerrufen, Allowlist hot-reloaden

**Captive Portal Detection (kein Auth):**
- `/generate_204`, `/gen_204` — Android
- `/hotspot-detect.html` — Apple
- `/connecttest.txt` — Windows
- 404-Catch-All → `/wifi` wenn AP aktiv

## Dashboard

**Stat-Grid** (4 Panels, unabhaengig gepolllt):
- **Power** — Batterie-Level, Ladebalken (32 Segmente), Ladestatus (10s-Polling)
- **Network** — SSID, IP-Adresse (15s-Polling via `/api/wifi/status`)
- **System** — Version, Uptime, Plattform (30s-Polling via `/api/system`)
- **Game State** — Zustand-Badge, Device-Name (2s-Polling via `/api/game-state`)

**Armed Strip** — nur sichtbar wenn `state == "armed"`:
- Modusname, Countdown-Timer (500ms-Update), Progress-Bar
- Verbleibende Zeit = `remainingAtSnapshot - (now - snapshotTs)`

**Recent Events** — Ring-Buffer, maxlen=20, aelteste Eintraege fallen heraus:

| Event-Typ | Meldung | Badge-Farbe | Ausloese |
|-----------|---------|-------------|----------|
| `boot` | "System started" | info | App-Start |
| `armed` | "Round armed · {mode}" | warning | Spiel beginnt |
| `defused` | "Defused with {m}:{s:02d} remaining" | success | Entschaerft |
| `detonated` | "Timer expired" | danger | Zeit abgelaufen |
| `tournament_on` | "Tournament mode activated" | info | Tournament Ein |
| `tournament_off` | "Tournament mode deactivated" | info | Tournament Aus |
| `info` | "Config saved via web" | default | Config gespeichert |
| `info` | "Service restart initiated" | default | Service-Restart |

`_append_recent_event(type, message)` in `app.py` — Thread-sicher via `_state_lock`.

**Quick Links** — 4 Buttons im 2-spaltigen Grid: Tournament, Config, USB Keys, Logs.

## Authentifizierung

- Session-Lifetime: 8 Stunden; Secret Key in `custom/secret_key` (auto-generiert)
- Cookie-Flags: HttpOnly, SameSite=Lax
- `_password_set()` prueft ob Hash in Web-Config vorhanden
- **Kein Passwort gesetzt** → Auth wird uebersprungen, aber Warning-Banner auf allen Seiten
- Passwort-Hashing via `werkzeug.security` (check/generate_password_hash)
- Context Processor injiziert `is_authenticated`, `password_set`, `no_password_warning` in jedes Template

## Branding-System

Logo und Team-Name werden in alle Templates injiziert:
- **Sidebar** (`base.html`): Logo oder Default-Crosshair-SVG + Team-Name
- **Login-Seite** (`login.html`): Logo + Team-Name
- **Context-Variablen:** `branding.team_name`, `branding.logo_url`, `branding.has_logo`

Logo-Validierung: Magic-Bytes-Erkennung (PNG `89 50 4E 47`, JPEG `FF D8 FF`, WebP `RIFF…WEBP`), max 512 KB. Kein SVG. Gespeichert in `custom/branding/logo.{ext}`.

`GET /api/branding/logo` ist **bewusst ohne Auth** — Login-Seite braucht das Logo vor dem Einloggen.

## Sidebar

- Zeigt aktuelle IP-Adresse einmalig beim Seitenload via `initSidebarInfo()` (holt `/api/wifi/status`)
- Kein Live-Uptime-Ticker (CPU-Last auf Pi Zero vermeiden)
- Burger-Button (Mobile): klappt Sidebar als Drawer auf

## Config-Persistierung

Zweistufig: `config/default.yaml` (Git-getrackt) + `custom/user.yaml` (nur Overrides, gitignored).

- `POST /api/config` filtert Abweichungen von Defaults, schreibt nach `custom/user.yaml`
- `POST /api/config/reset` loescht `custom/user.yaml` — **`custom/usb_keys.yaml` bleibt erhalten**
- `GET /api/config` liefert zusaetzlich `"customized": [...]` — UI markiert ueberschriebene Keys mit `*`
- Ladeordnung: `default.yaml` → `custom/user.yaml` → `hardware.yaml` → `network.yaml`
- Runtime-aenderbare Einstellungen (Volume, Backlight, Log-Level) werden sofort per Cross-Thread-Event angewendet

## Cross-Thread Events

WebUI-Aenderungen → `App._event_queue` (`queue.Queue`, thread-safe) → Main Loop.

**Events:** `tournament_activate`, `tournament_deactivate`, `audio_volume_changed`, `display_backlight_changed`, `logging_level_changed`

**HTTP 409:** Blockiert nur das Speichern von Tournament-Settings waehrend eines laufenden Spiels. Allgemeine Config-Aenderungen immer erlaubt.

## Custom Sounds

Hochgeladene WAV-Dateien in `custom/sounds/`. Validierung: `.wav`-Erweiterung + RIFF-Header-Pruefung. Kein Path-Traversal (`..` verboten). Ueberschreiben eines Default-Sounds wird per `overrides_default`-Flag angezeigt.

**Wichtig:** Neue Sounds an **zwei** Stellen registrieren:
1. `config/default.yaml` → `audio.sounds`
2. `src/hal/audio_mock.py` → `MockAudio.init()` → `self._sounds`

## Update-System

`GET /api/update/check`:
1. `git fetch --tags` (mit Tag-Fetch)
2. `git log HEAD..origin/main` — zaehlt ausstehende Commits
3. `git describe --tags --abbrev=0 origin/main` — neuestes Tag als `latest_version` (None wenn keine Tags)

Mock-Modus gibt statische Dummy-Daten (`latest_version: "1.1.0"`) zurueck.

## Captive Portal

- `CaptivePortalBase` (ABC): `start_ap()`, `stop_ap()`, `is_active()`, `get_ap_info()`, `start_monitor()`, `shutdown()`
- `CaptivePortal` (real): Nimmt wlan0 von NetworkManager, setzt statische IP, startet hostapd+dnsmasq mit Configs in `/tmp/`
- DNS-Redirect: `address=/#/<AP-IP>` in dnsmasq — alle Anfragen zeigen auf den Pi
- Background-Monitor-Thread: prueft WiFi alle 60s, startet AP bei Verbindungsverlust (thread-safe via `threading.Lock`)
- `MockCaptivePortal`: Simuliert AP ohne echte Prozesse

**`is_wifi_connected()` ist gecacht:**
Gibt nur `_wifi_connected: bool` zurueck (kein Subprocess). Echter nmcli-Aufruf nur im Monitor-Thread (60s) und einmalig im `__init__`. **Nicht entfernen** — fehlt die `__init__`-Initialisierung, startet das Geraet faelschlicherweise im AP-Modus.

## Netzwerk-Konzept

**Default-Hotspot:** In `config/network.yaml` konfiguriert. Nutzer stellt Handy-Hotspot auf gleichen Namen/Passwort. Web-Interface erreichbar unter `http://<Pi-IP>:8080`.

**Captive Portal:** Kein bekanntes WLAN → Pi startet eigenen AP. AP-Config in `config/network.yaml`: ssid, password, channel, ip (`192.168.4.1`), netmask, DHCP-Range.

## WiFi-Manager

- **`RealWifiManager`:** nmcli (NetworkManager). Netzwerk-aendernde Befehle via `sudo` (Sudoers: `/etc/sudoers.d/airsoft-prop-wifi`). `nmcli -t` Output mit Escape-aware Parser `_parse_nmcli_terse()`.
- **`MockWifiManager`:** Simuliert 5 Netzwerke fuer Desktop-Tests.

## USB Key Security System

**Motivation:** Ohne Validierung akzeptiert das Geraet jeden USB-Stick mit passend benannter `.KEY`-Datei.

**Token-Generierung:** UUID4-Token → `.KEY`-Datei auf USB schreiben → SHA-256-Hash in `custom/usb_keys.yaml`. Im Mock: kein USB-Write, nur Hash-Speicherung.

**Validierung:** Dateiinhalt lesen → strip → SHA-256 → Vergleich gegen In-Memory-Allowlist (`frozenset[str]`). Leere Allowlist = Permissive Mode. Erster registrierter Key aktiviert Strict Mode.

**`custom/usb_keys.yaml`:** Ueberlebt "Reset to Defaults". Getrennte Listen: `defuse_keys` und `tournament_keys` (je mit id, label, token_hash, created_at). Nur via `Config.load_usb_keys()` / `Config.save_usb_keys()` zugreifen.

**Tokens werden nie im Plaintext gespeichert.** Der rohe Token erscheint einmalig in der HTTP-Response und wird nicht erneut angezeigt.

## CSS-Konventionen

Kein CSS-Framework. CSS Custom Properties fuer Theming (Dark default, Light optional). Wichtige Klassen:

| Klasse | Verwendung |
|--------|-----------|
| `.panel` | Content-Container mit Eck-Klammern, hover-Effekt |
| `.btn` / `.btn-secondary` / `.btn-danger` / `.btn-small` | Button-Varianten |
| `.panel-actions` | Flex-Row mit `gap:8px` fuer Buttons |
| `.panel-actions-spread` | Wie panel-actions, aber `justify-content: space-between` |
| `.shortcut-grid` | 2-spaltiges Grid fuer Dashboard-Quick-Links |
| `.shortcut-btn` | Quick-Link-Button (zentriert, mit Icon) |
| `.file-input-row` | Flex-Row fuer versteckte File-Inputs + Label-Button + Filename-Anzeige |
| `.file-chosen` | Dateiname-Anzeige neben File-Select-Button |
| `.login-logo` | Team-Logo auf Login-Seite (max 200×120 px, object-fit: contain) |
| `.logo-preview` | Team-Logo-Vorschau auf Config-Seite (max 200×120 px) |
| `.segbar` | 32-Segment Batterie-Balken |
| `.stepper` | Zahl-Input mit +/- Buttons |
| `.chip` | Kleiner Status-Indikator (z.B. Spielzustand-Badge) |

**File-Inputs:** Native `<input type="file">` ist immer `style="display:none"`. Sichtbar als `<label for="...">` mit `.btn`-Klasse. Filename-Anzeige per JS in `.file-chosen`-Span.
