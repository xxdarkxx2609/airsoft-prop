# Display-Referenz -- LCD UI Design & Screen-Layouts

20x4 HD44780 LCD mit I2C (PCF8574). Custom Characters (8 Slots): WiFi-Icons, Batterie, Cursor, Rahmenelemente, Lock.

## Designregeln

- **Im Spiel:** Alle 4 Zeilen fuer Gameplay -- keine System-Info.
- **Im Menue:** Zeile 4 fixiert -- Shortcuts (`*`=Status, `/`=Update) + WiFi-Icon rechts.
- **Status-Info:** Eigener Screen -- Taste `*`, mehrseitig, Enter=weiter, `<-`=zurueck.
- **Modusliste scrollbar:** Bei >3 Modi scrollt die Liste, Zeile 4 bleibt fixiert.

## Performance-Regeln fuer render()

`render()` wird vom Main-Loop mit 5 Hz aufgerufen (alle 200ms). Auf dem Pi Zero bedeutet jeder Subprocess-Spawn oder Netzwerkaufruf in `render()` mehrere hundert Millisekunden CPU-Last und kann `dbus-daemon` belasten.

**Verboten in render():**
- `subprocess.run()` / `subprocess.Popen()` -- auch `iwgetid`, `nmcli` etc.
- Socket-Verbindungen oder HTTP-Requests
- Direkte HAL-Methoden, die intern nmcli aufrufen (z.B. `portal.is_wifi_connected()` -- **war früher ein nmcli-Aufruf, ist jetzt gecacht**)

**Pflicht bei langsamen Daten:**
- Subprocess-Ergebnisse (z.B. SSID via `iwgetid`) mit TTL cachen -- Muster: `_cache_ts: float = 0.0` + `time.monotonic()`-Vergleich. Beispiel: `StatusScreen._get_ssid_cached()` (10s TTL).
- Werte die sich selten aendern (z.B. Batterie-Icon im Menue, Schwelle 20%) mit laengerer TTL cachen. Beispiel: `MenuScreen._get_battery_level_cached()` (120s TTL).
- Zustand der WiFi-Verbindung: Nur `portal.is_wifi_connected()` aufrufen -- gibt gecachten Bool zurueck, kein Subprocess.

## Numpad-Navigation

Das Delock USB-Numpad sendet IMMER Ziffern-Keycodes (`KEY_KP0`-`KEY_KP9`), unabhaengig vom NumLock-Status. In Navigations-Screens werden 8/2/4/6 per `translate_digit_to_nav()` zu Up/Down/Left/Right uebersetzt. In Ziffern-Screens (Armed, Planting, Code-Eingabe) bleiben Ziffern unveraendert.

```
8=Up  2=Down  4=Left  6=Right    Navigation (Menue, Setup)
0-9                               Zifferneingabe (Armed, Planting, Code-Entry)
Enter                             Bestaetigen / Naechste Seite / Sub-Menue oeffnen
<- (Backspace)                    Zurueck / Abbrechen / Ziffer loeschen
+/-                               Schnell Wert +10/-10 (z.B. Timer +/- 5min)
*                                 Status Screen (aus Menue)
/                                 Update Screen (aus Menue)
```

## Konfigurierbarer Geraetename (`device_name`)

- **Config:** `game.device_name` in `config/default.yaml`, max 7 Zeichen (LCD-Limit).
- **Engste Stelle:** `** {name} ARMED **` -- 13 Zeichen fest, 7 frei bei 20 Spalten.
- **Validierung:** Web-Interface `maxlength="7"` + serverseitige Validierung, Config-Truncation-Fallback.
- **Zugriff im Code:**
  - Modi (haben `GameContext`): `context.custom_data.get("device_name", "Prop").upper()`
  - UI-Screens (haben `self.app`): `self.app.config.get("game", "device_name", default="Prop").upper()`
  - Wird beim Erstellen des `GameContext` in `setup_screen.py` und `tournament_screen.py` gesetzt.

## Screen-Layouts

### Boot
Zeile 1-2: `AIRSOFT PROP / PROP v{version}`, Zeile 4: `Booting...`, 2-3 Sek. sichtbar.

### Hauptmenue
Zeile 1-3: Modusliste mit Cursor (8/2=Up/Down, Enter=auswaehlen). Zeile 4: `* Status  / Upd  [WiFi]` (optional Batterie-Icon). Keine Ziffern-Shortcuts fuer Modi.

### Setup
Zeile 1: Modusname, Zeile 2-3: Optionen (8/2=waehlen, 4/6=aendern). Zeile 4: `<- Back  Ent Start` (RANGE) oder `<- Back  Ent Edit` (CODE_INPUT). Enter auf CODE_INPUT oeffnet Code-Eingabe Sub-Screen.

### Setup -- Code-Eingabe Sub-Screen
Zeile 1: Modusname, Zeile 2: `Enter Code:`, Zeile 3: `> {eingabe}____`, Zeile 4: `<- Back   Ent Ok`. Ziffern 0-9 direkt, Backspace loescht, Enter bestaetigt.

### Tournament
Zeile 1+4: `##Tournament-Mode##`, Zeile 2: `Game: <Modus>`, Zeile 3: `> Start Game`. Einzige Aktion: Enter = Spiel starten. 5x Backspace = PIN-Eingabe.

### Planting -- Code Entry
Zeile 1: `PLANTING {device_name}...`, Zeile 2: `Enter code to arm:`, Zeile 3: Aktivierungscode, Zeile 4: `> {eingabe}____`. Backspace loescht/bricht ab, korrekte Eingabe fuehrt zu ARMED.

### Planting -- Timed (Enter halten)
Zeile 1: `PLANTING {device_name}...`, Zeile 2: leer, Zeile 3: Progressbar `[=====>          ]`, Zeile 4: `Hold ENTER  Xs`. Enter loslassen = Abbruch, Countdown=0 = ARMED.

### Armed -- Random Code
Zeile 1: `** {device_name} ARMED **`, Zeile 2: Timer, Zeile 3: Generierter Code (max 20 Zeichen, KEIN Label), Zeile 4: Eingabe als Underscores (gleiche Laenge wie Code, `<-` loescht).

### Armed -- Set Code
Zeile 1: `** {device_name} ARMED **`, Zeile 2: Timer, Zeile 3: `Enter Code:`, Zeile 4: `> {eingabe}____` (Code NICHT sichtbar, max 10 Zeichen).

### Armed -- Random Code+ / Set Code+
Wie Basis-Modi, aber bei falscher Ziffer wird Zeile 4 kurz (~0.7s) durch `WRONG! -Xs` ersetzt. Set Code+ zeigt korrekte Ziffern als `*` (z.B. `> ***___`). Kein Backspace -- jede Ziffer wird sofort validiert.

### Armed -- USB Key Cracker (wartend)
Zeile 1: Armed-Header, Zeile 2: Timer, Zeile 3: leer, Zeile 4: `Insert USB Key...`

### Armed -- USB Key Cracker (cracking)
Zeile 1: Armed-Header, Zeile 2: `Cracking...  Xs`, Zeile 3: `[####........] XX%`, Zeile 4: `7 3 * * * * * *` (geknackte=fix, Rest=cycling).

### Letzte 30 Sekunden
Timer blinkt, Piepen beschleunigt (alle 2s statt 5s).

### Letzte 10 Sekunden
Timer wandert in Zeile 1 als `!! 00:07 !! ARMED !!` (blinkend). Restliche Zeilen bleiben modusspezifisch. Jeder Modus implementiert `render_last_10s()`:

- **Random Code (<=10 Ziffern):** Zeile 2 leer, Zeile 3 Code, Zeile 4 Eingabe
- **Random Code (>10 Ziffern):** Zeile 2 Code, Zeile 3 Eingabe, Zeile 4 leer
- **Set Code:** Zeile 2 leer, Zeile 3 `Enter Code:`, Zeile 4 Eingabe
- **USB Key Cracker (wartend):** Zeile 2 leer, Zeile 3 `INSERT USB KEY!!`, Zeile 4 leer
- **USB Key Cracker (cracking):** Zeile 2 Status, Zeile 3 Progressbar, Zeile 4 Digits
- **Random Code+:** Wie Random Code, aber Zeile 4 zeigt `WRONG! -Xs` bei Penalty-Flash
- **Set Code+:** Wie Set Code, aber Zeile 4 zeigt `> ***___` oder `WRONG! -Xs`

### Ergebnis -- Defused
`{device_name} DEFUSED!` + `Time left: MM:SS`, `Ent -> Menu`. Audio: `defused.wav`.

### Ergebnis -- Detonated
Invertierter Rahmen: `{device_name} EXPLODED! / GAME OVER!`. Audio: `explosion.wav` dann `siren.wav` (Endlosschleife bis Enter).

### Status (Taste *, blaetterbar)
- **Seite 1 Netzwerk:** WLAN-Name + IP im Station-Mode, oder AP-Info wenn Captive Portal aktiv.
- **Seite 2 System:** Version, CPU-Temp, RAM, Uptime.
- **Seite 3 Batterie:** Status/Prozent/Spannung (oder "No UPS HAT detected").
- **Navigation:** Enter=naechste Seite, `<-`=zurueck zum Menue.

### Update (Taste /)
Prueft Internet, zeigt Version, Enter=installieren, `<-`=abbrechen. Nach erfolgreichem Update: `Ent Restart <- Back` -- Enter startet den Service neu.
