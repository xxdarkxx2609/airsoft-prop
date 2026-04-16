# Spielmodi & Plugin-System

## Plugin-System

Jeder Spielmodus ist eine eigene Datei in `src/modes/` und erbt von `BaseMode` (`src/modes/base_mode.py`). Modi werden beim Start automatisch entdeckt (Auto-Discovery via `pkgutil.iter_modules`). Ein neuer Modus = eine neue Datei, keine weiteren Aenderungen noetig. Nutzer koennen eigene Modi in `custom/modes/` ablegen -- diese werden ebenfalls automatisch entdeckt.

**Frozen-Build-Fallback:** In PyInstaller-Builds kann `pkgutil` das Dateisystem nicht scannen. Dann greift eine explizite Modulliste `_KNOWN_MODES` in `src/modes/__init__.py`. Bei neuen Modi muss diese Liste sowie `hiddenimports` in `build/airsoft_prop.spec` aktualisiert werden.

## Planting-System

Drei Typen: INSTANT (kein Planting-Screen), CODE_ENTRY (Spieler gibt Code ein), TIMED (Spieler haelt Enter). Die Definitionen befinden sich in `src/modes/base_mode.py` (`PlantingType`, `PlantingConfig`). Modi definieren ihre Planting-Mechanik ueber `get_planting_config()`.

`HOLD_TIMEOUT = 0.6s` -- Toleranz fuer Key-Hold-Erkennung. Wenn >600ms kein Enter-Event kommt, gilt die Taste als losgelassen (OS Key-Repeat-Delay ist ~500ms).

**Zuordnung der Modi:**

| Modus            | Planting-Typ | Details                                          |
|------------------|--------------|--------------------------------------------------|
| Random Code      | CODE_ENTRY   | code_length=0 (nutzt den generierten Spielcode)  |
| Set Code         | CODE_ENTRY   | code_length=10 (separater Aktivierungscode)      |
| USB Key Cracker  | TIMED        | duration=10 (10s Enter halten)                   |
| INSTANT-Modi     | INSTANT      | Ueberspringen die Planting-Phase komplett         |

## Plus-Modi Penalty-System

Die "+" Varianten (Random Code+, Set Code+) nutzen `context.custom_data["penalty_seconds"]` (gesetzt von `setup_screen.py` aus Config) und signalisieren Fehler ueber `context.custom_data["penalty_triggered"]` an `armed_screen.py`, das den Sound abspielt. So bleiben Modi vom Audio-HAL entkoppelt.

## Spielmodi-Spezifikationen

### Random Code (`src/modes/random_code.py`)

- **Setup:** Timer (00:30--99:59, Schritte 30s, +/- 5min), Digits (4--20)
- **Planting:** CODE_ENTRY -- Spieler muss den generierten Spielcode eintippen um zu planten
- **Armed:** Zufaelliger Zahlencode wird angezeigt, Spieler muss identischen Code eintippen
- **Defuse:** Code vollstaendig korrekt eingegeben
- **Eingabe:** Backspace loescht letzte Ziffer, falsche Komplettierung -> Eingabe loeschen und neu

### Set Code (`src/modes/set_code.py`)

- **Setup:** Timer (00:30--99:59), Code (1--10 Ziffern, manuell eingeben)
- **Planting:** CODE_ENTRY -- separater 10-Ziffern Zufalls-Aktivierungscode (NICHT der Geraete-Code)
- **Armed:** Code wird NICHT angezeigt, Spieler muss ihn anderweitig herausfinden
- **Defuse:** Korrekter Code eingegeben
- **Eingabe:** Backspace loescht letzte Ziffer, falsche Komplettierung -> Eingabe loeschen und neu

### Random Code+ (`src/modes/random_code_plus.py`)

- Basiert auf Random Code, erbt von `RandomCodeMode`
- **Setup:** Timer (00:30--99:59), Digits (4--20) -- identisch zu Random Code
- **Planting:** CODE_ENTRY -- wie Random Code
- **Armed:** Zufaelliger Zahlencode angezeigt, **jede Ziffer wird sofort geprueft**
  - Korrekte Ziffer: bleibt stehen, naechste Position
  - Falsche Ziffer: wird verworfen, Zeitstrafe abgezogen (default 10s, konfigurierbar)
  - Visuelles Feedback: "WRONG! -Xs" wird ~0.7s auf der Eingabezeile angezeigt
  - Audio: `wrong.wav` wird bei Fehler abgespielt
  - Kein Backspace -- Ziffern werden sofort validiert
- **Config:** `game.penalty_seconds` (geteilt mit Set Code+, im Web-Interface konfigurierbar)

### Set Code+ (`src/modes/set_code_plus.py`)

- Basiert auf Set Code, erbt von `SetCodeMode`
- **Setup:** Timer (00:30--99:59), Code (1--10 Ziffern) -- identisch zu Set Code
- **Planting:** CODE_ENTRY -- separater 10-Ziffern Aktivierungscode (wie Set Code)
- **Armed:** Code wird NICHT angezeigt, **jede Ziffer wird sofort geprueft**
  - Korrekte Ziffer: als `*` angezeigt (Code bleibt verborgen)
  - Falsche Ziffer: wird verworfen, gleiche Zeitstrafe wie Random Code+
  - Anzeige: `> ***___` (3 von 6 Ziffern korrekt)
  - Kein Backspace

### USB Key Cracker (`src/modes/usb_key_cracker.py`)

- **Setup:** Timer (00:30--99:59), Digits (4--12, bestimmt Cracking-Dauer)
- **Planting:** TIMED -- Enter 10 Sekunden halten (loslassen = Abbruch)
- **Armed:** Zeigt `Insert USB Key...`, wartet auf USB-Stick mit `DEFUSE.KEY`
- **Defuse:** USB-Stick einstecken -> Cracking-Animation startet
  - Dauer: `digits * 2.5s` (z.B. 8 Ziffern = 20s)
  - Alle ~2.5s wird eine Ziffer in zufaelliger Reihenfolge "geknackt"
  - Ungeknackte Ziffern: schnelles Cycling (0-9 zufaellig, jeder Render-Frame)
  - Geknackte Ziffer: bleibt auf korrektem Wert stehen
  - USB-Stick ziehen -> Cracking abgebrochen, Fortschritt verloren
  - Alle Ziffern geknackt -> DEFUSED
- **HAL:** `UsbDetectorBase` -- pollt `DEFUSE.KEY` auf gemounteten USB-Medien, validiert Inhalt gegen Allowlist
- **Mock:** `.`-Taste togglet USB-Einstecken/Entfernen

### Cut the Wire (Draft)

- **Status:** In Ueberarbeitung, nicht aktiv im Menue
- Liegt in `src/modes/_drafts/` (wird von Auto-Discovery ignoriert)
- **Setup:** Timer, Wire-Check (alle 3 Kabel muessen stecken vor Start)
- **Armed:** 3 farbige Kabel (R=Rot, B=Blau, G=Gruen), Rollen zufaellig zugewiesen
  - 1 Wire = Defuse (Geraet entschaerft)
  - 1 Wire = Explode (sofortige Detonation)
  - 1 Wire = Halve (restliche Zeit halbiert)

## Config-Defaults fuer Setup-Optionen

Die Modi haben hardcoded Defaults (z.B. `default=300` fuer Timer). `SetupScreen._apply_config_defaults()` ueberschreibt diese nach `get_setup_options()` mit Werten aus der Config (`game.default_timer`, `modes.random_code.default_digits` etc.). Im Tournament Mode werden stattdessen die `tournament.settings.*` Werte verwendet.
