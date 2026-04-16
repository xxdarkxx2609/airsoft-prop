# Build, Deploy & Versionierung

## Standalone-Build (PyInstaller)

- Windows `.exe` via PyInstaller im `--onedir`-Modus (nicht `onefile`) -- Config-Dateien liegen editierbar neben der .exe
- `console: True` -- Terminal wird fuer das Mock-Display benoetigt
- Runtime-Hook (`build/hook-runtime-mock.py`): injiziert `--mock` in `sys.argv`
- Hidden Imports: alle Spielmodi (dynamisch importiert) + `pygame.mixer`
- Excludes: Flask, Werkzeug, Jinja2, RPi.GPIO, RPLCD, smbus2, gpiozero
- Daten: `config/*.yaml` und `assets/sounds/*.wav` werden neben die .exe kopiert (nicht in `_internal/`)
- Spec-Datei: `build/airsoft_prop.spec`

## Pfadaufloesung (`src/utils/paths.py`)

Zentrales Modul fuer die Projekt-Root-Erkennung. Alle Module nutzen `get_project_root()` statt `Path(__file__).parent.parent.parent`.

- **Source-Betrieb**: `Path(__file__).parent.parent.parent` (3 Ebenen hoch)
- **Frozen (PyInstaller)**: `Path(sys.executable).parent` (Ordner mit der .exe)
- **Nutzer**: `config.py`, `logger.py`, `audio_mock.py`, `version.py`

## GitHub Actions Workflow (`.github/workflows/build-release.yml`)

- **Trigger**: Push eines Tags `v*` (z.B. `git tag v1.0.0 && git push origin v1.0.0`)
- **Runner**: `windows-latest`, Python 3.11
- **Ablauf**: Checkout -> pip install (PyInstaller, PyYAML, pygame-ce, KEIN Flask) -> Config patchen (`web.enabled: false`) -> `VERSION`-Datei aus Tag generieren -> PyInstaller bauen -> config/, assets/ & VERSION kopieren -> ZIP erstellen -> GitHub Release mit `softprops/action-gh-release@v2`
- **Ausgabe**: `AirsoftProp-vX.X.X-windows.zip` als Release-Asset
- **VERSION-Datei**: Wird aus dem Git-Tag erzeugt (ohne `v`-Prefix) und neben die .exe gelegt -- `version.py` liest sie im Frozen Build

## Versionierung (Git-Tags)

Single Source of Truth: `git describe --tags --always`. Keine manuell gepflegte Versionsnummer.

- **Zentrales Modul**: `src/utils/version.py`
  - `get_version()` -- ermittelt die Version einmalig beim Start (gecacht)
  - `format_version_short(version)` -- kuerzt fuer 20-Zeichen-LCD (z.B. `1.0.0-3-gabcdef` -> `1.0.0+3`)
- **Aufloesungs-Reihenfolge**: 1. Frozen Build -> `VERSION`-Datei, 2. Source -> `git describe`, 3. Fallback -> `"unknown"`
- **Config-Injection**: `Config._load()` ruft `get_version()` auf und setzt `self._data["version"]`
- **Release-Workflow**: Code committen + pushen -> `git tag v1.0.1 && git push origin v1.0.1` -> Version erscheint automatisch ueberall (Boot Screen, Status Screen, Web UI, Update-Vergleich)

## Installer (`install.sh`)

- One-Click: System-Pakete (`python3-dev`, `libevdev-dev`, `hostapd`, `dnsmasq`), I2C aktivieren, Audio-Overlay, Python venv, `pip install -r requirements.txt` + `pip install -r requirements-pi.txt`
- User-Gruppen: `i2c`, `gpio`, `audio`, `input`
- Sudoers-Datei fuer passwortloses `sudo nmcli` und `sudo systemctl` (`/etc/sudoers.d/airsoft-prop-wifi`)
- systemd Service eingerichtet, hostapd/dnsmasq System-Services via `systemctl mask` deaktiviert
- Installationsverzeichnis: `/home/pi/airsoft-prop`
- **USB-Automount**: udev-Trigger (`99-airsoft-usb.rules`) + systemd-Template-Service (`usb-mount@.service`) + Mount-Helper (`/usr/local/bin/airsoft-usb-mount`). FAT/exFAT: Mount mit `uid/gid` des pi-Users. ext4: normaler Mount + `chown`.

## Update-System (`update.sh`)

- `git fetch --tags origin` -> Vergleich via `git describe --tags --always` (lokal vs. remote) -> `git pull` -> `pip install -r requirements.txt` + `pip install -r requirements-pi.txt` -> `systemctl restart`
- Aufrufbar aus dem Hauptmenue (Taste `/`) und dem Web-Interface
- Zeigt Tag-basierte Versionen an (z.B. `1.0.0 -> 1.0.1`)

## Bekannte Plattform-Hinweise

- **Python 3.13**: `distutils` wurde entfernt -- `pygame` (Original) baut nicht. Loesung: `pygame-ce>=2.5.3`
- **PyYAML**: Version 6.0.1 baut nicht from source auf Python 3.13 -- `>=6.0.1` als Pin damit pip 6.0.2+ waehlt
- **requirements.txt**: Verwendet `>=` statt `==` Pins fuer Kompatibilitaet ueber Python-Versionen hinweg
