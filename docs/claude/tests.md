# Tests — Regression Safety Net

186 Tests in `tests/`, vollstaendiger Lauf in ~1.7s. Jeder Test bewacht eine konkrete Bruchstelle — meist einen der 9 Gotchas aus [CLAUDE.md](../../CLAUDE.md#wichtige-fallstricke-gotchas), eine Mehrfach-Registrierung, oder eine cross-thread Invariante.

## Tests ausfuehren

```bash
# Volle Suite (Standard)
python -m pytest tests/

# Eine Test-Datei
python -m pytest tests/utils/test_config.py -v

# Eine Test-Klasse
python -m pytest tests/web/test_tournament_api.py::TestGameInProgressGuard -v

# Nur Sammeln (kein Run) — schnelle Discovery-Pruefung
python -m pytest tests/ --collect-only -q
```

CI laeuft auf jedem Push und PR gegen `main` mit Python 3.11 (Pi-Version) und 3.13 (Dev) -- siehe [.github/workflows/tests.yml](../../.github/workflows/tests.yml). `fetch-depth: 0` ist erforderlich, damit `git describe` fuer die Version-Tests funktioniert.

## Layout

`tests/` spiegelt `src/`:

| Test-Verzeichnis | Was wird getestet | Anzahl |
|------------------|-------------------|--------|
| [tests/utils/](../../tests/utils/) | Config-Loader, Logger | 17 |
| [tests/hal/](../../tests/hal/) | HAL-Basisklassen + alle Mock-Implementierungen | 37 |
| [tests/modes/](../../tests/modes/) | Spielmodi (alle 6 + Discovery) | 43 |
| [tests/app/](../../tests/app/) | App, State-Machine, Event-Queue, Shutdown | 21 |
| [tests/ui/](../../tests/ui/) | Screens, Screen-Manager, LCD-Helpers | 28 |
| [tests/web/](../../tests/web/) | Flask-API, Auth, Captive Portal | 25 |
| [tests/spec/](../../tests/spec/) | PyInstaller-Spec Konsistenz | 2 |
| [tests/test_version.py](../../tests/test_version.py) | Versions-String-Parsing (vorhanden seit langem) | 13 |

**Hinweis:** Verzeichnis heisst `tests/spec/`, nicht `tests/build/` -- pytest skippt standardmaessig jedes Verzeichnis namens `build` (norecursedirs).

## Gotcha-Abdeckung

| # | Gotcha | Test-Datei |
|---|--------|------------|
| 1 | pygame-ce, nicht pygame | implizit (jeder HAL-Test importiert ueber `audio_mock`) |
| 2 | Sound-Doppelregistrierung in `default.yaml` UND `audio_mock.py` | [tests/hal/test_audio_mock.py](../../tests/hal/test_audio_mock.py) `TestSoundRegistrationParity` |
| 3 | Mode-Doppelregistrierung in `_KNOWN_MODES` UND `airsoft_prop.spec` | [tests/modes/test_mode_discovery.py](../../tests/modes/test_mode_discovery.py) + [tests/spec/test_spec_consistency.py](../../tests/spec/test_spec_consistency.py) |
| 4 | `device_name` > 7 Zeichen | [tests/utils/test_config.py](../../tests/utils/test_config.py) (Layer 1: Config-Truncation) + [tests/web/test_config_api.py](../../tests/web/test_config_api.py) (Layer 2: API-Validierung → 400) |
| 5 | `reset_user_config` darf `usb_keys.yaml` nicht loeschen | [tests/utils/test_config.py](../../tests/utils/test_config.py) + [tests/web/test_config_api.py](../../tests/web/test_config_api.py) |
| 6 | Main-Loop 10-Errors-Shutdown | [tests/app/test_main_loop.py](../../tests/app/test_main_loop.py) |
| 7 | Kein subprocess/nmcli in `render()` | implizit ueber [tests/web/test_captive_portal.py](../../tests/web/test_captive_portal.py) (Cache-Test zaehlt subprocess-Aufrufe) |
| 8 | `CaptivePortal._wifi_connected` Cache-Primer im `__init__` | [tests/web/test_captive_portal.py](../../tests/web/test_captive_portal.py) `TestWifiConnectionCachePriming` |
| 9 | Graceful Shutdown (SIGTERM, < 5s) | [tests/app/test_shutdown.py](../../tests/app/test_shutdown.py) (HAL-Teardown isoliert pro Komponente) |

## Wann welche Tests laufen lassen

**Beim Aendern von...**

| Aenderung | Mindestens diese Tests | Vor Commit auch |
|-----------|------------------------|-----------------|
| Spielmodus (`src/modes/*.py`) | `tests/modes/test_<mode>.py` + `test_mode_discovery.py` | volle Suite |
| Neuer Sound (`config/default.yaml`) | `tests/hal/test_audio_mock.py` (faengt fehlende Mock-Eintrag) | -- |
| HAL-Basisklasse (`src/hal/base.py`) | `tests/hal/test_base_contracts.py` (faengt fehlende Mock-Methode) | volle Suite |
| Web-API (`src/web/server.py`) | `tests/web/*` | volle Suite |
| Config-Schema (`config/default.yaml`) | `tests/utils/test_config.py` + `tests/web/test_config_api.py` | volle Suite |
| State-Machine (`src/app.py`) | `tests/app/*` | volle Suite |
| Screen (`src/ui/*.py`) | `tests/ui/*` (insbesondere `test_tournament_screen.py` bei Tournament-Logik) | volle Suite |
| PyInstaller-Spec (`build/airsoft_prop.spec`) | `tests/spec/test_spec_consistency.py` | -- |

**Vor jedem PR gegen `main`:**

```bash
python -m pytest tests/
```

CI laeuft automatisch und blockiert Merges bei Test-Fehlern.

## Fixtures (zentrale Test-Hilfen)

Definiert in [tests/conftest.py](../../tests/conftest.py), sichtbar in allen Test-Dateien:

| Fixture | Was sie liefert | Wann verwenden |
|---------|-----------------|----------------|
| `tmp_project_root` | Temp-Verzeichnis mit `config/` + `custom/`, Config-Modul ist umgebogen | Config-Schreib/Lese-Tests die `custom/user.yaml` o.ae. anlegen |
| `mock_config` | Frische `Config()` aus `tmp_project_root` | Reine Config-Reads |
| `mock_app` | `App(mock=True)` mit allen HAL-Slots an Mocks gebunden, **ohne** `init()` (kein Daemon-Thread, kein Web-Server) | App-State-Tests, Event-Queue-Tests, UI-Tests die `app.config`/`app.usb_detector` brauchen |
| `web_client` | Flask `test_client()` verdrahtet mit `mock_app`, `mock_app.modes` ist via `discover_modes()` befuellt | Alle Tests gegen die HTTP-API |

## Patterns

### Mock-HAL nutzen statt echte Hardware mocken
Tests duerfen `RPi.GPIO`, `RPLCD`, `smbus2`, `gpiozero` nicht importieren -- die Mock-HAL-Klassen sind das Test-Doublé. Beispiel:

```python
from src.hal.wires_mock import MockWires

def test_my_thing():
    wires = MockWires()
    wires.init()
    wires.cut_wire("Green")
    assert not wires.all_wires_intact()
```

### Cross-Thread-Events testen
`mock_app` hat eine reale `_event_queue`. Events einreihen, dann `_process_events()` aufrufen, dann auf Seiteneffekte pruefen:

```python
mock_app.post_event({"type": "audio_volume_changed", "value": 0.42})
mock_app._process_events()
assert mock_app.audio._volume == 0.42
```

### Zeit kontrollieren
Fuer zeitabhaengige Logik (Tournament 5x-Backspace, Penalty-Flash) `time.time` im jeweiligen Modul monkeypatchen, nicht global:

```python
monkeypatch.setattr("src.ui.tournament_screen.time.time", lambda: 100.0)
```

Globales `time.sleep` NICHT patchen -- der Test selbst braucht es. Stattdessen `_LOOP_INTERVAL` patchen wenn der Main-Loop schnell laufen soll.

### `print()` in `src/` ist verboten
[tests/utils/test_logger.py](../../tests/utils/test_logger.py) `TestNoPrintInSrc` scannt `src/` per AST und faellt aus, wenn irgendwo `print(...)` auftaucht. Stattdessen `get_logger(__name__)`.

## Neue Tests schreiben

1. **Datei in `tests/<bereich>/test_<thema>.py`** -- spiegelt `src/`. `__init__.py` ist im Subverzeichnis erforderlich.
2. **Test-Klassen mit `class TestSomething:` gruppieren** -- existing pattern aus [tests/test_version.py](../../tests/test_version.py).
3. **Google-Style Docstring** an der Test-Klasse, der erklaert warum der Test existiert (welcher Gotcha, welche Bruchstelle).
4. **Fail-Message ist Pflicht bei nicht-trivialen Asserts**: `assert ..., "Erklaer warum das wichtig ist"`. Der naechste Maintainer bei rotem CI dankt dir.
5. **Tests muessen auf Linux UND Windows laufen** -- keine `\\`-Pfade, keine `msvcrt`-Imports. CI laeuft Ubuntu.

## Was bewusst NICHT getestet wird

- Echte Hardware (kein Pi im CI)
- pygame Display-Rendering Pixel-Vergleiche (zu fragil)
- WiFi `nmcli` Integration (gemockt am Boundary)
- PiSugar TCP-Daemon (gemockt)
- Stress / Performance
- Coverage-Quoten

Tritt eine Regression in einem dieser Bereiche auf, einen gezielten Test fuer den konkreten Fall hinzufuegen -- die Suite nicht praeventiv aufblaehen.
