# Drucker Dashboard (MK6)

![Bild](Bilder.png)

Lokales Web-Dashboard fuer 3D-/Resin-Drucker im eigenen Netzwerk. Ein
Python-Skript (`app.py`), keine Cloud, kein Account.

| Druckertyp | Anbindung | Kamera | Druck per Drag & Drop |
|---|---|:-:|:-:|
| **Bambu Lab** (X1/A1/H2/P1/P2/X2) | MQTT/TLS | ✅ | ✅ (`.gcode.3mf`, mit AMS-Dialog) |
| **Ultimaker** (UM3, S-Serie, Factor 4) | REST-API | ✅ | ✅ (`.gcode`, nach Kopplung) |
| **OctoPrint** | REST-API | ✅ | – |
| **Creality** (K1/K1C/K1 Max/K1 SE, Klipper) | Moonraker | ✅ | – |
| **Formlabs** (Drucker/Wash L/Cure L) | Local API | – | – |

Jeder Drucker bekommt automatisch einen **Verlauf** (standardmaessig
letzte 30 Druckauftraege, ueber `config.json` einstellbar - siehe
Abschnitt 3) sowie Bambu Lab/Ultimaker zusaetzlich eine
**Warteschlange** fuer beschaeftigte Drucker.

> Fuer Architektur, Codestellen und die vollstaendige
> Entwicklungshistorie siehe `UEBERGABE.md`. Diese README beschreibt nur
> den aktuellen Stand (v2.7.0).

---

## Inhalt

- [0. Build & Release per GitHub Actions](#0-build--release-per-github-actions)
- [1. Lokal einrichten/starten](#1-lokal-einrichtenstarten)
- [2. Drucker hinzufuegen](#2-drucker-hinzufuegen)
- [3. Verlauf, Warteschlange & Kartenlayout](#3-verlauf-warteschlange--kartenlayout)
- [4. Bambu Lab: Drag & Drop drucken](#4-bambu-lab-drag--drop-drucken)
- [5. Temperatur/Feuchte/Druckzeit-Anzeigen](#5-temperaturfeuchtedruckzeit-anzeigen)
- [6. Grenzen & Hinweise](#6-grenzen--hinweise)
- [7. Bedien-/Einstellungsmodus, Raeume & externe Kameras (seit v2.3.0)](#7-bedieneinstellungsmodus-raeume--externe-kameras-seit-v230)
- [8. FarmBot: automatische Warteschlange ueber mehrere Drucker (seit v2.6.0)](#8-farmbot-automatische-warteschlange-ueber-mehrere-drucker-seit-v260)

---

## 0. Build & Release per GitHub Actions

`.github/workflows/build-exe.yml` baut bei **jedem Push** automatisch
Windows- und macOS-arm64-Zips (`DruckerDashboard-v<Version>-...zip`,
je **drei** Dateien: `DruckerDashboard.exe` + `FtpsUploadHelper.exe` +
`ffmpeg.exe` - **im selben Ordner halten**) und veroeffentlicht sie
automatisch als **GitHub Release** (benannt nach `APP_VERSION` in
`app.py`).

**FFmpeg** (seit v2.2.22, fuer die Kamera der X1/P1/P2/H2/X2-Serie,
siehe Abschnitt 2) wird vom Workflow automatisch von einer jeweils
aktuellen, oeffentlich verfuegbaren Quelle heruntergeladen und mit ins
Zip gepackt - **kein manueller Schritt noetig**. Fuer macOS gibt es
dabei keine native Apple-Silicon(arm64)-FFmpeg-Variante, deshalb wird
dort die Intel(x86_64)-Version mitgeliefert; sie laeuft auf Apple-
Silicon-Macs ueber **Rosetta 2**, das macOS beim ersten Start bei Bedarf
automatisch zur Installation anbietet (einmalig, braucht kurz Internet).

**Setup:**
```bash
git init && git add . && git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<user>/<repo>.git
git push -u origin main
```
Danach: Tab **Actions** abwarten (2-4 Min), fertige Zips unter
**Releases**. Kein manueller Tag noetig, kein zusaetzliches Secret
(`GITHUB_TOKEN` liefert GitHub Actions automatisch). Falls der
Release-Schritt mit `403 Resource not accessible by integration`
fehlschlaegt: unter **Settings → Actions → General → Workflow
permissions** "Read and write permissions" aktivieren (der Workflow
fordert seit v2.2.19 zwar selbst Schreibzugriff an, manche
Organisations-Einstellungen koennen das aber weiterhin einschraenken).

**macOS/Gatekeeper** (Binaries sind unsigniert): Finder → Rechtsklick →
"Oeffnen" → "Trotzdem oeffnen", oder `xattr -dr com.apple.quarantine <Datei>`.

**Versionierung:** `APP_VERSION` in `app.py` (`MAJOR.MINOR.PATCH`) ist
die einzige Quelle der Wahrheit - PATCH = Bugfix, MINOR = neues Feature,
MAJOR = Breaking Change. Einfach anpassen und pushen, der Rest ist
automatisch.

## 1. Lokal einrichten/starten

Benoetigt **Python 3.9 oder neuer**. Bei direktem Start per `python3
app.py` (ohne gebaute exe) auf ungewoehnlichen/eingebetteten Systemen
(z. B. OpenWrt-Router) vorher `python3 --version` pruefen. Fuer eine
vollstaendige Installation auf einem Linux-/OpenWrt-Geraet (Autostart,
FFmpeg fuer musl-Systeme, Fehlerbehebung) siehe `LINUX-INSTALL.md`.

```bash
python -m venv venv && venv\Scripts\activate   # Windows
pip install -r requirements.txt                # flask, paho-mqtt (1.6.1!), pyinstaller
python app.py                                  # -> http://<IP-des-PCs>:8000
```

**Eigene exe bauen (optional, sonst siehe Abschnitt 0):**
```bash
pyinstaller --onefile --name DruckerDashboard --console app.py
pyinstaller --onefile --name FtpsUploadHelper --console ftps_upload_helper.py
```
Beide `dist/*.exe` werden zum Weitergeben benoetigt (gleicher Ordner).
Fuer die Kamera der X1/P1/P2/H2/X2-Serie zusaetzlich eine `ffmpeg(.exe)`
in denselben Ordner legen (siehe Abschnitt 0) - ohne sie funktioniert
nur diese Kamera-Variante nicht, alles andere (inkl. A1-Kamera)
unveraendert. `config.json` entsteht automatisch beim ersten Start.
Funktioniert identisch auf Apple Silicon (kein Rosetta fuer das
Hauptprogramm selbst noetig, kein `--add-data` noetig).

**Im Entwicklungsbetrieb** (direkter Start per `python app.py`, keine
gebaute exe) reicht fuer die RTSPS-Kamera alternativ eine separat
installierte, ueber PATH erreichbare FFmpeg-Installation (z. B. per
Paketmanager) - das Dashboard findet sie automatisch.

## 2. Drucker hinzufuegen

| Typ | Benoetigte Angaben | Voraussetzung |
|---|---|---|
| **Bambu Lab** | Name, IP, Access Code, Seriennummer, Druckerfamilie | LAN-Modus + **Developer Mode** aktivieren (**lokal am Drucker** ueber dessen Einstellungen, pro Geraet - im reinen LAN-Modus ist die Verbindung zur Bambu-Handy-App gekappt, dort laesst sich der Developer Mode nicht einschalten). H2-Serie/P2S: **USB-Stick muss stecken** (FTPS-Upload erreicht sonst keinen Speicher, Fehler `553 Could not create file`); X1/P1/A1 brauchen dafuer eine microSD. |
| **Ultimaker** | Name, IP | Einmalige Kopplung: "Jetzt koppeln" klicken, am Drucker-Display bestaetigen. |
| **OctoPrint** | IP, API-Key (Einstellungen → API), optional Port/HTTPS/Webcam-URL | - |
| **Creality** (K1/K1C/K1 Max/K1 SE, Klipper) | IP, Moonraker-Port (7125), optional API-Key/Webcam-URL | Moonraker muss installiert sein (werksseitig nicht vorhanden, z. B. per [Creality-Helper-Script](https://github.com/Guilouz/Creality-Helper-Script-Wiki)). "Creality OS" ohne Klipper wird nicht unterstuetzt. |
| **Formlabs** (Drucker/Wash L/Cure L) | Name, IP | Braucht laufenden **PreFormServer** (`PreFormServer.exe --port 44388`) auf einem PC im selben Netz. "Form Wash/Cure" ohne "L" werden nicht unterstuetzt (keine Netzwerkfunktion). |

**Bambu-Druckerfamilie** bestimmt, welches FTPS-/Druckstart-Profil
zuerst probiert wird (X1-Serie, A1-Serie, H2-Serie, P1-Serie, P2-Serie,
X2-Serie) - eine falsche Wahl verhindert den Druck nicht zwingend. Sie
bestimmt AUSSERDEM (seit v2.2.22), welches Kamera-Protokoll verwendet
wird:

- **A1-Serie:** funktioniert ohne weitere Einstellung (rohes MJPEG,
  Port 6000).
- **X1/P1/P2/H2/X2-Serie:** braucht zusaetzlich zum Developer Mode am
  Drucker-Display die SEPARATE Einstellung **"LAN Only Liveview"**
  (teils auch "LAN Mode Liveview" genannt, je nach Firmware-
  Uebersetzung an anderer Stelle im Menue als der Developer Mode) sowie
  eine mitgelieferte/installierte **FFmpeg**-Programmdatei (siehe
  Abschnitt 0/1) - ohne aktivierte Einstellung zeigt das Kamera-Fenster
  einen Hinweis darauf, ohne FFmpeg einen Hinweis, dass FFmpeg fehlt,
  statt eines kryptischen Fehlers.

**Eigene Sensoren/Schalter** ueber einen zweiten, von den Druckern
unabhaengigen MQTT-Broker (z. B. Home Assistant/Mosquitto) lassen sich
komplett im Abschnitt **"MQTT-Geraete (Sensoren/Schalter)"** des
Einstellungen-Modus (seit v2.3.0, seit v2.5.1 inline statt hinter einem
eigenen Knopf - siehe
[Abschnitt 7](#7-bedieneinstellungsmodus-raeume--externe-kameras-seit-v230);
vor v2.3.0 direkt im Kopfbereich als "MQTT-Sensoren") einrichten - kein
manuelles Bearbeiten der `config.json` mehr noetig:

1. Broker-Adresse/Port/Zugangsdaten eintragen und speichern - die
   Verbindung wird sofort (ohne Neustart) aufgebaut.
2. Ueber **"+ Sensor/Schalter hinzufuegen"** einen Eintrag anlegen:
   Drucker (oder **"Kein Drucker (eigenstaendig)"**, seit v2.5.0 - siehe
   [Abschnitt 7](#7-bedieneinstellungsmodus-raeume--externe-kameras-seit-v230)),
   Art (**Sensor** = reine Anzeige, **Schalter** = Ein/Aus-Buttons) und
   die zugehoerigen Felder (Topic + Einheit bzw. Befehls-Topic +
   Payloads) auswaehlen/eintragen. Im selben Dialog erscheinen die
   **zuletzt tatsaechlich vom Broker empfangenen Topics** zur
   Kontrolle/zum Uebernehmen per Klick - der haeufigste Stolperstein (ein
   falsch abgetipptes Topic) faellt damit weg. Bearbeiten/Loeschen
   bestehender Eintraege direkt in der Liste im Einstellungen-Bereich.
3. Bei einem Sensor zusaetzlich den **Anzeigebereich** waehlen:
   "Generisch" zeigt ihn wie bisher unten im Bereich "Sensoren &
   Schalter"; **"Temperatur"** oder **"Luftfeuchtigkeit"** platziert ihn
   stattdessen direkt in der Temperaturen-Zeile der Karte, GENAUSO wie
   die vom Drucker selbst gelieferten Werte (Duese/Bett/Kammer bzw.
   AMS-Feuchte). Seit v2.5.1 zeigt **jeder** Sensor, unabhaengig vom
   gewaehlten Anzeigebereich, ein kleines Verlaufsdiagramm
   (Sparkline) - die Auswahl entscheidet seitdem nur noch, WO er
   angezeigt wird.

Alternativ weiterhin per Hand in `config.json` moeglich (Beispiel in
`config.example.json`, Felder `extras_mqtt` global + `extras`-Liste je
Drucker) - beide Wege greifen auf dieselbe Konfiguration zu.

## 3. Verlauf, Warteschlange & Kartenlayout

**Verlauf** (Uhr-Symbol je Karte): jeder ueber das Dashboard gesendete
Druckauftrag landet mit Zeitstempel, Vorschaubild (Bambu) und
geschaetzter Druckzeit (siehe [Abschnitt 5](#5-temperaturfeuchtedruckzeit-anzeigen))
im Verlauf - **Erneut drucken**, **In Warteschlange**, **Zuweisen** (an
einen anderen Drucker gleichen Typs/Familie), **Loeschen**. Erneutes
Senden an denselben Drucker aktualisiert nur den Zeitstempel (kein
doppelter Eintrag). Automatisch begrenzt auf die Anzahl aus
`"history_max_jobs"` in `config.json` (Standardwert 30, je Drucker
separat gezaehlt) - als Wert geht eine positive Zahl, oder leer/`0`/
`null` bzw. der Text `"unendlich"` fuer KEIN Limit (der Verlaufsordner
waechst dann unbegrenzt, das im Auge zu behalten liegt dann beim
Nutzer). Ein ungueltiger Wert faellt defensiv auf 30 zurueck (mit einer
Warnung in der Server-Konsole beim Start). Seit v2.3.0 auch direkt im
Einstellungen-Modus aenderbar, ohne `config.json` von Hand zu bearbeiten
(siehe [Abschnitt 7](#7-bedieneinstellungsmodus-raeume--externe-kameras-seit-v230)).

**Warteschlange** (Listen-Symbol, nur Bambu/Ultimaker): eine Datei wird
automatisch eingereiht statt sofort gesendet, wenn der Drucker gerade
beschaeftigt ist. Aeltester Auftrag steht oben; **▲/▼** sortiert um,
**+ Datei hinzufuegen** (auch per Drag & Drop) fuegt manuell hinzu,
**Druckraum leer - naechsten senden** startet den obersten Auftrag,
sobald der Drucker wirklich fertig ist (bei Bambu: Status `FINISH`/
`IDLE`/`FAILED`).

**Kartenlayout:** Schaltflaechen **1/2/3/4** (4-spaltig seit v2.4.0) oben
rechts wechseln zwischen ein bis vier Spalten (je Browser in
`localStorage` gemerkt, bei schmalem Fenster automatisch reduziert).

## 4. Bambu Lab: Drag & Drop drucken

Nur fertig gesclicte **`.gcode.3mf`**-Dateien (Bambu Studio/OrcaSlicer-
Export) auf die Karte ziehen - **Developer Mode muss aktiv sein**
(siehe [Abschnitt 2](#2-drucker-hinzufuegen)).

1. **Vorschau/AMS-Zuordnung pruefen:** Datei wird ausgewertet, Dialog
   zeigt nur die auf Plate 1 tatsaechlich benoetigten Filamente mit
   automatischem Farb-/Typ-Vorschlag gegen die AMS-Faecher (oder
   manuelle Auswahl). Kein Match wird nie automatisch geraten (z. B.
   Verbundwerkstoffe wie `PLA-CF` nie mit der Grundvariante verwechselt).
2. **Drucken starten:** Upload per FTPS (Port 990), danach MQTT-Kommando
   `project_file`. Schlaegt der Upload fehl, bleiben Datei/Zuordnung
   erhalten - einfach erneut klicken.

**AMS HT (Stuetzmaterial-Einheit):** seit v2.2.21 vollstaendig
unterstuetzt, automatische Zuordnung eingeschlossen. v2.2.20 hatte das
noch bewusst ausgeschlossen, weil die interne Fach-Numerierung des
Dashboards faelschlich von 4 Faechern pro AMS-Einheit ausging (eine
AMS HT hat nur 1 Fach und meldet sich mit der Geraete-ID 128 statt
0/1/2) - das hatte bei einem H2D Pro (AMS 2 Pro + AMS HT fuer PLA-
Stuetzmaterial) einen Druckabbruch nach den ersten Schichten verursacht
("Zuordnungstabelle des AMS konnte nicht abgerufen werden"). Der
korrekte Wert wurde inzwischen durch einen vom Nutzer eingefangenen
echten Bambu-Studio-Befehl verifiziert (kein Raten mehr) und ist jetzt
fest hinterlegt. Details: `UEBERGABE.md`, v2.2.21.

Technisch nutzt jede Druckerfamilie automatisch das passende FTPS-Profil
und Druckstart-URL-Schema (`file:///sdcard/...` bei X1/A1/P1/X2,
`ftp:///...` bei H2/P2S). Details/Hintergrund zu geloesten FTPS-/AMS-
Problemen: `UEBERGABE.md`.

## 5. Temperatur/Feuchte/Druckzeit-Anzeigen

- **Temperatur-Sparklines:** jeder Duesen-/Bett-/Kammer-Chip zeigt eine
  kleine rote Verlaufskurve der letzten Werte (nur im Browser, geht
  beim Neuladen verloren - es wird keine Zeitreihe gespeichert). Seit
  v2.5.1 gilt das fuer **jeden** MQTT-Sensor (siehe
  [Abschnitt 2](#2-drucker-hinzufuegen)), nicht nur fuer die mit
  Anzeigebereich "Temperatur"/"Luftfeuchtigkeit".
- **AMS-Feuchte** (Bambu, je AMS-Einheit): zeigt bei AMS 2 Pro einen
  echten Prozentwert (`humidity_raw`, z. B. "44%" - unabhaengig vom
  Druckermodell, das AMS 2 Pro ist ein eigenstaendiges Zubehoerteil; laut
  Nutzerberichten tendenziell etwas zu niedrig messend). Aeltere
  Vier-Fach-AMS ohne Prozentwert zeigen stattdessen ein Wort-Label +
  Punkte-Skala (1-5) - die Richtung dieser Skala ist je nach
  AMS-Generation nicht einheitlich dokumentiert. Bei der A1-Familie
  (AMS Lite ohne Feuchtesensor) wird nichts angezeigt.
- **Kammertemperatur:** bei A1 nicht verfuegbar (kein Sensor). Bei
  X1C/H2S wird zusaetzlich zu `chamber_temper`/`chamber_temp` auch
  `device.ctc.info.temp` ausgewertet - vom Nutzer gegen Bambu Studio
  verifiziert und korrekt.
- **Geschaetzte Druckzeit** (neu, Verlauf & Warteschlange): aus
  `Metadata/slice_info.config` (Bambu, `prediction`-Feld der Plate) bzw.
  dem `;TIME:`-Kopfkommentar (Ultimaker/Cura) gelesen, als "Xh Ymin"
  angezeigt. Kein Wert, wenn sich aus der Datei nichts extrahieren
  laesst.
- **Druckbild neben dem Fortschrittsbalken:** Vorschau des zuletzt
  ueber das Dashboard gesendeten Auftrags (Bambu/Ultimaker).

## 6. Grenzen & Hinweise

- Bambu-Kamera und Drag-&-Drop-Druckversand nutzen von der Community
  reverse-engineerte, inoffizielle Protokolle - ein Firmware-Update kann
  das jederzeit aendern. Bambu-MQTT laeuft ausschliesslich lokal (TLS,
  kein Cloud-Account).
- `FtpsUploadHelper.exe` muss neben `DruckerDashboard.exe` liegen, sonst
  greift ein langsamerer Fallback (Selbstaufruf).
- `ffmpeg(.exe)` muss ebenfalls neben `DruckerDashboard.exe` liegen (bei
  Nutzung des per GitHub Actions gebauten Zips bereits enthalten, siehe
  Abschnitt 0), sonst funktioniert nur die Kamera der X1/P1/P2/H2/X2-
  Serie nicht (klare Fehlermeldung im Kamera-Fenster statt Absturz).
  Bleibt das Kamera-Fenster trotz aktivierter "LAN Only Liveview" und
  vorhandenem FFmpeg laenger als ~15 Sekunden ohne Bild oder
  Fehlermeldung haengen: in der Server-Konsole nach Zeilen mit dem
  Praefix `[MK6-FFMPEG]` suchen (seit v2.2.23/25 - u. a. "Starte
  FFmpeg-Prozess...", "FFmpeg-Prozess gestartet (PID ...)" sowie
  FFmpegs eigene Fehlerausgabe zur RTSPS-Verbindung). Erscheint nicht
  einmal "FFmpeg-Prozess gestartet" (nur die Start-Zeile davor): dann
  verzoegert/blockiert vermutlich eine Antivirus-Software/Windows
  Defender den Start der frisch heruntergeladenen `ffmpeg.exe` - im
  Windows-Sicherheitsverlauf (Viren- & Bedrohungsschutz -> Schutz-
  verlauf) nachsehen, und `ffmpeg.exe` testweise manuell im selben
  Ordner starten (z. B. `ffmpeg -version`).
- (Seit v2.2.26 behoben, Hintergrund zur Erinnerung:) Bis v2.2.25 blieb
  das Bild der X1/P1/P2/H2/X2-Kamera dauerhaft leer/schwarz, obwohl
  FFmpeg fehlerfrei lief - Ursache war ein browserinkompatibles
  Multipart-Format von FFmpegs eingebautem `mpjpeg`-Muxer (fehlender
  `Content-Length`-Header, `\n` statt `\r\n`). Das Dashboard trennt die
  JPEG-Bilder seitdem selbst aus dem FFmpeg-Rohstrom heraus und verpackt
  sie im selben Format wie die A1-Kamera. Details: `UEBERGABE.md`, v2.2.26.
- Waehrend eines Drag-&-Drop-Uploads pausiert Status/Kamera/AMS kurz
  (MQTT wird bewusst kurz getrennt und automatisch neu verbunden).
- **Status-Punkt bleibt bei einem Bambu-Drucker dauerhaft rot:** der
  Punkt zeigt AUSSCHLIESSLICH, ob die eigene MQTT-Verbindung des
  Dashboards zu diesem Drucker gerade steht - unabhaengig davon, ob
  Kamera (eigener, unabhaengiger Stream) oder Temperaturwerte angezeigt
  werden. Letztere werden bei einer getrennten Verbindung bewusst NICHT
  geloescht, sondern bleiben als "zuletzt bekannt" stehen (mit
  entsprechendem Hinweis auf der Karte) - sie sehen also ggf. "live" aus,
  obwohl sie veraltet sind. Zur Diagnose in der Server-Konsole nach
  Zeilen mit dem Praefix `[MK6-MQTT]` suchen: "rc=0: Connection Accepted"
  = Verbindung steht; ein anderer rc-Wert (z. B. "not authorised") deutet
  auf falschen Access Code/Seriennummer in der Drucker-Konfiguration hin;
  eine Zeile "Verbindungsfehler: ..." (z. B. Timeout/Connection refused)
  deutet auf ein Netzwerk-/Firewall-Problem auf Port `8883` hin
  (unabhaengig vom Kamera-Port `6000`, der separat erreichbar sein
  kann); eine Zeile "unerwartet getrennt (rc=7)" bedeutet "Connection
  Lost" (Client-Bibliothek, kein vom MQTT-Protokoll selbst definierter
  Code) - ein unerwartet geschlossener Socket, keine regulaere Abmeldung
  durch den Drucker, inkl. Standzeit seit dem letzten erfolgreichen
  Connect. **Bekannter, seit v2.5.5 behobener Fall (A1/A1 mini):** die
  Verbindung wurde reproduzierbar SOFORT (Standzeit "0.0s") nach dem
  Connect wieder getrennt - Ursache war das zusaetzliche, rein
  diagnostische Abo des eigenen "request"-Topics (siehe v2.2.20), das
  bei dieser Druckerfamilie zum sofortigen Verbindungsabbruch fuehrte;
  X1/H2 sind nicht betroffen. Seit v2.5.5 wird dieses Abo fuer
  `bambu_family: "a1"` deshalb nicht mehr gesetzt - Status-Report und
  "pushall"-Anfrage (und damit alle Status-/Temperaturwerte) sind davon
  unberuehrt, lediglich die Mitprotokollierung fremder project_file-
  Kommandos (nur fuer die AMS-HT-Mapping-Analyse relevant, siehe v2.2.20)
  steht fuer A1-Drucker nicht zur Verfuegung. Details zur Diagnose siehe
  `UEBERGABE.md`, v2.5.2-v2.5.5.
- Formlabs braucht PreFormServer, Creality braucht Moonraker - beides
  Hersteller-Einschraenkungen, keine Design-Entscheidung dieses Programms.
- Vorbereitete, aber nie bestaetigte Druckauftraege werden nach 20
  Minuten automatisch aufgeraeumt.
- Fuer Zugriff aus dem gesamten LAN ggf. Port `8000` in der Firewall
  freigeben.
- Die seit v2.3.0 frei konfigurierbaren externen RTSP-Kameras (siehe
  [Abschnitt 7](#7-bedieneinstellungsmodus-raeume--externe-kameras-seit-v230))
  brauchen genau wie die RTSPS-Kamera der X1/P1/P2/H2/X2-Serie FFmpeg -
  dieselben Hinweise/Fehlerbilder oben in diesem Abschnitt gelten dafuer
  entsprechend.

## 7. Bedien-/Einstellungsmodus, Raeume & externe Kameras (seit v2.3.0)

Seit v2.3.0 gibt es zwei Modi, umschaltbar ueber die Schaltflaeche
**"⚙ Einstellungen"** oben rechts (bzw. **"← Zur Bedienung"** zurueck):

- **Bedien-Modus** (Standard, das ist die bisherige Oberflaeche): alle
  Drucker samt Kamera, Verlauf, Warteschlange und allen Druckfunktionen
  ansehen/bedienen, Kartenlayout waehlen (seit v2.4.0 auch 4-spaltig).
  Externe RTSP-Kameras (siehe unten) erscheinen seit v2.4.0 als eigene,
  schlanke Kachel direkt zwischen den Druckern (**kein gemeinsamer
  "Kameras"-Knopf mehr** - mit v2.3.0 eingefuehrt, mit v2.4.0 wieder
  entfernt, weil Kameras seitdem genauso wie Drucker einem Raum
  zugewiesen und dort passend einsortiert werden). **Hinzufuegen/
  Entfernen von Druckern und Kameras ist hier bewusst NICHT moeglich**
  (siehe unten).
- **Einstellungen-Modus:** Drucker hinzufuegen/entfernen/einem Raum
  zuweisen/in der Reihenfolge verschieben, Raeume anlegen/umbenennen/
  entfernen/verschieben, externe RTSP-Kameras anlegen/bearbeiten/
  entfernen/einem Raum zuweisen, MQTT-Geraete verwalten (bisheriger
  "MQTT-Sensoren"-Dialog, jetzt nur noch von hier aus erreichbar, seit
  v2.5.0 auch ohne Druckerzuordnung moeglich, seit v2.5.1 inline wie die
  anderen Bereiche statt hinter einem eigenen Knopf - siehe unten) sowie
  die maximale Anzahl gespeicherter Verlaufseintraege
  (`history_max_jobs`, siehe
  [Abschnitt 3](#3-verlauf-warteschlange--kartenlayout)) direkt ueber die
  Oberflaeche statt per Hand in `config.json`. Der **"Speichern"-Knopf
  dafuer sitzt seit v2.5.0 in der Kopfzeile neben "← Zur Bedienung"**
  (vorher im Abschnitt "Druckverlauf" weiter unten, wo er faelschlich wie
  ein Teil davon aussah).

**Raeume/Gruppen:** rein organisatorisch, ohne technische Wirkung auf
die Drucker-/Kamera-Verbindung selbst. Im Bedien-Modus werden Drucker
UND externe Kameras (sobald mindestens ein Raum angelegt wurde) nach
Raum gruppiert angezeigt, mit Raumname als Zwischenueberschrift; nicht
zugewiesene Drucker/Kameras erscheinen unter "Ohne Raum". Ein
geloeschter Raum loescht WEDER Drucker noch Kameras - beide wandern
automatisch zurueck unter "Ohne Raum". Ohne angelegte Raeume sieht die
Ansicht unveraendert aus wie vor v2.3.0 (flache Liste).

**Externe RTSP-Kameras:** zusaetzlich zu den drucker-eigenen Kameras
lassen sich beliebige weitere, frei benennbare RTSP(S)-Kameras
hinterlegen (z. B. eine Raumuebersichtskamera) - Name, vollstaendige
`rtsp://`- bzw. `rtsps://`-URL, optional ein Raum sowie (seit v2.4.0)
optional **Benutzername/Passwort als eigene Felder** genuegen. Verlangt
die Kamera eine Anmeldung, muessen die Zugangsdaten NICHT mehr von Hand
in die URL eingebaut werden (`rtsp://user:pass@...`) - das Dashboard
baut sie selbst korrekt (inkl. automatischer Kodierung von
Sonderzeichen wie `@`, `:` oder `/` im Passwort) in die URL ein. Das
Streaming laeuft technisch genauso wie bei der RTSPS-Kamera der
X1/P1/P2/H2/X2-Serie (siehe [Abschnitt 2](#2-drucker-hinzufuegen) und
`UEBERGABE.md` v2.2.22/v2.2.26) - **FFmpeg wird also ebenfalls
benoetigt** (siehe Abschnitt 0/1 bzw. `LINUX-INSTALL.md`).

**Reihenfolge aendern:** sowohl Drucker als auch Raeume lassen sich im
Einstellungen-Modus per ▲/▼-Schaltflaechen (gleiches Bedienkonzept wie
die bestehende Warteschlangen-Umsortierung, siehe
[Abschnitt 3](#3-verlauf-warteschlange--kartenlayout)) in eine beliebige
Reihenfolge bringen - wirkt sich auf die Anzeigereihenfolge im Bedien-
Modus aus.

**Kartenlayout:** seit v2.4.0 zusaetzlich zu 1/2/3 auch **4-spaltig**
waehlbar (siehe [Abschnitt 3](#3-verlauf-warteschlange--kartenlayout)).

**Eigenstaendige MQTT-Sensoren/Schalter (seit v2.5.0):** im
"MQTT-Geraete"-Bereich des Einstellungen-Modus steht beim Anlegen eines
neuen Eintrags in der Drucker-Auswahl zusaetzlich **"Kein Drucker
(eigenstaendig)"** zur Verfuegung. Damit lassen sich Sensoren (z. B. ein
Raumthermometer) oder Schalter anlegen, die zu keinem bestimmten
Drucker gehoeren - vorher war dafuer zwingend ein bereits angelegter
Drucker noetig, ohne einen liess sich ueberhaupt kein Eintrag
speichern. Eigenstaendige Eintraege erscheinen im Bedien-Modus als
eigene, schlanke Kachel (wie eine externe Kamera) und koennen genauso
wie Drucker/Kameras einem Raum zugewiesen werden (Dropdown direkt in
der Eintragsliste im Einstellungen-Bereich).

**MQTT-Geraete-Bereich jetzt inline (seit v2.5.1):** Broker-
Einstellungen, das Anlegen-Formular (eigenes kleines Fenster, analog
zum Kamera-Anlegen-Dialog) und die Liste bestehender Sensoren/Schalter
sitzen jetzt direkt im "MQTT-Geraete"-Abschnitt des
Einstellungen-Modus - genau wie bei "Drucker verwalten"/"Raeume"/
"Externe RTSP-Kameras". Vorher steckte der komplette Bereich hinter
einem einzelnen "MQTT-Geraete verwalten"-Knopf in einem grossen,
eigenen Dialogfenster, als einziger Abschnitt mit abweichendem
Bedienkonzept.

**Sparkline-Farbe eigenstaendiger Sensoren (seit v2.5.6 korrekt):** ein
eigenstaendiger MQTT-Sensor mit der Anzeigeart "Bei Luftfeuchtigkeit
anzeigen" zeigt sein Verlaufsdiagramm jetzt genau wie ein gleichartiger,
druckergebundener Sensor in Blau - unabhaengig davon, ob er einem
Drucker zugeordnet ist oder nicht (vorher war die eigenstaendige Kachel
immer in der Default-Farbe Rot).

---

## 8. FarmBot: automatische Warteschlange ueber mehrere Drucker (seit v2.6.0)

**FarmBot** ist eine eigenstaendige, von den Warteschlangen einzelner
Drucker unabhaengige Funktion: statt eine Datei einem bestimmten
Drucker zuzuweisen, legt man sie in die Warteschlange eines FarmBot,
und FarmBot sucht sich bei Bedarf selbst einen gerade freien, passenden
Drucker. Mehrere unabhaengige FarmBots koennen gleichzeitig aktiviert
sein (z. B. einer je Druckerfamilie oder Werkstattbereich).

**Einrichten (Einstellungen-Modus &rarr; Abschnitt "FarmBot"):**
- **Namenszusatz** (optional) - unterscheidet mehrere FarmBots
  voneinander (z. B. "FarmBot Werkstatt").
- **Hersteller + Druckerfamilie**: aktuell **nur Bambu Lab oder
  Ultimaker** (nur fuer diese beiden existiert bereits ein
  automatisierter Upload+Druckstart ohne Eingriff am Drucker selbst -
  OctoPrint/Creality bleiben weiterhin rein manuell).
- **Arbeitstag** (von/bis): das Zeitfenster, in dem neue Druckauftraege
  gestartet werden sollen (siehe "Automatische Reihenfolge" unten) -
  **begrenzt nur das Starten neuer Auftraege**, nicht deren
  Fertigstellung: ein bereits laufender Druck darf unbeaufsichtigt
  ueber das Fensterende hinaus weiterdrucken.
- **Maximale Wartezeit in der Warteschlange (Tage)**: Auftraege, die
  diese Wartezeit erreichen, werden bei der naechsten Neuberechnung der
  Reihenfolge unabhaengig von ihrer Druckdauer vorrangig abgearbeitet.

**Bedienung:** ist mindestens ein FarmBot aktiviert, erscheint oberhalb
der Drucker-Kacheln ein eigenes Feld je FarmBot. Eine fertig gesclicte
Datei (`.gcode.3mf` fuer Bambu, `.gcode` fuer Ultimaker) wird per
Drag & Drop dort hinein gezogen; ueber "Warteschlange" laesst sich die
aktuelle Reihenfolge einsehen (sowie einzelne Auftraege entfernen).

**Automatische Reihenfolge:** nach jedem Hinzufuegen eines Auftrags
wird die Warteschlange automatisch neu sortiert - keine manuelle
Umsortierung wie bei der Warteschlange eines einzelnen Druckers.
Ueberfaellige Auftraege (siehe maximale Wartezeit) stehen zuerst,
danach die uebrigen Auftraege nach **kuerzester geschaetzter Druckzeit
zuerst** (maximiert die Anzahl der im Arbeitstag-Fenster noch
**startbaren** Drucke - der jeweils letzte darf dabei unbeaufsichtigt
ueber den Feierabend hinaus weiterlaufen, siehe Hinweis zum
Arbeitstag-Fenster oben). Die Druckzeit wird, genau wie im Verlauf/in der
Drucker-Warteschlange, automatisch aus der Datei ausgelesen, wenn
moeglich - gelingt das nicht, wird der Auftrag ans Ende gestellt statt
eine Dauer zu schaetzen.

**Haendische Umsortierung (seit v2.7.0):** im Warteschlangen-Modal lassen
sich Auftraege zusaetzlich per ▲/▼ frei verschieben, genau wie bei der
Warteschlange eines einzelnen Druckers. Diese haendische Reihenfolge
bleibt bestehen, bis der naechste Auftrag hinzugefuegt wird - danach
wird automatisch wieder wie oben beschrieben neu sortiert.

**"Naechsten Druck starten":** sucht einen passenden, gerade freien
Drucker der gewaehlten Hersteller-/Familienauswahl (mit Lastverteilung
zwischen mehreren passenden Druckern). Hat dieser Drucker zuvor bereits
etwas fertig gedruckt, zeigt das Dashboard zunaechst dessen Kamerabild
mit den Schaltflaechen **"Druckraum frei"** (startet den Druck) und
**"Anderer Drucker"** (sucht erneut, diesmal ohne diesen Drucker) - bei
einem frischen/noch nie benutzten Drucker entfaellt diese Abfrage. Der
Knopf funktioniert jederzeit, auch ausserhalb des eingestellten
Arbeitstag-Fensters (nur die automatische Umsortierung orientiert sich
am Fenster). Bei Bambu-Lab-Druckern erscheint danach wie gewohnt der
AMS-Zuordnungsdialog; die Zuordnung erfolgt also erst NACH Auswahl des
Druckers und Bestaetigung der Verfuegbarkeit. Ein ueber FarmBot
gestarteter Druck erscheint automatisch auch im Verlauf des jeweiligen
Druckers.

**Unabhaengigkeit:** der Betrieb eines FarmBot ist vollstaendig
unabhaengig von der direkten, manuellen Zuweisung von Druckauftraegen
an einzelne Drucker ueber das Dashboard - beide Wege koennen
gleichzeitig genutzt werden, ohne sich gegenseitig zu beeinflussen.

---

Fuer Architektur-Details, Codestellen und die vollstaendige
Entwicklungshistorie (inkl. MK5) siehe `UEBERGABE.md`.
