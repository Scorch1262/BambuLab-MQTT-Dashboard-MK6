# Übergabedokument: 3D-Drucker Dashboard (MK6)

Dieses Dokument fasst den aktuellen Stand des Projekts zusammen, damit die
Weiterentwicklung in einem neuen Chat (auch mit einem anderen Assistenten/
Modell) nahtlos möglich ist. Am besten diese Datei **zusammen mit `app.py`
und `README.md`** in den neuen Chat hochladen bzw. einfügen.

**Hinweis zu MK6:** Dies ist eine neue, eigenstaendig versionierte Ausgabe
(Versionszaehlung startet bei v1.0.0, siehe Abschnitt 9) auf Basis von
MK5 v1.6.8 - technisch ein rein additiver Fortsatz, kein Rewrite. Die
gesamte Architektur, alle Druckertypen und alle in MK5 hart erarbeiteten
Lessons Learned (Abschnitt 6/7, insbesondere die FTPS-Saga) gelten
unveraendert weiter. Neu in MK6 (v1.0.0): Druckauftrags-Verlauf je
Drucker (Abschnitt 5, Unterabschnitt "Druckauftrags-Verlauf").

---

## 1. Was ist das Projekt

Ein lokal laufendes Web-Dashboard (Flask, Python) für 3D-Drucker im
eigenen Netzwerk. Zeigt Fortschritt, aktuelle Datei, Temperaturen, Kamera
und (je nach Hersteller) weitere Daten in dunkel gehaltenen Karten
(Design angelehnt an Anduril Lattice) an. Läuft als Python-Skript oder als
über PyInstaller/GitHub Actions gebaute Windows-.exe.

**Zielumgebung:** Wird typischerweise per PyInstaller in eine Windows-EXE
gepackt und läuft neben `config.json` im selben Ordner. GitHub-Actions-
Workflow zum automatischen Bauen ist bereits vorhanden.

---

## 2. Datei-/Repo-Struktur

```
app.py                          <- das komplette Programm (Backend + Frontend in einer Datei)
ftps_upload_helper.py           <- separate Hilfsanwendung fuer den Bambu-FTPS-Upload (seit v1.5.3)
config.example.json             <- Beispiel-Config mit allen Druckertypen
requirements.txt                <- flask, paho-mqtt, pyinstaller
README.md                       <- ausführliche Nutzer-Doku (Setup, alle Druckertypen, GitHub Actions)
.gitignore
.github/workflows/build-exe.yml <- GitHub-Actions-Workflow, baut DruckerDashboard + FtpsUploadHelper
print_history/                  <- LAUFZEIT-Ordner (nicht im Repo, siehe .gitignore), automatisch
                                    angelegt neben der exe/app.py - ein Unterordner je Drucker-ID
                                    mit dessen Druckauftrags-Verlauf (seit MK6, siehe Abschnitt 5)
print_queue/                    <- LAUFZEIT-Ordner (nicht im Repo, siehe .gitignore), analog zu
                                    print_history/ - ein Unterordner je Drucker-ID mit dessen
                                    Warteschlange (seit MK6 v1.2.0, siehe Abschnitt 5)
```

`app.py` ist bewusst **eine einzige Datei** (mittlerweile > 4000 Zeilen):
Backend-Klassen, Flask-Routen und das komplette Frontend (HTML/CSS/JS) als
ein großer Python-String (`INDEX_HTML`, per `render_template_string`
ausgeliefert). Das hat sich für PyInstaller-Kompatibilität bewährt (kein
`--add-data` nötig, keine externen Template-/Static-Ordner).

---

## 3. Architektur-Überblick

- **Ein Connection-Objekt pro Drucker**, in einem eigenen Daemon-Thread,
  das per Polling (HTTP) oder MQTT-Callback seinen `self.status`-Dict
  aktuell hält. Jede Connection-Klasse hat `start()`, `stop()`, ein
  `status`-Dict mit `connected`, `last_update`, `error` u.a.
- **`DashboardApp`** verwaltet alle Connections (`self.connections`,
  `id -> Connection`), lädt/speichert `config.json`, dispatcht beim
  Anlegen (`_start_printer`) und beim Hinzufügen (`add_printer`) nach
  `type` auf die passende Connection-Klasse.
- **Flask-Routen** (`GET/POST /api/printers`, `DELETE /api/printers/<id>`,
  `GET /api/status`, `POST /api/printers/<id>/extras/<extra_id>/command`,
  `GET /camera/<id>`, `GET /`) sind dünne Wrapper um `DashboardApp`.
- **Frontend** pollt `GET /api/status` alle 2,5 Sekunden und rendert pro
  Drucker-Typ eine eigene Karten-Renderfunktion in JS
  (`renderBambuCard`, `renderFormlabsCard`, `renderOctoPrintCard`,
  `renderCrealityCard`, `renderUltimakerCard`). Der Dispatch dazu steht in
  `refresh()`.
- **Config-Datei** (`config.json`) liegt neben der exe/dem Skript
  (`base_dir()`), wird beim ersten Start automatisch mit
  `DEFAULT_CONFIG` angelegt. `load_config()` ergänzt fehlende Felder via
  `setdefault` (rückwärtskompatibel zu älteren `config.json`-Ständen).

### Wichtigste Codestellen zum Wiederfinden

| Was | Wo (grep-Muster) |
|---|---|
| Bekannte Druckertypen | `KNOWN_TYPES`, `FORMLABS_TYPES`, `CREALITY_TYPES` |
| Default-Konfiguration | `DEFAULT_CONFIG = {` |
| Verbindungsklassen | `class PrinterConnection`, `class FormlabsLocalApiConnection`, `class OctoPrintConnection`, `class CrealityConnection`, `class UltimakerConnection`, `class ExtrasMqttManager` |
| Druckauftrag senden (Bambu) | `PrinterConnection.preview_print()`, `PrinterConnection.send_print()`, `PrinterConnection._request_print()`, `PrinterConnection.pause_mqtt()`/`resume_mqtt()`/`wait_for_mqtt_reconnect()`, `class ImplicitFtpTls`, `FTPS_PROFILES`, `_find_ftps_upload_helper()`, `ftps_upload_helper.py` (separate Datei/exe, eigenes `PROFILES`-Dict), `_run_ftps_upload_worker()` + Sentinel-Check `--ftps-upload-worker` (Fallback, ganz frueh im Modul), `DashboardApp.add_printer()` (Parameter `bambu_family`), `DashboardApp.prepare_print_job()`/`start_confirm_print_job()`/`cancel_print_job()`/`get_print_progress()`, Routen `POST /api/printers` (Feld `bambu_family`)/`POST /api/printers/<id>/print/prepare`\|`/confirm`, `GET .../print/progress/<job_id>`, `POST .../print/cancel`, JS `renderDropZone()`/`dzDrop()`/`openAmsModal()`/`confirmAmsModal()`/`pollAmsProgress()`/`submitAdd()` (Feld `f_bambu_family`) |
| Druckauftrag senden (Ultimaker, seit v1.6.3) | `_parse_digest_challenge()`, `_build_digest_authorization()`, `_build_multipart_body()`, `UltimakerConnection.start_pairing()`/`check_pairing()`/`_digest_challenge()`/`send_print()`, `DashboardApp.start_ultimaker_pairing()`/`check_ultimaker_pairing()`/`send_ultimaker_print_now()` (nutzt dieselben `_print_jobs`/`_print_progress`-Strukturen wie Bambu weiter), Routen `POST /api/printers/<id>/ultimaker/pair/start`\|`/pair/status`\|`POST .../ultimaker/print` (nutzt die BESTEHENDEN generischen `GET .../print/progress/<job_id>`-Routen weiter, keine eigenen noetig), JS `renderUltimakerDropZone()`/`pairUltimaker()`/`dzDropUltimaker()`/`pollUltimakerProgress()` |
| AMS-Zuordnungsvorschlag | `PrinterConnection.preview_print()` (liefert `total_filaments`), `_parse_3mf_filaments()` (liefert `(filamente, gesamtanzahl)`), `_parse_plate1_used_filament_indices()`, `_find_matching_tray()` (Farbtoleranz seit v1.6.6), `_color_distance()`, `COLOR_MATCH_TOLERANCE`, `_types_compatible()`, `_slot_to_flat_index()`, JS `openAmsModal()`/`amsRowHtml()` (`data-true-index`)/`confirmAmsModal()` (baut `ams_mapping` an den echten Filament-Positionen, nicht Anzeige-Reihenfolge) |
| Versionsnummer | `APP_VERSION` (ganz oben in `app.py`), Route `GET /api/version`, `.github/workflows/build-exe.yml` (liest die Version per Regex aus) |
| Druckauftrags-Verlauf (seit MK6) | `class PrintHistoryStore`, `_extract_thumbnail()`, `PRINT_HISTORY_MAX_JOBS`, `DashboardApp.history`, `DashboardApp._start_printer()` (legt Ordner an), `DashboardApp.get_print_history()`/`delete_print_history_entry()`/`get_print_history_thumbnail_path()`/`reprint_from_history()`, Routen `GET/DELETE .../history`, `GET .../history/<job_id>/thumbnail`, `POST .../history/<job_id>/reprint`, JS `openHistoryModal()`/`refreshHistoryModal()`/`reprintHistoryEntry()`/`deleteHistoryEntry()`, `.hist-icon` in jeder Karte |
| Orchestrierung | `class DashboardApp` |
| REST-Routen | `@app.route(` |
| Frontend-HTML/JS | `INDEX_HTML = r"""` (ein einziger großer String bis zum Dateiende) |
| Kartenrenderer (JS) | `function render...Card(p){` |
| Typ-Formular (JS) | `function toggleTypeFields()`, `function submitAdd()` |

---

## 4. Unterstützte Druckertypen (Stand jetzt)

| `type`-Wert | Hersteller/Gerät | Anbindung | Auth nötig? | Kamera |
|---|---|---|---|---|
| `bambu` | Bambu Lab (P1/X1/A1) | MQTT/TLS, Port 8883, `device/{serial}/report` | Access Code + Seriennummer | Ja, eigenes reverse-engineertes Protokoll Port 6000 |
| `formlabs` | Formlabs Drucker (Form 3/4/Fuse) | Formlabs **Local API** über `PreFormServer` (Standard `http://localhost:44388`) | Nein, aber PreFormServer muss laufen | Nein |
| `formlabs_wash` | Form Wash L | wie `formlabs`, andere Labels | Nein | Nein |
| `formlabs_cure` | Form Cure L | wie `formlabs`, andere Labels | Nein | Nein |
| `octoprint` | Beliebiger Drucker mit OctoPrint | REST-API, `/api/printer`, `/api/job` | **API-Key Pflicht** | Ja, mjpg-streamer-Standard-URL (überschreibbar) |
| `creality_k1`, `creality_k1c`, `creality_k1max`, `creality_k1se`, `creality_other` | Creality Klipper-Drucker | Moonraker-API, Port 7125 | Optional (meist LAN-trusted) | Ja, Crowsnest-Standard-URL (überschreibbar) |
| `ultimaker` | Ultimaker UM3/S-Serie/Factor 4 | offizielle lokale REST-API `/api/v1/` | Nein fuer Status (nur lesend); Digest-Auth-Kopplung fuer Druckstart (seit v1.6.3) | Ja, mjpg-streamer-Standard-URL (überschreibbar) |

**Wichtiges Architekturprinzip:** Die 5 `creality_*`-Typen und die 3
`formlabs_*`-Typen nutzen **jeweils dieselbe Connection-Klasse** – der
`type`-Wert dient dort nur der Beschriftung/dem Label auf der Karte, nicht
einer unterschiedlichen technischen Anbindung. Bei einer neuen
Geräte-„Version" für einen bereits unterstützten Hersteller reicht es
daher meist, nur den Type-Tuple und die Frontend-Labels zu erweitern,
**keine neue Connection-Klasse** zu schreiben.

---

## 5. Weitere Features

- **Bambu Lab: Druckauftrag per Drag & Drop, zweistufig (prepare/confirm).**
  Jede Bambu-Karte hat ein Ablage-Feld unter der AMS-Anzeige
  (`renderDropZone()`). Akzeptiert werden ausschließlich bereits fertig
  gesclicte `.gcode.3mf`-Dateien — bewusst keine rohen `.gcode`-Dateien,
  da sich diese laut mehreren Community-Quellen nicht zuverlässig per
  MQTT starten lassen (siehe README, Abschnitt 4a). Ablauf:
  1. **Prepare:** `POST /api/printers/<id>/print/prepare` (multipart,
     Feld `file`) → `DashboardApp.prepare_print_job()` speichert die
     Datei serverseitig temporär (unter einer `job_id`, siehe
     `DashboardApp._print_jobs`) und ruft
     `PrinterConnection.preview_print()` auf: liest Farbe+Typ jedes
     Filaments aus `Metadata/project_settings.config` und schlägt anhand
     der live gemeldeten AMS-Fächer (`self.status["ams"]`) eine Zuordnung
     vor. **Es wird an dieser Stelle noch nichts an den Drucker
     gesendet.**
  2. **Frontend-Dialog** (`openAmsModal()`): zeigt die Vorschläge als
     editierbare Dropdowns pro Filament — analog zur AMS-Zuordnung in
     Bambu Studio. Der Nutzer kann jede Zuordnung von Hand ändern, bevor
     etwas passiert.
  3. **Confirm:** `POST /api/printers/<id>/print/confirm` ({job_id,
     mapping}) → `DashboardApp.confirm_print_job()` →
     `PrinterConnection.send_print()`, der zuerst per FTPS (Port 990,
     **implizites** TLS via `ImplicitFtpTls`, Login `bblp`/Access Code)
     hochlädt und danach über die MQTT-Verbindung das Kommando
     `project_file` mit der vom Nutzer bestätigten `ams_mapping` sendet.
     Alternativ `POST .../print/cancel` verwirft den Vorgang und räumt
     die Temp-Datei auf.
  Setzt **Developer Mode** am Drucker voraus (separate Einstellung
  zusätzlich zum LAN-Modus). Nicht bestätigte Jobs werden nach 20 Minuten
  automatisch aufgeräumt (`_purge_stale_print_jobs()`).
  **Nur benötigte Filamente:** `_parse_3mf_filaments()` filtert die
  vollständige Filamentliste aus `project_settings.config` (JSON) auf
  die Schnittmenge mit den in `Metadata/slice_info.config` (XML, nur in
  gesliceten Dateien vorhanden) für **Plate 1** tatsächlich verbrauchten
  Filamenten (`_parse_plate1_used_filament_indices()`, `<filament id=…>`-
  Elemente, id ist dort 1-basiert). Fehlt `slice_info.config` oder liefert
  keine Treffer, fällt die Funktion defensiv auf die volle Liste zurück
  (kein Risiko, nur weniger präzise) — Quelle für die Dateistruktur:
  siehe Kommentare in `app.py` bzw. README Abschnitt 4a.
  **Dialog-UX (v1.3.0):** pro benötigtem Filament zwei Radio-Optionen
  — "Vorschlag aus Datei verwenden" (automatischer Farbmatch oder
  "Extern/manuell") vs. "Anderes Material aus dem AMS wählen" (Dropdown
  mit den übrigen erkannten Fächern). `confirmAmsModal()` liest pro Zeile
  aus, welche Option gewählt ist, bevor `mapping` ans Backend geht.
  **v1.3.2:** Hex-Farbcode zusätzlich zum Farbfeld als Text angezeigt.
  **v1.4.0:** Hex-Text durch **Farbwort** ersetzt (`NAMED_COLORS`-Palette
  + `colorNameFor()`: nächster Treffer per RGB-Abstand zu einer festen
  Liste deutscher Farbnamen; exakter Hex-Wert bleibt als `title`-Tooltip
  erhalten, keine geratene 1:1-Übersetzung, sondern eine bewusste
  Näherung für die Anzeige) — betrifft benötigtes Filament, Vorschlagstext
  und "anderes Material"-Dropdown gleichermaßen.
  **Fortschrittsanzeige (v1.4.0):** `POST .../print/confirm` läuft jetzt
  asynchron — `DashboardApp.start_confirm_print_job()` startet
  `conn.send_print(..., on_progress=...)` in einem Hintergrund-Thread
  (`threading.Thread(daemon=True)`) und antwortet sofort. Fortschritt
  liegt in `DashboardApp._print_progress[job_id]` (eigener Lock), wird
  über `GET .../print/progress/<job_id>` abgefragt. Frontend
  (`pollAmsProgress()`) pollt alle 400ms und aktualisiert Balken +
  Prozent + übertragene/gesamte Bytes (`formatBytes()`).
  **Wichtige Verhaltensänderung:** Bei einem Fehler werden Job und
  Temp-Datei jetzt bewusst NICHT gelöscht (anders als in v1.2.0/v1.3.x) —
  ein erneuter Klick auf "Drucken starten" nutzt dieselbe `job_id` und
  denselben Datei-Inhalt erneut, ohne dass der Nutzer die Datei nochmal
  hochladen oder die AMS-Zuordnung neu auswählen muss. Nur bei Erfolg,
  explizitem Cancel, oder nach 20 Minuten Inaktivität
  (`_purge_stale_print_jobs()`) wird aufgeräumt.
  **FTPS-Drosselung (v1.4.0):** In `_ftps_upload_once()` nach jedem
  gesendeten 4096-Byte-Block `time.sleep(0.015)` ergänzt. Hintergrund:
  Nutzer-Feedback zeigte, dass zwei unabhängige Upload-Versuche exakt
  bei demselben Byte-Stand abbrachen (69632 Bytes, = 17×4096) — ein
  scheinbar reproduzierbarer Abbruch, der auf einen druckerseitigen
  Pufferüberlauf beim SD-Karten-Schreiben hindeutete.
  **v1.4.1 - bessere Diagnose statt weiterer Theorien:** Nach Einbau der
  Drosselung brach ein weiterer Upload-Versuch bereits nach 8192 Bytes
  ab (2×4096) — anders als der 69632-Byte-Abbruch aus v1.4.0. Die
  Retry-Logik wurde erweitert, um **alle 3 Versuche mit jeweiligem
  Byte-Stand** zu sammeln und gemeinsam in der Fehlermeldung anzuzeigen
  (`attempts`-Liste in `_ftps_upload()`), statt nur den letzten Versuch.
  **v1.4.2 - konkreter Bug gefunden und behoben:** Die v1.4.1-Diagnose
  zeigte, dass **alle 3 Versuche exakt bei 8192 Bytes** abbrachen -
  perfekt reproduzierbar, kein Netzwerk-Zufall. Beim Review von
  `_ftps_upload_once()` fiel auf: der manuelle Upload-Ablauf (seit
  v1.3.1, fuer stufenspezifische Fehlermeldungen) ruft
  `ftp.ntransfercmd(f"STOR {remote_name}")` direkt auf und **ueberspringt
  dabei das `TYPE I`-Kommando**, das `ftplib.FTP.storbinary()` in der
  Python-Standardbibliothek normalerweise automatisch VOR jedem Upload
  sendet (`self.voidcmd('TYPE I')`), um den Server explizit auf
  Binaermodus umzuschalten. Jetzt in `_ftps_upload_once()` vor
  `ntransfercmd()` ergaenzt (`ftp.voidcmd("TYPE I")`).

  **v1.4.3 - Zwischenschritt, spaeter widerlegt.** Der Fehler trat
  danach erneut exakt bei 8192 Bytes auf, alle 3 Versuche identisch.
  Vermutung zu diesem Zeitpunkt: TLS-inspizierende Sicherheitssoftware
  oder Firmen-Firewall (Rueckfrage beim Nutzer ergab beides zutreffend:
  AV mit HTTPS-Pruefung installiert + verwaltetes Netzwerk - passte zum
  Muster, war aber letztlich die falsche Fährte). `_ftps_upload()`
  bekam einen `same_offset`-Check, der bei identischem Byte-Stand ueber
  alle 3 Versuche einen AV/Firewall-Hinweis anhaengte.

  **v1.4.4 - TATSAECHLICHE URSACHE GEFUNDEN UND BEHOBEN.** Der Nutzer
  konnte einen direkten Vergleichstest mit FileZilla durchfuehren
  (identische Datei, Drucker, Netzwerk, Rechner) - **FileZilla hat die
  Datei problemlos uebertragen.** Das widerlegt die AV-/Firewall-Theorie
  aus v1.4.3 eindeutig (waere ein AV/Firewall-Problem, haette es auch
  FileZilla betroffen) und beweist: das Problem lag im **Dashboard-
  eigenen Code**, nicht im Netzwerk. Der manuelle Upload-Ablauf (seit
  v1.3.1, fuer stufenspezifische Fehlermeldungen eingefuehrt) sendet in
  ungewoehnlich kleinen 4-KB-Bloecken mit kuenstlicher `time.sleep()`-
  Pause zwischen jedem Block (seit v1.4.0) - ein Sende-Muster, das kein
  "normaler" FTP-Client wie FileZilla verwendet. **Fix:** kompletter
  Rueckbau von `_ftps_upload_once()` auf `ftp.storbinary()` (Pythons
  Standardmechanismus - Bytes werden in ueblichen 8-KB-Bloecken direkt
  hintereinander gesendet, kein Pacing, `TYPE I` automatisch inklusive).
  Das entspricht jetzt strukturell dem, was auch FileZilla macht.
  Die stufenspezifische Fehlerdiagnose (PASV vs. Transfer vs. Abschluss-
  Bestaetigung, eingefuehrt in v1.3.1) wurde dabei bewusst aufgegeben -
  sie hatte ihren Zweck erfuellt (den Bug einzugrenzen), aber die
  benoetigte Umsetzung (manueller Ablauf statt `storbinary()`) war die
  eigentliche Fehlerursache. `storbinary()` unterstuetzt einen
  `callback`-Parameter, ueber den die Fortschrittsanzeige
  (`on_progress`) unveraendert weiterfunktioniert. Bei einem Fehler
  wird weiterhin der Byte-Stand aus dem Callback-Zaehler in die
  Fehlermeldung eingebaut (`sent_state["sent"]`), nur ohne die
  Phasen-Unterscheidung von vorher.
  Der `same_offset`-Hinweis aus v1.4.3 (AV/Firewall-Vermutung) wurde
  wieder entfernt, da er sich als falsch herausgestellt hat.
  **Lesson Learned fuer die Weiterarbeit:** Ein ungewoehnliches,
  selbstgebautes Sende-/Zeitmuster (viele kleine Bloecke + kuenstliche
  Pausen) kann selbst OHNE erkennbaren Netzwerk-/TLS-Grund zu
  Verbindungsabbruechen fuehren, die sich wie ein Server-/Netzwerk-
  problem anfuehlen. Ein Vergleichstest mit einem bekannt funktionierenden
  Referenz-Client (hier: FileZilla) war der entscheidende Schritt, um
  das einzugrenzen - fuer aehnliche Debugging-Situationen in Zukunft
  eine gute erste Anlaufstelle, statt weiter an TLS-Parametern zu drehen.

  **v1.4.5 - zweite versteckte Abweichung gefunden und entfernt.**
  Trotz v1.4.4 trat der Fehler weiterhin auf, jetzt bei einem anderen,
  aber wieder festen Vielfachen der `storbinary()`-Blockgroesse
  (73728 = 9×8192 Bytes, alle 3 Versuche identisch). Der Rueckbau in
  v1.4.4 hatte nur die manuelle Sende-Schleife selbst ersetzt - die
  `ImplicitFtpTls`-Klasse (definiert seit v1.3.1, unveraendert durch
  v1.4.4) hatte aber IMMER NOCH eine ueberschriebene `ntransfercmd()`-
  Methode, die bewusst OHNE TLS-Session-Wiederverwendung fuer die
  Datenverbindung arbeitete (Theorie aus v1.3.1, nie bestaetigt).
  Zusaetzlich war weiterhin `ctx.maximum_version = TLSv1_2` gesetzt
  (aus v1.2.0, ebenfalls nie als tatsaechlich hilfreich bestaetigt).
  Beides sind Abweichungen vom Standardverhalten von Python/`ftplib`,
  die FileZilla mit hoher Wahrscheinlichkeit NICHT hat (FileZilla laesst
  TLS-Version frei aushandeln und nutzt vermutlich Session-Resumption
  wo sinnvoll). Beide Overrides entfernt:
  - `ImplicitFtpTls.ntransfercmd()`-Override komplett geloescht → Python
    nutzt wieder das eingebaute `ftplib.FTP_TLS.ntransfercmd()`
    (inklusive Session-Wiederverwendung via `session=self.sock.session`).
    `ImplicitFtpTls` ueberschreibt jetzt nur noch `sock` (Property) fuer
    das beim Verbindungsaufbau zwingend noetige Socket-Wrapping fuer
    implizites TLS - keine weiteren Anpassungen.
  - `ctx.maximum_version = ssl.TLSVersion.TLSv1_2` in `_ftps_upload_once()`
    entfernt → TLS-Version wird wieder frei ausgehandelt (typischerweise
    TLS 1.3, falls vom Drucker unterstuetzt).
  `ssl.OP_IGNORE_UNEXPECTED_EOF` (aus v1.2.0) wurde NICHT entfernt - das
  betrifft nur den sauberen Verbindungsabschluss (close_notify-
  Handling), nicht die Datenuebertragung selbst, und ist ein reines
  Sicherheitsnetz ohne beobachtete Nebenwirkungen.
  **Damit besteht der komplette FTPS-Upload-Pfad jetzt nur noch aus dem
  fuer implizites TLS absolut zwingenden Minimum plus Standard-
  `ftplib`-Verhalten** - keine weiteren spekulativen Anpassungen im
  Python-Code selbst mehr uebrig, die entfernt werden koennten. Das
  stellte sich jedoch als NICHT ausreichend heraus (siehe v1.4.6): der
  Fehler trat danach bei exakt demselben Byte-Wert wie zuvor erneut auf,
  was zeigt, dass die in v1.4.5 entfernten Overrides gar nicht die
  eigentliche Ursache waren.
  **v1.4.6/v1.4.7 - curl-Experiment (seit v1.4.9 wieder verworfen).**
  Nachdem v1.4.5 (minimaler Python-`ftplib`-Code) auf einem X1C erneut
  exakt beim selben Byte-Wert scheiterte, wurde der Upload testweise auf
  einen **`curl`-Unterprozess** umgestellt (curl bringt eine eigene,
  von Python unabhaengige TLS-Implementierung mit). v1.4.7 ergaenzte
  `--verbose`-Diagnose und ein `--tlsv1.2 --tls-max 1.2`-Experiment
  (curl unter Windows nutzt **Schannel**, nicht OpenSSL - ein anderer
  Code-Pfad als der vorherige Python-Versuch). **Ergebnis:** curl
  scheiterte auf X1C UND X1E genauso wie Python zuvor
  (`Send failure: Connection was reset` auf der Datenverbindung,
  Kontrollverbindung stets erfolgreich) - siehe v1.4.9 unten fuer die
  Konsequenz daraus. v1.4.8 war ein reiner Build-Fix ohne
  Verhaltensaenderung (f-string-Syntax, siehe Lessons Learned Punkt 6).

  **v1.4.9 - RUeCKBAU auf Python-`ftplib` (curl-Ansatz verworfen).**
  Der entscheidende neue Befund: curl (Schannel) scheitert auf X1C/X1E
  mit **exakt demselben Muster** wie Python zuvor - Kontrollverbindung
  (Port 990) baut sauber auf, die anschliessende PASV-Datenverbindung
  wird aber sofort zurueckgesetzt (`Send failure: Connection was
  reset`), noch bevor im `--verbose`-Log eine TLS-Aushandlung fuer diese
  zweite Verbindung sichtbar wird. **Das bedeutet: sowohl Python/OpenSSL
  als auch curl/Schannel scheitern an der X1-Serie, nur FileZilla
  (vermutlich GnuTLS) funktioniert.** Recherche ergab einen sehr
  aehnlichen dokumentierten Fall (anderer FTPS-Server, andere Clients):
  manche strikten FTPS-Server verlangen, dass die TLS-Sitzung der
  Datenverbindung nachweislich eine Fortsetzung der Kontrollverbindungs-
  Sitzung ist - FileZilla implementiert das korrekt, andere Clients
  (im gefundenen Fall FireFTP) nicht (Quelle: Adobe-Community-Forum,
  "FTPS TLS session resumption", 2015). Ob das exakt unsere Ursache
  ist, bleibt unbestaetigt - Python uebergibt zwar bereits
  `session=self.sock.session` beim Wrap der Datenverbindung (siehe
  `ftplib.FTP_TLS.ntransfercmd()`, Standardverhalten seit v1.4.5), was
  eigentlich Session-Resumption bedeuten sollte, scheiterte aber
  trotzdem - daher bleibt die genaue Ursache letztlich ungeklaert.
  **Entscheidung:** Da weder Python noch curl das X1-Problem loesen,
  aber curl eine zusaetzliche externe Abhaengigkeit (muss auf dem
  System vorhanden sein) einfuehrt OHNE einen Vorteil zu bringen, wurde
  bewusst auf den einfacheren Python-`ftplib`-Ansatz (Stand v1.4.5)
  zurueckgewechselt - der nachweislich fuer einen Teil der Druckerflotte
  (A1 Mini) zuverlaessig funktioniert, waehrend der curl-Ansatz keinen
  Mehrwert brachte. Konkrete Aenderungen:
  - `PrinterConnection._ftps_upload_once()`: komplett zurueckgebaut auf
    `ImplicitFtpTls` + `ftp.storbinary()` (identisch zum Code-Stand von
    v1.4.5 - kein `curl`, kein `subprocess`, keine `--verbose`-Log-
    Verarbeitung mehr).
  - `class ImplicitFtpTls`: Docstring aktualisiert, Klasse ist wieder
    aktiv (wird wieder instanziiert). Keine funktionale Aenderung
    gegenueber v1.4.5 (nur `sock`-Property-Override, kein
    `ntransfercmd()`-Override).
  - Nicht mehr benoetigte Imports entfernt: `subprocess`, `shutil`, `re`.
  - `_ftps_upload()` (Retry-Wrapper) faengt wieder
    `(ssl.SSLError, OSError, EOFError, RuntimeError, *ftplib.all_errors)`
    statt der curl-spezifischen `subprocess.SubprocessError`.
  - README Abschnitt 4a dokumentiert das X1-Problem jetzt offen als
    **bekannte, ungeloeste Einschraenkung** mit FileZilla als
    Workaround, statt eine (nicht mehr zutreffende) technische
    curl-Begruendung zu zeigen.
  **Getestet:** Regex-Sicherheitsscan auf die in v1.4.8 behobene
  f-string-Backslash-Problematik (keine neuen Faelle); vollstaendiger
  Async-Confirm-Flow inkl. Progress-Polling gegen `127.0.0.1:990`
  (erwartete Verbindungsverweigerung, aber korrekter Codepfad ohne
  curl-Referenzen bestaetigt); Verifikation per `inspect.getsource()`,
  dass `ImplicitFtpTls.ntransfercmd` wieder von `ftplib.FTP_TLS` geerbt
  wird (kein Override mehr) und `_ftps_upload_once` wieder
  `ImplicitFtpTls`/`storbinary` statt `curl` nutzt.
  **Fuer die Weiterarbeit:** Das X1-Problem ist damit NICHT geloest,
  nur die Zusatzkomplexitaet von curl ohne Nutzen wieder entfernt.
  Sinnvolle naechste Schritte, falls jemand weiter forschen moechte:
  (1) OpenSSL-basierter curl-Build (https://curl.se/windows/, nicht die
  Windows-eigene Schannel-Variante) manuell testen, um Schannel als
  Ursache ein- oder auszuschliessen (Ergebnis stand zum Zeitpunkt dieser
  Uebergabe noch aus); (2) FileZillas tatsaechlich ausgehandelte
  TLS-Version/Cipher-Suite aus dessen Nachrichtenprotokoll auslesen und
  versuchen, dieselbe explizit zu erzwingen; (3) Wireshark-Mitschnitt
  von FileZilla vs. Python/curl zum direkten ClientHello-Vergleich;
  (4) Firmware-Update-Check am X1C/X1E bzw. Bambu-Lab-Support-Kontakt,
  falls sich alle Client-seitigen Optionen als wirkungslos erweisen.

  **v1.5.0 - GRUNDURSACHE GEFUNDEN UND BEHOBEN (per Recherche-Auftrag).**
  Da alle bisherigen Client-seitigen Experimente (TLS-Version, Session-
  Reuse-An/Aus, curl statt Python, verschiedene Blockgroessen/Pacing)
  ergebnislos blieben, wurde ein dedizierter Recherche-Auftrag gestartet
  (Web-Suche nach bekannten Bambu-X1-FTPS-Problemen, Analyse bestehender
  Open-Source-Bambu-Python-Bibliotheken). Ergebnis, durch mehrere
  unabhaengige Quellen bestaetigt:
  - Die **X1-Serie (X1C/X1E) laeuft intern auf vsftpd** mit aktivierter
    Option `require_ssl_reuse` (laut vsftpd.conf(5)-Manpage seit v2.1.0,
    Standard: an). Diese Option verlangt, dass die TLS-Sitzung der
    PASV-Datenverbindung nachweislich eine Fortsetzung der Sitzung der
    Kontrollverbindung ist - ein Schutz gegen Session-Hijacking. Quelle:
    **greghesp/ha-bambulab, GitHub Discussion #1497** ("ftp TLS session
    copy?", Aug 2025): "we've determined that the X1C is running vsftpd
    and vsftpd forces ssl session context reuse as a form of avoiding
    session hijack." Der server-seitige Fehlertext dafuer (`522 SSL
    connection failed; session reuse required`) ist im TFyre/bambu-farm-
    Repo sowie in einem Bambu-Forum-Thread ("Issues with ftp connection")
    dokumentiert.
  - **Pythons `ftplib.FTP_TLS.ntransfercmd()` uebergibt bereits
    standardmaessig `session=self.sock.session`** beim Aufbau der
    Datenverbindung - die Sitzung wird also korrekt wiederverwendet.
    ABER: `ftplib.FTP.storbinary()` ruft am ENDE der Uebertragung
    automatisch `conn.unwrap()` auf, wenn `conn` eine `SSLSocket` ist
    (bestaetigt durch Einsicht in den tatsaechlichen CPython-Quellcode,
    `inspect.getsource(ftplib.FTP.storbinary)` in diesem Projekt selbst
    ausgefuehrt). Das zerstoert die gemeinsame TLS-Sitzung in einer
    Weise, die vsftpds `require_ssl_reuse`-Pruefung nicht toleriert -
    exakt das beobachtete `ssl.SSLEOFError` ("EOF occurred in violation
    of protocol").
  - **Warum A1 Mini nicht betroffen war:** die A1/P1-Serie nutzt einen
    leichteren, ESP32-basierten FTPS-Server ohne diese strikte vsftpd-
    Pruefung (Quelle: ha-bambulab-Maintainer-Aussage in derselben
    Diskussion).
  - **Warum FileZilla immer funktionierte:** es fuehrt TLS-Session-
    Wiederverwendung durchgehend korrekt durch und unterlaesst das
    problematische abschliessende `unwrap()`.
  - **Community-Bestaetigung des Fixes:** mehrere bestehende Open-Source-
    Bambu-Python-Bibliotheken loesen exakt dieses Problem identisch:
    `greghesp/ha-bambulab` (`pybambu/models.py`) mit einer eigenen
    `storbinary_no_unwrap()`-Funktion; `bambulabs_api` (PyPI/GitHub,
    Version 2.6.6, Commit `5bd1e84`) mit einer explizit als "Add unwrap
    connection option" bezeichneten Ergaenzung.
  - **Zusaetzliche Bestaetigung (unabhaengiger Beleg fuer generelles
    Bambu-FTPS-Datenkanal-Verhalten):** BambuStudio GitHub Issue #1404
    ("Uploading files to the P1P via ftps hangs/resets... at ~256kb")
    zeigt, dass Bambu-Drucker-Firmware generell fuer reproduzierbare
    Abbrueche bei groesseren FTPS-Uploads bekannt ist, unabhaengig vom
    Client - konsistent mit dem hier beobachteten Verhalten.
  **Implementierte Aenderung:**
  - Neue Modul-Funktion `_storbinary_no_unwrap(ftp, cmd, fp, blocksize,
    callback)`: Nachbau von `ftplib.FTP.storbinary()`, aber OHNE das
    abschliessende `conn.unwrap()`. Wird in `_ftps_upload_once()` anstelle
    von `ftp.storbinary()` aufgerufen.
  - `_ftps_upload_once()`: TLS zusaetzlich wieder auf maximal Version 1.2
    begrenzt (`ctx.maximum_version = TLSv1_2`) - laut Recherche ist
    Session-Reuse bei TLS 1.2 (Session-ID-basiert) in der Praxis
    zuverlaessiger als bei TLS 1.3 (Session-Ticket-basiert) ueber zwei
    getrennte Sockets hinweg. **Wichtig:** diese Einschraenkung allein
    hatte in fruehen Versuchen (v1.2.0-v1.4.4) NICHT geholfen - sie wirkt
    laut Recherche nur in Kombination mit dem No-Unwrap-Fix.
  - `ImplicitFtpTls`: unveraendert (kein `ntransfercmd()`-Override mehr
    noetig, da Pythons Standardverhalten die Session bereits korrekt
    uebergibt - das eigentliche Problem lag ausschliesslich im
    `unwrap()`-Aufruf innerhalb von `storbinary()`).
  **Getestet (ohne echten Drucker):** Ein Mock-`SSLSocket`-Objekt
  verifiziert, dass `_storbinary_no_unwrap()` `unwrap()` NIE aufruft, alle
  Daten korrekt sendet, und dieselben FTP-Kommandos (`TYPE I`, `STOR ...`)
  wie das Original sendet; Quellcode-Vergleich mit dem echten
  `ftplib.FTP.storbinary()` (per `inspect.getsource()`) bestaetigt, dass
  der einzige strukturelle Unterschied das fehlende `unwrap()` ist;
  vollstaendiger Async-Confirm-Flow inkl. Progress-Polling weiterhin
  funktionsfaehig.

  **v1.5.0 WAR EINE FALSCHE FAEHRTE - siehe v1.5.1 unten fuer die
  tatsaechliche Ursache.** Der No-Unwrap-Fix aenderte beim echten Test
  gegen X1C NICHTS (exakt derselbe Byte-Abbruch bei 73728 wie vorher).
  Der Python-Bugtracker-Issue-31727-Fix (der kanonische, im Web breit
  zitierte Ursprung des "no unwrap"-Patterns) behebt nachweislich einen
  ANDEREN Fehler (Abbruch am ENDE einer Uebertragung/bei `nlst()`),
  nicht einen Abbruch WAEHREND der Uebertragung bei 11% - die
  Diagnose war also fuer ein aehnlich aussehendes, aber tatsaechlich
  anderes Problem korrekt, traf aber nicht das hier vorliegende.

  **v1.5.1 - ZWISCHENSCHRITT: Prozess-Isolation (loeste das Problem noch
  NICHT vollstaendig, siehe v1.5.2 fuer die tatsaechliche Loesung).** Um
  die vsftpd-Theorie aus v1.5.0 endgueltig zu pruefen, wurde ein KOMPLETT
  EIGENSTAENDIGES Diagnose-Skript erstellt (`ftps_test_minimal.py`, als
  exe via eigenem GitHub-Actions-Workflow `build-ftps-test.yml` gebaut,
  da der Nutzer keine `.py`-Dateien direkt ausfuehren kann) - voellig
  unabhaengig von Flask/MQTT/Threading, nur reines `ftplib`. Ergebnis,
  in zwei Schritten:
  1. Erster Testlauf (mit No-Unwrap-Trick): Datei wurde **VOLLSTAENDIG
     (100%) uebertragen**, brach aber bei der Abschluss-Bestaetigung
     mit `426 Failure reading network stream` ab - ein voellig anderes
     Symptom als der bisherige 11%-Abbruch! Das allein war schon der
     entscheidende Hinweis: ausserhalb der App kommt der Upload viel
     weiter als innerhalb.
  2. Zweiter Testlauf (Vergleichsskript mit ZWEI automatischen Tests:
     Test A = normales `unwrap()`, Test B = No-Unwrap-Trick):
     **Test A war ein VOLLSTAENDIGER ERFOLG** ("226 Transfer complete."),
     Test B scheiterte wie erwartet am Abschluss (426-Fehler).
  **Schlussfolgerung (zum damaligen Zeitpunkt, spaeter praezisiert):**
  Standard-`ftplib`-Verhalten funktioniert einwandfrei, WENN es
  ausserhalb der App als eigener Prozess laeuft. Vermutung war zunaechst
  **Ressourcen-/Scheduling-Konkurrenz zwischen zwei Python-Threads im
  selben Prozess** (GIL-Kontention waehrend TLS-Handshake-Schritten).
  **Implementierte Aenderung (v1.5.1):**
  - `_storbinary_no_unwrap()` entfernt, `ImplicitFtpTls` wieder auf
    reines Standardverhalten zurueckgesetzt (kein Override mehr noetig).
  - **Der komplette FTPS-Upload laeuft seitdem in einem eigenen
    Betriebssystem-PROZESS statt einem Thread.** Neue Funktion
    `_run_ftps_upload_worker(argv)`: fuehrt NUR den Upload durch (kein
    Flask, kein MQTT, keine `DashboardApp`), meldet Fortschritt/Ergebnis
    als JSON-Zeilen auf stdout. Ausgeloest ueber einen Sentinel-
    Kommandozeilen-Parameter `--ftps-upload-worker <ip> <access_code>
    <datei> <ziel>`, mit dem sich die exe/das Skript selbst per
    `subprocess.Popen([sys.executable, ...])` erneut aufruft.
  - **Wichtig fuer die Code-Struktur:** Der Sentinel-Check
    (`if len(sys.argv) > 1 and sys.argv[1] == "--ftps-upload-worker":
    ... sys.exit(0)`) sitzt bewusst ganz frueh im Modul, DIREKT nach der
    `ImplicitFtpTls`-Klasse und VOR `dash = DashboardApp()` - andernfalls
    wuerde der Kindprozess unnoetig auch alle Drucker-Verbindungen
    aufbauen und einen zweiten Flask-Server versuchen zu starten. Bei
    kuenftigen Refactorings diese Reihenfolge unbedingt beibehalten.
  - `PrinterConnection._ftps_upload_once()` startet den Subprozess,
    liest dessen stdout zeilenweise (JSON: `{"type": "progress", ...}`,
    `{"type": "done", ...}`, `{"type": "error", ...}`) und uebersetzt
    das in `on_progress()`-Aufrufe bzw. eine `RuntimeError` mit Byte-
    Stand, exakt wie vorher aus Sicht des Aufrufers (`send_print()`,
    `DashboardApp.start_confirm_print_job()` etc. mussten NICHT
    angepasst werden - gilt weiterhin in v1.5.2).
  - Diagnose-Tool `ftps_test_minimal.py` (Version 2, mit automatischem
    A/B-Vergleichstest) plus `.github/workflows/build-ftps-test.yml`
    wurden dem Nutzer separat als eigenstaendiges Mini-Repo/Zip
    bereitgestellt - nicht Teil des Haupt-Dashboards, aber nuetzlich
    fuer aehnliche Diagnosen in Zukunft.

  **v1.5.2 - TATSAECHLICHE URSACHE: gleichzeitige MQTT- + FTPS-
  Verbindung, nicht Python-Threading.** Beim echten Test gegen X1C
  scheiterte der Upload trotz vollstaendiger Prozess-Isolation (v1.5.1)
  ERNEUT, mit demselben Byte-Bereich (65536-73728) wie zuvor. Das
  widerlegt die GIL-/Thread-Kontentions-Theorie aus v1.5.1 endgueltig:
  ein komplett separater Betriebssystem-Prozess kann per Definition
  nicht am Python-GIL des Hauptprozesses "hungern". Was in ALLEN
  bisherigen Versuchen (Thread wie Prozess) unveraendert blieb: die
  MQTT-Verbindung im Hauptprozess lief durchgehend weiter, waehrend die
  FTPS-Datenverbindung parallel dazu aufgebaut wurde. Das Standalone-
  Diagnoseskript aus v1.5.1 hatte dagegen NIE eine MQTT-Verbindung
  offen. **Schlussfolgerung: der Drucker (X1-Serie) kann eine aktive
  MQTT-Verbindung und eine neue, datenintensive FTPS-Verbindung
  offenbar nicht zuverlaessig gleichzeitig bedienen** - vermutlich eine
  Einschraenkung des eingebetteten Netzwerk-Stacks bei gleichzeitiger
  Auslastung durch zwei TLS-Sitzungen. Das erklaert auch, warum A1 Mini
  nicht betroffen ist (vermutlich robusterer Netzwerk-Stack) und warum
  FileZilla/das Standalone-Testskript immer funktionierten (dort war nie
  eine parallele MQTT-Verbindung zum selben Drucker aktiv).
  **Implementierte Aenderung:**
  - `PrinterConnection` bekommt drei neue Methoden: `pause_mqtt()`
    (trennt die MQTT-Verbindung und unterdrueckt automatisches
    Reconnect via ein neues `self._paused`-Flag, das `_connect_loop()`
    respektiert), `resume_mqtt()` (hebt die Pause wieder auf), und
    `wait_for_mqtt_reconnect(timeout)` (blockierendes Warten bis
    `status["connected"]` wieder `True` ist, mit Timeout).
  - `send_print()` ruft jetzt `pause_mqtt()` VOR dem FTPS-Upload auf.
    Bei **Erfolg** wird `resume_mqtt()` + `wait_for_mqtt_reconnect(15)`
    aufgerufen, BEVOR `_request_print()` (das MQTT-Kommando fuer den
    Druckstart) gesendet wird - die Verbindung muss dafuer wieder aktiv
    sein. Bei **Fehlschlag** wird `resume_mqtt()` zwar auch aufgerufen
    (Verbindung soll sich im Hintergrund von selbst erholen), aber
    bewusst NICHT blockierend auf den Reconnect gewartet - der Fehler
    soll dem Nutzer sofort angezeigt werden, nicht erst nach bis zu 15s
    zusaetzlicher Wartezeit (siehe Test unten, das hat die Fehler-
    Rueckmeldung von ca. 20s auf ca. 5s beschleunigt).
  - `_connect_loop()` prueft `self._paused` am Anfang jeder Iteration
    und ueberspringt in dem Fall den Verbindungsaufbau komplett (statt
    wie vorher automatisch nach wenigen Sekunden neu zu verbinden).
  **Getestet (ohne echten Drucker):** Isolierte Tests fuer
  `pause_mqtt()`/`resume_mqtt()`/`wait_for_mqtt_reconnect()` mit einem
  Fake-MQTT-Client (verifiziert: Disconnect wird ausgeloest, Status
  wird korrekt gesetzt, Timeout-Verhalten korrekt); Test, dass
  `_connect_loop()` waehrend der Pause KEINEN Verbindungsversuch
  unternimmt; Test, dass nach `resume_mqtt()` automatisch neu verbunden
  wird; Test der Aufrufreihenfolge in `send_print()` (pause → Upload →
  bei Erfolg: resume + wait, bei Fehler: nur resume, kein wait) per
  Mock; vollstaendiger Async-Confirm-Flow-Test bestaetigt sowohl die
  korrekte Funktion als auch die beschleunigte Fehler-Rueckmeldung
  (ca. 5s statt vorher ca. 20s bei einem fehlgeschlagenen Upload).
  **Ein Test gegen einen echten X1C/X1E mit dieser MQTT-Pause-Loesung
  konnte in dieser Umgebung nicht durchgefuehrt werden** - Bestaetigung
  durch den Nutzer steht zum Zeitpunkt dieser Übergabe noch aus. Sollte
  auch das nicht helfen, waere der naechste Verdacht ein generelleres
  Netzwerk-/Bandbreitenproblem statt einer reinen Verbindungsanzahl-
  Beschraenkung - dann waere ein Wireshark-Mitschnitt waehrend eines
  Uploads (mit UND ohne aktive MQTT-Verbindung, zum direkten Vergleich)
  der naechste sinnvolle Schritt.
  **v1.5.2 WAR ERNEUT EINE FALSCHE FAEHRTE - siehe v1.5.3 unten fuer die
  tatsaechliche, bestaetigte Ursache.** Trotz MQTT-Pause scheiterte der
  Upload beim echten Test auf X1C wieder exakt identisch (73728 Bytes),
  was die "gleichzeitige Verbindung"-Theorie ebenfalls widerlegte.

  **v1.5.3 - TATSAECHLICHE, BESTAETIGTE URSACHE: Selbstaufruf-Muster
  wird von Windows Defender als verdaechtig eingestuft.** Der
  entscheidende Vergleichstest: Nutzer fuehrte auf einem komplett
  isolierten Testnetzwerk (nur Windows Defender, kein Firmen-Proxy/AV)
  mit EXAKT DERSELBEN DATEI nacheinander (a) das Dashboard und (b) das
  eigenstaendige Diagnose-Tool (`ftps_test_minimal.py`/`FtpsTest.exe`)
  aus. Ergebnis: **Dashboard scheiterte identisch bei 73728 Bytes (11%),
  das Standalone-Tool uebertrug im selben Moment, im selben Netzwerk,
  mit derselben Datei erfolgreich 100% ("226 Transfer complete").** Das
  schliesst Netzwerk, Firmen-Sicherheitssoftware UND jede TLS-/Threading-
  /Verbindungs-Theorie endgueltig aus - der einzige verbleibende
  Unterschied zwischen beiden war der Programm-Aufrufmechanismus:
  - Standalone-Tool: normaler Programmstart durch den Nutzer (Doppelklick).
  - Dashboard (bis v1.5.2): rief sich SELBST mit einem versteckten
    Kommandozeilen-Argument (`--ftps-upload-worker`) erneut auf, um den
    Upload in einem separaten Prozess durchzufuehren (die Prozess-
    Isolation aus v1.5.1 war technisch korrekt umgesetzt - nur der
    AUFRUFMECHANISMUS war das eigentliche Problem, nicht die
    Prozess-Isolation an sich).
  **Erklaerung:** Ein Programm, das eine Kopie von sich selbst mit einem
  versteckten Kommandozeilen-Flag startet, ist ein Verhaltensmuster, das
  Sicherheitssoftware wie Windows Defender aehnlich wie manche
  Schadsoftware-Lademechanismen (z. B. Dropper/Loader-Patterns)
  behandeln kann - mit moeglichen Auswirkungen auf den Netzwerkverkehr
  des betroffenen Prozesses (z. B. durch Echtzeitueberwachung/AMSI-
  Scanning, das TLS-Handshake-Timing stoert), OHNE dass irgendetwas
  sichtbar blockiert oder eine Warnung angezeigt wird - was erklaert,
  warum dieses Verhalten so schwer zu diagnostizieren war.
  **Implementierte Aenderung:**
  - Neue Datei `ftps_upload_helper.py`: eigenstaendiges Skript mit der
    kompletten FTPS-Upload-Logik (eigene, minimale Kopie von
    `ImplicitFtpTls` + Hauptfunktion), das JSON-Fortschritts-/
    Ergebniszeilen auf stdout ausgibt - vom Aufruf-Interface her
    identisch zum bisherigen `_run_ftps_upload_worker()`.
  - Neue Funktion `_find_ftps_upload_helper()` in `app.py`: sucht nach
    `FtpsUploadHelper.exe` (Windows) bzw. `FtpsUploadHelper` (macOS/
    Linux) im selben Ordner wie die Haupt-exe (`base_dir()`).
  - `PrinterConnection._ftps_upload_once()`: ruft jetzt bevorzugt die
    gefundene Helfer-exe direkt auf (`subprocess.Popen([helper_path,
    ip, access_code, local_path, remote_name])`) - KEIN Selbstaufruf
    mehr. Der alte Sentinel-Mechanismus (`_run_ftps_upload_worker()` +
    der frueh im Modul plazierte `--ftps-upload-worker`-Check) bleibt
    als Fallback bestehen, falls die Helfer-exe (noch) nicht gefunden
    wird (z. B. im Entwicklungsbetrieb ohne vorherigen Build, oder
    falls jemand nur `app.py` ohne die separate Helfer-exe verteilt).
  - `pause_mqtt()`/`resume_mqtt()`/`wait_for_mqtt_reconnect()` aus
    v1.5.2 wurden NICHT zurueckgebaut - sie schaden nicht und bleiben
    als zusaetzliche, risikoarme Vorsichtsmassnahme bestehen (auch wenn
    sie sich als nicht ursaechlich fuer das eigentliche Problem erwiesen
    haben).
  - **Build-Workflow (`build-exe.yml`) grundlegend angepasst:** baut
    jetzt PRO PLATTFORM zwei Executables (`DruckerDashboard` +
    `FtpsUploadHelper`) und packt beide gemeinsam in ein Zip, da sie im
    selben Ordner ausgeliefert werden muessen (`_find_ftps_upload_helper()`
    sucht relativ zum Ordner der Haupt-exe). Windows nutzt dafuer
    PowerShells eingebautes `Compress-Archive` (keine zusaetzliche
    Tool-Abhaengigkeit), macOS weiterhin `zip -j` (bewahrt das
    Exec-Bit fuer beide Binaries).
  **Getestet (ohne echten Drucker):** `_find_ftps_upload_helper()` mit
  und ohne vorhandene Helfer-Datei verifiziert; `_ftps_upload_once()`
  mit einem Fake-Helfer-Skript, das die JSON-Kommunikation exakt
  nachbildet (Progress + Done) - bestaetigt, dass die Helfer-exe
  bevorzugt und korrekt angesprochen wird; Fallback-Pfad (kein Helfer
  vorhanden) weiterhin funktionsfaehig; vollstaendiger Async-Confirm-
  Flow-Test weiterhin erfolgreich. **Ein Test gegen einen echten
  X1C/X1E mit dieser Loesung konnte in dieser Umgebung nicht
  durchgefuehrt werden** - Bestaetigung durch den Nutzer stand zum
  Zeitpunkt dieser Übergabe noch aus, ist aber durch den vorangegangenen
  direkten A/B-Vergleichstest des Nutzers (Standalone-Tool vs.
  damaliges Dashboard, identische Datei/Netzwerk) außergewöhnlich gut
  abgesichert - das war der erste Fall in der gesamten Debugging-
  Chronologie, bei dem der einzige verbleibende Unterschied klar
  identifizierbar UND eine bekannte, dokumentierte Klasse von Sicherheits-
  software-Verhalten war (nicht nur eine plausible Theorie).

  **v1.5.3 WAR EBENFALLS EINE FALSCHE FAEHRTE - siehe v1.5.4 unten fuer
  die tatsaechliche, endgueltig bestaetigte Ursache.** Der Nutzer testete
  `FtpsUploadHelper.exe` komplett eigenstaendig (Dashboard vollstaendig
  geschlossen, Helfer-exe manuell von der Kommandozeile mit den
  Positions-Argumenten aufgerufen) - und selbst DANN scheiterte der
  Upload identisch bei 73728 Bytes. Das widerlegte die "Selbstaufruf-
  Muster wird als verdaechtig eingestuft"-Theorie endgueltig: die
  Helfer-exe ist ein voellig normales, unabhaengig gestartetes Programm
  ohne jeden Bezug zum Dashboard-Prozess, und scheiterte trotzdem exakt
  gleich.

  **v1.5.4 - TATSAECHLICHE, ENDGUELTIG BESTAETIGTE URSACHE: fehlende
  TLS-Session-Wiederverwendung - eine SELBST VERURSACHTE Regression.**
  Nachdem auch die separate Helfer-exe eigenstaendig scheiterte, blieb
  nur noch ein direkter Code-Vergleich zwischen der scheiternden
  `ftps_upload_helper.py` und dem erfolgreichen `ftps_test_minimal.py`
  (Test A). Der entscheidende Unterschied: `ftps_test_minimal.py`
  ueberschreibt `ntransfercmd()` explizit mit
  `session=self.sock.session`, waehrend `ftps_upload_helper.py` (und
  `app.py`s `ImplicitFtpTls` seit v1.4.5) KEIN solches Override hatte,
  in der Annahme, Pythons `ftplib.FTP_TLS.ntransfercmd()` wuerde das
  bereits automatisch tun. **Diese Annahme war schlicht falsch** -
  verifiziert per `inspect.getsource(ftplib.FTP_TLS.ntransfercmd)`
  direkt in diesem Projekt (Python 3.12): die eingebaute Methode
  uebergibt beim Wrap der Datenverbindung nur `server_hostname=self.host`,
  OHNE jedes `session=`-Argument. Es fand also seit v1.4.5 (als das
  urspruengliche `ntransfercmd()`-Override entfernt wurde) UEBERHAUPT
  KEINE TLS-Session-Wiederverwendung mehr fuer die Datenverbindung
  statt - fuer die X1-Serie (vsftpd mit `require_ssl_reuse`, siehe
  v1.5.0-Recherche weiter oben) fatal.
  **Das bedeutet: die urspruengliche vsftpd/Session-Reuse-Diagnose aus
  v1.5.0 war INHALTLICH KORREKT.** Sie wurde damals nur falsch
  umgesetzt und getestet: `_storbinary_no_unwrap()` (v1.5.0) entfernte
  zwar das problematische `unwrap()` am Ende, ergaenzte aber NIE die
  fehlende Session-Wiederverwendung beim Verbindungsaufbau (da zu dem
  Zeitpunkt faelschlich angenommen wurde, das sei bereits Standard-
  verhalten). Der v1.5.0-Test war also faktisch ein Test von "kein
  `unwrap()` UND weiterhin keine Session-Wiederverwendung" - beide
  fehlerhaft dokumentierten/ungetesteten Annahmen zusammen fuehrten zur
  falschen Schlussfolgerung "vsftpd-Theorie widerlegt".
  **Implementierte Aenderung:**
  - `ImplicitFtpTls` in `app.py` UND `ftps_upload_helper.py` bekommt
    wieder ein `ntransfercmd()`-Override, das `session=self.sock.session`
    beim Wrap der Datenverbindung uebergibt - exakt der Code, der im
    Diagnose-Testskript (Test A) nachweislich funktioniert hat. Normales
    `unwrap()`-Verhalten (kein Override von `storbinary()` mehr noetig)
    bleibt bestehen, ebenfalls wie in Test A.
  - Beide Docstrings wurden korrigiert, um die widerlegte "ist bereits
    Standardverhalten"-Annahme zu entfernen und stattdessen explizit auf
    die Verifikation per `inspect.getsource()` zu verweisen - falls
    jemand in Zukunft wieder versucht sein sollte, dieses Override als
    "unnoetig" zu entfernen, sollte der Docstring das verhindern.
  **Getestet (ohne echten Drucker):** `inspect.getsource()`-basierte
  Tests bestaetigen sowohl fuer `app.py` als auch `ftps_upload_helper.py`,
  dass `ntransfercmd` jetzt ueberschrieben ist und `session=self.sock.session`
  sowie `server_hostname=self.host` enthaelt; vollstaendiger Async-
  Confirm-Flow-Test weiterhin erfolgreich. **Ein Test gegen einen echten
  X1C/X1E mit dieser Loesung konnte in dieser Umgebung nicht durchgefuehrt
  werden**, ist aber die bislang am besten abgesicherte Loesung der
  gesamten Chronologie: sie entspricht buchstaeblich dem vom Nutzer selbst
  verifizierten, erfolgreichen Referenz-Code (Test A aus
  `ftps_test_minimal.py`), Zeile fuer Zeile.
  **KORRIGIERTES Lesson Learned (das vorherige, in v1.5.3 dokumentierte
  "Lesson Learned" war selbst Teil der Fehleinschaetzung und wird hier
  ersetzt):** Der eigentliche Fehler zog sich durch mehrere Versionen:
  in v1.4.5 wurde eine Code-Vereinfachung (Entfernen des `ntransfercmd()`-
  Overrides) vorgenommen, gestuetzt auf eine NICHT VERIFIZIERTE Annahme
  ueber Pythons Standardverhalten. Diese unbelegte Annahme wurde
  anschliessend ueber mehrere weitere Versionen (v1.4.5 bis v1.5.3)
  unhinterfragt fortgeschrieben, obwohl sie bei jeder folgenden
  Fehlersuche staendig neu haette challenged werden koennen. Erst der
  Vergleich mit dem Nutzer-eigenen, tatsaechlich funktionierenden Referenz-
  Code (nicht mit einer Web-Recherche oder einer weiteren Theorie) deckte
  die falsche Annahme auf. **Die zentrale Lektion:** Aussagen ueber das
  Verhalten von Standardbibliotheken ("X macht das bereits automatisch")
  sollten nicht aus Erinnerung/Training uebernommen, sondern bei
  sicherheitsrelevanten oder fehleranfaelligen Code-Pfaden aktiv mit
  `inspect.getsource()` oder aehnlichen Mitteln gegen die tatsaechlich
  installierte Version verifiziert werden - besonders wenn genau diese
  Annahme die Grundlage fuer das Entfernen von Code ist. Ein einziger
  `inspect.getsource(ftplib.FTP_TLS.ntransfercmd)`-Aufruf haette diesen
  gesamten Irrweg (v1.4.5 bis v1.5.3, mehrere fehlgeschlagene
  Alternativ-Theorien) von Anfang an vermieden.

  **v1.5.5 - Folgefehler nach erfolgreichem FTPS-Fix: falsche AMS-
  Zuordnung bei Verbundwerkstoffen.** Nachdem der FTPS-Upload seit
  v1.5.4 zuverlaessig funktioniert (vom Nutzer fuer PLA auf X1C und X1E
  bestaetigt), meldete der Nutzer ein neues, unabhaengiges Problem:
  Drucke mit **ASA-CF** wurden korrekt uebertragen und gestartet,
  blieben dann aber beim Materialladen haengen. Nach Ausschluss von
  Hardware-Ursachen (gehaertete Duese vorhanden, keine AMS-HT
  angeschlossen) fiel bei Code-Review auf: `_find_matching_tray()`
  verglich Materialtypen per reinem Teilstring-Test
  (`want_type not in tray_type and tray_type not in want_type`) - das
  hat einen gefaehrlichen blinden Fleck, da "ASA" ein Teilstring von
  "ASA-CF" ist (ebenso "PLA" in "PLA-CF", "PETG" in "PETG-CF" usw.).
  Ein Fach mit reinem ASA konnte dadurch bei uebereinstimmender Farbe
  faelschlich als passende automatische Zuordnung fuer ein ASA-CF-
  Filament vorgeschlagen werden. Wurde dieser Vorschlag vom Nutzer
  uebernommen (Standard-Verhalten im Dialog), sendete das Dashboard die
  falsche Fach-Nummer an den Drucker; beim Laden erkennt der RFID-Chip
  im Fach ein anderes Material als im Slicer hinterlegt, was am Drucker
  typischerweise eine Bestaetigungs-Abfrage auf dem Display ausloest -
  ohne jemanden vor Ort sieht das wie ein Haengenbleiben aus.
  **Implementierte Aenderung:** Neue Funktion `_types_compatible(want_type,
  tray_type)` ersetzt die rohe Teilstring-Pruefung in
  `_find_matching_tray()`. Logik: beide Typ-Strings werden am ersten "-"
  in Basis-Name und Suffix aufgeteilt (`"ASA-CF".partition("-")` →
  Basis `"ASA"`, Suffix `"CF"`); **die Suffixe muessen exakt
  uebereinstimmen** (leerer Suffix bei unverstaerkten Materialien zaehlt
  als eigener Wert, der nicht zu einem gefuellten Suffix passt), erst
  DANACH darf der Basis-Name weiterhin locker verglichen werden (fuer
  Faelle wie "PLA" vs. "PLA BASIC", die weiterhin funktionieren sollen).
  Das schliesst systematisch alle Verbundwerkstoff-Kombinationen aus
  (PLA-CF, PETG-CF, PA-CF, ABS-GF, PPS-CF usw. koennen nie mehr mit
  ihrer unverstaerkten Grundvariante verwechselt werden), nicht nur den
  konkret gemeldeten ASA/ASA-CF-Fall.
  **Getestet:** `_types_compatible()` isoliert fuer alle relevanten
  Faelle (ASA vs. ASA-CF in beide Richtungen falsch; PLA-CF, PETG-CF,
  PA-CF, ABS-GF vs. ihre Grundvariante ebenfalls falsch; exakte Matches
  weiterhin wahr; lockere Basis-Matches ohne Suffix wie "PLA"/"PLA
  BASIC" weiterhin wahr; gleiches Suffix mit lockerer Basis wie
  "PLA-CF"/"PLA BASIC-CF" weiterhin wahr; leere Typen weiterhin nicht
  blockierend). `_find_matching_tray()` mit dem exakten Bug-Szenario
  (schwarzes ASA-CF-Filament, AMS hat sowohl ein schwarzes ASA- als
  auch ein schwarzes ASA-CF-Fach): waehlt jetzt korrekt das ASA-CF-Fach,
  ueberspringt das ASA-Fach trotz Farb-Uebereinstimmung. Vollstaendiger
  End-to-End-Test ueber `POST /print/prepare` mit derselben Ausgangslage
  bestaetigt die korrekte Vorauswahl (`suggested_tray`) bis in die
  tatsaechliche API-Antwort hinein.
  **Fuer die Weiterarbeit:** Dieselbe Problemklasse (Teilstring-
  Ueberschneidungen) koennte theoretisch auch bei anderen, bisher nicht
  bekannten Bambu-Materialbezeichnungen mit anderer Suffix-Konvention
  auftreten (z. B. falls Bambu je ein Material ohne "-" als Trenner
  einfuehrt, das trotzdem eine Verbundwerkstoff-Variante ist) - aktuell
  nicht bekannt, aber falls in Zukunft ein aehnliches Symptom mit einem
  anderen Materialpaar auftritt, zuerst `_types_compatible()` mit den
  konkreten Typ-Strings durchtesten, bevor eine neue Ursache vermutet
  wird.

  **v1.5.6 - Folgefehler nach v1.5.5: AMS-Zuordnung war schon korrekt,
  trotzdem Haengenbleiben beim Materialladen.** Der Nutzer meldete
  zurueck: das ASA-CF-Fach wurde bereits in v1.5.4 korrekt vorgeschlagen
  (der Drucker hatte tatsaechlich ASA-CF geladen) - die v1.5.5-Diagnose
  (Verbundwerkstoff-Verwechslung) war also fuer DIESEN konkreten Fall
  nicht die Ursache (der Fix selbst bleibt trotzdem sinnvoll fuer den
  allgemeinen Fall). Wichtige Zusatzinfo vom Nutzer: keine
  Fehlermeldung am Display, Material wurde schon mehrfach erfolgreich
  gedruckt (kein grundsaetzliches Erstdruck-Problem). Da eine "falsche
  AMS-Zuordnung mit RFID-Mismatch" typischerweise eine sichtbare
  Bestaetigungs-Abfrage ausloest, aber KEINE Fehlermeldung auftrat,
  wurde der Verdacht auf das MQTT-Kommando selbst gelenkt: ein
  Vergleich des tatsaechlich gesendeten `project_file`-Befehls mit
  mehreren unabhaengig dokumentierten, als "funktioniert zuverlaessig"
  bestaetigten Referenz-Payloads (Cinder's Blog "Bambu AMS Filament
  Mapping"; Doridian/OpenBambuAPI auf GitHub) zeigte: unser Befehl
  enthielt nur eine Teilmenge der Felder, die Bambu Studio selbst
  sendet. Insbesondere fehlte **`bed_type`** komplett - ohne dieses
  Feld ist unklar, welchen Druckbett-Typ die Firmware fuer den
  weiteren Startablauf annimmt, was bei anspruchsvolleren Materialien
  (hoehere Bett-/Duesentemperatur, wie ASA-CF) eher zu Problemen fuehren
  kann als bei unkritischeren Materialien wie PLA - was zur beobachteten
  Materialabhaengigkeit passt. Ebenfalls fehlten `subtask_name`,
  `project_id`, `profile_id`, `task_id` (laut OpenBambuAPI-Spezifikation
  fuer lokale Drucke immer `"0"`, aber offenbar Teil des vollstaendigen,
  von der Firmware erwarteten Befehlsformats).
  **Implementierte Aenderung:** `_request_print()` sendet jetzt den
  vollstaendigen, dokumentierten Feldsatz: `"bed_type": "auto"` (laesst
  die Firmware selbst anhand der eingelegten Druckplatte entscheiden -
  die sicherste Wahl, keine Annahme ueber die tatsaechlich verwendete
  Platte), `"subtask_name"` (Auftragsname, aus dem Dateinamen ohne
  `.gcode.3mf`-Endung abgeleitet - zusaetzlicher Vorteil: der Drucker
  zeigt jetzt einen sinnvollen Namen statt eines leeren/generischen
  Werts an), sowie `"project_id"`, `"profile_id"`, `"task_id"` (alle
  `"0"`, wie fuer lokale/nicht-Cloud-Drucke dokumentiert).
  **Getestet (ohne echten Drucker):** vollstaendige Payload-Struktur
  gegen einen simulierten MQTT-Client verifiziert (alle neuen Felder
  korrekt gesetzt, `ams_mapping`/`use_ams` weiterhin korrekt aus der
  Nutzer-Zuordnung uebernommen); `subtask_name`-Extraktion fuer mehrere
  Dateinamen-Varianten getestet (inkl. Namen mit mehreren Punkten);
  vollstaendiger End-to-End-Test ueber `send_print()`. **Ein Test gegen
  einen echten Drucker mit ASA-CF konnte in dieser Umgebung nicht
  durchgefuehrt werden** - Bestaetigung durch den Nutzer stand zum
  Zeitpunkt dieser Übergabe noch aus.
  **Fuer die Weiterarbeit, falls der Fehler nach v1.5.6 weiterhin
  auftritt:** Ein MQTT-Sniffer (z. B. MQTT Explorer, mosquitto_sub)
  parallel zu Bambu Studio mitlaufen lassen und den *tatsaechlich* von
  Bambu Studio gesendeten `project_file`-Befehl fuer denselben Druck
  direkt mit unserem vergleichen (Byte-fuer-Byte-JSON-Diff) waere der
  naechste, praeziseste Schritt - zuverlaessiger als weitere
  Community-Referenz-Payloads zu vergleichen, da es den tatsaechlichen
  Befehl DIESES Druckers/dieser Firmware-Version zeigt.

  **v1.5.7 - X1C/X1E jetzt vom Nutzer bestaetigt funktionsfaehig, dafuer
  A1 Mini kaputt: echter Zielkonflikt zwischen Druckerfamilien
  entdeckt.** Der Nutzer bestaetigte: X1C und X1E uebertragen und
  starten Drucke jetzt zuverlaessig (v1.5.4-v1.5.6 haben ihr Ziel
  erreicht). ABER: der A1 Mini, der laut Nutzer in einer fruehen
  Version (vor der Session-Reuse-Einfuehrung in v1.5.4) bereits
  einwandfrei funktioniert hatte, scheiterte jetzt neu mit einem
  bisher unbekannten Fehlerbild: `The read operation timed out` -
  und zwar erst bei **exakt 100% uebertragenen Bytes** (`390206/390206`).
  Das ist ein voellig anderes Symptom als der X1-Abbruch (der brach
  waehrend der Uebertragung bei ~11% ab) - hier wird die komplette
  Datei erfolgreich gesendet, aber das Lesen der Server-Abschluss-
  bestaetigung (die "226 Transfer complete"-Antwort) blockiert bis zum
  Timeout. **Ursache:** Die in v1.5.4 eingefuehrte TLS-Session-
  Wiederverwendung (`session=self.sock.session` in `ntransfercmd()`),
  die fuer die X1-Serie zwingend noetig ist (vsftpd mit
  `require_ssl_reuse`), scheint beim A1 Mini genau umgekehrt zu wirken:
  sein leichterer, vermutlich ESP32-basierter FTPS-Server kommt mit
  einer wiederverwendeten TLS-Sitzung fuer die Datenverbindung nicht
  klar und schliesst die Verbindung nach der Uebertragung nicht wie
  erwartet ab (oder sendet die Abschluss-Antwort nicht in einer Weise,
  die unser Client noch korrekt zuordnen kann). **Beide Druckerfamilien
  brauchen also nachweislich GEGENSAETZLICHES Verhalten** - es gibt
  keine einzelne Einstellung, die fuer beide gleichzeitig korrekt ist.
  **Implementierte Aenderung:**
  - `ImplicitFtpTls` (in `app.py` UND `ftps_upload_helper.py`) bekommt
    einen neuen Konstruktor-Parameter `reuse_session: bool = True`.
    `ntransfercmd()` uebergibt `session=self.sock.session` nur noch,
    wenn `reuse_session` gesetzt ist; sonst wird die Datenverbindung wie
    vor v1.5.4 ohne Sitzungs-Wiederverwendung gewrappt.
  - `ftps_upload_helper.py`s `main()` akzeptiert ein optionales 5.
    Kommandozeilen-Argument ("1"/"0") fuer `reuse_session` (Standard
    "1", falls weggelassen - fuer Abwaertskompatibilitaet bei manuellem
    Aufruf). Analog fuer `_run_ftps_upload_worker()` in `app.py` (der
    Fallback-Sentinel-Mechanismus, falls die Helfer-exe fehlt).
  - `PrinterConnection._ftps_upload()` (der 3-Versuche-Retry-Wrapper)
    **alterniert jetzt zwischen den Versuchen**: Versuch 1 = mit
    Sitzungs-Wiederverwendung (`reuse_pattern = [True, False, True]`),
    Versuch 2 = ohne, Versuch 3 = wieder mit. Dadurch wird garantiert
    innerhalb der 3 Versuche fuer JEDES der beiden bekannten
    Druckerverhalten die passende Variante gefunden, ohne dass das
    Dashboard das Druckermodell vorher kennen muss. Die Fehlermeldung
    bei einem endgueltigen Fehlschlag nennt jetzt zusaetzlich, welche
    Variante bei welchem Versuch verwendet wurde (z. B. "Versuch 1 (mit
    Sitzungs-Wiederverwendung): ...").
  - `PrinterConnection._ftps_upload_once()` bekommt einen neuen
    Parameter `reuse_session: bool = True`, reicht ihn als 5. CLI-
    Argument an die Helfer-exe bzw. den Sentinel-Fallback durch.
  **Getestet (ohne echten Drucker):** Zwei Fake-Helfer-Skripte simulieren
  jeweils ein Druckerverhalten exakt nachgebildet vom real gemeldeten
  Symptom: (1) "A1-Mini-artig" - schlaegt bei `reuse=1` mit dem exakten
  gemeldeten Timeout-Fehler fehl, gelingt bei `reuse=0`; (2) "X1-artig"
  - schlaegt bei `reuse=0` fruehzeitig fehl (analog zum urspruenglichen
  X1-Symptom), gelingt bei `reuse=1`. In BEIDEN Faellen findet
  `_ftps_upload()` durch die Alternierung automatisch die passende
  Variante innerhalb der 3 Versuche, ohne manuelles Eingreifen. Fehler-
  Fall (beide Varianten schlagen fehl) zeigt korrekt beide Label in der
  zusammengefassten Fehlermeldung. Vollstaendiger Async-Confirm-Flow-
  Test weiterhin erfolgreich, inkl. Pruefung, dass die Fehlermeldung im
  Fehlerfall die neuen Label enthaelt.
  **Ein Test gegen einen echten A1 Mini mit dieser Loesung konnte in
  dieser Umgebung nicht durchgefuehrt werden** - Bestaetigung durch den
  Nutzer stand zum Zeitpunkt dieser Übergabe noch aus. Die X1C/X1E-
  Funktionsfaehigkeit sollte durch die Alternierung nicht negativ
  beeinflusst werden (Versuch 1 bleibt unveraendert "mit Reuse", was
  fuer die X1-Serie bereits nachweislich funktioniert - im Idealfall
  aendert sich fuer X1-Nutzer also gar nichts spuerbar, ausser dass der
  A1-Mini-Fall jetzt zusaetzlich abgedeckt ist).
  **Fuer die Weiterarbeit:** Sollte sich herausstellen, dass es noch
  weitere Druckermodelle mit einem DRITTEN, bisher unbekannten
  FTPS-Verhalten gibt, das mit BEIDEN Alternierungs-Varianten
  scheitert, waere der naechste Schritt, das erfolgreiche Verhalten
  fuer dieses Modell separat zu diagnostizieren (analog zum bisherigen
  Vorgehen: isoliertes Testskript, dann Vergleich) und ggf. eine
  dritte Variante in die Alternierung aufzunehmen (z. B. `reuse_pattern
  = [True, False, True]` auf eine laengere Sequenz erweitern, falls 3
  Versuche fuer 3 unterschiedliche Druckerverhalten nicht mehr reichen).
  Denkbar waere auch, das erfolgreiche `reuse_session`-Verhalten pro
  Drucker-Seriennummer in `config.json` zu merken (kein Neuraten bei
  jedem Druck mehr noetig) - aktuell nicht implementiert, da die
  Alternierung selbst bereits ausreichend zuverlaessig und einfach ist.

  **v1.5.8 - v1.5.7 WAR UNVOLLSTAENDIG: A1-Mini-Timeout trat AUCH ohne
  Sitzungs-Wiederverwendung auf, echte Ursache lag (auch) am TLS-
  Versions-Deckel.** Der Nutzer bestaetigte: X1C funktioniert weiterhin
  einwandfrei, der A1 Mini scheiterte aber weiterhin identisch - UND
  ZWAR BEI ALLEN 3 VERSUCHEN, also auch bei Versuch 2 (ohne Sitzungs-
  Wiederverwendung). Das widerlegt die alleinige "Sitzungs-
  Wiederverwendung ist die A1-Mini-Ursache"-Theorie aus v1.5.7
  eindeutig: der Timeout nach 100% uebertragenen Bytes trat identisch
  mit UND ohne `reuse_session` auf. Beim erneuten Abgleich mit der
  zuletzt beim Nutzer bestaetigt funktionierenden Version (v1.4.5) fiel
  ein zweiter, bisher uebersehener Unterschied auf: **der TLS-Versions-
  Deckel auf 1.2** (`ctx.maximum_version = ssl.TLSVersion.TLSv1_2`) war
  in v1.4.5 NICHT aktiv (wurde in v1.2.0 eingefuehrt, in v1.4.5 als
  unbestaetigte Vorsichtsmassnahme wieder entfernt, dann in v1.5.0 fuer
  die X1-Serie wieder eingefuehrt und seitdem unveraendert IMMER aktiv
  - auch fuer den A1 Mini, was in v1.5.7 uebersehen wurde). Es ist
  plausibel, dass der A1 Mini mit einer erzwungenen TLS-1.2-Verbindung
  (statt frei auszuhandeln, typischerweise TLS 1.3) beim saubereren
  Verbindungsabschluss ins Stocken geraet.
  **Implementierte Aenderung:** Statt eines einzelnen Schalters
  (`reuse_session`) gibt es jetzt zwei vollstaendige, benannte
  Verbindungsprofile (`FTPS_PROFILES` in `app.py`, `PROFILES` in
  `ftps_upload_helper.py` - inhaltlich identisch, aus technischen
  Gruenden in beiden Dateien dupliziert, da `ftps_upload_helper.py`
  komplett eigenstaendig als exe gebaut wird und keine Imports aus
  `app.py` haben kann):
  ```python
  {
      "x1": {"cap_tls12": True,  "reuse_session": True},
      "a1": {"cap_tls12": False, "reuse_session": False},
  }
  ```
  `_build_ftps_context(profile)` (app.py) / `_build_context(profile)`
  (ftps_upload_helper.py) bauen den SSL-Kontext je nach Profil auf -
  der TLS-1.2-Deckel wird nur noch fuer Profil "x1" gesetzt. Das 5.
  Kommandozeilen-Argument an die Helfer-exe/den Sentinel-Fallback ist
  jetzt ein Profilname-String ("x1"/"a1") statt "1"/"0". Die
  Alternierung in `_ftps_upload()` verwendet weiterhin dasselbe Muster
  (`profile_pattern = ["x1", "a1", "x1"]`) - X1-Nutzer bleiben also
  unveraendert beim ersten Versuch erfolgreich, A1-Mini-Nutzer sollten
  jetzt beim zweiten Versuch (Profil "a1": kein TLS-Deckel + keine
  Sitzungs-Wiederverwendung, exakt das v1.4.5-Verhalten) erfolgreich
  sein.
  **Getestet (ohne echten Drucker):** Zwei Fake-Helfer-Skripte, diesmal
  anhand des UEBERGEBENEN PROFILNAMENS (nicht mehr nur True/False)
  reagierend: (1) "A1-Mini-artig" - scheitert bei Profil "x1" mit dem
  exakten gemeldeten Timeout, gelingt bei Profil "a1"; (2) "X1-artig" -
  scheitert bei Profil "a1", gelingt bei Profil "x1" (unveraendert
  sofort im ersten Versuch, wie bereits in v1.5.7 verifiziert).
  Profilnamen-Aufloesung im Helferskript getestet (gueltige Namen "x1"/
  "a1", unbekannte Namen fallen sicher auf "x1" zurueck). Fehlerfall
  (beide Profile schlagen fehl) zeigt jetzt "Profil x1"/"Profil a1" in
  der zusammengefassten Fehlermeldung statt der vorherigen "mit/ohne
  Sitzungs-Wiederverwendung"-Formulierung. Vollstaendiger Async-
  Confirm-Flow-Test weiterhin erfolgreich.
  **Ein Test gegen einen echten A1 Mini mit dieser Loesung konnte in
  dieser Umgebung nicht durchgefuehrt werden** - Bestaetigung durch den
  Nutzer stand zum Zeitpunkt dieser Übergabe noch aus. Das ist jetzt
  der ZWEITE Versuch, den A1-Mini-Fall zu loesen (v1.5.7 reichte nicht
  aus) - falls Profil "a1" beim naechsten Test IMMER NOCH denselben
  Timeout zeigt, waere die naechste zu pruefende Variable die
  Blockgroesse (aktuell fest 8192 Bytes) oder der Verbindungs-Timeout
  (aktuell fest 25 Sekunden, siehe `ftp.connect(ip, 990, timeout=25)`)
  - beide waren in der v1.4.5-Basisversion identisch zu heute und daher
  bisher nicht als Verdaechtige betrachtet, sollten aber bei einem
  erneuten Fehlschlag nicht mehr ausgeschlossen werden.
  **Lesson Learned:** Nach der ersten (unvollstaendigen) Diagnose in
  v1.5.7 waere ein sorgfaeltigerer, VOLLSTAENDIGER Vergleich ALLER
  Unterschiede zur zuletzt bestaetigt funktionierenden Version (statt
  nur der einen naheliegendsten Variable) von Anfang an gruendlicher
  gewesen. Bei einem Regressionsfall (etwas, das FRUEHER nachweislich
  funktionierte, JETZT aber nicht mehr) ist ein systematischer Diff
  gegen die zuletzt bestaetigt funktionierende Version tendenziell
  zuverlaessiger als eine Einzelhypothese, auch wenn diese zunaechst
  plausibel erscheint - besonders wenn (wie hier) mehrere Aenderungen
  seit der letzten Bestaetigung akkumuliert wurden.

  **v1.5.9 - ENDGUELTIGE URSACHE GEFUNDEN: schlicht zu kurzes Timeout,
  nicht TLS.** Der Nutzer testete `FtpsUploadHelper.exe` mit Profil
  "a1" (= exakt die historisch bestaetigt funktionierende v1.4.5-
  Konfiguration) KOMPLETT EIGENSTAENDIG (Dashboard vollstaendig
  geschlossen) - und selbst DANN trat exakt derselbe Timeout auf
  ("The read operation timed out" bei 390206/390206 Bytes, 100%). Das
  ist der entscheidende Beleg: TLS-Konfiguration (Version, Sitzungs-
  Wiederverwendung) UND Dashboard-Kontext (MQTT-Pause, Subprozess-
  Isolation) sind damit BEIDE endgueltig als Ursache ausgeschlossen -
  der Fehler tritt identisch auf, wenn buchstaeblich nichts anderes als
  reines `ftplib` mit der historisch korrekten Konfiguration laeuft,
  voellig unabhaengig vom Dashboard. Da die Datei nachweislich
  VOLLSTAENDIG ankommt (100% in jedem einzelnen Testlauf ueber die
  gesamte Chronologie hinweg, nie ein Abbruch waehrend der eigentlichen
  Uebertragung), bleibt als einzig verbleibende Erklaerung: der A1 Mini
  braucht nach Abschluss der Datenuebertragung schlicht LAENGER als das
  bisherige **25-Sekunden-Zeitlimit**, um die Datei fertig zu
  verarbeiten (z. B. SD-Karten-Schreibvorgang, Pruefsumme) und seine
  "226 Transfer complete"-Abschluss-Antwort zu senden - das Dashboard
  gab vorzeitig auf, obwohl der Drucker die Datei laengst korrekt
  erhalten hatte und nur noch etwas Zeit brauchte, um das zu
  bestaetigen.
  **Implementierte Aenderung:** `ftp.connect(ip, 990, timeout=25)` auf
  `timeout=120` angehoben, in `ftps_upload_helper.py` UND `app.py`s
  Sentinel-Fallback (`_run_ftps_upload_worker()`). Dieser Timeout-Wert
  wird von `ftplib.FTP` fuer ALLE Socket-Operationen der Verbindung
  verwendet (nicht nur den initialen Verbindungsaufbau), betrifft also
  auch das Lesen der finalen Abschluss-Antwort nach `storbinary()`.
  Das aeussere `subprocess.Popen(...).wait(timeout=30)` in
  `_ftps_upload_once()` (app.py) musste NICHT angepasst werden: es
  greift erst NACH der zeilenweisen stdout-Leseschleife, die selbst
  kein eigenes Zeitlimit hat und beliebig lange auf den Kindprozess
  wartet - `proc.wait(timeout=30)` danach ist nur eine Formsache zum
  Einsammeln des bereits abgeschlossenen Prozesses, kein zusaetzliches
  Zeitlimit fuer die eigentliche FTP-Operation (per Code-Inspektion
  bestaetigt, nicht nur angenommen).
  **Getestet (ohne echten Drucker):** Fake-Helfer-Skript simuliert einen
  "langsamen, aber letztlich erfolgreichen" Drucker (Antwort kommt nach
  einer verzoegerten Zeitspanne, die frueher als Fehlschlag gegolten
  haette) - Upload gelingt jetzt korrekt, statt vorzeitig abzubrechen;
  vollstaendiger Async-Confirm-Flow-Test weiterhin erfolgreich; beide
  Timeout-Werte (`ftps_upload_helper.py` und `app.py`-Fallback) per
  Code-Inspektion auf den neuen Wert verifiziert.
  **Ein Test gegen einen echten A1 Mini konnte in dieser Umgebung nicht
  durchgefuehrt werden** - Bestaetigung durch den Nutzer stand zum
  Zeitpunkt dieser Übergabe noch aus. Das ist der DRITTE Anlauf fuer
  den A1-Mini-Fall (v1.5.7 und v1.5.8 reichten nicht aus). Sollte auch
  120 Sekunden nicht ausreichen, waere ein weiteres Anheben (z. B. auf
  300s) der naechste, sehr risikoarme Schritt - es gibt keinen Hinweis
  darauf, dass eine laengere Wartezeit selbst irgendein Problem
  verursachen wuerde, im Gegensatz zu den bisherigen TLS-Experimenten.
  **Lesson Learned (Ergaenzung zu v1.5.8):** Die "vollstaendige-
  Verbindungsprofile"-Analyse in v1.5.8 hat einen wichtigen Hinweis
  bereits selbst geliefert und dann nicht konsequent zu Ende verfolgt:
  das Symptom "Datei kommt zu 100% an, aber Abschluss-Antwort wird nie
  gelesen" beschreibt praezise ein TIMING-Problem (Timeout), nicht ein
  TLS-Konfigurationsproblem (das typischerweise die Uebertragung selbst
  stoeren wuerde, nicht nur das Lesen einer Antwort danach). Der
  Symptom-Text selbst ("The read operation timed out") war die ganze
  Zeit der staerkste Hinweis auf die Ursache. Bei einem `socket.timeout`/
  `TimeoutError` in einer Fehlermeldung sollte das Zeitlimit selbst
  immer eine der ersten zu pruefenden Variablen sein, nicht erst nach
  mehreren anderen Theorien.

  **NACHTRAG zu v1.5.9: Bestaetigung durch Nutzer ergab - Fehler
  bleibt bestehen, VIERTER Anlauf fuer A1 Mini noch offen.** Der Nutzer
  bestaetigte, dass der Fehler nach dem Timeout-Update weiterhin
  auftritt. Auf Nachfrage, ob es jetzt spuerbar laenger dauert (naeher
  an den neuen 120s) oder weiterhin gleich schnell wie vorher: die
  Antwort war uneindeutig ("dauert sehr lange, hat es aber vorher auch
  schon") - das laesst offen, ob das einzelne 120s-Zeitlimit pro
  Versuch tatsaechlich ausgeschoepft wird (was fuer "einfach noch mehr
  Zeit geben" spraeche) oder ob der Fehler weiterhin schnell auftritt
  (was gegen die reine Timeout-Theorie spraeche und eher auf eine
  aktiv zurueckgesetzte/vom Netzwerk gekappte Verbindung hindeuten
  wuerde, die nicht einfach durch laenger Warten geloest werden kann).
  **Fuer die Weiterarbeit:** Eine PRAeZISE Zeitmessung (Stoppuhr vom
  Start des Uploads bis zur finalen Fehlermeldung, in Sekunden) ist der
  naechste noetige Datenpunkt, um zwischen diesen beiden Erklaerungen zu
  unterscheiden - bisher nicht eingeholt, da der Fokus in derselben
  Nutzer-Ruecksprache auf ein zweites, neu gemeldetes Problem
  (Mehrfarb-Druck haengt beim Aufheizen, siehe v1.5.10 unten) verlagert
  wurde. Der A1-Mini-FTPS-Fall bleibt damit zum Zeitpunkt dieser
  Uebergabe ungeloest - siehe Abschnitt 7 fuer den vollstaendigen
  Status und naechste Schritte.

  **v1.5.10 - NEUES, EIGENSTAENDIGES PROBLEM: Mehrfarb-/Mehrmaterial-
  Druck haengt beim Aufheizen des Druckbetts (unabhaengig vom FTPS-
  Thema, betrifft X1C).** Waehrend der A1-Mini-FTPS-Fall noch offen
  war, meldete der Nutzer ein NEUES Symptom bei einem X1C: bei einem
  Mehrfarb-Druck (2-3 verschiedene Filamente, u. a. mit geringer
  Farbabweichung wie Gruen/Hellgruen, manuell im Dialog korrekt dem
  passenden AMS-Fach zugeordnet) wird die Datei korrekt uebertragen
  und der Druckauftrag im Speicher des Druckers angelegt, der Drucker
  beginnt aber NICHT mit dem Aufheizen des Druckbetts - er "steht"
  einfach, laesst sich aber abbrechen. Reine Einzelfarb-Drucke (PLA,
  ASA-CF) funktionieren weiterhin einwandfrei seit v1.5.6/v1.5.4.
  **Entscheidender Diagnoseschritt:** Derselbe, bereits erfolgreich
  uebertragene Druckauftrag wurde direkt am Display des Druckers
  (SD-Karten-Ansicht, nicht ueber das Dashboard) gestartet - **das
  funktionierte einwandfrei.** Das bewies eindeutig: die Datei und die
  AMS-Zuordnung sind vollstaendig in Ordnung, das Problem liegt
  spezifisch im von unserem Dashboard gesendeten MQTT-`project_file`-
  Kommando (analog zur bereits geloesten ASA-CF-Diagnose aus v1.5.6,
  aber ein anderes konkretes Feld betreffend).
  **Recherche:** Ein bekannter, gut dokumentierter Bambu-Firmware-
  Fehlerzustand "Failed to get AMS mapping table" tritt bei Mehrfarb-
  Drucken auf und wurde in zahlreichen GitHub-Issues (bambulab/
  Bambu-Handy#171, bambulab/BambuStudio#10181/#3965/#7257) und Forum-
  Threads dokumentiert - interessanterweise tritt dieser Fehler auch
  bei offiziellem Bambu Studio/der Handy-App auf (verschiedenste
  Ursachen: Firmware-Bugs, SD-Karten-Probleme, `filament_id`-
  Inkonsistenzen in der `.3mf`), ist also NICHT zwangslaeufig auf
  einen falschen MQTT-Befehl zurueckzufuehren. Ein Blog-Post (Cinder's
  Blog) behauptete, das `ams_mapping`-Array muesse IMMER genau 4
  Elemente haben (ein Eintrag pro physischem AMS-Fach) - das wurde
  durch die offizielle Dokumentation der etablierten Referenz-
  bibliothek **bambulabs_api** widerlegt: dort ist `ams_mapping:
  list[int]` mit Standardwert `[0]` dokumentiert - eine VARIABLE-LAeNGE-
  Liste mit einem Eintrag pro tatsaechlich benoetigtem Filament, exakt
  wie unser Dashboard es bereits implementiert (`_slot_to_flat_index()`,
  siehe Codestellen-Tabelle) - die 4-Elemente-Theorie war also eine
  falsche Faehrte, die NICHT weiterverfolgt wurde.
  Stattdessen fiel beim Vergleich mit `bambulabs_api`s dokumentierter
  API-Signatur ein anderer, konkreter Unterschied auf:
  `PrinterMQTTClient.start_print_3mf(..., flow_calibration: bool =
  True)` - die Referenzbibliothek verwendet standardmaessig **True**,
  waehrend unser Code `"flow_cali": False` fest einprogrammiert hatte
  (seit der urspruenglichen Payload-Erstellung, nie hinterfragt - auch
  nicht im v1.5.6-Rewrite, der zwar `bed_type` & Co. ergaenzte, aber
  `flow_cali` unangetastet liess). Mehrfarb-Drucke benoetigen beim
  Farbwechsel zwingend Spuelvorgaenge (Purging), fuer die vermutlich
  Kalibrierungsdaten vorhanden sein muessen - plausible Erklaerung fuer
  ein Haengenbleiben, das schon VOR dem eigentlichen Druckstart
  (Aufheizen) auftritt, waehrend Einzelfarb-Drucke (kein Farbwechsel
  noetig) davon unberuehrt bleiben.
  **Implementierte Aenderung:** `"flow_cali": False` auf `"flow_cali":
  True` geaendert in `_request_print()` (app.py), mit ausfuehrlichem
  Kommentar zur Begruendung und Quelle.
  **Getestet (ohne echten Drucker):** Payload-Struktur mit einem
  simulierten MQTT-Client fuer ein Mehrfach-Filament-Szenario
  (`ams_mapping = [0, 3, 5]`) verifiziert - `flow_cali: true` korrekt
  gesetzt, Mehrfach-Mapping unveraendert korrekt uebernommen;
  vollstaendiger End-to-End-Test ueber `/print/prepare` + `/print/
  confirm` mit einem 2-Filament-Szenario (leicht unterschiedliche
  Gruentoene, `#00FF00`/`#90EE90`) bestaetigt korrekte automatische
  Zuordnung UND korrekten Payload-Aufbau bis in die tatsaechliche
  MQTT-Nachricht hinein.
  **Ein Test gegen einen echten Mehrfarb-Druck auf X1C konnte in dieser
  Umgebung nicht durchgefuehrt werden** - Bestaetigung durch den Nutzer
  stand zum Zeitpunkt dieser Übergabe noch aus.
  **Fuer die Weiterarbeit, falls der Fehler nach v1.5.10 weiterhin
  auftritt:** Da "Failed to get AMS mapping table" laut Recherche ein
  bekanntermassen vielschichtiges Bambu-Firmware-Problem mit vielen
  moeglichen Ursachen ist (nicht nur `flow_cali`), waere der naechste
  Schritt ein MQTT-Sniffer-Vergleich (analog zum in v1.5.6 dokumentierten
  Vorschlag): den tatsaechlich von Bambu Studio beim Senden DESSELBEN
  Mehrfarb-Druckauftrags gesendeten `project_file`-Befehl direkt
  mitschneiden und Feld fuer Feld mit unserem vergleichen - das waere
  fuer diesen spezifischen Drucker/diese Firmware-Version wesentlich
  aussagekraeftiger als weitere Referenz-Payload-Vergleiche aus der
  Community.

  **v1.6.0 - A1-MINI-FTPS-PROBLEM ENDGUELTIG GELOEST: die v1.5.9-
  Timeout-Theorie war ebenfalls falsch - richtige Ursache war der
  formale TLS-Verbindungsabschluss (unwrap()), nicht die Wartezeit.**
  Der Nutzer lieferte den entscheidenden neuen Datenpunkt: eine
  Uebertragung DERSELBEN Datei per **Bambu Studio** schliesst bereits
  **1-2 Sekunden nach Erreichen von 100%** erfolgreich ab. Das
  widerlegt die v1.5.9-Timeout-Theorie vollstaendig - der A1 Mini ist
  nachweislich NICHT langsam, sondern antwortet prompt. Das lenkte den
  Verdacht auf den einzigen verbleibenden Schritt zwischen "Datei
  komplett gesendet" und "Antwort gelesen": Pythons
  `ftplib.FTP.storbinary()` ruft nach der Datenuebertragung automatisch
  `conn.unwrap()` auf - ein formaler TLS-Verbindungsabschluss der
  Datenverbindung, bei dem auf ein TLS-`close_notify` vom Server
  gewartet wird (per Quellcode-Inspektion in `ftplib` verifiziert, wie
  bereits in v1.5.0 dokumentiert - siehe dortige Chronologie, wo dieselbe
  Mechanik fuer ein AeHNLICHES, aber nicht identisches Problem bei der
  X1-Serie untersucht und dort verworfen wurde). Vermutung: der A1 Mini
  sendet die eigentliche "226 Transfer complete"-Antwort zwar prompt,
  reagiert aber nicht sauber auf das formale TLS-`close_notify`, das
  `unwrap()` erwartet - waehrend Bambu Studio (eigene C++-Implementierung,
  nicht Pythons `ftplib`) vermutlich keinen solchen formalen TLS-
  Abschluss der Datenverbindung abwartet, sondern die Verbindung nach
  der Uebertragung einfach schliesst.
  **Wichtiger Kontext:** Diese "No-Unwrap"-Technik wurde bereits EINMAL
  zuvor implementiert und wieder verworfen - in v1.5.0
  (`_storbinary_no_unwrap()`, damals fuer die X1-Serie gedacht, um ein
  anderes Problem [vsftpd `require_ssl_reuse`] zu loesen). Das
  scheiterte damals, weil beim X1C ohne `unwrap()` ein `426 Failure
  reading network stream`-Fehler auftrat (dokumentiert in `ftps_test_
  minimal.py`s Test-B-Ergebnis, siehe fruehere Chronologie). Das
  bedeutet: **No-Unwrap ist fuer die X1-Serie SCHAEDLICH, aber fuer den
  A1 Mini genau die Loesung** - ein weiterer Beleg dafuer, dass beide
  Druckerfamilien grundverschiedene FTPS-Server-Implementierungen
  haben und gegensaetzliches Client-Verhalten brauchen (analog zu den
  bereits bekannten Unterschieden bei TLS-Version und Sitzungs-
  Wiederverwendung, siehe v1.5.7/v1.5.8).
  **Implementierte Aenderung:**
  - `PROFILES`/`FTPS_PROFILES` bekommen ein drittes Feld
    `"skip_unwrap"`: `x1` = `False` (unveraendert, normales `unwrap()`
    bleibt fuer die X1-Serie bestehen), `a1` = `True` (neu).
  - Neue Funktion `_storbinary_no_unwrap()` (identisch in `app.py` und
    `ftps_upload_helper.py` - inhaltlich dieselbe wie die 2025 in
    v1.5.0 entfernte Version, jetzt wieder eingefuehrt und ueber das
    Profil-System sauber nur fuer `a1` aktiv): Nachbau von
    `ftplib.FTP.storbinary()`, aber ohne das abschliessende
    `conn.unwrap()`.
  - `main()` (ftps_upload_helper.py) und `_run_ftps_upload_worker()`
    (app.py, Sentinel-Fallback) waehlen je nach `profile["skip_unwrap"]`
    zwischen `ftp.storbinary()` (normal, `x1`) und
    `_storbinary_no_unwrap()` (`a1`).
  - Das 120-Sekunden-Zeitlimit aus v1.5.9 wurde NICHT zurueckgebaut -
    es schadet nicht und bleibt als zusaetzliche, risikoarme
    Absicherung bestehen, auch wenn es nicht die eigentliche Ursache
    war.
  **Getestet (ohne echten Drucker):** `_storbinary_no_unwrap()` isoliert
  mit einem Mock-Objekt verifiziert (unwrap() wird nie aufgerufen, Daten
  korrekt gesendet, `close()` erfolgt trotzdem normal ueber den
  `with`-Block); zwei Fake-Helfer-Szenarien: (1) A1-Mini-artig - Profil
  "x1" scheitert mit dem exakten gemeldeten Timeout, Profil "a1"
  (skip_unwrap) gelingt sofort (< 2s); (2) X1-artig - unveraendert:
  Profil "x1" gelingt weiterhin sofort im ersten Versuch, keine
  Regression fuer die bereits funktionierende X1-Serie. Vollstaendiger
  Async-Confirm-Flow-Test weiterhin erfolgreich.
  **Ein Test gegen einen echten A1 Mini konnte in dieser Umgebung nicht
  durchgefuehrt werden** - Bestaetigung durch den Nutzer stand zum
  Zeitpunkt dieser Übergabe noch aus. Das ist der FUENFTE Anlauf fuer
  den A1-Mini-FTPS-Fall (v1.5.7, v1.5.8, v1.5.9 reichten nicht aus),
  diesmal aber mit einem entscheidenden neuen empirischen Datenpunkt
  (Bambu-Studio-Vergleichszeit) statt einer weiteren ungeprueften
  Theorie - deutlich besser abgesichert als die vorherigen Versuche.
  **Lesson Learned:** Der Nutzer-Hinweis "Bambu Studio braucht nur 1-2s"
  war der entscheidende Durchbruch - eine einzige konkrete
  Vergleichsmessung gegen ein bekanntermassen funktionierendes
  Referenzprogramm hat mehr bewirkt als mehrere Runden Theoretisieren
  ueber TLS-Parameter. Dieses Muster hat sich jetzt zum wiederholten
  Mal bestaetigt (vgl. den X1-Durchbruch durch den A/B-Vergleichstest
  in v1.5.3/v1.5.4): bei hartnaeckigen, protokollnahen Bugs ist eine
  Messung gegen eine bekannte, funktionierende Referenzimplementierung
  fast immer aufschlussreicher als eine weitere Parameter-Theorie.

  **v1.6.1 - UX-Verbesserung (kein Bugfix): Druckerfamilie beim
  Anlegen waehlbar, spart unnoetigen ersten Fehlversuch.** Nutzer-
  Wunsch: da nun bekannt ist, dass X1- und A1-Serie unterschiedliche,
  teils gegensaetzliche FTPS-Verbindungsprofile brauchen (siehe
  FTPS_PROFILES/PROFILES, v1.5.4-v1.6.0), soll die Alternierungs-
  Reihenfolge nicht mehr blind bei "x1" starten, sondern das dem Nutzer
  bereits bekannte Druckermodell direkt beim ersten Versuch verwenden.
  **Implementierte Aenderung:**
  - Neues Konfigurationsfeld `bambu_family` (Werte: `"x1"` oder `"a1"`,
    Standard `"x1"`) pro Bambu-Drucker in `config.json`.
  - `DashboardApp.add_printer()`: neuer Parameter `bambu_family="x1"`,
    validiert gegen `("x1", "a1")` (unbekannte Werte fallen sicher auf
    `"x1"` zurueck), im Drucker-Dict gespeichert.
  - `api_add_printer()`-Route: liest `data.get("bambu_family")` aus dem
    POST-Body, validiert ebenfalls defensiv, reicht es an `add_printer()`
    durch.
  - `load_config()`: `setdefault("bambu_family", "x1")` fuer alle
    bestehenden Bambu-Drucker in einer bereits vorhandenen
    `config.json` (Rueckwaertskompatibilitaet - alte Konfigurationen
    ohne dieses Feld funktionieren unveraendert weiter, mit "x1" als
    implizitem Verhalten wie bisher).
  - `PrinterConnection._ftps_upload()`: `profile_pattern` wird jetzt
    dynamisch aus `self.cfg.get("bambu_family", "x1")` gebaut - das
    bekannte Profil steht an erster UND dritter Stelle, das jeweils
    andere an zweiter Stelle (bleibt als automatischer Fallback
    bestehen, z. B. falls die Familie versehentlich falsch gewaehlt
    wurde oder sich das Druckermodell im Nachhinein aendert).
  - Frontend: neues `<select id="f_bambu_family">`-Dropdown im
    "Drucker hinzufuegen"-Formular (nur sichtbar/relevant bei Typ
    `bambu`, da im selben `bambuFields`-Div wie Access Code/
    Seriennummer), Standardauswahl "X1-Serie". `submitAdd()` sendet
    `body.bambu_family` mit; `openAddModal()` setzt das Dropdown beim
    Oeffnen auf den Standardwert zurueck.
  - `config.example.json`: Beispiel-Bambu-Eintrag um `"bambu_family":
    "x1"` ergaenzt.
  **Bewusst NICHT implementiert:** kein Bearbeiten-Dialog fuer
  bestehende Drucker (existiert im gesamten Programm ohnehin nicht -
  Drucker koennen nur hinzugefuegt oder entfernt werden). Wer die
  Familie eines bereits angelegten Druckers nachtraeglich aendern
  moechte, muss entweder `config.json` manuell bearbeiten (Feld
  `bambu_family` beim jeweiligen Drucker-Eintrag) oder den Drucker
  entfernen und mit der richtigen Familie neu anlegen.
  **Getestet (ohne echten Drucker):** `add_printer()` mit `bambu_family=
  "a1"` gespeichert und verifiziert; `_ftps_upload()` mit einem Fake-
  Helfer, der protokolliert, welches Profil beim JEWEILS ERSTEN Aufruf
  verwendet wird - bestaetigt fuer `bambu_family="a1"` (nutzt "a1"
  zuerst) UND `bambu_family="x1"` (nutzt "x1" zuerst, unveraendertes
  Verhalten); Standardwert ohne explizite Angabe ist weiterhin "x1";
  `load_config()` mit einer manuell erstellten "alten" `config.json`
  ohne `bambu_family`-Feld getestet - wird korrekt per `setdefault` auf
  "x1" ergaenzt; vollstaendiger API-Test ueber `POST /api/printers`
  fuer drei Faelle (gueltiges "a1", ungueltiger Wert -> Fallback "x1",
  Feld komplett weggelassen -> Fallback "x1"); HTML-Smoke-Test bestaetigt
  das neue Dropdown-Element ist im Formular vorhanden.
  **Fuer die Weiterarbeit:** Falls in Zukunft weitere Bambu-Druckerfamilien
  mit jeweils eigenen FTPS-Anforderungen bekannt werden (z. B. P1-Serie,
  falls sich diese anders als A1 oder X1 verhalten sollte - bisher nicht
  getestet), waere die Dropdown-Liste und `FTPS_PROFILES`/`PROFILES`
  entsprechend um einen dritten Eintrag zu erweitern sowie
  `profile_pattern` in `_ftps_upload()` auf mehr als 3 Versuche
  auszuweiten oder die Zuordnung Familie→Profil zu verfeinern.

  **NACHTRAG: FTPS-Upload beim A1 Mini funktioniert (bestaetigt), aber
  neuer, ANDERSARTIGER Fehler beim Druckstart entdeckt - kein Bug,
  Konfigurationsproblem.** Der Nutzer bestaetigte: mit `bambu_family=
  "a1"` gelingt der FTPS-Upload jetzt beim ALLERERSTEN Versuch (die
  gesamte FTPS-Saga v1.5.0-v1.6.0 gilt damit als vollstaendig geloest
  UND vom Nutzer bestaetigt). Danach trat aber ein neuer, voellig
  anderer Fehler auf: der Drucker meldete beim Druckstart **"Die
  Ueberpruefung des MQTT-Befehls ist fehlgeschlagen"** ("MQTT command
  verification failed"). Recherche ergab (offizielle Bambu-Wiki-Seite,
  HMS-Code 0500-0500-0001-0007): dieser Fehler tritt auf, wenn der
  **Developer Mode** fuer das jeweilige Geraet NICHT aktiv ist - mit
  aktiviertem Developer Mode werden Autorisierung/Authentifizierung der
  MQTT-Befehle komplett uebersprungen. Der Nutzer bestaetigte: Developer
  Mode war fuer den A1 Mini tatsaechlich NICHT aktiviert (obwohl LAN-
  Modus bereits lief) - das ist eine Pro-Geraet-Einstellung, die separat
  fuer jeden Drucker gesetzt werden muss.
  **KORREKTUR (September 2026, ueber einen anderen Chat gemeldet):** die
  hier und in README Abschnitt 2 urspruenglich genannte Fundstelle "Bambu
  Handy App" fuer diese Einstellung ist FALSCH und wurde ungeprueft
  uebernommen. Im reinen LAN-Modus ist die Verbindung zwischen Drucker
  und Bambu-Handy-App gekappt - der Developer Mode kann dort gar nicht
  eingeschaltet werden. Aktivierung erfolgt stattdessen **lokal am
  Drucker selbst** ueber dessen eigene Einstellungen (genauer Menuepfad
  je nach Druckermodell vermutlich unterschiedlich - nicht recherchiert/
  geraten, siehe Regel "kein Raten bei undokumentierten Ablaeufen").
  README Abschnitt 2 wurde entsprechend korrigiert (v2.2.18).
  **Kein Software-Fix noetig** - der Nutzer aktivierte Developer Mode
  fuer den A1 Mini, danach sollte der Druck normal starten (Bestaetigung
  stand zum Zeitpunkt dieser Übergabe noch aus, aber die Diagnose ist
  durch offizielle Bambu-Dokumentation eindeutig bestaetigt, nicht nur
  vermutet). README Abschnitt 4 wurde um einen expliziten Hinweis auf
  dieses Fehlerbild und seine Ursache ergaenzt, damit zukuenftige Nutzer
  mit mehreren Druckern das nicht uebersehen.
  **Wichtiger Hintergrund fuer die Weiterarbeit, falls Developer Mode
  bestaetigt aktiviert ist und der Fehler TROTZDEM weiterhin auftritt:**
  Seit Januar 2025 verlangt neuere Bambu-Firmware fuer bestimmte
  "kritische" MQTT-Befehle zusaetzlich eine **X.509-Zertifikat-Signatur**
  (RSA-SHA256), die offiziell nur ueber die proprietaere "Bambu Connect"-
  Anwendung erfolgt - das damals von Bambu eingefuehrte Firmware-Update
  hat viele Drittanbieter-Tools (OctoPrint, Home Assistant, eigene
  Skripte) zunaechst komplett unterbrochen. Community-Forscher haben das
  in der "Bambu Connect"-App eingebettete X.509-Zertifikat samt privatem
  Schluessel extrahiert (siehe Hackaday-Artikel "Bambu Connect's
  Authentication X.509 Certificate and Private Key Extracted", Januar
  2025) - dieses Material ist inzwischen oeffentlich bekannt und in
  mehreren aktiv gepflegten Open-Source-Projekten eingebettet (u. a.
  `schwarztim/bambu-mcp`, `griches/bambu-mcp`). Sollte sich herausstellen,
  dass Developer Mode allein (entgegen der offiziellen Bambu-Doku) nicht
  ausreicht, waere die Implementierung einer aehnlichen X.509-Signatur
  fuer den `project_file`-Befehl der naechste Schritt - das ist aber ein
  nicht-trivialer Umfang (Krypto-Bibliothek, Zertifikat/Schluessel-
  Verwaltung, Signatur-Format) und sollte nur bei tatsaechlichem Bedarf
  angegangen werden, nicht praeventiv.

  **v1.6.2 - NEUER, ECHTER STRUKTURELLER BUG GEFUNDEN UND BEHOBEN:
  "Failed to get AMS mapping table" bei Mehrfarb-Drucken auf X1C -
  falsches Indexierungsschema im ams_mapping-Array.** Nachdem A1 Mini
  vollstaendig bestaetigt funktioniert (FTPS-Saga endgueltig
  abgeschlossen) und der Developer-Mode-Hinweis den vorherigen MQTT-
  Verifikationsfehler geklaert hatte, meldete der Nutzer einen NEUEN
  Fehler beim Drucken eines Mehrfarb-Modells auf einem X1C: der Drucker
  zeigte explizit auf dem Display **"Die Zuordnungstabelle des AMS
  konnte nicht abgerufen werden"** - die deutsche Uebersetzung des
  bereits in der v1.5.10-Recherche gefundenen, dokumentierten Bambu-
  Fehlers "Failed to get AMS mapping table".
  **Ursachenanalyse per Code-Review (kein weiterer Recherche-Auftrag
  noetig, der Bug war im eigenen Code klar erkennbar nach genauem
  Nachvollziehen des Datenflusses):**
  - `_parse_3mf_filaments()` filtert die vollstaendige Filamentliste aus
    `project_settings.config` (0-basiert, ALLE im Projekt konfigurierten
    Filamente) auf die per `slice_info.config` fuer Plate 1 tatsaechlich
    benoetigte Teilmenge - dabei bleibt zwar das ORIGINALE `index`-Feld
    pro Filament-Dict erhalten, ABER:
  - `PrinterConnection.preview_print()` baute das `suggestion`-Array
    bisher per einfachem `.append()` in der Reihenfolge der GEFILTERTEN
    Liste - die Position im Array entsprach also der Position in der
    gefilterten Anzeige-Liste, NICHT dem echten `index`-Feld.
  - Im Frontend baute `confirmAmsModal()` das an `/print/confirm`
    gesendete `mapping`-Array ebenfalls per einfachem `Array.from(rows)
    .map(...)` - rein positionsbasiert nach DOM-Reihenfolge, ohne
    jemals den echten Filament-Index zu beruecksichtigen (`amsRowHtml()`
    setzte `data-filament-index` auf die Schleifenposition `i`, nicht
    auf `filament.index`).
  - Ergebnis: Enthielt ein Projekt z. B. 4 Filamente, von denen Plate 1
    nur die Filamente mit echtem Index 1 und 3 benoetigt (Luecke bei 0
    und 2 - z. B. weil das Projekt urspruenglich mit mehr Farboptionen
    angelegt wurde, als auf DIESER Platte verwendet werden), wurde ein
    KOMPAKTES 2-Element-Array `[wert_fuer_index_1, wert_fuer_index_3]`
    gesendet - der Drucker interpretiert Position 0 und 1 aber als
    Zuordnung fuer die Filamente MIT ECHTEM INDEX 0 und 1, nicht 1 und
    3. Eine voellig falsche, vom Drucker als ungueltig zurueckgewiesene
    Zuordnungstabelle.
  - **Warum das bei Einzelfarb-Drucken (PLA, ASA-CF - beide bereits
    bestaetigt funktionierend) nie auffiel:** bei nur einem verwendeten
    Filament mit dem (haeufigsten) echten Index 0 sind kompaktes und
    "echtes" Array zufaellig identisch (`[wert]` an Position 0 in
    beiden Faellen) - der Bug hat also gezielt Mehrfarb-Drucke mit
    einer Indexluecke getroffen, nicht Einzelfarb-Drucke.
  **Implementierte Aenderung (Backend UND Frontend gemeinsam noetig):**
  - `_parse_3mf_filaments()`: Rueckgabe geaendert zu einem Tupel
    `(filamente, gesamtanzahl)` - `gesamtanzahl` ist die Laenge des
    VOLLSTAENDIGEN `filament_colour`-Arrays aus `project_settings.config`
    (noch vor dem Filtern auf Plate 1), damit die Aufrufer wissen, wie
    gross das finale `ams_mapping`-Array sein muss.
  - `PrinterConnection.preview_print()`: gibt zusaetzlich
    `total_filaments` zurueck (unveraendert `filaments` mit dem
    jeweils ECHTEN `index`-Feld pro Eintrag, wie es das auch vorher
    schon tat - das Feld war schon da, wurde nur nie konsequent
    genutzt).
  - `/api/printers/<id>/print/prepare`-Route: gibt `total_filaments`
    zusaetzlich in der JSON-Antwort mit aus.
  - Frontend `openAmsModal()`: neue globale Variable
    `amsModalTotalFilaments`, aus `data.total_filaments` uebernommen.
  - Frontend `amsRowHtml()`: neues `data-true-index="${filament.index}"`-
    Attribut pro Zeile (zusaetzlich zum bisherigen `data-filament-index`,
    das weiterhin die Schleifenposition fuer DOM-IDs/Radio-Gruppen haelt
    - diese beiden Zwecke wurden bewusst getrennt, um unnoetig grosse
    Aenderungen an der DOM-Struktur/den Radio-Gruppennamen zu vermeiden).
  - Frontend `confirmAmsModal()`: baut das `mapping`-Array jetzt als
    `new Array(amsModalTotalFilaments).fill(-1)` und traegt jede
    Zuordnung an der Position `trueIndex` (aus `data-true-index`) ein,
    statt einfach in DOM-Reihenfolge zu pushen. Nicht angezeigte
    Filamente (aus der urspruenglichen Datei, aber nicht auf Plate 1
    benoetigt) bleiben korrekt auf `-1`.
  - `amsModalTotalFilaments` wird beim Schliessen/Abschluss des Modals
    (in `cancelAmsModal()` und beim `'done'`-Progress-Status) auf `0`
    zurueckgesetzt, um Zustandslecks zwischen verschiedenen Druckauftraegen
    zu vermeiden.
  **Getestet (ohne echten Drucker):** `_parse_3mf_filaments()` mit einer
  eigens gebauten `.gcode.3mf`-Testdatei, die EXAKT das Bug-Szenario
  nachbildet (4 Filamente im Projekt, Plate 1 nutzt nur die mit echtem
  Index 1 und 3) - bestaetigt, dass die echten Indizes 1 und 3 erhalten
  bleiben (nicht zu 0 und 1 umnummeriert); `preview_print()` end-to-end
  mit derselben Testdatei bestaetigt korrekte `total_filaments` (4) und
  korrekte `suggested_tray`-Zuordnung pro echtem Index; vollstaendiger
  HTTP-Route-Test (`POST /print/prepare`) bestaetigt `total_filaments`
  in der tatsaechlichen JSON-Antwort. **Die Frontend-JS-Logik wurde
  zusaetzlich isoliert mit Node.js direkt getestet** (nicht nur gelesen):
  ein Node-Skript baut die exakte `confirmAmsModal()`-Logik nach und
  bestaetigt, dass bei simulierten `rows` mit `trueIndex` 1 und 3 sowie
  `amsModalTotalFilaments=4` korrekt das Array `[-1, 0, -1, 1]`
  entsteht - UND ein Vergleichslauf mit der ALTEN (fehlerhaften) Logik
  zeigt explizit den Unterschied (altes Verhalten haette `[0, 1]`
  geliefert, die falsche, vom Drucker zurueckgewiesene Zuordnung).
  Ausserdem: Regressionstest fuer den Einzelfarb-Fall (ein Filament mit
  echtem Index 0) bestaetigt identisches Verhalten wie vorher - keine
  Regression fuer die bereits funktionierenden Faelle. Vollstaendiger
  End-to-End-Test von der `.3mf`-Datei bis zum finalen MQTT-`ams_mapping`-
  Feld in `_request_print()`s Payload bestaetigt den kompletten
  Datenfluss.
  **Ein Test gegen einen echten Mehrfarb-Druck auf X1C konnte in dieser
  Umgebung nicht durchgefuehrt werden** - Bestaetigung durch den Nutzer
  stand zum Zeitpunkt dieser Übergabe noch aus. Anders als bei den
  vorherigen FTPS-Runden ist dieser Fix aber kein Verhaltens-Experiment,
  sondern die Behebung eines klar nachvollziehbaren, durch Tests
  bewiesenen strukturellen Bugs (Index-Verwechslung) - entsprechend hoch
  ist die Zuversicht, dass dies das gemeldete Symptom tatsaechlich behebt.
  **Fuer die Weiterarbeit, falls der Fehler nach v1.6.2 weiterhin
  auftritt:** Falls es noch einen weiteren, bisher nicht erkannten Fall
  von Index-Verwechslung gibt (z. B. falls die tatsaechliche Filament-
  Nummerierung des Druckers nicht 0-basiert ist, wie hier angenommen,
  sondern in einer noch anderen Konvention), waere ein MQTT-Sniffer-
  Vergleich (Bambu Studio vs. unser Dashboard fuer denselben Mehrfarb-
  Druckauftrag) der praeziseste naechste Schritt, um das exakte, vom
  Drucker erwartete Array-Format zu verifizieren.

  **v1.6.3 - NEUES FEATURE (kein Bugfix): Druckauftrag per Drag & Drop
  jetzt auch fuer Ultimaker-Drucker.** Auf Nutzerwunsch erweitert: analog
  zu Bambu Lab (Abschnitt "Bambu Lab: Druckauftrag...") koennen jetzt
  auch fertig gesclicte `.gcode`-Dateien (Cura-Export) per Drag & Drop
  auf die Ultimaker-Karte gezogen werden, um den Druck zu starten.
  **Wesentlicher Unterschied zu Bambu:** die Ultimaker-API verlangt fuer
  schreibende Aktionen (Datei-Upload, Druckstart) zusaetzlich zur reinen
  Statusabfrage eine gesonderte **Kopplung** (id/key-Paar), die der
  Drucker erst nach Bestaetigung AM EIGENEN DISPLAY ausgibt - vergleichbar
  mit Bluetooth-Pairing. Diese Kopplung ist einmalig pro Drucker noetig
  (Zugangsdaten werden dauerhaft in `config.json` gespeichert), nicht bei
  jedem Druck erneut.
  **Recherche (offizielle Ultimaker-Swagger-Doku + mehrere unabhaengige
  UltiMaker-Forum-Threads, konsistent beschrieben - keine geratenen
  Endpunkte):**
  - Kopplung: `POST /api/v1/auth/request` (Pflichtfelder `application`/
    `user`, sonst Fehler "application or user not supplied") liefert
    sofort ein `id`/`key`-Paar zurueck - dieses ist aber erst gueltig,
    NACHDEM der Nutzer eine am Drucker-Display erscheinende
    Bestaetigungs-Abfrage angenommen hat. Der Status wird per
    `GET /api/v1/auth/check/{id}` abgefragt (Polling), bis `"authorized"`
    oder `"unauthorized"` zurueckkommt.
  - Druckauftrag: `POST /api/v1/print_job` (multipart/form-data, Felder
    `file` + `jobname`), authentifiziert per **HTTP Digest Auth** (RFC
    2617) mit dem id/key-Paar als Benutzername/Passwort.
  - Bekannte Einschraenkung aus der Recherche: Firmware 8.1 hatte einen
    dokumentierten Bug, der `/auth/request` voruebergehend unbrauchbar
    machte (spaeter gepatcht) - als Hinweis in der README aufgenommen,
    kein Workaround im Code noetig (betrifft nur veraltete Firmware).
  **Implementierte Aenderung:**
  - Neue Modul-Funktionen `_parse_digest_challenge()` (parst einen
    `WWW-Authenticate: Digest ...`-Header), `_build_digest_authorization()`
    (baut den `Authorization`-Header nach RFC 2617, MD5, qop=auth, reine
    `hashlib`/`secrets`-Standardbibliothek, keine externe Digest-Auth-
    Bibliothek) und `_build_multipart_body()` (manueller multipart/
    form-data-Aufbau, da `urllib` dafuer keine eingebaute Unterstuetzung
    hat und sich fuer dieses eine Formular keine zusaetzliche
    Abhaengigkeit lohnt).
  - **Bewusste Design-Entscheidung gegen Pythons eingebauten
    `urllib.request.HTTPDigestAuthHandler`:** dieser wuerde bei jeder
    Anfrage zwingend ZWEI Round-Trips brauchen (erst unauthentifiziert
    -> 401, dann erneut MIT Anmeldedaten) - bei einem potenziell
    mehrere MB grossen `.gcode`-Upload wuerde die Datei dabei zweimal
    uebertragen. Stattdessen: `UltimakerConnection._digest_challenge()`
    loest die 401-Challenge ueber den bewusst LEICHTEN Endpunkt
    `/api/v1/auth/verify` aus (keine Datei-Uebertragung), danach wird
    der eigentliche Upload mit bereits fertig berechnetem
    `Authorization`-Header nur EINMAL gesendet.
  - `UltimakerConnection.start_pairing()`/`check_pairing()`/`send_print()`
    - neue Methoden, analog zur Struktur von `PrinterConnection` bei
    Bambu, aber deutlich einfacher (kein AMS-Aequivalent, kein FTPS,
    keine Profile/Alternierung noetig).
  - `DashboardApp.__init__()`: neues `self._ultimaker_pending_auth`-Dict
    (`printer_id -> (auth_id, auth_key, gestartet_um)`) fuer laufende,
    noch nicht bestaetigte Kopplungsanfragen - NUR waehrend einer
    laufenden Kopplung befuellt, danach entfernt (bei Erfolg wandern
    id/key dauerhaft in `config.json`, siehe `get_printer_cfg()` +
    `save_config()`; bei Fehlschlag/Timeout [2 Minuten] wird der Eintrag
    verworfen).
  - `DashboardApp.start_ultimaker_pairing()`/`check_ultimaker_pairing()`/
    `send_ultimaker_print_now()` - orchestrieren Kopplung bzw.
    Druckauftrag. **Wichtig:** `send_ultimaker_print_now()` startet den
    Druck SOFORT nach dem Hochladen (kein zweistufiger prepare/confirm-
    Ablauf wie bei Bambu noetig, da keine AMS-Zuordnung zu bestaetigen
    ist) - nutzt aber dieselben `_print_jobs`/`_print_progress`-
    Strukturen weiter, sodass die BESTEHENDEN generischen Routen
    `GET /print/progress/<job_id>` unveraendert wiederverwendet werden
    koennen (keine neuen Progress-/Cancel-Routen noetig).
  - Drei neue Flask-Routen: `POST /api/printers/<id>/ultimaker/pair/start`,
    `GET .../ultimaker/pair/status`, `POST .../ultimaker/print`.
  - `DashboardApp.all_status()`: liefert zusaetzlich `ultimaker_paired`
    (bool) fuer Drucker vom Typ `ultimaker`, damit das Frontend weiss,
    ob die Ablage-Flaeche oder der Kopplungs-Button angezeigt werden soll.
  - Frontend: `renderUltimakerDropZone()` (zeigt je nach `ultimaker_paired`
    entweder die Ablage-Flaeche oder einen "Jetzt koppeln"-Button),
    `pairUltimaker()` (startet Kopplung, pollt Status alle 2s bis zu
    130s), `dzDropUltimaker()` (validiert `.gcode`-Endung, laedt hoch),
    `pollUltimakerProgress()` (pollt denselben generischen Progress-
    Endpunkt wie Bambu, zeigt Toast bei `done`/`error`). Neue CSS-Klasse
    `.drop-zone.dz-disabled` fuer den ungekoppelten Zustand; `.btn-mini`
    (bereits vorhanden) fuer den Kopplungs-Button wiederverwendet.
  **Bewusste Vereinfachung:** kein granulares Fortschritts-Feedback
  waehrend des Uploads (die Ultimaker-API bietet dafuer keinen Hook wie
  Bambus FTPS-Callback) - die Ablage-Flaeche zeigt nur einen "wird
  hochgeladen"-Zustand ohne Prozentanzeige. Da gcode-Dateien i. d. R.
  deutlich kleiner als Bambus `.gcode.3mf`-Pakete sind, wurde das als
  akzeptabler Scope-Kompromiss bewertet, nicht als fehlende Funktion.
  **Getestet (ohne echten Drucker, aber ungewoehnlich gruendlich fuer
  ein neues Feature):**
  - `_parse_digest_challenge()`/`_build_digest_authorization()` isoliert
    getestet UND die berechnete Response-Hash-Kette manuell (per Hand
    nachgerechnetem MD5) gegen RFC 2617 verifiziert - nicht nur auf
    "sieht plausibel aus" geprueft.
  - `_build_multipart_body()` isoliert auf korrekte Struktur getestet.
  - `UltimakerConnection.send_print()` gegen einen ECHTEN, selbst
    geschriebenen `http.server.HTTPServer`-Testserver getestet, der die
    Digest-Antwort SERVERSEITIG selbst nachrechnet und nur bei
    korrekter Signatur akzeptiert - eine deutlich staerkere Verifikation
    als ein reiner Client-seitiger Test, da sie beweist, dass ein
    echter, unabhaengiger RFC-2617-Digest-Server die Anfrage als gueltig
    akzeptieren wuerde.
  - `start_pairing()`/`check_pairing()` gegen einen simulierten Server
    getestet (korrekte Felder gesendet, Antwort korrekt verarbeitet).
  - Alle drei neuen Flask-Routen end-to-end getestet: erfolgreiche
    Kopplung inkl. Persistierung in `config.json` und `ultimaker_paired`-
    Statusanzeige; vollstaendiger Druckauftrag-Flow von der Upload-Route
    bis zum digest-authentifizierten `send_print()`-Aufruf (wieder gegen
    den echten Test-HTTP-Server); alle Fehlerfaelle (falsche Datei-
    endung, fehlende Kopplung, fehlende Datei, Kopplungsstatus ohne
    laufende Anfrage, abgelaufene Kopplungsanfrage inkl. korrektem
    Aufraeumen).
  - Vollstaendiger Regressionstest mit gemischten Druckertypen
    (Bambu + Ultimaker gleichzeitig) bestaetigt keine gegenseitige
    Beeintraechtigung; `ultimaker_paired`-Feld erscheint korrekt NUR bei
    Ultimaker-Druckern, nicht bei anderen Typen.
  **Ein Test gegen einen echten Ultimaker-Drucker (inkl. der Display-
  Bestaetigung) konnte in dieser Umgebung nicht durchgefuehrt werden** -
  Bestaetigung durch den Nutzer stand zum Zeitpunkt dieser Übergabe noch
  aus. Die Implementierung folgt aber sehr genau der offiziellen, von
  mehreren unabhaengigen Quellen konsistent bestaetigten API-Dokumentation
  und wurde (soweit ohne echten Drucker moeglich) ungewoehnlich gruendlich
  gegen einen echten, unabhaengigen Digest-Auth-Server verifiziert.
  **Fuer die Weiterarbeit, falls beim ersten echten Test Probleme
  auftreten:**
  1. Falls die Kopplungsanfrage selbst fehlschlaegt (schon Schritt 1):
     Firmware-Version pruefen - Firmware 8.1 (vor einem Patch) hatte
     laut Recherche einen bekannten Bug bei `/auth/request`.
  2. Falls die Kopplung gelingt, der Druckstart aber mit HTTP 401
     scheitert: moeglicherweise erwartet die konkrete Firmware-Version
     ein anderes `algorithm`-Feld oder eine andere qop-Variante als
     `auth` (z. B. `auth-int`, das den Nachrichtenkoerper mit in den
     Hash einbezieht) - dann muesste `_build_digest_authorization()`
     um diese Variante ergaenzt werden.
  3. Falls "No file received" trotz korrekter Digest-Auth auftritt
     (ein in der Recherche gefundenes, von mehreren Nutzern unabhaengig
     berichtetes Symptom bei multipart-Uploads): den exakten Aufbau des
     multipart-Bodys mit einem Netzwerk-Mitschnitt (Wireshark) gegen
     einen erfolgreichen curl-Aufruf vergleichen - moeglicherweise
     erwartet die Firmware eine bestimmte Feld-Reihenfolge (`jobname`
     vor `file` oder umgekehrt) oder einen zusaetzlichen Header.

  **v1.6.4 - ERSTER PRAXISTEST (gegen einen Nachbau, nicht Original-
  Hardware): Kopplung funktionierte, Druckstart scheiterte mit
  "Erwartete Digest-Authentifizierungs-Anfrage (401) blieb aus".**
  Der Nutzer testete v1.6.3 gegen "Ultimaker Connect Raspi MK1" - ein in
  einem ANDEREN Chat von Claude selbst gebautes, separates Projekt
  (Raspberry Pi + USB-angeschlossener Ultimaker 2+, bildet die
  Netzwerk-API eines netzwerkfaehigen Ultimaker nach, damit Cura ihn
  wie einen normalen Netzwerkdrucker erkennt - siehe eigene
  Memory-Datei `/areas/ultimaker-connect-raspi.md` fuer Details zu
  jenem Projekt). **Der Chatverlauf jenes Projekts konnte trotz
  mehrerer conversation_search-Versuche mit verschiedenen Suchbegriffen
  nicht aufgefunden werden** - die exakte Implementierung des
  Nachbaus (welche Endpunkte er tatsaechlich unterstuetzt) ist daher
  NICHT bekannt, nur aus dem Fehlerbild erschlossen.
  **Ursachenanalyse:** Die Fehlermeldung selbst war eindeutig:
  `UltimakerConnection._digest_challenge()` (v1.6.3-Implementierung)
  fragte gezielt den separaten Endpunkt `GET /api/v1/auth/verify` ab,
  um die Digest-Challenge (realm/nonce) zu erhalten - erwartete dabei
  eine 401-Antwort mit `WWW-Authenticate: Digest ...`. Blieb diese aus,
  wurde eine Fehlermeldung geworfen. Da die KOPPLUNG (auth/request +
  auth/check) beim Nutzer nachweislich funktionierte, aber der
  Druckstart an dieser Stelle scheiterte, ist die wahrscheinlichste
  Erklaerung: der Nachbau implementiert `/api/v1/auth/verify` schlicht
  NICHT (dieser Endpunkt ist in der offiziellen Doku vorhanden, aber
  fuer die KERNFUNKTION - Kopplung + Druckstart - nicht zwingend
  erforderlich, ein Nachbau koennte ihn daher plausibel ausgelassen
  haben, ohne dass das dem urspruenglichen Auftrag "Netzwerk-API
  nachbilden, damit Cura den Drucker erkennt" widersprechen wuerde).
  **Implementierte Aenderung (Robustheits-Fix, kein Rate-Versuch):**
  `_digest_challenge()` fragt die Digest-Challenge jetzt nicht mehr
  ueber den separaten `/api/v1/auth/verify`-Endpunkt ab, sondern direkt
  vom TATSAECHLICHEN Ziel-Endpunkt `/api/v1/print_job` (per leerem
  `POST`, `data=b""`, OHNE Datei) - das ist ohnehin der Endpunkt, dessen
  Digest-Realm/Nonce fuer den anschliessenden echten Upload gebraucht
  wird, und muss fuer die Kernfunktion "Druckauftraege senden" so oder
  so korrekt auf eine unautorisierte Anfrage mit 401 + Digest-Challenge
  reagieren - unabhaengig davon, ob zusaetzliche Nebenendpunkte wie
  `/auth/verify` implementiert sind. Das macht die Implementierung
  robuster gegenueber Nachbauten/vereinfachten API-Implementierungen,
  ohne die Kompatibilitaet zu echter Ultimaker-Hardware zu gefaehrden
  (die REALE Ultimaker-API muss laut Dokumentation ohnehin auch
  `/print_job` selbst mit Digest-Auth schuetzen - das war nie
  fraglich, nur OB zusaetzlich `/auth/verify` separat existiert).
  Fehlermeldung fuer den verbleibenden Fehlerfall (Server akzeptiert die
  leere Anfrage komplett ohne 401) wurde praezisiert: erklaert jetzt
  explizit, dass entweder gar keine Digest-Authentifizierung verlangt
  wird oder das Antwortverhalten von der Doku abweicht.
  **Getestet (ohne echte Hardware, aber gezielt gegen das exakte
  gemeldete Fehlerbild):** ein simulierter Server, der `/api/v1/auth/
  verify` bewusst NICHT implementiert (404) aber `/print_job` korrekt
  per Digest schuetzt, akzeptiert jetzt den kompletten `send_print()`-
  Ablauf - dieses Szenario schlug mit dem v1.6.3-Code nachweislich fehl
  (siehe Test in der Chat-Historie: `_digest_challenge()` warf exakt die
  vom Nutzer gemeldete Fehlermeldung, bevor der Fix angewendet wurde).
  Zusaetzlich: ein simulierter Server MIT `/auth/verify` bestaetigt
  keine Regression fuer echte Ultimaker-Hardware (die diesen Endpunkt
  laut Doku implementiert); ein dritter Test (Server verlangt gar keine
  Authentifizierung) bestaetigt die praezisierte Fehlermeldung.
  **Bestaetigung durch den Nutzer, dass der Druckstart gegen den
  Nachbau jetzt tatsaechlich funktioniert, stand zum Zeitpunkt dieser
  Übergabe noch aus** - der naechste sinnvolle Schritt waere:
  1. Erneuter Test gegen "Ultimaker Connect Raspi MK1".
  2. Falls IMMER NOCH derselbe Fehler auftritt: der Nachbau verlangt
     vermutlich GAR KEINE Digest-Authentifizierung fuer `/print_job`
     (dann wuerde die praezisierte Fehlermeldung das jetzt auch klar so
     sagen) - dann waere zu klaeren, ob der Nachbau ueberhaupt eine
     Authentifizierung fuer den Druckstart implementiert, und falls
     nein, ob unser Dashboard optional auch OHNE Digest-Auth senden
     koennen soll (waere ein separater, expliziter Kompatibilitaetsmodus,
     kein Ersatz fuer die Digest-Auth-Implementierung, da echte
     Ultimaker-Hardware diese zwingend braucht).
  3. Falls ein ANDERER Fehler auftritt (z. B. 400/415 bei der leeren
     Probe-Anfrage, noch bevor der Server ueberhaupt zur Auth-Pruefung
     kommt): der Nachbau prueft moeglicherweise erst die Multipart-
     Struktur, bevor er Authentifizierung prueft - dann muesste die
     Probe-Anfrage einen (leeren) aber strukturell gueltigen multipart/
     form-data-Body mitschicken statt eines komplett leeren Bodys.
  4. Am zuverlaessigsten waere grundsaetzlich, den Chatverlauf des
     "Ultimaker Connect Raspi"-Projekts zu finden (z. B. indem der
     Nutzer direkt danach fragt oder dessen `app.py` hochlaedt) und die
     tatsaechlich implementierten Endpunkte/das Auth-Verhalten direkt
     nachzulesen, statt weiter aus Fehlermeldungen zu erschliessen.

  **v1.6.5 - URSACHE ENDGUELTIG GEKLAeRT (echter Quellcode statt
  Vermutung): der Nachbau prueft beim Druckstart GAR KEINE
  Authentifizierung.** Der Nutzer lud auf Nachfrage `app.py`,
  `README.md` UND `ultimaker_api.py` des "Ultimaker Connect Raspi
  MK1"-Projekts direkt als Projekt-Dateien hoch (`/mnt/project/`) -
  damit konnte die tatsaechliche Implementierung erstmals direkt
  gelesen werden, statt weiter aus Fehlermeldungen zu erschliessen (wie
  in v1.6.3/v1.6.4 noch noetig, da der zugehoerige Chat trotz mehrerer
  `conversation_search`-Versuche nicht auffindbar war). Zentrale
  Erkenntnisse aus dem tatsaechlichen Code:
  - `GET /api/v1/auth/verify` liefert IMMER `200 {"message": "ok"}` -
    nie eine 401-Antwort. Das erklaert den ERSTEN gemeldeten Fehler
    (v1.6.3-Code fragte genau diesen Endpunkt ab).
  - `POST /api/v1/print_job` prueft AUSSCHLIESSLICH, ob ein multipart-
    Feld `"file"` vorhanden ist (`if "file" not in request.files:
    return 400`) - **keinerlei Digest-Authentifizierung, keine
    Ueberpruefung des id/key-Paars ueberhaupt**. Das erklaert den
    ZWEITEN gemeldeten Fehler (v1.6.4-Code sendete eine leere Probe-
    Anfrage OHNE Datei an genau diesen Endpunkt, was prompt mit 400
    beantwortet wurde - nicht weil Authentifizierung fehlschlug,
    sondern weil ueberhaupt keine Datei mitgeschickt wurde und der
    Handler diese Pruefung offenbar VOR jeder denkbaren Auth-Pruefung
    durchfuehrt - die aber ohnehin nirgends im Code existiert).
  - `POST /api/v1/auth/request`/`GET /api/v1/auth/check/<id>`
    implementieren den Kopplungs-Handshake zwar korrekt genug, damit
    unser Dashboard eine erfolgreiche Kopplung sieht (jede Anfrage wird
    laut Code-Kommentar UND README bewusst automatisch autorisiert, da
    der Pi kein Display fuer eine physische Bestaetigung hat) - das
    dabei erzeugte id/key-Paar wird aber an keiner Stelle im gesamten
    Modul jemals wieder verwendet oder ueberprueft. Die Kopplung ist
    also rein kosmetisch/protokollkonform fuer Cura's Verbindungs-
    Dialog, hat aber keine tatsaechliche Sicherheitsfunktion in diesem
    Nachbau.
  **Implementierte Aenderung (generelle, nicht nachbau-spezifische
  Robustheit):** `_digest_challenge()` (Ruecknahme der bisherigen
  Fehler-werfenden Semantik) wurde zu `_digest_challenge_or_none()`
  umgebaut: liefert weiterhin die geparste Challenge bei einer echten
  401+Digest-Antwort (fuer echte Ultimaker-Hardware zwingend
  erforderlich), liefert aber jetzt **`None` statt eine Exception zu
  werfen**, wenn die Probe-Anfrage IRGENDEINE andere Antwort bekommt
  (200, 400, 201, ...) - das deckt sowohl "akzeptiert alles ohne Auth"
  als auch "lehnt aus einem anderen Grund ab, der nichts mit
  Authentifizierung zu tun hat" (wie beim Nachbau: fehlende Datei) ab,
  ohne zwischen beiden unterscheiden zu muessen - in beiden Faellen ist
  die richtige Reaktion identisch: den echten Upload OHNE
  Authorization-Header senden. `send_print()` fuegt den
  `Authorization`-Header nur noch bedingt hinzu, wenn `challenge is not
  None`. **Wichtig: das ist kein nachbau-spezifischer Hack**, sondern
  eine allgemein sinnvolle Verhaltensweise ("nutze Authentifizierung,
  falls verlangt, sonst nicht") - echte Ultimaker-Hardware, die
  weiterhin zwingend 401+Digest liefert, ist davon unveraendert
  betroffen und funktioniert weiterhin wie bisher; nur Server, die GAR
  KEINE Auth verlangen, werden jetzt zusaetzlich unterstuetzt, statt
  einen (in diesem Fall falschen) Fehler zu erzwingen.
  **Getestet:** ein Test-Server, der EXAKT das Verhalten der echten
  `ultimaker_api.py` nachbildet (auth/verify immer 200, print_job prueft
  nur auf `"file"` im Multipart-Body, keinerlei Auth-Pruefung) -
  `send_print()` funktioniert jetzt korrekt End-to-End dagegen. Zusaetzlich
  weiterhin bestaetigt: (1) echte Ultimaker-Hardware-Simulation (401 +
  Digest-Challenge, korrekte Zugangsdaten) funktioniert unveraendert -
  keine Regression; (2) falsche Zugangsdaten bei einem Server, der
  tatsaechlich Digest-Auth verlangt, wird weiterhin korrekt als Fehler
  erkannt (nicht faelschlich als "keine Auth noetig" fehlinterpretiert,
  da dieser Fall ueber einen echten 401 mit gueltiger Digest-Challenge
  laeuft, nur die spaetere Antwort auf den ECHTEN Upload mit den
  falschen Daten schlaegt fehl - unveraendertes Verhalten). Vollstaendiger
  Regressionstest mit gemischten Druckertypen weiterhin erfolgreich.
  **Bestaetigung durch den Nutzer, dass der Druckstart gegen den
  Nachbau jetzt tatsaechlich funktioniert, stand zum Zeitpunkt dieser
  Übergabe noch aus** - basiert aber diesmal auf einer Verifikation
  gegen den TATSAECHLICHEN, vom Nutzer bereitgestellten Quellcode, nicht
  mehr auf einer Vermutung aus dem Fehlerbild - deutlich hoehere
  Zuversicht als bei den beiden vorherigen Versuchen.
  **Lesson Learned:** Nach ZWEI aufeinanderfolgenden Fehlversuchen, das
  Problem allein aus der Fehlermeldung zu erschliessen (v1.6.3, v1.6.4),
  war die direkte Einsicht in den tatsaechlichen Server-Code der
  entscheidende Schritt - beide vorherigen "Robustheits-Fixes" waren
  in sich schluessig und plausibel, trafen aber nicht die tatsaechliche
  Ursache, weil sie auf Annahmen ueber ein unbekanntes System beruhten.
  Bei der Fehlersuche gegen ein System, dessen Quellcode potenziell
  verfuegbar ist (hier: ein Projekt, das der Nutzer selbst mit Claude in
  einem anderen Chat gebaut hat), sollte das Anfordern des tatsaechlichen
  Codes VOR weiteren Vermutungen stehen, sobald mehr als ein
  Vermutungsversuch fehlgeschlagen ist.

  **v1.6.6 - NEUER, ECHTER BUG GEFUNDEN: Farb-Zuordnung verlangte
  byte-genaue Uebereinstimmung, obwohl die richtige Farbe physisch
  vorhanden war.** Waehrend der Ultimaker-Nachbau-Fall (v1.6.5) noch
  offen war, meldete der Nutzer ein NEUES, unabhaengiges Problem: der
  bereits mehrfach beobachtete "Aufheizen des Druckbetts"-Hang trat auf
  einem X1C erneut auf - diesmal bei einem EINFARBIGEN Druck mit
  automatischer AMS-Zuordnung, obwohl mehrfarbige Drucke seit den
  fruehe­ren Fixes (v1.5.10 flow_cali, v1.6.2 ams_mapping-Indizierung)
  zuverlaessig funktioniert hatten. **Diagnose-Weg (mehrere Abzweigungen,
  bis zur tatsaechlichen Ursache):**
  1. Zunaechst vermutet: `flow_cali:true` (seit v1.5.10 fuer ALLE Drucke
     erzwungen, nicht nur Mehrfarb-Drucke) koennte fuer Einzelfarb-
     Drucke einen neuen Regressions-Fehler verursachen - Recherche ergab
     aber keinen eindeutigen Beleg, UND mechanisch haette Flusskalibrierung
     erst NACH dem Aufheizen relevant werden duerfen, nicht davor - diese
     Theorie wurde deshalb nicht weiterverfolgt.
  2. Der bewaehrte Diagnose-Test (Druck direkt am Display starten) wurde
     vorgeschlagen, aber durch die Antworten des Nutzers ueberholt: er
     stellte fest, dass es **am AMS-Zuordnungsdialog selbst** liegt - im
     SELBEN Dialog fuehrt "automatischen Vorschlag uebernehmen" zum
     Haengenbleiben, "Material selbst auswaehlen" funktioniert.
  3. Erste Vermutung (falsch): ein JS-Bug beim Auslesen von "suggested"
     vs. manuell gewaehltem Wert - der Code-Review zeigte aber, dass
     beide Pfade strukturell korrekt denselben Werttyp liefern.
  4. Entscheidende Klarstellung durch den Nutzer: der Dialog zeigte in
     Wahrheit **"Keine passende Farbe im AMS gefunden"** - der
     automatische Vorschlag fiel also auf "Extern/manuell" zurueck,
     OBWOHL der Nutzer bestaetigte, dass Fach 0 tatsaechlich blaues PLA
     enthielt und die Datei "PLA Blau" verlangte - physisch war die
     richtige Spule vorhanden, unsere Zuordnung fand sie trotzdem nicht.
  **Tatsaechliche Ursache:** `_find_matching_tray()` verlangte bisher
  eine BYTE-GENAUE Hex-Farb-Uebereinstimmung (`tray_color != want_color:
  continue`). Der vom Slicer in der `.3mf` hinterlegte Farbwert fuer
  "Blau" und der vom AMS/RFID gemeldete Farbwert fuer dieselbe physische
  Spule "Blau" muessen aber nicht byte-identisch sein (z. B. durch
  unterschiedliche Bambu-Filament-Profile, Rundungsdifferenzen o. Ä.) -
  beide sind zweifellos "Blau" fuer einen Menschen, aber technisch zwei
  verschiedene Hex-Werte. Das erklaert auch die FRUeHERE Nutzer-
  Beobachtung (vor v1.6.6, siehe Chatverlauf zum X1C-Mehrfarb-Fall):
  "Gruen und Hellgruen ... sollte von der automatischen Zuordnung
  automatisch als passend akzeptiert werden" - dieselbe Grundursache,
  nur mit einem NOCH GROESSEREN Farbunterschied.
  **Implementierte Aenderung:**
  - Neue Funktion `_color_distance(hex_a, hex_b)`: berechnet den
    euklidischen Abstand zweier 6-stelliger Hex-Farben im RGB-Raum
    (0 = identisch).
  - Neue Konstante `COLOR_MATCH_TOLERANCE = 30` - **bewusst konservativ
    gewaehlt**: faengt kleine, unbeabsichtigte Abweichungen (Rundung,
    unterschiedliche Profile fuer "dieselbe" Farbe) ab, ist aber weit
    davon entfernt, tatsaechlich unterschiedliche Farben zu verwechseln
    (Gruen/Hellgruen liegen bei Distanz ~231, also weit ausserhalb der
    Toleranz - **bewusste Design-Entscheidung, Gruen/Hellgruen weiterhin
    NICHT automatisch gleichzusetzen**, da eine falsche automatische
    Zuordnung [Druck in der physisch falschen Farbe] schlimmer waere als
    der sichere Rueckfall auf manuelle Auswahl).
  - `_find_matching_tray()` umgebaut: statt "erstes Fach mit exakter
    Farbe gewinnt" jetzt "Fach mit der GERINGSTEN Farbabweichung
    INNERHALB der Toleranz gewinnt" (bei mehreren moeglichen Kandidaten
    wird der naechstliegende Farbwert bevorzugt; bei einem exakten
    Treffer aendert sich das Verhalten nicht).
  - Verbundwerkstoff-Trennung (`_types_compatible()`, v1.5.5) bleibt
    davon unberuehrt und wird weiterhin unabhaengig geprueft - ASA-CF
    kann also auch mit der neuen Farbtoleranz nicht mit reinem ASA
    verwechselt werden.
  **Getestet:** `_color_distance()` isoliert mit mehreren realistischen
  Werten kalibriert (kleine Abweichungen ~8 → innerhalb Toleranz,
  Gruen/Hellgruen ~231 → weit ausserhalb, eindeutig andere Farben wie
  Rot vs. Blau → weit ausserhalb); `_find_matching_tray()` mit dem
  EXAKTEN gemeldeten AMS-Setup (Fach 0 Blau, Fach 1 leer, Fach 2 Grau,
  Fach 4 Schwarz) und einem leicht abweichenden Blau-Hexwert fuer die
  Datei nachgebildet - waehlt jetzt korrekt Fach 0 statt "kein Treffer";
  Regressionstests fuer exakte Treffer, "am naechsten gewinnt bei
  mehreren Kandidaten", eindeutig unterschiedliche Farben (Rot vs. Blau)
  und die ASA/ASA-CF-Trennung (v1.5.5) bestaetigen keine Regression.
  Vollstaendiger End-to-End-Test von der `.3mf`-Datei bis zur `/print/
  prepare`-API-Antwort mit dem exakten gemeldeten AMS-Setup bestaetigt
  `suggested_tray: 0` (Blau) statt `-1` (Extern/manuell).
  **Offene, separate Beobachtung (nicht durch diesen Fix abgedeckt):**
  Der Nutzer merkte an, dass beim Rueckfall auf "Extern/manuell" (wenn
  wirklich keine passende Farbe gefunden wird) am Drucker-Display KEINE
  Material-Abfrage erscheint, sondern der Drucker einfach haengen
  bleibt. Das war bereits VOR v1.6.6 als offene, unbestaetigte
  Vermutung dokumentiert (siehe fruehe Chronologie zum A1-Mini-Druck-
  start: "der Druck muesste dann eigentlich trotzdem starten, ggf. mit
  Nachfrage am Display") - mit diesem Fall erstmals empirisch
  bestaetigt, dass es tatsaechlich zu einem Haengenbleiben statt einer
  Nachfrage kommt. Da dieser Fix (bessere Farb-Erkennung) den
  KONKRETEN gemeldeten Fall bereits loesen sollte (die passende Farbe
  wird jetzt gefunden, kein Rueckfall auf Extern/manuell mehr noetig),
  wurde diese separate Beobachtung nicht weiterverfolgt - waere aber
  relevant, falls in Zukunft ein Fall auftritt, bei dem TATSAECHLICH
  keine passende Farbe im AMS vorhanden ist (echtes Extern/manuell-
  Szenario) und der Druck dabei haengt statt eine Nachfrage zu zeigen.
  Dann waere zu klaeren, ob unser MQTT-Kommando fuer den externen/
  manuellen Fall ein zusaetzliches Feld braucht, das wir bisher nicht
  kennen - dafuer waere (wie schon mehrfach zuvor) ein MQTT-Sniffer-
  Vergleich mit Bambu Studio fuer einen absichtlich auf "Extern"
  gestellten Druck der praezisestee naechste Schritt.
  **Bestaetigung durch den Nutzer stand zum Zeitpunkt dieser Übergabe
  noch aus.**

  **v1.6.7 - NEUES FEATURE (kein Bugfix): H2-Serie als dritte
  Druckerfamilie ergaenzt.** Auf Nutzerwunsch: Bambu Lab hat seit der
  urspruenglichen X1/A1-Unterscheidung (v1.6.1) eine dritte Produktlinie
  eingefuehrt, die H2-Serie (H2S, H2D, H2D Pro, H2C - recherchiert und
  bestaetigt ueber mehrere offizielle/haendlerseitige Quellen, keine
  geratenen Modellnamen). Der Nutzer wies explizit an: mangels eigener
  Erkenntnisse zum FTPS-Verhalten der H2-Serie soll sie VORERST
  dieselbe Uebertragungsmethode wie die X1-Serie verwenden.
  **Implementierte Aenderung:**
  - Neue Zuordnungstabelle `BAMBU_FAMILY_TO_FTPS_PROFILE` (Modulebene,
    direkt nach `FTPS_PROFILES` platziert): bildet die vom Nutzer
    gewaehlte Druckerfamilie ("x1"/"a1"/"h2") auf ein tatsaechliches
    Verbindungsprofil aus `FTPS_PROFILES` ab. Fuer "h2" aktuell `"x1"`
    - eine bewusste, im Code ausfuehrlich begruendete Annahme (H2-Serie
    laeuft vermutlich wie X1C/X1E auf einer vollwertigen Linux-Basis,
    eher vergleichbar mit der X1- als der leichtgewichtigeren,
    vermutlich ESP32-basierten A1-Serie), aber unbestaetigt. Diese
    Trennung (Familie vs. tatsaechliches Profil) ist bewusst so
    gewaehlt, dass eine kuenftige Korrektur (z. B. falls die H2-Serie
    doch ein eigenes Profil braucht) NUR diese eine Zuordnungstabelle
    betrifft - `FTPS_PROFILES` selbst, `_ftps_upload()`s Alternierungs-
    Logik und alle Tests bleiben davon unberuehrt, es sei denn, ein
    komplett neues, drittes Profil wird noetig.
  - `PrinterConnection._ftps_upload()`: liest jetzt `known_profile =
    BAMBU_FAMILY_TO_FTPS_PROFILE.get(known_family, "x1")` statt die
    Familie direkt als Profilnamen zu verwenden - die Alternierungs-
    Logik selbst (bekanntes Profil an 1./3. Stelle, das jeweils andere
    als Fallback an 2. Stelle) bleibt unveraendert.
  - `api_add_printer()`-Route und `DashboardApp.add_printer()`:
    Validierung um `"h2"` erweitert (`bambu_family not in ("x1", "a1",
    "h2")` faellt weiterhin auf `"x1"` zurueck).
  - Frontend: neue `<option value="h2">H2-Serie (H2S, H2D, H2D Pro,
    H2C)</option>` im "Drucker hinzufuegen"-Formular, Hinweistext um
    einen Satz zur H2-Serie ergaenzt.
  - `load_config()`s Rueckwaertskompatibilitaets-`setdefault()` bleibt
    unveraendert (`"x1"` als Default fuer alle bestehenden Konfigu-
    rationen ohne dieses Feld) - keine Anpassung noetig, da "h2" nur
    ein zusaetzlicher, gueltiger Wert ist, kein veraendertes
    Standardverhalten.
  **Getestet:** H2-Drucker anlegen und `bambu_family="h2"` korrekt
  gespeichert bestaetigt; ungueltiger Familienwert faellt weiterhin
  korrekt auf `"x1"` zurueck; `BAMBU_FAMILY_TO_FTPS_PROFILE`-Zuordnung
  isoliert verifiziert (`h2`→`x1`, `x1`→`x1`, `a1`→`a1`); vollstaendiger
  FTPS-Upload-Test mit einem H2-Drucker bestaetigt, dass tatsaechlich
  das `x1`-Profil beim ERSTEN Versuch verwendet wird (Fake-Helfer
  protokolliert das verwendete Profil); Fallback-Alternierung fuer
  H2-Drucker getestet (simulierter Fehlschlag mit `x1`-Profil fuehrt
  korrekt zum Fallback auf `a1`-Profil im zweiten Versuch - die
  bestehende Alternierungs-Logik funktioniert unveraendert, unabhaengig
  von der Familie); Rueckwaertskompatibilitaet mit einer alten
  `config.json` ohne `bambu_family`-Feld bestaetigt (weiterhin `"x1"`);
  HTML-Formular enthaelt die neue Option; vollstaendiger Regressionstest
  mit allen drei Familien gleichzeitig (X1/A1/H2) angelegt und ueber
  `/api/status` abgefragt.
  **Kein Test gegen echte H2-Serie-Hardware moeglich** (dem Nutzer
  liegt aktuell offenbar keine vor) - die "x1"-Profil-Annahme ist
  reine Vorsichtsmassnahme, keine verifizierte Tatsache. Sollte ein
  Nutzer mit H2-Serie-Hardware kuenftig einen FTPS-Fehler melden, waere
  der erste Schritt zu pruefen, ob Profil "a1" (der automatische
  Fallback im zweiten Versuch) erfolgreich ist - falls ja, sollte
  `BAMBU_FAMILY_TO_FTPS_PROFILE["h2"]` einfach auf `"a1"` umgestellt
  werden. Falls WEDER "x1" NOCH "a1" fuer die H2-Serie funktionieren,
  waere ein komplett neues, drittes Profil in `FTPS_PROFILES` noetig -
  dann waere die gleiche Diagnose-Methodik wie bei A1 Mini angebracht
  (Vergleich mit Bambu Studio, TLS-Version/Sitzungs-Wiederverwendung/
  Verbindungsabschluss systematisch durchtesten, siehe Chronologie zu
  v1.5.0-v1.6.0 fuer das Vorgehen).

  **v1.6.8 - NEUES FEATURE (kein Bugfix): P1-, P2- und X2-Serie nach
  demselben Muster wie H2 (v1.6.7) ergaenzt.** Auf Nutzerwunsch,
  explizit "auf die gleiche Weise" wie H2: drei weitere Bambu-
  Produktlinien als Druckerfamilie waehlbar - P1 (P1P, P1S), P2 (P2S)
  und X2 (X2D). Modellnamen recherchiert und ueber mehrere unabhaengige
  Quellen (Bambu-eigene Vergleichsseite, Haendlerseiten, Fachportale)
  bestaetigt, keine geratenen Bezeichnungen. Alle drei nutzen - wie bei
  H2 bereits mangels eigener Erkenntnisse entschieden - vorerst
  dasselbe FTPS-Profil wie die X1-Serie:
  - **P1-Serie:** laut Bambu Labs eigener Ankuendigung des P2S
    technisch direkt von der X1 abgeleitet ("retained the core
    technology" der X1, nur guenstigere Hardware/weniger Sensorik,
    urspruenglich als preiswertere X1-Variante eingefuehrt) - von den
    ergaenzten Familien am ehesten TATSAECHLICH mit dem X1-Profil
    identisch, nicht nur mangels Alternative angenommen.
  - **X2-Serie (X2D):** offizieller, direkter Nachfolger der im Maerz
    2026 eingestellten X1C/X1E - ebenfalls vollwertige Linux-Basis zu
    erwarten, X1-Profil als naheliegendste Annahme.
  - **P2-Serie (P2S):** Nachfolger der P1-Serie, "combines ... the
    P1-Series with next-generation technologies from H2D/H2S" - laut
    Recherche technische Abstammung nicht ganz eindeutig zwischen
    P1-/X1- und H2-Technik, aber ebenfalls eher mit der X1- als mit
    der leichtgewichtigeren A1-Serie vergleichbar (beide sind
    vollwertige Linux-Systeme, kein ESP32-artiger Aufbau).
  **Implementierte Aenderung:**
  - `BAMBU_FAMILY_TO_FTPS_PROFILE` um drei Eintraege ergaenzt:
    `"p1": "x1"`, `"p2": "x1"`, `"x2": "x1"` (alle vorlaeufig, analog
    zu `"h2"`).
  - Validierung an beiden bisherigen Stellen (`api_add_printer()`-
    Route, `DashboardApp.add_printer()`) refaktoriert: statt der
    Familie gegen eine hartkodierte Tupel-Liste zu pruefen (die bei
    jeder neuen Familie an ZWEI Stellen synchron gehalten werden
    musste), wird jetzt direkt gegen die Schluessel von
    `BAMBU_FAMILY_TO_FTPS_PROFILE` geprueft (`bambu_family not in
    BAMBU_FAMILY_TO_FTPS_PROFILE`) - eine neue Familie kuenftig
    hinzuzufuegen erfordert dadurch nur noch EINEN Code-Ort (die
    Zuordnungstabelle selbst), nicht mehr mehrere synchron zu
    haltende Stellen. Diese Refaktorierung ist rein strukturell, kein
    Verhaltensunterschied fuer bestehende Familien.
  - Frontend: drei neue `<option>`-Eintraege im "Drucker hinzufuegen"-
    Formular (`p1`/`p2`/`x2`), Hinweistext auf "H2-, P1-, P2- und
    X2-Serie" erweitert.
  **Getestet:** alle drei neuen Familien einzeln angelegt und
  `bambu_family` korrekt gespeichert bestaetigt; Profilzuordnung fuer
  alle drei isoliert verifiziert (`p1`/`p2`/`x2` → jeweils `"x1"`);
  bestehende Familien (`x1`/`a1`/`h2`) nach der Refaktorierung
  weiterhin unveraendert korrekt; ungueltiger Wert faellt weiterhin auf
  `"x1"` zurueck; vollstaendiger FTPS-Upload-Test mit einem X2-Drucker
  bestaetigt, dass tatsaechlich das `x1`-Profil beim ERSTEN Versuch
  verwendet wird (Fake-Helfer protokolliert das verwendete Profil);
  vollstaendiger API-Route-Test fuer alle vier "unbestaetigten"
  Familien (h2/p1/p2/x2); HTML-Formular enthaelt alle neuen Optionen;
  Regressionstest mit allen SECHS Familien gleichzeitig angelegt und
  ueber `/api/status` abgefragt.
  **Kein Test gegen echte P1-, P2- oder X2-Serie-Hardware moeglich**
  (dem Nutzer liegt aktuell offenbar keine vor) - wie bei H2 sind die
  "x1"-Profil-Annahmen fuer P2 und X2 reine Vorsichtsmassnahmen, keine
  verifizierten Tatsachen (fuer P1 etwas besser abgesichert durch die
  direkte technische Abstammung von X1). Gleiches Vorgehen wie bei H2
  fuer die Weiterarbeit: bei gemeldeten FTPS-Fehlern zuerst pruefen, ob
  der automatische Fallback (Profil "a1" im zweiten Versuch) hilft -
  falls ja, genuegt eine einzeilige Aenderung der Zuordnungstabelle;
  falls nein, dieselbe Diagnose-Methodik wie beim A1-Mini-Fall
  anwenden (siehe Chronologie zu v1.5.0-v1.6.0).
- **Zweiter, unabhängiger MQTT-Broker** (`ExtrasMqttManager`) für frei
  definierbare Sensoren/Schalter, die einer Drucker-Karte angehängt
  werden. Aktivierung über `extras_mqtt` in `config.json`, Zuordnung über
  die `extras`-Liste je Drucker. **Nur config-basiert**, kein Formular in
  der Oberfläche dafür (bewusste Scope-Entscheidung).
- **Restdruckzeit** wird über `formatRemaining()` (JS) als „X h Y min
  verbleibend" formatiert (Bambu Lab, OctoPrint, Ultimaker liefern
  `remaining_min`; Formlabs/Creality liefern es nicht).
- **PyInstaller/GitHub Actions:** `pyinstaller --onefile --name
  DruckerDashboard --console app.py`. Der Workflow in
  `.github/workflows/build-exe.yml` baut bei jedem Push automatisch und
  legt das Ergebnis als Artifact ab (bei Tag-Push zusätzlich als Release).
- **Druckauftrags-Verlauf je Drucker (neu seit MK6 v1.0.0).** Fuer JEDEN
  Drucker (unabhaengig vom Typ) wird beim Anlegen/Programmstart
  automatisch `<Ordner der exe>/print_history/<drucker-id>/` angelegt
  (`DashboardApp._start_printer()` → `PrintHistoryStore.ensure_dir()`,
  laeuft sowohl fuer beim Start aus `config.json` geladene als auch neu
  ueber `add_printer()` hinzugefuegte Drucker, da beide Wege ueber
  `_start_printer()` fuehren). Tatsaechlich befuellt wird der Verlauf
  nur bei erfolgreichem Versand ueber die bestehenden Sende-Pfade:
  `DashboardApp.start_confirm_print_job()` (Bambu, nach `conn.send_print()`)
  und `DashboardApp.send_ultimaker_print_now()` (Ultimaker, nach
  `conn.send_print()`) rufen jeweils `self.history.add_entry(...)` VOR
  dem bestehenden `_cleanup_job_file()`-Aufruf auf (der die temporaere
  Upload-Datei loescht) - `add_entry()` KOPIERT die Datei zuvor in den
  Verlaufsordner, ruehrt das Original also nicht an.
  - Ablage: `<job_id><endung>` (Originaldatei), optional `<job_id>.png`
    (Vorschaubild, siehe unten), plus ein gemeinsames `index.json` je
    Drucker-Ordner (Liste, neueste zuerst). Automatische Begrenzung auf
    `PRINT_HISTORY_MAX_JOBS = 30` Eintraege je Drucker - `add_entry()`
    entfernt ueberzaehlige aeltere Eintraege samt Dateien direkt beim
    Einfuegen.
  - **Vorschaubilder:** bei Bambu (`.gcode.3mf`, ein ZIP-Container) wird
    das von Bambu Studio/OrcaSlicer mitgelieferte Plate-Vorschaubild
    gelesen (`Metadata/plate_1.png`, mit `Metadata/top_1.png` und einem
    generischen `Metadata/plate_*.png`-Scan als Fallback fuer abweichende
    Slicer-/Profilversionen - siehe `_extract_thumbnail()`). Bei
    Ultimaker (`.gcode`, reiner Cura-Textexport) wird BEWUSST **kein**
    Extraktionsversuch unternommen - anders als beim klar dokumentierten
    Bambu-ZIP-Format gibt es fuer in `.gcode`-Kommentaren eingebettete
    Vorschaubilder keine ueber alle Cura-Versionen/Profile hinweg
    verifizierte Struktur; ein Rateversuch wuerde gegen das Prinzip
    "keine Endpunkte/Formate raten" (siehe Abschnitt 6, Punkt 1)
    verstossen. Eintraege ohne Bild zeigen im Frontend ein generisches
    Datei-Icon (`FILE_ICON`) statt eines Fotos - kein Fehler.
  - **Untermenue je Kachel:** neues Uhr-Symbol (`.hist-icon`, JS-Konstante
    `HIST_ICON`) im `card-head` JEDER Karte (auch Formlabs/OctoPrint/
    Creality, obwohl dort aktuell nie Eintraege entstehen - Konsistenz
    "jeder Drucker bekommt einen Verlauf" wichtiger als Sonderfaelle je
    Typ) oeffnet ein Modal (`openHistoryModal()`) mit Dateiname, Datum
    und Vorschaubild/Platzhalter je Eintrag, plus "Erneut drucken"
    (`reprintHistoryEntry()`) und "Loeschen" (`deleteHistoryEntry()`).
  - **"Erneut drucken" ist additiv, keine Parallel-Logik:**
    `DashboardApp.reprint_from_history()` kopiert die Verlaufsdatei in
    einen frischen temporaeren Job-Ordner (identisch zum Muster von
    `api_print_prepare()`/`api_ultimaker_print()`) und ruft dann fuer
    Bambu-Drucker ganz normal `prepare_print_job()` auf - der Nutzer
    durchlaeuft also wieder den bestehenden AMS-Zuordnungsdialog
    (`openAmsModal()`), NICHT die urspruenglich beim ersten Druck
    gewaehlte Zuordnung blind wiederholt (AMS-Bestueckung kann sich seit
    dem letzten Druck geaendert haben). Fuer Ultimaker wird direkt
    `send_ultimaker_print_now()` wiederverwendet (keine AMS-Zuordnung
    noetig, Druck startet sofort). Die JSON-Antwort der Reprint-Route
    ist bei Bambu bewusst identisch zu `/print/prepare` aufgebaut, damit
    das Frontend `openAmsModal()` unveraendert wiederverwenden kann.
  - Entfernen eines Druckers (`remove_printer()`) loescht seinen
    Verlaufsordner NICHT automatisch (bewusste Entscheidung gegen
    stillen Datenverlust) - er bleibt als verwaister Ordner bestehen und
    kann bei Bedarf manuell geloescht werden.
  - **Getestet (ohne echten Drucker):** vollstaendiger Flask-Test-Client-
    Smoke-Test - Verlaufsordner wird beim Anlegen jedes Druckertyps
    automatisch erzeugt; `add_entry()`/Thumbnail-Extraktion gegen eine
    synthetisch gebaute, aber strukturell echte `.gcode.3mf`-Testdatei
    (`project_settings.config` + `slice_info.config` + `plate_1.png`);
    `GET .../history` liefert den Eintrag; Thumbnail-Route liefert
    korrektes PNG; `POST .../reprint` liefert dieselbe AMS-Vorschau wie
    `/print/prepare` (Filament-/Typ-Filterung nach Plate-1-Nutzung
    korrekt uebernommen); `DELETE` entfernt Eintrag + Dateien, Index
    bleibt bestehen; Pruning-Grenze (30 Eintraege) mit 35 nacheinander
    hinzugefuegten Eintraegen verifiziert (aelteste 5 samt Dateien
    entfernt); Ultimaker-Reprint ohne vorherige Kopplung liefert einen
    sauberen 400-Fehler statt einer Ausnahme; Drucker-Entfernung laesst
    den Verlaufsordner nachweislich unangetastet. Kein Test gegen echte
    Hardware noetig, da diese Funktion ausschliesslich mit bereits vom
    Dashboard verwalteten lokalen Dateien arbeitet, nicht mit neuen
    Drucker-Protokollaufrufen.
- **Kartenlayout 1/2/3-spaltig (neu seit MK6 v1.1.0).** Rein
  praesentatorische Erweiterung, keine Backend-/`config.json`-Aenderung.
  - **CSS:** `main`/`#printerList` ist ein CSS-Grid
    (`grid-template-columns:1fr` im Grundzustand). Zwei Modifier-Klassen
    `.cols-2`/`.cols-3` auf demselben Element schalten auf
    `repeat(2, 1fr)` bzw. `repeat(3, 1fr)` um, inkl. groesserer
    `max-width` (1100px/1600px/2000px), damit die Karten im Mehrspalten-
    Modus nicht unnoetig gestaucht werden. `@media`-Regeln reduzieren die
    Spaltenzahl automatisch bei schmalerem Browserfenster (3→2 unter
    1150px, 2/3→1 unter 760px) - die manuelle Auswahl bleibt dabei
    erhalten, nur die tatsaechlich gerenderte Spaltenzahl weicht
    voruebergehend ab.
  - **Card-interne Aufteilung folgt mit (Container Queries):** `.card-
    body` (Status links, Steuerung rechts) hatte bereits eine
    `@media(max-width:760px)`-Regel fuer schmale Browserfenster. Neu
    zusaetzlich: `.printer-card{ container-type:inline-size; }` +
    `@container (max-width:560px){ .card-body{ grid-template-
    columns:1fr; } }` - dadurch faellt die Karten-Innenaufteilung auch
    dann auf einspaltig zurueck, wenn die KARTE SELBST schmal wird (z. B.
    im 3-Spalten-Modus auf einem normal breiten Monitor), nicht nur bei
    schmalem Gesamtfenster. Rein additiv: Browser ohne Container-Query-
    Unterstuetzung ignorieren die `@container`-Regel einfach und nutzen
    weiterhin nur die bestehende `@media`-Regel - kein Fallback-Risiko.
  - **UI:** neue Schaltflaechen-Gruppe `.layout-switch` (Buttons "1"/"2"/
    "3") im `<header>`, neben "+ Drucker hinzufuegen". Aktiver Modus wird
    per `.layout-btn.active`-Klasse hervorgehoben.
  - **JS:** `setLayoutCols(cols)` setzt/entfernt `.cols-2`/`.cols-3` auf
    `#printerList`, markiert den aktiven Button und schreibt die Wahl in
    `localStorage['dashboardLayoutCols']`. `getLayoutCols()` liest das
    beim Seitenaufruf zurueck (Fallback 1, auch falls `localStorage`
    nicht verfuegbar ist, z. B. privater Modus - Try/Catch). Aufruf
    `setLayoutCols(getLayoutCols())` erfolgt beim Start noch vor
    `loadVersion()`/`refresh()`.
  - **Bewusst `localStorage` statt `config.json`:** dies ist eine reine
    Anzeige-Praeferenz je Browser/Geraet, keine geteilte Dashboard-
    Konfiguration - mehrere Personen/Bildschirme koennen unterschiedliche
    Layouts bevorzugen, ohne sich gegenseitig zu beeinflussen.
  - **Getestet:** `python3 -m py_compile app.py`; Flask-Test-Client-
    Smoke-Test prueft, dass `GET /` die neuen Marker enthaelt
    (`class="layout-switch"`, alle drei `setLayoutCols(n)`-Aufrufe,
    `getLayoutCols`-Funktion, `main.cols-2`/`main.cols-3`-Regeln);
    zusaetzlich `node --check` auf dem extrahierten `<script>`-Block
    (Syntaxpruefung des gesamten Frontend-JS, nicht nur des neuen Teils).
    Kein Hardware-Test noetig (rein clientseitige CSS/JS-Aenderung ohne
    neue Backend-Route).
- **Warteschlange je Drucker (neu seit MK6 v1.2.0).** Groesstes MK6-
  Feature seit dem Druckauftrags-Verlauf - siehe README Abschnitt 3j fuer
  die Nutzersicht. Kernidee: ein Druckauftrag wird nur dann SOFORT an
  einen Bambu-/Ultimaker-Drucker geschickt, wenn dieser gerade NICHT
  beschaeftigt ist; ansonsten landet er in einer neuen, editierbaren
  Warteschlange, die der Nutzer nach Fertigstellung des laufenden Drucks
  per Knopfdruck weiterverarbeitet.
  - **`PRINTER_BUSY_STATES`** (Modul-Konstante, direkt unter
    `PRINT_HISTORY_MAX_JOBS`): dieselbe Zustandsmenge, die `stateClass()`
    im Frontend fuer den "running"/"paused"-Badge nutzt (`RUNNING`,
    `PRINTING`, `WASHING`, `CURING`, `BUSY`, `OPERATIONAL`, plus bewusst
    `PAUSE`/`PAUSED` dazu - ein pausierter Druck belegt den Druckraum
    weiterhin). `DashboardApp.is_printer_busy()` prueft `gcode_state` der
    laufenden `PrinterConnection`/`UltimakerConnection` gegen diese Menge;
    ein unbekannter/nicht verbundener Drucker gilt bewusst als NICHT
    beschaeftigt (sonst waere er das faelschlich dauerhaft, solange noch
    kein Status empfangen wurde - ein echtes Verbindungsproblem wird
    ohnehin beim eigentlichen `send_print()` gemeldet).
  - **`PrintQueueStore`** (neue Klasse, direkt nach `PrintHistoryStore`):
    Ablage strukturell identisch zu `PrintHistoryStore`
    (`print_queue/<drucker-id>/index.json` + `<job_id><endung>` +
    optional `<job_id>.png`), mit EINEM bewussten Unterschied:
    `add_entry()` haengt neue Eintraege am ENDE der Liste an (nicht vorne
    wie beim Verlauf), damit Position 0 immer der AELTESTE/naechste
    Auftrag ist - passend zur gewuenschten Anzeige "aeltester zuerst"
    (Verlauf zeigt bewusst umgekehrt "neuester zuerst"). Zusaetzliches
    Feld je Eintrag: optionales `history_ref` ({"printer_id","job_id"}) -
    gesetzt, wenn der Auftrag urspruenglich aus einem Verlaufseintrag
    stammt. Neue Methode `reorder(printer_id, ordered_job_ids)` validiert,
    dass die uebergebene Menge an job_ids EXAKT der aktuellen Warteschlange
    entspricht (sonst No-Op mit `False`-Rueckgabe) - verhindert Datenverlust
    durch einen veralteten Reorder-Request (z. B. zwei gleichzeitig offene
    Browser-Tabs).
  - **Kein doppelter Verlaufseintrag beim Reprint (neue Anforderung):**
    `PrintHistoryStore.touch_entry(printer_id, job_id)` aktualisiert einen
    BESTEHENDEN Verlaufseintrag (Zeitstempel + an Position 0 verschoben),
    OHNE einen neuen Eintrag anzulegen. `DashboardApp.
    _record_history_after_send(job)` (neue gemeinsame Methode, ersetzt die
    frueher in `start_confirm_print_job()`/`send_ultimaker_print_now()`
    direkt aufgerufene `history.add_entry()`) entscheidet nach jedem
    ERFOLGREICHEN Senden: `job["history_ref"]` gesetzt UND dessen
    `printer_id` == Ziel-`printer_id` des gerade gesendeten Auftrags ->
    `touch_entry()` (kein Duplikat); sonst -> normales `add_entry()` (neuer
    Eintrag - korrekt, wenn der Auftrag einem ANDEREN Drucker zugewiesen
    wurde, denn dort wurde ja tatsaechlich zum ersten Mal gedruckt). Direkt
    im Anschluss: ist `job["queue_ref"]` gesetzt, wird dieser
    Warteschlangen-Eintrag jetzt entfernt (`queue.delete_entry()`) - ERST
    NACH bestaetigtem Erfolg, nicht schon beim Dequeuen (siehe naechster
    Punkt).
  - **`history_ref`/`queue_ref` durch den bestehenden Job-Fluss geschleift:**
    `prepare_print_job()` und `send_ultimaker_print_now()` haben je zwei
    neue optionale Parameter (`history_ref=None, queue_ref=None`), die im
    `_print_jobs[job_id]`-Eintrag mitgespeichert (Bambu) bzw. per Closure
    an den Worker-Thread weitergereicht werden (Ultimaker) - beide Wege
    laufen am Ende durch `_record_history_after_send()`. Rueckwaertskompatibel:
    beide Parameter sind optional, bestehende Aufrufstellen ohne diese
    Argumente verhalten sich unveraendert (`history_ref=None` -> immer
    `add_entry()`, wie vor v1.2.0).
  - **`reprint_from_history()` erweitert:** prueft jetzt zuerst
    `is_printer_busy()`. Beschaeftigt -> `queue.add_entry()` DIREKT mit der
    Verlaufsdatei als Quelle (kein Zwischenkopieren in einen Temp-Ordner
    noetig - `add_entry()` kopiert ohnehin, das Original im Verlauf bleibt
    unangetastet), `history_ref` auf den eigenen Verlaufseintrag gesetzt,
    Rueckgabe `{"mode": "queued", "queue_entry": {...}}`. NICHT
    beschaeftigt -> wie bisher ueber `prepare_print_job()`/
    `send_ultimaker_print_now()`, aber jetzt ebenfalls MIT `history_ref` -
    auch ein direktes (nicht ueber die Warteschlange gelaufenes) "Erneut
    drucken" soll den Verlaufseintrag nur aktualisieren, nicht verdoppeln.
  - **`_copy_to_temp_job_dir(stored_path, filename)`** (neue
    `@staticmethod`): extrahiert das vorher in `reprint_from_history()`
    inline stehende "temporaeren Job-Ordner anlegen + Datei hineinkopieren"
    - jetzt von `reprint_from_history()` UND `start_next_queued_print()`
    gemeinsam genutzt, um Code-Duplikation zu vermeiden. Reines
    Utility-Refactoring ohne Verhaltensaenderung.
  - **`start_next_queued_print(printer_id)`** (neue Methode - "Druckraum
    leer"-Knopf): prueft SICHERHEITSHALBER erneut `is_printer_busy()`
    (verhindert einen versehentlichen Doppel-Klick waehrend eines noch
    laufenden Drucks), nimmt dann den AELTESTEN Warteschlangen-Eintrag
    (`entries[0]`), kopiert dessen Datei in einen frischen Temp-Ordner und
    dispatcht - wortwoertlich identisch zu `reprint_from_history()` - an
    `prepare_print_job()` (Bambu, AMS-Dialog erscheint erneut, da sich die
    Bestueckung seit dem Einreihen geaendert haben kann) bzw.
    `send_ultimaker_print_now()` (Ultimaker, sofortiger Druckstart). Der
    Warteschlangen-Eintrag wird NICHT beim Dequeuen entfernt, sondern erst
    von `_record_history_after_send()` nach bestaetigtem Erfolg - ein
    Abbruch im AMS-Dialog oder ein Sendefehler verliert den Auftrag also
    nicht aus der Warteschlange, "Druckraum leer" kann einfach erneut
    geklickt werden.
  - **Warteschlange manuell bearbeitbar:** `enqueue_upload()` (manueller
    Datei-Upload direkt in die Warteschlange, unabhaengig vom Beschaeftigt-
    Status - fuer vorausschauendes Planen), `reorder_print_queue()`
    (duenner Wrapper um `queue.reorder()`), `delete_print_queue_entry()`.
  - **Zuweisung an einen ANDEREN Drucker (neue Anforderung):**
    `add_history_entry_to_queue(printer_id, job_id, target_printer_id)` -
    kopiert einen Verlaufseintrag in die Warteschlange eines beliebigen
    Ziel-Druckers (Default: der eigene, fuer "In Warteschlange legen"),
    OHNE den Verlaufseintrag selbst zu entfernen; `history_ref` zeigt
    weiterhin auf den URSPRUENGLICHEN Drucker, damit die Dedup-Logik oben
    korrekt entscheidet (touch beim Ursprungsdrucker, add_entry bei jedem
    anderen). `move_queue_entry(printer_id, job_id, target_printer_id)` -
    VERSCHIEBT (nicht kopiert) einen Warteschlangen-Eintrag samt eventuell
    vorhandenem `history_ref` in die Warteschlange eines anderen Druckers
    und entfernt ihn aus der urspruenglichen.
  - **Neue REST-Routen** (alle unter `/api/printers/<id>/...`): `GET
    queue` (Liste, aeltester zuerst), `POST queue` (manueller Upload direkt
    in die Warteschlange), `GET queue/<job_id>/thumbnail`, `DELETE
    queue/<job_id>`, `POST queue/reorder` (Body `{"order": [job_id, ...]}`),
    `POST queue/next` ("Druckraum leer"), `POST queue/<job_id>/assign`
    (Body `{"target_printer_id": ...}`), `POST history/<job_id>/queue`
    (Body optional `{"target_printer_id": ...}`, Default = eigener
    Drucker). Bestehende Routen erweitert: `POST print/prepare` und `POST
    ultimaker/print` pruefen jetzt zuerst `is_printer_busy()` und liefern
    bei beschaeftigtem Drucker `{"mode": "queued", "queue_entry": {...}}`
    statt den normalen AMS-Vorbereitungs-/Sofort-Druck-Antworten; `POST
    history/<job_id>/reprint` kann jetzt ebenfalls `mode: "queued"`
    liefern.
  - **`all_status()` liefert `queue_count`** je Drucker (Laenge der
    Warteschlangen-Liste) - fuer das Zaehl-Badge am Warteschlangen-Symbol
    der Kachel, ueber denselben bestehenden 2,5-Sekunden-Poll (`GET
    /api/status`), kein separater Endpunkt noetig.
  - **Frontend:** neues Listen-Icon (`QUEUE_ICON`, `renderQueueIcon()`) NUR
    auf Bambu-/Ultimaker-Karten (bewusste Scope-Entscheidung - nur diese
    Typen unterstuetzen Druckversand per Dashboard-Upload). Neues Modal
    `queueModal` (Liste mit ▲/▼-Sortier-Buttons, "Zuweisen", "Loeschen",
    Datei-Upload-Button, "Druckraum leer"-Knopf). Neues generisches Modal
    `assignModal` (Dropdown mit allen anderen Bambu-/Ultimaker-Druckern,
    populiert aus `lastPrinterList` - der zuletzt von `refresh()`
    abgerufenen Druckerliste, kein zusaetzlicher Request noetig) - von
    sowohl Verlaufs- als auch Warteschlangen-Eintraegen aus aufrufbar
    (`openAssignModal('history'|'queue', printerId, jobId)`). Verlaufs-
    Modal um Sortier-Umschalter (`toggleHistorySort()`, rein clientseitige
    Sortierung von `lastHistoryEntries` - kein erneuter Server-Request)
    sowie "In Warteschlange"/"Zuweisen"-Buttons erweitert. `dzDrop()`/
    `dzDropUltimaker()` behandeln jetzt `data.mode === 'queued'` (Toast
    statt AMS-Dialog/Sofort-Druck-Polling).
  - **Getestet (ohne echten Drucker):** vollstaendige Kette per Flask-Test-
    Client + direktem Aufruf der `DashboardApp`-Methoden (`gcode_state`
    einer `PrinterConnection` manuell auf `RUNNING`/`IDLE` gesetzt, um
    Beschaeftigt-/Idle-Zustaende zu simulieren, da kein echter Drucker
    verfuegbar ist): Upload waehrend Idle -> normaler `/print/prepare`-Ablauf
    (kein `mode`-Feld); Upload waehrend Busy -> `mode: "queued"`, Datei
    landet nachweislich in der Warteschlange, urspruengliche Temp-Datei
    wird aufgeraeumt; `queue/next` waehrend Busy liefert Fehler (kein
    Absenden); `queue/next` waehrend Idle dispatcht korrekt an
    `prepare_print_job()`, Eintrag bleibt bis zum bestaetigten Erfolg
    erhalten (nach `cancel_print_job()` weiterhin in der Warteschlange
    vorhanden); Reorder mit korrekter/inkorrekter Job-id-Menge (Validierung
    greift); Loeschen; `move_queue_entry()` verschiebt nachweislich
    zwischen zwei Druckern (Quelle leer danach, Ziel hat den Eintrag);
    `_record_history_after_send()` direkt getestet: gleicher Zieldrucker
    wie `history_ref` -> `touch_entry()` (Eintragszahl bleibt bei 1, kein
    Duplikat), ANDERER Zieldrucker -> neuer Eintrag dort, Quelle
    unveraendert; `queue_ref` wird nach simuliertem Erfolg korrekt aus der
    Warteschlange entfernt. Zusaetzlich `python3 -m py_compile app.py`,
    `node --check` auf dem gesamten extrahierten `<script>`-Block, sowie
    ein Flask-Test-Client-Check, dass `GET /` alle neuen HTML-/JS-Marker
    enthaelt (Modals, Funktionen, Icon). Kein Test gegen echte Hardware
    noetig/moeglich, da FTPS-Upload und MQTT-Druckstart bereits durch die
    bestehenden, unveraendert wiederverwendeten Funktionen
    (`prepare_print_job()`/`send_ultimaker_print_now()`) abgedeckt sind.
- **"Druckraum leer" bei Bambu Lab: strengere Bereitschaftspruefung (seit
  v2.0.1).** Bis v1.2.0 durfte die Warteschlange fortgesetzt werden,
  sobald der Drucker NICHT in `PRINTER_BUSY_STATES` war - das schloss
  Uebergangszustaende wie `PREPARE`/`SLICING` (Drucker raeumt intern noch
  auf/bereitet sich vor, ist aber noch nicht wirklich fertig) faelschlich
  mit ein. Auf expliziten Nutzerwunsch verlangt Bambu Lab jetzt EXPLIZIT
  einen der `BAMBU_READY_FOR_NEXT_STATES` (`FINISH` oder `IDLE`) - neue
  Konstante direkt unter `PRINTER_BUSY_STATES`.
  - **`DashboardApp.is_ready_for_next_print(printer_id)`** (neue Methode,
    ersetzt NUR fuer `start_next_queued_print()` die bisherige
    `is_printer_busy()`-Pruefung - `is_printer_busy()` selbst bleibt
    unveraendert und wird weiterhin fuer die Auto-Warteschlangen-
    Entscheidung beim Upload/Reprint verwendet, siehe Kommentar an der
    Methode): bei Bambu Lab `gcode_state in BAMBU_READY_FOR_NEXT_STATES`,
    bei allen anderen Typen (aktuell nur Ultimaker relevant) unveraendert
    `not is_printer_busy()` - der Nutzer hat die Verschaerfung
    ausdruecklich nur fuer "bambulab" verlangt.
  - **`start_next_queued_print()`** ruft jetzt `is_ready_for_next_print()`
    statt `is_printer_busy()` auf und liefert bei Bambu Lab eine
    spezifischere Fehlermeldung ("...Status muss FINISH oder IDLE
    sein...").
  - **Frontend:** neuer Button `id="queueSendNextBtn"` + Hinweistext
    `id="queueSendHint"` im `queueModal`. Neue Funktion
    `updateQueueSendButtonState()` spiegelt dieselbe Logik client-seitig
    (JS-Konstante `PRINTER_BUSY_STATES_JS` als Spiegel von
    `PRINTER_BUSY_STATES` - bei Aenderung dort auch hier nachziehen) und
    deaktiviert den Knopf, solange der Drucker (bei Bambu: Status nicht
    `FINISH`/`IDLE`) nicht bereit ist ODER die Warteschlange leer ist -
    inkl. Hinweistext mit dem aktuellen Status. Wird sowohl beim
    Oeffnen/Aktualisieren des Warteschlangen-Modals als auch bei JEDEM
    regulaeren 2,5-Sekunden-Status-Poll (`refresh()`) neu ausgewertet,
    solange das Modal offen ist - der Knopf wird also automatisch aktiv,
    sobald der Druck fertig ist, ohne dass der Nutzer das Modal schliessen
    und neu oeffnen muss. Die serverseitige Pruefung in
    `start_next_queued_print()` bleibt in jedem Fall zusaetzlich bestehen
    (Client-Deaktivierung ist Komfort, keine alleinige Absicherung).
  - **`APP_VERSION` 1.2.0 -> 2.0.1** auf ausdruecklichen Wunsch des
    Nutzers (als Gesamtsumme mehrerer MK6-Aenderungen), nicht ueber die
    sonst uebliche Automatik (README Abschnitt 0a) hergeleitet - im Code
    per Kommentar direkt bei `APP_VERSION` dokumentiert.
  - **Getestet:** direkte Methodentests fuer `is_ready_for_next_print()`/
    `start_next_queued_print()` mit `gcode_state` manuell auf `RUNNING`,
    `PREPARE` (Uebergangszustand, bewusst NICHT in `PRINTER_BUSY_STATES`,
    aber trotzdem als "nicht bereit" bestaetigt), `FINISH` und `IDLE`
    gesetzt - jeweils erwartetes Verhalten (abgelehnt/abgelehnt/
    dispatcht/bereit) verifiziert; Ultimaker-Verhalten unveraendert
    bestaetigt (busy/idle weiterhin ausreichend). Zusaetzlich `python3 -m
    py_compile app.py`, `node --check` auf dem vollstaendigen extrahierten
    `<script>`-Block, sowie ein Flask-Test-Client-Check, dass `GET /` die
    neuen Marker (`queueSendNextBtn`, `queueSendHint`,
    `updateQueueSendButtonState`, `PRINTER_BUSY_STATES_JS`) enthaelt.

---

## 6. Wichtige Design-Entscheidungen / Lessons Learned (bitte beachten!)

1. **Keine Endpunkte raten.** Der erste Formlabs-Versuch hat mit
   geratenen HTTP-Pfaden gearbeitet – das hat in der Praxis nicht
   funktioniert ("zeigt keine Daten an"). Seitdem gilt: neue Integrationen
   nur auf Basis von tatsächlich recherchierten/dokumentierten APIs
   umsetzen (offizielle Doku, Community-Reverse-Engineering mit
   Quellenbeleg, oder zumindest mehrere unabhängige Quellen). Wenn keine
   verlässliche API bekannt ist (z. B. Creality-Modelle mit reinem
   "Creality OS" ohne Klipper), wird die Integration **bewusst
   weggelassen** statt geraten – siehe README, Abschnitt 3d.
2. **Defensive Parsing als Fallback**, wenn das genaue Antwortformat
   unsicher ist (z. B. `FormlabsLocalApiConnection._find_first()` sucht
   rekursiv nach plausiblen Feldnamen statt starre Keys vorauszusetzen).
   Wird bewusst eingesetzt, wenn eine API zwar real existiert, ihr exaktes
   JSON-Schema aber nicht mit Sicherheit bekannt ist.
3. **Bugfix-Beispiel Bambu Kammertemperatur:** Die `pushall`-MQTT-Anfrage
   brauchte laut Bambu-Protokoll zwingend `"version": 1` und
   `"push_target": 1` - ohne diese Felder hat die Firmware den Request
   komplett ignoriert. Immer bei "Wert kommt nie an"-Bugs zuerst die
   Rohantwort/das exakte Request-Format gegen die Originaldokumentation
   prüfen, bevor Umgehungslösungen gebaut werden.
4. **Jede Änderung wird getestet, bevor sie ausgeliefert wird:**
   - `python3 -m py_compile app.py` (Syntax) - **Achtung:** prueft nur
     gegen die lokal installierte Python-Version (hier 3.12), nicht
     gegen die vom GitHub-Actions-Build genutzte Version (3.11) - siehe
     Punkt 6 unten fuer die daraus resultierende Faustregel.
   - Ein kurzes Python-Testskript, das `app.dash.add_printer(...)` für
     jeden betroffenen Typ aufruft und `app.app.test_client()` für die
     relevanten Routen nutzt (siehe vorherige Chat-Historie für konkrete
     Beispiele).
   - Vor jedem Ausliefern `rm -f config.json`, damit keine Test-Drucker
     versehentlich in der ausgelieferten Beispiel-Config landen.
5. **"Ohne den bisherigen Aufbau zu ändern" ernst nehmen:** Neue
   Druckertypen/Features werden **additiv** eingebaut (neue Klassen, neue
   `elif`-Zweige, neue Konstanten) statt bestehende Funktionen
   umzuschreiben. Rückwärtskompatibilität von `config.json` wird über
   `setdefault()` in `load_config()` sichergestellt.
6. **`py_compile` beim Entwickeln reicht nicht - Ziel-Python-Version
   beachten.** `.github/workflows/build-exe.yml` baut explizit mit
   **Python 3.11** (bewusste, stabile Wahl). Lokales Testen/Entwickeln
   lief bislang mit Python 3.12, das mehr Syntax erlaubt als 3.11 (z. B.
   Backslashes im Ausdrucksteil eines f-strings, seit PEP 701/Python
   3.12). Ein `python3 -m py_compile app.py` unter 3.12 erkennt solche
   Faelle NICHT als Fehler, obwohl der GitHub-Actions-Build (Python
   3.11) dann mit `SyntaxError: f-string expression part cannot include
   a backslash` fehlschlaegt (siehe v1.4.8-Bugfix in Abschnitt 5).
   **Faustregel fuer neue f-strings:** keine Backslashes (`\n`, `\t`,
   escaped quotes etc.) direkt im `{...}`-Ausdrucksteil verwenden -
   den entsprechenden String-Teil immer vorher in eine eigene Variable
   auslagern und nur diese Variable im f-string referenzieren. Bei
   Unsicherheit: der Container hier hat keinen Zugriff auf einen
   Python-3.11-Interpreter (nur 3.12 vorinstalliert, `apt install
   python3.11` nicht in den erlaubten Paketquellen) - ein manueller
   Regex-Scan auf "Backslash innerhalb von geschweiften Klammern in
   einem f-string" ist ein brauchbarer Ersatz-Check, falls unsicher.

---

## 7. Bekannte Unsicherheiten / offene Punkte für die Weiterarbeit

- **H2-, P1-, P2- und X2-Serie als Druckerfamilie waehlbar seit v1.6.7/
  v1.6.8 - FTPS-Profil "x1" ist fuer alle vier eine unbestaetigte
  Annahme (fuer P1 etwas besser abgesichert), kein Test gegen echte
  Hardware fuer irgendeine davon moeglich.** Der Nutzer bat explizit
  darum, alle vier mangels eigener Erkenntnisse vorerst wie die
  X1-Serie zu behandeln (`BAMBU_FAMILY_TO_FTPS_PROFILE["h2"/"p1"/"p2"/
  "x2"] = "x1"`, siehe Abschnitt 5 "v1.6.7"/"v1.6.8"). Falls ein Nutzer
  mit einer dieser Serien einen FTPS-Fehler meldet: zuerst pruefen, ob
  der automatische Fallback (Profil "a1" im zweiten Versuch) erfolgreich
  ist - falls ja, genuegt eine einzeilige Aenderung der Zuordnungstabelle
  fuer die betroffene Familie. Falls WEDER "x1" NOCH "a1" funktionieren,
  waere ein komplett neues, drittes Profil noetig - dann dieselbe
  Diagnose-Methodik wie beim A1-Mini-Fall anwenden (Vergleich mit Bambu
  Studio, TLS-Version/Sitzungs-Wiederverwendung/Verbindungsabschluss
  systematisch durchtesten, siehe Chronologie zu v1.5.0-v1.6.0).
- **Ultimaker-Druckauftrag per Drag & Drop (v1.6.3-v1.6.5) - Ursache
  endgueltig geklaert durch direkte Einsicht in den echten Nachbau-
  Quellcode, Bestaetigung durch Nutzer noch ausstehend.** Erster
  Praxistest lief gegen einen Nachbau ("Ultimaker Connect Raspi MK1",
  ein separates Claude-Projekt aus einem anderen Chat), nicht gegen
  echte Ultimaker-Hardware. Kopplung funktionierte durchgehend, der
  Druckstart scheiterte zunaechst zweimal in Folge (v1.6.3, v1.6.4),
  da beide Fixes auf VERMUTUNGEN ueber das Nachbau-Verhalten beruhten
  (der zugehoerige Chat war trotz mehrerer `conversation_search`-
  Versuche nicht auffindbar). Erst nachdem der Nutzer `app.py`,
  `README.md` UND `ultimaker_api.py` des Nachbaus direkt als
  Projekt-Dateien hochlud, liess sich die tatsaechliche Ursache klar
  erkennen: **der Nachbau prueft beim Druckstart (`POST /api/v1/
  print_job`) ueberhaupt keine Authentifizierung** - er verlangt nur,
  dass ein Datei-Feld vorhanden ist. Das Kopplungs-Handshake (auth/
  request + auth/check) ist rein kosmetisch fuer Cura's Verbindungs-
  Dialog, das dabei erzeugte id/key-Paar wird nie ueberprueft. Fix
  (v1.6.5): `_digest_challenge_or_none()` liefert jetzt `None` statt
  eine Exception zu werfen, wenn die Probe-Anfrage keine 401-Digest-
  Antwort bekommt - `send_print()` sendet dann ohne Authorization-
  Header. Echte Ultimaker-Hardware (verlangt zwingend Digest-Auth)
  bleibt davon unberuehrt. Siehe Abschnitt 5 "v1.6.5" fuer
  vollstaendige Details. **Noch KEIN Test gegen echte Ultimaker-
  Original-Hardware; Bestaetigung fuer den Nachbau durch den Nutzer
  stand zum Zeitpunkt dieser Übergabe ebenfalls noch aus** - diesmal
  aber mit deutlich hoeherer Zuversicht, da der Fix gegen den
  tatsaechlichen, vom Nutzer bereitgestellten Server-Code verifiziert
  wurde, nicht nur gegen eine Vermutung.
- **Formlabs-Feldnamen** (`FL_PROGRESS_KEYS`, `FL_FILE_KEYS`,
  `FL_MATERIAL_KEYS`, `FL_STATE_KEYS` in `app.py`) sind nicht an einem
  echten Gerät verifiziert, nur aus Doku-Fragmenten plausibel abgeleitet.
  Falls ein Nutzer meldet, dass Formlabs-Karten leer bleiben (obwohl
  PreFormServer läuft), zuerst die rohe JSON-Antwort von
  `GET http://localhost:44388/devices/` bzw. `/devices/{id}/` einsehen
  lassen und die Konstanten entsprechend ergänzen.
- **Ultimaker-Feldnamen** (`/api/v1/print_job`: `name`, `progress`,
  `time_elapsed`, `time_total`) sind mit mittlerer Sicherheit aus
  Community-Quellen/Cloud-API-Doku abgeleitet, aber nicht an echter
  Hardware getestet. Gleiches Vorgehen wie bei Formlabs, falls Daten
  fehlen: rohe Antwort von `http://<IP>/api/v1/print_job` prüfen.
- **Kein UI-Editor für Extras (Sensoren/Schalter).** Aktuell nur über
  manuelles Bearbeiten von `config.json` möglich. Ein Formular dafür wäre
  ein sinnvoller nächster Ausbauschritt, wurde aber aus Aufwandsgründen
  bisher nicht umgesetzt.
- **Keine Authentifizierung am Dashboard selbst.** Es ist für den Betrieb
  im vertrauenswürdigen LAN gedacht, nicht für den Betrieb im offenen
  Internet.
- **Bambu-Kamera-Protokoll** ist reverse-engineert (Community-Wissen,
  nicht offiziell von Bambu Lab dokumentiert) und könnte durch ein
  Firmware-Update brechen.
- **Druckauftrag-Feature (Abschnitt 5) ist ebenfalls reverse-engineert**
  (FTPS-Upload + MQTT `project_file`, keine offizielle Bambu-API) und
  könnte durch ein Firmware-Update brechen — gleiche Kategorie wie das
  Kamera-Protokoll. Das gilt auch für die AMS-Zuordnung: die
  Umrechnungsregel "4 Fächer pro AMS-Einheit" (`_slot_to_flat_index()`)
  ist Community-Konvention, nicht offiziell dokumentiert.
- **AMS-Zuordnungsvorschlag matcht nur auf exakte Farbe (+ groben
  Typ-Abgleich).** Kein Abgleich auf `filament_id`/Hersteller-SKU, kein
  RFID-Abgleich wie bei manchen kommerziellen Tools. Bei zwei optisch
  identischen Farben in unterschiedlichen Fächern wird das erste
  unbenutzte Fach vorgeschlagen (Reihenfolge in `self.status["ams"]`) —
  der Nutzer sieht und bestätigt das aber im Dialog vor dem Drucken, es
  ist also (seit v1.2.0) kein automatischer Blindgriff mehr.
- **Kein Fortschritts-/Upload-Balken beim Bestätigen.** ~~Der Button
  zeigt nur "Wird gesendet ..." ohne Prozentfortschritt des
  FTPS-Uploads selbst.~~ **Seit v1.4.0 erledigt** (Fortschrittsbalken +
  Prozent + Byte-Anzeige, siehe Abschnitt 5).
- **FTPS-Upload: X1-Serie (X1C, X1E) VOM NUTZER BESTAETIGT FUNKTIONS-
  FAEHIG. A1 Mini: geloest in v1.6.0 (fuenfter Anlauf), Bestaetigung
  durch Nutzer ausstehend.** Vollstaendige Chronologie siehe Abschnitt 5
  "Bambu Lab: Druckauftrag...". Kurzfassung der Fehldiagnosen: v1.5.7
  (Sitzungs-Wiederverwendung allein), v1.5.8 (TLS-Version + Sitzungs-
  Wiederverwendung als "x1"/"a1"-Profile), v1.5.9 (Zeitlimit 25s→120s,
  Theorie: Drucker sei nur langsam) - alle scheiterten beim Nutzer-Test
  identisch mit "The read operation timed out" bei 100% uebertragenen
  Bytes. **Entscheidender neuer Datenpunkt:** der Nutzer verglich mit
  Bambu Studio - dieselbe Datei wird dort bereits 1-2 Sekunden nach
  Erreichen von 100% erfolgreich uebertragen, was die "Drucker ist
  langsam"-Theorie aus v1.5.9 endgueltig widerlegte. **Tatsaechliche
  Ursache (v1.6.0):** Pythons `ftplib.storbinary()` ruft nach der
  Uebertragung automatisch einen formalen TLS-Verbindungsabschluss
  (`unwrap()`) auf, auf den der A1 Mini offenbar nicht sauber reagiert -
  waehrend Bambu Studio (eigene Implementierung) das vermutlich gar
  nicht erst abwartet. Fix: `_storbinary_no_unwrap()` (bereits einmal
  in v1.5.0 fuer die X1-Serie implementiert und dort wieder verworfen,
  jetzt gezielt nur fuer das "a1"-Profil reaktiviert) - siehe Abschnitt
  5 fuer vollstaendige Details. Wichtig: dieselbe Technik ist fuer die
  X1-Serie SCHAEDLICH (426-Fehler, siehe v1.5.0-Historie), fuer den A1
  Mini aber die Loesung - ein weiterer Beleg fuer grundverschiedene
  FTPS-Server-Implementierungen zwischen beiden Druckerfamilien.
  **Fuer die Weiterarbeit, falls der Fehler nach v1.6.0 weiterhin
  auftritt** (das waere der SECHSTE Anlauf):
  1. Pruefen, ob der Fehlertext identisch bleibt oder sich aendert (z. B.
     zu einem `426`-artigen Fehler, wie er bei der X1-Serie ohne
     `unwrap()` auftrat) - das waere ein wichtiges neues Datum.
  2. Falls weiterhin exakt derselbe Timeout: ein Wireshark-Mitschnitt
     von Bambu Studio (erfolgreich) vs. unserem Dashboard (scheiternd)
     fuer denselben Druckauftrag waere der praeziseste naechste Schritt -
     zeigt exakt, an welcher Stelle im TLS-/FTP-Protokollablauf sich
     beide Implementierungen tatsaechlich unterscheiden, statt weiter zu
     vermuten.
  3. Alternativ: die Blockgroesse (aktuell fest 8192 Bytes) systematisch
     variieren, falls sich ein Zusammenhang zur Dateigroesse zeigt.
  **Workaround, falls weiterhin ungeloest:** Datei manuell per FileZilla
  oder Bambu Studio hochladen, Druck am Display starten (README
  Abschnitt 4a).
- **Mehrfarb-/Mehrmaterial-Druck (X1C) - VOLLSTAENDIG behoben (zwei
  zusammenhaengende Ursachen, v1.5.10 + v1.6.2), Bestaetigung durch
  Nutzer fuer den zweiten Fix noch ausstehend.** Zwei getrennte, nach-
  einander aufgetretene Probleme, beide ausschliesslich beim Start
  ueber das Dashboard (derselbe Druckauftrag lief bei manuellem Start
  am Display jeweils problemlos an): (1) v1.5.10: Drucker begann nicht
  mit dem Aufheizen des Druckbetts - Ursache war `flow_cali` fest auf
  `False` statt dem von der Referenzbibliothek `bambulabs_api`
  standardmaessig verwendeten `True`. Fix bestaetigt wirksam (der
  Nutzer berichtete danach ueber einen ANDEREN, neuen Fehler - das
  Aufheiz-Problem selbst trat nicht wieder auf). (2) v1.6.2: neuer
  Fehler "Die Zuordnungstabelle des AMS konnte nicht abgerufen werden"
  ("Failed to get AMS mapping table") - Ursache war ein echter,
  struktureller Indexierungsfehler: das an den Drucker gesendete
  `ams_mapping`-Array wurde kompakt in ANZEIGE-Reihenfolge gebaut statt
  an den ECHTEN Filament-Positionen aus der `.gcode.3mf`, was bei
  Projekten mit mehr definierten Filamenten als auf der gedruckten
  Platte tatsaechlich verwendet (Indexluecken) zu einer fuer den
  Drucker ungueltigen Zuordnungstabelle fuehrte. Fix betrifft Backend
  UND Frontend gemeinsam (siehe Abschnitt 5 fuer vollstaendige Details,
  inkl. isoliertem Node.js-Test der JS-Logik). Anders als bei den
  FTPS-Themen ist dies ein klar bewiesener struktureller Bug, kein
  Verhaltens-Experiment - entsprechend hohe Zuversicht in die Loesung.
  **Fuer die Weiterarbeit, falls "Failed to get AMS mapping table" nach
  v1.6.2 weiterhin auftritt:** ein MQTT-Sniffer-Vergleich (Bambu Studio
  vs. unser Dashboard fuer denselben Mehrfarb-Druckauftrag) waere der
  naechste, praeziseste Schritt, um zu pruefen, ob es noch eine weitere,
  bisher unentdeckte Indexierungs-Eigenheit gibt (z. B. falls die
  Filament-Nummerierung in bestimmten Faellen doch nicht 0-basiert waere).
- **Farb-Zuordnung im AMS verlangte byte-genaue Uebereinstimmung -
  behoben in v1.6.6, Bestaetigung durch Nutzer ausstehend.** Ein X1C
  zeigte erneut das "Aufheizen des Druckbetts"-Haengenbleiben, diesmal
  bei einem EINFARBIGEN Druck mit automatischer AMS-Zuordnung (Mehrfarb-
  Drucke funktionierten seit v1.5.10/v1.6.2 zuverlaessig). Nach mehreren
  Diagnose-Abzweigungen (flow_cali-Regression vermutet, dann verworfen;
  JS-Bug beim Lesen des Vorschlags vermutet, dann per Code-Review
  widerlegt) stellte sich heraus: der AMS-Dialog zeigte "Keine passende
  Farbe im AMS gefunden", OBWOHL das entsprechende Fach nachweislich
  die richtige Farbe (Blau) enthielt. Ursache: `_find_matching_tray()`
  verlangte eine BYTE-GENAUE Hex-Farb-Uebereinstimmung - der vom Slicer
  hinterlegte und der vom AMS/RFID gemeldete Farbwert fuer "dieselbe"
  Farbe muessen aber nicht byte-identisch sein. Erklaert auch eine
  fruehere Beobachtung des Nutzers zu Gruen/Hellgruen. Fix: neue
  `_color_distance()`-Funktion (euklidischer RGB-Abstand) mit bewusst
  konservativer Toleranz (`COLOR_MATCH_TOLERANCE = 30`) - faengt kleine
  Profilabweichungen ab, verwechselt aber NICHT tatsaechlich
  unterschiedliche Farben wie Gruen/Hellgruen (Distanz ~231, weit
  ausserhalb der Toleranz). Siehe Abschnitt 5 "v1.6.6" fuer
  vollstaendige Details, inkl. einer separaten, noch offenen
  Beobachtung (Drucker zeigt bei echtem "Extern/manuell"-Rueckfall
  keine Material-Abfrage, sondern haengt) - dafuer waere bei Bedarf ein
  MQTT-Sniffer-Vergleich mit Bambu Studio der naechste Schritt.
- **AMS-Zuordnung bei Verbundwerkstoffen (PLA-CF, PETG-CF, ASA-CF, PA-CF,
  ABS-GF usw.) - Fix in v1.5.5 ausgeliefert, war aber NICHT die Ursache
  des konkret gemeldeten Falls (siehe naechster Punkt fuer die
  tatsaechliche Ursache).** Urspruengliche Vermutung: die Typ-Pruefung
  in `_find_matching_tray()` nutzte einen reinen Teilstring-Vergleich,
  der "ASA" faelschlich als Teilmenge von "ASA-CF" akzeptierte. Der
  Fix (`_types_compatible()`, siehe Abschnitt 5) ist weiterhin sinnvoll
  und bleibt bestehen - der Nutzer bestaetigte aber, dass die AMS-
  Zuordnung in seinem konkreten Fall schon VOR diesem Fix korrekt war
  (ASA-CF wurde tatsaechlich vorgeschlagen und war im Drucker geladen).
- **Druck haengt beim Materialladen (kein Fehlerdisplay) - Ursache
  gefunden und behoben in v1.5.6, Bestaetigung durch Nutzer ausstehend.**
  Nach Ausschluss der AMS-Zuordnung als Ursache (siehe oben) fiel beim
  Vergleich mit dokumentierten Referenz-MQTT-Payloads auf: das
  `project_file`-Kommando fehlte mehrere Felder, allen voran `bed_type`
  - ohne dieses Feld ist unklar, welchen Druckbett-Typ die Firmware
  annimmt, was bei anspruchsvolleren Materialien (ASA-CF: hohe
  Bett-/Duesentemperatur) eher zu Problemen fuehrt als bei PLA. Fix:
  vollstaendiger Feldsatz ergaenzt (`bed_type: "auto"`, `subtask_name`,
  `project_id`/`profile_id`/`task_id`, siehe Abschnitt 5 fuer Details).
  **Fuer die Weiterarbeit, falls das Problem nach v1.5.6 weiterhin
  auftritt:** Ein MQTT-Sniffer (MQTT Explorer, mosquitto_sub) parallel
  zu einem erfolgreichen Bambu-Studio-Druck auf demselben Drucker
  mitlaufen lassen und den *tatsaechlich* gesendeten `project_file`-
  Befehl direkt (Byte-fuer-Byte-JSON-Diff) mit unserem vergleichen -
  das zeigt den fuer DIESE konkrete Firmware-Version tatsaechlich
  erwarteten Befehl, zuverlaessiger als weitere Community-Referenzen.
  Separat, unabhaengig von diesem Thema: Auf dem A1 Mini hat die
  Datei-Uebertragung (mit Python-`ftplib`, v1.4.5) funktioniert, der
  Druck selbst startete aber nicht - laut Nutzer wahrscheinlich, weil
  kein passendes Material ausgewaehlt/geladen war. Das ist vermutlich
  kein Bug, sondern normales Verhalten (siehe `send_print()`/
  `_request_print()`: ohne AMS-Daten fallen alle Filamente auf
  "Extern/manuell" zurueck, `use_ams` wird `False` - der Druck muesste
  dann eigentlich trotzdem starten, ggf. mit Nachfrage am Display
  welches Material eingelegt ist). Falls das beim naechsten Test
  weiterhin auftritt, lohnt sich ein genauerer Blick auf die genaue
  Fehlermeldung/das Verhalten am Drucker-Display.
- **Kein Live-Neuladen der AMS-Vorschau, falls sich der AMS-Inhalt
  während der Dialog offen ist ändert.** Die Vorschläge basieren auf dem
  Status zum Zeitpunkt des Drag & Drop (`preview_print()`); wechselt der
  Nutzer waehrenddessen z. B. eine Spule, muss die Datei erneut
  gezogen werden, um einen aktualisierten Vorschlag zu bekommen (die
  manuelle Korrektur im Dropdown funktioniert davon unabhängig trotzdem).
- **Farbwort-Zuordnung ist eine Näherung** (`NAMED_COLORS` in `app.py`,
  ca. 30 Einträge, nächster RGB-Abstand). Bei changierenden/gemischten
  Filamenten (z. B. "Silk Dual Color") kann das angezeigte Wort nur
  ungefähr passen — der exakte Hex-Wert bleibt per Tooltip abrufbar.
- **macOS-Build ist unsigniert/nicht notarisiert** (GitHub Actions,
  `.github/workflows/build-exe.yml`, Runner `macos-14` = natives Apple
  Silicon). Nutzer müssen die Gatekeeper-Warnung beim ersten Start
  einmalig bestätigen (siehe README, Abschnitt 0).

---

## 9. Versionierung & Commit-Konvention

**MK6 startet die Versionszaehlung bewusst neu bei v1.0.0.** Grund:
MK6 ist ein eigenstaendig weitergefuehrtes Projekt (neuer Chat/neue
Übergabe-Kette), technisch aber ein rein additiver Fortsatz von MK5
v1.6.8 - kein Rewrite, keine Breaking Changes gegenueber MK5. Die
detaillierte, chronologische Versionshistorie von MK5 (v1.0.0 bis
v1.6.8, insbesondere die lange FTPS-Debugging-Saga) bleibt in der
MK5-`UEBERGABE.md` erhalten und gilt technisch unveraendert fort (siehe
Abschnitt 6/7 dieser Datei fuer die daraus uebernommenen Lessons
Learned) - sie wird hier nicht dupliziert, nur fortgesetzt.

- **v1.0.0 (MK6, diese Übergabe):** Basis = MK5 v1.6.8, unveraendert.
  Neues Feature (kein Bugfix): **Druckauftrags-Verlauf je Drucker** -
  automatisch angelegter Ordner neben der exe/dem Skript
  (`print_history/<drucker-id>/`), befuellt bei jedem erfolgreich ueber
  das Dashboard gesendeten Druckauftrag (Bambu, Ultimaker), einsehbar/
  erneut startbar/loeschbar ueber ein neues Untermenue an jeder Drucker-
  Kachel. Siehe Abschnitt 5 (Unterabschnitt "Druckauftrags-Verlauf") fuer
  die vollstaendige technische Beschreibung und den Testumfang.
- **v1.1.0 (MK6):** Neues Feature (kein Bugfix, rein additiv):
  **waehlbares Kartenlayout (1/2/3-spaltig)** fuer die Drucker-Kacheln.
  CSS-Grid auf `#printerList` mit Modifier-Klassen `.cols-2`/`.cols-3`,
  Umschalt-Buttons im Header, Auswahl je Browser in `localStorage`
  gemerkt (keine `config.json`-Aenderung). Card-interne Zweispalten-
  Aufteilung faellt zusaetzlich per CSS Container Query auf einspaltig
  zurueck, wenn die einzelne Karte schmal wird (z. B. im 3-Spalten-
  Modus), unabhaengig von der Fensterbreite. Siehe Abschnitt 5
  (Unterabschnitt "Kartenlayout 1/2/3-spaltig") fuer die vollstaendige
  technische Beschreibung und den Testumfang.
- **v1.2.0 (MK6):** Neues Feature (kein Bugfix, rein additiv): **Warte-
  schlange je Drucker** fuer Bambu Lab/Ultimaker. Ein Druckauftrag wird
  nur noch sofort gesendet, wenn der Drucker gerade NICHT beschaeftigt
  ist (`PRINTER_BUSY_STATES`/`is_printer_busy()`) - sonst landet er in
  einer neuen, editierbaren Warteschlange (`PrintQueueStore`), die per
  "Druckraum leer"-Knopf (`start_next_queued_print()`) nach Abschluss des
  laufenden Drucks weiterverarbeitet wird. Reihenfolge aeltester zuerst
  (bewusst umgekehrt zum Verlauf). Zusaetzlich: manuelles Hinzufuegen/
  Umsortieren/Loeschen in der Warteschlange, Uebernahme von Verlaufs-
  eintraegen in eine Warteschlange, Zuweisen von Verlaufs-/Warteschlangen-
  Eintraegen an einen ANDEREN Drucker im Dashboard, alphabetische
  Sortierung im Verlauf umschaltbar, sowie ein Dedup-Mechanismus
  (`PrintHistoryStore.touch_entry()`/`DashboardApp.
  _record_history_after_send()`), der verhindert, dass ein an DENSELBEN
  Drucker erneut gesendeter Verlaufseintrag doppelt im Verlauf auftaucht.
  Siehe Abschnitt 5 (Unterabschnitt "Warteschlange je Drucker") fuer die
  vollstaendige technische Beschreibung und den Testumfang.
- **v2.0.1 (MK6):** Verhaltensverfeinerung (kein Bugfix, additiv): bei
  Bambu Lab darf die Warteschlange erst fortgesetzt werden ("Druckraum
  leer"-Knopf), wenn der Drucker EXPLIZIT den Status `FINISH` oder `IDLE`
  meldet (`BAMBU_READY_FOR_NEXT_STATES`/`DashboardApp.
  is_ready_for_next_print()`) - bisher reichte "nicht in
  `PRINTER_BUSY_STATES`", was Uebergangszustaende wie `PREPARE`/`SLICING`
  faelschlich zuliess. Der Knopf im Frontend ist jetzt bis dahin
  deaktiviert (`updateQueueSendButtonState()`, live aktualisiert ueber den
  bestehenden 2,5-Sekunden-Status-Poll) statt erst beim Klick einen
  Serverfehler zu melden. Ultimaker-Verhalten unveraendert. Versionssprung
  1.2.0 -> 2.0.1 auf ausdruecklichen Nutzerwunsch (Gesamtsumme mehrerer
  MK6-Aenderungen), nicht nach der sonst ueblichen Automatik hergeleitet.
  Siehe Abschnitt 5 (Unterabschnitt ""Druckraum leer" bei Bambu Lab:
  strengere Bereitschaftspruefung") fuer die vollstaendige technische
  Beschreibung und den Testumfang.
- **v2.1.0 (MK6):** Vier additive Verbesserungen, keine davon ein Bugfix:
  1. **Drag & Drop in die Warteschlange:** die Drop-Zone im Warteschlangen-
     Fenster (`#queueDropZone`) nimmt Dateien jetzt genau wie die Drucker-
     Kachel selbst per Drag & Drop entgegen (`dzDropQueue()`), zusaetzlich
     zum bestehenden Datei-Auswahl-Button. Beide Wege teilen sich jetzt die
     Upload-Logik ueber die neue gemeinsame Funktion `uploadFileToQueue()`
     (vorher nur in `addFileToQueue()` enthalten). Client-seitige
     Endungspruefung anhand des Druckertyps des offenen Modals (`.gcode.3mf`
     bei Bambu, `.gcode` bei Ultimaker), serverseitige Pruefung unveraendert.
  2. **Loesch-Schaltflaechen/-Symbole durchgehend rot:** `.del-icon` ist
     jetzt permanent (nicht erst bei Hover) in der Warnfarbe `--danger`
     eingefaerbt; die "Loeschen"-Knoepfe in Verlauf/Warteschlange nutzen
     dafuer eine neue, eigene CSS-Klasse `.btn-mini.btn-delete` - bewusst
     NICHT die bestehende `.btn-mini.off`, da diese auch fuer den
     unabhaengigen "Aus"-Knopf eines Sensoren/Schalter-Eintrags
     (`renderExtras()`) verwendet wird, der fachlich keine destruktive
     Aktion ist und daher nicht rot werden soll.
  3. **Temperaturanzeige auf max. 2 Nachkommastellen gerundet:** neue
     JS-Hilfsfunktion `formatTemp(v)` (Duesen-/Bett-/Kammertemperatur bei
     allen unterstuetzten Druckertypen), da einzelne Backends (v. a.
     Bambu-MQTT) Werte mit deutlich mehr Nachkommastellen liefern, als fuer
     die Anzeige sinnvoll ist. Rein darstellungsseitig, keine Aenderung an
     gespeicherten/uebertragenen Rohwerten.
  4. **Zuweisen nur innerhalb derselben Bambu-Druckerfamilie:** ein
     Verlaufs- oder Warteschlangen-Eintrag kann nur noch einem Drucker
     DESSELBEN Typs zugewiesen werden, bei Bambu Lab zusaetzlich nur
     einem Drucker derselben `bambu_family` (z. B. nur A1 untereinander,
     nur X1 untereinander) - ein fuer eine Familie vorbereiteter
     Druckauftrag (Slicing/AMS-Zuordnung) ist auf einer anderen nicht
     ohne Weiteres gueltig. Umgesetzt ueber eine neue gemeinsame
     Backend-Pruefung `DashboardApp._validate_assign_target()`, angewendet
     in `add_history_entry_to_queue()` und `move_queue_entry()`;
     `all_status()` liefert dafuer neu `bambu_family` je Bambu-Drucker
     mit, das Frontend (`openAssignModal()`) filtert die Zielauswahl
     bereits clientseitig entsprechend vor.
  Siehe Abschnitt 5 (Unterabschnitt "Warteschlange je Drucker") fuer die
  Einordnung dieser Erweiterungen in den Gesamtkontext des Feature.
- **v2.1.1 (MK6): Bugfix.** Nach einem fehlgeschlagenen Druck (Bambu-Status
  `FAILED`) liess sich der naechste Warteschlangen-Auftrag NICHT mehr
  ueber "Druckraum leer" starten - `BAMBU_READY_FOR_NEXT_STATES` enthielt
  bisher nur `FINISH`/`IDLE` (siehe v2.0.1-Eintrag oben), `FAILED` fehlte.
  Der Drucker verharrt nach einem Fehlschlag dauerhaft in diesem Status
  (anders als die dort beschriebenen, tatsaechlich VORUEBERGEHENDEN
  Uebergangszustaende wie `PREPARE`/`SLICING`), die Warteschlange war also
  bis zu einem manuell ausserhalb der Warteschlange gestarteten Druck
  komplett blockiert. Fix: `FAILED` zu `BAMBU_READY_FOR_NEXT_STATES`
  hinzugefuegt (Backend, `DashboardApp.is_ready_for_next_print()`) UND zur
  identisch dupliziert gefuehrten Zustandsliste im Frontend
  (`updateQueueSendButtonState()`, vorher hart codiert `['FINISH','IDLE']`)
  - beide Stellen muessen synchron gehalten werden, da das Frontend den
  Knopf-Zustand rein optisch vorab spiegelt, die tatsaechliche Pruefung
  aber weiterhin serverseitig erfolgt. Fehlermeldungstext bei blockiertem
  Klick ebenfalls angepasst ("... FINISH, IDLE oder FAILED sein ...").
  Getestet: `is_ready_for_next_print()`/`is_printer_busy()` fuer alle
  relevanten Zustaende (`FINISH`, `IDLE`, `FAILED`, `RUNNING`, `PREPARE`,
  `PAUSE`) einzeln durchgespielt - `FAILED` liefert jetzt `ready=True`,
  `PREPARE` weiterhin `ready=False` (kein versehentliches Aufweichen der
  v2.0.1-Uebergangszustands-Sperre); `start_next_queued_print()` bei
  Status `FAILED` durchlaeuft die Bereitschaftspruefung jetzt bis zum
  eigentlichen Druckversand, statt vorher mit der Blockiermeldung
  abzubrechen; identische JS-Logik der Frontend-Kopie isoliert mit
  Node.js nachgebildet und bestaetigt.

- **v2.2.0 (MK6):** Drei additive Features plus eine Diagnose-Erweiterung
  fuer ein noch ungeklaertes Problem:
  1. **Temperatur-Verlaufsdiagramme (Sparklines):** neue gemeinsame
     Frontend-Funktion `tempChip(printerId, field, label, value)` ersetzt
     die bisher in jeder Karten-Renderfunktion (Bambu/OctoPrint/Creality/
     Ultimaker) duplizierten `<div class="temp-chip">`-Templates. Erfasst
     bei jedem Aufruf den aktuellen Wert in `tempHistory` (reines
     Browser-Gedaechtnis, `TEMP_HISTORY_MAX_POINTS = 40` bei 2,5s-Poll-
     Takt entspricht ca. 100 Sekunden) und rendert zusaetzlich eine kleine
     Inline-SVG-Sparkline (`sparklineSvg()`, min/max-skaliert, keine
     externe Chart-Bibliothek noetig - Projekt bleibt eine einzelne
     Datei/PyInstaller-onefile-tauglich). Keine serverseitige Persistenz,
     geht beim Neuladen der Seite bewusst verloren.
  2. **Keine Kammertemperatur-Anzeige bei der A1-Familie:** die Bambu-
     Karte blendet den Kammer-Chip jetzt komplett aus, wenn
     `p.bambu_family === 'a1'` (A1-Serie hat keinen Kammersensor) - vorher
     wurde unabhaengig von der Familie immer ein Chip gerendert, der bei
     fehlendem Sensor dauerhaft `-°C` zeigte.
  3. **Druckbild neben dem Fortschrittsbalken:** `DashboardApp.
     all_status()` liefert je Drucker zusaetzlich `current_thumb_job_id`/
     `current_thumb_has_image`, ermittelt aus dem NEUESTEN Verlaufseintrag
     dieses Druckers (`PrintHistoryStore.list_entries()[0]`, kein neuer
     Speicherort/keine neue Drucker-Anfrage noetig). Frontend-Funktion
     `progressThumb(p)` rendert daraus ein `<img>` (ueber die bereits
     bestehende Verlaufs-Thumbnail-Route), eingefuegt in JEDEN
     `progress-row`-Block (Bambu/OctoPrint/Creality/Ultimaker/Formlabs) -
     bei Druckertypen ohne Dashboard-Versand (OctoPrint/Creality/
     Formlabs) bleibt der Verlauf leer, das Bild erscheint dort also gar
     nicht erst (kein Sonderfall im Markup noetig).
  4. **Diagnose-Erweiterung fuer "X1-Kammertemperatur zeigt weiterhin
     -°C" (Nutzer-gemeldet, NICHT abschliessend geloest):**
     `_apply_print_report()` akzeptiert jetzt defensiv zusaetzlich zum
     bekannten (getippten) Feldnamen `chamber_temper` auch den Feldnamen
     OHNE Tippfehler (`chamber_temp`), falls dieser stattdessen im Report
     vorkommt - rein additiver Fallback, kein bestehendes Verhalten
     geaendert. Liefert WEDER das eine NOCH das andere Feld einen Wert,
     obwohl die konfigurierte Druckerfamilie (alles ausser "a1") einen
     Kammersensor haben sollte, wird das EINMALIG pro Verbindung auf der
     Server-Konsole geloggt, inklusive der tatsaechlich im Report
     vorhandenen Schluessel (`sorted(p.keys())`) - bewusst KEINE weitere
     Vermutung ueber den echten Feldnamen ohne reale Rohdaten (siehe
     Lessons Learned Punkt 1 "keine Endpunkte/Felder raten"). Der Nutzer
     wurde gebeten, eine echte `.gcode.3mf`/den Konsolen-Log-Ausschnitt
     bereitzustellen, sobald das Problem weiter eingegrenzt ist.
  Getestet: `_apply_print_report()` fuer drei Faelle durchgespielt (kein
  Kammerfeld bei X1 -> Log-Ausgabe + `chamber_temp=None`; kein Kammerfeld
  bei A1 -> KEIN Log, da A1 laut Konfiguration ohnehin keinen Sensor haben
  sollte; Fallback-Feldname `chamber_temp` vorhanden -> uebernommen);
  `all_status()` end-to-end mit einer echten (synthetisch gebauten)
  `.gcode.3mf`-Datei inkl. eingebettetem Vorschaubild durch
  `PrintHistoryStore.add_entry()` geschickt und bestaetigt, dass
  `current_thumb_job_id`/`current_thumb_has_image` korrekt gesetzt werden
  UND die bestehende Thumbnail-Route (`GET /api/printers/<id>/history/
  <job>/thumbnail`) darueber ein gueltiges PNG liefert; `tempChip()`/
  `sparklineSvg()`/`progressThumb()` isoliert mit Node.js getestet
  (Verlaufs-Array-Aufbau, Sparkline-Punktberechnung, leeres Ergebnis bei
  < 2 Punkten bzw. fehlendem Vorschaubild). Zusaetzlich `python3 -m
  py_compile app.py`, `node --check` auf dem vollstaendigen extrahierten
  `<script>`-Block, sowie ein Flask-Test-Client-Check, dass `GET /` alle
  neuen Marker (`tempChip(`, `progressThumb(`, `sparklineSvg(`,
  `bambu_family === 'a1'`, `current_thumb_has_image`) enthaelt.

- **v2.2.1 (MK6):** Zwei Ergaenzungen zu den v2.2.0-Sparklines:
  1. **Sparklines jetzt rot:** `.temp-spark` (SVG-`<polyline stroke=
     "currentColor">`) von `color:var(--text-dim)` auf `color:
     var(--danger)` umgestellt, auf ausdruecklichen Nutzerwunsch. Gilt
     fuer ALLE Sparklines (Temperatur UND die neue Luftfeuchtigkeit
     unten), da beide dieselbe CSS-Klasse verwenden.
  2. **AMS-Luftfeuchtigkeit inkl. Verlaufsdiagramm:** `PrinterConnection.
     _apply_print_report()` liest zusaetzlich zu den Fach-Daten je
     AMS-EINHEIT (nicht je Fach) das Feld `"humidity"` aus dem Bambu-
     MQTT-`ams`-Objekt - ein community-dokumentierter Indexwert 1
     (trocken) bis 5 (feucht), KEIN Prozentwert (u. a. von der Home-
     Assistant-Bambu-Lab-Integration in gleicher Bedeutung genutzt).
     Defensiv geparst (`int(unit["humidity"])` in `try/except`) - fehlt
     das Feld oder ist es nicht numerisch, wird die Einheit einfach ohne
     Feuchte-Angabe gefuehrt statt zu raten. Neues Statusfeld
     `ams_units` (Liste `{id, humidity}` je Einheit, Default `[]` im
     initialen `PrinterConnection.status`). Frontend: neue Funktion
     `humidityChip()` nutzt bewusst dieselbe `tempHistory`/
     `sparklineSvg()`-Infrastruktur wie `tempChip()` (generischer
     Werteverlauf, nicht auf Temperaturen beschraenkt) - `renderAms()`
     bekam dafuer zwei neue Parameter (`printerId`, `amsUnits`), Aufrufer
     entsprechend angepasst (`renderAms(p.id, p.ams, p.ams_units)`).
     Nur Einheiten mit tatsaechlich vorhandenem (nicht-`null`) Wert
     werden angezeigt.
  Getestet: `_apply_print_report()` mit zwei AMS-Einheiten durchgespielt
  (gueltiger String-Wert `"3"` -> `int` 3 uebernommen; ungueltiger Wert
  `"not-a-number"` -> `None`, kein Absturz); `all_status()` gibt
  `ams_units` korrekt weiter; `renderAms()` isoliert mit Node.js
  getestet (zeigt nur die Einheit mit gueltigem Wert, filtert `null`
  korrekt heraus; leere AMS-Liste weiterhin `"Kein AMS erkannt"`).
  Zusaetzlich `python3 -m py_compile app.py`, `node --check` auf dem
  vollstaendigen extrahierten `<script>`-Block, sowie ein
  Flask-Test-Client-Check, dass `GET /` die neuen Marker
  (`humidityChip(`, `ams_units`, `color:var(--danger)`,
  `renderAms(p.id, p.ams, p.ams_units)`) enthaelt.

- **v2.2.2 (MK6):** Zwei Ergaenzungen zur v2.2.1-Luftfeuchtigkeit:
  1. **Sparkline der AMS-Luftfeuchtigkeit jetzt blau:** `sparklineSvg()`
     bekam einen zweiten, optionalen Parameter `cssClass` (Default
     `'temp-spark'`, weiterhin rot fuer Temperaturen) - `humidityChip()`
     uebergibt jetzt explizit die neue Klasse `'humidity-spark'`
     (`color:var(--info)`, neue blaue CSS-Variable). Rein additive
     Signatur-Erweiterung, `tempChip()` (ruft `sparklineSvg()` weiterhin
     ohne zweites Argument auf) unveraendert.
  2. **1-5-Massstab neben dem Feuchte-Rohwert:** neue Funktion
     `humidityScale(value)` rendert fuenf kleine Punkte, gefuellt bis
     einschliesslich der aktuellen Stufe (Tooltip nennt zusaetzlich die
     Bedeutung in Worten: "1 = trocken, 5 = feucht") - platziert
     zwischen dem Zahlenwert und der Sparkline in `humidityChip()`, damit
     die reine Zahl (1-5) ohne Nachschlagen im README eingeordnet werden
     kann.
  Getestet: `sparklineSvg()` mit und ohne `cssClass`-Argument isoliert
  mit Node.js getestet (liefert die jeweils erwartete CSS-Klasse);
  `humidityScale()` fuer alle Stufen 1-5 sowie `undefined`/`null`
  durchgespielt (korrekte Anzahl gefuellter Punkte, leerer String bei
  fehlendem Wert); `humidityChip()` end-to-end bestaetigt Zahlenwert +
  Massstab + blaue Sparkline in korrekter Reihenfolge. Zusaetzlich
  `python3 -m py_compile app.py`, `node --check` auf dem vollstaendigen
  extrahierten `<script>`-Block, sowie ein Flask-Test-Client-Check, dass
  `GET /` die neuen Marker (`humidityScale(`, `humidity-spark`,
  `--info:`, `.humidity-dot`) enthaelt.

- **v2.2.3 (MK6):** Nutzer-Feedback zur v2.2.2-Luftfeuchtigkeits-Anzeige:
  der reine Zahlenwert ("4") war ohne Hover auf den Massstab nicht als
  "eher schlecht" erkennbar. Fix (rein additiv, kein bestehendes
  Verhalten geaendert):
  - Neue Konstante `HUMIDITY_LEVELS` (1-5 -> `{label, severity}`,
    `severity` ∈ `good`/`mid`/`bad`) ordnet jeder Stufe ein Wort
    ("trocken", "leicht feucht", "mittel", "feucht", "sehr feucht") UND
    eine Ampelfarbe zu.
  - Neue Funktion `humidityLabel(value)` rendert das Wort-Label direkt
    neben dem Zahlenwert (in `humidityChip()` zwischen `<b>Wert</b>` und
    dem Massstab eingefuegt).
  - `humidityScale()` faerbt die gefuellten Punkte jetzt in derselben
    Ampelfarbe statt einheitlich blau (CSS `.humidity-dot.filled.good/
    .mid/.bad`) - die Sparkline-Linie selbst (`.humidity-spark`) bleibt
    bewusst blau, wie in v2.2.2 explizit gewuenscht; nur der Massstab
    bekommt die zusaetzliche Ampelfarbe.
  Getestet: `humidityLabel()`/`humidityScale()` fuer alle Stufen 1-5
  sowie `undefined` isoliert mit Node.js durchgespielt (korrektes
  Label/korrekte Severity-Klasse je Stufe, leerer String bei fehlendem
  Wert); `humidityChip()` end-to-end bestaetigt Reihenfolge Zahl -> Wort-
  Label -> Massstab -> blaue Sparkline. Zusaetzlich `python3 -m
  py_compile app.py`, `node --check` auf dem vollstaendigen extrahierten
  `<script>`-Block, sowie ein Flask-Test-Client-Check, dass `GET /` die
  neuen Marker (`humidityLabel(`, `HUMIDITY_LEVELS`, `.humidity-label`)
  enthaelt.

- **v2.2.4 (MK6):** UI-Bugfix/Verbesserung fuer Verlaufs- und
  Warteschlangen-Fenster: bei vielen Eintraegen scrollte bisher das
  GESAMTE Modal (`.modal{overflow-y:auto}` galt fuer Kopf, Werkzeuge/
  Drop-Zone, Liste UND die Aktions-Knoepfe am Ende gemeinsam) - "Schliessen"
  bzw. "Druckraum leer - naechsten senden" waren am Fuss einer langen
  Liste erst nach vollstaendigem Durchscrollen erreichbar (Nutzer-
  gemeldet: "sonst werden lange Druckverlaeufe unpraktisch").
  - HTML: `.modal-actions` (jetzt mit zusaetzlicher Klasse
    `modal-actions-top`) steht in beiden Modals jetzt VOR der Liste,
    nicht mehr danach.
  - CSS: `.history-modal` (gemeinsame Basisklasse von `historyModal`/
    `queueModal`) bekam `display:flex; flex-direction:column;
    overflow:hidden` - Kopf/Werkzeuge/Aktionen/Drop-Zone/Hinweistext sind
    `flex-shrink:0` (bleiben also in ihrer natuerlichen Groesse fix),
    NUR die neue Klasse `.history-modal-scroll` (auf `#historyModalBody`/
    `#queueModalBody`) bekommt `overflow-y:auto; min-height:0` - dadurch
    scrollt jetzt AUSSCHLIESSLICH die Liste selbst, waehrend Kopf- und
    Aktionsbereich permanent sichtbar bleiben (kein reines Verschieben
    der Knoepfe wie bei einer einfachen HTML-Reihenfolgeaenderung ohne
    CSS-Anpassung - das haette bei langen Listen weiterhin zum
    Wegscrollen der Knoepfe gefuehrt).
  - `.history-modal-tools` verlor dabei ihren negativen oberen Rand
    (`margin:-8px...` -> `margin:0...`), der nur zum direkten Anschluss
    an die (jetzt weiter oben stehende) Ueberschrift gedacht war und nach
    der Umsortierung zu Ueberlappung mit dem neuen Aktionsbereich gefuehrt
    haette.
  - Nur `.history-modal` betroffen (Basis fuer Verlaufs-/Warteschlangen-
    Fenster) - die generische `.modal`-Klasse (addModal/amsModal/
    assignModal) bleibt unveraendert, da deren Inhalte typischerweise
    nicht lang genug werden, um dasselbe Problem zu haben.
  Getestet: Flask-Test-Client bestaetigt per String-Positionsvergleich im
  gerenderten HTML, dass `modal-actions-top` in BEIDEN Modal-Bloecken vor
  `id="historyModalBody"` bzw. `id="queueModalBody"` steht. Zusaetzlich
  `python3 -m py_compile app.py` und `node --check` auf dem vollstaendigen
  extrahierten `<script>`-Block (HTML-Restrukturierung aendert nichts an
  JS-Funktionen/IDs, alle bestehenden `getElementById()`-Aufrufe bleiben
  gueltig).

- **v2.2.5 (MK6):** Auf ausdruecklichen Nutzerwunsch: Feuchteanzeige bei
  der A1-Familie generell unterdrueckt, wenn ein AMS Lite verbunden ist.
  Hintergrund: die A1-Serie wird mit dem "AMS Lite" betrieben, das -
  anders als das vollwertige AMS der X1-Serie - KEINEN echten
  Feuchtesensor besitzt. Der bisherige Filter in `renderAms()` (nur
  Einheiten mit tatsaechlich vorhandenem `humidity`-Feld anzeigen, siehe
  v2.2.1) reicht dafuer NICHT zwingend aus, falls manche Firmware-Staende
  des AMS Lite dort einen bedeutungslosen Platzhalterwert (z. B. `0`)
  statt gar kein Feld liefern - das waere sonst faelschlich als echte
  "trocken"-Messung anzeigt worden. Fix: `renderAms()` bekam einen
  vierten Parameter `bambuFamily` - ist er `'a1'`, wird die komplette
  Feuchteermittlung uebersprungen (`units = []`), UNABHAENGIG vom
  Rohwert. Aufrufer angepasst: `renderAms(p.id, p.ams, p.ams_units,
  p.bambu_family)`. Analog zur bereits bestehenden Kammertemperatur-
  Ausblendung fuer A1 (v2.2.0).
  Getestet: `renderAms()` isoliert mit Node.js fuer zwei Faelle
  durchgespielt - identische AMS-Einheit mit Platzhalterwert
  `humidity:0`, einmal mit `bambuFamily:'a1'` (keine Feuchteanzeige im
  Ergebnis-HTML) und einmal mit `bambuFamily:'x1'` (Feuchteanzeige wie
  gewohnt vorhanden) - bestaetigt den Unterschied. Zusaetzlich `python3
  -m py_compile app.py`, `node --check` auf dem vollstaendigen
  extrahierten `<script>`-Block, sowie ein Flask-Test-Client-Check, dass
  `GET /` die neuen Marker (`renderAms(p.id, p.ams, p.ams_units,
  p.bambu_family)`, `isA1`, `bambuFamily`) enthaelt.

- **v2.2.6 (MK6):** Nutzer-gemeldet: Upload auf H2S scheitert in allen 3
  Versuchen mit `553 Could not create file` (bei 0 Bytes). Analyse: 553
  ist eine inhaltliche Ablehnung des STOR-Kommandos durch den FTP-Server
  des Druckers - TLS-Handshake und Login haben also funktioniert, das ist
  KEIN Netzwerk-/PASV-/TLS-Profil-Problem (die bisherige Fehlermeldung
  verwies faelschlich auf PASV/Firewall). Recherche: bei H2-Serie (und
  P2S) erreicht FTPS ausschliesslich den USB-Stick, nicht den internen
  eMMC-Speicher (synman/bambu-printer-manager Issue #64: "FTPS reaches
  the USB stick and nothing else"; Bambu Studio nutzt fuer den internen
  Speicher einen separaten, undokumentierten Tunnel-Mechanismus mit
  `storage:"emmc"`). Bambu-Wiki "Failed to send print files" nennt
  fehlendes/volles/zu langsames Speichermedium generell als Ursache.
  Fix in `_ftps_upload()`: enthaelt die Fehlermeldung eines Versuchs
  "553", wird SOFORT abgebrochen (keine weiteren, sinnlosen Versuche mit
  anderem TLS-Profil) und eine spezifische Klartext-Meldung ausgegeben
  (USB-Stick bei H2/P2S, microSD bei X1/P1/A1). Alle anderen Fehler
  laufen unveraendert durch die 3 Versuche. Bewusst NICHT umgesetzt:
  Upload in den internen Speicher (undokumentierter Tunnel, siehe
  Lessons Learned Punkt 1). Offen/unverifiziert: ob der MQTT-Druckbefehl
  (`"url": "file:///sdcard/<datei>"`) bei der H2-Serie mit USB-Stick
  unveraendert funktioniert - falls der Upload nach Einstecken des Sticks
  klappt, der Druck aber nicht startet, ist das der naechste Pruefpunkt.
  Getestet: `_ftps_upload()` mit gemocktem `_ftps_upload_once()` - bei
  553 genau 1 Versuch + neue Meldung; bei anderem Fehler ("timed out")
  weiterhin 3 Versuche (x1/a1/x1) + bisherige Meldung. `py_compile`.
- **v2.2.7 (MK6):** Zwei Nutzer-Rueckmeldungen zu einem H2S nach dem
  Einstecken eines USB-Sticks (siehe v2.2.6, dort als offene Frage
  markiert): (1) Der Druckstart scheitert jetzt mit dem
  Druckerfehler "Nicht unterstuetzter Pfad oder Name der Druckdatei".
  (2) Die AMS-Feuchte zeigt "1" an, obwohl der Drucker selbst 44%
  ausweist.
  - **Zu (2), geloest:** Recherche (greghesp/ha-bambulab Issue #1235,
    maziggy/bambuddy Issue #3140) ergab: das neuere AMS 2 Pro (H2-Serie)
    liefert im MQTT-Report ZUSAETZLICH zur bisherigen 1-5-Stufe
    (`humidity`) das Feld `humidity_raw` - den tatsaechlichen
    Prozentwert. Aeltere AMS-Einheiten (vier Slots, AMS Lite) liefern
    dieses Feld nicht. Fix: `_apply_print_report()` parst `humidity_raw`
    jetzt zusaetzlich und defensiv (analog zu `humidity`, siehe
    Kommentar dort) in `ams_units`. Frontend (`humidityChip()`): ist ein
    Prozentwert vorhanden, wird er als Hauptanzeige verwendet (z. B.
    "44%") und auch im Verlaufsdiagramm aufgezeichnet; Wort-Label und
    Ampel-Punkte (`humidityLabel()`/`humidityScale()`) bleiben bewusst an
    der vom Hersteller gelieferten Stufe (`humidity`) ausgerichtet, da
    nur diese die vorgesehene gut/mittel/schlecht-Einordnung traegt - ein
    aus dem Prozentwert selbst abgeleiteter Schwellwert waere geraten
    und nicht dokumentiert. `renderAms()`: eine AMS-Einheit wird jetzt
    auch angezeigt, wenn NUR `humidity_raw` vorhanden ist (nicht mehr
    zwingend `humidity`). Getestet: Node-Test mit dem exakten
    Nutzer-Fall (`humidity=1, humidity_raw=44`) -> zeigt "44%" +
    Label/Punkte fuer Stufe 1; Legacy-Fall (nur `humidity=4`, kein
    `humidity_raw`) -> unveraendertes Verhalten wie vor v2.2.7; A1-Familie
    weiterhin komplett unterdrueckt (siehe v2.2.5), auch wenn
    `humidity_raw` vorhanden waere. Backend-Test mit
    `PrinterConnection._apply_print_report()`: korrektes Parsing fuer
    AMS-2-Pro-Fall, Legacy-Fall und defensiv fuer nicht-numerisches
    `humidity_raw`. `py_compile`, `node --check`.
  - **Zu (1), bewusst NICHT geraten geloest:** Recherche (u. a.
    [BambuStudio Issue #8091](https://github.com/bambulab/BambuStudio/issues/8091)
    "Unable to send file to Local Storage on H2S with properly formatted
    USB drive", ha-bambulab Issues #1512/#1520/#1521, Forum-Thread
    "Inconsistent MQTT paths compared with FTP access") zeigt: das exakte
    Pfad-/URL-Format, das die H2-Serie/P2S bei USB-Speicher (statt
    internem Speicher) fuer den MQTT-Druckstart-Befehl (`project_file`)
    erwartet, ist selbst in den aktivsten Community-Projekten noch offen
    - Issue #8091 zeigt, dass selbst Bambu Studio dieses Szenario (Stand
    dieser Recherche) nicht zuverlaessig beherrscht. `_request_print()`
    sendet unveraendert `"url": "file:///sdcard/{remote_name}"` (siehe
    OpenBambuAPI/mqtt.md: dieser Pfad wird dort explizit als generischer
    "root path" dokumentiert, unabhaengig vom physischen Speichermedium -
    fuer X1/P1/A1 mit microSD ist er nachweislich seit MK5 im produktiven
    Einsatz). Ein spekulatives Aendern dieses Pfads speziell fuer H2/P2S
    ohne dokumentierte Grundlage wuerde gegen die Projekt-Konvention
    verstossen, keine undokumentierten Protokolldetails zu erfinden -
    zumal ein falscher Pfad das bestehende, funktionierende Verhalten bei
    X1/P1/A1 gefaehrden koennte, wenn er printer-family-abhaengig
    umgestellt wuerde, ohne dass fuer H2/P2S ueberhaupt ein bestaetigt
    richtiger Ersatzwert bekannt ist. Stattdessen: `_request_print()`
    protokolliert jetzt bei jedem Druckstart die exakt gesendete
    `url`/`param`/`subtask_name` in der Konsole (`[MK6] Druckstart
    angefordert: ...`), damit bei einem erneuten Fehlschlag echte
    Beweisdaten statt Vermutungen vorliegen. In README Abschnitt 4 als
    bekannte offene Einschraenkung dokumentiert, inkl. Interims-Workaround
    (Druckstart direkt am Drucker ueber "Vom USB-Stick drucken", da dort
    nicht der MQTT-Weg verwendet wird). Getestet:
    `_request_print()` mit gemocktem MQTT-Client - Log-Zeile erscheint
    mit korrekten Werten, `publish()` wird wie zuvor aufgerufen, keine
    Verhaltensaenderung ausser der zusaetzlichen Log-Zeile.
- **v2.2.8 (MK6):** Nutzer-gemeldet, beim Versuch die v2.2.7-
  Diagnosezeile fuer das offene H2S-Druckstart-Problem einzusehen: die
  `[MK6] Druckstart angefordert: ...`-Zeile taucht im OpenWrt-Systemlog
  (`logread -f | grep -i mk6`) auf einem per `procd`-Autostart-Skript
  (siehe MK5-Chat "Dashboard auf GL.inet Brume 2 installieren") laufenden
  Router gar nicht auf, obwohl Flasks eigene Zugriffs-Logzeilen (`GET
  /api/status` usw.) zuverlaessig ankommen. Root Cause (kein
  Community-Protokoll, sondern dokumentiertes CPython-Verhalten): schreibt
  ein Python-Programm auf eine Standardausgabe, die kein Terminal ist
  (z. B. weil `procd` sie in eine Pipe/den Log-Daemon umleitet), puffert
  `sys.stdout` per Default BLOCKWEISE statt zeilenweise
  (`sys.stdout.line_buffering` ist in diesem Fall `False`) - `print()`-
  Aufrufe koennen dadurch beliebig lange im Puffer haengen bleiben, bevor
  sie tatsaechlich geschrieben werden. Flasks Zugriffs-Log laeuft ueber
  das `logging`-Modul auf `sys.stderr` und war davon nicht betroffen,
  daher der Unterschied. Fix: direkt nach den Imports werden
  `sys.stdout`/`sys.stderr` jetzt explizit per
  `reconfigure(line_buffering=True)` (Python 3.7+) auf zeilenweise
  Pufferung umgestellt, mit `try/except (AttributeError, ValueError)` als
  Fallback fuer Umgebungen ohne `TextIOWrapper`-stdout. Betrifft ALLE
  bestehenden und kuenftigen `print()`-Diagnosezeilen im Programm, nicht
  nur die aus v2.2.7 - reine Verhaltensaenderung bei WANN geschrieben
  wird, nicht WAS. Getestet: (a) `sys.stdout.line_buffering` in einem
  frischen Python-Prozess mit `stdout` als Pipe (kein Terminal) ist ohne
  den Fix nachweislich `False`; (b) Subprozess-Test, der `app.py`
  importiert (loest `reconfigure()` aus) und danach in eine Pipe
  schreibt: Testzeile kommt in <1s beim lesenden Ende an (vorher
  potenziell erst beim Prozessende/Pufferueberlauf). `py_compile`.
- **v2.2.9 (MK6):** Mit dem Buffering-Fix aus v2.2.8 konnte der Nutzer
  die v2.2.7-Diagnosezeile endlich einsehen:
  `url='file:///sdcard/test_druckbereit20.gcode.3mf' param='Metadata/
  plate_1.gcode' subtask_name='test_druckbereit20'` fuer einen H2S. Damit
  ist bestaetigt, dass der Dashboard-Code weiterhin unveraendert den seit
  MK5 produktiv genutzten Pfad sendet - die naechste offene Frage ist,
  WOHIN der vorangehende FTPS-Upload (`STOR test_druckbereit20....`)
  auf einem H2S tatsaechlich schreibt, da `file:///sdcard/<name>` nur
  dann stimmen kann, wenn die Datei auch dort landet. Weitere Recherche
  (greghesp/ha-bambulab Issue #2148, "H2C: print_weight never updates")
  ergab einen konkreten Hinweis: bei der H2-Serie ist externer Speicher
  (SD/USB) per FTPS zwar erreichbar, dort wird aber offenbar ein
  `/cache/`-Unterordner verwendet (unabhaengig vom hier zusaetzlich
  bestehenden, unabhaengigen eMMC-Cache-Mechanismus fuer
  MakerWorld-Downloads, der NICHT gemeint ist) - ob unser eigener
  `STOR <name>`-Upload (ohne Pfadangabe, landet im FTP-Login-
  Arbeitsverzeichnis) dort automatisch hineinschreibt oder woanders, ist
  aber weiterhin NICHT bestaetigt (Community-Quellen widersprechen sich
  nicht, sind aber unvollstaendig). Statt das zu erraten: `_ftps_upload_once()`
  (sowohl in `ftps_upload_helper.py`, der primaer verwendeten
  Implementierung, als auch im Selbstaufruf-Fallback `_run_ftps_upload_worker()`
  in `app.py`) listet jetzt per `ftp.nlst()` das FTPS-Arbeitsverzeichnis
  DIREKT NACH dem Login und VOR dem eigentlichen `STOR`-Befehl, als neuer
  JSON-Nachrichtentyp `{"type": "diag", "message": "..."}` auf stdout.
  `_ftps_upload_once()` in `app.py` (liest die stdout-Zeilen des
  Subprozesses zeilenweise) gibt diese Zeile als
  `[MK6] FTPS-Diagnose (Drucker='...', Profil=...): ...` aus - dank
  v2.2.8 jetzt auch zuverlaessig in `logread` sichtbar. Bewusst als
  eigenstaendiger `try/except`: ein fehlschlagendes `NLST` (manche FTP-
  Server unterstuetzen es nicht) darf den eigentlichen Upload nicht
  verhindern oder verzoegern - im Fehlerfall wird stattdessen eine
  Diagnosezeile mit der Fehlermeldung selbst ausgegeben. Sobald der
  Nutzer diese Zeile fuer einen H2S liefert, zeigt sie exakt, ob dort
  bereits eine "cache"-Struktur besteht und wie sich der von uns
  gesendete Dateiname darin einordnet - das ist die fehlende
  Information, um den Pfad im naechsten Schritt entweder zu bestaetigen
  oder gezielt (nicht spekulativ) zu korrigieren. Getestet: Node/Python-
  Test mit gefaketem Helfer-Subprozess, der eine `diag`-Zeile ausgibt -
  `_ftps_upload_once()` gibt sie korrekt als `[MK6] FTPS-Diagnose ...`
  aus, der Upload selbst (Progress/Done) laeuft unveraendert durch.
  `py_compile` fuer `app.py` UND `ftps_upload_helper.py`, Flask-Smoke-Test.
- **v2.2.10 (MK6):** Der Nutzer lieferte die v2.2.9-Diagnosezeile fuer
  einen H2S: `['test_druckbereit20.gcode.3mf', 'timelapse']` - die Datei
  liegt DIREKT im FTP-Wurzelverzeichnis, KEIN `/cache/`-Unterordner. Die
  in v2.2.9 aufgestellte Cache-Vermutung ist damit widerlegt (echte
  Daten statt Annahme - genau der Zweck der Diagnose-Zeile). Der bisher
  gesendete Pfad `file:///sdcard/test_druckbereit20.gcode.3mf` zeigt also
  exakt dorthin, wo die Datei tatsaechlich liegt, und der Drucker lehnt
  ihn trotzdem ab - der Fehler liegt folglich nicht am Verzeichnis,
  sondern hoechstwahrscheinlich am Alias-Namen "sdcard" selbst, den die
  H2-Serie (kein physischer SD-Kartenslot, anders als X1/P1/A1) mutmasslich
  nicht kennt. Weitere, gezielte Recherche (nicht mehr allgemein "H2 MQTT
  Pfad", sondern konkret: "wie konstruiert eine aktiv gepflegte
  Referenzbibliothek das url-Feld") foerderte einen konkreten Fund
  zutage: `bambulabs_api` (BambuTools/bambulabs_api,
  `mqtt_client.py`/`start_print_3mf()`) verwendet fuer ALLE
  Bambu-Modelle einheitlich `"url": f"ftp:///{filename}"` - KEINEN
  storage-spezifischen Alias, KEINE Modell-Fallunterscheidung. Diese
  Bibliothek ist in diesem Projekt bereits seit v1.5.6 als
  vertrauenswuerdige Quelle etabliert (dort fuer `bed_type`/`flow_cali`
  u. a. Felder desselben `project_file`-Befehls verwendet). `"ftp:///"`
  (kein Host, kein Alias, nur der Dateiname) passt exakt zu unserem
  Datei-Layout (STOR laedt die Datei flach ins FTP-Wurzelverzeichnis,
  ohne Unterordner).
  Fix in `_request_print()`: fuer `bambu_family in ("h2", "p2")` wird
  jetzt `f"ftp:///{remote_name}"` statt `f"file:///sdcard/{remote_name}"`
  gesendet. P2S bewusst mitgenommen (nicht nur H2), da laut Bambu selbst
  "combines the P1-Series with next-generation technologies from the
  H2D/H2S" - dieselbe Speicher-Architektur-Verwandtschaft, die bereits
  in `BAMBU_FAMILY_TO_FTPS_PROFILE` (v1.6.7) fuer die FTPS-Profilwahl
  zugrunde liegt. X1/A1/P1/X2 bleiben UNVERAENDERT bei
  `file:///sdcard/<datei>`, um das dort seit MK5 bestaetigt
  funktionierende Verhalten nicht zu gefaehrden - eine pauschale
  Umstellung fuer ALLE Familien (wie bambulabs_api es selbst tut) waere
  zwar durch die Referenzbibliothek gedeckt, aber ein zusaetzliches,
  unnoetiges Risiko fuer bereits funktionierende Drucker, das durch
  nichts in dieser Aenderung gerechtfertigt ist.
  **Ausdruecklich nicht bestaetigt:** ob `ftp:///<datei>` den
  Druckstart bei H2/P2S tatsaechlich zum Laufen bringt - das ist eine
  begruendete, quellenbasierte Korrektur, kein verifizierter Fix (dafuer
  fehlt echte H2/P2S-Hardware). In README als experimentell markiert,
  Rueckmeldung des Nutzers nach dem naechsten Testdruck ausstehend.
  Getestet: `_request_print()` mit gemocktem MQTT-Client fuer alle 6
  Familien (x1/a1/p1/x2 unveraendert `file:///sdcard/...`, h2/p2 neu
  `ftp:///...`) - alle Assertions bestanden. `py_compile`,
  Flask-Smoke-Test.
- **v2.2.11 (MK6, reine Dokumentations-Aktualisierung):** Nutzer
  bestaetigte auf echter H2S-Hardware: **der Druckstart funktioniert
  jetzt** mit dem in v2.2.10 eingefuehrten `ftp:///<datei>`-Pfad fuer
  H2/P2S. Damit ist die komplette, in v2.2.6 begonnene Fehlerkette
  (553-Upload-Fehler ohne USB-Stick -> Buffering-Problem bei
  procd-Autostart -> FTPS-Cache-Vermutung widerlegt -> "sdcard"-Alias als
  eigentliche Ursache -> `ftp:///`-Fix) end-to-end verifiziert - kein
  offener Punkt mehr zu diesem Themenkomplex. README Abschnitt 4 von
  "experimentell, unbestaetigt" auf "vom Nutzer auf echtem H2S bestaetigt
  funktionsfaehig" aktualisiert. Keine Code-Aenderung in diesem Schritt -
  `APP_VERSION` dennoch erhoeht (siehe Regel unten: jede ausgelieferte
  Aenderung, auch reine Dokumentation, bekommt eine neue Version), damit
  der ausgelieferte Zip-Stand mit dem Doku-Stand synchron bleibt.
- **v2.2.12 (MK6):** Nutzer meldete drei Fragen/Beobachtungen: (1) warum
  zeigt jetzt auch der X1 einen Prozentwert fuer die AMS-Feuchte an
  (bisher nur beim H2S beobachtet)? (2) gibt der Drucker beim H2 wirklich
  einen genauen Prozentwert aus? (3) warum wird beim H2 ein Wert von 41%
  als "trocken" angezeigt, beim X1 aber 24% als "feucht" - das wirkt
  widerspruechlich (24% RH ist fuer sich genommen eher trockener als
  41%).
  - **Zu (1):** `humidity_raw` (der Prozentwert) ist eine Eigenschaft des
    AMS-2-Pro-**Zubehoerteils** selbst, nicht des Druckermodells - ein
    AMS 2 Pro kann auch nachtraeglich an einem X1 betrieben werden und
    meldet dann ebenfalls `humidity_raw`, unabhaengig vom Drucker. Die
    Formulierung in v2.2.7 ("beim H2S/H2D") war insofern ungenau/zu eng
    und wurde in README korrigiert.
  - **Zu (2):** Ehrliche Antwort recherchiert statt behauptet: es ist der
    vom AMS-2-Pro-Sensor gemeldete Rohwert, unveraendert durchgereicht.
    Bambu-Forum-Thread "AMS2 Pro humidity consistently measures too low"
    deutet auf eine systematische Tendenz zu niedrig gemessener
    Feuchtewerte bei diesem Sensor hin - das Dashboard nimmt keine
    eigene Kalibrierung/Korrektur vor und kann daher keine Garantie fuer
    Laborgenauigkeit geben. In README als Warnhinweis ergaenzt.
  - **Zu (3), der eigentliche Bug:** `humidityChip()` leitete Wort-Label
    und Punktreihe SEIT v2.2.7 IMMER aus der separaten 1-5-Rohstufe
    ("value"/`humidity`) ab - auch dann, wenn zusaetzlich ein
    Prozentwert ("rawPercent"/`humidity_raw`) vorlag. `levelKnown` prueft
    bisher nur `value !== undefined/null`, nicht aber `!hasRaw`. Beide
    Felder sind aber unterschiedliche Messkanaele, die laut Recherche
    (maziggy/bambuddy Issue #3140, bereits in v2.2.7 als Quelle fuer die
    Existenz von `humidity_raw` zitiert, dort aber nicht vollstaendig
    ausgewertet) NICHT notwendig gleich skaliert sind: die 1-5-Rohstufe
    wird je nach AMS-Generation offenbar in UNTERSCHIEDLICHER Richtung
    gemeldet (Issue #3140 dokumentiert fuer das aeltere Vier-Fach-AMS
    explizit eine Umkehrung: MQTT-Wert 1 = feucht, MQTT-Wert 5 = trocken -
    also GENAU UMGEKEHRT zur bisherigen `HUMIDITY_LEVELS`-Zuordnung in
    diesem Projekt). Welche Richtung ein konkretes AMS-2-Pro-Geraet fuer
    sein EIGENES `humidity`-Feld tatsaechlich verwendet (dieselbe wie das
    alte AMS, die umgekehrte, oder eine dritte), ist nicht zuverlaessig
    bekannt - eine pauschale Umkehr-Korrektur fuer ALLE Faelle waere
    daher selbst wieder eine Vermutung.
    Fix (bewusst der risikoaermste, vollstaendig quellenbasierte Schritt):
    statt die Richtung der 1-5-Stufe zu erraten, wird Wort-Label und
    Punktreihe jetzt NUR NOCH angezeigt, wenn KEIN Prozentwert vorliegt
    (`levelKnown = !hasRaw && ...`). Liegt ein Prozentwert vor, ist er
    die praezisere, direkt interpretierbare Angabe (kein Rate-Massstab
    noetig) - eine zusaetzliche, potenziell falsch gepolte Einordnung
    danaben wuerde nur verwirren, wie der Nutzer hier konkret erlebt hat.
    Die eigentliche Frage "ist die 1-5-Stufe bei AMS 2 Pro umgekehrt
    gepolt wie beim alten AMS?" bleibt fuer den index-only-Fall
    (Geraete OHNE `humidity_raw`, z. B. das klassische Vier-Fach-AMS)
    unveraendert offen und ist NICHT Teil dieses Fixes - dort aendert
    sich nichts, mangels Bestaetigung fuer eine bestimmte Richtung.
    Getestet (Node): H2-Fall (`value=1, raw=41`) und X1-Fall
    (`value=4, raw=24`) zeigen jetzt beide NUR den Prozentwert, kein
    Label/keine Punkte mehr; Legacy-Fall (`value=4`, kein raw) zeigt
    weiterhin unveraendert Label + Punkte. `py_compile`, `node --check`,
    Flask-Smoke-Test.
- **v2.2.13 (MK6):** drei Anliegen in einer Nachricht:
  1. **README gekuerzt/neu strukturiert:** die extensive Versions-fuer-
     Versions-Historie (USB-Stick-Saga, Buffering-Fix, FTPS-Diagnose-
     Fix, Feuchte-Widerspruch-Fix usw.) wurde aus der README entfernt -
     sie steht bereits vollstaendig hier in UEBERGABE.md. Die README
     beschreibt jetzt bewusst nur noch den AKTUELLEN Stand je Abschnitt,
     nicht mehr den Weg dorthin. Anker/Ueberschriften weitgehend
     beibehalten (kleinere Kuerzungen wie "(neu seit MK6 v1.2.0)" ->
     entfernt), damit externe Links auf Abschnitte nicht brechen.
  2. **GitHub-Actions-Workflow: Release jetzt bei JEDEM Push, nicht nur
     bei Tag-Push.** Bisher war der Schritt "An GitHub Release anhaengen"
     mit `if: startsWith(github.ref, 'refs/tags/v')` an einen manuellen
     `git tag vX.Y.Z && git push origin vX.Y.Z` gekoppelt - ohne diesen
     manuellen Schritt gab es nur Build-Artifacts unter "Actions", aber
     kein sichtbares Release. Geaendert: die Bedingung wurde entfernt,
     der Schritt laeuft jetzt bei jedem Lauf des Workflows (Push auf
     main, Tag-Push, `workflow_dispatch`). `tag_name` wird jetzt
     EXPLIZIT auf `v${{ steps.version.outputs.version }}` gesetzt (statt
     sich wie bisher implizit auf einen tag-foermigen `github.ref` zu
     verlassen, der bei einem normalen Branch-Push gar nicht existiert)
     und `target_commitish: ${{ github.sha }}` ergaenzt, damit GitHub bei
     Bedarf automatisch einen Tag am gebauten Commit anlegt. Ergebnis:
     jeder Push mit erhoehter `APP_VERSION` erzeugt automatisch ein neues
     GitHub Release mit beiden Zips; ein Push ohne Versionserhoehung
     aktualisiert lediglich die Assets des bestehenden Release mit
     demselben Tag (kein Fehler, kein Duplikat). Ein manueller Tag-Push
     auf einen aelteren Commit bleibt weiterhin moeglich. Workflow-Kommentar
     und README Abschnitt 0/0a entsprechend aktualisiert.
  3. **Kammertemperatur X1C/H2S - neuer Feld-Versuch (Nutzer-Vorschlag,
     NOCH NICHT extern bestaetigt):** Nutzer vermutet, das MQTT-Feld
     `print.device.ctc.info.temp` enthalte die Kammertemperatur bei X1C
     und H2S ("ctc" vermutlich "Chamber Temperature Control"). Diese
     Quelle ist NICHT unabhaengig verifiziert (keine offizielle Bambu-
     Dokumentation, kein externer Community-Beleg gefunden) - daher rein
     additiv als DRITTER Fallback nach den bestehenden `chamber_temper`/
     `chamber_temp`-Feldern eingebaut (`PrinterConnection._apply_print_report()`),
     nicht als Ersatz. Struktur von `info` ist nicht gesichert bekannt
     (koennte laut MQTT-Konventionen anderer Felder ein Objekt oder eine
     Liste sein) - daher werden defensiv BEIDE Formen probiert. Wird ein
     Wert gefunden, wird das einmalig pro Verbindung mit dem Wert auf der
     Konsole geloggt (`[MK6] Kammertemperatur ueber 'device.ctc.info.temp'
     gefunden: ... - bitte pruefen ...`), damit der Nutzer den Wert aktiv
     gegen die tatsaechliche Kammertemperatur am Drucker verifizieren
     kann, BEVOR das als geloest gilt - kein stillschweigendes Uebernehmen
     ungeprueften Nutzer-Inputs als Tatsache, konsistent mit der
     "keine Vermutungen zu undokumentierten Protokollen ohne Beleg"-
     Konvention dieses Projekts. Liefert ein Drucker gar keines der drei
     Felder, bleibt der bestehende "Hinweis: liefert kein Feld ..."-Log
     (jetzt alle drei Feldnamen nennend) unveraendert bestehen.
     Getestet (Python, 5 Faelle): `info` als Dict, `info` als Liste,
     Vorrang der bestehenden Felder vor `ctc.info.temp` (keine Aenderung
     wenn `chamber_temper` bereits vorhanden), kein Treffer (keiner der
     drei Felder vorhanden), leeres `device`-Dict (kein Crash) - alle
     bestanden. `py_compile`, Flask-Smoke-Test. README Abschnitt 3k/6
     entsprechend ergaenzt, als unbestaetigt gekennzeichnet.
- **v2.2.14 (MK6):** drei Anliegen:
  1. **Kammertemperatur `device.ctc.info.temp` bestaetigt:** Nutzer
     verglich den in v2.2.13 angezeigten Wert mit der Anzeige in Bambu
     Studio - stimmt ueberein. Der in v2.2.13 als "noch nicht extern
     bestaetigt" markierte Fallback gilt damit als GELOEST fuer X1C und
     H2S. Der einmalige Diagnose-Log-Hinweis in
     `PrinterConnection._apply_print_report()` bleibt trotzdem bewusst
     bestehen (schadet nicht und hilft, falls sich bei einem anderen
     Druckermodell/einer anderen Firmware-Version doch ein abweichender
     Wert zeigt) - nur die README-Formulierung wurde von "unbestaetigt"
     auf "bestaetigt" geaendert (Abschnitt 3k/6).
  2. **README erheblich weiter gekuerzt:** nach der Kuerzung in v2.2.13
     empfand der Nutzer die README weiterhin als "voellig ueberladen".
     Zweite, deutlich aggressivere Kuerzungsrunde: lange Fliesstext-
     Erklaerungen zu Detailverhalten (z. B. AMS-Farbabgleich-Details,
     ausfuehrliche Warnkaesten) auf das Wesentliche eingedampft, mehrere
     Abschnitte zu kompakten Tabellen/Stichpunktlisten verdichtet, nur
     noch die fuer die Einrichtung/den Betrieb tatsaechlich noetigen
     Fakten behalten. Alles Entfernte war bereits (oder ist weiterhin)
     vollstaendig in dieser Datei (UEBERGABE.md) dokumentiert - nichts
     ist verloren gegangen, nur nicht mehr in der Nutzer-README
     dupliziert.
  3. **Geschaetzte Druckzeit in Verlauf und Warteschlange (neues
     Feature):** Nutzer wollte pro Eintrag sehen, wie lange der Druck
     voraussichtlich dauert. Recherchiert statt geraten (siehe
     Printago-Blogartikel zum 3mf-Dateiformat, WebSearch-Beleg in
     diesem Chat): Bambu Studio/OrcaSlicer legen in
     `Metadata/slice_info.config` (derselben Datei, die bereits fuer die
     Filamentzuordnung ausgewertet wird) pro `<plate>` ein
     `<metadata key="prediction" value="...">` ab - dokumentiert als
     geschaetzte Druckzeit in SEKUNDEN. Cura (Ultimaker) schreibt
     unabhaengig von der Gcode-Variante im Kopfbereich der `.gcode`-Datei
     eine Zeile `;TIME:<sekunden>` (zu unterscheiden von den
     zeilenweisen `;TIME_ELAPSED:...`-Fortschrittsmarkierungen im
     restlichen Code).
     - Neue Funktion `_extract_print_duration_seconds()` in `app.py`:
       liest bei `.gcode.3mf` gezielt die Plate mit `index="1"` (dieselbe
       Plate, die tatsaechlich gedruckt wird) und deren
       `prediction`-Wert; bei `.gcode` werden nur die ersten 64 KB nach
       `;TIME:<zahl>` durchsucht (Kopfbereich, kein Vollscan noetig).
       Rein informativ wie schon `_extract_thumbnail()` - liefert `None`
       statt einer Ausnahme, wenn nichts gefunden wird.
     - `PrintHistoryStore.add_entry()` und `PrintQueueStore.add_entry()`
       rufen die neue Funktion auf und speichern das Ergebnis als
       `duration_sec` im jeweiligen Eintrag (`index.json`). Auch
       Eintraege, die aus dem Verlauf in eine Warteschlange gelegt/einem
       anderen Drucker zugewiesen werden (`add_history_entry_to_queue()`,
       `move_queue_entry()`), laufen ueber `queue.add_entry()` und
       bekommen die Dauer dadurch automatisch mit.
     - Frontend: neue Funktion `formatDuration(sec)` formatiert die
       Rohsekunden als kurze "Xh Ymin"-Anzeige (nur Minuten, wenn unter
       einer Stunde); liefert eine leere Zeichenkette bei fehlendem Wert
       (aeltere Eintraege ohne `duration_sec`, oder wenn keine Schaetzung
       extrahiert werden konnte) - der Aufrufer zeigt dann einfach keinen
       Zeit-Hinweis an. In `renderHistoryEntries()` und der
       Warteschlangen-Renderfunktion wird die formatierte Dauer direkt
       neben dem Datum angezeigt ("... &middot; Druckzeit ca. Xh Ymin").
     - Getestet (Python, 6 Faelle): Bambu-Plate-1-Treffer, fehlende
       slice_info.config, Plate-1 ohne `prediction`-Schluessel,
       Ultimaker-`;TIME:`-Treffer, nur `;TIME_ELAPSED:` ohne `;TIME:`
       (muss `None` liefern, keine Verwechslung), unpassende
       Dateiendung - alle bestanden. Getestet (Node, 7 Faelle):
       `formatDuration()` fuer verschiedene Sekundenwerte inkl.
       Rundung, Stunden-Grenzfall, `null`/`undefined` - alle bestanden.
       `py_compile`, `node --check`, Flask-Smoke-Test.
- **v2.2.15 (MK6):** Nutzer meldete, dass die manuelle
  `config.json`-Konfiguration eines MQTT-Sensors "nicht funktioniert"
  hat, und bat darum, das Anlegen von MQTT-Sensoren/-Schaltern komplett
  ueber die Web-Oberflaeche zu ermoeglichen statt per Hand-Editieren.
  Neues Feature, additiv (die bisherige `config.json`-Konfiguration
  bleibt vollstaendig funktionsfaehig und kompatibel - beide Wege
  schreiben/lesen dieselben Felder):
  - **Neue `DashboardApp`-Methoden:** `get_extras_mqtt_settings()`,
    `update_extras_mqtt_settings()`, `get_discovered_mqtt_topics()`,
    `add_extra()`, `update_extra()`, `delete_extra()` (plus die private
    Hilfsmethode `_get_extras_list()` und die statische
    `_validate_extra_fields()`, die Sensor- vs. Schalter-Pflichtfelder
    prueft und beim Bearbeiten die Art (`kind`) bewusst NICHT mehr
    aendern laesst - ein Schalter hat strukturell andere Pflichtfelder
    als ein Sensor, ein Wechsel waere kein sinnvolles "Bearbeiten" mehr).
  - **`update_extras_mqtt_settings()` baut die Broker-Verbindung SOFORT
    neu auf** (alte `ExtrasMqttManager`-Instanz wird gestoppt, eine neue
    mit den frischen Werten erstellt und gestartet) - vorher war dafuer
    ein kompletter Neustart des Dashboards/der exe noetig. Das duerfte
    ein Grund gewesen sein, warum die manuelle `config.json`-Aenderung
    des Nutzers "nicht funktioniert" hat: ohne Neustart blieben die
    alten (oder fehlerhaften) Broker-Einstellungen bis zum naechsten
    Programmstart aktiv, ohne dass das fuer den Nutzer ersichtlich war.
    Ein leer gelassenes Passwort-Feld beim Speichern laesst das
    bestehende Passwort unveraendert (ein explizit leerer String
    loescht es dagegen - siehe Kommentar in `update_extras_mqtt_settings()`).
  - **Neue `ExtrasMqttManager.list_topics()`:** liefert die zuletzt
    empfangenen Topic/Wert-Paare (dank des bereits bestehenden breiten
    `"#"`-Abos in `_on_connect()` ALLE Topics dieses Brokers, nicht nur
    konfigurierte Sensoren), alphabetisch sortiert, auf 300 Eintraege
    begrenzt. Zweck: der zweitwahrscheinlichste Grund fuer "hat nicht
    funktioniert" ist ein falsch abgetipptes Topic - die neue
    Sensor-/Schalter-Verwaltung im Frontend zeigt diese Liste an, damit
    der Nutzer das TATSAECHLICH ankommende Topic per Klick uebernehmen
    kann, statt es blind einzutippen.
  - **Neue Routen:** `GET/POST /api/extras_mqtt` (Broker-Einstellungen
    lesen/speichern), `GET /api/extras_mqtt/discovered` (siehe oben),
    `POST /api/printers/<id>/extras` (neuer Sensor/Schalter),
    `PUT /api/printers/<id>/extras/<extra_id>` (bearbeiten),
    `DELETE /api/printers/<id>/extras/<extra_id>` (loeschen - die
    bestehende `DELETE`-Route fuer den ganzen Drucker sowie die separate
    `POST .../extras/<id>/command`-Route fuer Schalter-Klicks bleiben
    unveraendert, unterschiedliche Pfade/Methoden, kein Konflikt).
  - **Neues Modal "MQTT-Sensoren & Schalter"** im Frontend (Button oben
    im Kopfbereich neben "+ Drucker hinzufuegen"): Broker-Formular,
    Formular fuer neue Sensoren/Schalter (inkl. Drucker-Auswahl aus
    `lastPrinterList`), Liste bestehender Eintraege je Drucker mit
    "Bearbeiten"/"Loeschen", sowie die Liste der zuletzt empfangenen
    Topics zum Uebernehmen per Klick (`useDiscoveredTopic()`). Beim
    Bearbeiten eines bestehenden Eintrags werden Drucker-Auswahl und
    Art (Sensor/Schalter) im Formular gesperrt (`disabled`), da beides
    nachtraeglich nicht aenderbar ist - nur die uebrigen Felder bleiben
    editierbar. `mqttEditState` haelt fest, ob das Formular gerade neu
    anlegt (`null`) oder einen bestehenden Eintrag bearbeitet
    (`{printerId, extraId}` -> `PUT` statt `POST` beim Absenden).
  - Bewusst KEINE HTML-Eskapierung neu eingefuehrt (Label/Topic-Werte
    landen direkt per Template-Literal im `innerHTML`) - konsistent mit
    dem Rest des bestehenden Frontends (`renderExtras()`,
    `renderHistoryEntries()` etc. verfahren genauso), da dieses
    Dashboard bewusst ein einzelner, lokaler, nicht mehrbenutzerfaehiger
    Client ohne Konto/Auth ist (siehe Projektkonzept, Abschnitt 1).
  - Getestet (Python/Flask-Test-Client, 19 Faelle): Drucker anlegen,
    Default-Broker-Einstellungen lesen, Broker-Einstellungen setzen,
    Broker-Einstellungen ohne Passwort aktualisieren (Passwort bleibt
    erhalten), ungueltiger Port, aktiviert ohne Host, Sensor anlegen,
    Schalter anlegen, fehlendes Label, Sensor ohne Topic, Schalter ohne
    Payloads, unbekannter Drucker, Sensor bearbeiten, unbekannten
    Eintrag bearbeiten, Extras ueber `/api/printers` sichtbar, Sensor
    loeschen, doppeltes Loeschen (404), leere Themenliste ohne
    verbundenen Broker, tatsaechliche Persistenz in `config.json`
    (inkl. Bestaetigung, dass das Passwort beim reinen Host-Update
    unveraendert blieb) - alle bestanden. Zusaetzlich
    `ExtrasMqttManager.list_topics()` isoliert getestet (Sortierung +
    `limit`). `py_compile`, `node --check` auf dem extrahierten
    `<script>`-Block, Flask-Smoke-Test.
  - README Abschnitt 2 aktualisiert: der neue Web-UI-Weg steht jetzt an
    erster Stelle, die manuelle `config.json`-Bearbeitung bleibt als
    Alternative dokumentiert.
- **v2.2.16 (MK6):** Nutzer wollte, dass MQTT-Temperatur-/Feuchte-
  Sensoren GENAUSO wie die vom Drucker selbst gelieferten Sensordaten
  ein kleines Verlaufsdiagramm zeigen UND im selben Kartenbereich
  (Temperaturen-Zeile) erscheinen - bisher landeten alle MQTT-Extra-
  Sensoren unabhaengig vom Inhalt im generischen "Sensoren & Schalter"-
  Bereich unten auf der Karte, ohne Sparkline. Additive Erweiterung des
  in v2.2.15 eingefuehrten Sensor-/Schalter-Systems:
  - **Neues Feld `"display"`** an Sensor-Eintraegen (nicht an
    Schaltern - fuer die ist die Unterscheidung sinnlos):
    `"generic"` (Standard, unveraendertes Verhalten - Anzeige im
    bisherigen Bereich unten), `"temperature"` oder `"humidity"`
    (Anzeige stattdessen in der Temperaturen-Zeile). Validierung in
    `_validate_extra_fields()`: ein fehlender/leerer/unbekannter Wert
    faellt defensiv auf `"generic"` zurueck statt einen Fehler zu
    werfen - das haelt VOR v2.2.16 angelegte Eintraege (ganz ohne dieses
    Feld in ihrer gespeicherten `config.json`) unveraendert im
    gewohnten Bereich, ohne Migrationsschritt.
  - **Neue Frontend-Funktion `extraChip(printerId, extra)`:** nutzt
    bewusst dieselbe `recordTempHistory()`/`sparklineSvg()`-
    Infrastruktur wie `tempChip()`/`humidityChip()` (siehe v2.2.0/
    v2.2.1), damit ein MQTT-Sensor sich optisch und funktional nicht
    von einem "echten" Drucker-Sensor unterscheidet. Eigener
    `tempHistory`-Feldschluessel `"extra_<id>"` (kollisionsfrei
    gegenueber den festen Feldern `nozzle`/`bed`/`chamber`/
    `ams_humidity_*`). Der Rohwert vom MQTT-Broker ist ein String -
    wird nur dann als Zahl aufgezeichnet/mit Sparkline angezeigt, wenn
    er sich tatsaechlich in eine gueltige Zahl umwandeln laesst (z. B.
    Home-Assistant-Sensoren melden manchmal `"unavailable"` statt einer
    Zahl) - sonst wird der Rohwert unveraendert als Text angezeigt, ohne
    Sparkline und ohne Aufzeichnung (ein nicht-numerischer Wert wuerde
    die Skalierung der Sparkline sonst zerstoeren). `"humidity"`-Anzeige
    bekommt die blaue `humidity-spark`-Linie, `"temperature"` die rote
    `temp-spark`-Linie - identisch zur bereits bestehenden Farbcodierung.
  - **Neue Funktion `extraTempChips(printerId, extras)`:** filtert aus
    den Extras eines Druckers alle Sensoren mit `display` in
    (`temperature`, `humidity`) heraus und rendert sie als
    zusammenhaengenden Chip-String zum Einfuegen in die bestehende
    `.temps`-Zeile - EINMAL pro Karten-Render aufgerufen (nicht pro
    Chip), damit `recordTempHistory()` nicht versehentlich mehrfach pro
    Refresh-Zyklus denselben Wert aufzeichnet.
  - **Eingebunden in alle Karten-Renderfunktionen** (`renderBambuCard`,
    `renderOctoPrintCard`, `renderCrealityCard`, `renderUltimakerCard`):
    `extraTempChips()` wird direkt in die bestehende `.temps`-Zeile
    neben den Drucker-eigenen `tempChip()`-Aufrufen eingefuegt. Formlabs
    (`renderFormlabsCard`) hat von Haus aus GAR KEINE Temperaturen-Zeile
    - dort wird eine eigene "Temperaturen"-Ueberschrift samt `.temps`-
    Zeile nur dann eingeblendet, wenn tatsaechlich mindestens ein
    passender MQTT-Sensor an diesem Drucker haengt (sonst keine leere
    Ueberschrift ohne Inhalt).
  - **`renderExtras()` (der bisherige generische "Sensoren & Schalter"-
    Bereich) blendet Sensoren mit `display` in (`temperature`,
    `humidity`) jetzt aus** - sonst wuerden sie doppelt erscheinen (einmal
    oben in der Temperaturen-Zeile, einmal unten im generischen
    Bereich). Schalter sind davon nicht betroffen (kein `display`-Feld,
    erscheinen weiterhin ausschliesslich unten).
  - **Modal "MQTT-Sensoren & Schalter" um Auswahlfeld "Anzeigebereich"
    ergaenzt** (nur sichtbar bei Art "Sensor", nicht bei "Schalter") -
    wird beim Anlegen/Bearbeiten mitgesendet/vorausgefuellt
    (`resetMqttExtraForm()`/`startEditMqttExtra()`/`submitMqttExtra()`).
    Die Eintragsliste im selben Modal (`renderMqttExtrasList()`) zeigt
    den gewaehlten Anzeigebereich zusaetzlich in der Unterzeile an
    ("Sensoren-Bereich"/"Temperaturen-Bereich"/"Feuchte-Bereich").
  - Getestet (Node, 7 Faelle, isolierte Function-Scope-Ausfuehrung statt
    `eval()` - vermeidet Redeclaration-Konflikte zwischen mehreren
    Testlaeufen): erste Messung ohne Sparkline (nur 1 Punkt), zweite
    Messung MIT Sparkline und `temp-spark`-Klasse, Feuchte-Sensor mit
    `humidity-spark`-Klasse, nicht-numerischer Wert (Text ohne
    Sparkline, kein Crash), fehlender Wert (Bindestrich-Platzhalter),
    `extraTempChips()`-Filterung (nur temperature/humidity-Sensoren,
    weder generische Sensoren noch Schalter), leere/`null`-Extras-Liste
    - alle bestanden.
    Getestet (Python/Flask-Test-Client, 8 Faelle): Sensor mit
    `display=temperature`, mit `display=humidity`, ohne `display`-Feld
    (Default "generic"), mit ungueltigem `display`-Wert (faellt auf
    "generic" zurueck), Schalter bekommt nie ein `display`-Feld,
    Bearbeiten aendert den Anzeigebereich, `display` erscheint korrekt
    im `/api/printers`-Status, UND explizit ein reiner Ruecktkompatibi-
    litaetstest: ein von Hand ins In-Memory-Config-Objekt eingefuegter
    "Alt-Eintrag" ganz OHNE `display`-Schluessel (simuliert eine vor
    v2.2.16 gespeicherte `config.json`) durchlaeuft `all_status()` ohne
    Fehler - alle bestanden. `py_compile`, `node --check` auf dem
    extrahierten `<script>`-Block, Flask-Smoke-Test.
  - README Abschnitt 2 (MQTT-Sensoren-Anleitung) um den neuen Schritt 4
    "Anzeigebereich waehlen" ergaenzt.

- **v2.2.17 (MK6, reine Dokumentations-Aktualisierung):** Nutzer meldete,
  dass die README noch den Stand "v2.2.14" als aktuelle Version auswies
  (Hinweiszeile direkt unter der Druckertyp-Tabelle), obwohl der
  inhaltliche Text der README (Abschnitt 2 mit der 4-Schritte-MQTT-
  Anleitung inkl. "Anzeigebereich waehlen", Abschnitt 5 mit der
  "Geschaetzte Druckzeit"-Beschreibung) bereits seit v2.2.15/v2.2.16
  korrekt war - lediglich die Versionsnummer in der Kopfzeile war beim
  Ausliefern dieser beiden Versionen nicht mitgezogen worden. Geprueft:
  vollstaendiger Durchlauf der README auf weitere veraltete Versions-
  oder Statusangaben (z. B. Reste der fruehren "noch nicht extern
  bestaetigt"-Formulierung zur Kammertemperatur aus v2.2.13) - keine
  weiteren Fundstellen. UEBERGABE.md selbst war bereits durchgaengig
  aktuell (Versionshistorie bis v2.2.16 vollstaendig), hier war keine
  Aenderung noetig ausser diesem neuen Eintrag. Geaendert wurde
  ausschliesslich die eine Versionsangabe in README.md (v2.2.14 ->
  v2.2.16 zum Zeitpunkt der Korrektur, jetzt mit diesem Eintrag
  konsistent auf v2.2.17 fortgeschrieben) sowie `APP_VERSION` in
  `app.py`. Kein Code-, Verhaltens- oder API-Unterschied zu v2.2.16.
  Getestet: `py_compile app.py`, `node --check` auf dem extrahierten
  `<script>`-Block, Flask-Smoke-Test (App startet, `/api/version`
  liefert "2.2.17") - alle bestanden, wie bei jeder Auslieferung
  unabhaengig vom Umfang der Aenderung.

- **v2.2.18 (MK6, reine Dokumentations-Korrektur):** Nutzer meldete einen
  in einem ANDEREN Chat entdeckten Sachfehler: README Abschnitt 2 nannte
  als Fundstelle fuer die Aktivierung des **Developer Mode** die "Bambu
  Handy App (pro Geraet)". Das ist falsch - im reinen LAN-Modus (den
  dieses Dashboard voraussetzt) ist die Verbindung zwischen Drucker und
  Bambu-Handy-App gekappt, der Developer Mode kann dort also gar nicht
  eingeschaltet werden. Aktivierung erfolgt stattdessen **lokal am
  Drucker selbst** ueber dessen eigene Einstellungen (weiterhin eine
  Pro-Geraet-Einstellung). Der genaue Menuepfad am Drucker-Display
  wurde NICHT recherchiert oder geraten, da er je nach Druckermodell
  vermutlich unterschiedlich ist (Regel: kein Raten bei undokumentierten,
  modellabhaengigen Ablaeufen ohne verifizierbare Quelle) - README nennt
  daher nur, DASS und WO (lokal am Geraet) die Einstellung vorgenommen
  wird, nicht den genauen Klickpfad.
  Geaendert:
  - README.md, Abschnitt 2 (Tabellenzeile "Bambu Lab"): "Bambu Handy App,
    pro Geraet" ersetzt durch "lokal am Drucker ueber dessen Einstellungen,
    pro Geraet" plus kurze Begruendung (LAN-Modus kappt die App-Verbindung).
    Abschnitt 4 verweist nur per Link auf Abschnitt 2 zurueck und musste
    nicht separat geaendert werden.
  - UEBERGABE.md: Korrektur-Hinweis direkt bei der urspruenglichen
    v1.6.x-Fehldiagnose ergaenzt (dort stand die falsche Angabe zuerst),
    damit die historische Narrative nicht stillschweigend umgeschrieben
    wird, sondern die spaetere Korrektur nachvollziehbar bleibt.
  Kein Code-, Verhaltens- oder API-Unterschied. Getestet: `py_compile
  app.py`, `node --check` auf dem extrahierten `<script>`-Block,
  Flask-Smoke-Test (App startet, `/api/version` liefert "2.2.18") - alle
  bestanden.

- **v2.2.19 (MK6, GitHub-Actions-Fix):** Nutzer meldete einen fehl-
  geschlagenen Workflow-Lauf: der Release-Schritt
  (`softprops/action-gh-release@v2`) brach mit `403 Resource not
  accessible by integration` ab, direkt im Anschluss `Unexpected error
  fetching GitHub release ... HttpError: Resource not accessible by
  integration`. Root Cause (bekanntes, dokumentiertes GitHub-Actions-
  Verhalten, nicht geraten): der automatisch erzeugte `GITHUB_TOKEN`
  bekommt, wenn ein Workflow KEINEN expliziten `permissions`-Block
  deklariert, die unter **Settings -> Actions -> General -> Workflow
  permissions** des Repos/der Organisation hinterlegte Vorgabe - und
  deren Standardwert ist seit 2023 bei neu angelegten Repos/Orgs oft
  "Read repository contents and packages permissions" (nur Lesezugriff).
  Anlegen eines Release bzw. des zugehoerigen Tags braucht aber
  Schreibzugriff auf `contents` - ohne diesen schlaegt genau der
  gemeldete Schritt fehl. Der Workflow `build-exe.yml` hatte seit seiner
  Einfuehrung nie einen `permissions`-Block, war also immer von der
  (unbekannten, nicht vom Projekt kontrollierten) Repo-/Org-Vorgabe
  abhaengig - frueher vermutlich durch eine permissivere Standard-
  einstellung oder durch den damals noch an Tag-Pushes gekoppelten Ablauf
  (vor v2.2.13) unbemerkt geblieben.
  Geaendert:
  - `.github/workflows/build-exe.yml`: `permissions: contents: write`
    auf Workflow-Ebene ergaenzt (direkt vor dem `on:`-Block) - macht den
    Token-Scope unabhaengig von der Repo-/Org-Standardeinstellung
    ausreichend. Kommentarblock oben im Workflow um Begruendung erweitert.
  - README.md, Abschnitt 0: Troubleshooting-Hinweis ergaenzt (fuer den
    seltenen Fall, dass eine Organisations-Richtlinie den expliziten
    `permissions`-Block selbst noch ueberstimmt - dann hilft nur die
    manuelle Umstellung auf "Read and write permissions" in den Repo-
    Einstellungen). Versionshinweis auf v2.2.19 fortgeschrieben.
  Kein Python-/JS-Code betroffen (reine CI/CD-Konfiguration) - die
  uebliche `py_compile`/`node --check`/Flask-Smoke-Test-Pruefung wurde
  trotzdem fuer `app.py` (Versionsnummer-Erhoehung) durchgefuehrt, eine
  inhaltliche Pruefung des Workflows selbst ist nur durch einen
  tatsaechlichen Push ins Zielrepo moeglich (nicht Teil dieser
  Auslieferung, liegt beim Nutzer).

- **v2.2.20 (MK6, AMS-HT-Bug gefunden + abgesichert, voller
  Protokoll-Fix noch offen):** Nutzer meldete einen Druckabbruch auf
  einem **H2D Pro** mit **AMS 2 Pro + AMS HT** (PLA-Stuetzmaterial sollte
  aus der HT kommen): nach den ersten Schichten erschien am Drucker
  **"Die Zuordnungstabelle des AMS konnte nicht abgerufen werden"** -
  derselbe Fehlertext wie beim X1C-Bug aus v1.6.2, aber eine GAENZLICH
  ANDERE Ursache (dort: Position-in-gefilterter-Liste statt
  Original-Index; hier: siehe unten). Auf Nachfrage: manuelle Zuordnung
  am Drucker-Display hatte schon beim damaligen X1C-Problem nicht
  geholfen, und der Nutzer hat keine Moeglichkeit fuer eine
  Wireshark-/Mitmproxy-Analyse - beides floss in die Loesung unten ein.

  **Root Cause (bestaetigt per Recherche, NICHT geraten):**
  `_slot_to_flat_index()` berechnet den an den Drucker gesendeten
  "ams_mapping"-Positionswert als `int(ams_einheit_id) * 4 +
  int(fach_id)` - eine Community-Konvention, die davon ausgeht, dass
  JEDE AMS-Einheit 4 Faecher hat. Zwei unabhaengige Quellen mit echten
  MQTT-Rohdaten (bambulab/BambuStudio Issue #7931, TigerTag-Project/
  TigerSpool-RFID Issue #8) sowie die offizielle Bambu-Produktseite der
  AMS HT bestaetigen: **die AMS HT hat nur 1 Fach und meldet sich mit
  der Einheit-ID 128** (nicht 0/1/2/3 wie reguläre Einheiten). Die
  bestehende Formel berechnet fuer ein HT-Fach also `128 * 4 + 0 =
  512` - ein voellig sinnloser Wert, der trotzdem unveraendert als
  "ams_mapping"-Position an den Drucker gesendet wurde (sowohl bei
  automatischer ALS AUCH bei manueller Auswahl ueber den eigenen
  Zuordnungsdialog des Dashboards, da beide denselben `flat_index`
  verwenden). Das erklaert exakt das beobachtete Verhalten: der Druck
  startet (laeuft zunaechst mit bereits geladenem Material), scheitert
  aber, sobald der Drucker versucht, die Position 512 in seiner
  Zuordnungstabelle aufzuloesen, um auf die HT umzuschalten.

  **Was NICHT getan wurde:** der tatsaechlich fuer AMS-HT-Faecher
  erwartete "ams_mapping"-Wert (oder ob dafuer ueberhaupt ein anderes
  Feld wie "ams_mapping2" noetig ist - laut einem Fund aus der
  Recherche zu einem verwandten Python-Projekt [synman/
  bambu-printer-manager Issue #62] nutzt BambuStudio fuer DUAL-DUESEN-
  Drucker wie den H2D teils ein eigenes "ams_mapping2"-Array mit
  virtuellen Tray-IDs pro physischem Extruder, z. B. 255/254 fuer
  externe Spulen - unklar, ob/wie das mit AMS-HT-Faechern
  zusammenspielt) ist NICHT dokumentiert und wurde NICHT geraten
  (Projekt-Konvention). Ein zweiter Recherche-Fund (TigerTag-Project/
  TigerSpool-RFID Issue #8, allerdings zu einem ANDEREN MQTT-Kommando
  als project_file) schreibt explizit "writing to an HT slot is
  unverified" - selbst dort existiert also kein bestaetigter Wert.

  **Implementierter Zwischenschritt (sicher, keine Vermutung):**
  1. Neue Funktion `_is_ams_ht_slot(slot)`: erkennt AMS-HT-Faecher
     anhand der Einheit-ID (>= 128 - eine normale AMS-Einheit hat immer
     eine kleine ID, 128 ist dafuer nie plausibel).
  2. `_find_matching_tray()` bekommt einen neuen Parameter
     `include_ht` (Default `False`): schliesst AMS-HT-Faecher
     standardmaessig von der automatischen Zuordnung aus - ein
     Filament, das farblich/materialmaessig zu einem HT-Fach passen
     wuerde, bekommt also keinen Vorschlag mehr (faellt auf "-1" /
     extern-manuell zurueck), statt den kaputten Wert 512 zu erzeugen.
  3. `preview_print()`: prueft bei jedem nicht automatisch zugeordneten
     Filament ZUSAETZLICH (nur informativ, `include_ht=True`), ob
     eigentlich ein HT-Fach gepasst haette, und liefert das als neues
     Feld `"ht_excluded"` mit - damit der Nutzer im Dialog nicht
     faelschlich denkt, es sei ueberhaupt kein passendes Material
     vorhanden. `ams_trays` traegt jetzt zusaetzlich
     `"unsupported_ht": true/false` pro Fach.
  4. Frontend (`amsRowHtml()`): AMS-HT-Faecher werden aus dem "Andere
     Wahl"-Dropdown ENTFERNT (der Nutzer kann sie ueber das Dashboard
     also gar nicht mehr versehentlich anwaehlen) - stattdessen ein
     deaktivierter Hinweis-Eintrag "AMS HT: automatische Zuordnung noch
     nicht unterstuetzt". Bei `ht_excluded` zeigt der Vorschlagstext
     explizit, DASS ein passendes HT-Fach existiert, aber bewusst nicht
     automatisch zugeordnet wird (statt des sonst irrefuehrenden "keine
     passende Farbe gefunden").
  5. README Abschnitt 4 um einen entsprechenden Hinweisabsatz ergaenzt.

  **Diagnose-Mechanismus fuer eine spaetere vollstaendige Loesung**
  (neu, `_log_foreign_project_file_command()` +
  Request-Topic-Abonnement in `_on_connect()`/`_on_message()`): da der
  Nutzer weder Wireshark noch Mitmproxy zur Verfuegung hat, nutzt diese
  Loesung eine Eigenschaft des lokalen MQTT-Brokers eines Bambu-
  Druckers selbst: jeder damit verbundene Client (bisher nur fuer das
  eigene "report"-Topic genutzt) kann grundsaetzlich JEDES Topic
  abonnieren, auch eines, auf das ein ANDERER Client (z. B. Bambu
  Studio) veroeffentlicht - das ist Standard-MQTT-Pub/Sub-Verhalten,
  keine besondere Berechtigung. Das Dashboard abonniert deshalb seit
  dieser Version zusaetzlich das eigene `device/<serial>/request`-Topic
  (bisher nur zum Publizieren eigener Befehle genutzt) und protokolliert
  JEDES darauf beobachtete `project_file`-Kommando vollstaendig auf der
  Server-Konsole (`[MK6-DIAG]`-Zeile) - unabhaengig davon, ob es vom
  Dashboard selbst oder von einem anderen Client stammt. Druckt der
  Nutzer also einmal reguleaer ueber Bambu Studio mit aktiver AMS-HT-
  Zuordnung, waehrend das Dashboard mit demselben Drucker verbunden
  bleibt, taucht der tatsaechlich von Bambu Studio gesendete, echte
  "ams_mapping"/"ams_mapping2"-Wert fuer das HT-Fach in der Konsole auf
  - verifizierte Beweisdaten statt einer Vermutung. Enthaelt keine
  Zugangsdaten (Access Code wird nur beim TLS-Handshake verwendet).
  Naechster Schritt, SOBALD diese Daten vorliegen: `_slot_to_flat_index()`
  entsprechend erweitern und die Einschraenkung aus diesem Eintrag
  (Punkte 1-5 oben) wieder aufheben.

  Getestet: `py_compile app.py`, `node --check` auf dem extrahierten
  `<script>`-Block, Flask-Smoke-Test (App startet, `/api/version`
  liefert "2.2.20"). Zusaetzlich gezielte Python-Tests fuer
  `_is_ams_ht_slot()` (Einheit-ID 128/129 -> True, 0/1/2/3 -> False,
  nicht auswertbarer Slot-String -> False) und `_find_matching_tray()`
  mit `include_ht=False/True` gegen eine simulierte AMS-2-Pro+AMS-HT-
  Konfiguration (HT-Fach wird bei `include_ht=False` nie vorgeschlagen,
  aber bei `include_ht=True` korrekt gefunden) - alle bestanden. Der
  neue Diagnose-Mechanismus selbst (`_log_foreign_project_file_command`)
  konnte nur isoliert mit einem simulierten Kommando-Payload getestet
  werden (loggt korrekt bei `command=="project_file"`, bleibt still bei
  `"pushall"` und anderen Kommandos) - ein Test mit einem ECHTEN,
  gleichzeitig verbundenen Bambu-Studio-Client ist nur beim Nutzer
  selbst moeglich.

  **Auch korrigiert:** der in v2.2.18 uebersehene zweite Fundort
  derselben "Bambu Handy App"-Falschangabe zur Developer-Mode-
  Aktivierung - diesmal in einem Code-Kommentar bei `send_print()`
  (nicht in der README, dort war v2.2.18 bereits vollstaendig).

- **v2.2.21 (MK6, zwei Anliegen: konfigurierbares Verlaufslimit +
  AMS-HT-Fix mit jetzt verifizierten Daten):**

  **1. Verlaufslimit ueber config.json.** Nutzer wollte die maximale
  Anzahl der je Drucker im Verlauf aufbewahrten Druckauftraege (bisher
  fest `PRINT_HISTORY_MAX_JOBS = 30`) ueber `config.json` einstellbar
  machen koennen (Zahl oder unendlich). Umgesetzt:
  - `PRINT_HISTORY_MAX_JOBS` nach ganz oben vorgezogen (vor
    `DEFAULT_CONFIG`, das jetzt direkt darauf verweist statt den Wert 30
    ein zweites Mal hart zu codieren).
  - Neues Feld `"history_max_jobs"` in `DEFAULT_CONFIG`/`config.example.json`
    (Standardwert 30, unveraendertes Verhalten fuer alle bestehenden
    Installationen ohne dieses Feld).
  - Neue Funktion `_resolve_history_max_jobs(raw_value)`: akzeptiert
    eine positive Ganzzahl (= Limit), `0`, `null` oder den Text
    `"unendlich"` (Gross-/Kleinschreibung egal, = kein Limit, intern als
    `None` repraesentiert), faellt bei jedem anderen Wert (negative
    Zahl, sonstiger Text, Kommazahl, ...) defensiv auf den Standardwert
    30 zurueck und loggt das EINMALIG beim Start (`[MK6] Warnung: ...`),
    damit ein Tippfehler in `config.json` auffaellt statt still
    ignoriert zu werden.
  - `PrintHistoryStore.__init__()` bekommt jetzt `max_jobs_per_printer`
    als Parameter (Default weiterhin `PRINT_HISTORY_MAX_JOBS` fuer
    direkte Testbarkeit ohne Config), `DashboardApp.__init__()` uebergibt
    `_resolve_history_max_jobs(self.cfg.get("history_max_jobs"))`.
  - **Wichtiger interner Stolperstein, der VOR dem Ausliefern aufgefallen
    ist:** `add_entry()` schnitt die Liste bisher per
    `entries[self.MAX_JOBS_PER_PRINTER:]`/`entries[:self.MAX_JOBS_PER_PRINTER]`
    zu. Mit `None` als Limit haette `entries[None:]` in Python NICHT
    "nichts", sondern "die GESAMTE Liste" ergeben (Python wertet
    `liste[None:]` identisch zu `liste[:]`) - das haette bei "unendlich"
    jeden einzelnen Verlaufseintrag faelschlich als "zu entfernen"
    markiert und seine Dateien geloescht, obwohl der Index sie behalten
    sollte. Deshalb jetzt ein expliziter `if self.max_jobs_per_printer
    is None: removed = []`-Zweig statt der reinen Slice-Syntax.
  - README Abschnitt 3 und `config.example.json` entsprechend ergaenzt.
  - Betrifft bewusst NUR den Verlauf (`PrintHistoryStore`), nicht die
    Warteschlange (`PrintQueueStore`) - die hat ohnehin kein Limit, ihre
    Groesse ergibt sich allein aus tatsaechlich wartenden Auftraegen.

  **2. AMS-HT-Fix mit verifizierten Daten (loest die in v2.2.20
  offengelassene Einschraenkung ab).** Der in v2.2.20 eingebaute
  Diagnose-Mechanismus hat funktioniert: der Nutzer druckte regulaer
  ueber Bambu Studio auf dem H2D Pro (AMS 2 Pro + AMS HT) und schickte
  die `[MK6-DIAG]`-Konsolenausgabe. Der eingefangene, ECHTE
  `project_file`-Befehl zeigt:
  ```
  "ams_mapping": [1, -1, -1, ..., -1, 128]   (Position 0 = AMS-2-Pro-Fach
                                               1, Position 16 = AMS-HT-Fach)
  "ams_mapping2": [
    {"ams_id": 0,   "slot_id": 1},            (dieselbe Position 0)
    {"ams_id": 255, "slot_id": 255} * 15,      (ungenutzte Positionen)
    {"ams_id": 128, "slot_id": 0}              (dieselbe Position 16: AMS HT)
  ]
  ```
  Zwei neue, jetzt BEWIESENE (nicht mehr vermutete) Fakten:
  - Der flache `"ams_mapping"`-Wert fuer ein AMS-HT-Fach ist schlicht
    die rohe Geraete-ID (**128**, OHNE Multiplikation mit 4) - waehrend
    reguläre Einheiten weiterhin der alten `Einheit*4+Fach`-Formel folgen
    (bestaetigt: Einheit 0, Fach 1 -> Wert 1).
  - Bambu Studio sendet beim H2D Pro ZUSAETZLICH ein paralleles Feld
    `"ams_mapping2"`: ein Array von `{"ams_id", "slot_id"}`-Paaren, EIN
    Eintrag pro Filament-Position (parallel zu `"ams_mapping"`), mit dem
    Platzhalter `{"ams_id": 255, "slot_id": 255}` fuer nicht benoetigte
    Positionen (ANDERE Konvention als das `-1` von `"ams_mapping"`!).
    Vermutlich noetig, damit die Firmware bei Druckern mit MEHREREN
    physischen Duesen (H2D/H2D Pro) weiss, welcher Duese ein Filament
    zugeordnet ist - ob/wie das bei den vermutlich einduesigen H2S/H2C
    gebraucht wird, ist NICHT verifiziert.

  Umgesetzt:
  - `_slot_to_flat_index()`: Einheit-ID >= 128 -> Rueckgabe `unit + tray`
    (kein `*4` mehr), sonst unveraendert `unit*4+tray`.
  - Neue Funktion `_flat_index_to_ams_pair(flat_index)`: rein
    mechanische Umkehrung der obigen Formel (KEINE neue Vermutung) -
    liefert `(ams_id, slot_id)` fuer einen gueltigen flachen Index, oder
    `None` fuer "kein Fach" (-1).
  - `_request_print()`: baut jetzt zusaetzlich `"ams_mapping2"` aus dem
    vorhandenen `"ams_mapping"` (per `_flat_index_to_ams_pair()`), aber
    NUR wenn `bambu_family == "h2"` (H2S/H2D/H2D Pro/H2C) - bewusst NICHT
    fuer x1/a1/p1/p2/x2 gesetzt, um das dort seit MK5 bestaetigt
    funktionierende Verhalten nicht anzutasten; fuer diese Familien lag
    ohnehin kein Beweis vor, dass sie dieses Feld kennen oder brauchen.
  - Die in v2.2.20 eingefuehrte Ausschluss-/Warnlogik fuer AMS-HT-Faecher
    (`unsupported_ht`/`ht_excluded`-Felder, `include_ht`-Parameter bei
    `_find_matching_tray()`, das deaktivierte Dropdown-Element im
    Frontend) wurde vollstaendig zurueckgebaut - AMS-HT-Faecher werden
    wieder ganz normal wie jedes andere Fach automatisch vorgeschlagen
    UND manuell waehlbar.
  - Der Diagnose-Mechanismus selbst (`_log_foreign_project_file_command()`,
    Request-Topic-Abonnement) BLEIBT bestehen - weiterhin nuetzlich fuer
    kuenftige, aehnlich unklare Protokollfragen.
  - README Abschnitt 4 aktualisiert: Einschraenkung aufgehoben, AMS HT
    als vollstaendig unterstuetzt beschrieben.

  Getestet: `py_compile app.py`. Gezielte Python-Tests: `_slot_to_flat_index()`
  liefert fuer `"128-0"` jetzt 128 (vorher 512) und fuer `"0-1"`
  weiterhin 1; `_flat_index_to_ams_pair()` liefert fuer 128 `(128, 0)`,
  fuer 1 `(0, 1)` und fuer -1 `None`; End-to-End-Test von `_request_print()`
  mit einer simulierten AMS-2-Pro+AMS-HT-Konfiguration auf einem
  `bambu_family="h2"`-Drucker zeigt im gesendeten Payload exakt dieselbe
  Struktur wie der eingefangene, echte Bambu-Studio-Befehl (gleiche
  `ams_mapping`-Werte UND gleiche `ams_mapping2`-Paare); derselbe Test
  mit `bambu_family="x1"` zeigt: `ams_mapping` wie gehabt, aber KEIN
  `ams_mapping2`-Feld im Payload (bestaetigt die Familien-Beschraenkung).
  `node --check` auf dem extrahierten `<script>`-Block, Flask-Smoke-Test
  (Version 2.2.21) - alle bestanden.

  **Drittes Anliegen in derselben Nachricht (recherchiert, NICHT
  umgesetzt): Kamera funktioniert bei Ultimaker und A1 problemlos, bei
  X1 und H2 gar nicht.** Root Cause per Recherche gefunden (siehe
  ClusterM/open-bamboo-networking Issue #105 sowie printerhive.com-
  Dokumentation, beide unabhaengig zum selben Ergebnis): Bambu-Drucker
  nutzen je nach Modellreihe DREI VERSCHIEDENE, inkompatible lokale
  Kamera-Protokolle, nicht eines fuer alle:
  - **A1/A1 Mini:** rohes MJPEG ueber TLS auf Port 6000 - genau das, was
    `bambu_mjpeg_generator()` aktuell implementiert. Deshalb funktioniert
    nur diese Familie.
  - **X1(C/E)/P1(P/S)/P2S:** **RTSPS** auf Port 322 (NICHT Port 6000) -
    zusaetzlich muss am Drucker separat zum "Developer Mode" noch die
    Einstellung **"LAN Only Liveview"** aktiviert werden (schaltet das
    MQTT-Statusfeld `ipcam.rtsp_url` von `"disable"` auf eine echte
    `rtsps://...`-Adresse um). Unser Code versucht aktuell IMMER Port
    6000 mit dem A1-Protokoll - bei dieser Familie laeuft das ins Leere
    bzw. liefert Muell ("JPEG magic mismatch" laut dortigem Issue).
  - **H2S/H2D/H2D Pro/H2C (und X2D):** ein neues, von Bambu NICHT
    offiziell dokumentiertes Protokoll namens **"BRTC"** - das bestaetigt
    sich uebrigens auch im v2.2.20-Diagnose-Mitschnitt oben: die
    `"url"` im echten `project_file`-Befehl lautet `"brtc://emmc/..."`,
    nicht `"ftp:///..."` wie bisher angenommen/gesendet (separate
    Beobachtung, siehe unten). Die Rohdaten-Framing von BRTC ist laut
    dem GitHub-Issue nur in Ansaetzen reverse-engineered (ein
    Ablehnungspaket wurde dokumentiert, ein funktionierender Frame-
    Mitschnitt bisher nicht) - eine Implementierung waere derzeit
    zwangslaeufig Raten, was die Projekt-Konvention ausdruecklich
    ausschliesst.

  Konsequenz/Vorschlag (dem Nutzer vorgelegt, Entscheidung noch
  ausstehend): X1/P1/P2S waere ueber FFmpeg (RTSPS -> MJPEG-
  Transcoding fuer den Browser) technisch sauber loesbar, braucht aber
  FFmpeg als NEUE Build-/Laufzeit-Abhaengigkeit (bei PyInstaller fuer
  Windows UND macOS mitzubundlen - vergleichbares Abwaegungsthema wie
  der im September verworfene eingebettete MQTT-Broker) sowie die
  manuelle Aktivierung von "LAN Only Liveview" an jedem betroffenen
  Drucker. H2-Serie (BRTC) ist aktuell NICHT seriös umsetzbar, ohne das
  Protokoll zu raten.

  **Separat notiert, noch zu pruefen:** der oben eingefangene echte
  H2D-Pro-Befehl verwendet `"url": "brtc://emmc/<datei>"` fuer den
  Speicherort, waehrend unser Code fuer die "h2"-Familie bisher
  `"ftp:///<datei>"` sendet (siehe `_request_print()`, Kommentar zu
  v2.2.10). Der aktuell bei diesem Nutzer bestaetigt funktionierende
  Druckstart (dieselbe Diagnose-Session) legt nahe, dass `"ftp:///..."`
  trotzdem akzeptiert wird (sonst waere der Druck gar nicht erst
  gestartet) - mittel-/langfristig waere aber zu pruefen, ob
  `"brtc://emmc/..."` das eigentlich "korrekte", von Bambu Studio selbst
  verwendete Schema fuer H2-Geraete ist und `"ftp:///..."` nur ein
  (zufaellig noch funktionierender) Alias. Keine Aenderung in v2.2.21,
  nur dokumentiert fuer eine kuenftige Session.

- **v2.2.22 (MK6): Kameraproblem X1/H2 geloest - FFmpeg/RTSPS fuer
  X1/P1/P2/H2/X2, automatisch per GitHub Actions mitgebaut.** Nutzer
  meldete: Kamera funktioniert bei Ultimaker und A1 problemlos, bei X1
  und H2 gar nicht. Recherche (siehe v2.2.21-Eintrag oben fuer den
  ersten, noch unvollstaendigen Stand) ergab zunaechst drei vermeintlich
  verschiedene Protokolle je Familie - bei der Umsetzung dieser Version
  wurde das praezisiert und dabei eine fruehere, ZU KURZ GEGRIFFENE
  Annahme korrigiert:

  **KORREKTUR der v2.2.21-Einschaetzung:** die vermutete eigene,
  undokumentierte "BRTC"-Kameraprotokoll fuer die H2-Serie beruhte auf
  einer Verwechslung. Das im v2.2.20/21-Diagnose-Mitschnitt beobachtete
  `"url": "brtc://emmc/..."` ist ein DATEISPEICHER-Schema im
  project_file-Druckstart-Kommando, hat mit dem Kamera-Stream nichts zu
  tun. Fuer die Kamera selbst bestaetigt der Bambu-Forum-Thread "H2C RTSP
  for Camera?" ausdruecklich, dass ein Nutzer nach Aktivieren der
  Druckereinstellung "LAN Only Liveview" (separat vom vollen LAN-Only-
  Modus) erfolgreich per RTSPS auf einen H2C zugegriffen hat - identisch
  zum bereits fuer X1/P1 bekannten Mechanismus. Ebenso bestaetigt der
  Bambu-Forum-Thread "P2S: Lan Only Liveview while in Cloud Mode?" diese
  Einstellung fuer die P2-Serie. **Alle Bambu-Familien ausser A1 nutzen
  also denselben RTSPS-Mechanismus fuer die Kamera** - es gibt keine
  dritte, unloesbare Protokollvariante.

  **Verifizierte technische Eckpunkte (mehrere unabhaengige, sich
  gegenseitig bestaetigende Quellen, keine geratenen Werte):**
  - Stream-URL: `rtsps://bblp:<access_code>@<ip>:322/streaming/live/1`
    (Benutzername "bblp" + Access Code als Passwort, wie beim
    bestehenden MJPEG-Port-6000-Protokoll und beim FTPS-Upload) - per
    ffplay von einem Nutzer im Bambu-Forum-Thread "How to access camera
    on LAN ?(firmware 01.06+)" bestaetigt, identisch in der
    Referenzimplementierung "bambustudio_mcp" (camera/stream.py).
  - MQTT-Statusfeld `print.ipcam.rtsp_url`: woertlicher String
    `"disable"`, solange "LAN Only Liveview" am Drucker nicht aktiviert
    ist (exakt so ausgewertet in der aktiv gepflegten Home-Assistant-
    Integration greghesp/ha-bambulab, pybambu/models.py: "if
    self.rtsp_url == 'disable': ..."); sonst eine echte RTSPS-URL.
  - `-rtsp_transport tcp` als FFmpeg-Option ausdruecklich empfohlen (u. a.
    im genannten H2C-Thread: "ffplay with TCP transport successfully
    connected") - UDP scheitert oefter an lokalen Firewalls/NAT.
  - FFmpeg-TLS-Zertifikatspruefung fuer RTSPS: mehrere Nutzerberichte
    (ffplay/ffmpeg ohne jede Sonderbehandlung erfolgreich gegen das
    selbstsignierte Zertifikat der Drucker verbunden) zeigen, dass kein
    spezielles "TLS ueberspringen"-Flag noetig ist - bewusst KEIN
    Flag gesetzt, um keine (zum Implementierungszeitpunkt erst seit
    Mitte 2025 in FFmpeg ueberhaupt existierende) TLS-Option zu
    erzwingen, die je nach mitgelieferter FFmpeg-Version gar nicht
    existiert.
  - Eingabe-Codec des Streams (H.264/H.265/bereits MJPEG) ist oeffentlich
    nicht dokumentiert UND fuer die Umsetzung nicht relevant: FFmpeg
    erkennt/dekodiert jeden Eingabe-Codec automatisch, die Ausgabe wird
    in jedem Fall explizit nach MJPEG neu kodiert (`-c:v mjpeg`).

  **Umsetzung:**
  - Neue Konstante `BAMBU_RTSPS_CAMERA_FAMILIES = {"x1","p1","p2","h2","x2"}`
    (alles ausser "a1", das weiterhin `bambu_mjpeg_generator()`/Port 6000
    nutzt, seit MK5 bestaetigt funktionierend).
  - `_apply_print_report()`: wertet jetzt zusaetzlich `print.ipcam.rtsp_url`
    aus und haelt ihn in `self.status["ipcam_rtsp_url"]` nach (wie bei
    anderen optionalen Feldern NUR bei Vorhandensein im jeweiligen
    Report uebernommen, da "ipcam" typischerweise nur in vollen
    "pushall"-Antworten steckt, nicht in jedem Teil-Update).
  - Neue Funktion `_find_ffmpeg_binary()` (Pendant zu
    `_find_ftps_upload_helper()`): sucht zuerst `ffmpeg(.exe)` neben der
    Haupt-exe, faellt im Entwicklungsbetrieb (kein PyInstaller-Build) auf
    eine ueber PATH erreichbare Installation zurueck.
  - Neue Funktion `bambu_rtsp_mjpeg_generator(ip, access_code,
    ffmpeg_path)`: startet FFmpeg als Subprozess
    (`-rtsp_transport tcp -i rtsps://bblp:<code>@<ip>:322/streaming/live/1
    -an -c:v mjpeg -q:v 5 -r 10 -f mpjpeg -`) und reicht dessen rohe
    Standardausgabe 1:1 als Flask-Response durch - FFmpegs eingebauter
    "mpjpeg"-Muxer erzeugt bereits einen fertigen
    "multipart/x-mixed-replace"-Bytestrom mit fest codiertem Boundary-
    String "ffserver" (libavformat/mpjpeg.c), eigenes Frame-Parsing wie
    bei `bambu_mjpeg_generator()` ist dafuer nicht noetig. Im
    `finally`-Block wird der FFmpeg-Subprozess beim Schliessen der
    Browser-Verbindung zuverlaessig beendet (verhindert verwaiste
    RTSPS-Verbindungen zum Drucker).
  - `/camera/<printer_id>`: fuer `bambu_family` in
    `BAMBU_RTSPS_CAMERA_FAMILIES` wird vor dem Start klar unterschieden:
    `ipcam_rtsp_url == "disable"` -> 409 mit Hinweis auf "LAN Only
    Liveview"; `None` (noch kein Report empfangen) -> 503 mit Hinweis
    auf kurz warten; `_find_ffmpeg_binary()` liefert `None` -> 500 mit
    Hinweis auf fehlendes FFmpeg; sonst `bambu_rtsp_mjpeg_generator()`.
    A1 bleibt unveraendert auf `bambu_mjpeg_generator()`.
  - Frontend (`openCam()`/`closeCam()`): bei einem Ladefehler des
    Kamera-`<img>` (die obigen Fehlerfaelle liefern kurzen Klartext statt
    eines Bildes) wird derselbe Pfad zusaetzlich per `fetch()` als Text
    abgerufen und die konkrete Fehlermeldung in einem neuen Textfeld im
    Kamera-Fenster angezeigt, statt nur ein kaputtes Bild-Icon zu zeigen.

  **GitHub-Actions-Workflow (`build-exe.yml`):** FFmpeg wird bei jedem
  Build automatisch besorgt und neben `DruckerDashboard.exe`/
  `FtpsUploadHelper.exe` ins Zip gelegt - kein manueller Nutzer-Schritt:
  - Windows: aktuelles Release von `GyanD/codexffmpeg` (GitHub-Spiegel
    der etablierten gyan.dev-Windows-Builds) ueber die GitHub-REST-API
    abgefragt (Asset-Name enthaelt die FFmpeg-Versionsnummer und aendert
    sich bei jedem FFmpeg-Release, deshalb bewusst zur Laufzeit ermittelt
    statt fest eingetragen), `ffmpeg.exe` nach dem Entpacken per Suche
    (nicht per angenommenem Pfad) gefunden.
  - macOS: stabile, versionsunabhaengige Download-API-URL von
    `evermeet.cx/ffmpeg` (`.../ffmpeg/getrelease/zip`).
    **Einschraenkung:** evermeet.cx bietet laut eigener Aussage
    ausdruecklich KEINE native Apple-Silicon(arm64)-Variante, nur Intel
    (x86_64) - obwohl der `macos-14`-Build-Runner selbst natives arm64
    ist. Der Build-Runner fuehrt das heruntergeladene FFmpeg nicht aus
    (bettet es nur ein), das ist unproblematisch; auf dem Mac des Nutzers
    laeuft dieses x86_64-FFmpeg dann unter Rosetta 2 (von macOS bei
    Bedarf automatisch zur Installation angeboten, meist einmalig und
    transparent) - als bewusster, dem Nutzer kommunizierter Kompromiss
    akzeptiert (vergleichbare Abwaegung wie beim im September 2026
    verworfenen eingebetteten MQTT-Broker).

  README Abschnitte 0/1/2/6 aktualisiert (Zip-Inhalt jetzt drei Dateien,
  "LAN Only Liveview"-Voraussetzung je Familie, FFmpeg-Fallback im
  Entwicklungsbetrieb, Grenzen-Abschnitt).

  Getestet: `py_compile app.py`; `node --check` auf dem extrahierten
  `<script>`-Block; Flask-Smoke-Test (Version 2.2.22); gezielte Tests fuer
  `_find_ffmpeg_binary()` (neben der exe gefunden / weder exe noch PATH
  -> None); End-to-End-Tests von `/camera/<printer_id>` ueber den Flask-
  Testclient mit einer simulierten `PrinterConnection` fuer alle vier
  Faelle (ipcam_rtsp_url `"disable"` -> 409 mit Hinweistext, `None` ->
  503, gesetzt aber FFmpeg fehlt -> 500 mit Hinweistext, A1 unveraendert
  weiterhin ueber `bambu_mjpeg_generator()` - mit einem Fake-Generator
  getestet, um den echten 5-Sekunden-Netzwerk-Timeout bei einer
  Fantasie-IP zu vermeiden); Quellcode-Abgleich von RTSPS-URL-Format,
  FFmpeg-Kommandozeile und Boundary-String-Konsistenz zwischen FFmpegs
  mpjpeg-Muxer und dem gesetzten Flask-Response-Mimetype. Der GitHub-
  Actions-Workflow selbst (FFmpeg-Download/-Einbettung) konnte in dieser
  Umgebung nicht end-to-end getestet werden (kein GitHub-Actions-Runner
  verfuegbar) - die einzelnen Bausteine (API-Antwortformat/Asset-
  Benennung von GyanD/codexffmpeg, stabile Download-URL von evermeet.cx)
  wurden aber gegen die jeweilige Live-Quelle verifiziert, nicht geraten.

- **v2.2.23 (MK6): RTSPS-Kamera (v2.2.22) haengt bei X1E/H2D Pro trotz
  aktivierter "LAN Only Liveview" - kein Bild, kein Fehler.** Nutzer
  testete v2.2.22 auf echter Hardware (X1E, H2D Pro, "LAN Only
  Liveview" nachweislich aktiviert) und meldete: Kamera-Fenster laedt
  dauerhaft, weder Bild noch Fehlermeldung - auch nach laengerem Warten.

  Das Fehlen JEDER Reaktion (keiner der vier in v2.2.22 eingebauten
  klaren Fehlerfaelle - 409/503/500 - griff) zeigt: die Pruefungen VOR
  dem FFmpeg-Start liefen alle unauffaellig durch (ipcam_rtsp_url war
  weder "disable" noch None, FFmpeg wurde gefunden) - der eigentliche
  FFmpeg-Subprozess selbst blieb haengen, OHNE jemals Daten ODER ein
  Prozessende zu liefern. Mangels Fehlermeldung aus der Server-Konsole
  (stderr des Subprozesses wurde bisher mit stderr=PIPE erzeugt, aber
  NIE gelesen) war die exakte Ursache zu diesem Zeitpunkt NICHT
  feststellbar - zwei unabhaengige, beide plausible Erklaerungen kommen
  in Frage und wurden BEIDE behoben, statt eine zu raten:

  1. **Bekanntes, ursachenunabhaengiges Python-subprocess-Problem:** wird
     `stderr=subprocess.PIPE` gesetzt, aber nie gelesen, kann der
     Betriebssystem-interne Pipe-Puffer volllaufen (typischerweise schon
     bei wenigen zehn KB) - FFmpeg blockiert dann beim naechsten
     Schreibversuch nach stderr UNBEGRENZT. Das allein erzeugt exakt das
     beschriebene Bild ("haengt fuer immer, kein Fehler"), unabhaengig
     davon, ob die RTSPS-Verbindung selbst ueberhaupt ein Problem hatte.
  2. **Fehlender Verbindungs-Timeout:** ohne explizites Zeitlimit kann
     FFmpeg bei einer RTSPS-Verbindung, die aus irgendeinem Grund nicht
     zustande kommt (TLS-Handshake haengt, Drucker antwortet nicht wie
     erwartet, o.ae.), ebenfalls unbegrenzt warten, statt mit einem
     auswertbaren Fehler abzubrechen.

  **Umsetzung (beide Punkte, keine Vermutung ueber die eigentliche
  Protokollursache noetig):**
  - Neue Funktion `_drain_ffmpeg_stderr(proc, ip)`: liest die
    Standardfehlerausgabe des FFmpeg-Subprozesses fortlaufend in einem
    eigenen Daemon-Thread und gibt jede Zeile sofort auf der Server-
    Konsole aus (Praefix `[MK6-FFMPEG]`) - behebt den moeglichen
    Deadlock UND liefert ab sofort echte Diagnosedaten, falls das
    Problem (teilweise) am RTSPS-Protokoll selbst liegt.
  - `bambu_rtsp_mjpeg_generator()`: startet diesen Thread direkt nach
    dem FFmpeg-Start; neue FFmpeg-Option `-timeout 15000000` (15
    Sekunden, in Mikrosekunden - Socket-I/O-Timeout fuer Verbindungsaufbau
    UND Lesen beim RTSP-Demuxer). Der Optionsname "timeout" ist bewusst
    gewaehlt statt des aelteren "stimeout": laut FFmpeg-Aenderungshistorie
    (avformat/rtsp: "Remove deprecated old options, rename
    stimeout->timeout", FFmpeg 4.4, 2021) wurde "stimeout" seitdem
    ENTFERNT, nicht nur umbenannt - ein aktueller, ueber GyanD/codexffmpeg
    bezogener FFmpeg-Build (siehe build-exe.yml) kennt nur noch den neuen
    Namen.
  - Getestet (ohne echte Druckerhardware, da hier nicht verfuegbar):
    Quellcode-Abgleich der neuen Timeout-Option; gezielter Test mit
    einem Fake-FFmpeg-Skript, das 5000 Zeilen auf stderr schreibt (bei
    weitem genug, um den OS-Pipe-Puffer zu fuellen) UND Daten auf
    stdout liefert - OHNE den Drain-Thread waere das mit hoher
    Wahrscheinlichkeit haengen geblieben, MIT Thread laeuft der
    Generator in 0,03s durch und liefert die Daten korrekt.
  - **Was NICHT getan wurde:** keine Aenderung an der RTSPS-URL selbst
    (`rtsps://bblp:<code>@<ip>:322/streaming/live/1`) oder an sonstigen
    FFmpeg-Optionen, da ohne die jetzt verfuegbare echte Fehlerausgabe
    aus der Server-Konsole unklar ist, ob/welches weitere Problem dort
    noch vorliegt - das waere Raten. Der Nutzer wurde gebeten, nach
    einem erneuten Versuch die `[MK6-FFMPEG]`-Zeilen aus der Server-
    Konsole mitzuteilen, falls das Kamera-Fenster weiterhin nicht
    funktioniert (jetzt entweder mit konkretem Fehlertext oder nach
    spaetestens ~15s mit einem auswertbaren Timeout-Fehler statt
    unbegrenztem Haengen).

- **v2.2.24 (MK6): tatsaechliche Ursache des Kamera-Haengers gefunden
  und behoben - "-tls_verify 0" gegen das selbstsignierte Druckerzertifikat.**
  Der in v2.2.23 eingebaute `[MK6-FFMPEG]`-Mitschnitt lieferte den
  Nutzer-Mitschnitt von ECHTER X1E- UND H2D-Pro-Hardware (beide mit
  aktivierter "LAN Only Liveview") und zeigte exakt dieselbe Fehlerkette
  bei beiden Geraeten:
  ```
  [tls] Peer certificate failed verification
  [in#0] Error opening input: I/O error
  Error opening input file rtsps://bblp:...@...:322/streaming/live/1.
  Error opening input files: I/O error
  ```

  **Root Cause (verifiziert, nicht geraten):** FFmpeg 9.0 - das ueber
  `GyanD/codexffmpeg` bezogene, zum Implementierungszeitpunkt von
  v2.2.22 aktuelle Release (siehe build-exe.yml) - hat den Standardwert
  der Option `tls_verify` von `0` (nicht pruefen) auf `1` (pruefen)
  umgestellt (siehe u. a. den Fachartikel "FFmpeg 9.0 defaults
  tls_verify to 1", lilting.ch). Die Bambu-Drucker verwenden fuer ihren
  RTSPS-Kamera-Stream - wie bereits beim bestehenden MJPEG-Port-6000-
  Protokoll (`ssl._create_unverified_context()`) und beim FTPS-Datei-
  Upload - ein SELBSTSIGNIERTES Zertifikat, das die seit FFmpeg 9.0
  standardmaessig aktive Pruefung folgerichtig ablehnt. Die Forum-
  Berichte, auf die sich die urspruengliche v2.2.22-Umsetzung stuetzte
  (erfolgreiche RTSPS-Verbindung per ffplay ohne Sonderbehandlung),
  stammten erkennbar von AELTEREN FFmpeg-Versionen (vor diesem
  Standardwert-Wechsel) - zum Zeitpunkt dieser Berichte gab es das
  Problem schlicht noch nicht.

  **Umsetzung:** neue FFmpeg-Option `-tls_verify 0` in der Kommandozeile
  von `bambu_rtsp_mjpeg_generator()` (vor `-i`, wie von der Projekt-
  Dokumentation zu dieser 2025 neu hinzugefuegten RTSP-TLS-Option
  verlangt) - deaktiviert die Zertifikatspruefung wieder explizit,
  konsistent mit der bereits an anderer Stelle in diesem Projekt
  etablierten Begruendung (Drucker im eigenen LAN, kein oeffentliches
  Zertifikat zu erwarten).

  Getestet: `py_compile app.py`, `node --check`, Flask-Smoke-Test
  (Version 2.2.24), Quellcode-Abgleich der neuen Option. Ein End-to-
  Ende-Test gegen echte Druckerhardware war in dieser Umgebung nicht
  moeglich - die Korrektur beruht auf der vom Nutzer gelieferten, echten
  FFmpeg-Fehlermeldung (identisch auf zwei unterschiedlichen Geraeten:
  X1E und H2D Pro) und einer extern dokumentierten, bekannten FFmpeg-
  Verhaltensaenderung, nicht auf einer Vermutung. Der Nutzer wurde
  gebeten, nach dieser Version erneut zu testen und bei weiterhin
  bestehenden Problemen wieder die `[MK6-FFMPEG]`-Konsolenausgabe zu
  teilen.

- **v2.2.25 (MK6): weiterhin keine Anzeige nach v2.2.24 - diesmal aber
  OHNE JEDE `[MK6-FFMPEG]`-Zeile.** Nutzer testete erneut (X1E, H2D
  Pro) und lieferte die Konsolenausgabe: nur die normalen Flask/
  Werkzeug-Zugriffsprotokoll-Zeilen (`GET /camera/... 200`), KEINE
  einzige `[MK6-FFMPEG]`-Zeile - weder die neue Start-Meldung aus
  v2.2.23 noch eine Fehlermeldung.

  **Diagnostische Einordnung (noch keine abschliessende Loesung,
  bewusst keine weitere Vermutung ueber das RTSPS-Protokoll selbst):**
  das voellige Fehlen JEDER `[MK6-FFMPEG]`-Zeile bedeutet, dass entweder
  (a) bereits der Start des FFmpeg-Subprozesses selbst haengt (ein
  `subprocess.Popen()`-Aufruf, der nie zurueckkehrt, ist in Python
  durchaus moeglich, u. a. wenn eine frisch heruntergeladene, unsignierte
  exe beim allerersten Ausfuehren von Antivirus-Software/Windows
  Defender einer Echtzeitpruefung unterzogen wird, die den Prozessstart
  faktisch verzoegert oder haengen laesst - siehe die identische,
  bereits dokumentierte Problematik bei `FtpsUploadHelper.exe` weiter
  oben in dieser Datei), oder (b) ein weiterer, hier bislang
  unbekannter Fehler VOR der ersten geloggten Zeile auftrat. Da der
  Code bisher ERST NACH dem Start von FFmpeg ueberhaupt etwas loggte,
  liess sich zwischen beiden Faellen nicht unterscheiden.

  **Zusaetzlich identifizierter, unabhaengig vom obigen Verdacht echter
  Code-Fehler (jetzt ebenfalls behoben):** ein Python-Generator fuehrt
  seinen Funktionskoerper nicht beim Aufruf aus, sondern erst bei der
  ERSTEN Iteration. Bei einer Flask-Streaming-Response (wie
  `bambu_rtsp_mjpeg_generator()`) geschieht diese erste Iteration ERST
  beim Senden des Response-Bodys - zu diesem Zeitpunkt sind Status
  (200) und Header laengst an den Browser verschickt. Das umgebende
  `try/except` in `/camera/<printer_id>` (`except Exception as e:
  return f"Kamera nicht erreichbar: {e}", 502`) konnte einen Fehler
  INNERHALB des Generators (z. B. ein fehlschlagendes `Popen()`, ein
  Lesefehler) deshalb NIE abfangen - er wurde bisher entweder komplett
  verschluckt oder hoechstens als unformatierter Python-Traceback auf
  der Konsole sichtbar, nie als die eigentlich vorgesehene klare
  Fehlermeldung im Kamera-Fenster. Diese Einschraenkung besteht
  identisch auch beim unveraenderten, seit MK5 bestehenden
  `bambu_mjpeg_generator()` (A1-Kamera) - dort bisher nie aufgefallen,
  weil dieser Pfad in der Praxis zuverlaessig funktioniert.

  **Umsetzung (rein diagnostisch, keine weitere Protokoll-Vermutung):**
  - Neue Logzeile UNMITTELBAR vor `subprocess.Popen()`
    ("Starte FFmpeg-Prozess...") UND unmittelbar danach ("FFmpeg-Prozess
    gestartet (PID ...)") - damit naechstes Mal eindeutig erkennbar ist,
    ob der Start selbst haengt (nur die erste Zeile erscheint) oder
    FFmpeg zwar startet, aber danach nichts mehr liefert (beide Zeilen
    erscheinen, aber keine Daten/kein Fehler folgen).
  - `subprocess.Popen()` jetzt in einem eigenen `try/except`: ein
    Fehlschlagen beim Start (z. B. ungueltige/korrupte exe) wird jetzt
    MIT voller Fehlermeldung und dem verwendeten Pfad geloggt, der
    Generator endet danach sauber (keine Daten, kein Haengen) statt den
    Fehler unbehandelt zu werfen.
  - Die Lese-Schleife selbst steht jetzt ebenfalls in einem
    `try/except`, das jeden Fehler waehrend des Streamens klar loggt;
    zusaetzlich wird beim regulaeren Streamende der tatsaechliche
    FFmpeg-Exitcode mitgeloggt (haette in v2.2.22-24 sofort gezeigt,
    OB und mit welchem Code FFmpeg sich beendet, statt stillschweigend
    aufzuhoeren).

  **An den Nutzer:** bitte folgende drei Dinge pruefen/mitteilen, um
  zwischen den beiden oben genannten Erklaerungen zu unterscheiden,
  statt dass hier weiter geraten wird:
  1. Erscheint nach dieser Version MINDESTENS die Zeile "Starte
     FFmpeg-Prozess..." in der Konsole? Wenn selbst die fehlt, liegt das
     Problem bereits VOR `bambu_rtsp_mjpeg_generator()` (z. B. in der
     Drucker-Status-Abfrage) - bitte dann den GESAMTEN Konsolen-
     Ausschnitt (nicht nur nach "[MK6-FFMPEG]" gefiltert) schicken.
  2. Falls die Start-Zeile erscheint, aber "FFmpeg-Prozess gestartet
     (PID ...)" NICHT folgt (auch nach laengerem Warten): Verdacht (a)
     bestaetigt sich (Antivirus/Windows Defender blockiert/verzoegert
     den Prozessstart) - bitte den Windows-Sicherheitsverlauf (Windows-
     Sicherheit -> Viren- & Bedrohungsschutz -> Schutzverlauf) auf
     einen Eintrag zu `ffmpeg.exe` pruefen, und/oder `ffmpeg.exe` direkt
     per Doppelklick/Terminal im selben Ordner wie `DruckerDashboard.exe`
     manuell starten (z. B. `ffmpeg -version`), um zu sehen, ob das
     Betriebssystem/die Sicherheitssoftware dabei eingreift.
  3. Falls beide Zeilen erscheinen: der naechste Teil der Ausgabe (PID,
     ggf. `[MK6-FFMPEG]`-Fehlerzeilen von FFmpeg selbst, oder der
     Exitcode beim Streamende) zeigt dann hoffentlich die naechste
     Stufe des eigentlichen Problems.

  Getestet: `py_compile app.py`, `node --check`, Flask-Smoke-Test
  (Version 2.2.25); gezielte Tests fuer `bambu_rtsp_mjpeg_generator()`:
  ungueltiger FFmpeg-Pfad -> Popen-Fehler wird geloggt, Generator endet
  sofort (< 1ms) statt zu haengen/zu crashen; funktionierendes Fake-
  FFmpeg-Skript -> Start-/Ende-Logzeilen erscheinen korrekt, normaler
  Datenfluss unveraendert. Ein Test gegen echte Druckerhardware war in
  dieser Umgebung weiterhin nicht moeglich.

## v2.2.26 - RTSPS-Kamera: Ursache des schwarzen Bildes gefunden und behoben (browserinkompatibles mpjpeg-Format)

  Nach v2.2.25 (umfangreiche Diagnose-Protokollierung) hat der Nutzer in
  enger Zusammenarbeit eine Serie gezielter, isolierender Tests auf
  echter Hardware (X1E) durchgefuehrt, jeweils auf Anfrage und mit
  manuell per PowerShell ausgefuehrten FFmpeg-Kommandos, um die Ursache
  des "Kamera-Fenster bleibt dauerhaft schwarz, kein Fehler"-Problems
  einzugrenzen, ohne weiter zu raten:

  1. `-loglevel debug ... -f null -`: Verbindung (TLS/RTSP), SDP-
     Aushandlung und H.264-Decoding laufen vollstaendig fehlerfrei (88
     Frames, 0 Dekodierfehler) - widerlegt jede verbleibende Vermutung
     zu Verbindungs-/Protokollproblemen aus v2.2.22-24.
  2. Einzelbild per `-frames:v 1` als JPG gespeichert: einwandfrei, gut
     erkennbar (widerlegt die Hypothese "Kamera liefert nur ein
     schwarzes Bild, z. B. mangels Gehaeusebeleuchtung").
  3. Direkter URL-Aufruf von `/camera/<id>` in einem neuen Browser-Tab
     (Chrome UND Firefox, sowohl ueber das Dashboard als auch per
     direktem Pfad): durchgehend schwarz, keine Fehlermeldung - bei
     BEIDEN Browser-Engines identisch, was eine browserspezifische
     Einzel-Eigenart unwahrscheinlich macht.
  4. Fortlaufende Aufnahme als einzelne JPG-Dateien (kein mpjpeg-
     Container, `image2`-Muxer ueber Dateinamensmuster): alle 104
     erzeugten Bilder einwandfrei.
  5. Fortlaufende Aufnahme MIT `-f mpjpeg` in eine lokale Datei
     geschrieben (90 MB fuer ca. 10-15s, unauffaellige Groesse),
     anschliessend mit FFmpeg selbst wieder in Einzelbilder zerlegt:
     ebenfalls alle einwandfrei.
  6. Der tatsaechliche HTTP-Response des LAUFENDEN Flask-Servers wurde
     per `curl.exe --max-time 10 .../camera/<id> -o live_capture.bin`
     (am Browser vorbei) aufgezeichnet (27,9 MB), und ebenfalls wieder
     in Einzelbilder zerlegt: ebenfalls alle einwandfrei.

  Diese Tests grenzen die Ursache zweifelsfrei ein: Verbindung, RTSPS/
  TLS, H.264-Decoding, MJPEG-Encoding, FFmpegs eigenes `mpjpeg`-Muxing
  UND die Uebertragung durch den Flask-Server sind alle nachweislich
  fehlerfrei. Einzig die Interpretation des von FFmpeg per `-f mpjpeg`
  erzeugten Byte-Stroms durch den Browser selbst (fuer `<img>`-Tags mit
  `multipart/x-mixed-replace`) schlaegt fehl.

  **Root Cause (recherchiert im FFmpeg-Quellcode, nicht vermutet):**
  `libavformat/mpjpeg.c`
  (https://code.ffmpeg.org/Traneptora/FFmpeg/src/commit/afbc4d2dac0434f645bbce80d5a47e11e4d6d5fb/libavformat/mpjpeg.c)
  zeigt, dass der `mpjpeg`-Muxer pro Bild exakt folgendes schreibt:
  ```
  --ffserver\n
  Content-type: image/jpeg\n\n
  <JPEG-Rohdaten>
  \n--ffserver\n
  ```
  Auffaellig und ursaechlich: **kein** `Content-Length`-Header pro Bild,
  und als Zeilenende nur `\n` (LF) statt des fuer HTTP-/MIME-Multipart
  (RFC 2046) eigentlich vorgeschriebenen `\r\n` (CRLF). FFmpeg selbst
  erkennt beim erneuten Einlesen die Bildgrenzen trotzdem zuverlaessig,
  weil sein eigener Demuxer die binaeren JPEG-Start-/Endmarker direkt im
  Datenstrom sucht, unabhaengig von der Textformatierung der Boundary -
  das erklaert, warum die FFmpeg-eigenen Tests (2, 4, 5, 6 oben) alle
  erfolgreich waren. Der strikte Multipart-Parser von Chrome und Firefox
  fuer `<img src="...">` verlangt dagegen eine korrekt begrenzte
  Boundary-/Header-Struktur und kann die Bildgrenzen in diesem nicht
  standardkonformen Format offenbar nicht zuverlaessig erkennen - mit
  dem Ergebnis eines dauerhaft leeren/schwarzen Bildes ohne jede
  Fehlermeldung, exakt das beobachtete Verhalten.

  Bestaetigt wird diese Erklaerung zusaetzlich dadurch, dass die
  bereits bestehende, seit MK5 nachweislich funktionierende A1-Kamera
  (`bambu_mjpeg_generator()`) das Multipart-Format NICHT FFmpeg
  ueberlaesst, sondern selbst konstruiert: Boundary `--frame`, CRLF-
  Zeilenenden, expliziter `Content-Length`-Header pro Bild - also genau
  die Eigenschaften, die dem `mpjpeg`-Muxer fehlen.

  **Fix:** FFmpeg liefert jetzt nur noch rohe JPEG-Bilddaten ohne jedes
  Text-Wrapping (`-f image2pipe` statt `-f mpjpeg` in der Kommandozeile
  von `bambu_rtsp_mjpeg_generator()` - `image2pipe` ist ein regulaerer,
  dokumentierter FFmpeg-Standard-Muxer fuer die Bildausgabe als reiner
  Byte-Strom, kein Spezialfall). `bambu_rtsp_mjpeg_generator()` puffert
  den eingehenden Byte-Strom und trennt die einzelnen Bilder anhand der
  im JPEG-Format fest definierten binaeren Marker auf (nicht geraten,
  sondern Teil der offiziellen JPEG/JFIF-Spezifikation): SOI-Marker
  `0xFFD8` ("Start of Image") markiert den Bildanfang, EOI-Marker
  `0xFFD9` ("End of Image") das Bildende. Jedes so erkannte, vollstaen-
  dige Bild wird anschliessend exakt im selben Format wie bei
  `bambu_mjpeg_generator()` (A1-Kamera) neu verpackt: `--frame\r\n`,
  `Content-Type: image/jpeg\r\n`, `Content-Length: <n>\r\n\r\n`,
  Bilddaten, `\r\n`. Die `Response`-Mimetype in der `/camera/<printer_id>`-
  Route wurde entsprechend von `boundary=ffserver` auf `boundary=frame`
  angepasst. Ein Sicherheitslimit (`MAX_FRAME_BUFFER_BYTES = 10_000_000`)
  verhindert unbegrenztes Pufferwachstum, falls durch eine gestoerte
  Verbindung ein JPEG-Endmarker fehlen sollte.

  Getestet: `py_compile app.py`, `node --check`, Flask-Smoke-Test
  (Version 2.2.26); gezielter Unit-Test der neuen Marker-Parsing-Logik
  mit einem Fake-FFmpeg-Prozess, dessen Ausgabe absichtlich mitten in
  einem SOI-Marker auf mehrere Chunks aufgeteilt wird (simuliert
  realistisches FFmpeg-Leseverhalten mit `read(4096)`) - beide
  erzeugten Test-JPEGs werden korrekt erkannt, mit passendem
  `Content-Length` und korrekten `\r\n`-Grenzen; gezielter Flask-Test
  der `/camera/<printer_id>`-Route mit demselben Fake-Prozess bestaetigt
  Status 200, `Content-Type: multipart/x-mixed-replace; boundary=frame`
  und einen mit `--frame\r\n` beginnenden Response-Body. Ein Test gegen
  echte Druckerhardware/echten Browser war in dieser Umgebung weiterhin
  nicht moeglich - das naechste Feedback des Nutzers nach einem Test im
  Dashboard selbst steht noch aus.

  **Update (direkt im Anschluss):** Nutzer bestaetigte v2.2.26 auf
  echter Hardware (Kamera an X1C und H2S getestet, funktioniert) - der
  Fix ist damit auch auf echter Hardware/echtem Browser verifiziert.

## v2.2.27 - Python-Versionskompatibilitaet: PEP-604-Unions brechen auf aelterem Python (Linux/OpenWrt-Deployment)

  Beim Versuch, v2.2.26 zusaetzlich zur Windows-exe auch auf einem
  GL.iNet-Router (GL-MT2500 "Brume 2", OpenWrt 21.02-SNAPSHOT, direkter
  Start per `python3 app.py`, kein PyInstaller) zu aktualisieren, blieb
  die App nach einem Routerneustart komplett unerreichbar. Manueller
  Start im Vordergrund zeigte die eigentliche Ursache sofort:
  ```
  TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'
  ```
  in `PrintHistoryStore.__init__()` (Zeile `max_jobs_per_printer: int |
  None = ...`, eingefuehrt in v2.2.21 fuer die konfigurierbare
  Verlaufsgroesse). Root Cause (dokumentiertes Python-Sprachverhalten,
  nicht vermutet): die Kurzschreibweise `X | None` fuer Typ-Hinweise
  (PEP 604) wertet den `|`-Operator zwischen echten Typobjekten aus -
  das funktioniert nur ab Python 3.10, weil `type.__or__` erst seit
  dieser Version existiert. Funktionsannotationen werden beim Definieren
  der Funktion (hier: Klassenkoerper von `PrintHistoryStore`) sofort
  ausgewertet, daher scheiterte bereits der Import/Start des gesamten
  Moduls auf jedem Python vor 3.10 - nicht erst beim Aufruf der
  Funktion. Die bisherigen Windows-Builds (PyInstaller mit einer
  CI-seitig aktuellen Python-Version, siehe build-exe.yml) sowie die
  Entwicklungsumgebung hier liefen beide auf Python 3.10+, weshalb das
  bislang nirgends auffiel - das GL.iNet-Geraet ist der erste bekannte
  Einsatzort mit einem aelteren System-Python.

  Gesamte Codebasis nach allen `X | None`-Vorkommen durchsucht (Grep
  nach `\b(int|str|float|bool|bytes|dict|list)\s*\|\s*None\b` etc.):
  exakt zwei Fundstellen, beide aus v2.2.21 (`PrintHistoryStore.
  __init__()` und `_resolve_history_max_jobs()`). Keine weiteren
  Python-3.10+-spezifischen Konstrukte gefunden (z. B. kein
  `match`-Statement im Code).

  **Fix:** Beide Stellen auf `typing.Optional[...]` umgestellt (neuer
  Import `from typing import Optional`) - funktional identisch, aber
  seit Python 3.5 verfuegbar und damit kompatibel mit deutlich aelteren
  Python-Versionen, wie sie auf eingebetteten Linux-/Router-Systemen
  verbreitet sind.

  Getestet: `py_compile app.py`, `node --check`; `PrintHistoryStore`
  mit `None`, einem Integer und dem Standardwert instanziiert (alle
  drei funktionieren identisch zu vorher); `_resolve_history_max_jobs()`
  mit mehreren Werten aufgerufen; Flask-Smoke-Test (`/api/status`)
  erfolgreich. Ein Test mit einem echten Python-Interpreter vor 3.10 war
  in dieser Entwicklungsumgebung nicht moeglich (hier nur 3.10-3.13
  verfuegbar) - der Fix selbst (`typing.Optional` statt `X | None`) ist
  jedoch eine reine, allgemein bekannte Syntax-Rueckwaertskompatibilitaet
  ohne Verhaltensaenderung, keine Vermutung ueber unbekanntes Verhalten.
  Empfehlung an den Nutzer: nach der Aktualisierung auf dem Router
  `python3 --version` zu pruefen, um die tatsaechlich dort laufende
  Version zu kennen (README Abschnitt 1 jetzt entsprechend ergaenzt).

## v2.2.28 - Neue LINUX-INSTALL.md (reine Dokumentation, kein Code geaendert)

  Im direkten Anschluss an v2.2.27 wurde das GL.iNet-Dashboard (siehe
  dort) erfolgreich auf v2.2.26/27 aktualisiert, die Kamera funktionierte
  aber weiterhin nicht. Gemeinsame Fehlersuche per SSH/`logread` ergab
  zwei weitere, nacheinander aufgetretene und geloeste Probleme, die
  beide ueber den engeren Projektumfang hinaus allgemein relevant sind
  fuer jede Linux-/OpenWrt-Installation dieses Dashboards:

  1. **FFmpeg-Fehler "Option tls_verify not found"**: Das verwendete
     statische FFmpeg-Build (johnvansickle.com, Version 7.0.2) stammt
     von vor Mai/Juli 2025. Recherche in der FFmpeg-Entwicklerliste
     (https://ffmpeg.org/pipermail/ffmpeg-devel/2025-May/343202.html,
     Patch "avformat/rtsp: add TLS options") bestaetigt: Optionen wie
     `tls_verify` wurden fuer RTSPS-Verbindungen ueber den RTSP-Demuxer
     erst durch diesen Patch ueberhaupt nutzbar/durchgereicht - auf
     aelteren FFmpeg-Versionen schlaegt die Option daher mit genau
     dieser Meldung fehl, unabhaengig vom Rest der Konfiguration.
  2. **Danach `./ffmpeg: not found`, obwohl die Datei vorhanden war**:
     Das als Ersatz probierte Build von BtbN/FFmpeg-Builds (aktuelle
     FFmpeg-9.0-Linie, hat den obigen Patch) ist dynamisch gegen glibc
     gelinkt (bestaetigt per `grep -a 'ld-linux'` auf der Binaerdatei:
     eingebetteter Pfad `/lib/ld-linux-aarch64.so.1`). OpenWrt nutzt
     aber musl-libc und hat diesen Linker-Pfad nicht - der Kernel kann
     die Datei nicht laden, BusyBox' `ash` meldet das irrefuehrend als
     "not found". Geloest mit einem echten statischen Build von
     mwader/static-ffmpeg (https://github.com/wader/static-ffmpeg,
     laut eigener Dokumentation "hardened static PIE binaries with no
     external dependencies", ausdruecklich OpenWrt-tauglich), extrahiert
     aus dem Docker-Image `mwader/static-ffmpeg:9.0.2` auf einem
     Rechner mit Docker Desktop (siehe Mac-Testfall des Nutzers) und
     per `scp` auf den Router uebertragen - danach lief die Kamera auch
     auf diesem Geraet.

  Da beide Probleme (und ihre Loesungen) fuer jede kuenftige Linux-/
  OpenWrt-Installation dieses Dashboards erneut auftreten wuerden, hat
  der Nutzer gebeten, eine eigene Installationsanleitung nach diesem
  Vorbild dem Repository beizulegen. Neue Datei `LINUX-INSTALL.md`
  (Repository-Wurzel, neben README.md) dokumentiert: Voraussetzungen
  (Python-Version), Dateien uebertragen, manueller Testlauf, FFmpeg fuer
  musl-Systeme (inkl. des oben recherchierten Docker-Wegs mit genauem
  Dockerfile-Inhalt und Befehlen fuer macOS/Windows/Linux), ein
  generisches procd-Autostart-Skript (Standard-OpenWrt-Vorlage, keine
  druckerspezifische Vermutung) inkl. Hinweis, dass ein normaler
  Geraete-Neustart ohne aktiviertes (`enable`) Autostart-Skript die App
  NICHT automatisch wieder hochfaehrt (genau das urspruengliche Problem
  des Nutzers, das zu dieser gesamten Fehlersuche fuehrte), sowie eine
  Fehlerbehebungs-Tabelle mit allen in diesem und den vorherigen drei
  Versionen tatsaechlich aufgetretenen Fehlerbildern. README Abschnitt 1
  verweist jetzt auf diese neue Datei.

  Reine Dokumentationsaenderung, kein Code in `app.py` angefasst.
  Getestet: `py_compile app.py`, `node --check`, Flask-Smoke-Test
  (`/api/status`) - alle unveraendert erfolgreich, da keine
  Code-Aenderung vorliegt; `LINUX-INSTALL.md` manuell gegenkontrolliert
  gegen die tatsaechlichen, in diesem Chat mit dem Nutzer gemeinsam
  durchgefuehrten und bestaetigt erfolgreichen Schritte (kein
  erfundener Installationsweg).

## v2.3.0 - Bedien-/Einstellungsmodus, Raeume/Gruppen, frei konfigurierbare externe RTSP-Kameras, Drucker-/Raum-Reihenfolge

  Auf expliziten Nutzerwunsch umfangreiche, additive Erweiterung der
  Oberflaeche um eine klare Trennung zwischen taeglicher Bedienung und
  seltener Konfiguration - als MINOR (nicht PATCH) versioniert, da der
  Funktionsumfang entsprechend gross ist (ausdruecklicher Wunsch des
  Nutzers, siehe Kommentar bei `APP_VERSION`).

  **Config-Schema (additiv, mit Migration in `load_config()`):**
  - `"groups"`: Liste von Raeumen/Gruppen `{"id","name","order"}`.
  - `"rtsp_cameras"`: Liste frei konfigurierbarer, vom Drucker
    unabhaengiger RTSP(S)-Kameras `{"id","name","url","order"}`.
  - Jeder Drucker bekommt zusaetzlich `"group_id"` (Raum-Zuordnung,
    `None` = kein Raum) und `"order"` (Anzeige-Reihenfolge). Bestehende
    `config.json`-Dateien ohne diese Felder werden beim Laden defensiv
    ergaenzt (`group_id: None`, `order` anhand der bisherigen
    Listenreihenfolge) - keine manuelle Migration noetig, bestaetigt per
    Test mit einer vorher existierenden, aelteren `config.json`-Struktur.

  **Backend (`DashboardApp`, additive neue Methoden):** `get_groups()`/
  `add_group()`/`rename_group()`/`remove_group()`/`reorder_groups()`,
  `assign_printer_group()`/`reorder_printers()`, `get_rtsp_cameras()`/
  `add_rtsp_camera()`/`update_rtsp_camera()`/`remove_rtsp_camera()`,
  `get_settings()`/`update_history_max_jobs()` (macht `"history_max_jobs"`,
  bisher nur per Hand in `config.json` aenderbar, seit v2.3.0 ueber die
  Oberflaeche nutzbar - wirkt sofort auf den laufenden
  `PrintHistoryStore`, kein Neustart noetig, analog zu
  `update_extras_mqtt_settings()`). `remove_group()` loescht NIE Drucker,
  sondern setzt nur deren `group_id` zurueck - verhindert versehentlichen
  Datenverlust beim Aufraeumen von Raeumen.

  **Neue REST-Routen:** `GET/POST /api/groups`, `PUT/DELETE
  /api/groups/<id>`, `POST /api/groups/reorder`, `POST
  /api/printers/<id>/group`, `POST /api/printers/reorder`, `GET/POST
  /api/rtsp-cameras`, `PUT/DELETE /api/rtsp-cameras/<id>`, `GET
  /camera/rtsp/<id>` (Stream), `GET/PUT /api/settings`. Reorder-Routen
  validieren wie die bereits bestehende `/api/printers/<id>/queue/reorder`
  per Mengen-Vergleich (`sorted(ordered_ids) == sorted(vorhandene_ids)`),
  gleiche Fehlerbehandlung (409 bei Abweichung).

  **Kamera-Streaming fuer externe RTSP-Kameras**: NEUE, eigenstaendige
  Funktion `generic_rtsp_mjpeg_generator()` statt Umbau der bestehenden,
  auf echter X1E-/H2D-Pro-Hardware diagnostizierten und bestaetigt
  funktionierenden `bambu_rtsp_mjpeg_generator()` (siehe deren
  Kommentarblock, v2.2.22-26) - bewusste Entscheidung GEGEN eine
  Parametrisierung/Refactoring der bewiesenen Funktion, um deren
  Testabdeckung/Vertrauenswuerdigkeit nicht zu gefaehrden (additiv bleibt
  additiv, auch wenn das etwas FFmpeg-Kommandozeilen-/JPEG-Marker-Code
  verdoppelt). Fachlicher Unterschied: die URL kommt bereits vollstaendig
  vom Nutzer (kein zusammengebautes `rtsps://bblp:<code>@<ip>:322/...`),
  `-tls_verify 0` wird nur bei `rtsps://`-URLs gesetzt (bei reinem
  `rtsp://` nicht zutreffend). `_drain_ffmpeg_stderr()` wurde dafuer von
  einem festen `ip`-Parameter auf einen generischen `log_label`-String
  umgestellt (reine Beschriftungsaenderung der `[MK6-FFMPEG]`-Logzeilen,
  fuer den bestehenden Bambu-Pfad exakt gleicher Log-Text wie zuvor -
  manuell gegenkontrolliert).

  **Frontend:** neuer Umschalter "⚙ Einstellungen"/"← Zur Bedienung" oben
  im Kopfbereich. Bedien-Modus zeigt weiterhin alle bisherigen Karten-
  Funktionen (Kamera, Verlauf, Warteschlange, Drag & Drop, Temperaturen,
  AMS, Extras) sowie die Kartenlayout-Auswahl und neu eine "Kameras"-
  Schaltflaeche fuer die externen RTSP-Kameras (wiederverwendet dasselbe
  Anzeige-Modal wie die Drucker-Kamera, dafuer `openCam(id)` in
  `openCamUrl(url)` + duennen Wrapper aufgeteilt). Die "+ Drucker
  hinzufuegen"-Schaltflaeche, das "×"-Icon auf jeder Karte sowie der
  bisherige "MQTT-Sensoren"-Knopf wurden aus dem Bedien-Modus entfernt
  und sind nur noch im neuen Einstellungen-Bereich erreichbar (eigener
  Seitenbereich `#settingsPanel`, kein weiteres Modal - mehrere
  unabhaengige Listen gleichzeitig sichtbar erleichtert das Zuweisen von
  Druckern zu Raeumen). Raum-/Drucker-Umsortierung nutzt dieselben
  ▲/▼-Schaltflaechen (`.queue-order-btns`/`.btn-mini`) wie die bereits
  bestehende Warteschlangen-Umsortierung (`moveQueueEntry()`) - bewusste
  Wiederverwendung eines bereits funktionierenden, dem Nutzer vertrauten
  Bedienkonzepts statt Drag & Drop (deutlich weniger Fehleranfaelligkeit/
  Code als eine eigene Drag-&-Drop-Implementierung). Umbenennen von
  Raeumen/Bearbeiten von Kamera-Name+URL bewusst per `window.prompt()`
  gelost (kein zusaetzliches Modal noetig) - dabei WICHTIG: der aktuelle
  Name/die URL wird beim Aufruf aus der zuletzt geladenen Liste
  (`lastGroupList`/`lastCamsList`) nachgeschlagen, NICHT als String in
  das `onclick`-Attribut eingebettet - ein Name/eine URL mit
  Anfuehrungszeichen wuerde sonst das umgebende HTML-Attribut vorzeitig
  beenden (erst beim Schreiben bemerkt und korrigiert, bevor es zu einem
  echten Fehler wurde).

  Gruppierte Kartenanzeige: `main`/`#printerList` ist bereits ein
  CSS-Grid (`display:grid`, siehe bestehende `.cols-2`/`.cols-3`-Klassen
  fuer die Kartenlayout-Auswahl) - eine Raum-Ueberschrift als direktes
  Kind bekommt `grid-column:1/-1` (volle Breite), die zugehoerigen
  Drucker-Karten werden in einen Wrapper mit `display:contents` gepackt,
  damit sie weiterhin direkt als eigene Grid-Elemente von `main`
  behandelt werden (nicht als ein einziges grosses Element) - ohne
  Aenderung an der bestehenden Grid-/Spalten-Logik selbst. Ohne
  angelegte Raeume bleibt die Anzeige unveraendert eine flache, nach
  `order` sortierte Liste; leere Raeume werden im Bedien-Modus nicht
  angezeigt.

  Getestet: `py_compile app.py`; `node --check` auf dem extrahierten
  `<script>`-Block (Hinweis: die automatische Extraktion per regulaerem
  Ausdruck ab dem ERSTEN Vorkommen von "<script>" im Dateitext griff
  faelschlich auf eine Erwaehnung des Worts in einem Docstring-Kommentar
  weiter oben in `app.py` - korrigiert durch Suche ab dem LETZTEN
  Vorkommen von "<script>"); Flask-Test-Client-Smoke-Test deckt alle
  neuen Routen ab (Drucker/Raum/Kamera anlegen, umbenennen, zuweisen,
  umsortieren inkl. der 409-Fehlerfaelle bei inkonsistenter
  Reihenfolge, Raum loeschen mit Pruefung dass zugewiesene Drucker
  erhalten bleiben, RTSP-URL-Validierung, `history_max_jobs` inkl.
  Live-Uebernahme in den laufenden `PrintHistoryStore`) sowie die
  Config-Migration anhand einer manuell nachgebauten, aelteren
  `config.json`-Struktur ohne die neuen Felder.

## v2.4.0 - Externe RTSP-Kameras: eigene Anmeldung + Raum-Zuweisung, Kartenlayout 4-spaltig, Kameras als eigene Kachel statt gemeinsamem Knopf

  Direkter Nachfolger von v2.3.0, auf weiteren expliziten Nutzerwunsch:

  1. **Zugangsdaten fuer externe RTSP-Kameras**: bisher musste der Nutzer
     Zugangsdaten selbst als `rtsp://user:pass@host/pfad` in die URL
     einbauen - scheitert bei Sonderzeichen im Passwort (`@`, `:`, `/`
     u.ae. muessten nach RFC 3986 prozentkodiert werden, das kann vom
     Nutzer nicht erwartet werden). Jetzt zwei eigene Felder
     ("Benutzername"/"Passwort") in `config.json` (`"username"`,
     `"password"`, Klartext - konsistent mit allen anderen bereits
     vorhandenen Zugangsdaten dieses Programms wie Access Code, API-Keys
     etc., die ebenfalls unverschluesselt in `config.json` liegen; dieses
     Dashboard hat grundsaetzlich KEIN Authentifizierungs-/
     Berechtigungssystem, ist aber auch ausdruecklich nur fuer den
     Einsatz im eigenen, vertrauenswuerdigen LAN gedacht, siehe README
     einleitend). Neue Funktion `build_rtsp_url_with_auth(url, username,
     password)` baut die vollstaendige URL ERST unmittelbar vor dem
     FFmpeg-Aufruf zusammen (`urllib.parse.quote()` fuer die
     Prozentkodierung, IPv6-Hosts werden fuer die Netloc wieder in
     eckige Klammern gefasst, siehe RFC 3986 Abschnitt 3.2.2) - sind
     beide Felder leer, bleibt die URL unveraendert (deckt weiterhin
     Kameras ab, bei denen die Zugangsdaten wie vor v2.4.0 bereits in der
     URL stehen); sind sie gesetzt, ersetzen sie etwaige in der URL
     bereits enthaltene Zugangsdaten vollstaendig.

  2. **Kameras koennen jetzt Raeumen zugewiesen werden**, genau wie
     Drucker: `"group_id"` auf jedem `rtsp_cameras`-Eintrag,
     `assign_rtsp_camera_group()`/`POST /api/rtsp-cameras/<id>/group`
     (identisches Muster wie bei Druckern). `remove_group()` setzt jetzt
     korrekterweise auch die `group_id` betroffener KAMERAS zurueck, nicht
     nur die der Drucker - beim ersten Testlauf tatsaechlich vergessen
     und durch den Flask-Smoke-Test aufgefallen (Assertion schlug fehl,
     weil eine geloeschte Gruppe die Kamera-Zuordnung nicht aufraeumte),
     noch in dieser Version korrigiert.

  3. **Kein gemeinsamer "Kameras"-Knopf mehr**: der in v2.3.0 eingefuehrte
     Knopf samt Listen-Modal wurde wieder entfernt (ausdruecklicher
     Nutzerwunsch). Stattdessen erscheint jede externe Kamera als eigene,
     schlanke `.camera-card`-Kachel direkt im Grid (`cardForCamera()`),
     zusammen mit den Druckern nach Raum gruppiert (dieselbe
     `.room-group`/`display:contents`-Technik wie bei Druckern). Ohne
     Raum-Zuordnung erscheinen Kameras unter "Ohne Raum"; refresh() zeigt
     den "keine Drucker hinterlegt"-Hinweis jetzt nur noch, wenn AUCH
     keine Kameras vorhanden sind.

  4. **Kartenlayout 4-spaltig**: vierter Layout-Knopf, neue CSS-Klasse
     `main.cols-4` (zusaetzliche Media-Query-Stufe bei 1500px, damit vier
     Spalten auf kleineren Bildschirmen sauber auf drei/zwei reduzieren,
     analog zur bereits bestehenden Stufenlogik von `.cols-3`).

  **Frontend-Konsequenz aus Punkt 1+2**: das bisherige `window.prompt()`-
  basierte Bearbeiten einer Kamera reicht fuer vier Felder (Name, URL,
  Benutzername, Passwort) plus Raum-Auswahl nicht mehr aus - ersetzt
  durch ein einzelnes `#cameraModal` (wiederverwendet dieselbe
  `.modal`-Optik wie `#addModal`) fuer Anlegen UND Bearbeiten
  (`openCameraModal(camId)`, `camId` leer = Anlegen). Raum-Zuweisung
  laeuft beim Anlegen direkt ueber `group_id` im POST-Body (ein Request
  genuegt), beim Bearbeiten bewusst ueber den separaten
  `/group`-Endpunkt (wie bei Druckern) statt ueber PUT - verhindert ein
  versehentliches Leeren der Raum-Zuordnung, falls das PUT irgendwann
  ohne `group_id`-Feld aufgerufen wird.

  Getestet: `py_compile`; `node --check` auf dem (erneut ab dem LETZTEN
  "<script>"-Vorkommen extrahierten) Script-Block; `build_rtsp_url_with_
  auth()` direkt mit mehreren Faellen (ohne Zugangsdaten, nur Benutzername,
  Benutzername+Passwort mit Sonderzeichen `@`/`:`/`/`, Ersetzen bereits
  vorhandener URL-Zugangsdaten); Flask-Smoke-Test fuer Kamera-Anlegen mit
  Zugangsdaten+Raum, Raum-Zuweisung/-Aenderung/-Entfernung per eigener
  Route, Bearbeiten-Route laesst `group_id` unangetastet, sowie dass ein
  geloeschter Raum die Kamera-Zuordnung zuverlaessig aufraeumt (deckte den
  oben beschriebenen, noch in dieser Version behobenen Fehler auf);
  Config-Migration einer alten `rtsp_cameras`-Struktur ohne die neuen
  Felder (`username`/`password`/`group_id`); Index-Smoke-Test prueft,
  dass das alte Kameras-Modal/der Knopf nicht mehr im HTML vorkommen und
  die neuen Elemente (Kamera-Modal-Felder, 4. Layout-Knopf) vorhanden sind.

## v2.5.0 - Eigenstaendige MQTT-Sensoren/Schalter ohne Druckerzuordnung, "Speichern"-Knopf verschoben

  Direkter Nachfolger von v2.4.0, als Fehlerbehebung plus kleine
  UI-Korrektur gemeldet:

  1. **Fehler: MQTT-Sensor/-Schalter ohne Drucker liess sich nicht
     anlegen.** Ursache: die GESAMTE Extras-Datenstruktur war seit
     v2.2.15 zwingend an einen bestehenden Drucker gebunden
     (`printer_cfg["extras"]`, siehe `_get_extras_list(printer_id)` -
     lieferte `(None, None)`, wenn kein (oder noch kein) passender
     Drucker existierte). Im Frontend hatte `#mq_printer` kein "kein
     Drucker"-Feld, und `submitMqttExtra()` brach bei leerer Auswahl mit
     einer Fehlermeldung ab, OHNE ueberhaupt eine Anfrage zu senden -
     auch das Auswaehlen eines Topics aus "zuletzt empfangene Topics"
     half nichts, weil `useDiscoveredTopic()` nur das Topic-Feld setzt,
     nicht die Drucker-Pflichtauswahl umgeht.

     Behoben durch eine NEUE, separate Liste `"standalone_extras"` in
     `config.json` (additiv, parallel zu `printer_cfg["extras"]` - die
     druckergebundene Struktur bleibt vollstaendig unveraendert). Neue
     `DashboardApp`-Methoden `get_standalone_extras()`/
     `add_standalone_extra()`/`update_standalone_extra()`/
     `delete_standalone_extra()`/`assign_standalone_extra_group()`/
     `send_standalone_extra_command()` nutzen dieselbe
     `_validate_extra_fields()`-Validierung wie die druckergebundene
     Variante (keine Doppelung der Pflichtfeld-Regeln). Neue Routen:
     `GET/POST /api/standalone_extras`, `PUT/DELETE
     /api/standalone_extras/<id>`, `POST
     /api/standalone_extras/<id>/group`, `POST
     /api/standalone_extras/<id>/command`.

     Frontend: `#mq_printer` zeigt jetzt zusaetzlich die Option "Kein
     Drucker (eigenstaendig)" (leerer `value`,
     `populateMqttPrinterSelect()`). `submitMqttExtra()`/
     `deleteMqttExtra()`/`startEditMqttExtra()` pruefen jetzt, ob
     `printerId` gesetzt ist, und sprechen je nachdem die
     druckergebundene ODER die neue, eigenstaendige Route an - der
     fruehere Abbruch bei leerer Drucker-Auswahl (`if(!printerId){...
     return;}`) wurde dafuer ENTFERNT. `renderMqttExtrasList()` ist jetzt
     `async` (laedt `/api/standalone_extras` frisch, bevor die Liste neu
     aufgebaut wird) und zeigt eigenstaendige Eintraege zusaetzlich zu den
     druckergebundenen, mit "(kein Drucker)" statt eines Druckernamens.

     Eigenstaendige Sensoren/Schalter erscheinen im Bedien-Modus als
     eigene, schlanke Kachel (`cardForStandaloneExtra()`, optisch wie
     `.camera-card` aufgebaut - ein Sensor zeigt den aktuellen Wert, ein
     Schalter dieselben Ein/Aus-Knoepfe wie im druckergebundenen Fall,
     nur ueber den neuen `standaloneExtraCommand()`-Endpunkt). Sie sind,
     genau wie Drucker und externe Kameras, einem Raum zuweisbar
     (`group_id`-Feld, Dropdown direkt in der Eintragsliste des
     MQTT-Dialogs, `assignStandaloneExtraGroup()`) und werden in
     `refresh()` nach demselben `.room-group`-Muster einsortiert.
     `remove_group()` setzt beim Loeschen eines Raums jetzt auch die
     `group_id` betroffener eigenstaendiger Eintraege zurueck (analog zu
     Druckern/Kameras, nach demselben Muster wie der in v2.4.0 fuer
     Kameras behobene Fehler - hier von Anfang an mit beruecksichtigt).

  2. **"Speichern"-Knopf fuer den Druckverlauf verschoben**: sass bisher
     im "Druckverlauf"-Abschnitt des Einstellungen-Modus, direkt unter
     dem Eingabefeld fuer `history_max_jobs` - sah dadurch aus, als
     wuerde er (ausschliesslich) zu diesem Abschnitt gehoeren, obwohl er
     tatsaechlich die einzige Speichern-Aktion der gesamten
     Einstellungs-Seite war. Jetzt in der Kopfzeile des
     Einstellungen-Modus (`#settingsModeControls`), direkt neben
     "← Zur Bedienung" - `onclick="saveHistorySettings()"` und die
     Funktion selbst sind unveraendert, nur die Position im HTML wurde
     geaendert.

  Getestet: `py_compile`; `node --check` auf dem (ab dem letzten
  `<script>`-Vorkommen extrahierten) Script-Block; Flask-Smoke-Test fuer
  Anlegen (Sensor UND Schalter) ohne Drucker, Auflisten, Validierung
  (fehlendes Pflichtfeld -> 400), Bearbeiten, Raum-Zuweisung samt
  Zuruecksetzen beim Loeschen des Raums, Schalter-Kommando-Route,
  Loeschen (inkl. 404 bei unbekannter ID); Regressionstest, dass die
  druckergebundene Extras-Route (`POST /api/printers/<id>/extras`) sowie
  `/api/status` unveraendert funktionieren; Config-Migration einer alten
  `config.json` ohne den neuen Schluessel `"standalone_extras"` (wird
  defensiv mit `[]` ergaenzt, wie alle bisherigen additiven
  Config-Erweiterungen dieses Projekts).

## v2.5.1 - Verlaufsdiagramm fuer ALLE MQTT-Sensoren, MQTT-Bereich im Einstellungen-Modus jetzt inline

  Direkter Nachfolger von v2.5.0, zwei vom Nutzer gemeldete Punkte (beide
  ausdruecklich als PATCH eingestuft - reine Fehlerbehebungen/
  Anpassungen, kein neuer Funktionsumfang):

  1. **Alle Sensoren zeigen jetzt ein Verlaufsdiagramm.** Vorher bekam
     nur ein MQTT-Sensor mit `"display": "temperature"` oder
     `"humidity"` eine Sparkline (ueber `extraChip()`/`extraTempChips()`
     in der Temperaturen-Zeile) - ein Sensor mit `"display": "generic"`
     (Standard, Anzeige im Bereich "Sensoren & Schalter" unterhalb der
     Karte) zeigte nur den nackten Wert, ohne Verlauf. Behoben, OHNE die
     bestehende Trennung nach `display` anzutasten (die entscheidet
     weiterhin nur noch, WO ein Sensor angezeigt wird, nicht mehr OB er
     eine Sparkline bekommt):
     - `renderExtras()` (druckergebundene generische Sensoren)
       zeichnet jetzt bei numerischem Wert ebenfalls per
       `recordTempHistory()`/`sparklineSvg()` auf, unter demselben
       Feld-Namensraum `"extra_<id>"` wie `extraChip()` - ein Sensor, der
       zwischenzeitlich den Anzeigebereich wechselt, verliert seinen
       bisherigen Verlauf also nicht.
     - `cardForStandaloneExtra()` (eigenstaendige Sensoren, seit v2.5.0)
       zeichnet ebenso auf, unter einem eigenen Pseudo-Drucker-Schluessel
       `"__standalone__"` in `tempHistory` (verhindert Kollisionen mit
       druckergebundenen Extra-IDs, auch wenn zufaellig identisch).
     - Ein nicht-numerischer Sensorwert (Text) zeigt weiterhin KEIN
       Diagramm (technisch nicht sinnvoll), wie bei `extraChip()` schon
       bisher.

  2. **MQTT-Bereich im Einstellungen-Modus ist jetzt inline.** Vorher war
     "MQTT-Geraete (Sensoren/Schalter)" der einzige Abschnitt des
     Einstellungen-Modus, dessen GESAMTE Verwaltung (Broker-
     Einstellungen, Anlegen-Formular, Eintragsliste, zuletzt empfangene
     Topics) hinter einem einzelnen Knopf ("MQTT-Geraete verwalten") in
     einem grossen eigenen Modal steckte - "Drucker verwalten"/"Raeume/
     Gruppen"/"Externe RTSP-Kameras" zeigen ihre Verwaltungslisten dagegen
     alle direkt inline im Einstellungen-Bereich, mit allenfalls einem
     kleinen Modal NUR fuer das Anlegen/Bearbeiten eines einzelnen
     Eintrags (vgl. `#cameraModal`). Umgestellt auf dasselbe Muster:
     - Broker-Einstellungen (Felder `mq_enabled`/`mq_host`/.../`mq_tls`
       plus "Broker-Einstellungen speichern") sitzen jetzt direkt im
       "MQTT-Geraete"-Abschnitt, IDs unveraendert (nur die Position im
       HTML hat sich geaendert) - `saveExtrasMqttSettings()` zeigt Fehler
       jetzt per `showToast()` statt eines eigenen `#mqttError`-Felds
       (das sitzt jetzt im neuen, kleineren Anlegen/Bearbeiten-Modal),
       konsistent mit `createGroup()`/`deleteRtspCamera()` etc.
     - Die Eintragsliste (`mqttExtrasList`) sitzt ebenfalls direkt im
       Abschnitt, wird ueber die neue Funktion
       `refreshMqttSettingsSection()` mitgeladen, wenn
       `refreshSettingsPanel()` laeuft - genau wie
       `refreshPrinterManageList()`/`refreshGroupsManageList()`/
       `refreshCamerasManageList()`.
     - Anlegen/Bearbeiten eines EINZELNEN Sensors/Schalters passiert
       weiterhin in einem Modal (`#mqttExtraModal`, strukturell wie
       `#cameraModal`), geoeffnet ueber den neuen Knopf "+ Sensor/
       Schalter hinzufuegen" (`openAddMqttExtraModal()`) bzw. beim
       Bearbeiten ueber `startEditMqttExtra()` (oeffnet das Modal jetzt
       selbst, statt wie bisher nur Formularfelder in einem bereits
       offenen grossen Modal zu aendern). `closeMqttExtraModal()` ersetzt
       das alte `closeMqttModal()`; das bisherige Konzept "Bearbeiten
       abbrechen, Formular bleibt aber offen" (`cancelMqttExtraEdit()`,
       eigener Knopf `#mqttCancelEditBtn`) entfaellt zugunsten des
       einfacheren Camera-Modal-Musters ("Abbrechen" schliesst das Modal
       vollstaendig) - `resetMqttExtraForm()` bleibt als reiner
       Formular-Reset-Helfer bestehen.
     - `#mqttModal` (das alte, grosse Modal) wurde komplett entfernt;
       `openMqttModal()`/`closeMqttModal()`/`cancelMqttExtraEdit()`
       existieren nicht mehr.

  Getestet: `py_compile`; `node --check` auf dem (ab dem letzten
  `<script>`-Vorkommen extrahierten) Script-Block; Flask-Smoke-Test
  prueft, dass `index.html` das neue `#mqttExtraModal` enthaelt, `#mqttModal`
  NICHT mehr vorkommt und die neuen Funktionsnamen
  (`openAddMqttExtraModal`, `refreshMqttSettingsSection`) im ausgelieferten
  HTML vorhanden sind; Regressionstest fuer Anlegen/Abrufen/Loeschen eines
  eigenstaendigen Extras sowie `/api/status` (am reinen Frontend-/
  Darstellungs-Umbau in diesem Schritt hat sich backend-seitig nichts
  veraendert, Status-Routen unveraendert funktionsfaehig).

  **Versionierungs-Hinweis:** auf ausdruecklichen Nutzerwunsch werden
  bereits ausgelieferte Versionsnummern NICHT nachtraeglich geaendert
  (v2.5.0 bleibt v2.5.0). Da es sich bei den beiden Punkten dieses
  Eintrags um reine Fehlerbehebungen/Anpassungen handelt, wird
  ausschliesslich die letzte Versionsstelle erhoeht (v2.5.0 -> v2.5.1,
  PATCH) statt einer weiteren MINOR-Stufe.

## v2.5.2 - MQTT-Verbindungs-Logging ("[MK6-MQTT]"), Hinweis auf veraltete Temperaturwerte bei getrennter Verbindung

  Direkter Nachfolger von v2.5.1, Diagnose/Fix fuer einen vom Nutzer
  gemeldeten, zunaechst widerspruechlich wirkenden Fall: beim A1 mini
  bleibt der Status-Punkt dauerhaft rot, obwohl Kamera UND Temperatur-
  werte angezeigt werden - bei X1/H2-Druckern wird der Punkt dagegen
  gruen, sobald sie im WLAN angemeldet sind.

  **Diagnose (per Rueckfragen an den Nutzer eingegrenzt, nicht geraten):**
  Status bleibt dauerhaft (nicht nur kurzzeitig flackernd) rot, auch
  ohne gleichzeitig verbundenes Bambu Studio; die angezeigten Werte sind
  die normalen Duese-/Bett-/Kammer-Temperaturen (nicht die eigens per
  zweitem MQTT-Broker eingerichteten Extras) und aktualisieren sich
  NICHT mehr - es handelt sich also um eingefrorene alte Werte. Die
  Kamera liefert parallel ein echtes, bewegtes Livebild.

  Daraus liess sich der Mechanismus klar herleiten, OHNE das zugrunde
  liegende Netzwerk-/Konfigurationsproblem selbst zu erraten (dafuer
  fehlt der Zugriff auf den echten Drucker/die echte config.json):
  - Der Status-Punkt (`online = p.connected` im Frontend) spiegelt
    AUSSCHLIESSLICH `PrinterConnection.status["connected"]` wider -
    gesetzt einzig in `_on_connect()`(True bei `rc == 0`)/
    `_on_disconnect()`/dem Exception-Handler in `_connect_loop()`
    (jeweils False). Die Kamera (`bambu_rtsp_mjpeg_generator()`, Port
    6000/"LAN Only Liveview" bzw. bei der A1-Serie ganz ohne weitere
    Einstellung) ist eine VOELLIG unabhaengige Verbindung - ihr
    Funktionieren sagt nichts ueber die MQTT-Verbindung aus.
  - `_on_disconnect()` setzte bisher NUR `"connected"` zurueck, nicht
    aber `nozzle_temp`/`bed_temp`/`chamber_temp`/`progress`/etc. - diese
    blieben nach einem Verbindungsabbruch unveraendert stehen und sahen
    dadurch weiterhin wie aktuelle, live aktualisierte Werte aus, obwohl
    sie es nicht mehr waren. Das erklaert den gemeldeten Widerspruch
    vollstaendig, unabhaengig von der eigentlichen Account-/Netzwerk-
    Ursache beim A1 mini.
  - Die eigentliche Ursache, WARUM die MQTT-Verbindung beim A1 mini nie
    (auch nicht kurzzeitig) zustande kommt, liess sich aus der Ferne
    NICHT bestimmen - dafuer fehlte bisher jede Konsolen-Ausgabe: ein
    abgelehnter Verbindungsversuch (`_on_connect()` mit `rc != 0`, z. B.
    falscher Access Code/Seriennummer) und ein reiner Netzwerkfehler
    (Exception in `_connect_loop()`, z. B. Firewall/falscher Port) sahen
    fuer den Nutzer identisch aus (nur "rot"), obwohl die Ursachen und
    noetigen Korrekturen komplett unterschiedlich sind.

  **Fix (additiv, aendert kein Verbindungsverhalten, nur Sichtbarkeit):**
  - `_on_connect()` protokolliert jetzt IMMER (Erfolg und Ablehnung) mit
    Praefix `[MK6-MQTT]`, inkl. `mqtt.connack_string(rc)` fuer die vom
    MQTT-Protokoll vorgegebene Klartext-Bedeutung (z. B. "Connection
    Refused: not authorised" bei falschem Access Code/Seriennummer, vs.
    "Connection Accepted" bei Erfolg) - analog zum bestehenden
    `[MK6-FFMPEG]`-Praefix-Schema fuer die Kamera-Diagnose.
  - `_on_disconnect()` protokolliert einen unerwarteten Abbruch
    (`rc != 0`) ebenfalls mit diesem Praefix.
  - Der Exception-Handler in `_connect_loop()` (vorher: Fehler komplett
    verschluckt, nur `time.sleep(5)`) protokolliert jetzt die
    tatsaechliche Exception (`{e!r}`) - macht z. B. einen Verbindungs-
    Timeout oder ein abgelehntes TCP-Handshake sichtbar.
  - `renderBambuCard()` zeigt jetzt, wenn `!p.connected`, einen Hinweis
    direkt ueber den Temperaturwerten ("Nicht verbunden - die folgenden
    Werte sind die zuletzt bekannten ... KEINE Live-Daten mehr."),
    inklusive Zeitstempel aus `last_update`, statt die veralteten Werte
    kommentarlos wie aktuell aussehen zu lassen. Bewusst nur fuer die
    Bambu-Karte umgesetzt (dort gemeldet); dieselbe Technik liesse sich
    bei Bedarf auf OctoPrint/Creality/Ultimaker/Formlabs uebertragen.

  Getestet: `py_compile`; `node --check` auf dem (ab dem letzten
  `<script>`-Vorkommen extrahierten) Script-Block; isolierter Test von
  `_on_connect()`/`_on_disconnect()` gegen eine `PrinterConnection`-
  Instanz ohne echten Netzwerkzugriff (simulierte `rc`-Werte 0, 5, 7) -
  bestaetigt sowohl die korrekte `[MK6-MQTT]`-Konsolenausgabe (inkl.
  korrekt aufgeloestem Klartext "not authorised" fuer `rc=5`) als auch
  das weiterhin korrekte Setzen von `status["connected"]`;
  Flask-Smoke-Test bestaetigt den neuen Stale-Hinweis im ausgelieferten
  HTML sowie unveraendert funktionsfaehige `/api/status`-Route (reiner
  Logging-/Anzeige-Fix, keine Aenderung an Protokoll oder Datenmodell).

  **Offen:** die eigentliche Ursache des gemeldeten A1-Mini-Falls (ob
  falscher Access Code/Seriennummer, Firewall/Netzwerksegmentierung auf
  Port 8883, oder etwas anderes) ist damit noch nicht behoben, nur
  diagnostizierbar gemacht - Nutzer wurde gebeten, nach einem Neustart
  des Dashboards die `[MK6-MQTT]`-Zeilen fuer den A1 mini aus der
  Server-Konsole mitzuteilen, um gezielt weiterzumachen.

## v2.5.3 - Erweiterte MQTT-Diagnose: Standzeit bis Abbruch, Schritt-fuer-Schritt-Logging nach Connect

  Direkter Nachfolger von v2.5.2. Nutzer-Rueckmeldung (mit dem in v2.5.2
  eingefuehrten `[MK6-MQTT]`-Log, getestet mit v2.5.1 - dort noch ohne
  dieses Logging, daher zunaechst erneut mit v2.5.2 angefragt) fuer den
  A1 mini:

  ```
  [MK6-MQTT] (A1 Mini / 192.168.178.71): Verbindung erfolgreich (rc=0: Connection Accepted.)
  [MK6-MQTT] (A1 Mini / 192.168.178.71): Verbindung unerwartet getrennt (rc=7).
  ```

  **Einordnung (aus der MQTT-Client-Bibliothek, nicht geraten):** `rc=7`
  im `on_disconnect`-Callback von `paho-mqtt` ist der Bibliothekscode
  `MQTT_ERR_CONN_LOST` - ein unerwartet geschlossener Socket (z. B. TCP-
  Verbindungsabbruch), KEIN vom MQTT-Protokoll gesendeter Abmelde-Grund
  und KEIN `CONNACK`-Code wie bei `_on_connect()`. Die Verbindung wird
  also zunaechst angenommen, bricht dann aber von aussen (Netzwerk oder
  Drucker-Firmware) wieder ab - der genaue Ausloeser (sofort nach einer
  bestimmten Aktion dieses Dashboards, oder erst nach Ablauf des
  Keepalive-Intervalls von 30s) ließ sich aus dieser einen Logzeile noch
  nicht bestimmen, da bisher nur Connect und Disconnect, nicht aber die
  dazwischenliegenden Schritte (Subscribe auf "report"-/"request"-Topic,
  Senden der "pushall"-Anfrage) protokolliert wurden. Bewusst KEINE
  Spekulation ueber eine A1-mini-spezifische Firmware-Eigenart ohne
  weitere Daten - stattdessen genauere Protokollierung ergaenzt.

  **Fix (additiv, rein diagnostisch, aendert kein Verbindungsverhalten):**
  - `_on_connect()` protokolliert jetzt zusaetzlich jeden einzelnen
    Schritt nach einer erfolgreichen Verbindung: Abo des "report"-Topics,
    Abo des "request"-Topics, Senden der "pushall"-Anfrage.
  - Der Zeitpunkt der erfolgreichen Verbindung wird in
    `self._connected_at` gemerkt.
  - `_on_disconnect()` gibt bei einem unerwarteten Abbruch (`rc != 0`)
    jetzt zusaetzlich die Standzeit seit dem letzten erfolgreichen
    Connect aus (`time.time() - self._connected_at`).

  Damit laesst sich beim naechsten Reproduzieren ablesen, ob der Abbruch
  z. B. "0.1s" nach dem Connect (= direkt durch eine der drei Aktionen
  ausgeloest) oder erst nach rund 30s (= Keepalive-Problem, z. B. PINGREQ
  wird vom A1 mini nicht wie erwartet beantwortet) erfolgt.

  Getestet: `py_compile`; `node --check` auf dem extrahierten Script-
  Block; isolierter Test von `_on_connect()`/`_on_disconnect()` mit einem
  `FakeClient` (ohne echten Netzwerkzugriff) fuer die Faelle
  "Connect rc=0 dann Disconnect rc=7 nach ~0.3s" (bestaetigt korrekte
  Standzeit-Ausgabe "0.3s" und alle drei Schritt-Logzeilen in der
  richtigen Reihenfolge), "Connect rc=5" (abgelehnt, keine Schritt-Logs)
  und "Connect rc=0 dann Disconnect rc=0" (regulaer, keine Abbruch-
  Logzeile) - alle Assertions bestanden; Flask-Smoke-Test (`/`,
  `/api/status`) weiterhin unveraendert funktionsfaehig.

  **Offen (unveraendert):** die eigentliche Ursache des Abbruchs selbst
  ist weiterhin nicht bekannt - Nutzer wurde gebeten, mit dieser Version
  erneut zu reproduzieren und die vollstaendigen `[MK6-MQTT]`-Zeilen
  (inkl. Standzeit) fuer den A1 mini mitzuteilen.

## v2.5.4 - Experiment: Abo des "request"-Topics fuer A1-Drucker probeweise ausgesetzt

  Direkter Nachfolger von v2.5.3. Nutzer-Rueckmeldung mit v2.5.3 (zweimal
  reproduziert):

  ```
  [MK6-MQTT] (A1 Mini / 192.168.178.71): Verbindung erfolgreich (rc=0: Connection Accepted.)
  [MK6-MQTT] (A1 Mini / 192.168.178.71): Topic 'device/0309DA3B0700815/report' abonniert.
  [MK6-MQTT] (A1 Mini / 192.168.178.71): Topic 'device/0309DA3B0700815/request' abonniert.
  [MK6-MQTT] (A1 Mini / 192.168.178.71): 'pushall'-Anfrage gesendet.
  [MK6-MQTT] (A1 Mini / 192.168.178.71): Verbindung unerwartet getrennt (rc=7), Standzeit seit Connect: 0.0s.
  ```

  **Einordnung:** Standzeit "0.0s" schliesst ein Keepalive-/Timeout-
  Problem (haette erst nach ca. 30s auftreten muessen) aus - der Abbruch
  erfolgt stattdessen unmittelbar im Anschluss an die drei Aktionen nach
  dem Connect (Abo "report"-Topic, Abo "request"-Topic, "pushall"-
  Anfrage). WICHTIG: da `_on_connect()` diese drei Aktionen synchron
  ausfuehrt, bevor der Disconnect ueberhaupt verarbeitet werden kann,
  belegt die Logreihenfolge allein NICHT, dass die "pushall"-Anfrage (die
  letzte Aktion) die Ursache ist - jede der drei Aktionen, oder auch der
  CONNACK-Handshake selbst, kommt infrage. Es gibt KEINEN Zugriff auf die
  A1-Firmware-Dokumentation, um das sicher zu bestimmen.

  **Entscheidung fuer einen kontrollierten Test statt weiterer Spekulation:**
  Von den drei Aktionen ist das Abo des "request"-Topics die einzige rein
  diagnostische (siehe UEBERGABE.md v2.2.20: dient nur dem Mitlesen
  fremder `project_file`-Kommandos zur AMS-HT-Mapping-Analyse) - weder
  das "report"-Topic-Abo noch die "pushall"-Anfrage koennen ohne
  Funktionsverlust (keine Statuswerte mehr) entfallen. Es ist daher die
  einzige der drei Aktionen, die sich risikofrei probeweise aussetzen
  laesst, um sie als Ursache ein- oder auszugrenzen.

  **Fix/Experiment (reversibel, nur fuer `bambu_family == "a1"`):**
  - `_on_connect()` ueberspringt fuer A1-Drucker das Abo des eigenen
    "request"-Topics; `self._request_topic` bleibt in diesem Fall
    ungesetzt (von `_on_message()` ueber `getattr(..., None)` bereits
    abgesichert, keine Anpassung dort noetig).
  - Eine neue `[MK6-MQTT]`-Logzeile macht das Ueberspringen sichtbar.
  - "report"-Topic-Abo und "pushall"-Anfrage bleiben fuer A1-Drucker
    unveraendert bestehen - nur das diagnostische Mitlesen fremder
    Druckstart-Kommandos (praktisch relevant nur fuer AMS-HT-Mapping-
    Analyse, siehe v2.2.20) waere bei A1-Druckern dann nicht mehr
    verfuegbar, falls sich die Vermutung bestaetigt.
  - X1/P1/H2 (alle `bambu_family != "a1"`) sind unveraendert, da fuer
    diese laut Nutzer kein Problem gemeldet wurde.

  Getestet: `py_compile`; `node --check` auf dem extrahierten Script-
  Block; isolierter Test mit einem `FakeClient` fuer `bambu_family="a1"`
  (bestaetigt: nur "report"-Topic abonniert, "pushall" trotzdem gesendet,
  `_request_topic` bleibt `None`) und `bambu_family="x1"` (bestaetigt:
  Verhalten unveraendert, beide Topics abonniert); zusaetzlich bestaetigt,
  dass `_on_message()` fuer einen Report auf einem A1-Drucker ohne
  gesetztes `_request_topic` fehlerfrei durchlaeuft; Flask-Smoke-Test
  (`/`, `/api/status`) weiterhin unveraendert funktionsfaehig.

  **Ergebnis des Experiments: siehe v2.5.5 - bestaetigt.**

## v2.5.5 - A1-Verbindungsabbruch bestaetigt behoben, Firmware als Ursache ausgeschlossen

  Direkter Nachfolger von v2.5.4. Nutzer-Rueckmeldung:
  - Vergleichstest mit der deutlich aelteren v2.2.19 (vor Einfuehrung des
    "request"-Topic-Abos in v2.2.20) funktioniert beim A1 mini
    einwandfrei -> bestaetigt, dass die Drucker-Firmware selbst in
    Ordnung ist und das Problem ausschliesslich im Dashboard-seitigen
    MQTT-Client lag.
  - Mit v2.5.4 (Abo des "request"-Topics fuer A1-Drucker ausgesetzt)
    haelt die Verbindung zum A1 mini jetzt dauerhaft - sowohl im Test als
    auch im Produktivbetrieb bestaetigt.

  Damit ist der in v2.5.2 erstmals gemeldete Fall ("Status-Punkt bleibt
  bei A1 mini dauerhaft rot") vollstaendig aufgeklaert und behoben:
  - Grundursache: das seit v2.2.20 zusaetzlich zum "report"-Topic
    abonnierte eigene "request"-Topic (rein diagnostisch, fuer das
    Mitlesen fremder `project_file`-Kommandos zur AMS-HT-Mapping-
    Analyse) fuehrte beim A1 mini unmittelbar nach dem Connect zu einem
    von der Drucker-Firmware (oder deren eingebettetem Broker)
    ausgeloesten Verbindungsabbruch (`rc=7`/`MQTT_ERR_CONN_LOST`,
    Standzeit 0,0s) - X1/H2 sind davon nicht betroffen.
  - Die genaue firmwareseitige Ursache (z. B. ob die A1-Serie eine andere
    Broker-Implementierung nutzt, die ein Abo des eigenen "request"-
    Topics durch einen Client nicht toleriert) bleibt mangels Zugriff auf
    die A1-Firmware-Dokumentation unbekannt - fuer die Loesung war das
    nicht erforderlich, da das Abo ohnehin nur diagnostischen, keinen
    betrieblichen Zweck hatte.

  **Aenderung in diesem Schritt:** keine Code-Aenderung (die Logik aus
  v2.5.4 bleibt unveraendert) - lediglich Kommentare in `app.py`, die
  `[MK6-MQTT]`-Logzeile beim Ueberspringen des Subscribes sowie README
  und dieser Eintrag wurden von "Experiment"/"probeweise"/"nicht
  bestaetigt" auf einen bestaetigten, dauerhaften Fix aktualisiert.

  Getestet: `py_compile`; `node --check` auf dem extrahierten Script-
  Block; derselbe `FakeClient`-Regressionstest wie in v2.5.4 (A1: nur
  "report"-Topic abonniert, X1: beide Topics abonniert) erneut
  bestaetigt nach der Kommentaraenderung; Flask-Smoke-Test (`/`,
  `/api/status`) weiterhin unveraendert funktionsfaehig.

  **Fuer A1-Drucker weiterhin bewusst nicht verfuegbar:** die
  Mitprotokollierung fremder `project_file`-Druckstart-Kommandos (siehe
  `_log_foreign_project_file_command()`, v2.2.20) - relevant nur fuer die
  Analyse des `ams_mapping`-Formats von AMS-HT-Faechern bei gleichzeitig
  verbundenem Bambu Studio/Handy; alle anderen Funktionen (Status,
  Temperaturen, Fortschritt, Kamera, Drucksteuerung) sind fuer A1-Drucker
  unveraendert vollstaendig nutzbar.

## v2.5.6 - Sparkline-Farbe eigenstaendiger Luftfeuchte-Sensoren korrigiert

  Auf ausdruecklichen Nutzerwunsch: "Luftfeuchtigkeits Diagramme sollen
  immer blau sein auch wenn sie keinem Drucker zugeordnet sind".

  **Ursache:** `extraChip()` (druckergebundene Sensoren mit "display":
  "temperature"/"humidity", siehe v2.2.16/v2.5.1) waehlt die Sparkline-
  Klasse bereits korrekt anhand von `extra.display` (`humidity-spark` =
  blau vs. `temp-spark` = rot). `cardForStandaloneExtra()` (eigenstaendige
  Sensoren, seit v2.5.0, mit Verlaufsdiagramm seit v2.5.1) rief
  `sparklineSvg(history)` dagegen OHNE zweites Argument auf - `cssClass`
  faellt in `sparklineSvg()` dann auf den Default `'temp-spark'` (rot)
  zurueck, unabhaengig vom tatsaechlichen `display`-Feld des Sensors.
  `_validate_extra_fields()` setzt dieses Feld fuer druckergebundene UND
  eigenstaendige Sensoren identisch, das Frontend hat die Unterscheidung
  beim eigenstaendigen Fall schlicht nicht ausgewertet.

  **Fix (additiv, nur dieser eine Fall):** `cardForStandaloneExtra()`
  bestimmt `sparkClass` jetzt genau wie `extraChip()`
  (`e.display === 'humidity' ? 'humidity-spark' : 'temp-spark'`) und
  reicht sie an `sparklineSvg()` weiter. Druckergebundene Sensoren
  (bereits korrekt) sowie generische (nicht temperature/humidity)
  eigenstaendige Sensoren (weiterhin rot, da fuer sie keine andere Farbe
  gefordert war) sind unveraendert.

  Getestet: `py_compile`; `node --check` auf dem extrahierten Script-
  Block; per Regex gegen den extrahierten Script-Block bestaetigt, dass
  `cardForStandaloneExtra()` jetzt `sparkClass` nach `e.display` waehlt
  und an `sparklineSvg(history, sparkClass)` uebergibt; Flask-Smoke-Test
  (`/`, `/api/status`) weiterhin unveraendert funktionsfaehig.

**Regel für die Weiterarbeit (unveraendert seit MK5): bei jeder
ausgelieferten Änderung `APP_VERSION` in `app.py` erhöhen (semantisch:
MAJOR.MINOR.PATCH — siehe README, Abschnitt 0a) und einen passenden
Commit-Text mitliefern.**

<details>
<summary>Vollstaendige MK5-Versionshistorie (v1.1.0-v1.6.8, vor MK6) - zum Aufklappen</summary>

- Frühere Version (MK5, v1.6.8): (v1.1.0: Drag-&-Drop-Druckfeature,
  macOS-Build, Versionierung selbst. v1.2.0: AMS-Zuordnung als
  bestätigbarer Dialog statt Sofort-Druck. v1.3.0: Dialog zeigt nur noch
  die für den jeweiligen Druck tatsächlich benötigten Filamente
  [`slice_info.config`-Auswertung statt kompletter Projekt-Filamentliste],
  klare "Vorschlag vs. anderes Material"-Auswahl pro Filament. v1.3.1:
  FTPS-Datenverbindung ohne TLS-Session-Resumption + stufenspezifische
  Fehlermeldungen, da der `EOF occurred in violation of protocol`-Fehler
  trotz der Massnahmen aus v1.2.0 weiterhin reproduzierbar beim
  eigentlichen Datei-Upload auftrat. v1.3.2: Hex-Farbcode zusätzlich als
  Text im AMS-Dialog; großzügigerer Timeout + Byte-Fortschritt in der
  Fehlermeldung für die FTPS-Datenverbindung, nachdem Nutzer-Feedback
  bestätigte, dass der Fehler konkret während der laufenden Übertragung
  auftritt, nicht beim Verbindungsaufbau. v1.4.0: Farbe wird als Wort
  statt Hex-Code angezeigt; echter Fortschrittsbalken mit Prozent- und
  Byte-Anzeige beim Senden [asynchroner Confirm-Ablauf mit Polling];
  FTPS-Upload gedrosselt [Pause pro Block], nachdem zwei Versuche exakt
  beim selben Byte-Stand abbrachen — deutliches Indiz für einen
  druckerseitigen Pufferüberlauf statt Netzwerk-Flakiness. v1.4.1:
  Diese Theorie widerlegt (ein Versuch nach Drosselung brach noch
  früher/anders ab) - Fehlermeldung zeigt jetzt alle 3 Retry-Versuche
  einzeln statt nur den letzten, für bessere Diagnose. v1.4.2: Diese
  Diagnose zeigte perfekt reproduzierbare Abbrüche bei exakt 8192 Bytes
  über alle 3 Versuche — Review ergab einen konkreten fehlenden
  FTP-Protokollschritt (`TYPE I`, Binärmodus-Umschaltung), der beim
  Umbau in v1.3.1 versehentlich verlorengegangen war; jetzt ergänzt.
  v1.4.3: `TYPE I` hat den Fehler NICHT behoben (weiterhin exakt 8192
  Bytes) — Rückfrage beim Nutzer ergab TLS-inspizierende Antivirus-
  Software + verwaltetes Firmennetzwerk, Vermutung TLS-Inspektion als
  Ursache (spaeter widerlegt). v1.4.4: FileZilla-Vergleichstest bewies
  das Gegenteil — FileZilla überträgt dieselbe Datei im selben Netzwerk
  problemlos. Upload auf `ftp.storbinary()` zurückgebaut (statt der
  seit v1.3.1 manuellen Sende-Schleife) — reichte allein aber nicht,
  Fehler trat weiterhin bei festem Blockgrößen-Vielfachen auf. v1.4.5:
  zweite übersehene Abweichung gefunden — `ImplicitFtpTls` hatte
  weiterhin eine `ntransfercmd()`-Überschreibung ohne TLS-Session-
  Wiederverwendung (seit v1.3.1) und `_ftps_upload_once()` erzwang
  weiterhin TLS-Version 1.2 (seit v1.2.0), beides unbestätigte
  Altlasten. Beides entfernt — Upload-Pfad besteht jetzt nur noch aus
  dem für implizites TLS zwingend nötigen Minimum + Standard-`ftplib`-
  Verhalten, keine weiteren spekulativen Anpassungen mehr vorhanden.
  Bestätigung durch Nutzer stand zum Zeitpunkt dieser Übergabe noch aus.
  v1.4.6: Fehler trat auf dem X1C danach erneut exakt beim selben
  Byte-Wert auf wie vor v1.4.5 — zeigt, dass die dort entfernten
  Overrides gar nicht die Ursache waren. FTPS-Upload komplett auf einen
  `curl`-Unterprozess umgestellt statt Pythons `ftplib`/`ssl` zu nutzen
  [curl = von Python unabhängige TLS-Bibliothek, vorinstalliert auf
  Windows/macOS/Linux]. **Wichtige Präzisierung nach Auslieferung:**
  Nutzer-Feedback ergab, dass v1.4.5 [reiner Python-Code] auf einem A1
  Mini erfolgreich übertragen hatte, während derselbe Code auf dem X1C
  weiterhin scheiterte — das Problem ist also vermutlich X1C-spezifisch
  [Firmware-Eigenheit], nicht ein grundsätzliches Python/TLS-Problem.
  Ob curl [v1.4.6] das X1C-Problem tatsächlich löst, stand zum
  Zeitpunkt dieser Übergabe noch aus — siehe Abschnitt 7 für die
  offenen Fragen und nächsten Schritte. v1.4.7: Antwort kam — curl
  scheiterte ebenfalls, UND zwar auf X1C UND X1E [nicht nur X1C]. Damit
  eindeutig bestätigt: X1-Serie-spezifisches Problem, betrifft sowohl
  Python `ssl` als auch curl. Verbose-Logging [`--verbose`] ergänzt für
  echte TLS-Diagnose statt nacktem Exit-Code; `--tlsv1.2 --tls-max 1.2`
  als neues Experiment über curls Schannel-Backend [anderer Code-Pfad
  als der bereits gescheiterte Python/OpenSSL-Versuch]. Ergebnis stand
  zum Zeitpunkt dieser Übergabe noch aus. v1.4.8: reiner Build-Fix, kein
  Verhaltensunterschied — GitHub-Actions-macOS-Build schlug fehl
  [`SyntaxError: f-string expression part cannot include a backslash`],
  da der Runner mit Python 3.11 baut, während lokal mit 3.12 entwickelt
  wurde [dort seit PEP 701 erlaubt]. Betroffene Stelle in der
  curl-Fehlermeldungs-Konstruktion behoben, String-Teil vor dem
  f-string separat zusammengebaut. v1.4.9: curl-Ansatz wieder verworfen
  — curl (Schannel) scheiterte auf X1C/X1E identisch zu Python zuvor,
  brachte also keinen Vorteil bei zusätzlicher externer Abhängigkeit.
  Rückbau auf den einfacheren Python-`ftplib`-Ansatz [Stand v1.4.5],
  der nachweislich für einen Teil der Druckerflotte [A1 Mini]
  funktioniert. v1.5.0: Grundursache per Recherche vermutet — X1-Serie
  läuft auf vsftpd mit `require_ssl_reuse`, Pythons `storbinary()`
  verletze das durch ein abschließendes `unwrap()` [`_storbinary_no_unwrap()`
  als Fix] — **stellte sich als falsche Fährte heraus, änderte beim
  echten Test nichts**. v1.5.1: Prozess-Isolation des Uploads
  [Sentinel-Parameter `--ftps-upload-worker`] als Fix für eine vermutete
  Thread-/GIL-Konkurrenz mit dem MQTT-Hintergrundthread — **ebenfalls
  eine falsche Fährte**, scheiterte beim echten Test auf X1C identisch
  erneut. v1.5.2: vermutete gleichzeitige MQTT+FTPS-Verbindung als
  Ursache [Fix: `pause_mqtt()`/`resume_mqtt()`/`wait_for_mqtt_reconnect()`]
  — **ebenfalls eine falsche Fährte**, scheiterte beim echten Test
  erneut identisch (73728 Bytes). v1.5.3: vermutete Ursache — das
  Dashboard rief sich bis dahin selbst mit einem versteckten
  Kommandozeilen-Argument neu auf, was Windows Defender ähnlich wie
  manche Schadsoftware-Lademechanismen behandeln könnte. Fix: separate,
  eigenständig mitgelieferte Hilfsanwendung
  [`FtpsUploadHelper.exe`/`ftps_upload_helper.py`] statt Selbstaufruf —
  **ebenfalls eine falsche Fährte**: scheiterte beim Test sogar bei
  komplett eigenständigem Aufruf (Dashboard geschlossen) identisch.
  v1.5.4: tatsächliche, per direktem Code-Vergleich mit dem
  funktionierenden Referenzskript bestätigte Ursache — `ntransfercmd()`
  in `ImplicitFtpTls` übergab seit v1.4.5 kein `session=self.sock.session`
  mehr, basierend auf einer nie verifizierten Annahme über Pythons
  Standardverhalten (per `inspect.getsource()` widerlegt: die eingebaute
  Methode macht das nicht automatisch). Die ursprüngliche vsftpd-Diagnose
  aus v1.5.0 war die ganze Zeit inhaltlich richtig, nur unvollständig
  umgesetzt. Fix: `ntransfercmd()`-Override mit `session=self.sock.session`
  in `app.py` UND `ftps_upload_helper.py` wieder ergänzt — entspricht
  jetzt Zeile für Zeile dem vom Nutzer verifizierten Referenzcode. **Vom
  Nutzer bestätigt: mehrere PLA-Drucke auf X1C und X1E ohne Probleme.**
  v1.5.5: neues, unabhängiges Problem gemeldet — ASA-CF-Drucke blieben
  beim Materialladen hängen (PLA nicht betroffen). Ursache vermutet: zu
  lockere Teilstring-Typprüfung in `_find_matching_tray()` akzeptierte
  "ASA" als Teilmenge von "ASA-CF" (analog für alle Verbundwerkstoffe).
  Fix: neue Funktion `_types_compatible()` — **bestätigte sich beim
  Nutzer-Test als NICHT die Ursache dieses konkreten Falls** (Zuordnung
  war schon vorher korrekt), Fix bleibt aber für den allgemeinen Fall
  sinnvoll. v1.5.6: tatsächliche Ursache gefunden — das gesendete
  `project_file`-MQTT-Kommando fehlte mehrere von Bambu Studio selbst
  gesendete Felder, allen voran `bed_type`, was bei anspruchsvolleren
  Materialien wie ASA-CF (hohe Bett-/Düsentemperatur) zu einem
  Hängenbleiben beim Materialladen führen kann. Fix: vollständiger
  Feldsatz ergänzt [`bed_type: "auto"`, `subtask_name`, `project_id`/
  `profile_id`/`task_id`]. **Vom Nutzer bestätigt: X1C und X1E
  übertragen und starten Drucke jetzt zuverlässig.** v1.5.7: dabei
  aufgedeckter Zielkonflikt — der A1 Mini (fkt. vor v1.5.4 einwandfrei)
  scheiterte neu mit einem neuen Fehlerbild [Timeout nach 100%
  übertragenen Bytes]. Vermutete Ursache: TLS-Session-Wiederverwendung.
  Fix: `reuse_session`-Parameter, Alternierung über die 3 Versuche
  [mit/ohne/mit] — **beim Nutzer-Test scheiterten aber ALLE 3 Versuche
  identisch, auch ohne Sitzungs-Wiederverwendung: v1.5.7 war
  unvollständig.** v1.5.8: zweiter, übersehener Unterschied zu v1.4.5
  gefunden — der seit v1.5.0 immer aktive TLS-1.2-Deckel. Fix: zwei
  vollständige, benannte Profile ("x1": TLS-1.2 + Session-Reuse; "a1":
  freie TLS-Aushandlung ohne Session-Reuse, exakt v1.4.5-Verhalten)
  statt eines Einzelschalters, Alternierung zwischen beiden über die 3
  Versuche — **beim Nutzer-Test scheiterte auch Profil "a1" identisch:
  v1.5.8 ebenfalls unvollständig.** v1.5.9: Nutzer testete Profil "a1"
  komplett eigenständig [Dashboard geschlossen] — derselbe Timeout trat
  SELBST DANN auf, was TLS UND Dashboard-Kontext beide endgültig
  ausschloss. Vermutete Ursache: schlicht ein zu kurzes Zeitlimit
  [25 Sekunden]. Fix: Zeitlimit auf 120 Sekunden angehoben
  [`ftp.connect(ip, 990, timeout=120)`] — **beim Nutzer-Test besteht der
  Fehler WEITERHIN: v1.5.9 ebenfalls nicht bestätigt erfolgreich, vierter
  Anlauf für den A1-Mini-Fall bleibt offen**. v1.5.10:
  separates, neu gemeldetes Problem — Mehrfarb-Druck auf X1C blieb beim
  Aufheizen des Druckbetts hängen [Einzelfarb-Drucke funktionieren
  weiterhin]. Direkter Start am Display bewies: Datei/AMS-Zuordnung
  korrekt, Ursache im MQTT-Kommando. Fund: `flow_cali` war fest auf
  `False` gesetzt, Referenzbibliothek `bambulabs_api` nutzt standardmäßig
  `True`. Fix: `flow_cali` auf `True` geändert. Eine Alternativtheorie
  [`ams_mapping` müsse immer 4 Elemente haben] wurde durch
  `bambulabs_api`s Dokumentation widerlegt und nicht verfolgt.
  v1.6.0: entscheidender neuer Datenpunkt für den A1-Mini-Fall — Nutzer
  verglich mit Bambu Studio, das dieselbe Datei bereits 1-2s nach 100%
  erfolgreich überträgt, was die Timeout-Theorie aus v1.5.9 endgültig
  widerlegte. Tatsächliche Ursache: `ftplib.storbinary()` ruft nach der
  Übertragung automatisch `conn.unwrap()` [formaler TLS-Abschluss] auf,
  worauf der A1 Mini offenbar nicht sauber reagiert. Fix:
  `_storbinary_no_unwrap()` [bereits einmal in v1.5.0 für die X1-Serie
  implementiert und dort verworfen, jetzt gezielt nur für Profil "a1"
  reaktiviert] — schädlich für X1, aber die Lösung für A1 Mini.
  Fünfter Anlauf für den A1-Mini-Fall; Bestätigung durch Nutzer für
  beide offenen Fälle [A1-Mini-FTPS, Mehrfarb-Druck] stand zum
  Zeitpunkt dieser Übergabe noch aus. v1.6.1: reine UX-Verbesserung
  [kein Bugfix] — neues Feld `bambu_family` ["x1"/"a1", Standard "x1"]
  beim Anlegen eines Bambu-Druckers wählbar, steuert die Startreihenfolge
  in `_ftps_upload()`s Profil-Alternierung, sodass das bereits bekannte
  Druckermodell direkt im ersten statt im zweiten Versuch verwendet
  wird. Rückwärtskompatibel über `setdefault()` in `load_config()`.
  **A1 Mini vom Nutzer bestätigt: FTPS-Upload funktioniert jetzt
  einwandfrei — die gesamte FTPS-Saga [v1.5.0–v1.6.1] gilt damit als
  abgeschlossen.** v1.6.2: neuer, echter struktureller Bug gefunden —
  "Failed to get AMS mapping table" bei Mehrfarb-Drucken auf X1C. Das
  gesendete `ams_mapping`-Array wurde kompakt in Anzeige-Reihenfolge
  gebaut statt an den echten Filament-Positionen aus der `.gcode.3mf`,
  was bei Indexlücken [mehr Filamente im Projekt als auf der Platte
  verwendet] zu einer vom Drucker abgelehnten Zuordnungstabelle führte.
  Betraf nur Mehrfarb-Drucke — bei Einzelfarb-Drucken sind kompaktes
  und echtes Array zufällig identisch. Fix in Backend
  [`_parse_3mf_filaments()` liefert jetzt `(filamente, gesamtanzahl)`,
  `preview_print()` liefert `total_filaments`] UND Frontend
  [`confirmAmsModal()` baut das Array jetzt an den echten
  `data-true-index`-Positionen] gemeinsam. Isoliert mit Node.js
  getestet, inkl. Vergleichslauf alte vs. neue Logik. Bestätigung durch
  Nutzer stand zum Zeitpunkt dieser Übergabe noch aus. v1.6.3: neues
  Feature [kein Bugfix] auf Nutzerwunsch — Druckauftrag per Drag & Drop
  jetzt auch fuer Ultimaker (`.gcode`-Dateien, Cura-Export). Erfordert
  einmalige Kopplung [Digest-Auth id/key-Paar, Bestaetigung am Drucker-
  Display] vor dem ersten Druck. Eigene RFC-2617-Digest-Auth-
  Implementierung [`_build_digest_authorization()`] statt Pythons
  eingebautem `HTTPDigestAuthHandler`, um die Datei nur einmal statt
  zweimal senden zu muessen. Gegen einen echten, selbst geschriebenen
  Digest-Auth-Testserver verifiziert. Kompletter Test gegen einen
  echten Ultimaker-Drucker stand zum Zeitpunkt dieser Übergabe noch aus.
  v1.6.4: erster Praxistest — gegen "Ultimaker Connect Raspi MK1" [ein
  Nachbau aus einem anderen Chat, nicht Original-Hardware]. Kopplung
  funktionierte, Druckstart scheiterte: "Erwartete Digest-
  Authentifizierungs-Anfrage (401) blieb aus". Ursache vermutet:
  Challenge wurde über den separaten Endpunkt `/api/v1/auth/verify`
  angefragt, den der Nachbau vermutlich nicht implementiert. Fix:
  Challenge wird direkt vom Ziel-Endpunkt `/api/v1/print_job` geholt
  [leerer POST] — **beim erneuten Test schlug auch dieser Fix fehl**
  ["HTTP 400, erwartet: 401"]: v1.6.4 ebenfalls unvollständig. v1.6.5:
  Nutzer lud den TATSÄCHLICHEN Quellcode des Nachbaus hoch [app.py,
  README.md, ultimaker_api.py] — direkte Einsicht ergab: der Nachbau
  prüft beim Druckstart überhaupt KEINE Authentifizierung, nur ob ein
  Datei-Feld vorhanden ist. Fix: `_digest_challenge_or_none()` liefert
  `None` statt Exception, wenn keine 401-Digest-Antwort kommt —
  `send_print()` sendet dann ohne Authorization-Header, funktioniert
  für beide Fälle [echte Hardware mit Zwangs-Auth UND Server ohne Auth]
  gleichzeitig. Gegen den exakten Nachbau-Code getestet. Bestätigung
  durch Nutzer stand zum Zeitpunkt dieser Übergabe noch aus. v1.6.6:
  separates, neu gemeldetes Problem — X1C blieb erneut beim Aufheizen
  hängen, diesmal bei einem EINFARBIGEN Druck mit automatischer
  AMS-Zuordnung. Nach mehreren verworfenen Zwischentheorien [flow_cali-
  Regression, JS-Bug] stellte sich heraus: der Dialog zeigte "Keine
  passende Farbe im AMS gefunden", obwohl das Fach nachweislich die
  richtige Farbe enthielt. Ursache: `_find_matching_tray()` verlangte
  eine byte-genaue Hex-Farb-Übereinstimmung — Slicer- und AMS/RFID-
  Farbwert für "dieselbe" Farbe müssen nicht byte-identisch sein. Fix:
  neue `_color_distance()`-Funktion [euklidischer RGB-Abstand] mit
  bewusst konservativer Toleranz [`COLOR_MATCH_TOLERANCE = 30`] — fängt
  kleine Profilabweichungen ab, verwechselt aber nicht tatsächlich
  unterschiedliche Farben wie Grün/Hellgrün [Distanz ~231]. Bestätigung
  durch Nutzer stand zum Zeitpunkt dieser Übergabe noch aus. v1.6.7:
  neues Feature [kein Bugfix] auf Nutzerwunsch — H2-Serie [H2S, H2D,
  H2D Pro, H2C] als dritte Druckerfamilie ergänzt. Neue Zuordnungs-
  tabelle `BAMBU_FAMILY_TO_FTPS_PROFILE` bildet Familie auf FTPS-Profil
  ab; für "h2" vorerst identisch zu "x1" [Nutzer-Vorgabe, mangels
  eigener Erkenntnisse]. Kein Test gegen echte H2-Hardware möglich —
  reine Vorsichtsannahme, kein verifiziertes Verhalten. v1.6.8: auf
  Nutzerwunsch "auf die gleiche Weise" — P1- [P1P, P1S], P2- [P2S] und
  X2-Serie [X2D] ergänzt, alle drei vorerst ebenfalls auf "x1" gemappt.
  P1 dabei etwas besser abgesichert [laut Bambu direkt technisch von
  X1 abgeleitet], X2D als offizieller X1C/X1E-Nachfolger ebenfalls
  plausibel, P2 am unsichersten [Mischung aus P1- und H2-Technik laut
  Recherche]. Validierung an beiden Stellen [Route, add_printer()]
  refaktoriert: prüft jetzt gegen die Schlüssel von
  `BAMBU_FAMILY_TO_FTPS_PROFILE` statt einer doppelt gepflegten
  Tupel-Liste — künftige Familien brauchen dadurch nur noch einen
  Code-Ort. Kein Test gegen echte P1-/P2-/X2-Hardware möglich).

</details>

- `APP_VERSION` ist die einzige Quelle der Wahrheit; der GitHub-Actions-
  Workflow liest sie automatisch per Regex aus `app.py` aus.
- Empfohlener Ablauf beim Ausliefern einer neuen Version: `APP_VERSION`
  anpassen → committen mit dem mitgelieferten Commit-Text → taggen
  (`git tag vX.Y.Z && git push origin vX.Y.Z`) → GitHub Actions baut
  automatisch Windows-exe + macOS-arm64-Build und hängt beide ans
  Release an.

---

## 10. Wie man weiterarbeitet

1. `app.py`, `README.md` und dieses Dokument in den neuen Chat geben.
2. Bei neuen Druckertypen: erst kurz recherchieren, ob/wie eine lokale
   API existiert (siehe Abschnitt 6, Punkt 1), dann analog zu den
   bestehenden `*Connection`-Klassen eine neue Klasse anlegen (oder eine
   bestehende um einen neuen `type`-Wert erweitern, falls die Anbindung
   technisch identisch ist wie bei Creality/Formlabs).
3. Neue Typen müssen an folgenden Stellen ergänzt werden (siehe Tabelle
   in Abschnitt 3 "Wichtigste Codestellen"):
   - Typ-Konstante (`KNOWN_TYPES` bzw. eigenes `*_TYPES`-Tuple)
   - `DashboardApp._start_printer()` und `add_printer()`
   - `api_add_printer()` (Validierung der Pflichtfelder)
   - `camera_stream()` (falls Kamera unterstützt wird)
   - Frontend: `<select id="f_type">`-Option, ein neues `<div
     id="...Fields">` im Modal, `toggleTypeFields()`, `openAddModal()`
     (Felder zum Zurücksetzen ergänzen), `submitAdd()`, `refresh()`-
     Dispatch, eine neue `render...Card()`-Funktion
   - `config.example.json` um ein Beispiel ergänzen
   - `README.md` um einen neuen Abschnitt ergänzen (Nummerierung beachten)
4. Nach jeder Änderung: kompilieren + Smoke-Test (siehe Abschnitt 6,
   Punkt 4), bevor die Datei ausgeliefert wird.
