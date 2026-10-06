"""
3D-Drucker Dashboard
=====================
Ein lokal laufendes Web-Dashboard fuer 3D-Drucker im eigenen Netzwerk.

Unterstuetzte Geraetetypen:

- Bambu Lab (P1/X1/A1 Serie, LAN-/Developer-Modus): Verbindung per MQTT.
  Fortschritt, Datei, Kamera, AMS-Filamente, Temperaturen.
- Formlabs Drucker (Form 3/4/Fuse Serie): Verbindung ueber die offizielle
  "Formlabs Local API" (siehe Klasse FormlabsLocalApiConnection unten fuer
  Details/Voraussetzungen). Fortschritt, Druckauftrag, Material.
- Formlabs Wash L / Formlabs Cure L: gleiche Anbindung wie Formlabs
  Drucker, Fortschritt + aktueller Zyklus. (Die "kleinen" Form Wash/Form
  Cure OHNE "L" haben keinerlei Netzwerkfunktion und koennen technisch
  nicht eingebunden werden.)
- OctoPrint: Verbindung per REST-API (X-Api-Key). Fortschritt, Datei,
  Temperaturen, Kamera - wird optisch/funktional wie ein Bambu Lab
  Drucker dargestellt.

Zusaetzlich: ueber einen zweiten, unabhaengigen MQTT-Broker koennen frei
definierte Sensoren (Anzeige eines Werts) und Schaltflaechen (senden
fester An-/Aus-Nachrichten) konfiguriert und einer beliebigen Drucker-
karte angehaengt werden (siehe ExtrasMqttManager unten sowie die
"extras_mqtt"/"extras"-Abschnitte in config.json).

Start (Entwicklung):   python app.py
Erreichbar unter:      http://<IP-DES-PCS>:8000
Konfiguration:         config.json (liegt im selben Ordner wie das Skript
                        bzw. wie die von PyInstaller erzeugte .exe)
"""

# Versionsnummer (semantische Versionierung, siehe UEBERGABE.md
# Abschnitt "Versionierung"). Einzige Quelle der Wahrheit fuer die
# Version - wird vom GitHub-Actions-Workflow per Regex ausgelesen, um
# Release-Tag und Datei-Namen zu erzeugen. Bei jeder ausgelieferten
# Aenderung hier erhoehen (siehe Abschnitt in UEBERGABE.md fuer die
# Regeln, was Major/Minor/Patch bedeutet).
#
# MK6: Versionszaehlung startet bewusst neu bei 1.0.0 (siehe UEBERGABE.md
# Abschnitt 9) - die Detail-Historie von MK5 (1.0.0-1.6.8) bleibt in der
# MK5-UEBERGABE.md dokumentiert, gilt aber technisch unveraendert weiter
# fort (MK6 ist ein additiver Fortsatz von MK5 v1.6.8, kein Rewrite).
#
# Sprung 1.2.0 -> 2.0.1: auf ausdruecklichen Wunsch des Nutzers, als
# Gesamtsumme mehrerer MK6-Aenderungen (nicht nach der ansonsten in
# README Abschnitt 0a beschriebenen Automatik hergeleitet).
#
# v2.3.0: auf ausdruecklichen Wunsch des Nutzers als MINOR (nicht PATCH)
# erhoeht, da der Funktionsumfang umfangreich ist (Bedien-/Einstellungs-
# Modus, Raeume/Gruppen, frei konfigurierbare externe RTSP-Kameras,
# Drucker-/Raum-Reihenfolge) - siehe UEBERGABE.md v2.3.0 fuer Details.
#
# v2.4.0: erneut MINOR - externe RTSP-Kameras koennen jetzt eine eigene
# Anmeldung (Benutzername/Passwort) sowie einen Raum haben, Kartenlayout
# erlaubt zusaetzlich 4 Spalten, und die Kameras erscheinen direkt als
# eigene Kacheln in der (Raum-)Ansicht statt hinter einem gemeinsamen
# Knopf - siehe UEBERGABE.md v2.4.0.
#
# v2.5.0: MQTT-Sensoren/Schalter koennen jetzt auch OHNE Druckerzuordnung
# angelegt werden ("eigenstaendige" Extras, siehe DashboardApp.
# add_standalone_extra()); behebt den gemeldeten Fehler, dass das
# Hinzufuegen-Formular ohne Drucker-Auswahl wortlos nichts tat.
# Ausserdem: der "Speichern"-Knopf fuer die Druckverlauf-Einstellung
# wurde aus dem "Druckverlauf"-Abschnitt in die Kopfzeile des
# Einstellungen-Modus verschoben (neben "Zur Bedienung"), da seine
# vorherige Position faelschlich wie ein Teil des Druckverlaufs wirkte -
# siehe UEBERGABE.md v2.5.0.
#
# v2.5.1: PATCH, auf ausdruecklichen Nutzerwunsch (reine Fehlerbehebung/
# Anpassung, daher nur die letzte Versionsstelle erhoeht): ALLE
# MQTT-Sensoren zeigen jetzt ein Verlaufsdiagramm (vorher nur die mit
# "display": "temperature"/"humidity"), und der komplette MQTT-Bereich
# im Einstellungen-Modus wurde vom bisherigen Einzel-Modal auf dieselbe
# inline Darstellung wie "Drucker verwalten"/"Raeume"/"Externe RTSP-
# Kameras" umgestellt - siehe UEBERGABE.md v2.5.1.
#
# v2.5.2: PATCH - Diagnose/Fehlerbehebung fuer den gemeldeten Fall
# "Status-Punkt bleibt bei einem Bambu-Drucker (A1 mini) dauerhaft rot,
# obwohl Kamera und Sensorwerte angezeigt werden": (1) MQTT-Verbindungs-
# versuche/-ergebnisse werden jetzt in der Konsole protokolliert
# (Praefix "[MK6-MQTT]", analog zu "[MK6-FFMPEG]"), damit sich eine
# abgelehnte Anmeldung von einem reinen Netzwerkproblem unterscheiden
# laesst; (2) die Temperaturanzeige zeigt jetzt einen Hinweis, wenn die
# Werte wegen fehlender Verbindung nicht mehr aktuell sind, statt
# stillschweigend die letzten bekannten Werte wie Live-Daten aussehen zu
# lassen - siehe UEBERGABE.md v2.5.2.
#
# v2.5.3: PATCH - Weiterfuehrende Diagnose fuer denselben A1-mini-Fall:
# Nutzer-Rueckmeldung mit [MK6-MQTT]-Log (v2.5.2) zeigt "Verbindung
# erfolgreich (rc=0)" gefolgt von "Verbindung unerwartet getrennt (rc=7)"
# - rc=7 ist in der verwendeten MQTT-Client-Bibliothek MQTT_ERR_CONN_LOST
# (ein unerwartet geschlossener Socket, KEINE vom Drucker gesendete
# regulaere Abmeldung und KEIN vom MQTT-Protokoll selbst definierter
# CONNACK-Code). Um ohne Spekulation einzugrenzen, OB der Abbruch sofort
# nach einer bestimmten Aktion (Subscribe auf "report"/"request"-Topic,
# Senden der "pushall"-Anfrage) oder erst nach Ablauf des Keepalive-
# Intervalls (30s) auftritt, wird jetzt (1) jeder dieser Schritte
# einzeln protokolliert und (2) beim Abbruch die Standzeit seit dem
# erfolgreichen Connect mit ausgegeben - siehe UEBERGABE.md v2.5.3.
#
# v2.5.4: PATCH - Nutzer-Rueckmeldung mit v2.5.3 zeigt reproduzierbar
# "Standzeit seit Connect: 0.0s" beim A1 mini - die Trennung (rc=7) folgt
# also SOFORT, nicht erst nach Ablauf des Keepalive-Intervalls. Als
# kontrollierter, einfach umkehrbarer Test wird das rein diagnostische
# Abo des eigenen "request"-Topics (siehe _on_connect()) jetzt fuer
# bambu_family=="a1" probeweise ausgesetzt, um einzugrenzen, ob genau
# dieses Subscribe die sofortige Trennung ausloest - essenzielle
# Funktionen (Status-Report-Abo, "pushall"-Anfrage) sind davon nicht
# betroffen. Siehe UEBERGABE.md v2.5.4 fuer Details und offene Fragen.
#
# v2.5.5: PATCH - Nutzer-Rueckmeldung bestaetigt den v2.5.4-Test: mit
# ausgesetztem Abo des "request"-Topics haelt die Verbindung zum A1 mini
# dauerhaft (Test UND Produktivbetrieb); ein Vergleichstest mit v2.2.19
# (vor Einfuehrung dieses Subscribes) bestaetigt zusaetzlich, dass die
# Drucker-Firmware selbst in Ordnung ist. Keine Code-Aenderung noetig -
# nur Kommentare/Log-Text/Dokumentation von "Experiment"/"probeweise" auf
# bestaetigten, dauerhaften Fix aktualisiert. Siehe UEBERGABE.md v2.5.5.
#
# v2.5.6: PATCH, auf ausdruecklichen Nutzerwunsch: ein eigenstaendiger
# (keinem Drucker zugeordneter) MQTT-Sensor mit "display": "humidity"
# zeigte sein Verlaufsdiagramm bisher in der Default-Farbe (temp-spark,
# rot) statt wie sein druckergebundenes Gegenstueck (siehe extraChip())
# in Blau (humidity-spark) - cardForStandaloneExtra() hat die Sparkline-
# Klasse schlicht nicht anhand von "display" gewaehlt. Fix: dieselbe
# Logik wie in extraChip() ergaenzt. Siehe UEBERGABE.md v2.5.6.
APP_VERSION = "2.9.0"

import os
import sys
import json
import ssl
import ipaddress
import socket
import struct
import shutil
import threading
import time
import uuid
import tempfile
import zipfile
import ftplib
import hashlib
import secrets
import re
import subprocess
import json
import xml.etree.ElementTree as ET
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
from typing import Optional

from flask import Flask, jsonify, request, Response, render_template_string, redirect, send_file
from werkzeug.utils import secure_filename
import paho.mqtt.client as mqtt

# v2.2.8: Nutzer-gemeldet: die eigens fuer Fehlerdiagnose eingebauten
# print()-Konsolenzeilen (u. a. "[MK6] Druckstart angefordert: ...", seit
# v2.2.7) erschienen im OpenWrt-Systemlog (logread) eines per procd-
# Autostart betriebenen Routers ueberhaupt nicht, obwohl Flasks eigene
# Zugriffs-Logzeilen (GET /api/status usw.) zuverlaessig ankamen. Ursache
# (Python-Standardverhalten, keine Vermutung): schreibt ein Python-
# Programm auf eine Standardausgabe, die KEIN Terminal ist (z. B. weil
# procd sie in eine Pipe/den Log-Daemon umleitet), puffert Python
# `sys.stdout` standardmaessig BLOCKWEISE (mehrere KB) statt zeilenweise
# - print()-Aufrufe koennen dadurch lange im Puffer haengen bleiben, statt
# sofort geschrieben zu werden. Flasks Zugriffs-Log laeuft dagegen ueber
# das `logging`-Modul auf `sys.stderr`, das von dieser Umstellung nicht
# betroffen war und deshalb schon vorher zuverlaessig ankam. Fix: direkt
# beim Programmstart `sys.stdout`/`sys.stderr` explizit auf zeilenweise
# Pufferung umgestellt (`reconfigure()`, seit Python 3.7 verfuegbar) -
# betrifft ALLE bestehenden und kuenftigen print()-Diagnosezeilen im
# gesamten Programm, nicht nur die neuen aus v2.2.7, und aendert am
# Verhalten sonst nichts (nur WANN eine Zeile geschrieben wird, nicht WAS).
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except (AttributeError, ValueError):
    # z. B. wenn stdout/stderr umgeleitet und kein TextIOWrapper mehr ist
    # (kommt bei manchen eingebetteten/eingefrorenen Umgebungen vor) -
    # dann lieber ohne Zeilenpufferung weiterlaufen als abzustuerzen.
    pass


# ----------------------------------------------------------------------
# Pfade: Config liegt neben der EXE (bzw. neben app.py im Dev-Betrieb)
# ----------------------------------------------------------------------
def base_dir() -> str:
    if getattr(sys, "frozen", False):          # laeuft als PyInstaller-EXE
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _find_ftps_upload_helper():
    """Sucht nach einer separat mitgelieferten FtpsUploadHelper-exe im
    selben Ordner wie das Hauptprogramm. Siehe ausfuehrliche Begruendung
    bei PrinterConnection._ftps_upload_once() (v1.5.3): eine separate
    Helfer-exe statt eines Selbstaufrufs mit verstecktem Kommandozeilen-
    Flag, um Sicherheitssoftware-Heuristiken nicht zu triggern. Gibt
    None zurueck, wenn keine gefunden wird - der Aufrufer faellt dann
    auf den Selbstaufruf-Mechanismus zurueck (z. B. im Entwicklungs-
    betrieb ohne vorherigen Build der Helfer-exe)."""
    name = "FtpsUploadHelper.exe" if os.name == "nt" else "FtpsUploadHelper"
    candidate = os.path.join(base_dir(), name)
    return candidate if os.path.isfile(candidate) else None


def _find_ffmpeg_binary():
    """Sucht eine FFmpeg-Programmdatei fuer den RTSPS-Kamera-Stream der
    X1/P1/P2/H2/X2-Serie (siehe bambu_rtsp_mjpeg_generator(), v2.2.22).

    FFmpeg ist bewusst KEIN Python-Paket (es gibt dafuer keins - ein
    'pip install ffmpeg-python' o.ae. waere nur ein duenner Wrapper, der
    im Hintergrund trotzdem dieses eigenstaendige, in C geschriebene
    Programm braucht), sondern eine separate ausfuehrbare Datei. Analog
    zu _find_ftps_upload_helper() oben wird sie zuerst NEBEN der
    Haupt-exe gesucht - dorthin legt sie der GitHub-Actions-Workflow
    (build-exe.yml, v2.2.22) beim Bauen automatisch mit hinein, siehe
    dortiger Kommentar. Im Entwicklungsbetrieb (direkter Start per
    "python3 app.py", keine gebaute exe) wird zusaetzlich auf eine
    bereits separat installierte, ueber PATH erreichbare ffmpeg-
    Installation zurueckgegriffen (z. B. per Paketmanager installiert) -
    das ist reine Entwickler-Bequemlichkeit, am Ausgelieferten Verhalten
    (gebuendeltes FFmpeg neben der exe) aendert das nichts.

    Gibt None zurueck, wenn nichts gefunden wird - der Aufrufer zeigt
    dann eine klare Fehlermeldung statt eines kryptischen Absturzes."""
    name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    candidate = os.path.join(base_dir(), name)
    if os.path.isfile(candidate):
        return candidate
    return shutil.which("ffmpeg")


CONFIG_PATH = os.path.join(base_dir(), "config.json")
LOCK = threading.Lock()

# v2.2.21: nach oben vorgezogen (war urspruenglich erst nach DEFAULT_CONFIG
# definiert), damit DEFAULT_CONFIG unten direkt darauf verweisen kann statt
# den Wert 30 ein zweites Mal hart zu codieren.
PRINT_HISTORY_MAX_JOBS = 30  # Standardwert, ueber config.json ueberschreibbar (siehe _resolve_history_max_jobs())

DEFAULT_CONFIG = {
    "server": {
        "host": "0.0.0.0",
        "port": 8000
    },
    "preform_server": "http://localhost:44388",
    # v2.8.0: Oberflaechensprache (siehe SUPPORTED_LANGUAGES weiter unten
    # und den Abschnitt "Mehrsprachigkeit" in UEBERGABE.md) - "de" als
    # Standardwert, damit bestehende config.json-Dateien ohne dieses Feld
    # (siehe load_config()-Migration) unveraendert auf Deutsch weiterlaufen.
    "language": "de",
    # v2.2.21: ueber config.json einstellbar (siehe _resolve_history_max_jobs()
    # und README Abschnitt 3) - Standardwert unveraendert wie zuvor fest
    # codiert (PRINT_HISTORY_MAX_JOBS = 30).
    "history_max_jobs": PRINT_HISTORY_MAX_JOBS,
    "extras_mqtt": {
        "enabled": False,
        "host": "",
        "port": 1883,
        "username": "",
        "password": "",
        "tls": False
    },
    # v2.3.0: Raeume/Gruppen (siehe DashboardApp.add_group() etc.) - jede
    # Gruppe nur {"id","name","order"}, die Zuordnung eines Druckers zu
    # einer Gruppe steht beim jeweiligen Drucker selbst ("group_id",
    # siehe load_config()-Migration unten), nicht umgekehrt bei der
    # Gruppe - vermeidet zwei Quellen der Wahrheit fuer dieselbe Relation.
    "groups": [],
    # v2.3.0: frei benennbare, vom Drucker UNABHAENGIGE RTSP(S)-Kameras
    # (z. B. eine Raumuebersichtskamera) - siehe DashboardApp.
    # add_rtsp_camera()/generic_rtsp_mjpeg_generator().
    "rtsp_cameras": [],
    # v2.5.0: MQTT-Sensoren/Schalter, die KEINEM Drucker zugeordnet sind
    # (z. B. ein Raumthermometer) - vorher musste jeder Sensor/Schalter
    # zwingend an einen bestehenden Drucker haengen ("extras" je Drucker),
    # siehe DashboardApp.add_standalone_extra()/README Abschnitt 8.
    "standalone_extras": [],
    "printers": [],
    # v2.6.0: eigenstaendige Druckauftrags-Warteschlangen mit automatischer
    # Terminierung und Drucker-Zuweisung - siehe DashboardApp.add_farmbot()
    # und den Abschnitt "FarmBot" weiter unten.
    "farmbots": []
}

FORMLABS_TYPES = ("formlabs", "formlabs_wash", "formlabs_cure")
# Alle Creality-"Versionen" nutzen technisch dieselbe Anbindung (Moonraker-
# API, siehe CrealityConnection) - die verschiedenen Typwerte dienen nur
# der Beschriftung/Auswahl im Formular, nicht einer unterschiedlichen
# technischen Anbindung.
CREALITY_TYPES = ("creality_k1", "creality_k1c", "creality_k1max", "creality_k1se", "creality_other")
KNOWN_TYPES = ("bambu",) + FORMLABS_TYPES + ("octoprint",) + CREALITY_TYPES + ("ultimaker",)

# v2.6.0: FarmBot unterstuetzt bewusst nur Druckertypen, fuer die bereits
# ein automatisierter Upload+Druckstart ohne Nutzer-Interaktion am
# Drucker selbst existiert (siehe prepare_print_job()/send_ultimaker_
# print_now()) - OctoPrint und Creality/Klipper haben aktuell KEINEN
# solchen Pfad (nur manuelle Bedienung), waeren also fuer eine
# automatische Warteschlange nicht sinnvoll nutzbar. Siehe UEBERGABE.md
# v2.6.0 fuer die bewusste Entscheidung, das vorerst NICHT zusaetzlich
# nachzuruesten.
FARMBOT_MANUFACTURERS = ("bambu", "ultimaker")

# v2.8.0: Mehrsprachigkeit - die eigentlichen Uebersetzungen liegen
# vollstaendig im Frontend (siehe I18N-Objekt im <script>-Block von
# INDEX_HTML); das Backend kennt nur die gueltigen Sprachcodes zur
# Validierung von config.json/PUT /api/settings. Server-Fehlermeldungen
# (jsonify({"error": ...})) bleiben bewusst auf Deutsch - siehe
# UEBERGABE.md v2.8.0 fuer die Begruendung dieser Abgrenzung.
SUPPORTED_LANGUAGES = ("de", "en", "fr", "es", "zh", "ja", "tr")

# v2.8.0: True, solange seit dem Start dieses Prozesses noch KEINE
# config.json existierte (vor dem allerersten load_config()-Aufruf unten)
# UND seitdem noch keine Einstellung gespeichert wurde - siehe
# get_settings()/update_language() sowie den Sprachauswahl-Dialog, der
# serverseitig genau in diesem Fall beim Oeffnen der Seite als Erstes
# angezeigt werden soll (auf ausdruecklichen Nutzerwunsch). Wird beim
# ersten erfolgreichen PUT /api/settings wieder auf False gesetzt, damit
# der Dialog in diesem Prozess danach nicht erneut erscheint.
CONFIG_WAS_FRESH = False


# ----------------------------------------------------------------------
# MK6 NEUES FEATURE: Druckauftrags-Verlauf pro Drucker
#
# Fuer JEDEN im Dashboard angelegten Drucker (unabhaengig vom Typ) wird
# automatisch ein eigener Ordner neben der exe/dem Skript angelegt
# (siehe base_dir()), in dem die zuletzt ueber das Dashboard an ihn
# GESENDETEN Druckauftraege abgelegt werden - Datei, Zeitstempel und
# (falls extrahierbar) ein Vorschaubild. Tatsaechlich befuellt wird der
# Verlauf aktuell nur fuer Druckertypen, die ueberhaupt Druckauftraege
# per Drag & Drop senden koennen (Bambu Lab, Ultimaker - siehe
# DashboardApp.start_confirm_print_job()/send_ultimaker_print_now());
# fuer alle anderen Typen bleibt der angelegte Ordner leer, das
# Untermenue zeigt dann "noch keine Druckauftraege" an. Der Ordner wird
# bewusst bereits beim Anlegen/Start jedes Druckers erzeugt (nicht erst
# beim ersten Druck), damit er zuverlaessig vorhanden ist, sobald der
# Nutzer manuell hineinschauen moechte.
#
# v2.2.21: die maximale Anzahl aufbewahrter Eintraege pro Drucker ist
# jetzt ueber "history_max_jobs" in config.json einstellbar (Zahl, oder
# null/"unendlich" fuer unbegrenzt) - PRINT_HISTORY_MAX_JOBS (oben, vor
# DEFAULT_CONFIG definiert) ist dabei nur noch der Standardwert, falls
# das Feld in config.json fehlt. Siehe _resolve_history_max_jobs().
# ----------------------------------------------------------------------

# MK6 v1.2.0: Zustaende, in denen ein Drucker als "beschaeftigt" gilt (ein
# Druckauftrag belegt gerade den Druckraum) - dieselbe Zustandsmenge wie
# stateClass() im Frontend fuer den "running"/"paused"-Badge verwendet,
# hier aber fuer eine Backend-Entscheidung: neue Druckauftraege werden in
# diesem Zustand NICHT an den Drucker geschickt, sondern in dessen
# Warteschlange gelegt (siehe PrintQueueStore, DashboardApp.
# is_printer_busy()/enqueue_upload()/start_next_queued_print()). PAUSE/
# PAUSED zaehlt bewusst mit dazu - der vorherige Auftrag ist dann noch
# nicht abgeschlossen, der Druckraum also weiterhin belegt.
PRINTER_BUSY_STATES = {
    "RUNNING", "PRINTING", "WASHING", "CURING", "BUSY", "OPERATIONAL",
    "PAUSE", "PAUSED",
}

# v2.0.1: Fuer Bambu Lab reicht "nicht in PRINTER_BUSY_STATES" allein NICHT
# aus, um die Warteschlange fortzusetzen ("Druckraum leer") - dazwischen
# liegende Uebergangszustaende wie z. B. "PREPARE"/"SLICING" (Drucker
# bereitet bereits den naechsten, ihm intern bekannten Vorgang vor bzw.
# raeumt noch auf) sind zwar nicht in PRINTER_BUSY_STATES, aber ebenfalls
# NICHT "fertig". DashboardApp.is_ready_for_next_print() verlangt bei
# Bambu deshalb EXPLIZIT einen dieser Zustaende: "FINISH" (Druck soeben
# abgeschlossen), "IDLE" (Drucker war zuvor gar nicht am Drucken - z. B.
# frisch gestarteter/verbundener Drucker mit bereits vorbefuellter
# Warteschlange) oder "FAILED" (Druck abgebrochen/fehlgeschlagen - seit
# v2.1.1: der Druckraum ist dann GENAUSO frei wie nach "FINISH", der
# Nutzer muss nur wie gewohnt selbst pruefen/aufraeumen, bevor er
# "Druckraum leer" klickt. Ohne diesen Zustand blieb die Warteschlange
# nach einem fehlgeschlagenen Druck dauerhaft blockiert, da der Drucker
# in "FAILED" verharrt, bis der naechste Druckauftrag gestartet wird -
# ein tatsaechlicher Bug, kein Uebergangszustand wie "PREPARE"/"SLICING").
BAMBU_READY_FOR_NEXT_STATES = {"FINISH", "IDLE", "FAILED"}


def _extract_thumbnail(local_path: str, filename: str):
    """Versucht, ein Vorschaubild fuer einen Verlaufseintrag zu gewinnen.
    Rein informativ (siehe PrintHistoryStore) - liefert bewusst None statt
    eine Ausnahme zu werfen, wenn nichts Passendes gefunden wird.

    Bambu (.gcode.3mf, ein ZIP-Container): Bambu Studio/OrcaSlicer legen
    dort ein Plate-Vorschaubild ab, ueblicherweise unter
    "Metadata/plate_1.png" (Plate 1 - dieses Dashboard druckt immer
    "Metadata/plate_1.gcode", siehe PrinterConnection._request_print()),
    bei manchen Slicer-/Profilversionen alternativ unter
    "Metadata/top_1.png". Community-Tools, die dieselben .gcode.3mf-
    Dateien auswerten, nutzen dieselben Pfade zur Anzeige einer
    Druckvorschau - keine geratenen Felder.

    Ultimaker (.gcode, reiner Cura-Textexport): anders als beim klar
    dokumentierten ZIP-Format von Bambu gibt es fuer eingebettete
    Vorschaubilder in .gcode-Kommentaren keine einheitlich verifizierte
    Struktur ueber alle Cura-Versionen/Profile hinweg. Es wird deshalb
    bewusst KEIN Versuch unternommen, hier zu raten - Eintraege ohne
    Bild zeigen im Verlauf stattdessen ein generisches Datei-Icon, das
    ist kein Fehler."""
    lower = filename.lower()
    if lower.endswith(".gcode.3mf"):
        try:
            with zipfile.ZipFile(local_path) as zf:
                names = zf.namelist()
                for cand in ("Metadata/plate_1.png", "Metadata/top_1.png"):
                    if cand in names:
                        return zf.read(cand)
                # Fallback: irgendein Plate-Vorschaubild, falls die
                # bekannten Namen nicht passen (z. B. abweichende
                # Plate-Nummer bei aelteren/neueren Slicer-Versionen).
                for n in names:
                    if n.startswith("Metadata/plate_") and n.lower().endswith(".png"):
                        return zf.read(n)
        except Exception:
            return None
    return None


# v2.2.14: geschaetzte Druckzeit fuer Verlaufs-/Warteschlangeneintraege
# (siehe README Abschnitt 3h/3j sowie UEBERGABE.md). Rein informativ, wie
# schon bei _extract_thumbnail() oben - ein Fehlschlag liefert bewusst
# None statt eine Ausnahme, der Eintrag wird dadurch nicht ungueltig.
_CURA_TIME_RE = re.compile(rb"^\s*;\s*TIME\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*$", re.MULTILINE)
_CURA_TIME_SCAN_BYTES = 65536  # das Zeitkommentar steht bei Cura im Kopfbereich


def _extract_print_duration_seconds(local_path: str, filename: str):
    """Versucht, die vom Slicer geschaetzte Druckzeit (in Sekunden) aus
    der Datei zu lesen. Rein informativ (siehe PrintHistoryStore/
    PrintQueueStore) - liefert None statt einer Ausnahme, wenn nichts
    Passendes gefunden wird.

    Bambu (.gcode.3mf): "Metadata/slice_info.config" (dieselbe XML-Datei,
    die bereits fuer die Filamentzuordnung ausgewertet wird, siehe
    _parse_plate1_used_filament_indices()) enthaelt pro <plate> ein
    <metadata key="prediction" value="..."/> - dokumentiert als
    geschaetzte Druckzeit in SEKUNDEN fuer diese Plate (Community-
    dokumentiertes 3mf-Format, siehe UEBERGABE.md). Es wird gezielt die
    Plate mit index=1 verwendet (dieselbe, die das Dashboard tatsaechlich
    druckt, siehe PrinterConnection._request_print()).

    Ultimaker (.gcode, Cura-Export): Cura schreibt im Kopfbereich des
    gcode unabhaengig von der gewaehlten Gcode-Variante eine Zeile
    ";TIME:<sekunden>" (die von CuraEngine berechnete Gesamtdruckzeit,
    von der zeilenweisen ";TIME_ELAPSED:..."-Fortschrittsangabe
    innerhalb des Codes zu unterscheiden). Es werden defensiv nur die
    ersten 64 KB der Datei durchsucht (der Kommentar steht im
    Kopfbereich, ein voller Scan waere bei grossen Dateien unnoetig
    teuer) - wird dort nichts gefunden, wird NICHT im gesamten Rest der
    Datei weitergesucht, sondern None zurueckgegeben (kein Ratefeld)."""
    lower = filename.lower()
    if lower.endswith(".gcode.3mf"):
        try:
            with zipfile.ZipFile(local_path) as zf:
                with zf.open("Metadata/slice_info.config") as f:
                    root = ET.parse(f).getroot()
        except Exception:
            return None
        for plate in root.findall("plate"):
            index_val = None
            prediction_val = None
            for meta in plate.findall("metadata"):
                key = meta.get("key")
                if key == "index":
                    index_val = meta.get("value")
                elif key == "prediction":
                    prediction_val = meta.get("value")
            if index_val == "1" and prediction_val is not None:
                try:
                    return int(round(float(prediction_val)))
                except (TypeError, ValueError):
                    return None
        return None
    if lower.endswith(".gcode"):
        try:
            with open(local_path, "rb") as f:
                head = f.read(_CURA_TIME_SCAN_BYTES)
        except Exception:
            return None
        m = _CURA_TIME_RE.search(head)
        if not m:
            return None
        try:
            return int(round(float(m.group(1))))
        except (TypeError, ValueError):
            return None
    return None


def _format_duration_hm(seconds):
    """Formatiert Sekunden als 'Xh Ymin'-Kurzform fuers Backend-Logging
    (das Frontend formatiert dieselben Rohsekunden fuer die Anzeige
    unabhaengig selbst, siehe formatDuration() im <script>-Block)."""
    if seconds is None:
        return "unbekannt"
    total_min = max(0, int(round(seconds / 60)))
    h, m = divmod(total_min, 60)
    return f"{h}h {m}min" if h else f"{m}min"


class PrintHistoryStore:
    """Verwaltet pro Drucker einen eigenen Ordner mit den zuletzt ueber
    das Dashboard an ihn gesendeten Druckauftraegen, damit sie spaeter
    ueber das Untermenue der jeweiligen Drucker-Kachel eingesehen,
    erneut gestartet oder aus dem Zwischenspeicher geloescht werden
    koennen (siehe Kommentarblock oberhalb dieser Klasse).

    Ablage: "<Ordner der exe/des Skripts>/print_history/<drucker_id>/"
    (siehe base_dir()). Jeder Eintrag besteht aus bis zu zwei Dateien
    mit gemeinsamem "<job_id>"-Praefix im jeweiligen Drucker-Ordner:
      <job_id><endung>  - die urspruenglich gesendete Datei (".gcode.3mf"
                          bzw. ".gcode"), unveraendert - wird bei
                          "Erneut drucken" wiederverwendet (siehe
                          DashboardApp.reprint_from_history())
      <job_id>.png      - optionales Vorschaubild (siehe
                          _extract_thumbnail() oben); fehlt, wenn keins
                          gefunden/extrahiert werden konnte
    plus EINEM gemeinsamen "index.json" je Drucker-Ordner (Liste aller
    Eintraege, neueste zuerst)."""

    # v2.2.21: Instanz-Attribut statt fester Klassenkonstante - wird beim
    # Anlegen aus config.json ("history_max_jobs") gespeist, siehe
    # _resolve_history_max_jobs(). None bedeutet "kein Limit".
    def __init__(self, max_jobs_per_printer: Optional[int] = PRINT_HISTORY_MAX_JOBS):
        self._lock = threading.Lock()
        self.max_jobs_per_printer = max_jobs_per_printer

    def dir_for(self, printer_id: str) -> str:
        d = os.path.join(base_dir(), "print_history", printer_id)
        os.makedirs(d, exist_ok=True)
        return d

    def ensure_dir(self, printer_id: str) -> None:
        self.dir_for(printer_id)

    def _index_path(self, printer_id: str) -> str:
        return os.path.join(self.dir_for(printer_id), "index.json")

    def _load_index(self, printer_id: str) -> list:
        path = self._index_path(printer_id)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_index(self, printer_id: str, entries: list) -> None:
        path = self._index_path(printer_id)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

    def list_entries(self, printer_id: str) -> list:
        with self._lock:
            return self._load_index(printer_id)

    def get_entry(self, printer_id: str, job_id: str):
        for e in self.list_entries(printer_id):
            if e.get("job_id") == job_id:
                return e
        return None

    def add_entry(self, printer_id: str, local_path: str, filename: str):
        """Kopiert die soeben gesendete Datei in den Verlaufsordner des
        Druckers, versucht ein Vorschaubild zu extrahieren (best effort)
        und traegt den neuen Eintrag ganz oben (neuester zuerst) in
        index.json ein. Entfernt anschliessend die aeltesten Eintraege
        ueber MAX_JOBS_PER_PRINTER hinaus (samt Dateien) - der Ordner
        waechst dadurch nicht unbegrenzt. Ein Fehler hier wird bewusst
        nur geloggt (still verworfen) - der Verlauf ist ein
        Komfortfeature, ein Problem dabei darf einen bereits erfolgreich
        gestarteten Druck nicht nachtraeglich als Fehler erscheinen
        lassen."""
        try:
            job_id = uuid.uuid4().hex
            job_dir = self.dir_for(printer_id)
            ext = ".gcode.3mf" if filename.lower().endswith(".gcode.3mf") else (os.path.splitext(filename)[1] or ".job")
            stored_path = os.path.join(job_dir, f"{job_id}{ext}")
            shutil.copyfile(local_path, stored_path)

            has_image = False
            try:
                thumb = _extract_thumbnail(local_path, filename)
                if thumb:
                    with open(os.path.join(job_dir, f"{job_id}.png"), "wb") as f:
                        f.write(thumb)
                    has_image = True
            except Exception:
                has_image = False

            try:
                duration_sec = _extract_print_duration_seconds(local_path, filename)
            except Exception:
                duration_sec = None

            entry = {
                "job_id": job_id,
                "filename": filename,
                "file_ext": ext,
                "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "has_image": has_image,
                "duration_sec": duration_sec,
            }
            with self._lock:
                entries = self._load_index(printer_id)
                entries.insert(0, entry)
                # v2.2.21: self.max_jobs_per_printer kann jetzt None sein
                # ("unendlich", siehe _resolve_history_max_jobs()) - ACHTUNG,
                # kein simples entries[self.max_jobs_per_printer:] mehr
                # moeglich: Python wertet "liste[None:]" als "liste[:]" (die
                # GESAMTE Liste), nicht als "nichts" - das haette bei
                # "unendlich" versehentlich ALLE Eintraege als "removed"
                # markiert und ihre Dateien geloescht, obwohl sie im Index
                # behalten werden sollten. Deshalb der explizite Fall.
                if self.max_jobs_per_printer is None:
                    removed = []
                else:
                    removed = entries[self.max_jobs_per_printer:]
                    entries = entries[:self.max_jobs_per_printer]
                self._save_index(printer_id, entries)
            for old in removed:
                self._delete_files(printer_id, old)
            return entry
        except Exception:
            return None

    def get_job_file_path(self, printer_id: str, job_id: str):
        entry = self.get_entry(printer_id, job_id)
        if not entry:
            return None, None
        path = os.path.join(self.dir_for(printer_id), f"{job_id}{entry['file_ext']}")
        return (path, entry["filename"]) if os.path.exists(path) else (None, None)

    def get_thumbnail_path(self, printer_id: str, job_id: str):
        entry = self.get_entry(printer_id, job_id)
        if not entry or not entry.get("has_image"):
            return None
        path = os.path.join(self.dir_for(printer_id), f"{job_id}.png")
        return path if os.path.exists(path) else None

    def delete_entry(self, printer_id: str, job_id: str) -> bool:
        with self._lock:
            entries = self._load_index(printer_id)
            match = next((e for e in entries if e.get("job_id") == job_id), None)
            if not match:
                return False
            entries = [e for e in entries if e.get("job_id") != job_id]
            self._save_index(printer_id, entries)
        self._delete_files(printer_id, match)
        return True

    def _delete_files(self, printer_id: str, entry: dict) -> None:
        job_dir = self.dir_for(printer_id)
        job_id = entry.get("job_id")
        for suffix in (entry.get("file_ext", ".job"), ".png"):
            try:
                os.remove(os.path.join(job_dir, f"{job_id}{suffix}"))
            except Exception:
                pass

    def touch_entry(self, printer_id: str, job_id: str) -> bool:
        """MK6 v1.2.0: Aktualisiert einen BESTEHENDEN Verlaufseintrag auf
        "jetzt gesendet" und verschiebt ihn an die oberste (=neueste)
        Stelle, OHNE einen zusaetzlichen Eintrag anzulegen oder Dateien
        erneut zu kopieren. Wird verwendet, wenn ein bereits im Verlauf
        vorhandener Auftrag ERNEUT an DENSELBEN Drucker gesendet wird
        (direktes "Erneut drucken" oder ueber die Warteschlange mit
        gesetztem history_ref) - ohne dies wuerde derselbe Druckauftrag ein
        zweites Mal in der Liste auftauchen (siehe DashboardApp.
        _record_history_after_send())."""
        with self._lock:
            entries = self._load_index(printer_id)
            match = next((e for e in entries if e.get("job_id") == job_id), None)
            if not match:
                return False
            match["sent_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entries = [e for e in entries if e.get("job_id") != job_id]
            entries.insert(0, match)
            self._save_index(printer_id, entries)
        return True


# ----------------------------------------------------------------------
# MK6 v1.2.0 NEUES FEATURE: Warteschlange je Drucker - wird beim
# Hochladen eines Druckauftrags befuellt, wenn der Ziel-Drucker gerade
# beschaeftigt ist (siehe PRINTER_BUSY_STATES/DashboardApp.
# is_printer_busy()), statt den Auftrag sofort zu senden. Der Nutzer kann
# die Warteschlange einsehen, umsortieren, Eintraege loeschen, manuell
# weitere Auftraege (auch aus dem Verlauf, auch fuer einen ANDEREN
# Drucker) hinzufuegen, und nach Fertigstellung des laufenden Drucks per
# Schaltflaeche ("Druckraum leer") den jeweils aeltesten Auftrag an den
# Drucker senden lassen. Siehe README Abschnitt 3j und UEBERGABE.md
# Abschnitt 5 fuer die vollstaendige Beschreibung.
# ----------------------------------------------------------------------
class PrintQueueStore:
    """Verwaltet pro Drucker eine Warteschlange noch nicht gesendeter
    Druckauftraege. Ablage-Struktur bewusst identisch zu
    PrintHistoryStore (job_id-Praefix je Datei + ein gemeinsames
    index.json je Drucker-Ordner), mit EINEM wichtigen Unterschied in der
    Reihenfolge: neue Eintraege werden hier am ENDE der Liste angehaengt
    (nicht vorne eingefuegt wie beim Verlauf), so dass Position 0 immer
    der AELTESTE und damit naechste zu druckende Auftrag ist - passend
    zur gewuenschten Anzeige-Reihenfolge "aeltester/naechster zuerst".

    Jeder Eintrag kann optional ein "history_ref"-Feld tragen
    ({"printer_id":..., "job_id":...}), gesetzt, wenn der Auftrag
    urspruenglich aus einem Verlaufseintrag stammt (Reprint waehrend der
    Zieldrucker beschaeftigt war, oder bewusst per "In Warteschlange
    legen"/"Zuweisen" aus dem Verlauf hinzugefuegt). Beim tatsaechlichen
    Senden wertet DashboardApp._record_history_after_send() dieses Feld
    aus, damit derselbe Auftrag nicht doppelt im Verlauf auftaucht.

    Ablage: "<Ordner der exe/des Skripts>/print_queue/<drucker_id>/".

    v2.6.0: `root` waehlt den obersten Ablageordner (Default weiterhin
    "print_queue", unveraendertes Verhalten fuer alle bestehenden
    Aufrufer) - FarmBot (siehe DashboardApp.farmbot_queue) nutzt eine
    ZWEITE, unabhaengige Instanz mit `root="farmbot_queue"` und FarmBot-
    IDs statt Drucker-IDs als Schluessel, um dieselbe bereits getestete
    Ablage-/Index-/Dauer-Schaetzungs-Logik (inkl. _extract_print_
    duration_seconds()) ohne Code-Duplizierung wiederzuverwenden, ohne
    mit echten Drucker-Warteschlangen im selben Ordner zu kollidieren."""

    def __init__(self, root: str = "print_queue"):
        self._lock = threading.Lock()
        self._root = root

    def dir_for(self, printer_id: str) -> str:
        d = os.path.join(base_dir(), self._root, printer_id)
        os.makedirs(d, exist_ok=True)
        return d

    def ensure_dir(self, printer_id: str) -> None:
        self.dir_for(printer_id)

    def _index_path(self, printer_id: str) -> str:
        return os.path.join(self.dir_for(printer_id), "index.json")

    def _load_index(self, printer_id: str) -> list:
        path = self._index_path(printer_id)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_index(self, printer_id: str, entries: list) -> None:
        path = self._index_path(printer_id)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

    def list_entries(self, printer_id: str) -> list:
        """Aeltester (=naechster) Auftrag zuerst - siehe Klassenkommentar."""
        with self._lock:
            return self._load_index(printer_id)

    def get_entry(self, printer_id: str, job_id: str):
        for e in self.list_entries(printer_id):
            if e.get("job_id") == job_id:
                return e
        return None

    def add_entry(self, printer_id: str, local_path: str, filename: str, history_ref: dict = None):
        """Kopiert `local_path` in den Warteschlangen-Ordner (das Original
        wird hier NICHT geloescht/verschoben - das entscheidet die
        aufrufende Stelle, siehe DashboardApp.enqueue_upload() vs.
        reprint_from_history()) und haengt den neuen Eintrag am ENDE der
        Liste an. Best effort wie PrintHistoryStore.add_entry() - ein
        Fehler wird nur geloggt (still verworfen), damit ein bereits
        erfolgreich hochgeladenes/laufendes Verhalten nicht nachtraeglich
        als Fehler erscheint."""
        try:
            job_id = uuid.uuid4().hex
            job_dir = self.dir_for(printer_id)
            ext = ".gcode.3mf" if filename.lower().endswith(".gcode.3mf") else (os.path.splitext(filename)[1] or ".job")
            stored_path = os.path.join(job_dir, f"{job_id}{ext}")
            shutil.copyfile(local_path, stored_path)

            has_image = False
            try:
                thumb = _extract_thumbnail(local_path, filename)
                if thumb:
                    with open(os.path.join(job_dir, f"{job_id}.png"), "wb") as f:
                        f.write(thumb)
                    has_image = True
            except Exception:
                has_image = False

            try:
                duration_sec = _extract_print_duration_seconds(local_path, filename)
            except Exception:
                duration_sec = None

            entry = {
                "job_id": job_id,
                "filename": filename,
                "file_ext": ext,
                "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "has_image": has_image,
                "history_ref": history_ref,
                "duration_sec": duration_sec,
            }
            with self._lock:
                entries = self._load_index(printer_id)
                entries.append(entry)
                self._save_index(printer_id, entries)
            return entry
        except Exception:
            return None

    def get_job_file_path(self, printer_id: str, job_id: str):
        entry = self.get_entry(printer_id, job_id)
        if not entry:
            return None, None
        path = os.path.join(self.dir_for(printer_id), f"{job_id}{entry['file_ext']}")
        return (path, entry["filename"]) if os.path.exists(path) else (None, None)

    def get_thumbnail_path(self, printer_id: str, job_id: str):
        entry = self.get_entry(printer_id, job_id)
        if not entry or not entry.get("has_image"):
            return None
        path = os.path.join(self.dir_for(printer_id), f"{job_id}.png")
        return path if os.path.exists(path) else None

    def delete_entry(self, printer_id: str, job_id: str) -> bool:
        with self._lock:
            entries = self._load_index(printer_id)
            match = next((e for e in entries if e.get("job_id") == job_id), None)
            if not match:
                return False
            entries = [e for e in entries if e.get("job_id") != job_id]
            self._save_index(printer_id, entries)
        self._delete_files(printer_id, match)
        return True

    def reorder(self, printer_id: str, ordered_job_ids: list) -> bool:
        """Setzt eine vollstaendig neue Reihenfolge (z. B. nach Verschieben
        eines Eintrags per Pfeil-Buttons im Frontend). `ordered_job_ids`
        muss GENAU dieselbe Menge an job_ids enthalten wie die aktuelle
        Warteschlange, sonst wird NICHTS geaendert - verhindert, dass ein
        veralteter/unvollstaendiger Reorder-Request (z. B. zwei Browser-
        Tabs gleichzeitig offen) Eintraege verliert."""
        with self._lock:
            entries = self._load_index(printer_id)
            by_id = {e.get("job_id"): e for e in entries}
            if set(by_id.keys()) != set(ordered_job_ids) or len(ordered_job_ids) != len(entries):
                return False
            new_entries = [by_id[jid] for jid in ordered_job_ids]
            self._save_index(printer_id, new_entries)
        return True

    def _delete_files(self, printer_id: str, entry: dict) -> None:
        job_dir = self.dir_for(printer_id)
        job_id = entry.get("job_id")
        for suffix in (entry.get("file_ext", ".job"), ".png"):
            try:
                os.remove(os.path.join(job_dir, f"{job_id}{suffix}"))
            except Exception:
                pass


def load_config() -> dict:
    global CONFIG_WAS_FRESH
    if not os.path.exists(CONFIG_PATH):
        # v2.8.0: merken, dass config.json beim Start dieses Prozesses
        # noch nicht existierte - siehe CONFIG_WAS_FRESH/get_settings().
        CONFIG_WAS_FRESH = True
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("server", DEFAULT_CONFIG["server"])
    cfg.setdefault("preform_server", DEFAULT_CONFIG["preform_server"])
    # v2.8.0: ungueltiger/fehlender Sprachcode faellt defensiv auf Deutsch
    # zurueck (unveraendertes Verhalten fuer bestehende config.json-Dateien
    # ohne dieses Feld).
    if cfg.get("language") not in SUPPORTED_LANGUAGES:
        cfg["language"] = DEFAULT_CONFIG["language"]
    cfg.setdefault("history_max_jobs", DEFAULT_CONFIG["history_max_jobs"])
    cfg.setdefault("extras_mqtt", json.loads(json.dumps(DEFAULT_CONFIG["extras_mqtt"])))
    cfg.setdefault("groups", [])
    cfg.setdefault("rtsp_cameras", [])
    cfg.setdefault("standalone_extras", [])
    cfg.setdefault("printers", [])
    cfg.setdefault("farmbots", [])  # v2.6.0, siehe DashboardApp-Abschnitt "FarmBot"
    # v2.3.0: bestehende config.json-Dateien (vor Einfuehrung von Raeumen/
    # Reihenfolge) haben weder "group_id" noch "order" je Drucker/Gruppe/
    # Kamera - hier defensiv ergaenzt, damit aeltere Konfigurationen ohne
    # manuellen Eingriff weiterlaufen (additiv, wie im ganzen Projekt
    # ueblich). "order" wird anhand der bisherigen Listenreihenfolge in
    # config.json vergeben, damit sich an der bisher gezeigten Reihenfolge
    # durch das Update selbst nichts aendert.
    for idx, p in enumerate(cfg["printers"]):
        p.setdefault("extras", [])
        if p.get("type") == "bambu":
            p.setdefault("bambu_family", "x1")
        p.setdefault("group_id", None)
        p.setdefault("order", idx)
    for idx, g in enumerate(cfg["groups"]):
        g.setdefault("order", idx)
    for idx, c in enumerate(cfg["rtsp_cameras"]):
        c.setdefault("order", idx)
        # v2.4.0: Anmeldedaten und Raum-Zuordnung - siehe add_rtsp_camera().
        c.setdefault("username", "")
        c.setdefault("password", "")
        c.setdefault("group_id", None)
    for idx, e in enumerate(cfg["standalone_extras"]):
        e.setdefault("order", idx)
        e.setdefault("group_id", None)
    # v2.6.0: siehe add_farmbot() fuer die Bedeutung der einzelnen Felder.
    for idx, fb in enumerate(cfg["farmbots"]):
        fb.setdefault("order", idx)
        fb.setdefault("enabled", True)
        fb.setdefault("name_suffix", "")
        fb.setdefault("manufacturer", "bambu")
        if fb["manufacturer"] == "bambu":
            fb.setdefault("bambu_family", "x1")
        fb.setdefault("work_start", "08:00")
        fb.setdefault("work_end", "18:00")
        fb.setdefault("max_queue_days", 3)
    return cfg


# v2.2.21: siehe README Abschnitt 3 und Kommentar bei PRINT_HISTORY_MAX_JOBS.
# "history_max_jobs" in config.json darf sein:
#   - eine positive ganze Zahl  -> genau dieses Limit je Drucker
#   - 0, null ODER der String "unendlich" (Gross-/Kleinschreibung egal)
#     -> KEIN Limit, der Verlauf waechst unbegrenzt (Nutzer ist dafuer
#     selbst verantwortlich, den Ordner "print_history/" im Auge zu
#     behalten - siehe README)
# Jeder andere Wert (negative Zahl, Text, der nicht "unendlich" ist, ...)
# gilt als ungueltig: faellt defensiv auf PRINT_HISTORY_MAX_JOBS zurueck,
# statt entweder zu raten oder den Verlauf kaputtzumachen - wird EINMALIG
# beim Start geloggt, damit ein Tippfehler in config.json auffaellt statt
# still ignoriert zu werden.
_history_max_jobs_warned = False


def _resolve_history_max_jobs(raw_value) -> Optional[int]:
    """Wandelt den rohen "history_max_jobs"-Wert aus config.json in ein
    fuer PrintHistoryStore nutzbares Ergebnis um: None bedeutet "kein
    Limit", eine positive Zahl das tatsaechliche Limit. Siehe
    Kommentarblock oberhalb dieser Funktion fuer die akzeptierten
    Werte."""
    global _history_max_jobs_warned
    if raw_value is None:
        return None
    if isinstance(raw_value, str) and raw_value.strip().lower() == "unendlich":
        return None
    if isinstance(raw_value, bool):
        pass  # bool ist in Python eine int-Unterklasse - bewusst wie unten als ungueltig behandeln
    elif isinstance(raw_value, int):
        if raw_value == 0:
            return None
        if raw_value > 0:
            return raw_value
    if not _history_max_jobs_warned:
        _history_max_jobs_warned = True
        print(f"[MK6] Warnung: 'history_max_jobs' in config.json hat einen "
              f"ungueltigen Wert ({raw_value!r}) - erwartet wird eine "
              f"positive ganze Zahl, 0, null oder der Text 'unendlich'. "
              f"Verwende stattdessen den Standardwert ({PRINT_HISTORY_MAX_JOBS}).")
    return PRINT_HISTORY_MAX_JOBS


def save_config(cfg: dict) -> None:
    with LOCK:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)


# ----------------------------------------------------------------------
# MQTT-Client fuer einen einzelnen Bambu Lab Drucker
# ----------------------------------------------------------------------
class PrinterConnection:
    """Haelt die MQTT-Verbindung zu einem Bambu Lab Drucker und den
    zuletzt empfangenen, aufbereiteten Status."""

    PUSHALL_INTERVAL_SEC = 300

    def __init__(self, printer_cfg: dict):
        self.cfg = printer_cfg
        self.id = printer_cfg["id"]
        self.status = {
            "connected": False,
            "last_update": None,
            "gcode_state": "UNKNOWN",
            "progress": 0,
            "file_name": "-",
            "chamber_temp": None,
            "nozzle_temp": None,
            "bed_temp": None,
            "remaining_min": None,
            "ams": [],
            "ams_units": [],  # v2.2.1: Luftfeuchtigkeit je AMS-Einheit, siehe _apply_print_report()
            # v2.2.22: letzter bekannter Wert von "ipcam.rtsp_url" aus dem
            # MQTT-Report - None, solange noch kein Report mit diesem Feld
            # empfangen wurde; der woertliche String "disable", solange am
            # Drucker die Einstellung "LAN Only Liveview" nicht aktiviert
            # ist; sonst die tatsaechliche RTSPS-Stream-URL. Siehe
            # bambu_rtsp_mjpeg_generator() und /camera/<printer_id>.
            "ipcam_rtsp_url": None,
        }
        self._client = None
        self._stop = False
        self._paused = False
        self._last_pushall = 0.0
        self._connected_at = None  # v2.5.3, siehe _on_connect()/_on_disconnect()

    def start(self):
        self._stop = False
        client_id = f"dashboard-{self.id}-{uuid.uuid4().hex[:6]}"
        self._client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
        self._client.username_pw_set("bblp", self.cfg["access_code"])
        self._client.tls_set_context(ssl._create_unverified_context())
        self._client.tls_insecure_set(True)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect
        self._client.reconnect_delay_set(min_delay=1, max_delay=15)
        threading.Thread(target=self._connect_loop, daemon=True).start()

    def _connect_loop(self):
        while not self._stop:
            if self._paused:
                # Waehrend eines FTPS-Uploads bewusst pausiert (siehe
                # pause_mqtt()/resume_mqtt()) - kein Reconnect-Versuch,
                # bis explizit fortgesetzt wird.
                time.sleep(0.5)
                continue
            try:
                self._client.connect(self.cfg["ip"], int(self.cfg.get("mqtt_port", 8883)), keepalive=30)
                self._client.loop_forever(retry_first_connection=True)
            except Exception as e:
                # v2.5.2: vorher wurde ein Verbindungsfehler (z. B. falsche
                # IP/Port, Netzwerk nicht erreichbar, TLS-Handshake
                # schlaegt fehl) komplett verschluckt - der Status-Punkt
                # wurde zwar korrekt rot, aber es gab in der Konsole
                # KEINERLEI Hinweis darauf, WARUM die Verbindung nicht
                # zustande kommt (im Unterschied zu einer abgelehnten
                # Anmeldung, die stattdessen ueber _on_connect() mit einem
                # rc != 0 laeuft, siehe dort). Gemeldeter Fall: A1 mini
                # zeigt dauerhaft rot, obwohl die Kamera - die OHNE MQTT
                # und ohne Anmeldedaten auskommt, siehe
                # bambu_rtsp_mjpeg_generator()/Port 6000 - ein bewegtes
                # Bild liefert; das MQTT-Problem war damit von
                # Netzwerkproblemen NICHT zu unterscheiden, ohne diese
                # Ausgabe. Gleiches Praefix-Schema wie bei [MK6-FFMPEG].
                print(f"[MK6-MQTT] ({self.cfg.get('name', '?')} / {self.cfg.get('ip', '?')}): "
                      f"Verbindungsfehler: {e!r}")
                self.status["connected"] = False
                time.sleep(5)
            if self._stop:
                break
            time.sleep(3)

    def stop(self):
        self._stop = True
        try:
            if self._client:
                self._client.disconnect()
        except Exception:
            pass

    def pause_mqtt(self):
        """Trennt die MQTT-Verbindung voruebergehend und unterdrueckt
        automatisches Reconnect, bis resume_mqtt() aufgerufen wird.

        Hintergrund (v1.5.2): Selbst mit vollstaendiger Prozess-Isolation
        des FTPS-Uploads (siehe _run_ftps_upload_worker()) trat der
        Verbindungsabbruch auf der X1-Serie weiterhin identisch auf -
        das schliesst Python-Thread-/GIL-Konkurrenz als Ursache aus.
        Was in beiden Faellen unveraendert blieb: die dauerhaft aktive
        MQTT-Verbindung im Hauptprozess laeuft parallel zur FTPS-
        Datenverbindung weiter. Vermutung: der eingebettete Netzwerk-
        Stack des Druckers kommt mit einer gleichzeitig aktiven MQTT-
        Verbindung UND einer neuen, datenintensiven FTPS-Verbindung
        nicht zuverlaessig zurecht. Deshalb wird die MQTT-Verbindung
        jetzt waehrend des Uploads bewusst kurz getrennt."""
        self._paused = True
        try:
            if self._client:
                self._client.disconnect()
        except Exception:
            pass

    def resume_mqtt(self):
        """Hebt eine mit pause_mqtt() gesetzte Pause wieder auf - der
        Hintergrund-Thread (_connect_loop) verbindet sich danach
        automatisch neu."""
        self._paused = False

    def wait_for_mqtt_reconnect(self, timeout: float = 15.0) -> bool:
        """Wartet bis zu `timeout` Sekunden darauf, dass die MQTT-
        Verbindung nach resume_mqtt() wiederhergestellt ist (fuer
        _request_print(), das eine aktive Verbindung braucht)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.status.get("connected"):
                return True
            time.sleep(0.3)
        return self.status.get("connected", False)

    def _on_connect(self, client, userdata, flags, rc):
        # v2.5.2: Verbindungsergebnis (Erfolg UND Ablehnung) jetzt in der
        # Konsole protokolliert - vorher wurde ein rc != 0 (z. B. falscher
        # Access Code/Seriennummer -> vom Drucker abgelehnte Anmeldung)
        # kommentarlos nur auf "connected": False gesetzt, ohne jeden
        # Hinweis in der Konsole auf den Grund. `mqtt.connack_string(rc)`
        # liefert dafuer die vom MQTT-Protokoll vorgegebene Klartext-
        # Bedeutung (z. B. "Connection Refused: not authorised").
        label = f"{self.cfg.get('name', '?')} / {self.cfg.get('ip', '?')}"
        try:
            reason = mqtt.connack_string(rc)
        except Exception:
            reason = str(rc)
        print(f"[MK6-MQTT] ({label}): Verbindung {'erfolgreich' if rc == 0 else 'ABGELEHNT'} (rc={rc}: {reason})")
        if rc == 0:
            # v2.5.3: Zeitpunkt der erfolgreichen Verbindung merken, um in
            # _on_disconnect() die Standzeit bis zu einem (unerwarteten)
            # Abbruch protokollieren zu koennen - gemeldeter Fall (A1 mini):
            # Verbindung wird angenommen (rc=0), bricht aber kurz danach mit
            # rc=7 (MQTT_ERR_CONN_LOST, Client-Bibliothek - keine vom
            # Drucker gesendete Abmelde-Nachricht, sondern ein unerwartet
            # geschlossener Socket) wieder ab. Ohne Zeitangabe laesst sich
            # nicht unterscheiden, ob das SOFORT nach einer bestimmten
            # Aktion (Subscribe/Publish, s. u.) oder erst nach Ablauf des
            # Keepalive-Intervalls (30s) passiert - beides deutet auf eine
            # andere Ursache hin. Siehe UEBERGABE.md v2.5.3.
            self._connected_at = time.time()
            self.status["connected"] = True
            topic = f"device/{self.cfg['serial']}/report"
            client.subscribe(topic)
            print(f"[MK6-MQTT] ({label}): Topic '{topic}' abonniert.")
            # v2.2.20: zusaetzlich das eigene "request"-Topic abonnieren -
            # NICHT um eigene Befehle zu verarbeiten (siehe _on_message:
            # Nachrichten auf diesem Topic werden dort explizit NICHT an
            # _apply_print_report() weitergereicht), sondern rein zu
            # Diagnosezwecken: der lokale MQTT-Broker eines Bambu-
            # Druckers liefert laut MQTT-Spezifikation JEDEM auf ein
            # Topic abonnierten Client ALLE darauf veroeffentlichten
            # Nachrichten - unabhaengig davon, WER sie gesendet hat. Ist
            # also gleichzeitig Bambu Studio mit demselben Drucker
            # verbunden und sendet von dort aus einen Druck mit
            # project_file, sieht auch dieses Dashboard diesen Befehl
            # mit. Hintergrund: siehe _log_foreign_project_file_command()
            # unten - damit laesst sich das tatsaechliche, nicht
            # dokumentierte "ams_mapping"-Format fuer AMS-HT-Faecher OHNE
            # Wireshark/Mitmproxy erfassen (Nutzer hat keine Moeglichkeit
            # fuer eine solche Analyse, siehe UEBERGABE.md v2.2.20).
            #
            # v2.5.4/v2.5.5: fuer bambu_family=="a1" bewusst ausgesetzt.
            # Beim A1 mini fuehrte dieses Subscribe reproduzierbar (Standzeit
            # 0,0s, siehe v2.5.3) zu einer sofortigen, unerwarteten Trennung
            # (rc=7/CONN_LOST) - X1/H2 sind davon nicht betroffen. Der v2.5.4-
            # Test (dieses eine Subscribe probeweise ausgesetzt, da als
            # einziges der drei Schritte rein diagnostisch und ohne
            # Funktionsverlust entbehrlich) wurde vom Nutzer bestaetigt: mit
            # ausgesetztem Subscribe haelt die Verbindung zum A1 mini seitdem
            # dauerhaft, sowohl im Test als auch im Produktivbetrieb; ein
            # Vergleichstest mit v2.2.19 (vor Einfuehrung dieses Subscribes
            # in v2.2.20) bestaetigte zusaetzlich, dass die Drucker-Firmware
            # selbst in Ordnung ist. Das "report"-Topic-Abo und die
            # "pushall"-Anfrage (fuer den Status) bleiben unveraendert
            # bestehen. Fuer A1-Drucker bleibt dadurch lediglich die
            # Mitprotokollierung fremder project_file-Kommandos (siehe
            # _log_foreign_project_file_command(), nur fuer die AMS-HT-
            # Mapping-Analyse relevant) ungenutzt - alle anderen Funktionen
            # sind unberuehrt. Siehe UEBERGABE.md v2.5.4/v2.5.5.
            if self.cfg.get("bambu_family", "x1") != "a1":
                self._request_topic = f"device/{self.cfg['serial']}/request"
                client.subscribe(self._request_topic)
                print(f"[MK6-MQTT] ({label}): Topic '{self._request_topic}' abonniert.")
            else:
                print(f"[MK6-MQTT] ({label}): Abo des 'request'-Topics uebersprungen "
                      f"(bambu_family=a1, behebt sofortigen Verbindungsabbruch - "
                      f"siehe UEBERGABE.md v2.5.4/v2.5.5).")
            self._request_pushall(client)
            print(f"[MK6-MQTT] ({label}): 'pushall'-Anfrage gesendet.")
        else:
            self.status["connected"] = False

    def _request_pushall(self, client):
        req_topic = f"device/{self.cfg['serial']}/request"
        payload = {"pushing": {"sequence_id": "0", "command": "pushall", "version": 1, "push_target": 1}}
        try:
            client.publish(req_topic, json.dumps(payload))
            self._last_pushall = time.time()
        except Exception:
            pass

    def _on_disconnect(self, client, userdata, rc):
        # v2.5.2: siehe Kommentar in _on_connect() - dieselbe bisher
        # fehlende Konsolen-Ausgabe, hier fuer den Fall einer (zunaechst
        # erfolgreichen) Verbindung, die anschliessend wieder abbricht
        # (rc != 0 = unerwarteter Abbruch, rc == 0 = regulaeres disconnect()).
        if rc != 0:
            # v2.5.3: Standzeit seit erfolgreichem Connect mitloggen (siehe
            # Kommentar in _on_connect()), damit sich ein sofortiger Abbruch
            # (z. B. ausgeloest durch Subscribe/Publish) von einem erst nach
            # Ablauf des Keepalive-Intervalls auftretenden Abbruch
            # unterscheiden laesst.
            connected_at = getattr(self, "_connected_at", None)
            standzeit = f"{time.time() - connected_at:.1f}s" if connected_at else "unbekannt"
            print(f"[MK6-MQTT] ({self.cfg.get('name', '?')} / {self.cfg.get('ip', '?')}): "
                  f"Verbindung unerwartet getrennt (rc={rc}), Standzeit seit Connect: {standzeit}.")
        self.status["connected"] = False

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8", errors="ignore"))
        except Exception:
            return
        # v2.2.20: Nachrichten auf dem (seit v2.2.20 zusaetzlich
        # abonnierten) "request"-Topic sind Befehle (von diesem
        # Dashboard selbst ODER von einem anderen Client wie Bambu
        # Studio), KEINE Status-Reports - duerfen also nicht an
        # _apply_print_report() gehen (andere Feldbedeutungen,
        # wuerde den Status verfaelschen). Stattdessen rein diagnostisch
        # behandelt, siehe _log_foreign_project_file_command().
        if msg.topic == getattr(self, "_request_topic", None):
            self._log_foreign_project_file_command(payload)
            return
        p = payload.get("print")
        if p:
            self._apply_print_report(p)
        if time.time() - self._last_pushall > self.PUSHALL_INTERVAL_SEC:
            self._request_pushall(client)

    def _log_foreign_project_file_command(self, payload: dict):
        """v2.2.20, rein diagnostisch: protokolliert JEDES
        project_file-Druckstart-Kommando, das auf dem lokalen MQTT-
        Broker dieses Druckers beobachtet wird - ob von diesem
        Dashboard selbst (send_print()) oder von einem ANDEREN im
        selben Netz verbundenen Client (z. B. Bambu Studio, Bambu Handy
        App) gesendet. Hintergrund (siehe UEBERGABE.md, v2.2.20):
        unklar ist, welchen "ams_mapping"/"ams_mapping2"-Wert Bambu
        Studio fuer Faecher einer AMS HT verwendet - ohne Wireshark/
        Mitmproxy-Zugriff (beim Nutzer nicht moeglich) ist das Mitlesen
        auf dem lokalen Broker der einzige Weg, echte Beweisdaten statt
        einer Vermutung zu bekommen, da ein MQTT-Broker jedem
        abonnierten Client alle Nachrichten eines Topics zustellt,
        unabhaengig vom urspruenglichen Absender.

        Filtert bewusst auf command=="project_file" (blendet den sehr
        viel haeufigeren "pushall"-Verkehr aus). Das geloggte Kommando
        ENTHAELT KEINE Zugangsdaten (der Access Code wird nur beim TLS-
        Handshake verwendet, taucht in diesem Kommando nicht auf) und
        kann daher gefahrlos aus der Server-Konsole kopiert und geteilt
        werden."""
        p = payload.get("print")
        if not isinstance(p, dict) or p.get("command") != "project_file":
            return
        print(f"[MK6-DIAG] project_file-Kommando auf dem lokalen Broker von "
              f"'{self.cfg.get('name', self.id)}' beobachtet (von diesem "
              f"Dashboard ODER einem anderen Client wie Bambu Studio "
              f"gesendet). Vollstaendiges Kommando (keine Zugangsdaten "
              f"enthalten):\n"
              f"{json.dumps(payload, indent=2, ensure_ascii=False)}")

    def _apply_print_report(self, p: dict):
        s = self.status
        s["connected"] = True
        s["last_update"] = datetime.now().strftime("%H:%M:%S")

        if "gcode_state" in p:
            s["gcode_state"] = p["gcode_state"]
        if "mc_percent" in p:
            s["progress"] = p["mc_percent"]
        if "subtask_name" in p and p["subtask_name"]:
            s["file_name"] = p["subtask_name"]
        elif "gcode_file" in p and p["gcode_file"]:
            s["file_name"] = p["gcode_file"]
        # v2.2.0: Diagnose fuer "Kammertemperatur zeigt immer -degC" bei
        # Druckern, die laut Druckerfamilie eigentlich einen Kammersensor
        # haben (X1-Serie; A1 hat generell keinen, siehe README/Frontend-
        # Ausblendung fuer bambu_family=="a1"). "chamber_temper" ist der
        # bekannte (getippte) Feldname im offiziellen Bambu-MQTT-Protokoll
        # - als defensiver Fallback wird zusaetzlich der (theoretisch
        # denkbare, in manchen Firmware-Staenden kolportierte) Feldname
        # OHNE den Tippfehler akzeptiert, falls "chamber_temper" fehlt.
        # Liefert WEDER das eine NOCH das andere Feld einen Wert, obwohl
        # die konfigurierte Druckerfamilie einen Kammersensor haben sollte,
        # wird das EINMALIG pro Verbindung geloggt (Server-Konsole) - das
        # ist die Grundlage, um mit einer echten Rohnutzlast (kompletter
        # "print"-Report dieses Druckers) den tatsaechlichen Feldnamen zu
        # verifizieren, statt hier ungeprueft weiterzuraten.
        if "chamber_temper" in p:
            s["chamber_temp"] = p["chamber_temper"]
        elif "chamber_temp" in p:
            s["chamber_temp"] = p["chamber_temp"]
        else:
            # v2.2.13: Nutzer-Vorschlag (noch NICHT extern/per Quelle
            # bestaetigt, siehe UEBERGABE.md): fuer X1C und H2S soll die
            # Kammertemperatur unter "device.ctc.info.temp" liegen ("ctc"
            # vermutlich "Chamber Temperature Control"). Struktur von
            # "info" (Objekt oder Liste) ist nicht gesichert bekannt -
            # daher rein defensiv, beide Formen versucht, und bei Erfolg
            # EINMALIG geloggt (nicht stillschweigend uebernommen), damit
            # sich der Wert gegen die tatsaechliche Kammertemperatur am
            # Drucker pruefen laesst, bevor er als endgueltig geloest gilt.
            ctc_temp = None
            try:
                info = p.get("device", {}).get("ctc", {}).get("info")
                if isinstance(info, dict):
                    ctc_temp = info.get("temp")
                elif isinstance(info, list):
                    for entry in info:
                        if isinstance(entry, dict) and entry.get("temp") is not None:
                            ctc_temp = entry.get("temp")
                            break
            except (AttributeError, TypeError):
                ctc_temp = None
            if ctc_temp is not None:
                s["chamber_temp"] = ctc_temp
                if not getattr(self, "_chamber_ctc_logged", False):
                    self._chamber_ctc_logged = True
                    print(f"[MK6] Kammertemperatur ueber 'device.ctc.info.temp' "
                          f"gefunden: Drucker='{self.cfg.get('name', self.id)}' "
                          f"Wert={ctc_temp!r} - bitte pruefen, ob das mit der "
                          f"tatsaechlichen Kammertemperatur am Drucker uebereinstimmt "
                          f"(noch nicht extern bestaetigtes Feld, siehe UEBERGABE.md).")
            elif self.cfg.get("bambu_family", "x1") != "a1" and not getattr(self, "_chamber_missing_logged", False):
                self._chamber_missing_logged = True
                print(f"[MK6] Hinweis: Drucker '{self.cfg.get('name', self.id)}' "
                      f"(Familie: {self.cfg.get('bambu_family', 'x1')}) liefert kein "
                      f"'chamber_temper'/'chamber_temp'/'device.ctc.info.temp'-Feld im "
                      f"MQTT-Report. Rohreport-Schluessel in diesem Update: "
                      f"{sorted(p.keys())}")
        if "nozzle_temper" in p:
            s["nozzle_temp"] = p["nozzle_temper"]
        if "bed_temper" in p:
            s["bed_temp"] = p["bed_temper"]
        if "mc_remaining_time" in p:
            s["remaining_min"] = p["mc_remaining_time"]
        # v2.2.22: fuer den RTSPS-Kamera-Stream (siehe
        # bambu_rtsp_mjpeg_generator()) - das "ipcam"-Unterobjekt steckt
        # (wie "ams" auch) nicht in jedem einzelnen MQTT-Update, sondern
        # typischerweise nur in vollen "pushall"-Antworten. Deshalb wie
        # bei den uebrigen optionalen Feldern hier NUR bei Vorhandensein
        # uebernehmen (sonst bliebe der zuletzt bekannte Wert erhalten,
        # statt bei jedem Teil-Update faelschlich auf None zu fallen).
        ipcam = p.get("ipcam")
        if isinstance(ipcam, dict) and "rtsp_url" in ipcam:
            s["ipcam_rtsp_url"] = ipcam["rtsp_url"]

        ams_root = p.get("ams", {}).get("ams")
        if isinstance(ams_root, list):
            slots = []
            units = []
            for unit in ams_root:
                for tray in unit.get("tray", []):
                    slots.append({
                        "slot": f'{unit.get("id", "0")}-{tray.get("id", "0")}',
                        "type": tray.get("tray_type") or "-",
                        "color": _argb_to_css(tray.get("tray_color")),
                        "remain": tray.get("remain", -1)
                    })
                # v2.2.1: Luftfeuchtigkeit je AMS-Einheit (nicht je Fach) -
                # community-dokumentiertes Feld "humidity" im Bambu-MQTT-
                # Protokoll (u. a. genutzt von der Home-Assistant-Bambu-
                # Lab-Integration), eine STUFE von 1 (trocken) bis 5
                # (feucht) - KEIN Prozentwert. Defensiv geparst: fehlt das
                # Feld oder ist es nicht als Zahl auswertbar, wird die
                # Einheit einfach ohne Feuchte-Angabe gefuehrt, statt zu
                # raten.
                humidity = None
                try:
                    if unit.get("humidity") is not None:
                        humidity = int(unit["humidity"])
                except (TypeError, ValueError):
                    humidity = None
                # v2.2.7: Nutzer meldete, dass ein H2S (AMS 2 Pro) die
                # Luftfeuchte tatsaechlich als 44% anzeigt, das Dashboard
                # aber nur "1" zeigte. Recherche (u. a. greghesp/ha-bambulab
                # Issue #1235 und maziggy/bambuddy Issue #3140) ergab: das
                # aeltere AMS (vier Slots) liefert NUR "humidity" (Stufe
                # 1-5). Das neuere AMS 2 Pro liefert ZUSAETZLICH das Feld
                # "humidity_raw" - den tatsaechlichen Prozentwert (0-100).
                # Beide Felder koennen parallel vorhanden sein. Ebenfalls
                # defensiv geparst, keine Annahme ueber Wertebereich.
                humidity_raw = None
                try:
                    if unit.get("humidity_raw") is not None:
                        humidity_raw = int(unit["humidity_raw"])
                except (TypeError, ValueError):
                    humidity_raw = None
                units.append({
                    "id": unit.get("id", "0"),
                    "humidity": humidity,
                    "humidity_raw": humidity_raw,
                })
            s["ams"] = slots
            s["ams_units"] = units

    # ------------------------------------------------------------------
    # Druckauftrag per Drag & Drop senden
    #
    # Bambu-Drucker haben keine REST-Upload-API. Der Ablauf ist:
    #   1. Datei per FTPS (Port 990, IMPLIZITES TLS - nicht das normale
    #      "AUTH TLS", siehe ImplicitFtpTls unten) auf den Drucker
    #      hochladen. Login: Benutzer "bblp", Passwort = Access Code.
    #   2. Ueber den bereits bestehenden MQTT-Kanal ein "project_file"-
    #      Kommando senden, das auf die hochgeladene Datei zeigt.
    #
    # Quelle/Recherche (siehe UEBERGABE.md Abschnitt 6, Punkt 1 - keine
    # geratenen Endpunkte): community-dokumentiertes MQTT-Kommando
    # "project_file" (Bambu-Forum "MQTT for A1"), FTPS Port 990 mit
    # implizitem TLS (OpenBambuAPI-Projekt, diverse Community-Tools).
    #
    # WICHTIGE EINSCHRAENKUNG: Es werden bewusst nur bereits fertig
    # gesclicte .gcode.3mf-Dateien (Export aus Bambu Studio/OrcaSlicer)
    # unterstuetzt. Rohe .gcode-Dateien lassen sich laut mehreren
    # Community-Quellen nicht zuverlaessig per MQTT starten.
    #
    # WICHTIGE VORAUSSETZUNG: Auf dem Drucker muss "Developer Mode" /
    # LAN-Modus aktiviert sein (v2.2.18-Korrektur: LOKAL am Drucker
    # ueber dessen eigene Einstellungen, NICHT in der Bambu Handy App -
    # im reinen LAN-Modus ist die Verbindung zur App gekappt). Ohne das
    # lehnt neuere Firmware den project_file-Befehl ab. Siehe README,
    # Abschnitt "Bambu Lab: Druckauftrag per Drag & Drop senden".
    #
    # AUTOMATISCHE AMS-ZUORDNUNG (siehe UEBERGABE.md Abschnitt 7 fuer
    # Quellenlage): Die .gcode.3mf-Datei enthaelt in
    # "Metadata/project_settings.config" (JSON) die Arrays
    # "filament_colour" und "filament_type" (0-basiert, ein Eintrag pro
    # im Slicer verwendetem Filament). Diese werden gegen die *aktuell*
    # vom Drucker gemeldeten AMS-Faecher (self.status["ams"], live per
    # MQTT-Report) nach Farbe+Typ gematcht und dem Nutzer als Vorschlag
    # angezeigt (siehe preview_print), BEVOR tatsaechlich gedruckt wird -
    # der Nutzer kann jede Zuordnung im Browser wie in Bambu Studio von
    # Hand korrigieren, bevor send_print() sie final an den Drucker
    # sendet. Es wird also nirgends mehr "blind" gedruckt.
    # ------------------------------------------------------------------
    def preview_print(self, local_path: str):
        """Liest Filament-Infos aus der .gcode.3mf und schlaegt eine
        AMS-Zuordnung anhand der aktuell bekannten AMS-Faecher vor. Wirft
        keine Exception bei nicht auswertbarer Datei - liefert dann leere
        Listen, das Frontend zeigt dann "keine AMS-Zuordnung moeglich".

        WICHTIG (v1.6.2 - Bugfix "Zuordnungstabelle des AMS konnte nicht
        abgerufen werden" bei Mehrfarb-Drucken): Jedes zurueckgegebene
        Filament behaelt sein ORIGINALES 0-basiertes "index"-Feld aus
        der .3mf (siehe _parse_3mf_filaments()), NICHT die Position in
        dieser (ggf. gefilterten) Liste - das Frontend MUSS dieses Feld
        beim Zusammenbauen des finalen "ams_mapping"-Arrays als Position
        verwenden. "total_filaments" wird zusaetzlich zurueckgegeben,
        damit das Frontend ein VOLLSTAENDIG GROSSES Array bauen kann
        (mit -1 an allen nicht benoetigten Positionen) - der Drucker
        erwartet offenbar ein Array, dessen Positionen den originalen
        Projekt-Filament-IDs entsprechen, nicht ein kompaktes Array nur
        der auf dieser Platte benoetigten Filamente. Wurde das kompakte
        Array (Position = Index in der gefilterten Liste) gesendet,
        quittierte der Drucker das bei Mehrfarb-Drucken mit "Failed to
        get AMS mapping table" - siehe UEBERGABE.md fuer Details.

        WICHTIG (v2.2.20: AMS HT zunaechst bewusst ausgeschlossen, v2.2.21:
        Ausschluss wieder aufgehoben): v2.2.20 hatte Faecher einer AMS HT
        hier bewusst von der automatischen Zuordnung ausgenommen, weil
        _slot_to_flat_index() faelschlich einen sinnlosen Wert (128*4=512)
        berechnete. Ein vom Nutzer per Diagnose-Log (siehe
        _log_foreign_project_file_command()) eingefangener ECHTER
        project_file-Befehl von Bambu Studio hat inzwischen den
        tatsaechlich erwarteten Wert bestaetigt (siehe korrigierte
        _slot_to_flat_index() sowie UEBERGABE.md, v2.2.21) - AMS-HT-
        Faecher werden deshalb wieder ganz normal wie jedes andere Fach
        behandelt."""
        filaments, total_filaments = _parse_3mf_filaments(local_path)
        ams_trays_raw = list(self.status.get("ams") or [])
        ams_trays = [{
            "flat_index": _slot_to_flat_index(t.get("slot")),
            "slot": t.get("slot"),
            "type": t.get("type"),
            "color": _normalize_hex(t.get("color")) or "666666",
            "remain": t.get("remain"),
        } for t in ams_trays_raw]

        used_slots = set()
        suggestion = []
        for fil in filaments:
            best = _find_matching_tray(fil, ams_trays_raw, used_slots)
            if best is None:
                suggestion.append(-1)
            else:
                used_slots.add(best["slot"])
                suggestion.append(_slot_to_flat_index(best["slot"]))

        return {
            "filaments": [
                {"index": f["index"], "color": f["color"] or "666666", "type": f["type"],
                 "suggested_tray": suggestion[i]}
                for i, f in enumerate(filaments)
            ],
            "ams_trays": ams_trays,
            "total_filaments": total_filaments,
        }

    def send_print(self, local_path: str, remote_name: str, mapping, on_progress=None):
        """Laedt local_path per FTPS auf den Drucker hoch und startet den
        Druck mit der vom Nutzer (im Browser) bestaetigten/korrigierten
        AMS-Zuordnung. mapping ist eine Liste von AMS-Fach-Indizes (-1 =
        kein AMS / externe Spule fuer dieses Filament) oder None/leer,
        wenn ganz ohne AMS gedruckt werden soll. on_progress(sent, total)
        wird waehrend des Uploads wiederholt aufgerufen (fuer die
        Fortschrittsanzeige im Browser). Wirft eine Exception mit
        Klartext-Fehlermeldung bei Problemen."""
        use_ams = bool(mapping) and any(m is not None and int(m) >= 0 for m in mapping)
        ams_summary = {
            "use_ams": use_ams,
            "mapping": [int(m) for m in mapping] if mapping else None,
            "total": len(mapping) if mapping else 0,
            "matched": sum(1 for m in (mapping or []) if m is not None and int(m) >= 0),
        }
        # WICHTIG (v1.5.2): MQTT-Verbindung waehrend des Uploads bewusst
        # kurz trennen - siehe ausfuehrliche Begruendung bei
        # pause_mqtt(). Bei einem Fehlschlag wird die Verbindung zwar
        # ebenfalls wieder freigegeben, aber NICHT blockierend auf den
        # Reconnect gewartet (der Fehler soll dem Nutzer sofort
        # angezeigt werden, nicht erst nach bis zu 15s Wartezeit) - das
        # Reconnect passiert dann einfach im Hintergrund. Nur bei Erfolg
        # wird gewartet, weil der nachfolgende MQTT-Druckbefehl
        # (_request_print) eine aktive Verbindung braucht.
        self.pause_mqtt()
        try:
            self._ftps_upload(local_path, remote_name, on_progress=on_progress)
        except Exception:
            self.resume_mqtt()
            raise
        self.resume_mqtt()
        self.wait_for_mqtt_reconnect(timeout=15)
        self._request_print(remote_name, ams_summary)
        return ams_summary

    def _ftps_upload(self, local_path: str, remote_name: str, on_progress=None):
        # Bis zu 3 Versuche mit jeweils komplett neuer Verbindung, statt
        # beim ersten TLS-Ausrutscher aufzugeben - defensive Robustheit
        # (analog zu Punkt 2 in UEBERGABE.md, "defensives Parsen als
        # Fallback"). Alle 3 Versuche werden gesammelt und am Ende
        # gemeinsam gezeigt, nicht nur der letzte - das war entscheidend
        # fuer die Diagnose in v1.4.1-v1.4.3 (siehe UEBERGABE.md,
        # Chronologie) und bleibt aus Diagnosegruenden bestehen.
        #
        # WICHTIG (v1.5.8): Ein isolierter Test von nur `reuse_session`
        # (v1.5.7) hat gezeigt, dass der A1-Mini-Timeout nach 100%
        # uebertragener Bytes UNABHAENGIG davon auftritt (mit UND ohne
        # Sitzungs-Wiederverwendung identisch) - die Ursache lag also
        # nicht (nur) dort. Vergleich mit der zuletzt beim A1 Mini
        # bestaetigt funktionierenden Version (v1.4.5) zeigte: dort war
        # zusaetzlich KEIN TLS-Versions-Deckel aktiv. Deshalb jetzt zwei
        # vollstaendige Profile ("x1"/"a1", siehe FTPS_PROFILES) statt
        # eines einzelnen Schalters - werden zwischen den 3 Versuchen
        # alterniert, damit innerhalb der 3 Versuche garantiert die
        # fuer das jeweilige Druckermodell passende Kombination
        # gefunden wird, unabhaengig davon, welches Modell tatsaechlich
        # am anderen Ende haengt.
        # WICHTIG (v1.6.1): Die Reihenfolge richtet sich jetzt nach der
        # beim Anlegen des Druckers gewaehlten Druckerfamilie
        # (`self.cfg["bambu_family"]`, "x1" oder "a1") - das bekannte
        # Modell wird beim ERSTEN Versuch probiert (kein unnoetiger
        # Fehlversuch mehr, wenn das Modell bereits bekannt ist), das
        # jeweils andere Profil bleibt als automatischer Fallback fuer
        # Versuch 2 erhalten (z. B. falls die Familie falsch gewaehlt
        # wurde oder sich das Druckermodell geaendert hat), Versuch 3
        # wiederholt das urspruenglich bekannte Profil sicherheitshalber.
        # WICHTIG (v1.6.7): "bambu_family" (x1/a1/h2, vom Nutzer beim
        # Anlegen gewaehlt) wird ueber BAMBU_FAMILY_TO_FTPS_PROFILE auf
        # ein TATSAECHLICHES Verbindungsprofil abgebildet - fuer "h2"
        # aktuell identisch zu "x1" (siehe dortiger Kommentar). Die
        # Alternierung selbst bleibt unveraendert: das ermittelte Profil
        # steht an erster UND dritter Stelle, das jeweils andere Profil
        # (meist "a1") bleibt als automatischer Fallback fuer Versuch 2
        # erhalten.
        known_family = self.cfg.get("bambu_family", "x1")
        known_profile = BAMBU_FAMILY_TO_FTPS_PROFILE.get(known_family, "x1")
        other_profile = "a1" if known_profile == "x1" else "x1"
        profile_pattern = [known_profile, other_profile, known_profile]
        attempts = []
        for attempt in range(1, 4):
            profile_name = profile_pattern[attempt - 1]
            label = f"Profil {profile_name}"
            try:
                self._ftps_upload_once(local_path, remote_name, on_progress=on_progress, profile_name=profile_name)
                return
            except (OSError, RuntimeError, subprocess.SubprocessError) as e:
                attempts.append(f"Versuch {attempt} ({label}): {e}")
                # v2.2.6: "553 Could not create file" ist KEIN Verbindungs-/
                # TLS-Problem, sondern eine inhaltliche Ablehnung durch den
                # FTP-Server des Druckers (Anmeldung und TLS haben also
                # funktioniert) - weitere Versuche mit anderem TLS-Profil
                # sind sinnlos. Typische Ursache: am Drucker ist kein
                # beschreibbarer Speicher eingebunden. Bei der H2-Serie
                # (H2D/H2S, ebenso P2S) erreicht FTPS AUSSCHLIESSLICH den
                # USB-Stick, NICHT den internen Speicher (Bambu Studio
                # nutzt fuer den internen Speicher einen eigenen,
                # undokumentierten Weg) - ohne eingesteckten USB-Stick
                # scheitert jeder FTPS-Upload genau so. Quellen:
                # synman/bambu-printer-manager Issue #64 ("FTPS reaches the
                # USB stick and nothing else"), Bambu-Wiki "Failed to send
                # print files" (Speichermedium fehlt/voll/zu langsam).
                if "553" in str(e):
                    raise RuntimeError(
                        f"Der Drucker hat das Anlegen der Datei abgelehnt "
                        f"(FTP 553 \"Could not create file\") - die Verbindung "
                        f"selbst funktioniert, aber am Drucker ist kein "
                        f"beschreibbarer Speicher verfuegbar.\n"
                        f"Bei H2D/H2S (und P2S): Uploads per LAN/FTPS landen "
                        f"AUSSCHLIESSLICH auf einem eingesteckten USB-Stick, "
                        f"nicht im internen Speicher - bitte einen USB-Stick "
                        f"(FAT32 oder exFAT, mind. USB 2.0) einstecken und am "
                        f"Druckerdisplay pruefen, dass er erkannt wird.\n"
                        f"Bei X1/P1/A1: pruefen, ob eine microSD-Karte "
                        f"eingesteckt, erkannt und nicht voll/schreibgeschuetzt "
                        f"ist.\n"
                        f"Details: Versuch {attempt} ({label}): {e}"
                    )
                if attempt < 3:
                    time.sleep(1.5 * attempt)
        attempts_text = "\n".join(attempts)
        raise RuntimeError(
            f"FTPS-Upload nach 3 Versuchen fehlgeschlagen:\n{attempts_text}\n"
            f"Falls das auf eine PASV-Datenverbindung hinweist: bitte pruefen, "
            f"ob Dashboard-Rechner und Drucker im selben Netzwerksegment ohne "
            f"Client-/AP-Isolation und ohne dazwischenliegende Firewall/VPN/"
            f"Docker-NAT sind. Ansonsten: Developer Mode am Drucker pruefen "
            f"und ob am Display selbst ein Fehler angezeigt wird."
        )

    def _ftps_upload_once(self, local_path: str, remote_name: str, on_progress=None, profile_name: str = "x1"):
        # ------------------------------------------------------------
        # WICHTIG (v1.5.3) - Der Upload laeuft ueber eine SEPARATE,
        # eigenstaendig mitgelieferte Helfer-exe (FtpsUploadHelper),
        # NICHT mehr per Selbstaufruf der Haupt-exe mit einem
        # versteckten Sentinel-Flag (wie in v1.5.1/v1.5.2).
        #
        # Vorgeschichte: Trotz Prozess-Isolation (v1.5.1) und MQTT-Pause
        # waehrend des Uploads (v1.5.2) scheiterte der Upload im
        # Dashboard weiterhin reproduzierbar - selbst auf einem
        # komplett isolierten Testnetzwerk mit nur Windows Defender,
        # mit identischer Datei, bei der ein eigenstaendiges Diagnose-
        # Tool (ftps_test_minimal.py, praktisch identische FTPS-Logik)
        # im direkten Vergleich zuverlaessig funktionierte. Der einzige
        # verbleibende strukturelle Unterschied: das Dashboard rief
        # sich SELBST mit einem versteckten Kommandozeilen-Argument neu
        # auf ("--ftps-upload-worker"). Ein Programm, das eine Kopie
        # von sich selbst mit einem versteckten Flag startet, ist ein
        # Verhaltensmuster, das Sicherheitssoftware (u. a. Windows
        # Defender) aehnlich wie manche Schadsoftware-Lademechanismen
        # behandeln kann - mit moeglichen Auswirkungen auf dessen
        # Netzwerkverkehr, auch ohne dass etwas sichtbar blockiert wird.
        #
        # Loesung: eine separate, eindeutig benannte Helfer-exe
        # (FtpsUploadHelper.exe, aus ftps_upload_helper.py gebaut, liegt
        # neben der Haupt-exe) wird stattdessen aufgerufen. "Programm A
        # startet Programm B" ist ein voellig normaler, unauffaelliger
        # Vorgang fuer Sicherheitssoftware. Der Selbstaufruf-Mechanismus
        # (_run_ftps_upload_worker() weiter unten) bleibt als Fallback
        # bestehen, falls die Helfer-exe (noch) nicht gefunden wird
        # (z. B. im Entwicklungsbetrieb ohne vorherigen Build).
        #
        # WICHTIG (v1.5.8): `profile_name` ("x1"/"a1", siehe
        # FTPS_PROFILES) wird als 5. Kommandozeilen-Argument an die
        # Helfer-exe bzw. den Selbstaufruf-Fallback durchgereicht -
        # siehe _ftps_upload() fuer die Begruendung (X1-Serie braucht
        # TLS-1.2-Deckel + Sitzungs-Wiederverwendung, A1 Mini braucht
        # freie TLS-Aushandlung ohne Sitzungs-Wiederverwendung).
        # ------------------------------------------------------------
        helper_path = _find_ftps_upload_helper()
        if helper_path:
            cmd = [helper_path, self.cfg["ip"], self.cfg["access_code"], local_path, remote_name, profile_name]
        else:
            exe = sys.executable
            if getattr(sys, "frozen", False):
                cmd = [exe, "--ftps-upload-worker", self.cfg["ip"], self.cfg["access_code"], local_path, remote_name, profile_name]
            else:
                cmd = [exe, os.path.abspath(__file__), "--ftps-upload-worker",
                       self.cfg["ip"], self.cfg["access_code"], local_path, remote_name, profile_name]

        total_size = os.path.getsize(local_path)
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        result = None
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except Exception:
                    continue  # unerwartete Ausgabe ignorieren, kein Grund zum Abbruch
                if msg.get("type") == "progress":
                    if on_progress:
                        try:
                            on_progress(msg.get("sent", 0), msg.get("total", total_size))
                        except Exception:
                            pass
                elif msg.get("type") == "diag":
                    # v2.2.9: FTPS-Verzeichnislisting aus dem Upload-
                    # Subprozess (Helfer-exe oder Selbstaufruf-Fallback,
                    # siehe dortiger Kommentar) - dient ausschliesslich der
                    # Fehlersuche zum offenen H2S-Druckstart-Problem
                    # ("Nicht unterstuetzter Pfad oder Name der
                    # Druckdatei", siehe UEBERGABE.md v2.2.6/v2.2.7) und
                    # aendert am Upload-Ablauf selbst nichts.
                    print(f"[MK6] FTPS-Diagnose (Drucker='{self.cfg.get('name', self.id)}', "
                          f"Profil={profile_name}): {msg.get('message')}")
                elif msg.get("type") in ("done", "error"):
                    result = msg
        finally:
            try:
                proc.wait(timeout=30)
            except Exception:
                proc.kill()
                proc.wait()

        if result is None:
            stderr_text = ""
            try:
                stderr_text = (proc.stderr.read() or "").strip()
            except Exception:
                pass
            raise RuntimeError(
                f"Upload-Prozess wurde beendet, ohne ein Ergebnis zu melden "
                f"(Exit-Code {proc.returncode}).{(' ' + stderr_text) if stderr_text else ''}"
            )

        if result.get("type") == "error":
            sent = result.get("sent", 0)
            total = result.get("total", total_size)
            percent = int(sent * 100 / total) if total else 0
            raise RuntimeError(
                f"Verbindung ist waehrend der Dateiuebertragung abgebrochen "
                f"(bei {sent}/{total} Bytes, {percent}%): {result.get('message')}. "
                f"Die Datei ist damit unvollstaendig auf dem Drucker "
                f"gelandet (falls ueberhaupt)."
            )

        if on_progress:
            on_progress(total_size, total_size)

    def _request_print(self, remote_name: str, ams_summary: dict = None):
        if not self._client or not self.status.get("connected"):
            raise RuntimeError(
                "Keine aktive MQTT-Verbindung zum Drucker - Druckauftrag "
                "kann nicht gestartet werden."
            )
        ams_summary = ams_summary or {}
        # WICHTIG (v1.5.6): Der Befehl enthielt bisher nur eine Teilmenge
        # der von Bambu Studio selbst gesendeten Felder. Recherche nach
        # einem gemeldeten Problem ("Druck startet, haengt dann aber beim
        # Materialladen - nur bei bestimmten Materialien wie ASA-CF, PLA
        # unbetroffen") ergab per Vergleich mit mehreren unabhaengigen,
        # dokumentierten Referenz-Payloads (Cinder's Blog "Bambu AMS
        # Filament Mapping", als "funktioniert zuverlaessig" bestaetigt;
        # OpenBambuAPI-Projekt, Doridian/OpenBambuAPI auf GitHub): es
        # fehlten mehrere Felder, allen voran `bed_type` - ohne dieses
        # Feld ist unklar, welchen Druckbett-Typ die Firmware annimmt,
        # was insbesondere bei anspruchsvolleren Materialien (hohe
        # Bett-/Duesentemperatur, wie ASA-CF) zu Problemen im weiteren
        # Startablauf fuehren kann. Ergaenzt um den vollstaendigen,
        # dokumentierten Feldsatz - alle zusaetzlichen Felder sind laut
        # beiden Quellen fuer lokale (nicht Cloud-)Drucke unkritisch mit
        # "0" bzw. "auto" zu befuellen.
        job_name = os.path.splitext(os.path.splitext(remote_name)[0])[0] or remote_name
        # v2.2.10: Nutzer lieferte fuer einen H2S mit eingestecktem
        # USB-Stick den vollstaendigen Beweis: das FTPS-Verzeichnislisting
        # (v2.2.9-Diagnose) zeigt die hochgeladene Datei DIREKT im
        # FTP-Wurzelverzeichnis (kein "cache"-Unterordner, widerlegt die
        # in UEBERGABE.md v2.2.9 dokumentierte Cache-Vermutung) - der
        # bisher gesendete Pfad "file:///sdcard/<datei>" zeigt also exakt
        # dorthin, wo die Datei tatsaechlich liegt, und trotzdem lehnt der
        # Drucker ihn mit "Nicht unterstuetzter Pfad oder Name der
        # Druckdatei" ab. Naheliegende Erklaerung: der Alias "sdcard"
        # selbst ist bei der H2-Serie (kein physischer SD-Kartenslot,
        # anders als X1/P1/A1) nicht gueltig. Die aktiv gepflegte
        # Referenzbibliothek bambulabs_api (in diesem Projekt bereits seit
        # v1.5.6 als vertrauenswuerdige Quelle fuer andere project_file-
        # Felder genutzt, OHNE eigene H2/X1-Fallunterscheidung) verwendet
        # fuer ALLE Modelle einheitlich "ftp:///<datei>" statt eines
        # storage-spezifischen Alias - passt exakt zu unserem Datei-Layout
        # (Datei liegt flach im FTP-Wurzelverzeichnis, kein Unterordner).
        # Um das seit MK5 bestaetigt funktionierende Verhalten bei X1/A1/
        # P1/X2 NICHT zu riskieren, wird diese Umstellung bewusst nur fuer
        # die Familien angewendet, bei denen der bisherige Pfad
        # nachweislich scheitert bzw. dieselbe Speicher-Eigenart wie H2
        # hat (P2S laut Bambu selbst technisch mit H2D/H2S verwandt, siehe
        # BAMBU_FAMILY_TO_FTPS_PROFILE oben) - experimentell, bis der
        # Nutzer den tatsaechlichen Druckstart bestaetigt oder verwirft.
        bambu_family = self.cfg.get("bambu_family", "x1")
        if bambu_family in ("h2", "p2"):
            print_url = f"ftp:///{remote_name}"
        else:
            print_url = f"file:///sdcard/{remote_name}"
        payload = {
            "print": {
                "sequence_id": "0",
                "command": "project_file",
                "param": "Metadata/plate_1.gcode",
                "url": print_url,
                "bed_type": "auto",
                "project_id": "0",
                "profile_id": "0",
                "task_id": "0",
                "subtask_id": "0",
                "subtask_name": job_name,
                "use_ams": bool(ams_summary.get("use_ams")),
                "timelapse": False,
                # WICHTIG (v1.6.0): Bisher fest auf False, obwohl die
                # etablierte Referenzbibliothek "bambulabs_api" hierfuer
                # den Standardwert True verwendet
                # (PrinterMQTTClient.start_print_3mf(..., flow_calibration:
                # bool = True), siehe bambutools.github.io/bambulabs_api).
                # Ein gemeldetes Problem ("Mehrfarbdruck bleibt vor dem
                # Aufheizen haengen, Einzelfarb-Drucke funktionieren")
                # passt zu einer fehlenden Fluss-Kalibrierung: Mehrfarb-
                # Drucke brauchen zwingend Spuelvorgaenge beim Farbwechsel,
                # die ohne Kalibrierungsdaten offenbar zu einem Haengen-
                # bleiben schon vor dem eigentlichen Druckstart fuehren
                # koennen. Auf True umgestellt, um dem bestaetigten
                # Referenzverhalten zu entsprechen.
                "flow_cali": True,
                "bed_leveling": True,
                "layer_inspect": True,
                "vibration_cali": True,
            }
        }
        if ams_summary.get("mapping") is not None:
            payload["print"]["ams_mapping"] = ams_summary["mapping"]
            # v2.2.21: zusaetzliches "ams_mapping2"-Feld, NUR fuer die
            # H2-Serie (H2S/H2D/H2D Pro/H2C). Hintergrund: ein vom Nutzer
            # per Diagnose-Log eingefangener ECHTER project_file-Befehl
            # von Bambu Studio fuer einen H2D Pro (siehe UEBERGABE.md,
            # v2.2.20/v2.2.21) enthielt dieses Feld IMMER zusaetzlich zum
            # klassischen "ams_mapping" - ein paralleles Array mit
            # expliziten {"ams_id", "slot_id"}-Paaren statt eines flachen
            # Index, Platzhalter {"ams_id": 255, "slot_id": 255} fuer
            # nicht benoetigte Positionen. Vermutlich noetig, damit die
            # Firmware bei Druckern mit MEHREREN physischen Duesen (H2D/
            # H2D Pro) weiss, welcher Duese ein Filament zugeordnet ist -
            # ob das Feld bei den (vermutlich einduesigen) H2S/H2C
            # tatsaechlich gebraucht wird, ist nicht verifiziert, wird
            # hier aber aus Konsistenz zum beobachteten Verhalten fuer
            # die GESAMTE "h2"-Familie gesetzt. Bewusst NICHT fuer x1/a1/
            # p1/p2/x2 gesetzt, um das dort seit MK5 bestaetigt
            # funktionierende Verhalten nicht zu riskieren - fuer diese
            # Familien lag ohnehin kein Beweis vor, dass sie dieses Feld
            # ueberhaupt kennen oder brauchen.
            if self.cfg.get("bambu_family", "x1") == "h2":
                ams_mapping2 = []
                for m in ams_summary["mapping"]:
                    pair = _flat_index_to_ams_pair(m)
                    if pair is None:
                        ams_mapping2.append({"ams_id": 255, "slot_id": 255})
                    else:
                        ams_mapping2.append({"ams_id": pair[0], "slot_id": pair[1]})
                payload["print"]["ams_mapping2"] = ams_mapping2
        # v2.2.7: Nutzer meldete bei einem H2S (mit frisch eingestecktem
        # USB-Stick) den Druckerfehler "Nicht unterstuetzter Pfad oder
        # Name der Druckdatei" nach einem erfolgreichen FTPS-Upload.
        # Recherche (u. a. bambulab/BambuStudio Issue #8091 "Unable to
        # send file to Local Storage on H2S with properly formatted USB
        # drive", greghesp/ha-bambulab Issues #1512/#1520/#1521, Forum-
        # Thread "Inconsistent MQTT paths compared with FTP access")
        # zeigt: das exakte Pfad-/URL-Format, das die H2-Serie bei einem
        # USB-Stick (statt internem Speicher) fuer den MQTT-Druckstart-
        # Befehl erwartet, ist selbst in den aktivsten Community-Projekten
        # und laut Issue #8091 sogar in Bambu Studio selbst noch ungeklaert
        # (Stand dieser Recherche: offene, ungeloeste Issues ohne
        # bestaetigtes Ergebnis). Ein geratenes Pfad-Format wuerde gegen
        # die Projekt-Konvention verstossen, keine undokumentierten
        # Protokolldetails zu erfinden. Stattdessen: der tatsaechlich
        # gesendete Befehl wird protokolliert, damit bei einem erneuten
        # Fehlschlag echte Beweisdaten (statt Vermutungen) vorliegen.
        print(f"[MK6] Druckstart angefordert: Drucker='{self.cfg.get('name', self.id)}' "
              f"(Familie: {self.cfg.get('bambu_family', 'x1')}) url='{payload['print']['url']}' "
              f"param='{payload['print']['param']}' subtask_name='{job_name}'")
        req_topic = f"device/{self.cfg['serial']}/request"
        result = self._client.publish(req_topic, json.dumps(payload))
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError("MQTT-Befehl zum Druckstart konnte nicht gesendet werden.")

    # v2.9.0: laufenden Druck abbrechen ("print"/"command":"stop") - exakt
    # dieselbe "print"-Befehlsstruktur wie bei _request_print() oben
    # ("command"/"sequence_id"/"param"), hier mit "command": "stop" und
    # leerem "param". Quelle: die bereits an anderer Stelle in diesem
    # Projekt als vertrauenswuerdig zitierte Referenzbibliothek
    # bambulabs_api (PrinterMQTTClient.stop_print()) sendet exakt dieses
    # Payload - keine geratenen/undokumentierten Felder.
    def request_stop_print(self):
        if not self._client or not self.status.get("connected"):
            raise RuntimeError(
                "Keine aktive MQTT-Verbindung zum Drucker - Abbrechen ist "
                "gerade nicht moeglich."
            )
        payload = {
            "print": {
                "sequence_id": "0",
                "command": "stop",
                "param": "",
            }
        }
        req_topic = f"device/{self.cfg['serial']}/request"
        result = self._client.publish(req_topic, json.dumps(payload))
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError("MQTT-Befehl zum Abbrechen konnte nicht gesendet werden.")


def _parse_3mf_filaments(local_path: str):
    """Liest Filamentfarbe/-typ aus einer .gcode.3mf (ZIP-Container) und
    schraenkt sie auf die fuer DIESEN Druck (Plate 1 - das Dashboard
    druckt immer "Metadata/plate_1.gcode", siehe _request_print)
    tatsaechlich benoetigten Filamente ein.

    Quelle/Struktur (siehe UEBERGABE.md fuer Details, keine geratenen
    Felder): "Metadata/project_settings.config" (JSON) enthaelt die
    Arrays "filament_colour"/"filament_type" fuer ALLE im Projekt
    konfigurierten Filamente (0-basiert, parallel) - das koennen mehr
    sein, als auf einer einzelnen Platte tatsaechlich verwendet werden.
    "Metadata/slice_info.config" (XML) enthaelt pro Plate die WIRKLICH
    verbrauchten Filamente als <filament id="1" .../>-Elemente
    (1-basiert!). Nur diese Schnittmenge wird angezeigt/zugeordnet.

    Rein defensiv: Ist project_settings.config nicht auswertbar, wird
    eine leere Liste zurueckgegeben. Ist slice_info.config nicht
    vorhanden/auswertbar oder liefert keine Treffer fuer Plate 1, wird
    NICHT geraten, sondern auf die vollstaendige Filamentliste aus
    project_settings.config zurueckgefallen (sicherer, nur etwas
    weniger praezise als die Plate-gefilterte Liste).

    Gibt ein Tupel (filamente, gesamtanzahl) zurueck. WICHTIG (v1.6.2 -
    Bugfix): jedes Filament behaelt sein ORIGINALES 0-basiertes
    "index"-Feld aus project_settings.config, auch nach dem Filtern -
    dieser Wert MUSS als Position im finalen "ams_mapping"-Array an den
    Drucker verwendet werden (nicht die Position in der gefilterten
    Liste!), siehe ausfuehrliche Begruendung bei
    PrinterConnection.preview_print()."""
    try:
        with zipfile.ZipFile(local_path) as zf:
            with zf.open("Metadata/project_settings.config") as f:
                cfg = json.load(f)
    except Exception:
        return [], 0

    colours = cfg.get("filament_colour")
    types = cfg.get("filament_type")
    if not isinstance(colours, list) or not colours:
        return [], 0
    if not isinstance(types, list):
        types = []

    all_filaments = []
    for i, colour in enumerate(colours):
        ftype = types[i] if i < len(types) else ""
        all_filaments.append({
            "index": i,
            "color": _normalize_hex(colour),
            "type": (ftype or "").strip().upper(),
        })
    total_count = len(all_filaments)

    used_indices = _parse_plate1_used_filament_indices(local_path)
    if used_indices:
        filtered = [f for f in all_filaments if f["index"] in used_indices]
        if filtered:
            return filtered, total_count
    return all_filaments, total_count


def _parse_plate1_used_filament_indices(local_path: str):
    """Liest "Metadata/slice_info.config" (XML) und liefert die Menge
    der auf Plate 1 tatsaechlich verbrauchten Filament-Indizes
    (0-basiert), oder None, wenn die Datei fehlt/nicht auswertbar ist
    bzw. keine Plate mit index=1 gefunden wird - der Aufrufer faellt
    dann bewusst auf die volle Filamentliste zurueck statt zu raten."""
    try:
        with zipfile.ZipFile(local_path) as zf:
            with zf.open("Metadata/slice_info.config") as f:
                root = ET.parse(f).getroot()
    except Exception:
        return None

    for plate in root.findall("plate"):
        index_val = None
        for meta in plate.findall("metadata"):
            if meta.get("key") == "index":
                index_val = meta.get("value")
                break
        if index_val != "1":
            continue
        indices = set()
        for fil in plate.findall("filament"):
            fid = fil.get("id")
            if fid is None:
                continue
            try:
                indices.add(int(fid) - 1)  # 1-basiert (slice_info) -> 0-basiert
            except ValueError:
                continue
        return indices or None

    return None


def _normalize_hex(value):
    if not isinstance(value, str):
        return ""
    v = value.strip().lstrip("#").upper()
    return v[0:6] if len(v) >= 6 else ""


def _slot_to_flat_index(slot: str) -> int:
    """Wandelt den Slot-Bezeichner "<ams_unit>-<tray>" (wie ihn
    _apply_print_report weiter oben erzeugt) in den flachen AMS-Index
    um, den "ams_mapping" erwartet (Community-Konvention: 4 Faecher pro
    AMS-Einheit, siehe UEBERGABE.md Abschnitt 7 - nicht offiziell von
    Bambu dokumentiert).

    WICHTIG (v2.2.21 - jetzt per echtem MQTT-Mitschnitt verifiziert,
    siehe UEBERGABE.md): eine AMS HT (Einheit-ID >= 128, siehe
    _is_ams_ht_slot()) hat nur 1 Fach und wird NICHT nach dem "*4"-Schema
    behandelt - der vom Nutzer per Diagnose-Log (v2.2.20) eingefangene,
    echte project_file-Befehl von Bambu Studio zeigt fuer ein HT-Fach
    (Einheit-ID 128, Fach-ID 0) direkt den Wert 128 im "ams_mapping"-
    Array - OHNE Multiplikation. Fuer reguläre Einheiten (ID < 128)
    bleibt die bisherige, ebenfalls durch denselben Mitschnitt bestaetigte
    Formel (Einheit 0, Fach 1 -> Wert 1) unveraendert."""
    try:
        unit_str, tray_str = slot.split("-", 1)
        unit = int(unit_str)
        tray = int(tray_str)
        if unit >= 128:
            return unit + tray
        return unit * 4 + tray
    except Exception:
        return -1


def _flat_index_to_ams_pair(flat_index):
    """Kehrt _slot_to_flat_index() um: liefert (ams_id, slot_id) fuer
    einen gueltigen flachen Index, oder None fuer "kein Fach" (-1 oder
    nicht auswertbar). Rein mechanische Umkehrung der oben verifizierten
    Formel - KEINE neue Vermutung. Wird fuer das Zusatzfeld
    "ams_mapping2" gebraucht (siehe _request_print(), v2.2.21): der vom
    Nutzer eingefangene echte project_file-Befehl von Bambu Studio fuer
    einen H2D Pro enthielt NEBEN dem flachen "ams_mapping"-Array
    zusaetzlich ein paralleles "ams_mapping2"-Array mit expliziten
    {"ams_id": ..., "slot_id": ...}-Paaren pro Filament (Platzhalter
    {"ams_id": 255, "slot_id": 255} fuer nicht benoetigte Positionen -
    ANDERE Konvention als das "-1" von "ams_mapping"!)."""
    try:
        flat = int(flat_index)
    except (TypeError, ValueError):
        return None
    if flat < 0:
        return None
    if flat >= 128:
        return (flat, 0)
    return (flat // 4, flat % 4)


# v2.2.20: Bestaetigt per Recherche (Bambu-Produktseite fuer die AMS HT
# UND zwei unabhaengige, aktiv gepflegte Community-Projekte, die reale
# MQTT-Rohdaten zeigen - bambulab/BambuStudio Issue #7931 sowie
# TigerTag-Project/TigerSpool-RFID Issue #8): eine AMS HT hat GENAU 1
# Fach (nicht 4 wie AMS/AMS Pro/AMS 2 Pro) und meldet sich im MQTT-
# Status mit der AMS-Einheit-ID 128 (Tray-ID 0), NICHT mit einer
# fortlaufenden kleinen Zahl wie reguläre Einheiten (0, 1, 2, ...).
# Weitere AMS-HT-Einheiten in derselben Kette duerften ab 128 weiter
# hochzaehlen - das ist aber NICHT verifiziert, daher wird hier bewusst
# nur grob "Einheit-ID >= 128" als "ist eine AMS HT" gewertet (jede
# normale AMS-Einheit hat eine kleine ID im niedrigen einstelligen
# Bereich, 128 ist dafuer niemals plausibel).
def _is_ams_ht_slot(slot) -> bool:
    """Prueft anhand des Slot-Bezeichners "<ams_unit>-<tray>", ob das
    Fach zu einer AMS HT gehoert (Einheit-ID >= 128, siehe Kommentar
    oben). Liefert False bei nicht auswertbarem Slot-String (dann wird
    das Fach wie eine normale AMS-Einheit behandelt - kein Falsch-
    Positiv-Risiko, da eine echte AMS HT immer eine gueltige Zahl >= 128
    liefert)."""
    if not slot:
        return False
    try:
        unit_str, _tray_str = str(slot).split("-", 1)
        return int(unit_str) >= 128
    except (ValueError, TypeError):
        return False


def _types_compatible(want_type: str, tray_type: str) -> bool:
    """Prueft, ob zwei Materialtyp-Bezeichnungen (z. B. "PLA", "PLA
    BASIC", "ASA-CF") als kompatibel gelten duerfen fuer die
    automatische AMS-Zuordnung.

    WICHTIG (Bugfix): Ein reiner Teilstring-Vergleich ("want_type in
    tray_type or tray_type in want_type") hat einen gefaehrlichen
    Nebeneffekt: "ASA" ist ein Teilstring von "ASA-CF" - ein Fach mit
    normalem ASA wuerde damit faelschlich als passend fuer ein
    ASA-CF-Filament gelten (und umgekehrt), obwohl das voellig
    unterschiedliche Materialien mit unterschiedlichen Druck-
    eigenschaften sind (das gilt analog fuer alle Verbundwerkstoff-
    Varianten: PLA-CF, PETG-CF, PA-CF, PPS-CF, ABS-GF usw.). Traf das
    zufaellig auf ein farblich uebereinstimmendes Fach mit dem falschen
    Grundmaterial, wurde es automatisch vorgeschlagen und (wenn vom
    Nutzer uebernommen) an den Drucker gesendet - der RFID-Chip im Fach
    meldet dann ein anderes Material als im Slicer hinterlegt, was am
    Drucker typischerweise eine Bestaetigungs-Abfrage auf dem Display
    ausloest, die ohne jemanden vor Ort wie ein "Haengenbleiben beim
    Materialladen" wirkt.

    Deshalb: der Teil nach einem "-" (Verbundwerkstoff-Suffix wie "CF",
    "GF") muss auf beiden Seiten identisch sein - "ASA" (kein Suffix)
    und "ASA-CF" (Suffix "CF") gelten damit NICHT mehr als kompatibel.
    Der Teil vor dem "-" darf weiterhin locker verglichen werden (z. B.
    "PLA" vs. "PLA BASIC", beide ohne Suffix)."""
    if not want_type or not tray_type:
        return True  # nichts zum Vergleichen - nicht blockieren
    if want_type == tray_type:
        return True
    want_base, _, want_suffix = want_type.partition("-")
    tray_base, _, tray_suffix = tray_type.partition("-")
    if want_suffix != tray_suffix:
        return False  # z. B. "ASA" vs. "ASA-CF" - unterschiedliche Materialien
    return want_base in tray_base or tray_base in want_base


def _color_distance(hex_a: str, hex_b: str) -> int:
    """Euklidischer Abstand zweier 6-stelliger Hex-Farbwerte im RGB-Raum
    (0 = identisch, hoeher = unaehnlicher). Liefert eine sehr grosse Zahl
    (kein Match moeglich), wenn einer der beiden Werte nicht als 6-
    stellige Hex-Farbe geparst werden kann."""
    try:
        ar, ag, ab = int(hex_a[0:2], 16), int(hex_a[2:4], 16), int(hex_a[4:6], 16)
        br, bg, bb = int(hex_b[0:2], 16), int(hex_b[2:4], 16), int(hex_b[4:6], 16)
    except (ValueError, IndexError):
        return 10**9
    return int(((ar - br) ** 2 + (ag - bg) ** 2 + (ab - bb) ** 2) ** 0.5)


# WICHTIG (v1.6.6 - Bugfix): Bewusst gewaehlte, KONSERVATIVE Toleranz
# fuer die Farb-Zuordnung (siehe _find_matching_tray() unten). Vorher
# wurde ein EXAKTER Hex-Vergleich verlangt - das fuehrte zu einem
# bestaetigten, reproduzierbaren Fall: Die Slicer-Datei verlangte
# "PLA Blau", das AMS hatte tatsaechlich ein Fach mit blauem PLA
# bestueckt, trotzdem meldete der Dialog "Keine passende Farbe im AMS
# gefunden" - weil der vom Slicer verwendete Blau-Hexwert nicht
# BYTE-GENAU mit dem vom AMS/RFID gemeldeten Blau-Hexwert
# uebereinstimmte (beide von einem Menschen zweifellos als "Blau"
# bezeichnet, aber technisch unterschiedliche Werte, z. B. durch
# unterschiedliche Bambu-Filament-Profile). Der Wert 30 ist bewusst
# ENG gewaehlt (typische kleine Profil-/Rundungsabweichungen werden
# erfasst) - er reicht NICHT aus, um z. B. "Gruen" und "Hellgruen"
# (deutlich groesserer, beabsichtigter Farbunterschied) miteinander zu
# verwechseln, da eine falsche automatische Zuordnung (Druck in der
# physisch falschen Farbe) ein schlechteres Ergebnis waere als der
# sichere Rueckfall auf "Extern/manuell am Display".
COLOR_MATCH_TOLERANCE = 30


def _find_matching_tray(filament: dict, ams_trays: list, used_slots: set):
    """Sucht das AM BESTEN passende, noch nicht verwendete AMS-Fach:
    Farbe muss innerhalb von COLOR_MATCH_TOLERANCE liegen (siehe dort -
    bewusst eng, um keine tatsaechlich unterschiedlichen Farben zu
    verwechseln) und der Typ muss plausibel uebereinstimmen (z. B.
    angefordertes "PLA" passt zu Fach-Typ "PLA Basic", aber "ASA" passt
    NICHT zu "ASA-CF" - siehe _types_compatible()). Bei mehreren
    passenden Faechern gewinnt das mit der GERINGSTEN Farbabweichung
    (bei einem exakten Treffer aendert sich dadurch nichts). Liefert
    None statt zu raten, wenn nichts hinreichend gut passt.

    Seit v2.2.21 OHNE Sonderbehandlung von AMS-HT-Faechern (v2.2.20 hatte
    sie hier noch ausgeschlossen, siehe _slot_to_flat_index() fuer den
    seitdem korrigierten/verifizierten Hintergrund)."""
    want_color = filament.get("color") or ""
    want_type = filament.get("type") or ""
    if not want_color:
        return None
    best = None
    best_distance = None
    for tray in ams_trays:
        slot = tray.get("slot")
        if not slot or slot in used_slots:
            continue
        tray_color = _normalize_hex(tray.get("color"))
        if not tray_color:
            continue
        distance = _color_distance(want_color, tray_color)
        if distance > COLOR_MATCH_TOLERANCE:
            continue
        tray_type = (tray.get("type") or "").strip().upper()
        if not _types_compatible(want_type, tray_type):
            continue
        if best is None or distance < best_distance:
            best = tray
            best_distance = distance
    return best


def _run_ftps_upload_worker(argv):
    """Wird ausgefuehrt, wenn die exe/das Skript mit dem Sentinel-
    Argument "--ftps-upload-worker" gestartet wird (siehe Abzweig ganz
    oben im Programm, VOR jeglicher Flask-/MQTT-/DashboardApp-
    Initialisierung). Fuehrt AUSSCHLIESSLICH den FTPS-Upload durch -
    keine Drucker-Verbindungen, kein Flask, kein MQTT - und meldet
    Fortschritt/Ergebnis als einzelne JSON-Zeilen auf stdout, dann
    beendet sich der Prozess. Aufgerufen von
    PrinterConnection._ftps_upload_once() im Hauptprozess ueber
    subprocess.Popen() - siehe dortiger Kommentar fuer die Begruendung
    (Ressourcen-/Scheduling-Konkurrenz mit dem MQTT-Thread im
    Hauptprozess, wenn der Upload dort als Thread liefe). Nur der
    Fallback-Pfad, falls die separate FtpsUploadHelper-exe nicht
    gefunden wird - siehe _find_ftps_upload_helper()."""
    if len(argv) not in (4, 5):
        print(json.dumps({"type": "error", "message": "Falsche Anzahl Argumente fuer --ftps-upload-worker"}))
        return
    ip, access_code, local_path, remote_name = argv[:4]
    profile_name = argv[4] if len(argv) >= 5 and argv[4] in FTPS_PROFILES else "x1"
    profile = FTPS_PROFILES[profile_name]

    ctx = _build_ftps_context(profile)

    try:
        total_size = os.path.getsize(local_path)
    except OSError as e:
        print(json.dumps({"type": "error", "message": f"Datei nicht lesbar: {e}", "sent": 0, "total": 0}), flush=True)
        return

    sent = 0
    last_pct = -1

    def _progress_cb(block):
        nonlocal sent, last_pct
        sent += len(block)
        pct = int(sent * 100 / total_size) if total_size else 100
        if pct != last_pct:
            last_pct = pct
            print(json.dumps({"type": "progress", "sent": sent, "total": total_size}), flush=True)

    try:
        ftp = ImplicitFtpTls(context=ctx, reuse_session=profile["reuse_session"])
        # WICHTIG (v1.5.9): Timeout erhoeht (25s -> 120s) - siehe
        # ausfuehrliche Begruendung im identischen Kommentar in
        # ftps_upload_helper.py (dort die primaer verwendete
        # Implementierung; dieser Pfad ist nur der Fallback).
        ftp.connect(ip, 990, timeout=120)
        ftp.login("bblp", access_code)
        ftp.prot_p()
        ftp.set_pasv(True)
        # v2.2.9: identische Diagnose wie in ftps_upload_helper.py (dort
        # die primaer verwendete Implementierung) - siehe Kommentar dort
        # fuer die Begruendung. Dieser Pfad ist nur der Selbstaufruf-
        # Fallback, falls die Helfer-exe nicht gefunden wird.
        try:
            listing = ftp.nlst()
            print(json.dumps({
                "type": "diag",
                "message": f"FTPS-Verzeichnis vor Upload (NLST): {listing}",
            }), flush=True)
        except Exception as e:
            print(json.dumps({
                "type": "diag",
                "message": f"FTPS-Verzeichnislisting nicht moeglich: {e}",
            }), flush=True)
        with open(local_path, "rb") as f:
            if profile["skip_unwrap"]:
                _storbinary_no_unwrap(ftp, f"STOR {remote_name}", f, blocksize=8192, callback=_progress_cb)
            else:
                ftp.storbinary(f"STOR {remote_name}", f, blocksize=8192, callback=_progress_cb)
        try:
            ftp.quit()
        except Exception:
            try:
                ftp.close()
            except Exception:
                pass
        print(json.dumps({"type": "done", "sent": sent, "total": total_size}), flush=True)
    except Exception as e:
        print(json.dumps({"type": "error", "message": str(e), "sent": sent, "total": total_size}), flush=True)


class ImplicitFtpTls(ftplib.FTP_TLS):
    """ftplib.FTP_TLS kann von Haus aus nur explizites TLS (AUTH TLS).
    Bambu-Drucker verlangen auf Port 990 IMPLIZITES TLS (die Verbindung
    ist von Anfang an TLS-verschluesselt, kein AUTH-Kommando). Diese
    Subklasse wrappt den Socket direkt beim Verbindungsaufbau - dafuer
    zwingend noetig.

    WICHTIG (v1.5.8 - Profile statt Einzelschalter): Die X1-Serie
    (X1C/X1E, bestaetigt funktionsfaehig) und der A1 Mini (bestaetigt
    NICHT funktionsfaehig mit den bisherigen Einstellungen) brauchen
    unterschiedliche TLS-Konfigurationen. Ein isolierter Test von nur
    `reuse_session` (v1.5.7) hat gezeigt: Der A1-Mini-Timeout nach 100%
    uebertragener Bytes tritt UNABHAENGIG von `reuse_session` auf (mit
    UND ohne identisch) - die eigentliche Ursache lag also woanders.
    Beim Vergleich mit der zuletzt beim Nutzer bestaetigt funktionierenden
    Version (v1.4.5) fiel auf: dort war KEIN TLS-Versions-Deckel aktiv
    (`ctx.maximum_version` wurde erst spaeter, in v1.5.0 fuer die
    X1-Serie, wieder eingefuehrt) - TLS durfte sich frei aushandeln
    (typischerweise TLS 1.3). Deshalb jetzt zwei vollstaendige,
    benannte Profile statt einzelner Schalter (siehe `PROFILES` und
    `_ftps_upload()` fuer die Alternierung ueber die 3 Upload-Versuche):
      - "x1": TLS gedeckelt auf Version 1.2 + Sitzungs-Wiederverwendung
        fuer die Datenverbindung (X1-Serie/vsftpd braucht beides)
      - "a1": KEIN TLS-Versions-Deckel (freie Aushandlung) + KEINE
        Sitzungs-Wiederverwendung (entspricht dem zuletzt beim A1 Mini
        bestaetigt funktionierenden Verhalten aus v1.4.5)"""

    def __init__(self, *args, reuse_session: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self._sock = None
        self._reuse_session = reuse_session

    @property
    def sock(self):
        return self._sock

    @sock.setter
    def sock(self, value):
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value)
        self._sock = value

    def ntransfercmd(self, cmd, rest=None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            if self._reuse_session:
                conn = self.context.wrap_socket(
                    conn, server_hostname=self.host, session=self.sock.session
                )
            else:
                conn = self.context.wrap_socket(conn, server_hostname=self.host)
        return conn, size


# Vollstaendige, benannte Verbindungsprofile fuer den FTPS-Upload -
# siehe Klassen-Docstring von ImplicitFtpTls oben fuer die Begruendung.
# Werden sowohl vom Sentinel-Fallback (_run_ftps_upload_worker()) als
# auch als Referenz fuer die an die separate Helfer-exe uebergebenen
# Profilnamen genutzt (siehe _ftps_upload()/_ftps_upload_once()).
# WICHTIG (v1.6.0): "a1" bekommt zusaetzlich "skip_unwrap": True - siehe
# ausfuehrliche Begruendung im identischen Kommentar in
# ftps_upload_helper.py (dort die primaer verwendete Implementierung).
FTPS_PROFILES = {
    "x1": {"cap_tls12": True, "reuse_session": True, "skip_unwrap": False},
    "a1": {"cap_tls12": False, "reuse_session": False, "skip_unwrap": True},
}

# WICHTIG (v1.6.7): Bildet die beim Anlegen eines Druckers gewaehlte
# Druckerfamilie ("x1"/"a1"/"h2"/"p1"/"p2"/"x2", siehe DashboardApp.
# add_printer()) auf ein tatsaechliches FTPS-Verbindungsprofil aus
# FTPS_PROFILES ab. Fuer H2 (H2S/H2D/H2D Pro/H2C, ergaenzt in v1.6.7)
# sowie P1 (P1P/P1S), P2 (P2S) und X2 (X2D, ergaenzt in v1.6.8) liegen
# noch KEINE eigenen Erkenntnisse zum FTPS-Verhalten vor - sie nutzen
# deshalb vorerst mangels anderer Informationen dasselbe Profil wie die
# X1-Serie:
#   - P1-Serie: laut Bambu-eigener Ankündigung technisch direkt vom X1
#     abgeleitet ("retained the core technology" der X1, nur guenstigere
#     Hardware/weniger Sensorik) - von den hier ergaenzten Familien am
#     ehesten tatsaechlich mit dem X1-Profil identisch.
#   - X2-Serie (X2D): offizieller Nachfolger der (im Maerz 2026
#     eingestellten) X1C/X1E-Modelle - ebenfalls vollwertige Linux-
#     Basis zu erwarten.
#   - P2-Serie (P2S): Nachfolger der P1-Serie, "combines the ...
#     P1-Series with next-generation technologies from the H2D/H2S" -
#     technische Abstammung nicht ganz eindeutig, aber ebenfalls eher
#     mit der X1-Serie als mit der leichtgewichtigeren A1-Serie
#     vergleichbar.
# Stellt sich das fuer eine dieser Familien als falsch heraus, genuegt
# es, hier den jeweiligen Eintrag zu aendern (ggf. mit einem eigenen,
# neuen Profil in FTPS_PROFILES, falls weder "x1" noch "a1" passen).
BAMBU_FAMILY_TO_FTPS_PROFILE = {
    "x1": "x1",
    "a1": "a1",
    "h2": "x1",  # vorlaeufig, siehe Kommentar oben
    "p1": "x1",  # vorlaeufig, siehe Kommentar oben
    "p2": "x1",  # vorlaeufig, siehe Kommentar oben
    "x2": "x1",  # vorlaeufig, siehe Kommentar oben
}

# v2.2.22: Welche Bambu-Familien ihren Kamera-Stream ueber RTSPS (Port
# 322, statt des rohen MJPEG-ueber-TLS-Protokolls auf Port 6000) liefern -
# siehe bambu_rtsp_mjpeg_generator() und /camera/<printer_id> unten fuer
# die vollstaendige Quellenlage. NUR "a1" bleibt aussen vor (nutzt
# weiterhin bambu_mjpeg_generator() auf Port 6000, seit MK5 bestaetigt
# funktionierend). Alle anderen bekannten Familien - X1/P1/P2 UND,
# entgegen einer frueheren, ZU KURZ GEGRIFFENEN Einschaetzung in dieser
# Codebasis, auch die H2-Serie (und vermutlich X2D) - verwenden laut
# mehreren unabhaengigen Quellen (Bambu-Forum-Thread "H2C RTSP for
# Camera?": ein Nutzer bestaetigt RTSPS-Verbindung auf einem H2C nach
# Aktivieren der separaten Druckereinstellung "LAN Only Liveview"/"LAN
# Mode Liveview"; ebenso Bambu-Forum "P2S: Lan Only Liveview while in
# Cloud Mode?") DIESELBE RTSPS-Methode wie X1/P1. Die in einer frueheren
# Recherche dieses Projekts vermutete eigene, undokumentierte
# "BRTC"-Kameraprotokoll fuer die H2-Serie beruhte auf einer Verwechslung:
# das beobachtete "brtc://emmc/..." aus dem project_file-Kommando (siehe
# UEBERGABE.md v2.2.20/21) ist ein DATEISPEICHER-Schema fuer den
# Druckstart, hat mit dem Kamera-Stream nichts zu tun - fuer Kamera
# nutzt auch die H2-Serie denselben "ipcam"-Mechanismus.
BAMBU_RTSPS_CAMERA_FAMILIES = {"x1", "p1", "p2", "h2", "x2"}


def _build_ftps_context(profile: dict):
    ctx = ssl._create_unverified_context()
    ctx.options |= getattr(ssl, "OP_IGNORE_UNEXPECTED_EOF", 0)
    if profile["cap_tls12"]:
        try:
            ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        except (AttributeError, ValueError):
            pass
    return ctx


def _storbinary_no_unwrap(ftp, cmd, fp, blocksize=8192, callback=None):
    """Wie ftplib.FTP.storbinary(), aber bewusst OHNE den abschliessenden
    Aufruf von conn.unwrap() bei TLS-Datenverbindungen - siehe
    ausfuehrliche Begruendung beim FTPS_PROFILES-Dict oben."""
    ftp.voidcmd("TYPE I")
    with ftp.transfercmd(cmd) as conn:
        while True:
            buf = fp.read(blocksize)
            if not buf:
                break
            conn.sendall(buf)
            if callback:
                callback(buf)
        # WICHTIG: bewusst KEIN conn.unwrap() hier.
    return ftp.voidresp()


# ----------------------------------------------------------------------
# WICHTIG: Sentinel-Abzweig fuer den isolierten FTPS-Upload-Kindprozess.
# Muss VOR jeglicher Flask-/MQTT-/DashboardApp-Initialisierung geprueft
# werden (siehe unten "dash = DashboardApp()") - sonst wuerde der
# Kindprozess unnoetig auch alle Drucker-Verbindungen aufbauen und
# einen zweiten Flask-Server starten. Wird von
# PrinterConnection._ftps_upload_once() ausgeloest, das die exe/das
# Skript mit "--ftps-upload-worker <ip> <access_code> <datei> <ziel>"
# neu aufruft (siehe dortiger Kommentar fuer die Begruendung).
# ----------------------------------------------------------------------
if len(sys.argv) > 1 and sys.argv[1] == "--ftps-upload-worker":
    _run_ftps_upload_worker(sys.argv[2:])
    sys.exit(0)


def _argb_to_css(hexval):
    if not hexval or len(hexval) < 6:
        return "#666666"
    return "#" + hexval[0:6]


# ----------------------------------------------------------------------
# Kamera-Stream (Bambu Lab lokaler Kamera-Feed, Port 6000)
# ----------------------------------------------------------------------
def bambu_mjpeg_generator(ip: str, access_code: str, port: int = 6000):
    ctx = ssl._create_unverified_context()
    raw_sock = socket.create_connection((ip, port), timeout=5)
    sock = ctx.wrap_socket(raw_sock)

    auth = bytearray()
    auth += struct.pack("<I", 0x40)
    auth += struct.pack("<I", 0x3000)
    auth += struct.pack("<I", 0)
    auth += struct.pack("<I", 0)
    user_bytes = b"bblp".ljust(32, b"\x00")
    code_bytes = access_code.encode("ascii").ljust(32, b"\x00")
    auth += user_bytes
    auth += code_bytes
    sock.write(auth)

    boundary = b"--frame"
    try:
        while True:
            header = _recv_exact(sock, 16)
            if header is None:
                break
            img_len = struct.unpack("<I", header[0:4])[0]
            payload_len = struct.unpack("<I", header[4:8])[0]
            if img_len == 0 or img_len > 5_000_000:
                break
            jpeg = _recv_exact(sock, img_len)
            if jpeg is None:
                break
            if payload_len > img_len:
                _recv_exact(sock, payload_len - img_len)
            yield (boundary + b"\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" +
                   jpeg + b"\r\n")
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except Exception:
            return None
        if not chunk:
            return None
        buf += chunk
    return buf


# ----------------------------------------------------------------------
# Kamera-Stream der X1/P1/P2/H2/X2-Serie (RTSPS, Port 322) - v2.2.22
#
# Anders als die A1-Familie (rohes MJPEG-ueber-TLS, Port 6000, siehe
# bambu_mjpeg_generator() oben) liefern alle anderen bekannten Bambu-
# Familien ihren Live-Kamera-Feed stattdessen als RTSPS-Stream (RTSP
# ueber TLS) auf Port 322 - siehe BAMBU_RTSPS_CAMERA_FAMILIES oben fuer
# die Quellenlage. Belege (mehrere unabhaengige Quellen, keine geratenen
# Werte):
#   - URL-Format "rtsps://bblp:<access_code>@<ip>:322/streaming/live/1"
#     (Benutzername "bblp" + Access Code als Passwort, wie beim
#     bestehenden MJPEG-Port-6000-Protokoll und beim FTPS-Upload) -
#     u. a. im Bambu-Forum-Thread "How to access camera on LAN ?
#     (firmware 01.06+)" von einem Nutzer per ffplay bestaetigt, sowie
#     identisch in der Referenzimplementierung "bambustudio_mcp"
#     (camera/stream.py, "rtsps://bblp:{access_code}@{host}:{port}/
#     streaming/live/1", Standardport 322).
#   - Vor dem eigentlichen Stream-Zugriff muss am Drucker ZUSAETZLICH
#     zum "Developer Mode" eine SEPARATE Einstellung aktiviert werden
#     ("LAN Only Liveview" bzw. "LAN Mode Liveview" je nach Firmware-
#     Uebersetzung, am Drucker-Display zu finden, NICHT identisch mit
#     dem vollen LAN-Only-Modus) - ohne diese Einstellung liefert der
#     MQTT-Report das Feld "ipcam.rtsp_url" als woertlichen String
#     "disable" statt einer echten URL. Dieses Verhalten ist in der
#     aktiv gepflegten Home-Assistant-Bambu-Lab-Integration
#     (greghesp/ha-bambulab, pybambu/models.py) exakt so implementiert
#     ("if self.rtsp_url == 'disable': ...") und wird hier genauso
#     ausgewertet (siehe _apply_print_report() und /camera/<printer_id>)
#     statt den rohen Verbindungsfehler von FFmpeg unkommentiert
#     durchzureichen.
#   - KORREKTUR einer frueheren, zu kurz gegriffenen Annahme dieses
#     Projekts: die H2-Serie braucht KEIN eigenes, undokumentiertes
#     Protokoll fuer die Kamera - sie nutzt denselben RTSPS-Mechanismus
#     wie X1/P1/P2 (siehe Kommentar bei BAMBU_RTSPS_CAMERA_FAMILIES).
#
# Technisch wird dafuer (anders als beim handgestrickten Parsing bei
# bambu_mjpeg_generator()) eine separate, extern mitgelieferte FFmpeg-
# Programmdatei als Subprozess gestartet (siehe _find_ffmpeg_binary()):
# FFmpeg uebernimmt Verbindungsaufbau, TLS-Handshake, RTSP-Signalisierung
# und - unabhaengig davon, ob der Drucker intern H.264, H.265 oder
# bereits MJPEG ueber RTSP sendet (nicht oeffentlich dokumentiert und
# fuer diese Implementierung auch nicht relevant, da FFmpeg jeden
# Eingabe-Codec automatisch erkennt/dekodiert) - die Neukodierung nach
# MJPEG fuer die Ausgabe. Ausgabeformat ist FFmpegs eingebauter
# "mpjpeg"-Muxer: er erzeugt direkt einen fertigen
# "multipart/x-mixed-replace"-Bytestrom (fester, im FFmpeg-Quellcode
# hart codierter Boundary-String "ffserver", siehe libavformat/mpjpeg.c)
# - die rohen Ausgabe-Bytes von FFmpeg koennen deshalb 1:1 als Flask-
# Response-Body durchgereicht werden, ganz ohne eigenes Frame-Parsing
# wie bei bambu_mjpeg_generator().
#
# "-rtsp_transport tcp": erzwingt TCP statt des RTSP-Standards UDP fuer
# die eigentliche Mediendaten-Uebertragung - in mehreren der oben
# genannten Quellen (u. a. "H2C RTSP for Camera?"-Thread: "ffplay with
# TCP transport successfully connected") ausdruecklich als notwendig
# fuer eine zuverlaessige Verbindung zu Bambu-Druckern genannt (UDP
# scheitert haeufig an lokalen Firewalls/NAT-internen Eigenheiten).
def _drain_ffmpeg_stderr(proc, log_label: str):
    """Liest die Standardfehlerausgabe des FFmpeg-Subprozesses fortlaufend
    in einem eigenen Thread mit und gibt jede Zeile ueber die Server-
    Konsole aus (Praefix "[MK6-FFMPEG]").

    ZWEI Gruende, warum das noetig ist (v2.2.23, nach einem Nutzerbericht
    "Kamera-Fenster laedt dauerhaft, weder Bild noch Fehlermeldung" fuer
    X1E/H2D Pro trotz aktivierter "LAN Only Liveview"):
      1. Diagnose: FFmpeg schreibt Verbindungs-/Protokollfehler nach
         stderr - ohne das mitzulesen, war bisher nicht erkennbar, WARUM
         FFmpeg haengt oder scheitert (reine Vermutung waere hier gegen
         die Projekt-Konvention).
      2. Ein bekanntes, von der Ursache unabhaengiges Python-
         subprocess-Problem: wird stderr=PIPE gesetzt, aber NIE gelesen
         (wie bisher), kann der interne Betriebssystem-Puffer dieser
         Pipe volllaufen (typischerweise bereits bei wenigen zehn KB) -
         FFmpeg blockiert dann beim naechsten Schreibversuch nach stderr
         UNBEGRENZT, komplett unabhaengig vom eigentlichen RTSPS-Problem.
         Das allein kann bereits ein "haengt fuer immer, ohne Fehler"-
         Bild erzeugen, wie vom Nutzer beschrieben."""
    try:
        for raw_line in iter(proc.stderr.readline, b""):
            line = raw_line.decode("utf-8", errors="ignore").rstrip()
            if line:
                print(f"[MK6-FFMPEG] ({log_label}): {line}")
    except Exception:
        pass


def bambu_rtsp_mjpeg_generator(ip: str, access_code: str, ffmpeg_path: str):
    rtsp_url = f"rtsps://bblp:{access_code}@{ip}:322/streaming/live/1"
    cmd = [
        ffmpeg_path,
        "-loglevel", "error",
        "-rtsp_transport", "tcp",
        # v2.2.23: Socket-I/O-Timeout (Verbindungsaufbau UND Lesen) in
        # Mikrosekunden - OHNE dieses Limit kann FFmpeg bei einer nicht
        # zustande kommenden RTSPS-Verbindung unbegrenzt haengen bleiben
        # (vom Nutzer genau so beobachtet: "Kamera-Fenster laedt
        # dauerhaft, weder Bild noch Fehlermeldung"). Der Optionsname
        # "timeout" ist die seit FFmpeg 4.4 (2021) aktuelle Bezeichnung
        # fuer den RTSP-Demuxer (siehe ffmpeg-protocols(1)); die aeltere
        # Bezeichnung "stimeout" wurde seitdem entfernt, nicht nur
        # umbenannt - ein FFmpeg-Build aus GyanD/codexffmpeg (siehe
        # build-exe.yml) ist aktuell genug, um nur den neuen Namen zu
        # kennen. 15 Sekunden als grosszuegiger, aber endlicher Wert.
        "-timeout", "15000000",
        # v2.2.24: Nutzer lieferte per [MK6-FFMPEG]-Mitschnitt (siehe
        # _drain_ffmpeg_stderr(), v2.2.23) den tatsaechlichen Fehler auf
        # echter X1E- UND H2D-Pro-Hardware: "[tls] Peer certificate
        # failed verification" -> "Error opening input: I/O error". Das
        # ist die eigentliche Ursache des in v2.2.22/23 beobachteten
        # Haengenbleibens, nicht (nur) das in v2.2.23 behobene stderr-
        # Deadlock-Risiko. Root Cause identifiziert (keine Vermutung,
        # klar belegt): FFmpeg 9.0 (das ueber GyanD/codexffmpeg bezogene,
        # zum Implementierungszeitpunkt aktuelle Release, siehe
        # build-exe.yml) hat den Standardwert der TLS-Zertifikatspruefung
        # ("tls_verify") von 0 (nicht pruefen) auf 1 (pruefen) umgestellt
        # - fuer die allermeisten TLS-Verbindungen (echte, von einer
        # oeffentlichen Zertifizierungsstelle signierte Zertifikate) eine
        # sinnvolle Verschaerfung, bricht hier aber die Verbindung zum
        # Drucker, der (wie bei der bestehenden FTPS-Datei-Uebertragung
        # und dem MJPEG-Port-6000-Protokoll auch) ein SELBSTSIGNIERTES
        # Zertifikat verwendet. Die aeltere FFmpeg-Generation, auf die
        # sich mehrere Forum-Berichte zur erfolgreichen RTSPS-Verbindung
        # noch stuetzten (siehe UEBERGABE.md v2.2.22), hatte diesen
        # strengen Standardwert noch nicht - daher dort kein Problem.
        # "-tls_verify 0" deaktiviert die Pruefung wieder explizit, genau
        # wie es das bereits bestehende `ssl._create_unverified_context()`
        # fuer den A1-MJPEG-Port-6000- und den FTPS-Upload-Pfad in diesem
        # Projekt ebenfalls tut (gleiche Begruendung: Drucker im eigenen
        # LAN, kein oeffentliches Zertifikat zu erwarten).
        "-tls_verify", "0",
        "-i", rtsp_url,
        "-an",
        "-c:v", "mjpeg",
        "-q:v", "5",
        "-r", "10",
        # v2.2.26: siehe ausfuehrliche Begruendung weiter unten (direkt vor
        # dem JPEG-Marker-Parsing) - "image2pipe" statt des zuvor
        # verwendeten "mpjpeg"-Muxers, weil Letzterer kein browserkompat-
        # ibles Multipart-Format erzeugt (recherchiert, nicht vermutet:
        # siehe libavformat/mpjpeg.c).
        "-f", "image2pipe",
        "-",
    ]
    # v2.2.25: Nutzer meldete nach v2.2.24 weiterhin keine Anzeige - diesmal
    # aber OHNE JEDE [MK6-FFMPEG]-Zeile in der Konsole (nur die normalen
    # Zugriffsprotokoll-Zeilen von Flask/Werkzeug). Das ist diagnostisch
    # wichtig: entweder haengt bereits der Start des FFmpeg-Subprozesses
    # selbst (Popen() kehrt nie zurueck - denkbar z. B. durch Antivirus-/
    # Windows-Defender-Pruefung einer frisch heruntergeladenen, unsignierten
    # ffmpeg.exe beim allerersten Ausfuehren, siehe dieselbe Problematik
    # bei FtpsUploadHelper.exe weiter oben in dieser Datei), oder FFmpeg
    # laeuft, haengt aber in einer Phase, die weder "-loglevel error"
    # noch die bisherige "-timeout"-Option abdecken. Ohne weitere, hier
    # bewusst NICHT geratene Protokolldetails sind explizite Logzeilen VOR
    # und NACH dem Start der einzige Weg, diese beiden Faelle sauber
    # auseinanderzuhalten - gleichzeitig wird ein evtl. Fehler beim Start
    # selbst (z. B. "nicht ausfuehrbar") jetzt abgefangen und sichtbar
    # gemacht statt (wie zuvor) unbemerkt im Generator unterzugehen: ein
    # Python-Generator fuehrt seinen Code erst bei der ERSTEN Iteration
    # aus, die bei einer Flask-Streaming-Response ERST beim Senden des
    # Response-Bodys erfolgt - zu diesem Zeitpunkt sind Status/Header
    # (200) laengst verschickt, das umgebende try/except in
    # /camera/<printer_id> kann einen hier auftretenden Fehler also gar
    # nicht mehr abfangen (greift nur fuer Fehler VOR dem ersten Yield-
    # Aufruf, siehe bereits bestehende, identische Einschraenkung bei
    # bambu_mjpeg_generator()).
    print(f"[MK6-FFMPEG] (Drucker-IP {ip}): Starte FFmpeg-Prozess fuer RTSPS-Kamera-Stream...")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        print(f"[MK6-FFMPEG] (Drucker-IP {ip}): FEHLER beim Start von FFmpeg: {e!r} "
              f"(Pfad: {ffmpeg_path!r})")
        return
    print(f"[MK6-FFMPEG] (Drucker-IP {ip}): FFmpeg-Prozess gestartet (PID {proc.pid}).")
    stderr_thread = threading.Thread(target=_drain_ffmpeg_stderr, args=(proc, f"Drucker-IP {ip}"), daemon=True)
    stderr_thread.start()
    # v2.2.26: Nutzer berichtete nach v2.2.25 (mit umfangreicher Diagnose-
    # Protokollierung) folgenden, schrittweise eingegrenzten Befund: FFmpeg
    # startet erfolgreich (PID bestaetigt), verbindet sich zum Drucker
    # (TLS/RTSP erfolgreich, keine Fehler), decodiert und re-encodiert den
    # H.264-Stream fehlerfrei zu MJPEG - ALLE folgenden, vom Nutzer auf
    # unsere Bitte hin durchgefuehrten Tests ergaben einwandfreie Bilder:
    #   1. Einzelbild per "-frames:v 1" direkt als JPG gespeichert: gut.
    #   2. Fortlaufende Aufnahme als einzelne JPG-Dateien (kein mpjpeg-
    #      Container): alle 104 Bilder gut.
    #   3. Fortlaufende Aufnahme MIT "-f mpjpeg" in eine Datei geschrieben,
    #      anschliessend mit FFmpeg selbst wieder in Einzelbilder zerlegt:
    #      alle Bilder gut (Dateigroesse ca. 90 MB fuer 10-15s, unauffaellig).
    #   4. Der tatsaechliche HTTP-Response des LAUFENDEN Flask-Servers
    #      wurde per "curl" (am Browser vorbei) 10 Sekunden lang in eine
    #      Datei aufgezeichnet (27,9 MB) und ebenfalls wieder in Einzel-
    #      bilder zerlegt: ebenfalls alle gut.
    #   Nur die Anzeige im Browser selbst (Chrome UND Firefox, sowohl ueber
    #   das Dashboard als auch per direktem URL-Aufruf) blieb durchgehend
    #   schwarz, ohne jede Fehlermeldung.
    # Das grenzt die Ursache zweifelsfrei auf das Byte-Format des von
    # FFmpeg per "-f mpjpeg" erzeugten Multipart-Streams selbst ein - nicht
    # auf Verbindung, Decoding, Flask-Uebertragung oder Pufferung. Recherche
    # im FFmpeg-Quellcode (libavformat/mpjpeg.c) bestaetigt den Grund: Der
    # mpjpeg-Muxer schreibt pro Bild exakt
    #     --ffserver\n Content-type: image/jpeg\n\n <JPEG-Daten> \n--ffserver\n
    # - also OHNE "Content-Length"-Header und nur mit "\n" (LF) statt dem
    # fuer HTTP-/MIME-Multipart (RFC 2046) eigentlich vorgeschriebenen
    # "\r\n" (CRLF) als Zeilenende. FFmpeg selbst kann diese Daten beim
    # erneuten Einlesen trotzdem korrekt interpretieren, weil sein eigener
    # Demuxer die JPEG-Bilder anhand ihrer binaeren Start-/Endmarker (siehe
    # unten) erkennt, unabhaengig von der Boundary-Textformatierung - genau
    # deshalb waren alle vier oben genannten FFmpeg-eigenen Tests
    # erfolgreich. Der strikte "multipart/x-mixed-replace"-Parser der
    # Browser fuer <img>-Tags verlangt dagegen eine korrekt begrenzte
    # Boundary/Header-Struktur und kann die Bildgrenzen in diesem Format
    # offenbar nicht zuverlaessig erkennen, was zu einem dauerhaft leeren/
    # schwarzen Bild ohne jede Fehlermeldung fuehrt - exakt das beobachtete
    # Verhalten.
    #
    # Die bereits bestehende, nachweislich funktionierende A1-Kamera
    # (bambu_mjpeg_generator() weiter oben) umgeht dieses Problem, indem
    # sie das Multipart-Format selbst erzeugt: boundary "--frame", CRLF-
    # Zeilenenden und ein expliziter "Content-Length"-Header pro Bild.
    # Fuer den RTSPS-Pfad bauen wir jetzt denselben, bereits bewaehrten
    # Mechanismus nach: FFmpeg liefert ueber den Standard-Muxer
    # "image2pipe" (siehe Kommandozeile oben) nur noch die rohen JPEG-
    # Bilddaten hintereinander, ohne jegliches Text-Wrapping. Wir trennen
    # diese Bilder anhand der im JPEG-Format fest definierten (nicht
    # geratenen) binaeren Marker auf: jedes JPEG beginnt mit dem SOI-Marker
    # 0xFFD8 ("Start of Image") und endet mit dem EOI-Marker 0xFFD9 ("End
    # of Image"). Mit diesen eindeutigen Grenzen verpacken wir jedes Bild
    # exakt wie bei der A1-Kamera erneut in ein korrektes Multipart-Format.
    SOI_MARKER = b"\xff\xd8"
    EOI_MARKER = b"\xff\xd9"
    MAX_FRAME_BUFFER_BYTES = 10_000_000  # Sicherheitsgrenze gegen unbegrenztes Wachstum bei kaputten/fehlenden Endmarkern
    buf = bytearray()
    try:
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                exit_code = proc.poll()
                print(f"[MK6-FFMPEG] (Drucker-IP {ip}): Stream beendet "
                      f"(FFmpeg-Exitcode: {exit_code!r}).")
                break
            buf += chunk
            while True:
                start = buf.find(SOI_MARKER)
                if start == -1:
                    # Kein Bildanfang im Puffer - bis auf das letzte Byte
                    # verwerfen (falls der Marker genau an der Grenze
                    # zweier FFmpeg-Lesevorgaenge zerschnitten wurde).
                    if len(buf) > 1:
                        del buf[:-1]
                    break
                if start > 0:
                    del buf[:start]
                end = buf.find(EOI_MARKER, 2)
                if end == -1:
                    if len(buf) > MAX_FRAME_BUFFER_BYTES:
                        print(f"[MK6-FFMPEG] (Drucker-IP {ip}): Puffer ohne "
                              f"JPEG-Endmarker ueber {MAX_FRAME_BUFFER_BYTES} "
                              f"Bytes gewachsen - verwerfe Puffer.")
                        del buf[:]
                    break
                frame = bytes(buf[:end + 2])
                del buf[:end + 2]
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n"
                       b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n" +
                       frame + b"\r\n")
    except Exception as e:
        print(f"[MK6-FFMPEG] (Drucker-IP {ip}): FEHLER waehrend des Streamens: {e!r}")
    finally:
        # Verhindert, dass bei einem Browser-Tab-Wechsel/Schliessen des
        # Kamera-Fensters der FFmpeg-Subprozess (und damit die
        # RTSPS-Verbindung zum Drucker) unbemerkt weiterlaeuft - Flask
        # ruft den finally-Block eines Response-Generators zuverlaessig
        # auf, sobald die Verbindung zum Browser endet (auch bei
        # abgebrochener Uebertragung).
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.stdout.close()
        except Exception:
            pass
        try:
            proc.stderr.close()
        except Exception:
            pass


# v2.4.0: baut Benutzername/Passwort (getrennt in config.json gespeichert,
# siehe DashboardApp.add_rtsp_camera()) in die vom Nutzer hinterlegte
# RTSP(S)-URL ein, statt den Nutzer zu zwingen, sie selbst als
# "rtsp://user:pass@host:port/pfad" von Hand zusammenzusetzen - das
# scheitert bei Sonderzeichen im Passwort (z. B. "@", ":" oder "/"), die
# in dieser Position per RFC 3986 prozentkodiert werden muessten.
# urllib.parse.quote() uebernimmt genau das. Ist weder Benutzername noch
# Passwort gesetzt, bleibt die URL unveraendert (deckt weiterhin den
# Fall ab, dass der Nutzer die Zugangsdaten - wie vor v2.4.0 einzig
# moeglich - bereits selbst in die URL eingebaut hat). Sind sie gesetzt,
# ersetzen sie etwaige bereits in der URL enthaltene Zugangsdaten
# vollstaendig (eindeutiger Vorrang, keine Vermischung zweier Quellen).
def build_rtsp_url_with_auth(url: str, username: str, password: str) -> str:
    if not username and not password:
        return url
    parsed = urllib.parse.urlsplit(url)
    user_enc = urllib.parse.quote(username or "", safe="")
    pass_enc = urllib.parse.quote(password or "", safe="")
    credentials = user_enc + (":" + pass_enc if pass_enc else "")
    host = parsed.hostname or ""
    # v2.4.0: IPv6-Hosts muessen in der Netloc wieder in eckige Klammern
    # gefasst werden (urlsplit().hostname liefert sie OHNE Klammern
    # zurueck) - siehe RFC 3986 Abschnitt 3.2.2. Bambu/IP-Kameras im LAN
    # nutzen praktisch immer IPv4, das wird hier defensiv trotzdem korrekt
    # behandelt statt nur fuer IPv4 anzunehmen.
    if host and ":" in host:
        host = f"[{host}]"
    netloc = host + (f":{parsed.port}" if parsed.port else "")
    new_netloc = f"{credentials}@{netloc}" if credentials else netloc
    return urllib.parse.urlunsplit((parsed.scheme, new_netloc, parsed.path, parsed.query, parsed.fragment))


# v2.3.0: frei konfigurierbare, vom Drucker UNABHAENGIGE RTSP(S)-Kamera
# (z. B. eine Raumuebersichtskamera, siehe DashboardApp.add_rtsp_camera()).
# Bewusst eine EIGENSTAENDIGE Funktion statt einer Umbau/Parametrisierung
# von bambu_rtsp_mjpeg_generator() oben: Letztere ist auf echter X1E-/H2D-
# Pro-Hardware ausfuehrlich diagnostiziert und bestaetigt funktionsfaehig
# (siehe deren Kommentarblock) - additiv bleiben heisst hier, den bereits
# bewiesenen Pfad nicht anzufassen, auch wenn das etwas Code verdoppelt.
# Die FFmpeg-Kommandozeile und das JPEG-Marker-basierte Neuverpacken ins
# bewaehrte "--frame"-Multipart-Format (siehe ausfuehrliche Begruendung
# oben bei bambu_rtsp_mjpeg_generator()) sind identisch; einziger
# fachlicher Unterschied: die URL kommt hier bereits vollstaendig vom
# Nutzer (kein fest zusammengebautes "rtsps://bblp:<code>@<ip>:322/...")
# und "-tls_verify 0" wird nur bei "rtsps://"-URLs gesetzt (die Option
# existiert fuer reines "rtsp://" nicht/ist dort bedeutungslos, siehe
# ffmpeg-protocols(1): "tls_verify" gehoert zum TLS-Transport).
def generic_rtsp_mjpeg_generator(rtsp_url: str, ffmpeg_path: str, label: str):
    cmd = [
        ffmpeg_path,
        "-loglevel", "error",
        "-rtsp_transport", "tcp",
        "-timeout", "15000000",
    ]
    if rtsp_url.strip().lower().startswith("rtsps://"):
        cmd += ["-tls_verify", "0"]
    cmd += [
        "-i", rtsp_url,
        "-an",
        "-c:v", "mjpeg",
        "-q:v", "5",
        "-r", "10",
        "-f", "image2pipe",
        "-",
    ]
    print(f"[MK6-FFMPEG] (Kamera '{label}'): Starte FFmpeg-Prozess fuer RTSP-Kamera-Stream...")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        print(f"[MK6-FFMPEG] (Kamera '{label}'): FEHLER beim Start von FFmpeg: {e!r} "
              f"(Pfad: {ffmpeg_path!r})")
        return
    print(f"[MK6-FFMPEG] (Kamera '{label}'): FFmpeg-Prozess gestartet (PID {proc.pid}).")
    stderr_thread = threading.Thread(target=_drain_ffmpeg_stderr, args=(proc, f"Kamera '{label}'"), daemon=True)
    stderr_thread.start()
    SOI_MARKER = b"\xff\xd8"
    EOI_MARKER = b"\xff\xd9"
    MAX_FRAME_BUFFER_BYTES = 10_000_000
    buf = bytearray()
    try:
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                exit_code = proc.poll()
                print(f"[MK6-FFMPEG] (Kamera '{label}'): Stream beendet "
                      f"(FFmpeg-Exitcode: {exit_code!r}).")
                break
            buf += chunk
            while True:
                start = buf.find(SOI_MARKER)
                if start == -1:
                    if len(buf) > 1:
                        del buf[:-1]
                    break
                if start > 0:
                    del buf[:start]
                end = buf.find(EOI_MARKER, 2)
                if end == -1:
                    if len(buf) > MAX_FRAME_BUFFER_BYTES:
                        print(f"[MK6-FFMPEG] (Kamera '{label}'): Puffer ohne "
                              f"JPEG-Endmarker ueber {MAX_FRAME_BUFFER_BYTES} "
                              f"Bytes gewachsen - verwerfe Puffer.")
                        del buf[:]
                    break
                frame = bytes(buf[:end + 2])
                del buf[:end + 2]
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n"
                       b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n" +
                       frame + b"\r\n")
    except Exception as e:
        print(f"[MK6-FFMPEG] (Kamera '{label}'): FEHLER waehrend des Streamens: {e!r}")
    finally:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.stdout.close()
        except Exception:
            pass
        try:
            proc.stderr.close()
        except Exception:
            pass


# ----------------------------------------------------------------------
# Formlabs (Drucker, Wash L, Cure L) ueber die offizielle Local API
# ----------------------------------------------------------------------
def _walk_json(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _walk_json(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_json(item)


def _find_first(obj, candidate_keys):
    lowered = {c.lower() for c in candidate_keys}
    for k, v in _walk_json(obj):
        if isinstance(k, str) and k.lower() in lowered and v not in (None, ""):
            return v
    return None


FL_PROGRESS_KEYS = ["progress_percentage", "percent_complete", "progress",
                     "print_progress", "completion_percentage", "percentage"]
FL_FILE_KEYS = ["job_name", "print_file_name", "current_job_name",
                "file_name", "job", "print_name", "current_job"]
FL_MATERIAL_KEYS = ["material_name", "material", "cartridge_material",
                     "resin_type", "material_code", "tank_material"]
FL_STATE_KEYS = ["status", "state", "print_status", "device_status", "machine_state"]


class FormlabsLocalApiConnection:
    """Fragt den Status eines Formlabs-Geraets (Drucker, Form Wash L oder
    Form Cure L) ueber die offizielle "Formlabs Local API" ab.

    WICHTIG - Voraussetzung: Formlabs bietet KEINE direkt auf dem Geraet
    unter seiner eigenen IP erreichbare Status-API an. Die einzige von
    Formlabs offiziell dokumentierte Moeglichkeit, lokal per IP an
    Geraetestatus zu kommen, ist die "Formlabs Local API": dafuer muss
    zusaetzlich auf einem PC im selben Netzwerk (typischerweise dem PC,
    auf dem auch dieses Dashboard laeuft) das kostenlose Programm
    "PreFormServer" (Teil der normalen PreForm-Installation) im
    Hintergrund laufen, z. B. gestartet mit:

        PreFormServer.exe --port 44388

    Dieses Dashboard verbindet sich dann zu http://localhost:44388
    (konfigurierbar ueber "preform_server" in config.json) und fragt dort
    den Status des Geraets mit der hinterlegten IP-Adresse ab. Laeuft kein
    PreFormServer, bleibt die Karte zwangslaeufig ohne Daten - das ist eine
    Einschraenkung von Formlabs selbst, nicht dieses Programms.

    Die Original-Geraete "Form Wash" und "Form Cure" (ohne "L") haben laut
    Formlabs KEINE Netzwerkfunktion und koennen technisch nicht
    eingebunden werden - nur die "L"-Varianten (Form Wash L / Form Cure L).

    Das genaue JSON-Format der Geraeteantwort kann sich je nach
    Geraetetyp/Firmware unterscheiden. Diese Klasse durchsucht die Antwort
    daher defensiv nach den wichtigsten Feldern (siehe FL_*_KEYS oben),
    statt starre Schluessel vorauszusetzen.
    """

    POLL_INTERVAL_SEC = 5

    def __init__(self, printer_cfg: dict, preform_server_url: str):
        self.cfg = printer_cfg
        self.id = printer_cfg["id"]
        self.preform_url = (preform_server_url or DEFAULT_CONFIG["preform_server"]).rstrip("/")
        self.status = {
            "connected": False,
            "last_update": None,
            "progress": 0,
            "file_name": "-",
            "material": "-",
            "device_status": "UNKNOWN",
            "error": None
        }
        self._stop = False
        self._device_id = None

    def start(self):
        self._stop = False
        threading.Thread(target=self._poll_loop, daemon=True).start()

    def stop(self):
        self._stop = True

    def _poll_loop(self):
        self._discover()
        while not self._stop:
            try:
                self._refresh()
            except urllib.error.URLError:
                self.status["connected"] = False
                self.status["error"] = (
                    f"PreFormServer unter {self.preform_url} nicht erreichbar. "
                    f"Laeuft PreFormServer.exe im Hintergrund?"
                )
            except Exception as e:
                self.status["connected"] = False
                self.status["error"] = str(e)
            time.sleep(self.POLL_INTERVAL_SEC)

    def _http_json(self, method, path, payload=None):
        url = f"{self.preform_url}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            raw = resp.read()
        return json.loads(raw.decode("utf-8", errors="ignore")) if raw else {}

    def _discover(self):
        try:
            self._http_json("POST", "/discover-devices/",
                             {"ip_address": self.cfg["ip"], "timeout_seconds": 8})
        except Exception:
            pass

    def _refresh(self):
        data = self._http_json("GET", "/devices/")
        devices = data.get("devices", [])
        match = next((d for d in devices if d.get("ip_address") == self.cfg["ip"]), None)

        if not match:
            self.status["connected"] = False
            self.status["error"] = (
                "Geraet mit dieser IP wurde vom PreFormServer (noch) nicht gefunden. "
                "Pruefen: PreFormServer laeuft, Geraet ist eingeschaltet und im "
                "gleichen Netzwerk erreichbar."
            )
            return

        self.status["error"] = None
        self._device_id = match.get("id")
        detail = match
        if self._device_id:
            try:
                detail = self._http_json("GET", f"/devices/{self._device_id}/")
            except Exception:
                pass

        self.status["connected"] = bool(match.get("is_connected", True))

        state = _find_first(detail, FL_STATE_KEYS)
        if state:
            self.status["device_status"] = str(state).upper()

        progress_raw = _find_first(detail, FL_PROGRESS_KEYS)
        if progress_raw is not None:
            try:
                pct = float(progress_raw)
                if pct <= 1:
                    pct *= 100
                self.status["progress"] = round(pct, 1)
            except (TypeError, ValueError):
                pass

        file_name = _find_first(detail, FL_FILE_KEYS)
        if file_name:
            self.status["file_name"] = str(file_name)

        if self.cfg.get("type") == "formlabs":
            material = _find_first(detail, FL_MATERIAL_KEYS)
            if material:
                self.status["material"] = str(material)

        self.status["last_update"] = datetime.now().strftime("%H:%M:%S")


# ----------------------------------------------------------------------
# OctoPrint (offiziell dokumentierte REST-API, https://docs.octoprint.org)
# ----------------------------------------------------------------------
class OctoPrintConnection:
    """Bindet einen 3D-Drucker mit angeschlossenem OctoPrint (z. B. an
    einem Raspberry Pi) genauso ein wie einen Bambu Lab Drucker: gleiche
    Kartenansicht mit Fortschritt, Dateiname, Temperaturen und Kamera.

    Benoetigt einen OctoPrint API-Key (OctoPrint -> Einstellungen ->
    API -> "API Key").

    Hinweis: OctoPrint liefert i. d. R. keine Kammertemperatur (nur
    Duesen- und Betttemperatur) und kein AMS-Aequivalent - diese Felder
    bleiben daher bei OctoPrint-Druckern leer, das ist kein Fehler.
    """

    POLL_INTERVAL_SEC = 3

    def __init__(self, printer_cfg: dict):
        self.cfg = printer_cfg
        self.id = printer_cfg["id"]
        self.status = {
            "connected": False,
            "last_update": None,
            "gcode_state": "UNKNOWN",
            "progress": 0,
            "file_name": "-",
            "chamber_temp": None,
            "nozzle_temp": None,
            "bed_temp": None,
            "remaining_min": None,
            "ams": [],
            "error": None
        }
        self._stop = False

    def start(self):
        self._stop = False
        threading.Thread(target=self._poll_loop, daemon=True).start()

    def stop(self):
        self._stop = True

    def _poll_loop(self):
        while not self._stop:
            try:
                self._refresh()
            except urllib.error.URLError:
                self.status["connected"] = False
                self.status["error"] = "OctoPrint nicht erreichbar (IP/Port pruefen)."
            except urllib.error.HTTPError as e:
                self.status["connected"] = False
                if e.code == 403:
                    self.status["error"] = "OctoPrint hat den API-Key abgelehnt (403)."
                else:
                    self.status["error"] = f"OctoPrint HTTP-Fehler {e.code}."
            except Exception as e:
                self.status["connected"] = False
                self.status["error"] = str(e)
            time.sleep(self.POLL_INTERVAL_SEC)

    def _base_url(self):
        scheme = "https" if self.cfg.get("https") else "http"
        port = int(self.cfg.get("port", 80))
        return f"{scheme}://{self.cfg['ip']}:{port}"

    def _get(self, path):
        url = self._base_url() + path
        req = urllib.request.Request(url, headers={"X-Api-Key": self.cfg.get("api_key", "")})
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read()
        return json.loads(raw.decode("utf-8", errors="ignore")) if raw else {}

    # v2.9.0: laufenden Druck abbrechen - POST /api/job mit
    # {"command": "cancel"}, offiziell dokumentierter OctoPrint-Endpunkt
    # ("Issue a job command", docs.octoprint.org/en/master/api/job.html).
    def cancel_print(self):
        url = self._base_url() + "/api/job"
        body = json.dumps({"command": "cancel"}).encode()
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"X-Api-Key": self.cfg.get("api_key", ""), "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 409:
                raise RuntimeError(
                    "OctoPrint meldet: aktuell kein Druckauftrag aktiv, der "
                    "abgebrochen werden koennte (HTTP 409)."
                ) from e
            if e.code == 403:
                raise RuntimeError("OctoPrint hat den API-Key abgelehnt (403).") from e
            raise RuntimeError(f"OctoPrint lehnte den Abbruch-Befehl ab (HTTP {e.code}).") from e

    def _refresh(self):
        printer = self._get("/api/printer")
        job = self._get("/api/job")

        self.status["connected"] = True
        self.status["error"] = None

        state_text = (printer.get("state") or {}).get("text", "UNKNOWN")
        self.status["gcode_state"] = str(state_text).upper()

        temps = printer.get("temperature") or {}
        tool0 = temps.get("tool0") or {}
        bed = temps.get("bed") or {}
        if tool0.get("actual") is not None:
            self.status["nozzle_temp"] = tool0["actual"]
        if bed.get("actual") is not None:
            self.status["bed_temp"] = bed["actual"]

        job_info = job.get("job") or {}
        file_info = job_info.get("file") or {}
        if file_info.get("name"):
            self.status["file_name"] = file_info["name"]

        progress = job.get("progress") or {}
        completion = progress.get("completion")
        if completion is not None:
            self.status["progress"] = round(completion, 1)

        remaining = progress.get("printTimeLeft")
        if remaining is not None:
            self.status["remaining_min"] = round(remaining / 60)

        self.status["last_update"] = datetime.now().strftime("%H:%M:%S")


# ----------------------------------------------------------------------
# Creality (Klipper-basierte Modelle: K1 / K1C / K1 Max / K1 SE sowie
# jeder andere Klipper-faehige Creality-Drucker), ueber die offizielle
# Moonraker-API (https://moonraker.readthedocs.io)
# ----------------------------------------------------------------------
class CrealityConnection:
    """Bindet einen Creality-Drucker mit Klipper-Firmware ueber die
    offizielle Moonraker-API ein (das Backend hinter Fluidd/Mainsail).

    Die Moonraker-API selbst ist bei allen Klipper-faehigen Creality-
    Druckern identisch (K1, K1C, K1 Max, K1 SE, oder ein Ender/CR-Drucker
    mit Klipper-Umbau z. B. per Sonic Pad) - das in config.json hinterlegte
    "type"-Feld (creality_k1 / creality_k1c / creality_k1max /
    creality_k1se / creality_other) dient daher NUR der Beschriftung auf
    der Karte, nicht einer unterschiedlichen technischen Anbindung.

    WICHTIGE Voraussetzung: Auf den werkseitigen K1/K1C/K1 Max/K1 SE ist
    Moonraker NICHT vorinstalliert. Der Drucker muss zuerst per SSH
    "gerootet" und Moonraker manuell nachinstalliert werden (z. B. ueber
    das verbreitete Creality-Helper-Script) - siehe README fuer Details.
    Ist Moonraker nicht erreichbar, bleibt die Karte ohne Daten und zeigt
    einen entsprechenden Hinweis an.

    Neuere Modelle mit reinem "Creality OS" ohne Klipper (z. B. Ender-3 V3
    SE) werden bewusst NICHT unterstuetzt, da es dafuer keine offiziell
    dokumentierte lokale Status-API gibt - eine Anbindung waere reines
    Rätselraten wie zuvor beim ersten (fehlgeschlagenen) Formlabs-Versuch.
    """

    POLL_INTERVAL_SEC = 3

    def __init__(self, printer_cfg: dict):
        self.cfg = printer_cfg
        self.id = printer_cfg["id"]
        self.status = {
            "connected": False,
            "last_update": None,
            "gcode_state": "UNKNOWN",
            "progress": 0,
            "file_name": "-",
            "chamber_temp": None,
            "nozzle_temp": None,
            "bed_temp": None,
            "remaining_min": None,
            "ams": [],
            "error": None
        }
        self._stop = False
        self._chamber_object_name = None   # per Discovery ermittelt, falls vorhanden

    def start(self):
        self._stop = False
        threading.Thread(target=self._poll_loop, daemon=True).start()

    def stop(self):
        self._stop = True

    def _poll_loop(self):
        self._discover_objects()
        while not self._stop:
            try:
                self._refresh()
            except urllib.error.URLError:
                self.status["connected"] = False
                self.status["error"] = "Moonraker nicht erreichbar (IP/Port pruefen, laeuft Moonraker auf dem Drucker?)."
            except urllib.error.HTTPError as e:
                self.status["connected"] = False
                self.status["error"] = f"Moonraker HTTP-Fehler {e.code}."
            except Exception as e:
                self.status["connected"] = False
                self.status["error"] = str(e)
            time.sleep(self.POLL_INTERVAL_SEC)

    def _base_url(self):
        return f"http://{self.cfg['ip']}:{int(self.cfg.get('port', 7125))}"

    def _get(self, path):
        url = self._base_url() + path
        headers = {}
        if self.cfg.get("api_key"):
            headers["X-Api-Key"] = self.cfg["api_key"]
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read()
        return json.loads(raw.decode("utf-8", errors="ignore")) if raw else {}

    # v2.9.0: laufenden Druck abbrechen - POST /printer/print/cancel,
    # offiziell dokumentierter Moonraker-Endpunkt (moonraker.readthedocs.io,
    # Abschnitt "Printer Administration").
    def cancel_print(self):
        url = self._base_url() + "/printer/print/cancel"
        headers = {}
        if self.cfg.get("api_key"):
            headers["X-Api-Key"] = self.cfg["api_key"]
        req = urllib.request.Request(url, data=b"", method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Moonraker lehnte den Abbruch-Befehl ab (HTTP {e.code}).") from e

    def _discover_objects(self):
        """Fragt einmalig ab, welche Klipper-Objekte auf diesem Drucker
        ueberhaupt existieren, um z. B. einen optionalen Kammer-
        Temperatursensor (falls per Klipper-Config vorhanden, z. B. beim
        K1 Max) nur dann mit abzufragen, wenn er wirklich da ist - fehlt
        er und wird trotzdem abgefragt, lehnt Moonraker die ganze Anfrage ab."""
        try:
            data = self._get("/printer/objects/list")
            objects = data.get("result", {}).get("objects", [])
            chamber = next(
                (o for o in objects if o.lower().startswith("temperature_sensor") and "chamber" in o.lower()),
                None
            )
            self._chamber_object_name = chamber
        except Exception:
            self._chamber_object_name = None

    def _refresh(self):
        objs = ["print_stats", "display_status", "extruder", "heater_bed"]
        if self._chamber_object_name:
            objs.append(self._chamber_object_name)
        query = "&".join(urllib.parse.quote(o) for o in objs)

        data = self._get(f"/printer/objects/query?{query}")
        status = (data.get("result") or {}).get("status", {})

        self.status["connected"] = True
        self.status["error"] = None

        ps = status.get("print_stats") or {}
        if ps.get("state"):
            self.status["gcode_state"] = str(ps["state"]).upper()
        if ps.get("filename"):
            self.status["file_name"] = ps["filename"]

        ds = status.get("display_status") or {}
        progress = ds.get("progress")
        if progress is not None:
            self.status["progress"] = round(float(progress) * 100, 1)

        extruder = status.get("extruder") or {}
        if extruder.get("temperature") is not None:
            self.status["nozzle_temp"] = round(extruder["temperature"], 1)

        bed = status.get("heater_bed") or {}
        if bed.get("temperature") is not None:
            self.status["bed_temp"] = round(bed["temperature"], 1)

        if self._chamber_object_name and self._chamber_object_name in status:
            chamber_obj = status[self._chamber_object_name] or {}
            if chamber_obj.get("temperature") is not None:
                self.status["chamber_temp"] = round(chamber_obj["temperature"], 1)

        self.status["last_update"] = datetime.now().strftime("%H:%M:%S")


# ----------------------------------------------------------------------
# Ultimaker (S-Serie, UM3) ueber die offizielle lokale Drucker-API
# ----------------------------------------------------------------------

def _parse_digest_challenge(header_value: str) -> dict:
    """Parst einen "WWW-Authenticate: Digest ..."-Header (RFC 2617) in
    ein Dict aus Schluessel/Wert-Paaren (u. a. realm, nonce, qop,
    opaque, algorithm). Keine externe Bibliothek noetig - reines
    Parsen einer kommagetrennten "schluessel=wert"-Liste, bei der Werte
    optional in Anfuehrungszeichen stehen."""
    parts = {}
    body = header_value.split(" ", 1)[1] if " " in header_value else header_value
    for match in re.finditer(r'(\w+)=("(?:[^"\\]|\\.)*"|[^,]*)', body):
        key, val = match.group(1), match.group(2)
        parts[key] = val.strip('"')
    return parts


def _build_digest_authorization(challenge: dict, username: str, password: str,
                                 method: str, uri: str) -> str:
    """Baut den Wert des Authorization-Headers (RFC 2617, MD5, optional
    qop=auth) fuer eine Digest-authentifizierte Anfrage - anhand einer
    zuvor per _parse_digest_challenge() erhaltenen Challenge. Reine
    Python-Standardbibliothek (hashlib/secrets), keine externe
    Digest-Auth-Bibliothek noetig."""
    realm = challenge.get("realm", "")
    nonce = challenge.get("nonce", "")
    qop = challenge.get("qop", "")
    opaque = challenge.get("opaque")
    algorithm = challenge.get("algorithm") or "MD5"

    ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
    ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
    nc = "00000001"
    cnonce = secrets.token_hex(8)

    if qop:
        # RFC 2617 qop=auth: response haengt zusaetzlich von nc/cnonce ab,
        # um Replay-Angriffe zu erschweren.
        response = hashlib.md5(
            f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}".encode()
        ).hexdigest()
    else:
        response = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()

    fields = [
        f'username="{username}"', f'realm="{realm}"', f'nonce="{nonce}"',
        f'uri="{uri}"', f'response="{response}"',
    ]
    if qop:
        fields += [f'qop={qop}', f'nc={nc}', f'cnonce="{cnonce}"']
    if opaque:
        fields.append(f'opaque="{opaque}"')
    if algorithm:
        fields.append(f'algorithm={algorithm}')
    return "Digest " + ", ".join(fields)


def _build_multipart_body(boundary: str, fields: list, files: list) -> bytes:
    """Baut den Rohkoerper einer multipart/form-data-Anfrage (RFC 7578)
    von Hand zusammen - urllib (im Gegensatz zu z. B. der externen
    requests-Bibliothek) hat dafuer keine eingebaute Unterstuetzung, und
    fuer dieses eine Formular (ein Textfeld + eine Datei) lohnt sich
    keine zusaetzliche Abhaengigkeit.
    fields: Liste von (name, wert)-Tupeln (einfache Textfelder).
    files: Liste von (name, dateiname, inhalt_bytes)-Tupeln."""
    parts = []
    for name, value in fields:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    for name, filename, content in files:
        parts.append(
            (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
             f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
        )
        parts.append(content)
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts)


class UltimakerConnection:
    """Bindet einen netzwerkfaehigen Ultimaker-Drucker (UM3, S3, S5, S7,
    Factor 4, ...) ueber dessen offizielle, direkt auf dem Drucker
    laufende lokale REST-API ein: http://<Drucker-IP>/api/v1/ (Swagger-
    Dokumentation dazu ist direkt am Drucker unter
    http://<Drucker-IP>/docs/api/ abrufbar).

    Diese API ist fuer reine Status-Abfragen OHNE Authentifizierung
    nutzbar - ein Login/API-Key wird laut Ultimaker-Dokumentation nur
    fuer schreibende Aktionen (z. B. Druckauftrag starten) benoetigt.
    Dieses Dashboard fragt ausschliesslich lesend ab, es ist daher kein
    API-Key noetig.

    Verwendete Endpunkte:
      GET /api/v1/printer/status                                -> Status-Text (z. B. "printing", "idle")
      GET /api/v1/print_job                                     -> aktueller Druckauftrag (404 wenn keiner laeuft)
      GET /api/v1/printer/bed/temperature                       -> {"current":.., "target":..}
      GET /api/v1/printer/heads/0/extruders/0/hotend/temperature -> {"current":.., "target":..}

    Hinweis: Ultimaker-Desktopdrucker (UM3/S-Serie) haben keinen
    Kammertemperatursensor - dieses Feld bleibt daher immer leer, das
    ist normal und kein Fehler.
    """

    POLL_INTERVAL_SEC = 3

    def __init__(self, printer_cfg: dict):
        self.cfg = printer_cfg
        self.id = printer_cfg["id"]
        self.status = {
            "connected": False,
            "last_update": None,
            "gcode_state": "UNKNOWN",
            "progress": 0,
            "file_name": "-",
            "chamber_temp": None,
            "nozzle_temp": None,
            "bed_temp": None,
            "remaining_min": None,
            "error": None
        }
        self._stop = False

    def start(self):
        self._stop = False
        threading.Thread(target=self._poll_loop, daemon=True).start()

    def stop(self):
        self._stop = True

    def _poll_loop(self):
        while not self._stop:
            try:
                self._refresh()
            except urllib.error.URLError:
                self.status["connected"] = False
                self.status["error"] = "Drucker nicht erreichbar (IP/Port pruefen)."
            except Exception as e:
                self.status["connected"] = False
                self.status["error"] = str(e)
            time.sleep(self.POLL_INTERVAL_SEC)

    def _base_url(self):
        return f"http://{self.cfg['ip']}:{int(self.cfg.get('port', 80))}"

    def _get(self, path):
        url = self._base_url() + path
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read()
        return json.loads(raw.decode("utf-8", errors="ignore")) if raw else None

    def _refresh(self):
        state = self._get("/api/v1/printer/status")
        self.status["connected"] = True
        self.status["error"] = None
        if isinstance(state, str) and state:
            self.status["gcode_state"] = state.upper()

        # Kein aktiver Druckauftrag -> Ultimaker antwortet hier mit 404,
        # das ist der Normalfall im Leerlauf, keine Fehlermeldung wert.
        try:
            job = self._get("/api/v1/print_job")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                job = None
            else:
                raise

        if job:
            if job.get("name"):
                self.status["file_name"] = job["name"]
            progress = job.get("progress")
            if progress is not None:
                self.status["progress"] = round(float(progress) * 100, 1)
            elapsed = job.get("time_elapsed")
            total = job.get("time_total")
            if elapsed is not None and total is not None and total > elapsed:
                self.status["remaining_min"] = round((total - elapsed) / 60)
        else:
            self.status["file_name"] = "-"
            self.status["progress"] = 0
            self.status["remaining_min"] = None

        try:
            bed = self._get("/api/v1/printer/bed/temperature")
            if bed and bed.get("current") is not None:
                self.status["bed_temp"] = round(bed["current"], 1)
        except Exception:
            pass

        try:
            hotend = self._get("/api/v1/printer/heads/0/extruders/0/hotend/temperature")
            if hotend and hotend.get("current") is not None:
                self.status["nozzle_temp"] = round(hotend["current"], 1)
        except Exception:
            pass

        self.status["last_update"] = datetime.now().strftime("%H:%M:%S")

    # ------------------------------------------------------------------
    # Druckauftrag per Drag & Drop (seit v1.6.3)
    #
    # Anders als die reinen Status-Abfragen oben verlangt die Ultimaker-
    # API fuer schreibende Aktionen (Datei hochladen + Druck starten)
    # eine Authentifizierung per HTTP Digest Auth mit einem id/key-Paar,
    # das der Drucker erst nach BESTAETIGUNG AM EIGENEN DISPLAY ausgibt
    # ("Kopplung", vergleichbar mit Bluetooth-Pairing) - siehe
    # start_pairing()/check_pairing(). Quelle: offizielle Ultimaker-
    # Swagger-Dokumentation (direkt am Drucker unter /docs/api/
    # abrufbar) sowie mehrere unabhaengige Community-Threads im
    # UltiMaker-Forum, die den Ablauf uebereinstimmend beschreiben -
    # keine geratenen Endpunkte.
    # ------------------------------------------------------------------
    def start_pairing(self):
        """Schritt 1 von 2 der Kopplung: fragt beim Drucker eine neue
        id/key-Kombination an. Der Drucker zeigt danach am eigenen
        Display eine Bestaetigungs-Abfrage - die Kombination ist erst
        gueltig, nachdem der Nutzer dort zugestimmt hat (siehe
        check_pairing()). "application"/"user" sind Pflichtfelder laut
        Ultimaker-API (ohne sie: Fehler "application or user not
        supplied") und werden nur am Drucker-Display angezeigt, damit
        erkennbar ist, welche Anwendung um Zugriff bittet."""
        body = urllib.parse.urlencode({
            "application": "DruckerDashboard",
            "user": "dashboard",
        }).encode()
        req = urllib.request.Request(
            self._base_url() + "/api/v1/auth/request",
            data=body, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["id"], data["key"]

    def check_pairing(self, auth_id: str) -> str:
        """Schritt 2: fragt ab, ob der Nutzer die Kopplungsanfrage am
        Drucker-Display bereits bestaetigt (oder abgelehnt) hat. Liefert
        den vom Drucker gemeldeten Status als String, typischerweise
        "authorized", "unauthorized" oder ein Zwischenzustand, waehrend
        noch niemand am Display reagiert hat."""
        req = urllib.request.Request(
            self._base_url() + f"/api/v1/auth/check/{auth_id}",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("message", "unknown")

    def _digest_challenge_or_none(self, timeout: float = 5.0):
        """Versucht, ueber eine leere Anfrage (POST OHNE Datei) an das
        eigentliche Ziel-Endpunkt (/api/v1/print_job) eine 401-Antwort
        mit "WWW-Authenticate: Digest ..." zu erhalten. Liefert die
        geparste Challenge (dict), oder **None**, falls der Drucker gar
        keine Digest-Authentifizierung fuer Druckauftraege verlangt -
        in dem Fall sendet send_print() den Upload ganz ohne
        Authorization-Header.

        Dadurch muss der eigentliche Datei-Upload nur EINMAL gesendet
        werden (kein zweimaliges Senden wie bei generischen Digest-
        Auth-Bibliotheken ueblich), UND die Implementierung funktioniert
        sowohl mit echter Ultimaker-Hardware (verlangt zwingend Digest-
        Auth) als auch mit vereinfachten Nachbauten der Ultimaker-API
        (z. B. eigenen Heimprojekten), die den Druckstart bewusst OHNE
        Authentifizierung implementieren - siehe UEBERGABE.md fuer den
        konkreten Fall, der zu dieser Anpassung gefuehrt hat: dort
        prueft der `/print_job`-Endpunkt lediglich, ob ein Datei-Feld
        mitgeschickt wurde, aber keinerlei Anmeldedaten.

        WICHTIG (v1.6.5 - Korrektur): Vorherige Versionen warfen bei
        JEDER Antwort ausser 401 eine Exception, in der Annahme, jeder
        Ultimaker-kompatible Drucker wuerde zwingend Digest-Auth
        verlangen. Das war zu strikt - eine 400-Antwort (wie beim oben
        beschriebenen Nachbau, dessen /print_job-Handler die leere
        Probe-Anfrage schlicht als "keine Datei mitgeschickt" ablehnt,
        OHNE ueberhaupt eine Authentifizierungspruefung zu erreichen)
        bedeutet nicht zwangslaeufig einen Fehler - es kann schlicht
        heissen, dass keine Authentifizierung noetig ist."""
        req = urllib.request.Request(
            self._base_url() + "/api/v1/print_job",
            data=b"", method="POST",
            headers={"Accept": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=timeout)
            # Akzeptierte sogar die leere Anfrage klaglos -> definitiv
            # keine Authentifizierung noetig.
            return None
        except urllib.error.HTTPError as e:
            if e.code == 401:
                www_auth = e.headers.get("WWW-Authenticate", "")
                if www_auth.lower().startswith("digest"):
                    return _parse_digest_challenge(www_auth)
                raise RuntimeError(f"Unerwartetes Authentifizierungsschema vom Drucker: {www_auth!r}") from e
            # Jede andere Fehlerantwort (z. B. 400 "kein Datei-Feld
            # gefunden") deutet darauf hin, dass der Endpunkt ueberhaupt
            # keine Authentifizierung prueft - der Fehler kommt allein
            # daher, dass die Probe-Anfrage absichtlich keine Datei
            # mitschickt. In dem Fall wird ohne Anmeldedaten gesendet;
            # sollte das tatsaechlich falsch sein, meldet der spaetere
            # echte Upload-Versuch das ueber einen klaren 401-Fehler
            # (siehe send_print()).
            return None

    def send_print(self, local_path: str, job_name: str, on_progress=None):
        """Laedt local_path (eine fertig gesclicte .gcode-Datei, z. B.
        aus Cura exportiert) per POST an /api/v1/print_job hoch und
        startet den Druck - mit Digest-Authentifizierung, falls der
        Drucker das verlangt (siehe _digest_challenge_or_none()), sonst
        ohne. Setzt eine vorherige erfolgreiche Kopplung voraus
        (self.cfg["ultimaker_auth_id"]/["ultimaker_auth_key"], siehe
        start_pairing()/check_pairing()) - die Zugangsdaten werden nur
        dann tatsaechlich mitgesendet, wenn der Drucker ueberhaupt
        Digest-Auth verlangt. on_progress(sent, total) wird nur einmal
        am Ende aufgerufen (kein granulares Fortschritts-Feedback
        waehrend des Uploads - die Ultimaker-API bietet dafuer keinen
        Hook, und gcode-Dateien sind i. d. R. deutlich kleiner als
        Bambu-3mf-Pakete, sodass der Upload meist ohnehin schnell
        abgeschlossen ist)."""
        auth_id = self.cfg.get("ultimaker_auth_id")
        auth_key = self.cfg.get("ultimaker_auth_key")
        if not auth_id or not auth_key:
            raise RuntimeError(
                "Dieser Ultimaker ist noch nicht mit dem Dashboard gekoppelt - "
                "bitte zuerst ueber den Button \"Jetzt koppeln\" koppeln und "
                "die Anfrage am Drucker-Display bestaetigen."
            )

        total_size = os.path.getsize(local_path)
        challenge = self._digest_challenge_or_none()
        uri = "/api/v1/print_job"

        boundary = uuid.uuid4().hex
        with open(local_path, "rb") as f:
            file_bytes = f.read()
        body = _build_multipart_body(
            boundary,
            fields=[("jobname", job_name)],
            files=[("file", os.path.basename(local_path), file_bytes)],
        )

        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        }
        if challenge is not None:
            headers["Authorization"] = _build_digest_authorization(challenge, auth_id, auth_key, "POST", uri)

        req = urllib.request.Request(
            self._base_url() + uri, data=body, method="POST", headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            if e.code == 401:
                raise RuntimeError(
                    "Der Drucker hat die gespeicherten Zugangsdaten abgelehnt "
                    "(HTTP 401) - die Kopplung wurde vermutlich am Drucker "
                    "zurueckgesetzt. Bitte erneut koppeln."
                ) from e
            raise RuntimeError(
                f"Drucker lehnte den Druckauftrag ab (HTTP {e.code})"
                f"{': ' + detail if detail else ''}."
            ) from e

        if on_progress:
            on_progress(total_size, total_size)

    # v2.9.0: laufenden Druck abbrechen - PUT /api/v1/print_job/state mit
    # {"target": "abort"}, offiziell dokumentierter Endpunkt laut
    # Ultimaker-Swagger-Doku (siehe Klassendoku oben, /docs/api/ direkt
    # am Drucker). Verlangt dieselbe Digest-Authentifizierung wie
    # send_print() - die Challenge wird bewusst ueber die bereits
    # bestehende Probe gegen /api/v1/print_job geholt (_digest_challenge_
    # or_none()) statt eine zweite, identische Probe gegen /print_job/
    # state zu bauen: laut RFC 2617 gilt eine Digest-Challenge fuer den
    # gesamten "Protection Space" (hier: alle schreibenden Endpunkte
    # desselben Druckers), nicht nur fuer den einen Pfad, ueber den sie
    # angefragt wurde.
    def abort_print(self):
        auth_id = self.cfg.get("ultimaker_auth_id")
        auth_key = self.cfg.get("ultimaker_auth_key")
        if not auth_id or not auth_key:
            raise RuntimeError(
                "Dieser Ultimaker ist noch nicht mit dem Dashboard gekoppelt - "
                "Abbrechen ueber das Dashboard ist daher nicht moeglich."
            )
        uri = "/api/v1/print_job/state"
        challenge = self._digest_challenge_or_none()
        body = json.dumps({"target": "abort"}).encode()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if challenge is not None:
            headers["Authorization"] = _build_digest_authorization(challenge, auth_id, auth_key, "PUT", uri)
        req = urllib.request.Request(self._base_url() + uri, data=body, method="PUT", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            if e.code == 401:
                raise RuntimeError(
                    "Der Drucker hat die gespeicherten Zugangsdaten abgelehnt "
                    "(HTTP 401) - die Kopplung wurde vermutlich am Drucker "
                    "zurueckgesetzt. Bitte erneut koppeln."
                ) from e
            raise RuntimeError(
                f"Drucker lehnte den Abbruch-Befehl ab (HTTP {e.code})"
                f"{': ' + detail if detail else ''}."
            ) from e


# ----------------------------------------------------------------------
# Zweiter, unabhaengiger MQTT-Broker fuer frei definierbare Sensoren
# und Schaltflaechen, die einer Drucker-Karte angehaengt werden
# ----------------------------------------------------------------------
class ExtrasMqttManager:
    """Verbindet sich (falls in config.json unter "extras_mqtt" aktiviert)
    zu einem ZWEITEN, von den Druckern unabhaengigen MQTT-Broker (z. B.
    einem Heimautomatisierungs-Broker wie Mosquitto/Home Assistant) und
    haelt die zuletzt empfangenen Werte aller relevanten Topics vor.

    Sensoren: ein an einem Drucker hinterlegter "extras"-Eintrag mit
    kind="sensor" abonniert "topic" und zeigt den zuletzt empfangenen
    Rohwert (als Text) auf der Drucker-Karte an.

    Schalter: ein Eintrag mit kind="switch" zeigt zwei Buttons ("Ein"/
    "Aus") auf der Karte. Ein Klick veroeffentlicht den konfigurierten
    payload_on/payload_off auf "command_topic" - es wird kein Zustand
    vom Broker zurueckgelesen (einfache "Fire-and-forget"-Schaltflaeche,
    wie angefragt).
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg.get("extras_mqtt") or {}
        self.values = {}
        self._client = None
        self._stop = False

    def start(self):
        if not self.cfg.get("enabled") or not self.cfg.get("host"):
            return
        self._stop = False
        threading.Thread(target=self._connect_loop, daemon=True).start()

    def stop(self):
        self._stop = True
        try:
            if self._client:
                self._client.disconnect()
        except Exception:
            pass

    def _connect_loop(self):
        client_id = f"dashboard-extras-{uuid.uuid4().hex[:6]}"
        self._client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
        if self.cfg.get("username"):
            self._client.username_pw_set(self.cfg.get("username"), self.cfg.get("password", ""))
        if self.cfg.get("tls"):
            self._client.tls_set_context(ssl._create_unverified_context())
            self._client.tls_insecure_set(True)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=15)

        while not self._stop:
            try:
                self._client.connect(self.cfg["host"], int(self.cfg.get("port", 1883)), keepalive=30)
                self._client.loop_forever(retry_first_connection=True)
            except Exception:
                time.sleep(5)
            if self._stop:
                break
            time.sleep(3)

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            client.subscribe("#")

    def _on_message(self, client, userdata, msg):
        try:
            self.values[msg.topic] = msg.payload.decode("utf-8", errors="ignore")
        except Exception:
            pass

    def get_value(self, topic):
        if not topic:
            return None
        return self.values.get(topic)

    def list_topics(self, limit=300):
        """v2.2.15: liefert die zuletzt empfangenen Topic/Wert-Paare (durch
        das breite "#"-Abo in _on_connect() bereits ALLE Topics dieses
        Brokers, nicht nur konfigurierte Sensoren) - dient dem
        "MQTT-Sensoren"-Dialog im Frontend als Hilfe beim Einrichten: der
        Nutzer sieht die tatsaechlich ankommenden Topics/Werte, statt das
        Topic blind abtippen zu muessen (haeufigste Fehlerquelle bei der
        bisherigen reinen config.json-Konfiguration, siehe UEBERGABE.md).
        Alphabetisch sortiert, auf `limit` Eintraege begrenzt (rein zum
        Schutz vor einer sehr "geschwaetzigen" Broker-Installation mit
        tausenden Topics - eine Momentaufnahme, kein Anspruch auf
        Vollstaendigkeit)."""
        items = sorted(self.values.items())[:limit]
        return [{"topic": t, "value": v} for t, v in items]

    def publish(self, topic, payload):
        if not self._client:
            return False
        try:
            self._client.publish(topic, payload)
            return True
        except Exception:
            return False


# ----------------------------------------------------------------------
# Zentrale Verwaltung aller Drucker-Verbindungen
# ----------------------------------------------------------------------
class DashboardApp:
    PRINT_JOB_MAX_AGE_SEC = 20 * 60  # Aufraeumen liegen gebliebener Temp-Dateien

    def __init__(self):
        self.cfg = load_config()
        self.connections = {}
        # v2.2.21: Limit aus config.json ("history_max_jobs") statt der
        # bisher fest codierten Konstante - siehe _resolve_history_max_jobs().
        self.history = PrintHistoryStore(_resolve_history_max_jobs(self.cfg.get("history_max_jobs")))
        self.queue = PrintQueueStore()  # MK6 v1.2.0: siehe PrintQueueStore-Kommentar
        self.extras = ExtrasMqttManager(self.cfg)
        self.extras.start()
        for p in self.cfg["printers"]:
            self._start_printer(p)
        self._print_jobs = {}          # job_id -> {local_path, remote_name, printer_id, created,
                                        #            history_ref, queue_ref} (letzte zwei: MK6 v1.2.0)
        self._print_jobs_lock = threading.Lock()
        self._print_progress = {}      # job_id -> {phase, sent, total, percent, error, ams}
        self._print_progress_lock = threading.Lock()
        # printer_id -> (auth_id, auth_key, gestartet_um) - siehe
        # start_ultimaker_pairing()/check_ultimaker_pairing(). Nur
        # WAEHREND einer laufenden Kopplung befuellt, danach entfernt
        # (erfolgreich: id/key wandern dauerhaft in config.json).
        self._ultimaker_pending_auth = {}
        # ------------------------------------------------------------------
        # v2.6.0: FarmBot - siehe Klassenkommentar beim Abschnitt "FarmBot"
        # weiter unten (nahe pick_farmbot_job()) fuer die vollstaendige
        # Beschreibung. Eigene PrintQueueStore-Instanz (siehe dortiger
        # Kommentar: gleiche Ablage-/Dauer-Schaetzungs-Logik, eigener
        # Ordner "farmbot_queue/<farmbot_id>/", damit FarmBot-Warteschlangen
        # niemals mit den Warteschlangen einzelner Drucker (self.queue)
        # verwechselt/vermischt werden koennen - siehe UEBERGABE.md v2.6.0,
        # Abschnitt "Unabhaengigkeit von der druckereigenen Warteschlange").
        self.farmbot_queue = PrintQueueStore(root="farmbot_queue")
        for fb in self.cfg.get("farmbots", []):
            self.farmbot_queue.ensure_dir(fb["id"])
        # printer_id -> bool: letzter bekannter Beschaeftigt-Zustand, siehe
        # _update_bed_confirm_flags().
        self._printer_was_busy = {}
        # printer_id -> True, solange FarmBot vor dem naechsten Druck auf
        # DIESEM Drucker eine Bestaetigung "Druckraum frei" braucht (siehe
        # _update_bed_confirm_flags()/pick_farmbot_job()/assign_farmbot_job()).
        self._farmbot_bed_confirm_pending = {}
        # printer_id -> Anzahl bisher ueber FarmBot auf diesem Drucker
        # gestarteter Druckauftraege - rein in-memory (setzt sich nach
        # einem Neustart des Dashboards zurueck), nur fuer die
        # Lastverteilung zwischen mehreren Druckern derselben Familie
        # gedacht, siehe pick_farmbot_job().
        self._farmbot_print_counts = {}

    def _start_printer(self, printer_cfg: dict):
        # MK6: Verlaufsordner fuer JEDEN Drucker anlegen, unabhaengig vom
        # Typ und noch bevor je ein Druckauftrag gesendet wurde (siehe
        # PrintHistoryStore-Kommentar) - deckt sowohl beim Programmstart
        # aus config.json geladene als auch ueber add_printer() neu
        # angelegte Drucker ab, da beide Wege ueber diese Methode laufen.
        self.history.ensure_dir(printer_cfg["id"])
        self.queue.ensure_dir(printer_cfg["id"])  # MK6 v1.2.0: siehe PrintQueueStore-Kommentar
        ptype = printer_cfg.get("type", "bambu")
        if ptype in FORMLABS_TYPES:
            conn = FormlabsLocalApiConnection(printer_cfg, self.cfg.get("preform_server"))
        elif ptype == "octoprint":
            conn = OctoPrintConnection(printer_cfg)
        elif ptype in CREALITY_TYPES:
            conn = CrealityConnection(printer_cfg)
        elif ptype == "ultimaker":
            conn = UltimakerConnection(printer_cfg)
        else:
            conn = PrinterConnection(printer_cfg)
        self.connections[printer_cfg["id"]] = conn
        conn.start()

    def add_printer(self, name, ip, ptype="bambu", access_code=None, serial=None,
                     camera_port=6000, mqtt_port=8883,
                     api_key=None, port=None, https=False, webcam_url=None,
                     bambu_family="x1"):
        new_printer = {
            "id": uuid.uuid4().hex[:10],
            "name": name,
            "type": ptype,
            "ip": ip,
            "extras": [],
            # v2.3.0: neue Drucker gehoeren zunaechst keinem Raum an und
            # werden ans Ende der Anzeigereihenfolge gehaengt (siehe
            # reorder_printers()/all_status() fuer die Verwendung).
            "group_id": None,
            "order": len(self.cfg["printers"]),
        }
        if ptype in FORMLABS_TYPES:
            pass
        elif ptype == "octoprint":
            new_printer.update({
                "api_key": api_key or "",
                "port": port or 80,
                "https": https,
                "webcam_url": webcam_url or ""
            })
        elif ptype in CREALITY_TYPES:
            new_printer.update({
                "api_key": api_key or "",
                "port": port or 7125,     # Moonraker-Standardport
                "webcam_url": webcam_url or ""
            })
        elif ptype == "ultimaker":
            new_printer.update({
                "port": port or 80,
                "webcam_url": webcam_url or ""
            })
        else:
            new_printer.update({
                "access_code": access_code,
                "serial": serial,
                "mqtt_port": mqtt_port,
                "camera_port": camera_port,
                # "x1" (X1C/X1E), "a1" (A1/A1 Mini), "h2" (H2S/H2D/H2D
                # Pro/H2C), "p1" (P1P/P1S), "p2" (P2S) oder "x2" (X2D) -
                # steuert, welches FTPS-Verbindungsprofil beim ersten
                # Upload-Versuch genutzt wird (siehe FTPS_PROFILES/
                # BAMBU_FAMILY_TO_FTPS_PROFILE/_ftps_upload()).
                "bambu_family": bambu_family if bambu_family in BAMBU_FAMILY_TO_FTPS_PROFILE else "x1",
            })

        self.cfg["printers"].append(new_printer)
        save_config(self.cfg)
        self._start_printer(new_printer)
        return new_printer

    def remove_printer(self, printer_id):
        self.cfg["printers"] = [p for p in self.cfg["printers"] if p["id"] != printer_id]
        save_config(self.cfg)
        conn = self.connections.pop(printer_id, None)
        if conn:
            conn.stop()

    def get_printer_cfg(self, printer_id):
        for p in self.cfg["printers"]:
            if p["id"] == printer_id:
                return p
        return None

    # ------------------------------------------------------------------
    # v2.3.0: Raeume/Gruppen - rein organisatorisch (Anzeige gruppiert
    # nach Raum im Bedien-Modus), ohne jede technische Wirkung auf die
    # Drucker-Verbindungen selbst. Die Zuordnung eines Druckers zu einer
    # Gruppe steht beim Drucker ("group_id", siehe assign_printer_group()),
    # das Loeschen einer Gruppe setzt diese Zuordnung defensiv auf None
    # zurueck statt die betroffenen Drucker versehentlich mitzuloeschen.
    # ------------------------------------------------------------------
    def get_groups(self):
        return sorted(self.cfg.get("groups", []), key=lambda g: g.get("order", 0))

    def add_group(self, name):
        new_group = {
            "id": uuid.uuid4().hex[:10],
            "name": name,
            "order": len(self.cfg.get("groups", [])),
        }
        self.cfg.setdefault("groups", []).append(new_group)
        save_config(self.cfg)
        return new_group

    def rename_group(self, group_id, name):
        for g in self.cfg.get("groups", []):
            if g["id"] == group_id:
                g["name"] = name
                save_config(self.cfg)
                return True
        return False

    def remove_group(self, group_id):
        groups = self.cfg.get("groups", [])
        if not any(g["id"] == group_id for g in groups):
            return False
        self.cfg["groups"] = [g for g in groups if g["id"] != group_id]
        # Drucker UND externe Kameras (seit v2.4.0 ebenfalls raum-
        # zuweisbar) dieser Gruppe werden NICHT geloescht, nur die
        # Zuordnung entfernt (erscheinen danach im Bedien-Modus unter
        # "Ohne Raum").
        for p in self.cfg["printers"]:
            if p.get("group_id") == group_id:
                p["group_id"] = None
        for c in self.cfg.get("rtsp_cameras", []):
            if c.get("group_id") == group_id:
                c["group_id"] = None
        # v2.5.0: eigenstaendige (nicht an einen Drucker gebundene) MQTT-
        # Sensoren/Schalter sind seitdem ebenfalls raum-zuweisbar (siehe
        # add_standalone_extra()) - analog zu Druckern/Kameras oben wird
        # beim Loeschen der Gruppe nur die Zuordnung entfernt.
        for e in self.cfg.get("standalone_extras", []):
            if e.get("group_id") == group_id:
                e["group_id"] = None
        save_config(self.cfg)
        return True

    def reorder_groups(self, ordered_ids):
        groups = self.cfg.get("groups", [])
        if sorted(ordered_ids) != sorted(g["id"] for g in groups):
            return False
        order_map = {gid: idx for idx, gid in enumerate(ordered_ids)}
        for g in groups:
            g["order"] = order_map[g["id"]]
        save_config(self.cfg)
        return True

    def assign_printer_group(self, printer_id, group_id):
        p = self.get_printer_cfg(printer_id)
        if not p:
            return False
        if group_id is not None and not any(g["id"] == group_id for g in self.cfg.get("groups", [])):
            return False
        p["group_id"] = group_id
        save_config(self.cfg)
        return True

    def reorder_printers(self, ordered_ids):
        printers = self.cfg["printers"]
        if sorted(ordered_ids) != sorted(p["id"] for p in printers):
            return False
        order_map = {pid: idx for idx, pid in enumerate(ordered_ids)}
        for p in printers:
            p["order"] = order_map[p["id"]]
        save_config(self.cfg)
        return True

    # ------------------------------------------------------------------
    # v2.3.0: frei konfigurierbare, vom Drucker unabhaengige RTSP(S)-
    # Kameras (z. B. eine Raumuebersichtskamera) - Streaming laeuft ueber
    # denselben FFmpeg-basierten Mechanismus wie die RTSPS-Kamera der
    # X1/P1/P2/H2/X2-Serie (siehe generic_rtsp_mjpeg_generator()), hier
    # nur die Verwaltung der Eintraege in config.json.
    # ------------------------------------------------------------------
    def get_rtsp_cameras(self):
        return sorted(self.cfg.get("rtsp_cameras", []), key=lambda c: c.get("order", 0))

    def get_rtsp_camera(self, camera_id):
        for c in self.cfg.get("rtsp_cameras", []):
            if c["id"] == camera_id:
                return c
        return None

    def add_rtsp_camera(self, name, url, username="", password="", group_id=None):
        new_cam = {
            "id": uuid.uuid4().hex[:10],
            "name": name,
            "url": url,
            # v2.4.0: Anmeldedaten bewusst GETRENNT von der URL gespeichert
            # (nicht vom Nutzer selbst als "user:pass@" in die URL
            # eingebaut) - siehe build_rtsp_url_with_auth() fuer den Grund
            # (Sonderzeichen in Passwoertern wuerden eine manuell
            # eingebaute URL sonst unbrauchbar machen) sowie group_id fuer
            # die Raum-Zuordnung, analog zu Druckern.
            "username": username or "",
            "password": password or "",
            "group_id": group_id,
            "order": len(self.cfg.get("rtsp_cameras", [])),
        }
        self.cfg.setdefault("rtsp_cameras", []).append(new_cam)
        save_config(self.cfg)
        return new_cam

    def update_rtsp_camera(self, camera_id, name, url, username="", password=""):
        cam = self.get_rtsp_camera(camera_id)
        if not cam:
            return False
        cam["name"] = name
        cam["url"] = url
        cam["username"] = username or ""
        cam["password"] = password or ""
        save_config(self.cfg)
        return True

    def remove_rtsp_camera(self, camera_id):
        cams = self.cfg.get("rtsp_cameras", [])
        if not any(c["id"] == camera_id for c in cams):
            return False
        self.cfg["rtsp_cameras"] = [c for c in cams if c["id"] != camera_id]
        save_config(self.cfg)
        return True

    def assign_rtsp_camera_group(self, camera_id, group_id):
        cam = self.get_rtsp_camera(camera_id)
        if not cam:
            return False
        if group_id is not None and not any(g["id"] == group_id for g in self.cfg.get("groups", [])):
            return False
        cam["group_id"] = group_id
        save_config(self.cfg)
        return True

    # ------------------------------------------------------------------
    # v2.3.0: Einstellungen-Modus - bislang nur per Hand in config.json
    # aenderbarer "history_max_jobs" (siehe _resolve_history_max_jobs())
    # jetzt zusaetzlich ueber die Web-Oberflaeche aenderbar. Analog zu
    # update_extras_mqtt_settings() wird der Effekt (Limit des bereits
    # laufenden PrintHistoryStore) SOFORT uebernommen, kein Neustart noetig.
    # ------------------------------------------------------------------
    def get_settings(self):
        return {
            "history_max_jobs": self.cfg.get("history_max_jobs"),
            # v2.8.0: siehe SUPPORTED_LANGUAGES/CONFIG_WAS_FRESH/update_language().
            "language": self.cfg.get("language", "de"),
            "first_run": CONFIG_WAS_FRESH,
        }

    def update_history_max_jobs(self, raw_value):
        self.cfg["history_max_jobs"] = raw_value
        save_config(self.cfg)
        self.history.max_jobs_per_printer = _resolve_history_max_jobs(raw_value)
        return True

    def update_language(self, lang):
        """v2.8.0: auf ausdruecklichen Nutzerwunsch - Oberflaechensprache,
        umschaltbar im Einstellungen-Modus UND (beim allerersten Start
        ohne vorhandene config.json) ueber den Sprachauswahl-Dialog, der
        dann als Erstes beim Oeffnen der Seite erscheint (siehe
        CONFIG_WAS_FRESH/get_settings()). Setzt CONFIG_WAS_FRESH IMMER mit
        zurueck, auch wenn der Nutzer zufaellig die bereits aktive Sprache
        erneut waehlt - der Dialog darf in diesem Prozess danach in jedem
        Fall nicht mehr erscheinen."""
        global CONFIG_WAS_FRESH
        if lang not in SUPPORTED_LANGUAGES:
            return False, "Unbekannter Sprachcode."
        self.cfg["language"] = lang
        save_config(self.cfg)
        CONFIG_WAS_FRESH = False
        return True, None

    def _resolve_extras(self, printer_cfg):
        out = []
        for ex in printer_cfg.get("extras", []):
            item = dict(ex)
            if ex.get("kind") == "sensor":
                item["value"] = self.extras.get_value(ex.get("topic"))
            out.append(item)
        return out

    # ------------------------------------------------------------------
    # v2.2.15: Verwaltung des zweiten MQTT-Brokers ("extras_mqtt") und der
    # daran haengenden Sensoren/Schalter je Drucker ueber die Web-
    # Oberflaeche - vorher nur per manueller config.json-Bearbeitung
    # moeglich (siehe README Abschnitt 2 vor v2.2.15). Ergaenzt bewusst
    # nur die Verwaltung, das Laufzeitverhalten von ExtrasMqttManager
    # (Sensor-Anzeige, Schalter-Befehle) bleibt unveraendert.
    # ------------------------------------------------------------------
    def get_extras_mqtt_settings(self):
        return dict(self.cfg.get("extras_mqtt") or {})

    def update_extras_mqtt_settings(self, data):
        """Speichert die Broker-Einstellungen und baut die Verbindung
        SOFORT mit den neuen Werten neu auf (alte ExtrasMqttManager-
        Instanz wird gestoppt, eine neue erstellt/gestartet) - vorher war
        dafuer ein kompletter Neustart des Dashboards/der exe noetig, was
        vermutlich mit ein Grund war, warum eine Aenderung an config.json
        von Hand "nicht funktioniert hat" (siehe Chat-Verlauf): ohne
        Neustart blieben alte, ggf. falsche Einstellungen bis zum
        naechsten Programmstart aktiv."""
        enabled = bool(data.get("enabled"))
        host = (data.get("host") or "").strip()
        try:
            port = int(data.get("port") or 1883)
        except (TypeError, ValueError):
            return False, "Ungueltiger Port.", None
        if enabled and not host:
            return False, "Broker-Adresse ist bei aktiviertem Broker ein Pflichtfeld.", None
        username = (data.get("username") or "").strip()
        # Passwort bleibt unveraendert, wenn das Feld im Formular leer
        # gelassen wurde (z. B. weil der Nutzer nur den Host aendern
        # wollte) - ein "password": "" im Request loescht es dagegen
        # bewusst (leerer String ist ein gueltiger, expliziter Wert).
        if "password" in data and data.get("password") is not None:
            password = data.get("password")
        else:
            password = (self.cfg.get("extras_mqtt") or {}).get("password", "")
        tls = bool(data.get("tls"))

        self.cfg["extras_mqtt"] = {
            "enabled": enabled, "host": host, "port": port,
            "username": username, "password": password, "tls": tls,
        }
        save_config(self.cfg)

        old_extras = self.extras
        self.extras = ExtrasMqttManager(self.cfg)
        self.extras.start()
        try:
            old_extras.stop()
        except Exception:
            pass
        return True, None, self.get_extras_mqtt_settings()

    def get_discovered_mqtt_topics(self):
        return self.extras.list_topics()

    def _get_extras_list(self, printer_id):
        """Liefert (printer_cfg, extras_liste) oder (None, None), wenn der
        Drucker nicht existiert. Die Liste ist eine Referenz auf
        printer_cfg["extras"] - Aenderungen daran wirken sich direkt auf
        self.cfg aus, muessen aber trotzdem explizit mit save_config()
        persistiert werden (wie ueberall sonst in dieser Klasse)."""
        p = self.get_printer_cfg(printer_id)
        if not p:
            return None, None
        return p, p.setdefault("extras", [])

    @staticmethod
    def _validate_extra_fields(data, existing_kind=None):
        """Prueft/normalisiert die Felder eines Sensor-/Schalter-Eintrags.
        `existing_kind` wird beim Bearbeiten uebergeben - die Art
        (Sensor/Schalter) laesst sich nachtraeglich bewusst NICHT mehr
        aendern (ein Schalter hat strukturell andere Pflichtfelder als
        ein Sensor), nur ihre Werte. Gibt (None, error) oder
        (entry_dict_ohne_id, None) zurueck."""
        kind = existing_kind or (data.get("kind") or "").strip().lower()
        if kind not in ("sensor", "switch"):
            return None, "'kind' muss 'sensor' oder 'switch' sein."
        label = (data.get("label") or "").strip()
        if not label:
            return None, "Bezeichnung ist ein Pflichtfeld."
        entry = {"label": label, "kind": kind}
        if kind == "sensor":
            topic = (data.get("topic") or "").strip()
            if not topic:
                return None, "MQTT-Topic ist bei einem Sensor ein Pflichtfeld."
            entry["topic"] = topic
            unit = (data.get("unit") or "").strip()
            if unit:
                entry["unit"] = unit
            # v2.2.16: legt fest, WO der Sensor auf der Drucker-Karte
            # erscheint - "generic" (Standard) im bisherigen "Sensoren &
            # Schalter"-Bereich unten, "temperature"/"humidity" dagegen
            # direkt in der Temperaturen-Zeile, GENAUSO wie die vom
            # Drucker selbst gelieferten Werte (Duese/Bett/Kammer bzw.
            # AMS-Feuchte) - inklusive derselben Sparkline-Infrastruktur
            # (siehe extraChip() im Frontend). Ein unbekannter/leerer Wert
            # faellt defensiv auf "generic" zurueck statt einen Fehler zu
            # werfen - so bleiben auch vor v2.2.16 angelegte Eintraege
            # (ohne dieses Feld) unveraendert im gewohnten Bereich.
            display = (data.get("display") or "generic").strip().lower()
            if display not in ("generic", "temperature", "humidity"):
                display = "generic"
            entry["display"] = display
        else:
            command_topic = (data.get("command_topic") or "").strip()
            payload_on = data.get("payload_on")
            payload_off = data.get("payload_off")
            if not command_topic:
                return None, "Befehls-Topic ist bei einem Schalter ein Pflichtfeld."
            if payload_on is None or payload_on == "" or payload_off is None or payload_off == "":
                return None, "Payload fuer 'Ein' und 'Aus' sind bei einem Schalter Pflichtfelder."
            entry["command_topic"] = command_topic
            entry["payload_on"] = payload_on
            entry["payload_off"] = payload_off
        return entry, None

    def add_extra(self, printer_id, data):
        p, extras = self._get_extras_list(printer_id)
        if p is None:
            return False, "Drucker nicht gefunden.", None
        entry, err = self._validate_extra_fields(data)
        if err:
            return False, err, None
        entry["id"] = uuid.uuid4().hex[:10]
        extras.append(entry)
        save_config(self.cfg)
        return True, None, entry

    def update_extra(self, printer_id, extra_id, data):
        p, extras = self._get_extras_list(printer_id)
        if p is None:
            return False, "Drucker nicht gefunden.", None
        existing = next((e for e in extras if e.get("id") == extra_id), None)
        if not existing:
            return False, "Eintrag nicht gefunden.", None
        entry, err = self._validate_extra_fields(data, existing_kind=existing.get("kind"))
        if err:
            return False, err, None
        entry["id"] = extra_id
        extras[extras.index(existing)] = entry
        save_config(self.cfg)
        return True, None, entry

    def delete_extra(self, printer_id, extra_id):
        p, extras = self._get_extras_list(printer_id)
        if p is None:
            return False
        before = len(extras)
        p["extras"] = [e for e in extras if e.get("id") != extra_id]
        save_config(self.cfg)
        return len(p["extras"]) != before

    # ------------------------------------------------------------------
    # v2.5.0: eigenstaendige (vom Drucker UNABHAENGIGE) MQTT-Sensoren und
    # -Schalter - z. B. ein Raumthermometer, das an keinem bestimmten
    # Drucker haengt. Vorher musste JEDER Sensor/Schalter zwingend einem
    # bestehenden Drucker zugeordnet werden (siehe _get_extras_list()
    # oben), wodurch sich ohne mindestens einen angelegten Drucker gar
    # keine Sensoren/Schalter anlegen liessen - das Hinzufuegen-Formular
    # im Frontend brach in diesem Fall wortlos ab (siehe submitMqttExtra()
    # im <script>-Block). Diese Liste ist bewusst parallel zu, NICHT
    # innerhalb von, "extras" je Drucker aufgebaut, um die bestehende
    # Druckerzuordnung unveraendert zu lassen (additiv). Validierung
    # (Pflichtfelder je nach "kind") nutzt dieselbe _validate_extra_fields()
    # wie die druckergebundenen Extras. Analog zu Druckern/Kameras seit
    # v2.3.0/v2.4.0 koennen auch eigenstaendige Sensoren/Schalter einem
    # Raum zugewiesen werden (siehe assign_standalone_extra_group()),
    # damit sie sich im Bedien-Modus sinnvoll einsortieren lassen.
    # ------------------------------------------------------------------
    def get_standalone_extras(self):
        out = []
        for ex in sorted(self.cfg.get("standalone_extras", []), key=lambda e: e.get("order", 0)):
            item = dict(ex)
            if ex.get("kind") == "sensor":
                item["value"] = self.extras.get_value(ex.get("topic"))
            out.append(item)
        return out

    def add_standalone_extra(self, data):
        entry, err = self._validate_extra_fields(data)
        if err:
            return False, err, None
        entry["id"] = uuid.uuid4().hex[:10]
        entry["group_id"] = None
        entry["order"] = len(self.cfg.get("standalone_extras", []))
        self.cfg.setdefault("standalone_extras", []).append(entry)
        save_config(self.cfg)
        return True, None, entry

    def update_standalone_extra(self, extra_id, data):
        extras = self.cfg.get("standalone_extras", [])
        existing = next((e for e in extras if e.get("id") == extra_id), None)
        if not existing:
            return False, "Eintrag nicht gefunden.", None
        entry, err = self._validate_extra_fields(data, existing_kind=existing.get("kind"))
        if err:
            return False, err, None
        entry["id"] = extra_id
        entry["group_id"] = existing.get("group_id")
        entry["order"] = existing.get("order", 0)
        extras[extras.index(existing)] = entry
        save_config(self.cfg)
        return True, None, entry

    def delete_standalone_extra(self, extra_id):
        extras = self.cfg.get("standalone_extras", [])
        before = len(extras)
        self.cfg["standalone_extras"] = [e for e in extras if e.get("id") != extra_id]
        save_config(self.cfg)
        return len(self.cfg["standalone_extras"]) != before

    def assign_standalone_extra_group(self, extra_id, group_id):
        extra = next((e for e in self.cfg.get("standalone_extras", []) if e.get("id") == extra_id), None)
        if not extra:
            return False
        if group_id is not None and not any(g["id"] == group_id for g in self.cfg.get("groups", [])):
            return False
        extra["group_id"] = group_id
        save_config(self.cfg)
        return True

    def send_standalone_extra_command(self, extra_id, action):
        extra = next((e for e in self.cfg.get("standalone_extras", []) if e.get("id") == extra_id), None)
        if not extra or extra.get("kind") != "switch":
            return False, "Schalter nicht gefunden."
        topic = extra.get("command_topic")
        payload = extra.get("payload_on") if action == "on" else extra.get("payload_off")
        if not topic or payload is None:
            return False, "Schalter ist in config.json nicht vollstaendig konfiguriert."
        ok = self.extras.publish(topic, payload)
        return ok, (None if ok else "MQTT-Verbindung fuer Sensoren/Schalter nicht verfuegbar.")

    # ------------------------------------------------------------------
    # v2.6.0: FarmBot - eigenstaendige, vom Drucker UNABHAENGIGE Warte-
    # schlange je FarmBot-Instanz, die automatisch einem freien Drucker
    # einer gewaehlten Hersteller-/Familien-Kombination zugewiesen wird.
    # Auf ausdruecklichen Nutzerwunsch, siehe UEBERGABE.md v2.6.0 fuer die
    # vollstaendige Beschreibung (Entstehung, Entscheidungen, bewusste
    # Vereinfachungen). Kurzueberblick:
    #   - Mehrere unabhaengige FarmBot-Instanzen moeglich (eigener Name-
    #     Zusatz, eigene Warteschlange, eigene Einstellungen) - siehe
    #     add_farmbot()/update_farmbot()/delete_farmbot().
    #   - Dateien werden per Drag&Drop in die FarmBot-eigene Warteschlange
    #     gelegt (self.farmbot_queue, siehe add_farmbot_job()); die
    #     Reihenfolge wird danach IMMER automatisch neu berechnet, siehe
    #     _reorder_farmbot_queue().
    #   - "Naechsten Druck starten" laeuft zweistufig: pick_farmbot_job()
    #     ermittelt (OHNE Seiteneffekt) den naechsten Auftrag + einen
    #     freien Zieldrucker (inkl. Lastverteilung) und meldet, ob eine
    #     Kamera-Bestaetigung ("Druckraum frei"/"anderer Drucker") noetig
    #     ist; erst assign_farmbot_job() verschiebt die Datei tatsaechlich
    #     und startet den Druck (AMS-Dialog bei Bambu, sofortiger Start
    #     bei Ultimaker - identischer Ablauf wie ein manueller Drag&Drop-
    #     Upload auf die Drucker-Kachel selbst).
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_farmbot_work_window(work_start: str, work_end: str):
        try:
            sh, sm = map(int, work_start.split(":"))
            eh, em = map(int, work_end.split(":"))
            if not (0 <= sh <= 23 and 0 <= sm <= 59 and 0 <= eh <= 23 and 0 <= em <= 59):
                raise ValueError
        except Exception:
            return False, "Arbeitstag-Fenster muss im Format HH:MM angegeben werden."
        if (eh, em) <= (sh, sm):
            return False, ("Arbeitstag-Ende muss nach dem Arbeitstag-Beginn liegen (ueber Mitternacht "
                            "hinausgehende Arbeitstage werden aktuell nicht unterstuetzt).")
        return True, None

    def get_farmbots(self):
        return sorted(self.cfg.get("farmbots", []), key=lambda f: f.get("order", 0))

    def get_farmbot_cfg(self, farmbot_id):
        return next((f for f in self.cfg.get("farmbots", []) if f.get("id") == farmbot_id), None)

    def _apply_farmbot_fields(self, entry: dict, data: dict):
        """Gemeinsame Validierung/Uebernahme fuer add_farmbot()/
        update_farmbot() - mutiert `entry` nur, wenn ALLE Felder gueltig
        sind, und gibt sonst (False, Fehlermeldung) zurueck, OHNE `entry`
        schon teilweise zu veraendern."""
        manufacturer = (data.get("manufacturer") or "bambu").strip().lower()
        if manufacturer not in FARMBOT_MANUFACTURERS:
            return False, "Hersteller muss 'Bambu Lab' oder 'Ultimaker' sein."
        work_start = (data.get("work_start") or "08:00").strip()
        work_end = (data.get("work_end") or "18:00").strip()
        ok, err = self._validate_farmbot_work_window(work_start, work_end)
        if not ok:
            return False, err
        try:
            max_days = int(data.get("max_queue_days", 3))
            if max_days < 1:
                raise ValueError
        except Exception:
            return False, "Maximale Wartezeit in der Warteschlange muss eine positive ganze Zahl (Tage) sein."
        bambu_family = None
        if manufacturer == "bambu":
            bambu_family = (data.get("bambu_family") or "x1").strip().lower()
            if bambu_family not in BAMBU_FAMILY_TO_FTPS_PROFILE:
                bambu_family = "x1"

        entry["name_suffix"] = (data.get("name_suffix") or "").strip()
        entry["enabled"] = bool(data.get("enabled", True))
        entry["manufacturer"] = manufacturer
        entry["work_start"] = work_start
        entry["work_end"] = work_end
        entry["max_queue_days"] = max_days
        if manufacturer == "bambu":
            entry["bambu_family"] = bambu_family
        else:
            entry.pop("bambu_family", None)
        return True, None

    def add_farmbot(self, data: dict):
        entry = {"id": uuid.uuid4().hex[:10], "order": len(self.cfg.get("farmbots", []))}
        ok, err = self._apply_farmbot_fields(entry, data)
        if not ok:
            return False, err, None
        self.cfg.setdefault("farmbots", []).append(entry)
        save_config(self.cfg)
        self.farmbot_queue.ensure_dir(entry["id"])
        return True, None, entry

    def update_farmbot(self, farmbot_id, data: dict):
        entry = self.get_farmbot_cfg(farmbot_id)
        if not entry:
            return False, "FarmBot nicht gefunden.", None
        candidate = dict(entry)
        ok, err = self._apply_farmbot_fields(candidate, data)
        if not ok:
            return False, err, None
        entry.clear()
        entry.update(candidate)
        save_config(self.cfg)
        return True, None, entry

    def delete_farmbot(self, farmbot_id):
        before = len(self.cfg.get("farmbots", []))
        self.cfg["farmbots"] = [f for f in self.cfg.get("farmbots", []) if f.get("id") != farmbot_id]
        changed = len(self.cfg["farmbots"]) != before
        if changed:
            save_config(self.cfg)
            # Warteschlangen-Dateien dieses FarmBot bewusst NICHT geloescht
            # (analog zu Druckern: auch deren print_queue/print_history-
            # Ordner bleiben beim Entfernen unangetastet) - vermeidet
            # versehentlichen Datenverlust bei einem Tippfehler/Testlauf.
            self._farmbot_bed_confirm_pending = {
                pid: v for pid, v in self._farmbot_bed_confirm_pending.items()
            }
        return changed

    @staticmethod
    def _farmbot_display_name(fb: dict) -> str:
        suffix = (fb.get("name_suffix") or "").strip()
        return f"FarmBot {suffix}" if suffix else "FarmBot"

    def _work_window_budget_minutes(self, fb: dict) -> int:
        """Minuten bis zum Ende des Arbeitstag-Fensters - AUSSERHALB des
        Fensters (vor Beginn oder nach Ende) wird vereinfachend die volle
        Fensterlaenge angenommen (siehe UEBERGABE.md v2.6.0: kein echter
        Mehrtage-Terminplaner, nur eine Orientierungsgroesse fuer die
        Anzeige "passt heute noch X mal" und fuer die Sortierung - die
        Sortierung selbst (kuerzeste Druckzeit zuerst) ist unabhaengig
        von der konkreten Budget-Zahl immer optimal fuer "moeglichst viele
        Auftraege heute noch STARTEN", siehe _reorder_farmbot_queue()/
        _farmbot_status_extra() - v2.6.1: der Arbeitstag begrenzt nur das
        Starten neuer Auftraege, nicht deren Fertigstellung; ein bereits
        gestarteter Druck darf unbeaufsichtigt ueber das Fensterende hinaus
        weiterlaufen)."""
        try:
            sh, sm = map(int, fb["work_start"].split(":"))
            eh, em = map(int, fb["work_end"].split(":"))
        except Exception:
            return 0
        now = datetime.now()
        start_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
        end_dt = now.replace(hour=eh, minute=em, second=0, microsecond=0)
        if end_dt <= start_dt:
            return 0
        if start_dt <= now <= end_dt:
            return max(0, int((end_dt - now).total_seconds() // 60))
        return int((end_dt - start_dt).total_seconds() // 60)

    def _farmbot_status_extra(self, fb: dict) -> dict:
        """v2.6.1 - BUGFIX/Klarstellung auf ausdruecklichen Nutzerwunsch:
        "Der Arbeitstag soll auch nur für den Start des letzten Druckes
        relevant sein, da der Drucker auch außerhalb des Arbeitstages ohne
        menschlichen Bediener weiterarbeiten kann aber halt keine neuen
        Drucke starten kann." Der Arbeitstag begrenzt also NUR, wie viele
        Auftraege heute noch GESTARTET werden koennen - nicht, wie viele
        davon noch VOR Feierabend FERTIG werden. Ein Auftrag zaehlt daher
        schon als "passt noch rein", wenn vor seinem Start noch Restzeit
        im Fenster uebrig ist (`remaining > 0`); seine eigene Druckdauer
        darf diese Restzeit ueberschreiten (der Drucker laeuft dann
        unbeaufsichtigt ueber Feierabend hinaus weiter) - danach ist die
        Restzeit fuer den naechsten Auftrag dann aber verbraucht, da der
        Drucker erst nach Feierabend wieder frei wird. Vorherige Version
        brach bereits ab, wenn die Druckdauer DIESES Auftrags allein schon
        die Restzeit ueberschritt - das zaehlte faelschlich auch den
        letzten, gerade noch rechtzeitig gestarteten Auftrag nicht mit."""
        entries = self.farmbot_queue.list_entries(fb["id"])
        remaining = self._work_window_budget_minutes(fb) * 60
        fits = 0
        for e in entries:
            if remaining <= 0:
                break
            dur = e.get("duration_sec")
            if dur is None:
                break  # ab hier unbekannte Dauer - Abschaetzung endet hier bewusst (siehe Kommentar unten)
            fits += 1
            remaining -= dur
        return {
            "display_name": self._farmbot_display_name(fb),
            "queue_count": len(entries),
            "fits_in_workday": fits,
        }

    def get_farmbots_status(self):
        return [dict(fb, **self._farmbot_status_extra(fb)) for fb in self.get_farmbots()]

    def get_farmbot_jobs(self, farmbot_id):
        return self.farmbot_queue.list_entries(farmbot_id)

    def get_farmbot_job_thumbnail_path(self, farmbot_id, job_id):
        return self.farmbot_queue.get_thumbnail_path(farmbot_id, job_id)

    def _reorder_farmbot_queue(self, farmbot_id):
        """Wird nach JEDEM Hinzufuegen eines neuen Auftrags automatisch
        aufgerufen (siehe add_farmbot_job(), auf ausdruecklichen
        Nutzerwunsch). Zwei Kriterien, in dieser Prioritaet:
          1. Auftraege, die die eingestellte maximale Wartezeit
             ("max_queue_days") bereits erreicht/ueberschritten haben,
             werden ganz nach vorne gestellt (laengste Wartezeit zuerst) -
             sie muessen unabhaengig von ihrer Druckdauer vorrangig
             abgearbeitet werden.
          2. Alle uebrigen Auftraege: aufsteigend nach geschaetzter
             Druckdauer ("duration_sec") sortiert - das ist die klassische
             "Shortest Job First"-Heuristik, die (unabhaengig vom exakten
             Restzeit-Budget) nachweislich die ANZAHL der innerhalb eines
             Zeitbudgets noch STARTBAREN Auftraege maximiert (v2.6.1: der
             Arbeitstag begrenzt nur das Starten, nicht die Fertigstellung
             - ein gestarteter Druck darf unbeaufsichtigt ueber Feierabend
             hinaus weiterlaufen, siehe _farmbot_status_extra()).
             Auftraege OHNE bekannte Dauer (Datei ohne auslesbare
             Zeitschaetzung, siehe _extract_print_duration_seconds())
             werden bewusst ans Ende gestellt, statt eine Dauer zu raten -
             auf ausdruecklichen Nutzerwunsch ("nur automatisch, kein
             Eingriff")."""
        fb = self.get_farmbot_cfg(farmbot_id)
        if not fb:
            return
        entries = self.farmbot_queue.list_entries(farmbot_id)
        if len(entries) < 2:
            return
        max_days = fb.get("max_queue_days") or 3
        now = datetime.now()

        def age_days(e):
            try:
                added = datetime.strptime(e["added_at"], "%Y-%m-%d %H:%M:%S")
            except Exception:
                return 0.0
            return (now - added).total_seconds() / 86400.0

        urgent = sorted((e for e in entries if age_days(e) >= max_days), key=age_days, reverse=True)
        rest = sorted((e for e in entries if age_days(e) < max_days),
                       key=lambda e: (e.get("duration_sec") is None, e.get("duration_sec") or 0))
        self.farmbot_queue.reorder(farmbot_id, [e["job_id"] for e in urgent + rest])

    def add_farmbot_job(self, farmbot_id, local_path, filename):
        fb = self.get_farmbot_cfg(farmbot_id)
        if not fb:
            return False, "FarmBot nicht gefunden.", None
        entry = self.farmbot_queue.add_entry(farmbot_id, local_path, filename)
        self._cleanup_job_file({"local_path": local_path})
        if not entry:
            return False, "Datei konnte nicht zur Warteschlange hinzugefuegt werden.", None
        self._reorder_farmbot_queue(farmbot_id)
        return True, None, entry

    def delete_farmbot_job(self, farmbot_id, job_id):
        return self.farmbot_queue.delete_entry(farmbot_id, job_id)

    def reorder_farmbot_queue(self, farmbot_id, ordered_job_ids):
        """v2.7.0 - auf ausdruecklichen Nutzerwunsch: die automatisch
        berechnete Reihenfolge (siehe _reorder_farmbot_queue()) soll sich
        haendisch uebersteuern lassen, genau wie bei der Warteschlange
        eines einzelnen Druckers (siehe reorder_print_queue()). Diese
        manuelle Reihenfolge bleibt bestehen, bis der naechste Auftrag
        hinzugefuegt wird - add_farmbot_job() ruft danach weiterhin
        IMMER automatisch _reorder_farmbot_queue() auf, das uebersteuert
        eine manuelle Umsortierung also bewusst wieder (identisches
        Verhalten zu vorher, nur dass es jetzt explizit eine manuelle
        Zwischenstufe gibt)."""
        return self.farmbot_queue.reorder(farmbot_id, ordered_job_ids)

    def _update_bed_confirm_flags(self):
        """Erkennt je Drucker den Uebergang "beschaeftigt" -> "nicht mehr
        beschaeftigt" (unabhaengig vom genauen Status-Wert, siehe
        PRINTER_BUSY_STATES - funktioniert damit druckertyp-uebergreifend
        fuer Bambu UND Ultimaker, ohne druckerspezifische Status-Werte zu
        erraten) und merkt sich das als "Druckraum vermutlich noch belegt
        von einem vorherigen Druck", bis entweder FarmBot per Kamera-
        Bestaetigung ("Druckraum frei") fortfaehrt oder irgendein neuer
        Druck auf diesem Drucker erfolgreich gestartet wurde (dann ist die
        Frage ohnehin hinfaellig). Guenstig genug, um bei jedem
        /api/status-Abruf mitzulaufen - kein eigener Hintergrund-Thread
        noetig, siehe all_status()."""
        for pid, conn in self.connections.items():
            state = str(conn.status.get("gcode_state") or "").upper()
            busy = state in PRINTER_BUSY_STATES
            was_busy = self._printer_was_busy.get(pid, False)
            if was_busy and not busy:
                self._farmbot_bed_confirm_pending[pid] = True
            self._printer_was_busy[pid] = busy

    def _farmbot_matching_printers(self, fb: dict):
        """Alle Drucker im Dashboard, die zur Hersteller-/Familienauswahl
        dieses FarmBot passen UND fuer einen automatisierten Druckstart
        grundsaetzlich nutzbar sind (bei Ultimaker: bereits gekoppelt,
        siehe start_ultimaker_pairing())."""
        out = []
        for p in self.cfg.get("printers", []):
            if p.get("type", "bambu") != fb["manufacturer"]:
                continue
            if fb["manufacturer"] == "bambu" and p.get("bambu_family", "x1") != fb.get("bambu_family", "x1"):
                continue
            if fb["manufacturer"] == "ultimaker" and not (p.get("ultimaker_auth_id") and p.get("ultimaker_auth_key")):
                continue
            out.append(p)
        return out

    def pick_farmbot_job(self, farmbot_id, exclude_printer_ids=None):
        """Ermittelt OHNE Seiteneffekt (keine Datei wird verschoben, kein
        Druck gestartet) den naechsten Auftrag dieses FarmBot sowie einen
        passenden, gerade freien Zieldrucker - fuer den "Naechsten Druck
        starten"-Knopf, VOR der eigentlichen Kamera-Bestaetigung/Zuweisung
        (siehe assign_farmbot_job()). `exclude_printer_ids` wird genutzt,
        wenn der Nutzer im Kamera-Dialog "anderer Drucker" waehlt - dann
        wird derselbe Auftrag erneut, aber ohne die bereits abgelehnten
        Drucker, zugeordnet.

        Lastverteilung: unter den aktuell freien, passenden Druckern wird
        der mit den WENIGSTEN bisher ueber FarmBot gestarteten Auftraegen
        gewaehlt (self._farmbot_print_counts, rein in-memory seit dem
        letzten Programmstart) - bei Gleichstand entscheidet die Anzeige-
        Reihenfolge/ID (deterministisch, kein Zufall)."""
        fb = self.get_farmbot_cfg(farmbot_id)
        if not fb:
            return False, "FarmBot nicht gefunden.", None
        if not fb.get("enabled", True):
            return False, "Dieser FarmBot ist deaktiviert.", None
        entries = self.farmbot_queue.list_entries(farmbot_id)
        if not entries:
            return False, "Die Warteschlange ist leer.", None
        next_job = entries[0]

        exclude = set(exclude_printer_ids or [])
        candidates = [p for p in self._farmbot_matching_printers(fb)
                      if p["id"] not in exclude and self.is_ready_for_next_print(p["id"])]
        if not candidates:
            return False, ("Kein freier Drucker der gewaehlten Hersteller-/Familienauswahl "
                            "verfuegbar."), None
        candidates.sort(key=lambda p: (self._farmbot_print_counts.get(p["id"], 0), p.get("order", 0), p["id"]))
        target = candidates[0]
        needs_confirm = bool(self._farmbot_bed_confirm_pending.get(target["id"], False))
        return True, None, {
            "job_id": next_job["job_id"],
            "filename": next_job["filename"],
            "printer_id": target["id"],
            "printer_name": target["name"],
            "needs_bed_confirm": needs_confirm,
        }

    def assign_farmbot_job(self, farmbot_id, job_id, printer_id):
        """Fuehrt das Ergebnis von pick_farmbot_job() tatsaechlich aus -
        erst HIER wird die Datei in einen temporaeren Job-Ordner kopiert
        und der eigentliche Druckvorgang angestossen (fruehestens, nachdem
        der Nutzer eine ggf. noetige Kamera-Bestaetigung gegeben hat,
        siehe pick_farmbot_job()).

        WICHTIG (Unabhaengigkeit von der druckereigenen Warteschlange,
        auf ausdruecklichen Nutzerwunsch): dies laeuft NICHT ueber
        enqueue_upload()/self.queue/start_next_queued_print() (das koennte
        mit dort bereits manuell liegenden Auftraegen desselben Druckers
        kollidieren bzw. deren Reihenfolge durcheinanderbringen), sondern
        direkt wie ein frischer manueller Drag&Drop-Upload auf die
        Drucker-Kachel selbst, ueber dieselben Basisfunktionen
        (prepare_print_job() fuer Bambu, send_ultimaker_print_now() fuer
        Ultimaker) - der Drucker merkt also keinen Unterschied, ob der
        Auftrag manuell oder ueber FarmBot kam, und eine bereits laufende
        eigene Warteschlange dieses Druckers bleibt unberuehrt.

        Bei Bambu ist dies bewusst NUR der erste (Vorschau-)Schritt, genau
        wie bei einem manuellen Upload: der Rueckgabewert enthaelt die
        AMS-Zuordnungsvorschau; das Frontend oeffnet darauf denselben
        bestehenden AMS-Dialog und bestaetigt ueber den bestehenden
        Endpunkt /api/printers/<id>/print/confirm (start_confirm_print_job())
        - dort erfolgt dann auch die vom Nutzer gewuenschte AMS-Zuordnung
        "direkt beim Start, nach Auswahl des Druckers und Bestaetigung der
        Verfuegbarkeit". Sowohl der Bambu- als auch der Ultimaker-Pfad
        laufen anschliessend asynchron in einem Hintergrund-Thread (Upload
        kann dauern) - der eigentliche Erfolg (und damit das Entfernen aus
        der FarmBot-Warteschlange, die Lastverteilungs-Zaehlung und das
        Zuruecksetzen des "Druckraum frei"-Flags) wird deshalb NICHT hier,
        sondern zentral in _record_history_after_send() behandelt, siehe
        dort ("farmbot_ref") - identisch zum bestehenden Muster fuer
        history_ref/queue_ref."""
        fb = self.get_farmbot_cfg(farmbot_id)
        if not fb:
            return False, "FarmBot nicht gefunden.", None
        target_cfg = self.get_printer_cfg(printer_id)
        if not target_cfg:
            return False, "Ziel-Drucker nicht gefunden.", None
        if target_cfg.get("type", "bambu") != fb["manufacturer"] or (
            fb["manufacturer"] == "bambu"
            and target_cfg.get("bambu_family", "x1") != fb.get("bambu_family", "x1")
        ):
            return False, "Ziel-Drucker passt nicht zur Hersteller-/Familienauswahl dieses FarmBot.", None
        if not self.is_ready_for_next_print(printer_id):
            return False, "Ziel-Drucker ist inzwischen nicht mehr frei - bitte erneut versuchen.", None

        stored_path, filename = self.farmbot_queue.get_job_file_path(farmbot_id, job_id)
        if not stored_path:
            return False, "Dieser Auftrag ist nicht mehr vorhanden.", None
        try:
            tmp_path = self._copy_to_temp_job_dir(stored_path, filename)
        except Exception as e:
            return False, f"Datei konnte nicht kopiert werden: {e}", None

        farmbot_ref = {"farmbot_id": farmbot_id, "job_id": job_id}
        if target_cfg.get("type") == "ultimaker":
            ok, err, new_job_id = self.send_ultimaker_print_now(printer_id, tmp_path, filename, farmbot_ref=farmbot_ref)
            if not ok:
                self._cleanup_job_file({"local_path": tmp_path})
                return False, err, None
            result = {"mode": "ultimaker", "job_id": new_job_id}
        else:
            ok, err, new_job_id, preview = self.prepare_print_job(printer_id, tmp_path, filename, farmbot_ref=farmbot_ref)
            if not ok:
                self._cleanup_job_file({"local_path": tmp_path})
                return False, err, None
            result = {
                "mode": "bambu",
                "job_id": new_job_id,
                "filename": filename,
                "filaments": preview["filaments"],
                "ams_trays": preview["ams_trays"],
                "total_filaments": preview.get("total_filaments", len(preview["filaments"])),
            }

        return True, None, result

    def all_status(self):
        # v2.6.0: bei jedem Status-Abruf mitlaufen lassen (siehe
        # _update_bed_confirm_flags()) - guenstig genug, kein eigener
        # Hintergrund-Thread noetig, und so garantiert immer aktuell, wenn
        # das FarmBot-Feld im Dashboard als naechstes "Druckraum frei?"
        # abfragen muesste.
        self._update_bed_confirm_flags()
        out = []
        for p in self.cfg["printers"]:
            conn = self.connections.get(p["id"])
            item = {
                "id": p["id"],
                "name": p["name"],
                "ip": p["ip"],
                "type": p.get("type", "bambu"),
                # v2.3.0: Raum-Zuordnung und Anzeige-Reihenfolge - siehe
                # assign_printer_group()/reorder_printers() sowie die
                # gruppierte Darstellung in refresh() im <script>-Block.
                "group_id": p.get("group_id"),
                "order": p.get("order", 0),
            }
            item.update(conn.status if conn else {})
            item["extras"] = self._resolve_extras(p)
            if p.get("type") == "ultimaker":
                item["ultimaker_paired"] = bool(p.get("ultimaker_auth_id") and p.get("ultimaker_auth_key"))
            # MK6 v2.1.0: Druckerfamilie (x1/a1/h2/...) fuer Bambu-Lab-Drucker
            # mitliefern, damit das Frontend beim Zuweisen (openAssignModal)
            # nur Drucker derselben Familie als Ziel anbietet.
            if p.get("type", "bambu") == "bambu":
                item["bambu_family"] = p.get("bambu_family", "x1")
            # MK6 v1.2.0: Anzahl wartender Auftraege, fuer das Badge am
            # Warteschlangen-Symbol der Kachel - wird ueber denselben
            # 2,5-Sekunden-Status-Poll mitgeliefert, kein eigener Endpunkt
            # noetig. Guenstig genug (kleine JSON-Datei einlesen), um bei
            # jedem Status-Abruf frisch berechnet zu werden.
            item["queue_count"] = len(self.queue.list_entries(p["id"]))
            # MK6 v2.2.0: Vorschaubild des aktuellen/zuletzt gestarteten
            # Druckauftrags fuer die Anzeige neben dem Fortschrittsbalken.
            # Quelle: der NEUESTE Verlaufseintrag dieses Druckers (Verlauf
            # wird bereits bei jedem erfolgreich ueber das Dashboard
            # gesendeten Auftrag befuellt, siehe PrintHistoryStore/
            # _record_history_after_send() - kein neuer Speicherort noetig,
            # kein zusaetzlicher Aufruf an den Drucker selbst). Ist bewusst
            # NICHT auf "druckt gerade" beschraenkt - bei OctoPrint/
            # Creality/Formlabs (kein Versand ueber das Dashboard moeglich)
            # bleibt der Verlauf ohnehin leer, das Bild erscheint dort also
            # gar nicht erst.
            latest_history = self.history.list_entries(p["id"])
            if latest_history:
                item["current_thumb_job_id"] = latest_history[0]["job_id"]
                item["current_thumb_has_image"] = bool(latest_history[0].get("has_image"))
            else:
                item["current_thumb_job_id"] = None
                item["current_thumb_has_image"] = False
            out.append(item)
        return out

    def send_extra_command(self, printer_id, extra_id, action):
        p = self.get_printer_cfg(printer_id)
        if not p:
            return False, "Drucker nicht gefunden."
        extra = next((e for e in p.get("extras", []) if e.get("id") == extra_id), None)
        if not extra or extra.get("kind") != "switch":
            return False, "Schalter nicht gefunden."
        topic = extra.get("command_topic")
        payload = extra.get("payload_on") if action == "on" else extra.get("payload_off")
        if not topic or payload is None:
            return False, "Schalter ist in config.json nicht vollstaendig konfiguriert."
        ok = self.extras.publish(topic, payload)
        return ok, (None if ok else "MQTT-Verbindung fuer Sensoren/Schalter nicht verfuegbar.")

    def send_print_job(self, printer_id, local_path, remote_name):
        p = self.get_printer_cfg(printer_id)
        if not p:
            return False, "Drucker nicht gefunden.", None
        if p.get("type", "bambu") != "bambu":
            return False, "Druckauftrag per Drag & Drop wird aktuell nur fuer Bambu Lab Drucker unterstuetzt.", None
        conn = self.connections.get(printer_id)
        if not conn:
            return False, "Keine Verbindung zu diesem Drucker.", None
        try:
            ams_summary = conn.send_print(local_path, remote_name, None)
            return True, None, ams_summary
        except Exception as e:
            return False, str(e), None

    # ------------------------------------------------------------------
    # Zweistufiger Ablauf fuer die AMS-Zuordnungspruefung im Browser
    # (wie in Bambu Studio): erst "prepare" (Datei parsen, Vorschlag
    # anzeigen), dann "confirm" (mit ggf. vom Nutzer korrigierter
    # Zuordnung tatsaechlich hochladen + drucken), oder "cancel".
    # ------------------------------------------------------------------
    def _purge_stale_print_jobs(self):
        cutoff = time.time() - self.PRINT_JOB_MAX_AGE_SEC
        stale = [jid for jid, j in self._print_jobs.items() if j["created"] < cutoff]
        for jid in stale:
            job = self._print_jobs.pop(jid, None)
            if job:
                self._cleanup_job_file(job)
            with self._print_progress_lock:
                self._print_progress.pop(jid, None)

    def prepare_print_job(self, printer_id, local_path, remote_name, history_ref=None, queue_ref=None, farmbot_ref=None):
        p = self.get_printer_cfg(printer_id)
        if not p:
            return False, "Drucker nicht gefunden.", None, None
        if p.get("type", "bambu") != "bambu":
            return False, "Druckauftrag per Drag & Drop wird aktuell nur fuer Bambu Lab Drucker unterstuetzt.", None, None
        conn = self.connections.get(printer_id)
        if not conn:
            return False, "Keine Verbindung zu diesem Drucker.", None, None

        preview = conn.preview_print(local_path)

        with self._print_jobs_lock:
            self._purge_stale_print_jobs()
            job_id = uuid.uuid4().hex
            self._print_jobs[job_id] = {
                "local_path": local_path,
                "remote_name": remote_name,
                "printer_id": printer_id,
                "created": time.time(),
                # MK6 v1.2.0: siehe _record_history_after_send() - history_ref
                # verhindert einen doppelten Verlaufseintrag bei Reprint/
                # Warteschlange, queue_ref entfernt den urspruenglichen
                # Warteschlangen-Eintrag erst NACH bestaetigtem Erfolg.
                "history_ref": history_ref,
                "queue_ref": queue_ref,
                # v2.6.0: siehe _record_history_after_send() - raeumt den
                # FarmBot-Warteschlangen-Eintrag ebenfalls erst NACH
                # bestaetigtem Erfolg auf (AMS-Zuordnung erfolgt bei Bambu
                # erst NACH diesem Aufruf, ueber den normalen Bestaetigungs-
                # Dialog/-Endpunkt - siehe assign_farmbot_job()).
                "farmbot_ref": farmbot_ref,
            }
        return True, None, job_id, preview

    def _set_progress(self, job_id, **kwargs):
        with self._print_progress_lock:
            p = self._print_progress.setdefault(job_id, {
                "phase": "idle", "sent": 0, "total": 0, "percent": 0,
                "error": None, "ams": None,
            })
            p.update(kwargs)

    def get_print_progress(self, job_id):
        with self._print_progress_lock:
            p = self._print_progress.get(job_id)
            return dict(p) if p else None

    def start_confirm_print_job(self, job_id, mapping):
        """Startet FTPS-Upload + Druckstart in einem Hintergrund-Thread
        und kehrt SOFORT zurueck - der Fortschritt wird ueber
        get_print_progress(job_id) abgefragt (Polling vom Browser).
        Bei einem Fehler bleiben Job und Temp-Datei bewusst erhalten
        (kein Cleanup), damit der Nutzer erneut "Drucken starten"
        klicken kann, ohne die Datei nochmal hochladen und die
        AMS-Zuordnung neu waehlen zu muessen. Nur bei Erfolg oder durch
        cancel_print_job()/die 20-Minuten-Aufraeumroutine wird die
        Temp-Datei geloescht."""
        with self._print_jobs_lock:
            job = self._print_jobs.get(job_id)
        if not job:
            return False, "Druckauftrag nicht gefunden oder abgelaufen - bitte Datei erneut hochladen."
        conn = self.connections.get(job["printer_id"])
        if not conn:
            return False, "Keine Verbindung mehr zu diesem Drucker."

        try:
            total_size = os.path.getsize(job["local_path"])
        except OSError:
            with self._print_jobs_lock:
                self._print_jobs.pop(job_id, None)
            return False, "Zwischengespeicherte Datei nicht mehr vorhanden - bitte erneut hochladen."

        self._set_progress(job_id, phase="uploading", sent=0, total=total_size, percent=0, error=None, ams=None)

        def worker():
            def on_progress(sent, total):
                percent = int(sent * 100 / total) if total else 0
                self._set_progress(job_id, phase="uploading", sent=sent, total=total, percent=percent)
            try:
                ams_summary = conn.send_print(job["local_path"], job["remote_name"], mapping, on_progress=on_progress)
                self._set_progress(job_id, phase="done", sent=total_size, total=total_size, percent=100, ams=ams_summary)
                # MK6: erfolgreich gesendeten Auftrag in den Verlauf des
                # Druckers uebernehmen (bzw. bei Reprint/Warteschlange nur
                # den bestehenden Eintrag aktualisieren - siehe
                # _record_history_after_send()), BEVOR die temporaere Datei
                # unten per _cleanup_job_file() geloescht wird.
                self._record_history_after_send(job)
                with self._print_jobs_lock:
                    self._print_jobs.pop(job_id, None)
                self._cleanup_job_file(job)
            except Exception as e:
                self._set_progress(job_id, phase="error", error=str(e))

        threading.Thread(target=worker, daemon=True).start()
        return True, None

    def cancel_print_job(self, job_id):
        with self._print_jobs_lock:
            job = self._print_jobs.pop(job_id, None)
        if job:
            self._cleanup_job_file(job)
        with self._print_progress_lock:
            self._print_progress.pop(job_id, None)
        return True

    @staticmethod
    def _cleanup_job_file(job):
        try:
            os.remove(job["local_path"])
            os.rmdir(os.path.dirname(job["local_path"]))
        except Exception:
            pass

    def _record_history_after_send(self, job):
        """MK6 v1.2.0: gemeinsame Verlaufs-/Warteschlangen-Buchfuehrung
        NACH erfolgreichem Senden, verwendet von start_confirm_print_job()
        (Bambu) und send_ultimaker_print_now() (Ultimaker).

        - Traegt den Auftrag normalerweise als NEUEN Eintrag in den
          Verlauf des Zieldruckers ein (history.add_entry()).
        - AUSSER `job["history_ref"]` verweist auf einen Verlaufseintrag
          DESSELBEN Druckers (job["history_ref"]["printer_id"] ==
          job["printer_id"]) - dann wird stattdessen NUR dieser bestehende
          Eintrag aktualisiert (history.touch_entry()), damit ein erneut
          gedruckter Verlaufseintrag nicht ein zweites Mal in der Liste
          auftaucht. Wurde der Auftrag hingegen einem ANDEREN Drucker
          zugewiesen, ist ein neuer Eintrag in DESSEN Verlauf korrekt (er
          wurde dort schliesslich tatsaechlich gedruckt).
        - War der Auftrag Teil einer Warteschlange (`job["queue_ref"]`
          gesetzt), wird der Warteschlangen-Eintrag jetzt entfernt - ERST
          NACH bestaetigtem Erfolg, damit ein fehlgeschlagener/
          abgebrochener Versuch ihn nicht verliert (siehe start_
          next_queued_print()-Kommentar: "Druckraum leer" kann dann
          einfach erneut geklickt werden)."""
        printer_id = job["printer_id"]
        history_ref = job.get("history_ref")
        if history_ref and history_ref.get("printer_id") == printer_id:
            self.history.touch_entry(history_ref["printer_id"], history_ref["job_id"])
        else:
            self.history.add_entry(printer_id, job["local_path"], job["remote_name"])
        queue_ref = job.get("queue_ref")
        if queue_ref:
            self.queue.delete_entry(queue_ref["printer_id"], queue_ref["job_id"])
        # v2.6.0: analoges Aufraeumen fuer einen FarmBot-Auftrag - siehe
        # assign_farmbot_job()/prepare_print_job()/send_ultimaker_print_now().
        # Erst HIER (nach bestaetigtem Senden) wird der Warteschlangen-
        # Eintrag entfernt und die Lastverteilungs-Zaehlung sowie ein noch
        # offenes "Druckraum frei"-Flag fuer den Zieldrucker aktualisiert -
        # ein fehlgeschlagener Versuch darf den Auftrag nicht aus der
        # FarmBot-Warteschlange verlieren.
        farmbot_ref = job.get("farmbot_ref")
        if farmbot_ref:
            self.farmbot_queue.delete_entry(farmbot_ref["farmbot_id"], farmbot_ref["job_id"])
            self._farmbot_print_counts[printer_id] = self._farmbot_print_counts.get(printer_id, 0) + 1
            self._farmbot_bed_confirm_pending.pop(printer_id, None)

    def is_printer_busy(self, printer_id) -> bool:
        """MK6 v1.2.0: True, wenn der Druckraum dieses Druckers gerade
        belegt ist (siehe PRINTER_BUSY_STATES) - entscheidet, ob ein neu
        hochgeladener/erneut gestarteter Druckauftrag sofort gesendet
        oder stattdessen in die Warteschlange gelegt wird. Unbekannte/
        nicht verbundene Drucker gelten bewusst als NICHT beschaeftigt
        (liefert sonst widerspruechlich immer "beschaeftigt", solange der
        Status noch nicht einmal einmal empfangen wurde) - ein
        tatsaechliches Verbindungsproblem wird ohnehin an anderer Stelle
        (send_print()) gemeldet."""
        conn = self.connections.get(printer_id)
        if not conn:
            return False
        state = str(conn.status.get("gcode_state") or "").upper()
        return state in PRINTER_BUSY_STATES

    def is_ready_for_next_print(self, printer_id) -> bool:
        """v2.0.1: Gibt an, ob die Warteschlange dieses Druckers jetzt
        fortgesetzt werden darf ("Druckraum leer"-Knopf). Bei Bambu Lab
        strenger als is_printer_busy(): reicht "nicht beschaeftigt" allein
        NICHT - verlangt EXPLIZIT einen der BAMBU_READY_FOR_NEXT_STATES
        ("FINISH", "IDLE" oder seit v2.1.1 auch "FAILED"), siehe Kommentar
        dort. Uebergangszustaende wie "PREPARE"/"SLICING" gelten damit
        bewusst NICHT als bereit, obwohl sie nicht in PRINTER_BUSY_STATES
        stehen. Fuer alle anderen
        Druckertypen (aktuell nur Ultimaker relevant, da nur diese Typen
        eine Warteschlange haben) bleibt es bei der bisherigen, einfachen
        Regel "nicht beschaeftigt" - dafuer wurde keine Verschaerfung
        angefragt."""
        p = self.get_printer_cfg(printer_id)
        ptype = p.get("type", "bambu") if p else "bambu"
        if ptype == "bambu":
            conn = self.connections.get(printer_id)
            if not conn:
                return False
            state = str(conn.status.get("gcode_state") or "").upper()
            return state in BAMBU_READY_FOR_NEXT_STATES
        return not self.is_printer_busy(printer_id)

    # v2.9.0: laufenden Druck abbrechen - auf ausdruecklichen Nutzerwunsch
    # ("Passe das Dashboard so an das ein laufender Druck abgebrochen
    # werden kann"). Reiner Dispatch nach Druckertyp auf die jeweils neu
    # ergaenzte Abbrechen-Methode der Connection-Klasse (siehe
    # PrinterConnection.request_stop_print()/OctoPrintConnection.
    # cancel_print()/CrealityConnection.cancel_print()/
    # UltimakerConnection.abort_print()) - jede davon nutzt ausschliesslich
    # offiziell dokumentierte Endpunkte/Befehle (siehe jeweilige
    # Methodendoku), keine geratenen Protokolldetails.
    #
    # Formlabs (Drucker/Wash/Cure) bleibt bewusst aussen vor: Druckauftraege
    # werden bei diesem Typ nicht ueber das Dashboard gestartet (siehe
    # README-Tabelle, Spalte "Druck per Drag & Drop" - "-"), sondern lokal
    # per PreForm - es gibt dafuer keinen vom Formlabs Local API offiziell
    # dokumentierten Fernabbruch-Endpunkt, ein geratener Endpunkt waere ein
    # Verstoss gegen die Projekt-Konvention "keine undokumentierten
    # Protokolldetails erfinden".
    def abort_print(self, printer_id):
        p = self.get_printer_cfg(printer_id)
        if not p:
            return False, "Unbekannter Drucker."
        ptype = p.get("type", "bambu")
        conn = self.connections.get(printer_id)
        if not conn:
            return False, "Keine aktive Verbindung zu diesem Drucker."
        try:
            if ptype == "bambu":
                conn.request_stop_print()
            elif ptype == "octoprint":
                conn.cancel_print()
            elif ptype in CREALITY_TYPES:
                conn.cancel_print()
            elif ptype == "ultimaker":
                conn.abort_print()
            else:
                return False, (
                    "Fuer diesen Druckertyp ist das Abbrechen eines laufenden "
                    "Drucks ueber das Dashboard nicht unterstuetzt."
                )
        except Exception as e:
            return False, str(e)
        return True, None

    @staticmethod
    def _copy_to_temp_job_dir(stored_path, filename):
        """Kopiert eine dauerhaft gespeicherte Datei (Verlauf oder
        Warteschlange) in einen frischen temporaeren Job-Ordner, wie ihn
        prepare_print_job()/send_ultimaker_print_now() fuer jeden Upload
        erwarten. Wirft bei einem Fehler weiter (Aufrufer entscheidet
        ueber die Fehlermeldung) - raeumt den halb angelegten Ordner dabei
        aber auf."""
        tmp_dir = tempfile.mkdtemp(prefix="dashboard-print-")
        tmp_path = os.path.join(tmp_dir, filename)
        try:
            shutil.copyfile(stored_path, tmp_path)
        except Exception:
            try:
                os.rmdir(tmp_dir)
            except Exception:
                pass
            raise
        return tmp_path

    # ------------------------------------------------------------------
    # Ultimaker: Kopplung ("Pairing") und Druckauftrag per Drag & Drop
    # (seit v1.6.3) - siehe UltimakerConnection.start_pairing()/
    # check_pairing()/send_print() fuer den technischen Hintergrund.
    # ------------------------------------------------------------------
    def start_ultimaker_pairing(self, printer_id):
        p = self.get_printer_cfg(printer_id)
        if not p or p.get("type") != "ultimaker":
            return False, "Kein Ultimaker-Drucker mit dieser ID gefunden."
        conn = self.connections.get(printer_id)
        if not conn:
            return False, "Keine Verbindung zu diesem Drucker."
        try:
            auth_id, auth_key = conn.start_pairing()
        except Exception as e:
            return False, f"Kopplungsanfrage fehlgeschlagen: {e}"
        self._ultimaker_pending_auth[printer_id] = (auth_id, auth_key, time.time())
        return True, None

    def check_ultimaker_pairing(self, printer_id):
        """Wird vom Frontend wiederholt abgefragt (Polling), waehrend
        auf die Bestaetigung am Drucker-Display gewartet wird. Liefert
        "pending" (weiter warten), "authorized" (Kopplung erfolgreich -
        id/key wurden bereits dauerhaft in config.json gespeichert) oder
        "unauthorized" (am Display abgelehnt)."""
        pending = self._ultimaker_pending_auth.get(printer_id)
        if not pending:
            return False, "Keine laufende Kopplungsanfrage fuer diesen Drucker.", None
        auth_id, auth_key, started_at = pending
        if time.time() - started_at > 120:
            self._ultimaker_pending_auth.pop(printer_id, None)
            return False, ("Kopplungsanfrage abgelaufen (keine Bestaetigung am Display "
                            "innerhalb von 2 Minuten) - bitte erneut versuchen."), None
        conn = self.connections.get(printer_id)
        if not conn:
            self._ultimaker_pending_auth.pop(printer_id, None)
            return False, "Keine Verbindung mehr zu diesem Drucker.", None
        try:
            status = conn.check_pairing(auth_id)
        except Exception as e:
            return False, f"Fehler beim Pruefen der Kopplung: {e}", None

        if status == "authorized":
            self._ultimaker_pending_auth.pop(printer_id, None)
            p = self.get_printer_cfg(printer_id)
            if p is not None:
                p["ultimaker_auth_id"] = auth_id
                p["ultimaker_auth_key"] = auth_key
                save_config(self.cfg)
            return True, None, "authorized"
        if status == "unauthorized":
            self._ultimaker_pending_auth.pop(printer_id, None)
            return True, None, "unauthorized"
        return True, None, "pending"

    def send_ultimaker_print_now(self, printer_id, local_path, filename, history_ref=None, queue_ref=None, farmbot_ref=None):
        """Anders als bei Bambu (siehe prepare_print_job()/
        start_confirm_print_job()) gibt es bei Ultimaker keine AMS-
        Zuordnung zu bestaetigen - der Druck wird deshalb SOFORT nach
        dem Hochladen der Datei ins Dashboard gestartet, ohne
        Zwischenschritt. Nutzt dieselben _print_jobs/_print_progress-
        Strukturen wie Bambu weiter, damit das Frontend denselben
        generischen Polling-Endpunkt (/print/progress/<job_id>)
        verwenden kann."""
        p = self.get_printer_cfg(printer_id)
        if not p:
            return False, "Drucker nicht gefunden.", None
        if p.get("type") != "ultimaker":
            return False, "Diese Funktion ist nur fuer Ultimaker-Drucker verfuegbar.", None
        if not (p.get("ultimaker_auth_id") and p.get("ultimaker_auth_key")):
            return False, ("Dieser Ultimaker ist noch nicht mit dem Dashboard gekoppelt - "
                            "bitte zuerst koppeln."), None
        conn = self.connections.get(printer_id)
        if not conn:
            return False, "Keine Verbindung zu diesem Drucker.", None

        try:
            total_size = os.path.getsize(local_path)
        except OSError:
            return False, "Hochgeladene Datei nicht gefunden.", None

        with self._print_jobs_lock:
            self._purge_stale_print_jobs()
            job_id = uuid.uuid4().hex
            self._print_jobs[job_id] = {
                "local_path": local_path,
                "remote_name": filename,
                "printer_id": printer_id,
                "created": time.time(),
                "history_ref": history_ref,   # MK6 v1.2.0: siehe _record_history_after_send()
                "queue_ref": queue_ref,
                "farmbot_ref": farmbot_ref,   # v2.6.0: siehe _record_history_after_send()
            }

        self._set_progress(job_id, phase="uploading", sent=0, total=total_size, percent=0, error=None)

        def worker():
            def on_progress(sent, total):
                percent = int(sent * 100 / total) if total else 0
                self._set_progress(job_id, phase="uploading", sent=sent, total=total, percent=percent)
            try:
                conn.send_print(local_path, filename, on_progress=on_progress)
                self._set_progress(job_id, phase="done", sent=total_size, total=total_size, percent=100)
                # MK6: siehe identischer Kommentar in start_confirm_print_job() oben.
                self._record_history_after_send({
                    "printer_id": printer_id, "local_path": local_path,
                    "remote_name": filename, "history_ref": history_ref, "queue_ref": queue_ref,
                    "farmbot_ref": farmbot_ref,
                })
                with self._print_jobs_lock:
                    job = self._print_jobs.pop(job_id, None)
                if job:
                    self._cleanup_job_file(job)
            except Exception as e:
                self._set_progress(job_id, phase="error", error=str(e))

        threading.Thread(target=worker, daemon=True).start()
        return True, None, job_id

    # ------------------------------------------------------------------
    # MK6: Druckauftrags-Verlauf - Abfragen, Loeschen, Erneut drucken
    # (siehe PrintHistoryStore-Kommentar fuer die Ablage). Diese drei
    # Methoden sind duenne Wrapper um PrintHistoryStore, mit Ausnahme
    # von reprint_from_history(), das den bestehenden Sende-Ablauf
    # (prepare_print_job()/send_ultimaker_print_now()) wiederverwendet,
    # statt eine eigene, parallele Druckstart-Logik einzufuehren.
    # ------------------------------------------------------------------
    def get_print_history(self, printer_id):
        return self.history.list_entries(printer_id)

    def delete_print_history_entry(self, printer_id, job_id):
        return self.history.delete_entry(printer_id, job_id)

    def get_print_history_thumbnail_path(self, printer_id, job_id):
        return self.history.get_thumbnail_path(printer_id, job_id)

    def reprint_from_history(self, printer_id, job_id):
        """Startet einen im Verlauf gespeicherten Druckauftrag erneut -
        ueber genau denselben Ablauf wie ein frischer Drag&Drop-Upload,
        mit der gespeicherten Datei als Quelle. Die Verlaufsdatei selbst
        bleibt dabei unangetastet (es wird zuerst eine Kopie in einem
        neuen temporaeren Job-Ordner angelegt, wie es prepare_print_job()/
        send_ultimaker_print_now() ohnehin fuer jeden Upload erwarten -
        deren Cleanup-Pfade loeschen also nur die Kopie, nie das
        Original im Verlauf).

        Fuer Bambu-Drucker durchlaeuft das erneut den AMS-Zuordnungs-
        dialog (preview_print()) statt die frueher gesendete Zuordnung
        blind zu wiederholen - die AMS-Bestueckung kann sich seit dem
        letzten Druck geaendert haben. Fuer Ultimaker (keine AMS-
        Zuordnung noetig) wird der Druck dagegen sofort gestartet,
        identisch zu send_ultimaker_print_now().

        MK6 v1.2.0: Ist der Drucker gerade beschaeftigt (is_printer_busy()),
        wird NICHT sofort erneut gedruckt, sondern der Auftrag landet in
        dessen Warteschlange (mode "queued") - mit history_ref auf den
        urspruenglichen Verlaufseintrag, damit ein spaeteres tatsaechliches
        Senden ueber die Warteschlange KEINEN zweiten Verlaufseintrag
        erzeugt (siehe _record_history_after_send()). Auch im NICHT
        beschaeftigten Fall wird history_ref mitgegeben, aus demselben
        Grund - ein direktes "Erneut drucken" soll den Verlaufseintrag nur
        aktualisieren, nicht verdoppeln."""
        p = self.get_printer_cfg(printer_id)
        if not p:
            return False, "Drucker nicht gefunden.", None
        stored_path, filename = self.history.get_job_file_path(printer_id, job_id)
        if not stored_path:
            return False, "Dieser Verlaufseintrag ist nicht mehr vorhanden.", None

        history_ref = {"printer_id": printer_id, "job_id": job_id}

        if self.is_printer_busy(printer_id):
            entry = self.queue.add_entry(printer_id, stored_path, filename, history_ref=history_ref)
            if not entry:
                return False, "Auftrag konnte nicht in die Warteschlange gelegt werden.", None
            return True, None, {"mode": "queued", "queue_entry": entry}

        try:
            tmp_path = self._copy_to_temp_job_dir(stored_path, filename)
        except Exception as e:
            return False, f"Datei konnte nicht aus dem Verlauf kopiert werden: {e}", None

        if p.get("type") == "ultimaker":
            ok, err, new_job_id = self.send_ultimaker_print_now(printer_id, tmp_path, filename, history_ref=history_ref)
            if not ok:
                self._cleanup_job_file({"local_path": tmp_path})
                return False, err, None
            return True, None, {"mode": "ultimaker", "job_id": new_job_id}

        ok, err, new_job_id, preview = self.prepare_print_job(printer_id, tmp_path, filename, history_ref=history_ref)
        if not ok:
            self._cleanup_job_file({"local_path": tmp_path})
            return False, err, None
        return True, None, {
            "mode": "bambu",
            "job_id": new_job_id,
            "filename": filename,
            "filaments": preview["filaments"],
            "ams_trays": preview["ams_trays"],
            "total_filaments": preview.get("total_filaments", len(preview["filaments"])),
        }

    # ------------------------------------------------------------------
    # MK6 v1.2.0 NEUES FEATURE: Warteschlange je Drucker (siehe
    # PrintQueueStore-Kommentar). Analog zu reprint_from_history() oben
    # nutzt start_next_queued_print() denselben Sende-Ablauf wieder
    # (prepare_print_job()/send_ultimaker_print_now()), statt eine eigene
    # parallele Druckstart-Logik einzufuehren.
    # ------------------------------------------------------------------
    def get_print_queue(self, printer_id):
        return self.queue.list_entries(printer_id)

    def delete_print_queue_entry(self, printer_id, job_id):
        return self.queue.delete_entry(printer_id, job_id)

    def get_print_queue_thumbnail_path(self, printer_id, job_id):
        return self.queue.get_thumbnail_path(printer_id, job_id)

    def reorder_print_queue(self, printer_id, ordered_job_ids):
        return self.queue.reorder(printer_id, ordered_job_ids)

    def enqueue_upload(self, printer_id, local_path, filename):
        """Legt eine frisch hochgeladene Datei in die Warteschlange - sei
        es automatisch, weil der Drucker beim Hochladen beschaeftigt war
        (api_print_prepare()/api_ultimaker_print()), oder weil der Nutzer
        bewusst manuell vorab einreiht (api_print_queue_add()). `local_path`
        ist eine EINMALIGE Temp-Datei dieses Uploads (wie sonst auch beim
        direkten Druckstart) - queue.add_entry() kopiert sie in den
        Warteschlangen-Ordner, das Original wird danach hier geloescht
        (identisch zum Muster von _cleanup_job_file())."""
        p = self.get_printer_cfg(printer_id)
        if not p:
            return False, "Drucker nicht gefunden.", None
        entry = self.queue.add_entry(printer_id, local_path, filename)
        self._cleanup_job_file({"local_path": local_path})
        if not entry:
            return False, "Datei konnte nicht in die Warteschlange gelegt werden.", None
        return True, None, entry

    def _validate_assign_target(self, source_cfg, target_cfg):
        """MK6 v2.1.0: prueft, ob ein Druckauftrag von source_cfg auf
        target_cfg zugewiesen werden darf. Beide Drucker muessen vom
        selben Typ sein; bei Bambu Lab zusaetzlich derselben Druckerfamilie
        angehoeren (z.B. nur A1 untereinander, nur X1 untereinander) - ein
        auf A1 vorbereiteter Druckauftrag (Slicing/AMS-Zuordnung) ist auf
        einem X1 nicht ohne Weiteres gueltig. Gibt (True, None) oder
        (False, Fehlermeldung) zurueck."""
        source_type = source_cfg.get("type", "bambu")
        target_type = target_cfg.get("type", "bambu")
        if source_type != target_type:
            return False, "Ein Druckauftrag kann nur einem Drucker desselben Typs zugewiesen werden."
        if source_type == "bambu":
            source_family = source_cfg.get("bambu_family", "x1")
            target_family = target_cfg.get("bambu_family", "x1")
            if source_family != target_family:
                return False, ("Ein Druckauftrag kann bei Bambu Lab nur einem Drucker derselben "
                               "Druckerfamilie zugewiesen werden (z.B. nur A1 untereinander, "
                               "nur X1 untereinander).")
        return True, None

    def add_history_entry_to_queue(self, printer_id, job_id, target_printer_id=None):
        """Legt einen VORHANDENEN Verlaufseintrag in eine Warteschlange -
        standardmaessig die EIGENE des Druckers ("In Warteschlange legen"),
        oder per target_printer_id die eines ANDEREN Druckers im Dashboard
        ("Zuweisen"). Der Verlaufseintrag selbst bleibt in jedem Fall
        unangetastet bestehen (stored_path wird nur KOPIERT)."""
        target_printer_id = target_printer_id or printer_id
        target_cfg = self.get_printer_cfg(target_printer_id)
        if not target_cfg:
            return False, "Ziel-Drucker nicht gefunden.", None
        if target_printer_id != printer_id:
            source_cfg = self.get_printer_cfg(printer_id)
            if not source_cfg:
                return False, "Quell-Drucker nicht gefunden.", None
            ok, err = self._validate_assign_target(source_cfg, target_cfg)
            if not ok:
                return False, err, None
        stored_path, filename = self.history.get_job_file_path(printer_id, job_id)
        if not stored_path:
            return False, "Dieser Verlaufseintrag ist nicht mehr vorhanden.", None
        entry = self.queue.add_entry(target_printer_id, stored_path, filename,
                                      history_ref={"printer_id": printer_id, "job_id": job_id})
        if not entry:
            return False, "Auftrag konnte nicht in die Warteschlange gelegt werden.", None
        return True, None, entry

    def move_queue_entry(self, printer_id, job_id, target_printer_id):
        """Weist einen Warteschlangen-Eintrag einem ANDEREN Drucker im
        Dashboard zu: kopiert ihn (samt ggf. vorhandenem history_ref) in
        dessen Warteschlange und entfernt ihn danach aus der urspruenglichen
        - er wird also VERSCHOBEN, nicht dupliziert."""
        if not target_printer_id or target_printer_id == printer_id:
            return False, "Ziel-Drucker muss sich vom aktuellen Drucker unterscheiden.", None
        target_cfg = self.get_printer_cfg(target_printer_id)
        if not target_cfg:
            return False, "Ziel-Drucker nicht gefunden.", None
        source_cfg = self.get_printer_cfg(printer_id)
        if not source_cfg:
            return False, "Quell-Drucker nicht gefunden.", None
        ok, err = self._validate_assign_target(source_cfg, target_cfg)
        if not ok:
            return False, err, None
        src_entry = self.queue.get_entry(printer_id, job_id)
        stored_path, filename = self.queue.get_job_file_path(printer_id, job_id)
        if not stored_path:
            return False, "Dieser Warteschlangen-Eintrag ist nicht mehr vorhanden.", None
        history_ref = (src_entry or {}).get("history_ref")
        new_entry = self.queue.add_entry(target_printer_id, stored_path, filename, history_ref=history_ref)
        if not new_entry:
            return False, "Auftrag konnte nicht dem Ziel-Drucker zugewiesen werden.", None
        self.queue.delete_entry(printer_id, job_id)
        return True, None, new_entry

    def start_next_queued_print(self, printer_id):
        """'Druckraum leer' - startet den AELTESTEN (=naechsten) Auftrag
        der Warteschlange dieses Druckers, ueber denselben Ablauf wie
        reprint_from_history() (AMS-Dialog bei Bambu, sofortiger Druck bei
        Ultimaker). Der Warteschlangen-Eintrag wird erst NACH bestaetigtem
        Erfolg entfernt (siehe _record_history_after_send()), nicht schon
        hier - ein Abbruch im AMS-Dialog oder ein Sendefehler verliert den
        Auftrag also nicht aus der Warteschlange.

        Prueft sicherheitshalber ERNEUT is_ready_for_next_print() -
        verhindert, dass ein versehentlicher zweiter Klick waehrend eines
        noch laufenden Drucks (oder, bei Bambu, waehrend eines
        Uebergangszustands wie "PREPARE"/"SLICING") einen weiteren
        Auftrag ueber dieselbe Verbindung lostreten will (v2.0.1: bei
        Bambu Lab strenger als reines "nicht beschaeftigt" - siehe
        is_ready_for_next_print())."""
        p = self.get_printer_cfg(printer_id)
        if not p:
            return False, "Drucker nicht gefunden.", None
        if not self.is_ready_for_next_print(printer_id):
            if p.get("type", "bambu") == "bambu":
                return False, ("Dieser Bambu-Lab-Drucker ist noch nicht fertig (Status muss FINISH, "
                                "IDLE oder FAILED sein) - die Warteschlange kann erst fortgesetzt "
                                "werden, wenn der aktuelle Druck abgeschlossen oder abgebrochen "
                                "ist."), None
            return False, ("Dieser Drucker druckt (oder pausiert) noch - die Warteschlange kann "
                            "erst fortgesetzt werden, wenn der aktuelle Druck abgeschlossen ist."), None
        entries = self.queue.list_entries(printer_id)
        if not entries:
            return False, "Die Warteschlange dieses Druckers ist leer.", None
        next_entry = entries[0]
        job_id = next_entry["job_id"]
        stored_path, filename = self.queue.get_job_file_path(printer_id, job_id)
        if not stored_path:
            self.queue.delete_entry(printer_id, job_id)
            return False, "Datei zu diesem Warteschlangen-Eintrag fehlt - Eintrag wurde entfernt.", None

        try:
            tmp_path = self._copy_to_temp_job_dir(stored_path, filename)
        except Exception as e:
            return False, f"Datei konnte nicht aus der Warteschlange kopiert werden: {e}", None

        queue_ref = {"printer_id": printer_id, "job_id": job_id}
        history_ref = next_entry.get("history_ref")

        if p.get("type") == "ultimaker":
            ok, err, new_job_id = self.send_ultimaker_print_now(printer_id, tmp_path, filename,
                                                                  history_ref=history_ref, queue_ref=queue_ref)
            if not ok:
                self._cleanup_job_file({"local_path": tmp_path})
                return False, err, None
            return True, None, {"mode": "ultimaker", "job_id": new_job_id}

        ok, err, new_job_id, preview = self.prepare_print_job(printer_id, tmp_path, filename,
                                                                history_ref=history_ref, queue_ref=queue_ref)
        if not ok:
            self._cleanup_job_file({"local_path": tmp_path})
            return False, err, None
        return True, None, {
            "mode": "bambu",
            "job_id": new_job_id,
            "filename": filename,
            "filaments": preview["filaments"],
            "ams_trays": preview["ams_trays"],
            "total_filaments": preview.get("total_filaments", len(preview["filaments"])),
        }


dash = DashboardApp()
app = Flask(__name__)


# ----------------------------------------------------------------------
# REST-API
# ----------------------------------------------------------------------
@app.route("/api/printers", methods=["GET"])
def api_list_printers():
    return jsonify(dash.all_status())


@app.route("/api/printers", methods=["POST"])
def api_add_printer():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    ip = (data.get("ip") or "").strip()
    ptype = (data.get("type") or "bambu").strip().lower()

    if ptype not in KNOWN_TYPES:
        return jsonify({"error": "Unbekannter Druckertyp."}), 400
    if not name or not ip:
        return jsonify({"error": "Name und IP sind Pflichtfelder."}), 400
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return jsonify({"error": "Ungueltige IP-Adresse."}), 400

    if ptype in FORMLABS_TYPES:
        printer = dash.add_printer(name, ip, ptype=ptype)

    elif ptype == "octoprint":
        api_key = (data.get("api_key") or "").strip()
        if not api_key:
            return jsonify({"error": "Fuer OctoPrint ist der API-Key ein Pflichtfeld."}), 400
        try:
            port = int(data.get("port") or 80)
        except ValueError:
            return jsonify({"error": "Ungueltiger Port."}), 400
        https = bool(data.get("https"))
        webcam_url = (data.get("webcam_url") or "").strip()
        printer = dash.add_printer(name, ip, ptype="octoprint", api_key=api_key,
                                    port=port, https=https, webcam_url=webcam_url)

    elif ptype in CREALITY_TYPES:
        # Moonraker erlaubt vertrauenswuerdige LAN-IPs standardmaessig ohne
        # API-Key (siehe [authorization] trusted_clients in moonraker.conf)
        # - der Key ist hier deshalb optional, anders als bei OctoPrint.
        api_key = (data.get("api_key") or "").strip()
        try:
            port = int(data.get("port") or 7125)
        except ValueError:
            return jsonify({"error": "Ungueltiger Port."}), 400
        webcam_url = (data.get("webcam_url") or "").strip()
        printer = dash.add_printer(name, ip, ptype=ptype, api_key=api_key,
                                    port=port, webcam_url=webcam_url)

    elif ptype == "ultimaker":
        # Die Ultimaker-API benoetigt fuer reine Status-Abfragen (die
        # dieses Dashboard ausschliesslich macht) keinerlei Login/Key.
        try:
            port = int(data.get("port") or 80)
        except ValueError:
            return jsonify({"error": "Ungueltiger Port."}), 400
        webcam_url = (data.get("webcam_url") or "").strip()
        printer = dash.add_printer(name, ip, ptype="ultimaker", port=port, webcam_url=webcam_url)

    else:
        access_code = (data.get("access_code") or "").strip()
        serial = (data.get("serial") or "").strip()
        if not access_code or not serial:
            return jsonify({"error": "Fuer Bambu Lab Drucker sind Access Code und Seriennummer Pflichtfelder."}), 400
        # WICHTIG (v1.6.1): Druckerfamilie bestimmt, welches FTPS-
        # Verbindungsprofil beim allerersten Upload-Versuch benutzt
        # wird (siehe PrinterConnection._ftps_upload() und
        # FTPS_PROFILES) - vermeidet unnoetige Fehlversuche, wenn das
        # Druckermodell bereits bekannt ist. "x1" bleibt der Standard
        # (Ruestet auch bestehende Konfigurationen ohne dieses Feld ab -
        # siehe load_config()), da die X1-Serie zuerst zuverlaessig
        # geloest wurde und mehr Nutzer betreffen duerfte.
        # WICHTIG (v1.6.7/v1.6.8): "h2" (H2S/H2D/H2D Pro/H2C), "p1"
        # (P1P/P1S), "p2" (P2S) und "x2" (X2D) als weitere Familien
        # ergaenzt - gueltige Werte ergeben sich direkt aus
        # BAMBU_FAMILY_TO_FTPS_PROFILE (siehe dortiger Kommentar fuer
        # die Begruendung, warum sie vorerst alle das X1-Profil nutzen -
        # das ist jeweils eine begruendete, aber unbestaetigte Annahme).
        # Sollte sich das fuer eine Familie als falsch herausstellen,
        # ist die einzige noetige Aenderung ein neuer Eintrag in
        # BAMBU_FAMILY_TO_FTPS_PROFILE (und ggf. ein eigenes Profil in
        # FTPS_PROFILES, falls X1 nicht passt).
        bambu_family = (data.get("bambu_family") or "x1").strip().lower()
        if bambu_family not in BAMBU_FAMILY_TO_FTPS_PROFILE:
            bambu_family = "x1"
        printer = dash.add_printer(name, ip, ptype="bambu", access_code=access_code,
                                    serial=serial, bambu_family=bambu_family)

    return jsonify(printer), 201


@app.route("/api/printers/<printer_id>", methods=["DELETE"])
def api_delete_printer(printer_id):
    dash.remove_printer(printer_id)
    return jsonify({"ok": True})


@app.route("/api/printers/reorder", methods=["POST"])
def api_reorder_printers():
    """Setzt eine vollstaendig neue Anzeige-Reihenfolge ueber ALLE Drucker
    (unabhaengig von deren Raum-Zuordnung), Body {"order": [printer_id, ...]}
    - siehe DashboardApp.reorder_printers() fuer die Validierung."""
    data = request.get_json(force=True) or {}
    order = data.get("order")
    if not isinstance(order, list) or not order:
        return jsonify({"error": "order (Liste von Drucker-IDs) fehlt."}), 400
    if not dash.reorder_printers(order):
        return jsonify({"error": "Reihenfolge passt nicht zu den aktuell angelegten Druckern."}), 409
    return jsonify({"ok": True})


@app.route("/api/printers/<printer_id>/group", methods=["POST"])
def api_assign_printer_group(printer_id):
    """Weist einen Drucker einem Raum/einer Gruppe zu (oder entfernt die
    Zuordnung), Body {"group_id": "<id>"} bzw. {"group_id": null}."""
    data = request.get_json(force=True) or {}
    group_id = data.get("group_id")
    if group_id is not None and not isinstance(group_id, str):
        return jsonify({"error": "group_id muss eine Zeichenkette oder null sein."}), 400
    if not dash.assign_printer_group(printer_id, group_id):
        return jsonify({"error": "Drucker oder Raum nicht gefunden."}), 404
    return jsonify({"ok": True})


# ----------------------------------------------------------------------
# v2.3.0: Raeume/Gruppen - siehe DashboardApp-Methoden fuer Details.
# ----------------------------------------------------------------------
@app.route("/api/groups", methods=["GET"])
def api_list_groups():
    return jsonify(dash.get_groups())


@app.route("/api/groups", methods=["POST"])
def api_add_group():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name ist ein Pflichtfeld."}), 400
    return jsonify(dash.add_group(name)), 201


@app.route("/api/groups/<group_id>", methods=["PUT"])
def api_rename_group(group_id):
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name ist ein Pflichtfeld."}), 400
    if not dash.rename_group(group_id, name):
        return jsonify({"error": "Raum nicht gefunden."}), 404
    return jsonify({"ok": True})


@app.route("/api/groups/<group_id>", methods=["DELETE"])
def api_delete_group(group_id):
    if not dash.remove_group(group_id):
        return jsonify({"error": "Raum nicht gefunden."}), 404
    return jsonify({"ok": True})


@app.route("/api/groups/reorder", methods=["POST"])
def api_reorder_groups():
    data = request.get_json(force=True) or {}
    order = data.get("order")
    if not isinstance(order, list) or not order:
        return jsonify({"error": "order (Liste von Raum-IDs) fehlt."}), 400
    if not dash.reorder_groups(order):
        return jsonify({"error": "Reihenfolge passt nicht zu den aktuell angelegten Raeumen."}), 409
    return jsonify({"ok": True})


# ----------------------------------------------------------------------
# v2.3.0: frei konfigurierbare, vom Drucker unabhaengige RTSP(S)-Kameras -
# siehe DashboardApp-Methoden sowie generic_rtsp_mjpeg_generator().
# ----------------------------------------------------------------------
@app.route("/api/rtsp-cameras", methods=["GET"])
def api_list_rtsp_cameras():
    return jsonify(dash.get_rtsp_cameras())


@app.route("/api/rtsp-cameras", methods=["POST"])
def api_add_rtsp_camera():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    url = (data.get("url") or "").strip()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    group_id = data.get("group_id")
    if not name or not url:
        return jsonify({"error": "Name und RTSP(S)-URL sind Pflichtfelder."}), 400
    if not (url.lower().startswith("rtsp://") or url.lower().startswith("rtsps://")):
        return jsonify({"error": "Die URL muss mit rtsp:// oder rtsps:// beginnen."}), 400
    if group_id is not None and not isinstance(group_id, str):
        return jsonify({"error": "group_id muss eine Zeichenkette oder null sein."}), 400
    if group_id is not None and not any(g["id"] == group_id for g in dash.cfg.get("groups", [])):
        return jsonify({"error": "Raum nicht gefunden."}), 404
    cam = dash.add_rtsp_camera(name, url, username=username, password=password, group_id=group_id)
    return jsonify(cam), 201


@app.route("/api/rtsp-cameras/<camera_id>", methods=["PUT"])
def api_update_rtsp_camera(camera_id):
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    url = (data.get("url") or "").strip()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not name or not url:
        return jsonify({"error": "Name und RTSP(S)-URL sind Pflichtfelder."}), 400
    if not (url.lower().startswith("rtsp://") or url.lower().startswith("rtsps://")):
        return jsonify({"error": "Die URL muss mit rtsp:// oder rtsps:// beginnen."}), 400
    if not dash.update_rtsp_camera(camera_id, name, url, username=username, password=password):
        return jsonify({"error": "Kamera nicht gefunden."}), 404
    return jsonify({"ok": True})


@app.route("/api/rtsp-cameras/<camera_id>", methods=["DELETE"])
def api_delete_rtsp_camera(camera_id):
    if not dash.remove_rtsp_camera(camera_id):
        return jsonify({"error": "Kamera nicht gefunden."}), 404
    return jsonify({"ok": True})


@app.route("/api/rtsp-cameras/<camera_id>/group", methods=["POST"])
def api_assign_rtsp_camera_group(camera_id):
    """Weist eine externe RTSP-Kamera einem Raum zu (oder entfernt die
    Zuordnung), Body {"group_id": "<id>"} bzw. {"group_id": null} - siehe
    api_assign_printer_group() fuer dasselbe Muster bei Druckern."""
    data = request.get_json(force=True) or {}
    group_id = data.get("group_id")
    if group_id is not None and not isinstance(group_id, str):
        return jsonify({"error": "group_id muss eine Zeichenkette oder null sein."}), 400
    if not dash.assign_rtsp_camera_group(camera_id, group_id):
        return jsonify({"error": "Kamera oder Raum nicht gefunden."}), 404
    return jsonify({"ok": True})


@app.route("/camera/rtsp/<camera_id>")
def rtsp_camera_stream(camera_id):
    cam = dash.get_rtsp_camera(camera_id)
    if not cam:
        return "Kamera nicht gefunden", 404
    ffmpeg_path = _find_ffmpeg_binary()
    if not ffmpeg_path:
        return ("FFmpeg wurde nicht gefunden (weder neben dem Programm noch "
                "ueber PATH). Externe RTSP-Kameras brauchen FFmpeg - siehe README."), 500
    try:
        # v2.4.0: Benutzername/Passwort (getrennt gespeichert, siehe
        # add_rtsp_camera()) erst hier, unmittelbar vor dem FFmpeg-Aufruf,
        # in die URL eingebaut - build_rtsp_url_with_auth() dort fuer die
        # Begruendung (Sonderzeichen im Passwort).
        url = build_rtsp_url_with_auth(cam["url"], cam.get("username", ""), cam.get("password", ""))
        gen = generic_rtsp_mjpeg_generator(url, ffmpeg_path, cam["name"])
        return Response(gen, mimetype="multipart/x-mixed-replace; boundary=frame")
    except Exception as e:
        return f"Kamera nicht erreichbar: {e}", 502


# ----------------------------------------------------------------------
# v2.3.0: Einstellungen (aktuell: maximale Anzahl Verlaufseintraege) -
# siehe DashboardApp.get_settings()/update_history_max_jobs().
# ----------------------------------------------------------------------
@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    return jsonify(dash.get_settings())


@app.route("/api/settings", methods=["PUT"])
def api_update_settings():
    data = request.get_json(force=True) or {}
    if "history_max_jobs" in data:
        raw_value = data["history_max_jobs"]
        # Das Frontend sendet entweder eine ganze Zahl oder null
        # ("unbegrenzt") - siehe saveHistorySettings() im <script>-Block.
        # Strings (z. B. "unendlich") bleiben fuer die manuelle
        # config.json-Bearbeitung weiterhin gueltig (siehe
        # _resolve_history_max_jobs()).
        if raw_value is not None and not isinstance(raw_value, (int, str)):
            return jsonify({"error": "history_max_jobs muss eine Zahl, null oder 'unendlich' sein."}), 400
        if isinstance(raw_value, bool):
            return jsonify({"error": "history_max_jobs muss eine Zahl, null oder 'unendlich' sein."}), 400
        dash.update_history_max_jobs(raw_value)
    if "language" in data:
        ok, err = dash.update_language(data["language"])
        if not ok:
            return jsonify({"error": err}), 400
    return jsonify(dash.get_settings())


@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify(dash.all_status())


@app.route("/api/printers/<printer_id>/extras/<extra_id>/command", methods=["POST"])
def api_extra_command(printer_id, extra_id):
    data = request.get_json(force=True) or {}
    action = (data.get("action") or "").strip().lower()
    if action not in ("on", "off"):
        return jsonify({"error": "action muss 'on' oder 'off' sein."}), 400
    ok, err = dash.send_extra_command(printer_id, extra_id, action)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True})


# v2.2.15: Verwaltung des zweiten MQTT-Brokers und der Sensoren/Schalter
# je Drucker ueber die Web-Oberflaeche (siehe DashboardApp-Methoden
# oben) - vorher nur per manueller config.json-Bearbeitung moeglich.
@app.route("/api/extras_mqtt", methods=["GET"])
def api_get_extras_mqtt():
    return jsonify(dash.get_extras_mqtt_settings())


@app.route("/api/extras_mqtt", methods=["POST"])
def api_update_extras_mqtt():
    data = request.get_json(force=True) or {}
    ok, err, settings = dash.update_extras_mqtt_settings(data)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify(settings)


@app.route("/api/extras_mqtt/discovered", methods=["GET"])
def api_extras_mqtt_discovered():
    return jsonify(dash.get_discovered_mqtt_topics())


@app.route("/api/printers/<printer_id>/extras", methods=["POST"])
def api_add_extra(printer_id):
    data = request.get_json(force=True) or {}
    ok, err, entry = dash.add_extra(printer_id, data)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify(entry), 201


@app.route("/api/printers/<printer_id>/extras/<extra_id>", methods=["PUT"])
def api_update_extra(printer_id, extra_id):
    data = request.get_json(force=True) or {}
    ok, err, entry = dash.update_extra(printer_id, extra_id, data)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify(entry)


@app.route("/api/printers/<printer_id>/extras/<extra_id>", methods=["DELETE"])
def api_delete_extra(printer_id, extra_id):
    ok = dash.delete_extra(printer_id, extra_id)
    if not ok:
        return jsonify({"error": "Eintrag nicht gefunden."}), 404
    return jsonify({"ok": True})


# v2.5.0: eigenstaendige (vom Drucker unabhaengige) MQTT-Sensoren/Schalter -
# siehe DashboardApp.add_standalone_extra() fuer den Hintergrund.
@app.route("/api/standalone_extras", methods=["GET"])
def api_get_standalone_extras():
    return jsonify(dash.get_standalone_extras())


@app.route("/api/standalone_extras", methods=["POST"])
def api_add_standalone_extra():
    data = request.get_json(force=True) or {}
    ok, err, entry = dash.add_standalone_extra(data)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify(entry), 201


@app.route("/api/standalone_extras/<extra_id>", methods=["PUT"])
def api_update_standalone_extra(extra_id):
    data = request.get_json(force=True) or {}
    ok, err, entry = dash.update_standalone_extra(extra_id, data)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify(entry)


@app.route("/api/standalone_extras/<extra_id>", methods=["DELETE"])
def api_delete_standalone_extra(extra_id):
    ok = dash.delete_standalone_extra(extra_id)
    if not ok:
        return jsonify({"error": "Eintrag nicht gefunden."}), 404
    return jsonify({"ok": True})


@app.route("/api/standalone_extras/<extra_id>/group", methods=["POST"])
def api_assign_standalone_extra_group(extra_id):
    data = request.get_json(force=True) or {}
    group_id = data.get("group_id") or None
    if not dash.assign_standalone_extra_group(extra_id, group_id):
        return jsonify({"error": "Eintrag oder Raum nicht gefunden."}), 400
    return jsonify({"ok": True})


@app.route("/api/standalone_extras/<extra_id>/command", methods=["POST"])
def api_standalone_extra_command(extra_id):
    data = request.get_json(force=True) or {}
    action = (data.get("action") or "").strip().lower()
    if action not in ("on", "off"):
        return jsonify({"error": "action muss 'on' oder 'off' sein."}), 400
    ok, err = dash.send_standalone_extra_command(extra_id, action)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True})


@app.route("/api/printers/<printer_id>/print/prepare", methods=["POST"])
def api_print_prepare(printer_id):
    """Schritt 1: Nimmt eine per Drag & Drop hochgeladene, bereits
    gesclicte .gcode.3mf-Datei entgegen, liest die Filament-Infos aus
    und schlaegt eine AMS-Zuordnung vor - laedt aber noch NICHTS auf den
    Drucker hoch und startet noch keinen Druck. Der Nutzer bestaetigt
    oder korrigiert die Zuordnung im Browser, danach folgt /print/confirm."""
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "Keine Datei erhalten."}), 400

    filename = secure_filename(f.filename)
    if not filename.lower().endswith(".gcode.3mf"):
        return jsonify({
            "error": "Nur fertig gesclicte .gcode.3mf-Dateien werden unterstuetzt "
                     "(Export aus Bambu Studio/OrcaSlicer)."
        }), 400

    tmp_dir = tempfile.mkdtemp(prefix="dashboard-print-")
    tmp_path = os.path.join(tmp_dir, filename)
    f.save(tmp_path)

    # MK6 v1.2.0: Ist der Drucker gerade beschaeftigt, wird NICHT der
    # AMS-Zuordnungsdialog geoeffnet, sondern die Datei landet in dessen
    # Warteschlange (siehe PrintQueueStore-Kommentar) - der Nutzer sendet
    # sie spaeter ueber "Druckraum leer" (POST .../queue/next).
    if dash.is_printer_busy(printer_id):
        ok, err, entry = dash.enqueue_upload(printer_id, tmp_path, filename)
        if not ok:
            return jsonify({"error": err}), 400
        return jsonify({"ok": True, "mode": "queued", "queue_entry": entry})

    ok, err, job_id, preview = dash.prepare_print_job(printer_id, tmp_path, filename)
    if not ok:
        try:
            os.remove(tmp_path)
            os.rmdir(tmp_dir)
        except Exception:
            pass
        return jsonify({"error": err}), 400

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "filename": filename,
        "filaments": preview["filaments"],
        "ams_trays": preview["ams_trays"],
        "total_filaments": preview.get("total_filaments", len(preview["filaments"])),
    })


@app.route("/api/printers/<printer_id>/print/confirm", methods=["POST"])
def api_print_confirm(printer_id):
    """Schritt 2: Startet FTPS-Upload + Druckstart der in /print/prepare
    zwischengespeicherten Datei mit der vom Nutzer bestaetigten bzw. im
    Browser korrigierten AMS-Zuordnung IM HINTERGRUND und antwortet
    sofort. Fortschritt wird ueber GET .../print/progress/<job_id>
    abgefragt (Polling)."""
    data = request.get_json(force=True) or {}
    job_id = data.get("job_id")
    mapping = data.get("mapping")
    if not job_id:
        return jsonify({"error": "job_id fehlt."}), 400
    if mapping is not None and not isinstance(mapping, list):
        return jsonify({"error": "mapping muss eine Liste sein."}), 400

    ok, err = dash.start_confirm_print_job(job_id, mapping)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/api/printers/<printer_id>/print/progress/<job_id>", methods=["GET"])
def api_print_progress(printer_id, job_id):
    """Fortschritt eines per /print/confirm gestarteten Uploads.
    phase: "uploading" | "done" | "error". Wird vom Browser alle paar
    hundert Millisekunden abgefragt, um Prozent-Anzeige + Fortschritts-
    balken zu aktualisieren."""
    progress = dash.get_print_progress(job_id)
    if not progress:
        return jsonify({"error": "Kein laufender Vorgang mit dieser job_id gefunden."}), 404
    return jsonify(progress)


@app.route("/api/printers/<printer_id>/print/cancel", methods=["POST"])
def api_print_cancel(printer_id):
    """Bricht einen vorbereiteten (aber noch nicht bestaetigten)
    Druckauftrag ab und raeumt die zwischengespeicherte Datei auf."""
    data = request.get_json(force=True) or {}
    job_id = data.get("job_id")
    if not job_id:
        return jsonify({"error": "job_id fehlt."}), 400
    dash.cancel_print_job(job_id)
    return jsonify({"ok": True})


# v2.9.0: bricht einen auf dem Drucker BEREITS LAUFENDEN Druck ab - zu
# unterscheiden von /print/cancel oben (das verwirft nur einen noch nicht
# bestaetigten, vorbereiteten Auftrag vor dem eigentlichen Senden). Siehe
# DashboardApp.abort_print() fuer den Dispatch nach Druckertyp.
@app.route("/api/printers/<printer_id>/print/abort", methods=["POST"])
def api_print_abort(printer_id):
    ok, err = dash.abort_print(printer_id)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True})


@app.route("/api/printers/<printer_id>/ultimaker/pair/start", methods=["POST"])
def api_ultimaker_pair_start(printer_id):
    """Schritt 1 der Ultimaker-Kopplung: fordert beim Drucker eine neue
    id/key-Kombination an. Der Drucker zeigt danach am eigenen Display
    eine Bestaetigungs-Abfrage - das Frontend muss danach wiederholt
    /ultimaker/pair/status abfragen, bis der Nutzer dort reagiert hat."""
    ok, err = dash.start_ultimaker_pairing(printer_id)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True})


@app.route("/api/printers/<printer_id>/ultimaker/pair/status", methods=["GET"])
def api_ultimaker_pair_status(printer_id):
    """Wird vom Frontend gepollt, waehrend auf die Bestaetigung am
    Drucker-Display gewartet wird. status: "pending" | "authorized" |
    "unauthorized"."""
    ok, err, status = dash.check_ultimaker_pairing(printer_id)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"status": status})


@app.route("/api/printers/<printer_id>/ultimaker/print", methods=["POST"])
def api_ultimaker_print(printer_id):
    """Nimmt eine fertig gesclicte .gcode-Datei entgegen (z. B. Export
    aus Cura) und startet den Druck SOFORT (keine Zuordnung wie bei
    Bambus AMS-Dialog noetig). Der Fortschritt wird ueber denselben
    generischen Endpunkt wie bei Bambu abgefragt: GET
    /api/printers/<id>/print/progress/<job_id>."""
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "Keine Datei erhalten."}), 400

    filename = secure_filename(f.filename)
    if not filename.lower().endswith(".gcode"):
        return jsonify({
            "error": "Nur fertig gesclicte .gcode-Dateien werden unterstuetzt (Export aus Cura)."
        }), 400

    tmp_dir = tempfile.mkdtemp(prefix="dashboard-print-")
    tmp_path = os.path.join(tmp_dir, filename)
    f.save(tmp_path)

    # MK6 v1.2.0: siehe identischer Kommentar in api_print_prepare() oben.
    if dash.is_printer_busy(printer_id):
        ok, err, entry = dash.enqueue_upload(printer_id, tmp_path, filename)
        if not ok:
            return jsonify({"error": err}), 400
        return jsonify({"ok": True, "mode": "queued", "queue_entry": entry})

    ok, err, job_id = dash.send_ultimaker_print_now(printer_id, tmp_path, filename)
    if not ok:
        try:
            os.remove(tmp_path)
            os.rmdir(tmp_dir)
        except Exception:
            pass
        return jsonify({"error": err}), 400

    return jsonify({"ok": True, "job_id": job_id})


# ----------------------------------------------------------------------
# MK6 NEUES FEATURE: Druckauftrags-Verlauf pro Drucker (siehe
# PrintHistoryStore/DashboardApp.reprint_from_history() weiter oben)
# ----------------------------------------------------------------------
@app.route("/api/printers/<printer_id>/history", methods=["GET"])
def api_print_history(printer_id):
    """Liste der zuletzt ueber das Dashboard an diesen Drucker
    gesendeten Druckauftraege (neueste zuerst), fuer das Untermenue der
    Drucker-Kachel."""
    return jsonify(dash.get_print_history(printer_id))


@app.route("/api/printers/<printer_id>/history/<job_id>/thumbnail", methods=["GET"])
def api_print_history_thumbnail(printer_id, job_id):
    path = dash.get_print_history_thumbnail_path(printer_id, job_id)
    if not path:
        return "Kein Vorschaubild vorhanden.", 404
    return send_file(path, mimetype="image/png")


@app.route("/api/printers/<printer_id>/history/<job_id>", methods=["DELETE"])
def api_print_history_delete(printer_id, job_id):
    """Entfernt einen einzelnen Verlaufseintrag (Datei + ggf.
    Vorschaubild + Index-Eintrag) dauerhaft aus dem Zwischenspeicher."""
    ok = dash.delete_print_history_entry(printer_id, job_id)
    if not ok:
        return jsonify({"error": "Verlaufseintrag nicht gefunden."}), 404
    return jsonify({"ok": True})


@app.route("/api/printers/<printer_id>/history/<job_id>/reprint", methods=["POST"])
def api_print_history_reprint(printer_id, job_id):
    """Startet einen gespeicherten Druckauftrag erneut - siehe
    DashboardApp.reprint_from_history() fuer den Ablauf. Bei Bambu-
    Druckern liefert die Antwort dieselben Felder wie /print/prepare
    (job_id, filename, filaments, ams_trays, total_filaments), damit das
    Frontend denselben AMS-Zuordnungsdialog (openAmsModal()) weiter-
    verwenden kann; bei Ultimaker nur job_id (Fortschritt ueber den
    bestehenden generischen /print/progress/<job_id>-Endpunkt). MK6
    v1.2.0: ist der Drucker gerade beschaeftigt, liefert die Antwort
    stattdessen mode "queued" + queue_entry (Auftrag wurde in die
    Warteschlange gelegt, siehe DashboardApp.reprint_from_history())."""
    ok, err, result = dash.reprint_from_history(printer_id, job_id)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, **result})


@app.route("/api/printers/<printer_id>/history/<job_id>/queue", methods=["POST"])
def api_print_history_to_queue(printer_id, job_id):
    """MK6 v1.2.0: Legt einen Verlaufseintrag in eine Warteschlange -
    standardmaessig die EIGENE des Druckers ("In Warteschlange legen"),
    optional per Body {"target_printer_id": "..."} die eines ANDEREN
    Druckers im Dashboard ("Zuweisen"). Der Verlaufseintrag selbst bleibt
    unangetastet erhalten (siehe DashboardApp.add_history_entry_to_queue())."""
    data = request.get_json(force=True) or {}
    target_printer_id = data.get("target_printer_id") or printer_id
    ok, err, entry = dash.add_history_entry_to_queue(printer_id, job_id, target_printer_id)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, "queue_entry": entry})


# ----------------------------------------------------------------------
# MK6 v1.2.0 NEUES FEATURE: Warteschlange pro Drucker (siehe
# PrintQueueStore/DashboardApp.start_next_queued_print() weiter oben)
# ----------------------------------------------------------------------
@app.route("/api/printers/<printer_id>/queue", methods=["GET"])
def api_print_queue(printer_id):
    """Liste der wartenden Druckauftraege dieses Druckers, AELTESTER
    (=naechster) zuerst, fuer das Warteschlangen-Untermenue der Kachel."""
    return jsonify(dash.get_print_queue(printer_id))


@app.route("/api/printers/<printer_id>/queue", methods=["POST"])
def api_print_queue_add(printer_id):
    """Legt eine Datei manuell in die Warteschlange - UNABHAENGIG vom
    Beschaeftigt-Status des Druckers (fuer vorausschauendes Einreihen
    mehrerer Auftraege, auch waehrend der Drucker gerade idle ist)."""
    p = dash.get_printer_cfg(printer_id)
    if not p:
        return jsonify({"error": "Drucker nicht gefunden."}), 404
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "Keine Datei erhalten."}), 400

    filename = secure_filename(f.filename)
    ptype = p.get("type", "bambu")
    if ptype == "ultimaker":
        if not filename.lower().endswith(".gcode"):
            return jsonify({"error": "Nur fertig gesclicte .gcode-Dateien werden unterstuetzt (Export aus Cura)."}), 400
    elif ptype == "bambu":
        if not filename.lower().endswith(".gcode.3mf"):
            return jsonify({
                "error": "Nur fertig gesclicte .gcode.3mf-Dateien werden unterstuetzt "
                         "(Export aus Bambu Studio/OrcaSlicer)."
            }), 400
    else:
        return jsonify({"error": "Eine Warteschlange wird fuer diesen Druckertyp aktuell nicht unterstuetzt."}), 400

    tmp_dir = tempfile.mkdtemp(prefix="dashboard-print-")
    tmp_path = os.path.join(tmp_dir, filename)
    f.save(tmp_path)

    ok, err, entry = dash.enqueue_upload(printer_id, tmp_path, filename)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, "queue_entry": entry})


@app.route("/api/printers/<printer_id>/queue/<job_id>/thumbnail", methods=["GET"])
def api_print_queue_thumbnail(printer_id, job_id):
    path = dash.get_print_queue_thumbnail_path(printer_id, job_id)
    if not path:
        return "Kein Vorschaubild vorhanden.", 404
    return send_file(path, mimetype="image/png")


@app.route("/api/printers/<printer_id>/queue/<job_id>", methods=["DELETE"])
def api_print_queue_delete(printer_id, job_id):
    """Entfernt einen einzelnen Warteschlangen-Eintrag (Datei + ggf.
    Vorschaubild + Index-Eintrag) dauerhaft."""
    ok = dash.delete_print_queue_entry(printer_id, job_id)
    if not ok:
        return jsonify({"error": "Warteschlangen-Eintrag nicht gefunden."}), 404
    return jsonify({"ok": True})


@app.route("/api/printers/<printer_id>/queue/reorder", methods=["POST"])
def api_print_queue_reorder(printer_id):
    """Setzt eine vollstaendig neue Reihenfolge, Body {"order": [job_id, ...]}
    - siehe PrintQueueStore.reorder() fuer die Validierung."""
    data = request.get_json(force=True) or {}
    order = data.get("order")
    if not isinstance(order, list) or not order:
        return jsonify({"error": "order (Liste von job_ids) fehlt."}), 400
    ok = dash.reorder_print_queue(printer_id, order)
    if not ok:
        return jsonify({
            "error": "Reihenfolge passt nicht zur aktuellen Warteschlange (evtl. zwischenzeitlich "
                     "geaendert) - bitte Ansicht neu laden."
        }), 409
    return jsonify({"ok": True})


@app.route("/api/printers/<printer_id>/queue/next", methods=["POST"])
def api_print_queue_next(printer_id):
    """'Druckraum leer' - startet den aeltesten Auftrag der Warteschlange,
    siehe DashboardApp.start_next_queued_print(). Antwortformat identisch
    zu /history/<job_id>/reprint (mode "bambu"/"ultimaker")."""
    ok, err, result = dash.start_next_queued_print(printer_id)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, **result})


@app.route("/api/printers/<printer_id>/queue/<job_id>/assign", methods=["POST"])
def api_print_queue_assign(printer_id, job_id):
    """Weist einen Warteschlangen-Eintrag einem ANDEREN Drucker im
    Dashboard zu (verschiebt ihn in dessen Warteschlange), Body
    {"target_printer_id": "..."}."""
    data = request.get_json(force=True) or {}
    target_printer_id = data.get("target_printer_id")
    if not target_printer_id:
        return jsonify({"error": "target_printer_id fehlt."}), 400
    ok, err, entry = dash.move_queue_entry(printer_id, job_id, target_printer_id)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, "queue_entry": entry})


# ----------------------------------------------------------------------
# v2.6.0 NEUES FEATURE: FarmBot - eigenstaendige, drucker-unabhaengige
# Warteschlange mit automatischer Terminierung und Zuweisung an einen
# freien Drucker der gewaehlten Hersteller-/Familienauswahl. Siehe
# DashboardApp-Abschnitt "FarmBot" (nahe pick_farmbot_job()) fuer die
# vollstaendige Beschreibung des Ablaufs.
# ----------------------------------------------------------------------
@app.route("/api/farmbots", methods=["GET"])
def api_list_farmbots():
    return jsonify(dash.get_farmbots_status())


@app.route("/api/farmbots", methods=["POST"])
def api_add_farmbot():
    data = request.get_json(force=True) or {}
    ok, err, entry = dash.add_farmbot(data)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, "farmbot": entry})


@app.route("/api/farmbots/<farmbot_id>", methods=["PUT"])
def api_update_farmbot(farmbot_id):
    data = request.get_json(force=True) or {}
    ok, err, entry = dash.update_farmbot(farmbot_id, data)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, "farmbot": entry})


@app.route("/api/farmbots/<farmbot_id>", methods=["DELETE"])
def api_delete_farmbot(farmbot_id):
    ok = dash.delete_farmbot(farmbot_id)
    if not ok:
        return jsonify({"error": "FarmBot nicht gefunden."}), 404
    return jsonify({"ok": True})


@app.route("/api/farmbots/<farmbot_id>/jobs", methods=["GET"])
def api_farmbot_jobs(farmbot_id):
    """Liste der wartenden Druckauftraege dieses FarmBot, AELTESTER
    (=naechster) zuerst - fuer die Warteschlangen-Ansicht im FarmBot-
    Feld des Dashboards."""
    return jsonify(dash.get_farmbot_jobs(farmbot_id))


@app.route("/api/farmbots/<farmbot_id>/jobs", methods=["POST"])
def api_farmbot_jobs_add(farmbot_id):
    """Nimmt eine per Drag & Drop in das FarmBot-Feld gelegte Datei
    entgegen - welche Dateiendung erlaubt ist, richtet sich nach der
    Hersteller-Auswahl dieses FarmBot (Bambu: .gcode.3mf, Ultimaker:
    .gcode), genau wie bei der Warteschlange eines einzelnen Druckers
    (siehe api_print_queue_add()). Die Reihenfolge wird danach
    automatisch neu berechnet (siehe DashboardApp._reorder_farmbot_queue())."""
    fb = dash.get_farmbot_cfg(farmbot_id)
    if not fb:
        return jsonify({"error": "FarmBot nicht gefunden."}), 404
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "Keine Datei erhalten."}), 400

    filename = secure_filename(f.filename)
    if fb["manufacturer"] == "ultimaker":
        if not filename.lower().endswith(".gcode"):
            return jsonify({"error": "Nur fertig gesclicte .gcode-Dateien werden unterstuetzt (Export aus Cura)."}), 400
    else:
        if not filename.lower().endswith(".gcode.3mf"):
            return jsonify({
                "error": "Nur fertig gesclicte .gcode.3mf-Dateien werden unterstuetzt "
                         "(Export aus Bambu Studio/OrcaSlicer)."
            }), 400

    tmp_dir = tempfile.mkdtemp(prefix="dashboard-print-")
    tmp_path = os.path.join(tmp_dir, filename)
    f.save(tmp_path)

    ok, err, entry = dash.add_farmbot_job(farmbot_id, tmp_path, filename)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, "queue_entry": entry})


@app.route("/api/farmbots/<farmbot_id>/jobs/<job_id>/thumbnail", methods=["GET"])
def api_farmbot_job_thumbnail(farmbot_id, job_id):
    path = dash.get_farmbot_job_thumbnail_path(farmbot_id, job_id)
    if not path:
        return "Kein Vorschaubild vorhanden.", 404
    return send_file(path, mimetype="image/png")


@app.route("/api/farmbots/<farmbot_id>/jobs/<job_id>", methods=["DELETE"])
def api_farmbot_job_delete(farmbot_id, job_id):
    ok = dash.delete_farmbot_job(farmbot_id, job_id)
    if not ok:
        return jsonify({"error": "Warteschlangen-Eintrag nicht gefunden."}), 404
    return jsonify({"ok": True})


@app.route("/api/farmbots/<farmbot_id>/jobs/reorder", methods=["POST"])
def api_farmbot_jobs_reorder(farmbot_id):
    """v2.7.0: setzt eine vollstaendig neue, haendisch vom Nutzer
    gewaehlte Reihenfolge, Body {"order": [job_id, ...]} - siehe
    PrintQueueStore.reorder() fuer die Validierung. Diese manuelle
    Reihenfolge bleibt bestehen, bis der naechste Auftrag hinzugefuegt
    wird - DANACH wird automatisch wieder neu sortiert (siehe
    DashboardApp.add_farmbot_job()/_reorder_farmbot_queue())."""
    data = request.get_json(force=True) or {}
    order = data.get("order")
    if not isinstance(order, list) or not order:
        return jsonify({"error": "order (Liste von job_ids) fehlt."}), 400
    ok = dash.reorder_farmbot_queue(farmbot_id, order)
    if not ok:
        return jsonify({
            "error": "Reihenfolge passt nicht zur aktuellen Warteschlange (evtl. zwischenzeitlich "
                     "geaendert) - bitte Ansicht neu laden."
        }), 409
    return jsonify({"ok": True})


@app.route("/api/farmbots/<farmbot_id>/pick", methods=["POST"])
def api_farmbot_pick(farmbot_id):
    """Ermittelt OHNE Seiteneffekt den naechsten Auftrag + einen dazu
    passenden, gerade freien Zieldrucker (siehe DashboardApp.
    pick_farmbot_job()) - fuer den 'Naechsten Druck starten'-Knopf.
    Body optional {"exclude_printer_ids": [...]}, genutzt, wenn der
    Nutzer im Kamera-Dialog 'anderer Drucker' waehlt."""
    data = request.get_json(force=True) or {}
    exclude = data.get("exclude_printer_ids") or []
    ok, err, result = dash.pick_farmbot_job(farmbot_id, exclude_printer_ids=exclude)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, **result})


@app.route("/api/farmbots/<farmbot_id>/assign", methods=["POST"])
def api_farmbot_assign(farmbot_id):
    """Fuehrt das Ergebnis von /pick tatsaechlich aus (siehe DashboardApp.
    assign_farmbot_job()), Body {"job_id": "...", "printer_id": "..."}.
    Bei Bambu-Druckern liefert die Antwort dieselben Felder wie
    /print/prepare (job_id, filename, filaments, ams_trays,
    total_filaments) - das Frontend oeffnet darauf denselben bestehenden
    AMS-Zuordnungsdialog und bestaetigt ueber den bestehenden Endpunkt
    POST /api/printers/<printer_id>/print/confirm; bei Ultimaker wurde der
    Druck bereits gestartet, Fortschritt ueber den bestehenden Endpunkt
    GET /api/printers/<printer_id>/print/progress/<job_id>."""
    data = request.get_json(force=True) or {}
    job_id = data.get("job_id")
    printer_id = data.get("printer_id")
    if not job_id or not printer_id:
        return jsonify({"error": "job_id und printer_id sind Pflichtfelder."}), 400
    ok, err, result = dash.assign_farmbot_job(farmbot_id, job_id, printer_id)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, "printer_id": printer_id, **result})


@app.route("/api/version", methods=["GET"])
def api_version():
    return jsonify({"version": APP_VERSION})


@app.route("/camera/<printer_id>")
def camera_stream(printer_id):
    pcfg = dash.get_printer_cfg(printer_id)
    if not pcfg:
        return "Drucker nicht gefunden", 404
    ptype = pcfg.get("type", "bambu")

    if ptype == "bambu":
        bambu_family = pcfg.get("bambu_family", "x1")
        if bambu_family in BAMBU_RTSPS_CAMERA_FAMILIES:
            # v2.2.22: X1/P1/P2/H2/X2 - RTSPS ueber FFmpeg, siehe
            # bambu_rtsp_mjpeg_generator() fuer die vollstaendige
            # Quellenlage/Begruendung der einzelnen Schritte unten.
            conn = dash.connections.get(printer_id)
            rtsp_status = conn.status.get("ipcam_rtsp_url") if conn else None
            if rtsp_status == "disable":
                return ("Kamera-Livestream ist am Drucker nicht aktiviert. Bitte "
                        "zusaetzlich zum Developer Mode am Drucker-Display die "
                        "separate Einstellung \"LAN Only Liveview\" (teils auch "
                        "\"LAN Mode Liveview\" genannt) aktivieren - siehe README."), 409
            if rtsp_status is None:
                return ("Kamera-Status noch nicht bekannt (noch kein vollstaendiger "
                        "MQTT-Report vom Drucker empfangen). Bitte kurz warten und "
                        "erneut versuchen."), 503
            ffmpeg_path = _find_ffmpeg_binary()
            if not ffmpeg_path:
                return ("FFmpeg wurde nicht gefunden (weder neben dem Programm noch "
                        "ueber PATH). Der Kamera-Stream dieser Druckerfamilie "
                        "braucht FFmpeg - siehe README."), 500
            try:
                gen = bambu_rtsp_mjpeg_generator(pcfg["ip"], pcfg["access_code"], ffmpeg_path)
                # v2.2.26: boundary jetzt "frame" statt "ffserver" - der
                # Generator verpackt die Bilder seit v2.2.26 selbst im
                # selben Format wie bambu_mjpeg_generator() (A1-Kamera),
                # nicht mehr im (browserinkompatiblen) Rohformat von
                # FFmpegs "-f mpjpeg"-Muxer. Siehe ausfuehrliche Begruendung
                # in bambu_rtsp_mjpeg_generator().
                return Response(gen, mimetype="multipart/x-mixed-replace; boundary=frame")
            except Exception as e:
                return f"Kamera nicht erreichbar: {e}", 502
        try:
            gen = bambu_mjpeg_generator(pcfg["ip"], pcfg["access_code"], int(pcfg.get("camera_port", 6000)))
            return Response(gen, mimetype="multipart/x-mixed-replace; boundary=frame")
        except Exception as e:
            return f"Kamera nicht erreichbar: {e}", 502

    elif ptype == "octoprint":
        webcam_url = pcfg.get("webcam_url") or f"http://{pcfg['ip']}:8080/webcam/?action=stream"
        return redirect(webcam_url)

    elif ptype in CREALITY_TYPES:
        # Crowsnest (der bei Klipper/Moonraker-Setups uebliche Webcam-Dienst)
        # stellt seinen MJPEG-Stream typischerweise unter diesem Pfad bereit.
        webcam_url = pcfg.get("webcam_url") or f"http://{pcfg['ip']}/webcam/?action=stream"
        return redirect(webcam_url)

    elif ptype == "ultimaker":
        # Bei allen netzwerkfaehigen Ultimaker-Modellen mit eingebauter
        # Kamera (UM3, S-Serie) liefert der integrierte mjpg-streamer den
        # Stream ueblicherweise unter diesem Pfad.
        webcam_url = pcfg.get("webcam_url") or f"http://{pcfg['ip']}:8080/?action=stream"
        return redirect(webcam_url)

    else:
        return "Kamera-Funktion ist fuer diesen Druckertyp nicht verfuegbar.", 400


@app.route("/")
def index():
    return render_template_string(INDEX_HTML)


# ----------------------------------------------------------------------
# Frontend (dunkles, technisches Dashboard-Design)
# ----------------------------------------------------------------------
INDEX_HTML = r"""
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Drucker Dashboard</title>
<style>
  :root{
    --bg:#0a0c0f;
    --panel:#12151a;
    --panel-2:#171b21;
    --border:#242a33;
    --text:#e5e8ec;
    --text-dim:#8891a0;
    --accent:#ff9142;
    --accent-2:#3ddc97;
    --danger:#ff5d5d;
    --info:#4aa3ff; /* v2.2.2: AMS-Luftfeuchtigkeit (Sparkline + Massstab) */
    --mono: 'JetBrains Mono', 'Consolas', 'SFMono-Regular', monospace;
    --sans: 'Inter', 'Segoe UI', system-ui, sans-serif;
  }
  *{box-sizing:border-box;}
  body{
    margin:0; background:var(--bg); color:var(--text);
    font-family:var(--sans); letter-spacing:0.1px;
  }
  header{
    display:flex; align-items:center; justify-content:space-between;
    padding:22px 32px; border-bottom:1px solid var(--border);
    background:linear-gradient(180deg,#0d1014,#0a0c0f);
  }
  header h1{
    font-size:18px; font-weight:600; margin:0; letter-spacing:0.5px;
    text-transform:uppercase; color:var(--text);
  }
  header h1 span{ color:var(--accent); }
  .btn{
    background:var(--accent); color:#12100c; border:none; border-radius:6px;
    padding:10px 18px; font-weight:600; font-size:13px; cursor:pointer;
    letter-spacing:0.3px; transition:filter .15s ease;
  }
  .btn:hover{ filter:brightness(1.1); }
  .btn-ghost{
    background:transparent; color:var(--text-dim); border:1px solid var(--border);
  }
  .btn-ghost:hover{ color:var(--text); border-color:#3a4250; }
  .btn-mini{
    background:#1b2027; color:var(--text); border:1px solid var(--border);
    border-radius:5px; padding:5px 10px; font-size:11px; cursor:pointer;
    font-family:var(--mono);
  }
  .btn-mini:hover{ border-color:var(--accent-2); }
  .btn-mini.off:hover{ border-color:var(--danger); }
  /* v2.1.0: alle echten "Loeschen"-Schaltflaechen (Verlauf/Warteschlange)
     durchgehend rot, nicht erst bei Hover - analog zu .del-icon. Bewusst
     eine EIGENE Klasse statt .btn-mini.off: .off wird bereits fuer den
     "Aus"-Knopf eines Sensoren/Schalter-Eintrags verwendet (siehe
     renderExtras()) - der soll NICHT rot werden, das waere fachlich
     falsch (Ausschalten ist keine destruktive Loesch-Aktion). */
  .btn-mini.btn-delete{ color:var(--danger); border-color:#c0392b66; }
  .btn-mini.btn-delete:hover{ border-color:var(--danger); filter:brightness(1.15); }
  /* MK6: main = #printerList - Karten-Layout wahlweise 1/2/3/4-spaltig
     (4 seit v2.4.0), siehe .cols-2/.cols-3/.cols-4 (per JS umgeschaltet,
     Wahl lokal gespeichert). */
  main{
    padding:28px 32px; max-width:1100px; margin:0 auto;
    display:grid; grid-template-columns:1fr; gap:22px; align-items:start;
  }
  main.cols-2{ max-width:1600px; grid-template-columns:repeat(2, 1fr); }
  main.cols-3{ max-width:2000px; grid-template-columns:repeat(3, 1fr); }
  main.cols-4{ max-width:2400px; grid-template-columns:repeat(4, 1fr); }
  @media(max-width:1500px){
    main.cols-4{ grid-template-columns:repeat(3, 1fr); max-width:2000px; }
  }
  @media(max-width:1150px){
    main.cols-3, main.cols-4{ grid-template-columns:repeat(2, 1fr); max-width:1600px; }
  }
  @media(max-width:760px){
    main.cols-2, main.cols-3, main.cols-4{ grid-template-columns:1fr; max-width:1100px; }
  }
  .layout-switch{
    display:flex; border:1px solid var(--border); border-radius:6px; overflow:hidden;
  }
  .layout-btn{
    background:#1b2027; color:var(--text-dim); border:none; border-right:1px solid var(--border);
    padding:9px 13px; font-size:12px; font-family:var(--mono); cursor:pointer;
  }
  .layout-btn:last-child{ border-right:none; }
  .layout-btn:hover{ color:var(--text); }
  .layout-btn.active{ background:var(--accent); color:#12100c; font-weight:600; }
  .printer-card{
    background:var(--panel); border:1px solid var(--border); border-radius:10px;
    overflow:hidden; container-type:inline-size;
  }
  .card-head{
    display:flex; align-items:center; justify-content:space-between;
    padding:16px 20px; border-bottom:1px solid var(--border);
    background:var(--panel-2);
  }
  .card-head .name{ font-size:15px; font-weight:600; }
  .card-head .ip{ font-family:var(--mono); font-size:12px; color:var(--text-dim); margin-left:10px;}
  .type-badge{
    font-family:var(--mono); font-size:10px; padding:2px 8px; border-radius:20px;
    border:1px solid var(--border); color:var(--text-dim); text-transform:uppercase; margin-left:10px;
  }
  .status-dot{
    width:9px; height:9px; border-radius:50%; display:inline-block; margin-right:8px;
    background:var(--danger);
  }
  .status-dot.online{ background:var(--accent-2); box-shadow:0 0 6px var(--accent-2); }
  .head-right{ display:flex; align-items:center; gap:14px; }
  .cam-icon{
    cursor:pointer; width:30px; height:30px; border-radius:6px;
    display:flex; align-items:center; justify-content:center;
    border:1px solid var(--border); background:#1b2027;
  }
  .cam-icon:hover{ border-color:var(--accent); }
  .cam-icon svg{ width:16px; height:16px; fill:var(--text-dim); }
  .cam-icon:hover svg{ fill:var(--accent); }
  .hist-icon{
    cursor:pointer; width:30px; height:30px; border-radius:6px;
    display:flex; align-items:center; justify-content:center;
    border:1px solid var(--border); background:#1b2027;
  }
  .hist-icon:hover{ border-color:var(--accent-2); }
  .hist-icon svg{ width:16px; height:16px; fill:var(--text-dim); }
  .hist-icon:hover svg{ fill:var(--accent-2); }
  /* v2.1.0: Loesch-Icon/-Buttons durchgehend rot hinterlegt (nicht erst
     bei Hover), damit eine destruktive Aktion sofort erkennbar ist. */
  .del-icon{ cursor:pointer; color:var(--danger); font-size:18px; padding:0 4px;}
  .del-icon:hover{ filter:brightness(1.25); }

  .card-body{ padding:20px; display:grid; grid-template-columns:1.3fr 1fr; gap:24px; }
  .card-body.single-col{ grid-template-columns:1fr; }
  @media(max-width:760px){ .card-body{ grid-template-columns:1fr; } }
  /* Faellt zusaetzlich auf einspaltig zurueck, wenn die KARTE SELBST schmal
     ist (z. B. im 3-Spalten-Layout auf einem normal breiten Monitor) - nicht
     nur wenn das ganze Browserfenster schmal ist. Browser ohne Container-
     Query-Unterstuetzung ignorieren das einfach und nutzen weiterhin nur die
     media-query-Regel oben (rein additiv, kein Fallback-Risiko). */
  @container (max-width:560px){ .card-body{ grid-template-columns:1fr; } }

  .field-label{ font-size:11px; text-transform:uppercase; letter-spacing:0.6px; color:var(--text-dim); margin-bottom:6px; }
  .file-name{ font-family:var(--mono); font-size:13px; margin-bottom:14px; word-break:break-all; }
  .error-hint{
    font-family:var(--mono); font-size:11.5px; color:var(--danger);
    background:#2a1414; border:1px solid #4a1f1f; border-radius:6px;
    padding:8px 10px; margin-top:4px;
  }

  .progress-row{ display:flex; align-items:center; gap:12px; margin-bottom:16px; }
  /* v2.2.0: Vorschaubild des aktuellen/zuletzt gestarteten Druckauftrags
     neben dem Fortschrittsbalken (siehe progressThumb()) - dieselbe
     Bildquelle wie im Verlaufs-Fenster, daher dieselbe Bildproportion
     (object-fit:cover, quadratisch zugeschnitten). */
  .progress-thumb{
    width:40px; height:40px; border-radius:6px; object-fit:cover;
    border:1px solid var(--border); flex-shrink:0; background:#1b2027;
  }
  .progress-track{
    flex:1; height:10px; border-radius:5px; background:#20252c; overflow:hidden;
    border:1px solid var(--border);
  }
  .progress-fill{
    height:100%; background:linear-gradient(90deg,var(--accent-2),#2bb987);
    width:0%; transition:width .4s ease;
  }
  .progress-pct{ font-family:var(--mono); font-size:14px; min-width:46px; text-align:right;}

  .temps{ display:flex; gap:18px; margin-top:6px; flex-wrap:wrap; }
  .temp-chip{
    background:#1b2027; border:1px solid var(--border); border-radius:6px;
    padding:8px 12px; font-family:var(--mono); font-size:12.5px; color:var(--text-dim);
    display:flex; align-items:center; gap:8px;
  }
  .temp-chip b{ color:var(--text); font-size:13px; }
  /* v2.2.0: kleines Verlaufsdiagramm (Sparkline) je Temperaturanzeige -
     rein client-seitig aus den letzten Status-Umfragen aufgebaut (siehe
     tempHistory/sparklineSvg() im Skript), kein Backend-Speicher noetig.
     "currentColor" (siehe SVG-<polyline> in sparklineSvg()) uebernimmt
     diese Farbe. v2.2.1: auf ausdruecklichen Wunsch des Nutzers als rote
     Linie dargestellt (vorher gedimmte Chip-Textfarbe). v2.2.2: die AMS-
     Luftfeuchtigkeit (humidityChip()) nutzt jetzt eine EIGENE Klasse
     (.humidity-spark, blau) statt .temp-spark, um sie optisch von den
     Temperatur-Sparklines zu unterscheiden - siehe dort. */
  .temp-spark{ color:var(--danger); flex-shrink:0; opacity:0.9; }
  .humidity-spark{ color:var(--info); flex-shrink:0; opacity:0.9; }

  /* v2.2.2: kleiner 1-5-Massstab neben dem Feuchte-Rohwert (siehe
     humidityScale()) - gefuellte Punkte bis einschliesslich der
     aktuellen Stufe, damit die Zahl ohne Nachschlagen eingeordnet werden
     kann. v2.2.3 - NUTZER-FEEDBACK: einheitliches Blau liess nicht
     erkennen, ob ein Wert gut oder schlecht ist - die Punkte werden
     jetzt zusaetzlich in Ampelfarbe eingefaerbt (gruen/gelb/rot je nach
     Stufe, siehe HUMIDITY_LEVELS im Skript), die Sparkline-Linie selbst
     bleibt bewusst blau (siehe .humidity-spark oben). */
  .humidity-scale{ display:inline-flex; align-items:center; gap:2px; flex-shrink:0; }
  .humidity-dot{
    width:6px; height:6px; border-radius:50%; background:#232a33;
    border:1px solid var(--border); display:inline-block;
  }
  .humidity-dot.filled.good{ background:var(--accent-2); border-color:var(--accent-2); }
  .humidity-dot.filled.mid{ background:#e8b23d; border-color:#e8b23d; }
  .humidity-dot.filled.bad{ background:var(--danger); border-color:var(--danger); }
  /* v2.2.3: Wort-Label ("trocken"/"feucht"/...) neben dem Zahlenwert,
     siehe humidityLabel() - dieselbe Ampelfarbe wie der Massstab. */
  .humidity-label{ font-family:var(--sans); font-size:11px; font-weight:600; }
  .humidity-label.good{ color:var(--accent-2); }
  .humidity-label.mid{ color:#e8b23d; }
  .humidity-label.bad{ color:var(--danger); }

  .ams-title{ font-size:11px; text-transform:uppercase; letter-spacing:0.6px; color:var(--text-dim); margin-bottom:10px;}
  .ams-slot{ display:flex; align-items:center; gap:10px; margin-bottom:9px; }
  /* v2.2.1: Luftfeuchtigkeit je AMS-Einheit, unterhalb der Fach-Liste */
  .ams-humidity-row{ margin-top:4px; }
  .ams-swatch{ width:14px; height:14px; border-radius:3px; border:1px solid #000a; flex-shrink:0;}
  .ams-meta{ font-family:var(--mono); font-size:11.5px; color:var(--text-dim); width:110px; flex-shrink:0;}
  .ams-track{ flex:1; height:8px; border-radius:4px; background:#20252c; overflow:hidden; border:1px solid var(--border);}
  .ams-fill{ height:100%; }
  .ams-remain{ font-family:var(--mono); font-size:11.5px; width:36px; text-align:right; color:var(--text-dim);}
  .empty-ams{ font-size:12px; color:var(--text-dim); font-style:italic; }

  .drop-zone{
    margin-top:16px; border:1px dashed var(--border); border-radius:8px;
    padding:14px; text-align:center; font-size:12px; color:var(--text-dim);
    transition:border-color .15s ease, background .15s ease;
  }
  .drop-zone.dragover{ border-color:var(--accent-2); background:#132018; color:var(--text); }
  .drop-zone.uploading{ border-color:var(--accent); color:var(--text); }
  .drop-zone.dz-disabled{
    cursor:default; border-style:solid; background:#1b2027;
  }
  .drop-zone.dz-disabled .btn-mini{ margin-top:6px; }
  .drop-zone .dz-hint{ font-size:10.5px; margin-top:4px; color:var(--text-dim); }
  .drop-zone .dz-status{
    font-family:var(--mono); font-size:11.5px; margin-top:8px;
  }
  .drop-zone .dz-status.err{ color:var(--danger); }
  .drop-zone .dz-status.ok{ color:var(--accent-2); }

  .ver-badge{
    font-family:var(--mono); font-size:11px; color:var(--text-dim);
    font-weight:400; vertical-align:middle; margin-left:4px;
  }

  .ams-modal{ width:480px; }
  .mqtt-modal{ width:560px; }
  .mqtt-extra-row{
    display:flex; align-items:center; justify-content:space-between; gap:10px;
    padding:8px 0; border-bottom:1px solid var(--border);
  }
  .mqtt-extra-row:last-child{ border-bottom:none; }
  .mqtt-extra-row .mqtt-extra-info{ font-size:12px; }
  .mqtt-extra-row .mqtt-extra-info .mqtt-extra-sub{ color:var(--text-dim); font-size:11px; margin-top:2px; }
  .mqtt-discovered-row{
    display:flex; justify-content:space-between; gap:10px; padding:4px 0;
    cursor:pointer; font-family:var(--mono); font-size:11px;
  }
  .mqtt-discovered-row:hover{ color:var(--accent); }
  .mqtt-discovered-list{ max-height:160px; overflow-y:auto; }
  .ams-row{
    display:flex; align-items:flex-start; gap:12px; padding:12px 0;
    border-bottom:1px solid var(--border);
  }
  .ams-row:last-child{ border-bottom:none; }
  .ams-row-body{ flex:1; min-width:0; }
  .ams-row-label{ font-size:13px; font-weight:600; margin-bottom:8px; }
  .ams-row-type{ font-family:var(--mono); font-size:11px; font-weight:400; color:var(--text-dim); }
  .ams-swatch{ margin-top:3px; }
  .ams-radio{
    display:flex; align-items:center; gap:8px; font-size:12.5px; color:var(--text-dim);
    padding:5px 0; cursor:pointer;
  }
  .ams-radio input[type="radio"]{ width:auto; margin:0; flex-shrink:0; accent-color:var(--accent-2); }
  .ams-radio b{ color:var(--text); font-weight:600; }
  .ams-row-select{
    background:#0d1014; border:1px solid var(--border); color:var(--text);
    padding:5px 7px; border-radius:6px; font-family:var(--mono); font-size:11.5px;
    margin-left:4px;
  }
  .ams-row-select:disabled{ opacity:0.4; cursor:not-allowed; }

  .ams-progress-wrap{ margin-top:16px; }
  .ams-progress-track{
    height:8px; background:#0d1014; border:1px solid var(--border);
    border-radius:5px; overflow:hidden;
  }
  .ams-progress-bar{
    height:100%; background:var(--accent-2); width:0%;
    transition:width .25s ease;
  }
  .ams-progress-label{
    font-family:var(--mono); font-size:11.5px; color:var(--text-dim);
    margin-top:6px;
  }

  .toast-container{
    position:fixed; top:18px; right:18px; z-index:80;
    display:flex; flex-direction:column; gap:10px; max-width:340px;
  }
  .toast{
    background:var(--panel); border:1px solid var(--border); border-radius:8px;
    padding:12px 14px; font-size:13px; box-shadow:0 6px 18px rgba(0,0,0,.45);
  }
  .toast.ok{ border-color:#2bb98755; color:var(--accent-2); }
  .toast.err{ border-color:#c0392b55; color:var(--danger); }

  .state-badge{
    font-family:var(--mono); font-size:11px; padding:3px 9px; border-radius:20px;
    border:1px solid var(--border); color:var(--text-dim); text-transform:uppercase;
  }
  .state-badge.running{ color:var(--accent-2); border-color:#2bb98755; }
  .state-badge.paused{ color:var(--accent); border-color:#ff914255; }

  .empty-state{
    text-align:center; padding:70px 20px; color:var(--text-dim);
  }
  .empty-state .btn{ margin-top:16px; }

  .extras-section{ margin-top:18px; padding-top:14px; border-top:1px solid var(--border); }
  .extras-row{ display:flex; flex-wrap:wrap; gap:10px; }
  .extra-sensor{
    background:#1b2027; border:1px solid var(--border); border-radius:6px;
    padding:7px 11px; font-family:var(--mono); font-size:12px; color:var(--text-dim);
    display:flex; gap:8px; align-items:center;
  }
  .extra-sensor b{ color:var(--text); }
  .extra-switch{
    background:#1b2027; border:1px solid var(--border); border-radius:6px;
    padding:6px 10px; display:flex; gap:8px; align-items:center; font-size:12px;
  }

  /* Modal */
  .modal-backdrop{
    display:none; position:fixed; inset:0; background:rgba(0,0,0,.6);
    align-items:center; justify-content:center; z-index:50;
  }
  .modal-backdrop.show{ display:flex; }
  .modal{
    background:var(--panel); border:1px solid var(--border); border-radius:10px;
    width:400px; padding:24px; max-height:85vh; overflow-y:auto;
  }
  .modal h2{ font-size:15px; margin:0 0 18px 0; text-transform:uppercase; letter-spacing:0.5px;}
  .modal label{ font-size:11px; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px;}
  .modal input, .modal select{
    width:100%; background:#0d1014; border:1px solid var(--border); color:var(--text);
    padding:9px 10px; border-radius:6px; margin:6px 0 14px 0; font-family:var(--mono); font-size:13px;
  }
  .modal input:focus, .modal select:focus{ outline:none; border-color:var(--accent); }
  .checkbox-row{ display:flex; align-items:center; gap:8px; margin:6px 0 14px 0; }
  .checkbox-row input{ width:auto; margin:0; }
  .modal-actions{ display:flex; justify-content:flex-end; gap:10px; margin-top:6px;}
  .error-msg{ color:var(--danger); font-size:12px; margin-bottom:10px; display:none;}
  .hint-text{ font-size:11px; color:var(--text-dim); margin:-8px 0 14px 0; line-height:1.4;}

  /* v2.3.0: Einstellungen-Modus - eigener Bereich statt main-Grid, siehe
     enterSettingsMode()/exitSettingsMode() sowie Markup direkt nach
     <main id="printerList">. */
  #settingsPanel{ padding:28px 32px; max-width:900px; margin:0 auto; }
  .settings-section{
    background:var(--panel); border:1px solid var(--border); border-radius:10px;
    padding:20px 24px; margin-bottom:22px;
  }
  .settings-section h2{
    font-size:14px; margin:0 0 10px 0; text-transform:uppercase; letter-spacing:0.5px;
  }
  .settings-section label{
    font-size:11px; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px;
    display:block; margin-bottom:6px;
  }
  .settings-section input, .settings-section select{
    background:#0d1014; border:1px solid var(--border); color:var(--text);
    padding:9px 10px; border-radius:6px; font-family:var(--mono); font-size:13px;
  }
  .settings-section input:focus, .settings-section select:focus{ outline:none; border-color:var(--accent); }
  .settings-inline-form{ display:flex; flex-wrap:wrap; gap:10px; align-items:center; }
  .settings-inline-form input{ flex:1; min-width:180px; }
  .manage-row{
    display:flex; align-items:center; justify-content:space-between; gap:10px;
    padding:10px 0; border-bottom:1px solid var(--border);
  }
  .manage-row:last-child{ border-bottom:none; }
  .manage-row .manage-info{ font-size:13px; flex:1; min-width:0; }
  .manage-row .manage-info .manage-sub{
    color:var(--text-dim); font-size:11px; font-family:var(--mono); margin-top:2px;
    word-break:break-all;
  }
  .manage-row .manage-actions{ display:flex; align-items:center; gap:6px; flex-shrink:0; }
  .manage-row select{ max-width:160px; }
  /* v2.3.0: Raum-Ueberschrift innerhalb des #printerList-Grids - main ist
     selbst ein CSS-Grid (siehe main{display:grid;...} oben), daher
     "grid-column:1/-1" fuer die volle Breite UND "display:contents" auf
     dem Wrapper der zugehoerigen Druckerkarten (.room-group), damit diese
     Karten weiterhin direkt als Grid-Elemente von main behandelt werden
     (nicht als ein einzelnes grosses Element). */
  .room-header{
    grid-column:1/-1; font-family:var(--mono); font-size:12px; letter-spacing:1px;
    text-transform:uppercase; color:var(--text-dim); padding-bottom:8px;
    border-bottom:1px solid var(--border); margin-top:6px;
  }
  main .room-header:first-child{ margin-top:0; }
  .room-group{ display:contents; }
  /* v2.4.0: Kachel fuer eine externe RTSP-Kamera - bewusst schlanker als
     .printer-card (keine Druckfunktionen), reiht sich aber als normales
     Grid-Element genauso in main/.room-group ein. */
  .camera-card{
    background:var(--panel); border:1px solid var(--border); border-radius:10px;
    padding:16px 20px; display:flex; align-items:center; justify-content:space-between; gap:14px;
  }
  .camera-card .name{ font-size:15px; font-weight:600; }

  /* v2.6.0: FarmBot-Feld(er) - sitzt bewusst AUSSERHALB von #printerList
     (eigenes display:grid), da FarmBot keine group_id/Raum-Zuordnung hat
     und immer oberhalb der Drucker erscheinen soll, siehe
     renderFarmbotPanel(). Jede Karte in eigenem, schmaleren Grid (mehrere
     FarmBots nebeneinander), damit sie sich optisch klar von den
     Drucker-Kacheln darunter abhebt. */
  #farmbotPanel{
    display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr));
    gap:14px; margin-bottom:18px;
  }
  .farmbot-card{
    background:var(--panel); border:1px solid #6b5b2a; border-radius:10px;
    padding:16px 20px;
  }
  .farmbot-card .card-head{
    display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:10px;
  }
  .farmbot-card .name{ font-size:15px; font-weight:600; }
  .farmbot-card .farmbot-sub{ color:var(--text-dim); font-size:12px; margin-top:2px; }
  .farmbot-card .farmbot-actions{ display:flex; align-items:center; gap:8px; }
  .farmbot-card.disabled{ opacity:0.55; }

  .cam-modal .modal{ width:auto; padding:0; overflow:hidden; }
  .cam-modal img{ display:block; max-width:90vw; max-height:80vh; background:#000; }
  .cam-modal .cam-close{
    position:absolute; top:14px; right:20px; color:#fff; font-size:26px; cursor:pointer; z-index:60;
  }

  /* MK6: Druckauftrags-Verlauf */
  /* v2.2.4: eigenes Scroll-Verhalten fuer Verlaufs-/Warteschlangen-Modal -
     Kopfbereich (Ueberschrift, Aktions-Knoepfe, Werkzeuge/Drop-Zone)
     bleibt fest sichtbar, NUR die Liste selbst (.history-modal-scroll)
     scrollt bei vielen Eintraegen. Vorher scrollte das gesamte .modal
     als ein Block (siehe .modal{overflow-y:auto}), wodurch "Schliessen"/
     "Druckraum leer" am Fuss einer langen Liste nur nach vollstaendigem
     Durchscrollen erreichbar war. */
  .history-modal{
    width:460px; display:flex; flex-direction:column; overflow:hidden;
  }
  .history-modal .modal-actions-top{ flex-shrink:0; margin-top:0; margin-bottom:14px; }
  .history-modal .history-modal-tools{ flex-shrink:0; }
  .history-modal .hint-text{ flex-shrink:0; margin:0 0 10px 0; }
  .history-modal .queue-drop-zone{ flex-shrink:0; }
  .history-modal-scroll{ overflow-y:auto; min-height:0; }
  .history-empty{ font-size:12px; color:var(--text-dim); font-style:italic; padding:10px 0; }
  .history-item{
    display:flex; gap:12px; align-items:center; padding:12px 0;
    border-bottom:1px solid var(--border);
  }
  .history-item:last-child{ border-bottom:none; }
  .history-thumb{
    width:56px; height:56px; border-radius:6px; object-fit:cover; flex-shrink:0;
    background:#0d1014; border:1px solid var(--border);
  }
  .history-thumb-placeholder{
    width:56px; height:56px; border-radius:6px; flex-shrink:0;
    background:#0d1014; border:1px solid var(--border);
    display:flex; align-items:center; justify-content:center;
  }
  .history-thumb-placeholder svg{ width:22px; height:22px; fill:var(--text-dim); }
  .history-body{ flex:1; min-width:0; }
  .history-filename{
    font-family:var(--mono); font-size:12.5px; word-break:break-all; margin-bottom:3px;
  }
  .history-date{ font-family:var(--mono); font-size:11px; color:var(--text-dim); }
  .history-actions{ display:flex; flex-direction:column; gap:6px; flex-shrink:0; }

  /* MK6 v1.2.0: Warteschlange je Drucker */
  .queue-icon{
    position:relative; cursor:pointer; width:30px; height:30px; border-radius:6px;
    display:flex; align-items:center; justify-content:center;
    border:1px solid var(--border); background:#1b2027;
  }
  .queue-icon:hover{ border-color:var(--accent); }
  .queue-icon svg{ width:16px; height:16px; fill:var(--text-dim); }
  .queue-icon:hover svg{ fill:var(--accent); }
  .queue-badge{
    position:absolute; top:-6px; right:-6px; min-width:16px; height:16px; padding:0 4px;
    border-radius:8px; background:var(--accent); color:#12100c; font-size:10px;
    font-weight:700; font-family:var(--mono); display:flex; align-items:center; justify-content:center;
  }
  .history-modal-tools{
    display:flex; justify-content:flex-end; margin:0 0 10px 0; gap:8px;
  }
  .queue-item{ align-items:center; }
  .queue-order-btns{ display:flex; flex-direction:column; gap:2px; flex-shrink:0; }
  .queue-order-btns .btn-mini{ padding:2px 7px; line-height:1; }
  .file-btn{ display:inline-block; }
  /* v2.1.0: Drop-Zone oben im Warteschlangen-Modal (Drag & Drop-Upload,
     analog zur Drop-Zone auf der Drucker-Kachel selbst) */
  .queue-drop-zone{ margin-top:0; margin-bottom:14px; }
  .queue-drop-zone .file-btn{ margin-top:4px; }
</style>
</head>
<body>

<header>
  <h1>Drucker<span>Dashboard</span> <span class="ver-badge" id="verBadge"></span></h1>
  <!-- v2.3.0: Bedien-Modus (Standard) - Drucker-/Raum-Verwaltung, MQTT-
       Geraete-Verwaltung und Kamera-Verwaltung sind nur noch im
       Einstellungen-Modus erreichbar (siehe enterSettingsMode()/
       exitSettingsMode()); Layoutwahl und alle bisherigen Bedien-
       funktionen auf den Kacheln selbst bleiben hier. v2.4.0: KEIN
       gemeinsamer "Kameras"-Knopf mehr - externe RTSP-Kameras erscheinen
       stattdessen als eigene Kachel direkt in der (Raum-)Ansicht, siehe
       cardForCamera()/refresh(). -->
  <div style="display:flex; align-items:center; gap:14px;" id="operatorControls">
    <!-- MK6: Layout-Umschalter 1/2/3/4-spaltig, siehe setLayoutCols()/getLayoutCols() -->
    <div class="layout-switch" title="Kartenlayout" data-i18n-title="layout_switch_title">
      <button type="button" class="layout-btn" data-cols="1" onclick="setLayoutCols(1)">1</button>
      <button type="button" class="layout-btn" data-cols="2" onclick="setLayoutCols(2)">2</button>
      <button type="button" class="layout-btn" data-cols="3" onclick="setLayoutCols(3)">3</button>
      <button type="button" class="layout-btn" data-cols="4" onclick="setLayoutCols(4)">4</button>
    </div>
    <button class="btn" onclick="enterSettingsMode()">&#9881; <span data-i18n="btn_settings">Einstellungen</span></button>
  </div>
  <div style="display:none; align-items:center; gap:14px;" id="settingsModeControls">
    <button class="btn" onclick="exitSettingsMode()">&larr; <span data-i18n="btn_back_to_operation">Zur Bedienung</span></button>
    <!-- v2.5.0: hierher verschoben (vorher im "Druckverlauf"-Abschnitt
         weiter unten) - dort sah es so aus, als gehoere "Speichern" zum
         Druckverlauf, dabei speichert es dort ausschliesslich das Feld
         "Maximal gespeicherte Druckauftraege je Drucker" (siehe
         saveHistorySettings()). Funktional unveraendert. -->
    <button class="btn" onclick="saveHistorySettings()" data-i18n="btn_save">Speichern</button>
  </div>
</header>

<!-- v2.6.0: FarmBot-Feld(er) - ausserhalb der Raum-Gruppierung, da FarmBot
     keine group_id hat (siehe DashboardApp "FarmBot"-Abschnitt). Nur
     sichtbar, wenn mindestens ein FarmBot angelegt wurde, siehe
     renderFarmbotPanel(). -->
<div id="farmbotPanel"></div>

<main id="printerList"></main>

<!-- v2.3.0: Einstellungen-Modus - Drucker-/Raum-/Kamera-Verwaltung sowie
     Verlaufs-Einstellung, siehe enterSettingsMode()/refreshSettingsPanel().
     Bewusst EIGENER Bereich statt eines weiteren Modals: mehrere
     unabhaengige Listen (Drucker, Raeume, Kameras) gleichzeitig sichtbar
     zu haben erleichtert das Zuweisen von Druckern zu Raeumen. -->
<div id="settingsPanel" style="display:none;">

  <!-- v2.8.0: Sprache - siehe SUPPORTED_LANGUAGES/I18N weiter unten im
       <script>-Block. Bewusst als ERSTER Abschnitt, gut sichtbar. -->
  <div class="settings-section">
    <h2 data-i18n="settings_language_title">Sprache</h2>
    <div class="hint-text" data-i18n="settings_language_hint">
      Oberflaechensprache des Dashboards - wirkt sich sofort auf alle
      Labels, Schaltflaechen und Hinweistexte aus. Fehlermeldungen vom
      Server bleiben unabhaengig von dieser Einstellung auf Deutsch.
    </div>
    <select id="languageSelect" onchange="changeLanguage(this.value)"></select>
  </div>

  <div class="settings-section">
    <h2 data-i18n="settings_printers_title">Drucker verwalten</h2>
    <div class="hint-text" data-i18n="settings_printers_hint">
      Hinzufuegen, entfernen, einem Raum zuweisen und die Anzeige-
      Reihenfolge aendern. Die Kamera-Anzeige und alle Druckfunktionen
      bleiben im Bedien-Modus.
    </div>
    <button class="btn" onclick="openAddModal()" data-i18n="btn_add_printer">+ Drucker hinzufuegen</button>
    <div id="printerManageList" style="margin-top:14px;"></div>
  </div>

  <!-- v2.6.0: FarmBot - siehe DashboardApp-Abschnitt "FarmBot". Mehrere
       unabhaengige FarmBots moeglich, jeweils mit eigenem Namenszusatz,
       eigener Hersteller-/Familienauswahl, eigenem Arbeitstag-Fenster und
       eigener maximaler Wartezeit. -->
  <div class="settings-section">
    <h2>FarmBot</h2>
    <div class="hint-text" data-i18n="settings_farmbot_hint">
      Eigenstaendige Druckauftrags-Warteschlange(n), die automatisch einem
      gerade freien Drucker der gewaehlten Hersteller-/Familienauswahl
      zugewiesen werden - unabhaengig von der Warteschlange einzelner
      Drucker. Aktiviert erscheint je FarmBot ein eigenes Feld oberhalb
      der Drucker im Bedien-Modus.
    </div>
    <button class="btn" onclick="openAddFarmbotModal()" data-i18n="btn_add_farmbot">+ FarmBot hinzufuegen</button>
    <div id="farmbotManageList" style="margin-top:14px;"></div>
  </div>

  <div class="settings-section">
    <h2 data-i18n="settings_groups_title">Raeume / Gruppen</h2>
    <div class="hint-text" data-i18n="settings_groups_hint">
      Drucker koennen im Bedien-Modus nach Raum gruppiert angezeigt
      werden. Ein geloeschter Raum loescht KEINE Drucker - sie erscheinen
      danach unter "Ohne Raum".
    </div>
    <div class="settings-inline-form">
      <input id="newGroupName" placeholder="Name des neuen Raums (z. B. Werkstatt)" data-i18n-placeholder="placeholder_new_group_name">
      <button class="btn" onclick="createGroup()" data-i18n="btn_add_group">+ Raum anlegen</button>
    </div>
    <div id="groupsManageList" style="margin-top:10px;"></div>
  </div>

  <div class="settings-section">
    <h2 data-i18n="settings_cameras_title">Externe RTSP-Kameras</h2>
    <div class="hint-text" data-i18n="settings_cameras_hint">
      Zusaetzlich zu den Drucker-eigenen Kameras koennen beliebige weitere
      RTSP(S)-Kameras hinterlegt werden (z. B. eine Raumuebersicht) - sie
      erscheinen danach als eigene Kachel im Bedien-Modus, im zugewiesenen
      Raum (oder unter "Ohne Raum"). Bei Bedarf mit eigener Anmeldung
      (Benutzername/Passwort). Benoetigt FFmpeg (siehe README/
      LINUX-INSTALL.md), genau wie die RTSPS-Kamera der X1/P1/P2/H2/X2-Serie.
    </div>
    <button class="btn" onclick="openCameraModal()" data-i18n="btn_add_camera">+ Kamera hinzufuegen</button>
    <div id="camerasManageList" style="margin-top:14px;"></div>
  </div>

  <div class="settings-section">
    <h2 data-i18n="settings_mqtt_title">MQTT-Geraete (Sensoren/Schalter)</h2>
    <div class="hint-text" data-i18n="settings_mqtt_hint">
      Zweiter, von den Druckern unabhaengiger MQTT-Broker fuer frei
      definierte Sensoren (Anzeige eines Werts, mit Verlaufsdiagramm) und
      Schaltflaechen (senden fester An-/Aus-Nachrichten) - wahlweise je
      Drucker oder eigenstaendig (siehe "Kein Drucker" beim Anlegen).
    </div>

    <div class="field-label" style="margin-top:10px;" data-i18n="field_broker_settings">Broker-Einstellungen</div>
    <div class="checkbox-row">
      <input type="checkbox" id="mq_enabled">
      <label style="margin:0;" data-i18n="label_enabled">Aktiviert</label>
    </div>
    <label data-i18n="label_broker_address">Broker-Adresse</label>
    <input id="mq_host" placeholder="192.168.1.5">
    <label data-i18n="label_port">Port</label>
    <input id="mq_port" placeholder="1883">
    <label data-i18n="label_username_optional">Benutzername (optional)</label>
    <input id="mq_user" placeholder="">
    <label data-i18n="label_password_optional_unchanged">Passwort (optional, leer lassen = unveraendert)</label>
    <input id="mq_pass" type="password" placeholder="">
    <div class="checkbox-row">
      <input type="checkbox" id="mq_tls">
      <label style="margin:0;" data-i18n="label_use_tls">TLS verwenden</label>
    </div>
    <div class="settings-inline-form" style="margin-top:4px;">
      <button class="btn" onclick="saveExtrasMqttSettings()" data-i18n="btn_save_broker_settings">Broker-Einstellungen speichern</button>
    </div>
    <div class="hint-text" id="mqttStatusHint" style="margin-top:4px;"></div>

    <div class="field-label" style="margin-top:14px;" data-i18n="field_sensors_switches">Sensoren &amp; Schalter</div>
    <button class="btn" onclick="openAddMqttExtraModal()">+ Sensor/Schalter hinzufuegen</button>
    <div id="mqttExtrasList" style="margin-top:14px;" class="hint-text">Noch keine Sensoren/Schalter angelegt.</div>
  </div>

  <div class="settings-section">
    <h2 data-i18n="settings_history_title">Druckverlauf</h2>
    <label data-i18n="label_history_max_jobs">Maximal gespeicherte Druckauftraege je Drucker (leer lassen = unbegrenzt)</label>
    <input id="historyMaxJobsInput" style="max-width:160px;" placeholder="z. B. 30">
    <div class="hint-text" data-i18n="hint_history_save">
      Wird ueber den "Speichern"-Knopf oben neben "&larr; Zur Bedienung"
      gesichert (siehe dort) - gilt nur fuer dieses Feld.
    </div>
  </div>

</div>

<!-- Modal: externe RTSP-Kamera anlegen/bearbeiten (Einstellungen-Modus) -->
<div class="modal-backdrop" id="cameraModal">
  <div class="modal">
    <h2 id="cameraModalTitle" data-i18n="modal_camera_add_title">Kamera hinzufuegen</h2>
    <div class="error-msg" id="cameraModalError"></div>

    <label data-i18n="label_name">Name</label>
    <input id="cam_name" placeholder="z. B. Werkstatt-Uebersicht">
    <label data-i18n="label_rtsp_url">RTSP(S)-URL</label>
    <input id="cam_url" placeholder="rtsp(s)://IP:Port/Pfad">
    <div class="hint-text" data-i18n="hint_camera_credentials">
      Ohne Zugangsdaten in der URL selbst - die beiden Felder unten
      werden automatisch (inkl. Sonderzeichen) eingebaut.
    </div>
    <label data-i18n="label_username_optional">Benutzername (optional)</label>
    <input id="cam_username" placeholder="nur falls die Kamera eine Anmeldung verlangt">
    <label data-i18n="label_password_optional">Passwort (optional)</label>
    <input id="cam_password" type="password" placeholder="nur falls die Kamera eine Anmeldung verlangt">
    <label data-i18n="label_room_optional">Raum (optional)</label>
    <select id="cam_group"><option value="" data-i18n="option_no_room">Kein Raum</option></select>

    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeCameraModal()" data-i18n="btn_cancel">Abbrechen</button>
      <button class="btn" onclick="submitCameraModal()" data-i18n="btn_save">Speichern</button>
    </div>
  </div>
</div>

<!-- Modal: Drucker hinzufuegen -->
<div class="modal-backdrop" id="addModal">
  <div class="modal">
    <h2 data-i18n="modal_add_printer_title">Neuen Drucker hinzufuegen</h2>
    <div class="error-msg" id="addError"></div>

    <label data-i18n="label_printer_type">Druckertyp</label>
    <select id="f_type" onchange="toggleTypeFields()">
      <option value="bambu">Bambu Lab</option>
      <option value="formlabs" data-i18n="type_formlabs">Formlabs (Drucker)</option>
      <option value="formlabs_wash">Formlabs Wash L</option>
      <option value="formlabs_cure">Formlabs Cure L</option>
      <option value="octoprint">OctoPrint</option>
      <option value="creality_k1">Creality K1</option>
      <option value="creality_k1c">Creality K1C</option>
      <option value="creality_k1max">Creality K1 Max</option>
      <option value="creality_k1se">Creality K1 SE</option>
      <option value="creality_other" data-i18n="type_creality_other">Creality (sonstiger Klipper-Drucker)</option>
      <option value="ultimaker">Ultimaker</option>
    </select>

    <label data-i18n="label_name">Name</label>
    <input id="f_name" placeholder="z. B. X1C Werkstatt">
    <label data-i18n="label_device_ip">IP-Adresse des Geraets</label>
    <input id="f_ip" placeholder="192.168.1.50">

    <div id="bambuFields">
      <label data-i18n="label_access_code">Access Code (LAN-Modus, Drucker-Display &rarr; Einstellungen)</label>
      <input id="f_code" placeholder="8-stelliger Code">
      <label data-i18n="label_serial">Seriennummer</label>
      <input id="f_serial" placeholder="z. B. 01P00A123456789">
      <label data-i18n="label_printer_family">Druckerfamilie</label>
      <select id="f_bambu_family">
        <option value="x1">X1-Serie (X1C, X1E)</option>
        <option value="a1">A1-Serie (A1, A1 Mini)</option>
        <option value="h2">H2-Serie (H2S, H2D, H2D Pro, H2C)</option>
        <option value="p1">P1-Serie (P1P, P1S)</option>
        <option value="p2">P2-Serie (P2S)</option>
        <option value="x2">X2-Serie (X2D)</option>
      </select>
      <div class="hint-text" data-i18n="hint_bambu_family">
        Bestimmt, welche Verbindungseinstellung fuer den Datei-Upload
        beim ersten Versuch benutzt wird (X1- und A1-Serie brauchen
        unterschiedliche, teils gegensaetzliche Einstellungen). Bei
        falscher Wahl wird automatisch die jeweils andere Einstellung
        im zweiten Versuch ausprobiert - der Druck funktioniert also so
        oder so, eine korrekte Auswahl spart nur einen Fehlversuch.
        Fuer die H2-, P1-, P2- und X2-Serie liegen noch keine eigenen
        Erkenntnisse vor - sie nutzen vorerst dieselbe Einstellung wie
        die X1-Serie.
      </div>
    </div>

    <div id="formlabsHint" class="hint-text" data-i18n="hint_formlabs">
      Benoetigt den lokal laufenden "PreFormServer" (Formlabs Local API,
      Teil der PreForm-Installation) - siehe README.
    </div>

    <div id="octoprintFields">
      <label data-i18n="label_api_key">API-Key</label>
      <input id="f_apikey" placeholder="OctoPrint-Einstellungen &rarr; API">
      <label data-i18n="label_port">Port</label>
      <input id="f_port" placeholder="80">
      <div class="checkbox-row">
        <input type="checkbox" id="f_https">
        <label style="margin:0;" data-i18n="label_use_https">HTTPS verwenden</label>
      </div>
      <label data-i18n="label_webcam_url_optional">Webcam-URL (optional)</label>
      <input id="f_webcam" placeholder="http://IP:8080/webcam/?action=stream">
    </div>

    <div id="crealityFields">
      <div class="hint-text" data-i18n="hint_creality_moonraker">
        Benoetigt Moonraker auf dem Drucker (bei werkseitigen K1/K1C/K1 Max/
        K1 SE muss dafuer erst per SSH "gerootet" werden) - siehe README.
      </div>
      <label data-i18n="label_api_key_optional_see_readme">API-Key (meist nicht noetig, siehe README)</label>
      <input id="f_creality_apikey" placeholder="optional">
      <label data-i18n="label_moonraker_port">Moonraker-Port</label>
      <input id="f_creality_port" placeholder="7125">
      <label data-i18n="label_webcam_url_optional">Webcam-URL (optional)</label>
      <input id="f_creality_webcam" placeholder="http://IP/webcam/?action=stream">
    </div>

    <div id="ultimakerFields">
      <div class="hint-text" data-i18n="hint_ultimaker_api">
        Nutzt die offizielle, unauthentifizierte lokale Ultimaker-API -
        kein Login/API-Key noetig, siehe README.
      </div>
      <label data-i18n="label_port_optional">Port (optional)</label>
      <input id="f_ultimaker_port" placeholder="80">
      <label data-i18n="label_webcam_url_optional">Webcam-URL (optional)</label>
      <input id="f_ultimaker_webcam" placeholder="http://IP:8080/?action=stream">
    </div>

    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeAddModal()" data-i18n="btn_cancel">Abbrechen</button>
      <button class="btn" onclick="submitAdd()" data-i18n="btn_add">Hinzufuegen</button>
    </div>
  </div>
</div>

<!-- Modal: MQTT-Sensor/Schalter anlegen/bearbeiten (Einstellungen-Modus).
     v2.5.1: NUR noch dieses eine Formular ist ein Modal - die Broker-
     Einstellungen und die Liste vorhandener Eintraege sitzen seitdem
     inline im "MQTT-Geraete"-Abschnitt des Einstellungen-Modus, genau wie
     bei "Drucker verwalten"/"Raeume"/"Externe RTSP-Kameras" (vorher
     steckte der GESAMTE MQTT-Bereich - Broker-Einstellungen, Formular UND
     Liste - hinter einem einzelnen "MQTT-Geraete verwalten"-Knopf in
     einem grossen Modal, als einziger Abschnitt mit diesem abweichenden
     Bedienkonzept). Entspricht strukturell #cameraModal. -->
<div class="modal-backdrop" id="mqttExtraModal">
  <div class="modal mqtt-modal">
    <h2 id="mqttExtraModalTitle">Sensor/Schalter hinzufuegen</h2>
    <div class="error-msg" id="mqttError"></div>

    <label>Drucker</label>
    <select id="mq_printer"></select>
    <div class="hint-text" style="margin-top:-4px;">
      "Kein Drucker (eigenstaendig)" legt einen Sensor/Schalter an, der zu
      keinem Drucker gehoert - er erscheint danach als eigene Kachel im
      Bedien-Modus.
    </div>
    <label>Art</label>
    <select id="mq_kind" onchange="toggleMqttKindFields()">
      <option value="sensor">Sensor (Anzeige)</option>
      <option value="switch">Schalter (Ein/Aus)</option>
    </select>
    <label>Bezeichnung</label>
    <input id="mq_label" placeholder="z. B. Temperatur Werkstatt">

    <div id="mqttSensorFields">
      <label>MQTT-Topic</label>
      <input id="mq_topic" placeholder="home/werkstatt/temperature">
      <label>Einheit (optional)</label>
      <input id="mq_unit" placeholder="&deg;C">
      <label>Anzeigebereich</label>
      <select id="mq_display">
        <option value="generic">Generisch (eigener Bereich "Sensoren &amp; Schalter")</option>
        <option value="temperature">Bei Temperaturen anzeigen (wie Duese/Bett/Kammer)</option>
        <option value="humidity">Bei Luftfeuchtigkeit anzeigen (wie AMS-Feuchte)</option>
      </select>
      <div class="hint-text" style="margin-top:-4px;">
        Zeigt seit v2.5.1 IMMER ein Verlaufsdiagramm - diese Auswahl
        entscheidet nur noch, WO der Sensor angezeigt wird.
      </div>
    </div>
    <div id="mqttSwitchFields" style="display:none;">
      <label>Befehls-Topic</label>
      <input id="mq_cmd_topic" placeholder="home/werkstatt/licht/set">
      <label>Payload "Ein"</label>
      <input id="mq_payload_on" placeholder="ON">
      <label>Payload "Aus"</label>
      <input id="mq_payload_off" placeholder="OFF">
    </div>

    <div class="field-label" style="margin-top:14px;">
      Zuletzt vom Broker empfangene Topics (anklicken, um das Topic-Feld zu uebernehmen)
    </div>
    <div id="mqttDiscoveredList" class="mqtt-discovered-list hint-text">
      Noch keine Nachrichten vom Broker empfangen.
    </div>

    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeMqttExtraModal()">Abbrechen</button>
      <button class="btn" id="mqttSubmitBtn" onclick="submitMqttExtra()">Hinzufuegen</button>
    </div>
  </div>
</div>

<!-- Modal: Kamera -->
<div class="modal-backdrop cam-modal" id="camModal">
  <span class="cam-close" onclick="closeCam()">&times;</span>
  <div class="modal">
    <img id="camImg" src="">
    <div id="camError" class="hint-text" style="display:none; padding:16px; max-width:480px;"></div>
  </div>
</div>

<!-- Modal: AMS-Zuordnung pruefen/korrigieren vor dem Drucken -->
<div class="modal-backdrop" id="amsModal">
  <div class="modal ams-modal">
    <h2 data-i18n="modal_ams_title">AMS-Zuordnung pruefen</h2>
    <div class="file-name" id="amsModalFilename" style="margin-bottom:16px;"></div>
    <div id="amsModalRows"></div>
    <div class="ams-progress-wrap" id="amsProgressWrap" style="display:none;">
      <div class="ams-progress-track"><div class="ams-progress-bar" id="amsProgressBar" style="width:0%"></div></div>
      <div class="ams-progress-label" id="amsProgressLabel"></div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-ghost" id="amsModalCancelBtn" onclick="cancelAmsModal()" data-i18n="btn_cancel">Abbrechen</button>
      <button class="btn" id="amsModalConfirmBtn" onclick="confirmAmsModal()" data-i18n="btn_start_print">Drucken starten</button>
    </div>
  </div>
</div>

<!-- Modal: Druckauftrags-Verlauf (MK6) -->
<div class="modal-backdrop" id="historyModal">
  <div class="modal history-modal">
    <h2 data-i18n="modal_history_title">Druckauftrags-Verlauf</h2>
    <!-- v2.2.4: Schliessen-Schaltflaeche jetzt OBEN statt unten - bei
         langen Verlaufslisten war der Knopf am Ende der (langen) Liste
         nur nach vollstaendigem Durchscrollen erreichbar. Siehe auch
         .history-modal{display:flex...}/.history-modal-scroll weiter
         unten im CSS: nur die Liste selbst scrollt jetzt, Kopf- und
         Aktionsbereich bleiben stets sichtbar. -->
    <div class="modal-actions modal-actions-top">
      <button class="btn btn-ghost" onclick="closeHistoryModal()" data-i18n="btn_close">Schliessen</button>
    </div>
    <div class="history-modal-tools">
      <button class="btn-mini" id="historySortBtn" onclick="toggleHistorySort()" data-i18n="sort_newest_first">Sortierung: Neueste zuerst</button>
    </div>
    <div id="historyModalBody" class="history-modal-scroll"></div>
  </div>
</div>

<!-- Modal: Warteschlange (MK6 v1.2.0) -->
<div class="modal-backdrop" id="queueModal">
  <div class="modal history-modal">
    <h2 data-i18n="modal_queue_title">Warteschlange</h2>
    <!-- v2.2.4: siehe Kommentar bei historyModal oben - Schliessen UND
         "Druckraum leer" sind jetzt OBEN, bleiben also bei langen
         Warteschlangen ohne Scrollen erreichbar. -->
    <div class="modal-actions modal-actions-top">
      <button class="btn btn-ghost" onclick="closeQueueModal()" data-i18n="btn_close">Schliessen</button>
      <button class="btn" id="queueSendNextBtn" onclick="sendNextQueued(queueModalPrinterId)" data-i18n="btn_bed_empty_send_next">Druckraum leer - naechsten senden</button>
    </div>
    <!-- v2.0.1: Hinweistext + Deaktivierung siehe updateQueueSendButtonState() -->
    <div class="hint-text" id="queueSendHint"></div>
    <!-- v2.1.0: Datei kann per Drag & Drop hierher gezogen werden -
         genau wie auf die Drucker-Kachel selbst (dzDrop()/dzDropUltimaker()) -
         oder ueber den Datei-Auswahl-Button darin. -->
    <div class="drop-zone queue-drop-zone" id="queueDropZone"
         ondragover="dzDragOver(event)"
         ondragleave="dzDragLeave(event)"
         ondrop="dzDropQueue(event)">
      <span data-i18n="dz_drop_to_queue">Datei hier ablegen, um sie in die Warteschlange zu legen</span>
      <div class="dz-hint">
        <span data-i18n="dz_or">oder</span>
        <label class="btn-mini file-btn">
          <span data-i18n="dz_choose_file">Datei auswaehlen</span>
          <input type="file" style="display:none" onchange="addFileToQueue(queueModalPrinterId, this)">
        </label>
      </div>
    </div>
    <div id="queueModalBody" class="history-modal-scroll"></div>
  </div>
</div>

<!-- Modal: Auftrag einem anderen Drucker zuweisen (MK6 v1.2.0) -->
<div class="modal-backdrop" id="assignModal">
  <div class="modal">
    <h2 data-i18n="modal_assign_title">Auftrag zuweisen</h2>
    <label data-i18n="label_target_printer">Ziel-Drucker</label>
    <select id="assignTargetSelect"></select>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeAssignModal()" data-i18n="btn_cancel">Abbrechen</button>
      <button class="btn" onclick="confirmAssign()" data-i18n="btn_assign">Zuweisen</button>
    </div>
  </div>
</div>

<!-- v2.6.0: Modal: FarmBot-Warteschlange (Liste der Auftraege, die auf
     Zuweisung an einen freien Drucker warten) - Aufbau bewusst identisch
     zum Warteschlangen-Modal eines einzelnen Druckers (queueModal), ABER
     ohne manuelle Umsortier-Pfeile, da die Reihenfolge hier IMMER
     automatisch berechnet wird (siehe DashboardApp._reorder_farmbot_queue()). -->
<div class="modal-backdrop" id="farmbotQueueModal">
  <div class="modal history-modal">
    <h2 id="farmbotQueueModalTitle">FarmBot-Warteschlange</h2>
    <div class="modal-actions modal-actions-top">
      <button class="btn btn-ghost" onclick="closeFarmbotQueueModal()" data-i18n="btn_close">Schliessen</button>
      <button class="btn" id="farmbotQueueNextBtn" onclick="farmbotStartNext(farmbotQueueModalId)" data-i18n="btn_start_next_print">Naechsten Druck starten</button>
    </div>
    <div class="hint-text" id="farmbotQueueHint"></div>
    <!-- v2.7.0: haendische Umsortierung per ▲/▼ moeglich (siehe
         moveFarmbotQueueEntry()) - wird beim naechsten Datei-Upload
         automatisch wieder ueberschrieben. -->
    <div class="hint-text" data-i18n="hint_farmbot_manual_reorder">
      Reihenfolge laesst sich per ▲/▼ haendisch aendern - bei der
      naechsten hochgeladenen Datei wird automatisch wieder umsortiert.
    </div>
    <div class="drop-zone queue-drop-zone" id="farmbotQueueDropZone"
         ondragover="dzDragOver(event)"
         ondragleave="dzDragLeave(event)"
         ondrop="farmbotDzDropIntoModal(event)">
      <span data-i18n="dz_drop_to_farmbot_queue">Datei hier ablegen, um sie dieser FarmBot-Warteschlange hinzuzufuegen</span>
      <div class="dz-hint">
        <span data-i18n="dz_or">oder</span>
        <label class="btn-mini file-btn">
          <span data-i18n="dz_choose_file">Datei auswaehlen</span>
          <input type="file" style="display:none" onchange="addFileToFarmbotQueue(farmbotQueueModalId, this)">
        </label>
      </div>
    </div>
    <div id="farmbotQueueModalBody" class="history-modal-scroll"></div>
  </div>
</div>

<!-- v2.6.0: Modal: Kamera-Bestaetigung "Druckraum frei", bevor FarmBot
     einen Auftrag auf einem Drucker startet, der zuvor bereits etwas
     fertig gedruckt hat (siehe DashboardApp._update_bed_confirm_flags()/
     pick_farmbot_job() - auf ausdruecklichen Nutzerwunsch: "Nur wenn der
     Drucker zuvor etwas fertig gedruckt hat"). -->
<div class="modal-backdrop" id="farmbotBedModal">
  <div class="modal">
    <h2 data-i18n="modal_farmbot_bed_title">Druckraum freigeben</h2>
    <div class="hint-text" id="farmbotBedModalHint"></div>
    <img id="farmbotBedCamImg" src="" style="width:100%; border-radius:8px; background:#000; margin:10px 0;">
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="farmbotBedOtherPrinter()" data-i18n="btn_other_printer">Anderer Drucker</button>
      <button class="btn" onclick="farmbotBedConfirmFree()" data-i18n="btn_bed_free">Druckraum frei</button>
    </div>
  </div>
</div>

<!-- v2.6.0: Modal: FarmBot anlegen/bearbeiten (Einstellungen-Modus) -
     Aufbau bewusst angelehnt an addModal (Hersteller-/Familienauswahl
     identisch zum Anlegen eines Druckers), siehe FARMBOT_MANUFACTURERS. -->
<div class="modal-backdrop" id="farmbotModal">
  <div class="modal">
    <h2 id="farmbotModalTitle">FarmBot hinzufuegen</h2>
    <div class="error-msg" id="farmbotModalError"></div>

    <label data-i18n="label_name_suffix_optional">Namenszusatz (optional)</label>
    <input id="fb_name_suffix" placeholder="z. B. Werkstatt">
    <div class="checkbox-row">
      <input type="checkbox" id="fb_enabled" checked>
      <label style="margin:0;" data-i18n="label_enabled">Aktiviert</label>
    </div>

    <label data-i18n="label_manufacturer">Hersteller</label>
    <select id="fb_manufacturer" onchange="toggleFarmbotManufacturerFields()">
      <option value="bambu">Bambu Lab</option>
      <option value="ultimaker">Ultimaker</option>
    </select>

    <div id="farmbotBambuFields">
      <label data-i18n="label_printer_family">Druckerfamilie</label>
      <select id="fb_bambu_family">
        <option value="x1">X1-Serie (X1C, X1E)</option>
        <option value="a1">A1-Serie (A1, A1 Mini)</option>
        <option value="h2">H2-Serie (H2S, H2D, H2D Pro, H2C)</option>
        <option value="p1">P1-Serie (P1P, P1S)</option>
        <option value="p2">P2-Serie (P2S)</option>
        <option value="x2">X2-Serie (X2D)</option>
      </select>
    </div>
    <div class="hint-text" id="farmbotUltimakerHint" style="display:none;" data-i18n="hint_farmbot_ultimaker">
      Es werden nur bereits mit dem Dashboard gekoppelte Ultimaker-Drucker
      beruecksichtigt (siehe "Drucker verwalten").
    </div>

    <label data-i18n="label_workday_from">Arbeitstag von</label>
    <input id="fb_work_start" placeholder="08:00">
    <label data-i18n="label_workday_to">Arbeitstag bis</label>
    <input id="fb_work_end" placeholder="18:00">
    <label data-i18n="label_max_queue_days">Maximale Wartezeit in der Warteschlange (Tage)</label>
    <input id="fb_max_queue_days" placeholder="3">
    <div class="hint-text" data-i18n="hint_max_queue_days">
      Auftraege, die diese Wartezeit erreichen, werden bei der naechsten
      automatischen Neuberechnung der Reihenfolge unabhaengig von ihrer
      Druckdauer vorrangig abgearbeitet.
    </div>

    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeFarmbotModal()" data-i18n="btn_cancel">Abbrechen</button>
      <button class="btn" onclick="submitFarmbotModal()" data-i18n="btn_save">Speichern</button>
    </div>
  </div>
</div>

<!-- Toasts (unabhaengig vom Drucker-Grid, ueberleben refresh()) -->
<div class="toast-container" id="toastContainer"></div>

<script>
// v2.8.0: Mehrsprachige Oberflaeche (de/en/fr/es/zh/ja/tr) - siehe
// SUPPORTED_LANGUAGES im Python-Teil. Es wird NUR die Oberflaeche
// (Labels, Schaltflaechen, Hinweistexte) uebersetzt; Fehlermeldungen vom
// Server (jsonify({"error": ...})) bleiben unabhaengig von dieser
// Einstellung auf Deutsch (siehe README, Abschnitt "Mehrsprachigkeit").
// t(key, vars) liefert den uebersetzten Text fuer die aktuell aktive
// Sprache (currentLang, siehe changeLanguage()); vars erlaubt einfache
// {platzhalter}-Ersetzung fuer Texte mit eingebetteten Werten (siehe
// z. B. farmbot_sub_bambu). Fehlt ein Key in der Zielsprache, wird auf
// Deutsch zurueckgefallen (und, falls auch das fehlt, der Key selbst
// angezeigt) - so bleibt die Oberflaeche auch bei einer unvollstaendigen
// Uebersetzung benutzbar.
let currentLang = 'de';

const I18N = {
de: {
  layout_switch_title: "Kartenlayout",
  btn_settings: "Einstellungen",
  btn_back_to_operation: "Zur Bedienung",
  btn_save: "Speichern",
  settings_language_title: "Sprache",
  settings_language_hint: "Oberflaechensprache des Dashboards - wirkt sich sofort auf alle Labels, Schaltflaechen und Hinweistexte aus. Fehlermeldungen vom Server bleiben unabhaengig von dieser Einstellung auf Deutsch.",
  settings_printers_title: "Drucker verwalten",
  settings_printers_hint: "Hinzufuegen, entfernen, einem Raum zuweisen und die Anzeige-Reihenfolge aendern. Die Kamera-Anzeige und alle Druckfunktionen bleiben im Bedien-Modus.",
  btn_add_printer: "+ Drucker hinzufuegen",
  settings_farmbot_hint: "Eigenstaendige Druckauftrags-Warteschlange(n), die automatisch einem gerade freien Drucker der gewaehlten Hersteller-/Familienauswahl zugewiesen werden - unabhaengig von der Warteschlange einzelner Drucker. Aktiviert erscheint je FarmBot ein eigenes Feld oberhalb der Drucker im Bedien-Modus.",
  btn_add_farmbot: "+ FarmBot hinzufuegen",
  settings_groups_title: "Raeume / Gruppen",
  settings_groups_hint: "Drucker koennen im Bedien-Modus nach Raum gruppiert angezeigt werden. Ein geloeschter Raum loescht KEINE Drucker - sie erscheinen danach unter \"Ohne Raum\".",
  placeholder_new_group_name: "Name des neuen Raums (z. B. Werkstatt)",
  btn_add_group: "+ Raum anlegen",
  settings_cameras_title: "Externe RTSP-Kameras",
  settings_cameras_hint: "Zusaetzlich zu den Drucker-eigenen Kameras koennen beliebige weitere RTSP(S)-Kameras hinterlegt werden (z. B. eine Raumuebersicht) - sie erscheinen danach als eigene Kachel im Bedien-Modus, im zugewiesenen Raum (oder unter \"Ohne Raum\"). Bei Bedarf mit eigener Anmeldung (Benutzername/Passwort). Benoetigt FFmpeg (siehe README/LINUX-INSTALL.md), genau wie die RTSPS-Kamera der X1/P1/P2/H2/X2-Serie.",
  btn_add_camera: "+ Kamera hinzufuegen",
  settings_mqtt_title: "MQTT-Geraete (Sensoren/Schalter)",
  settings_mqtt_hint: "Zweiter, von den Druckern unabhaengiger MQTT-Broker fuer frei definierte Sensoren (Anzeige eines Werts, mit Verlaufsdiagramm) und Schaltflaechen (senden fester An-/Aus-Nachrichten) - wahlweise je Drucker oder eigenstaendig (siehe \"Kein Drucker\" beim Anlegen).",
  field_broker_settings: "Broker-Einstellungen",
  label_enabled: "Aktiviert",
  label_broker_address: "Broker-Adresse",
  label_port: "Port",
  label_username_optional: "Benutzername (optional)",
  label_password_optional_unchanged: "Passwort (optional, leer lassen = unveraendert)",
  label_use_tls: "TLS verwenden",
  btn_save_broker_settings: "Broker-Einstellungen speichern",
  field_sensors_switches: "Sensoren & Schalter",
  settings_history_title: "Druckverlauf",
  label_history_max_jobs: "Maximal gespeicherte Druckauftraege je Drucker (leer lassen = unbegrenzt)",
  hint_history_save: "Wird ueber den \"Speichern\"-Knopf oben neben \"← Zur Bedienung\" gesichert (siehe dort) - gilt nur fuer dieses Feld.",
  modal_camera_add_title: "Kamera hinzufuegen",
  label_name: "Name",
  label_rtsp_url: "RTSP(S)-URL",
  hint_camera_credentials: "Ohne Zugangsdaten in der URL selbst - die beiden Felder unten werden automatisch (inkl. Sonderzeichen) eingebaut.",
  label_password_optional: "Passwort (optional)",
  label_room_optional: "Raum (optional)",
  option_no_room: "Kein Raum",
  btn_cancel: "Abbrechen",
  modal_add_printer_title: "Neuen Drucker hinzufuegen",
  label_printer_type: "Druckertyp",
  type_formlabs: "Formlabs (Drucker)",
  type_creality_other: "Creality (sonstiger Klipper-Drucker)",
  label_device_ip: "IP-Adresse des Geraets",
  label_access_code: "Access Code (LAN-Modus, Drucker-Display → Einstellungen)",
  label_serial: "Seriennummer",
  label_printer_family: "Druckerfamilie",
  hint_bambu_family: "Bestimmt, welche Verbindungseinstellung fuer den Datei-Upload beim ersten Versuch benutzt wird (X1- und A1-Serie brauchen unterschiedliche, teils gegensaetzliche Einstellungen). Bei falscher Wahl wird automatisch die jeweils andere Einstellung im zweiten Versuch ausprobiert - der Druck funktioniert also so oder so, eine korrekte Auswahl spart nur einen Fehlversuch. Fuer die H2-, P1-, P2- und X2-Serie liegen noch keine eigenen Erkenntnisse vor - sie nutzen vorerst dieselbe Einstellung wie die X1-Serie.",
  hint_formlabs: "Benoetigt den lokal laufenden \"PreFormServer\" (Formlabs Local API, Teil der PreForm-Installation) - siehe README.",
  label_api_key: "API-Key",
  label_use_https: "HTTPS verwenden",
  label_webcam_url_optional: "Webcam-URL (optional)",
  hint_creality_moonraker: "Benoetigt Moonraker auf dem Drucker (bei werkseitigen K1/K1C/K1 Max/K1 SE muss dafuer erst per SSH \"gerootet\" werden) - siehe README.",
  label_api_key_optional_see_readme: "API-Key (meist nicht noetig, siehe README)",
  label_moonraker_port: "Moonraker-Port",
  hint_ultimaker_api: "Nutzt die offizielle, unauthentifizierte lokale Ultimaker-API - kein Login/API-Key noetig, siehe README.",
  label_port_optional: "Port (optional)",
  btn_add: "Hinzufuegen",
  modal_ams_title: "AMS-Zuordnung pruefen",
  btn_start_print: "Drucken starten",
  modal_history_title: "Druckauftrags-Verlauf",
  btn_close: "Schliessen",
  sort_newest_first: "Sortierung: Neueste zuerst",
  modal_queue_title: "Warteschlange",
  btn_bed_empty_send_next: "Druckraum leer - naechsten senden",
  dz_drop_to_queue: "Datei hier ablegen, um sie in die Warteschlange zu legen",
  dz_or: "oder",
  dz_choose_file: "Datei auswaehlen",
  modal_assign_title: "Auftrag zuweisen",
  label_target_printer: "Ziel-Drucker",
  btn_assign: "Zuweisen",
  btn_start_next_print: "Naechsten Druck starten",
  hint_farmbot_manual_reorder: "Reihenfolge laesst sich per ▲/▼ haendisch aendern - bei der naechsten hochgeladenen Datei wird automatisch wieder umsortiert.",
  dz_drop_to_farmbot_queue: "Datei hier ablegen, um sie dieser FarmBot-Warteschlange hinzuzufuegen",
  modal_farmbot_bed_title: "Druckraum freigeben",
  btn_other_printer: "Anderer Drucker",
  btn_bed_free: "Druckraum frei",
  label_name_suffix_optional: "Namenszusatz (optional)",
  label_manufacturer: "Hersteller",
  hint_farmbot_ultimaker: "Es werden nur bereits mit dem Dashboard gekoppelte Ultimaker-Drucker beruecksichtigt (siehe \"Drucker verwalten\").",
  label_workday_from: "Arbeitstag von",
  label_workday_to: "Arbeitstag bis",
  label_max_queue_days: "Maximale Wartezeit in der Warteschlange (Tage)",
  hint_max_queue_days: "Auftraege, die diese Wartezeit erreichen, werden bei der naechsten automatischen Neuberechnung der Reihenfolge unabhaengig von ihrer Druckdauer vorrangig abgearbeitet.",
  temp_nozzle: "Duese",
  temp_bed: "Bett",
  temp_chamber: "Kammer",
  tooltip_show_camera: "Kamera anzeigen",
  tooltip_history: "Druckauftrags-Verlauf",
  ams_filament_title: "AMS / Filament",
  empty_no_printers: "Noch keine Drucker hinterlegt.",
  btn_add_printer_empty: "+ Drucker hinzufuegen",
  dz_hint_developer_mode: "Erfordert Developer Mode / LAN-Modus am Drucker",
  dz_hint_cura_export: "Export aus Cura, z. B. ueber \"Datei speichern\"",
  camera_type_badge: "Kamera",
  switch_type_badge: "Schalter",
  sensor_type_badge: "Sensor",
  btn_on: "Ein",
  btn_off: "Aus",
  hint_octoprint_no_chamber: "OctoPrint liefert keine Kammertemperatur / kein AMS-Aequivalent.",
  hint_creality_chamber: "Ueber Moonraker angebunden. Kammertemperatur nur sichtbar, falls im Klipper-Setup ein entsprechender Sensor konfiguriert ist.",
  hint_ultimaker_no_chamber: "Ultimaker-Desktopdrucker haben keinen Kammertemperatursensor.",
  title_progress_thumb: "Vorschau des aktuellen/letzten Druckauftrags",
  farmbot_sub_ultimaker: "Ultimaker",
  farmbot_sub_bambu: "Bambu Lab &middot; {family}",
  farmbot_sub_suffix: " &middot; Arbeitstag {start}&ndash;{end} Uhr &middot; max. {days} Tage Wartezeit",
  farmbot_fits_text: "{fits} von {total} Auftraegen koennen rechnerisch heute noch gestartet werden (der jeweils letzte darf dabei unbeaufsichtigt ueber den Feierabend hinaus weiterdrucken).",
  farmbot_queue_empty: "Warteschlange ist leer.",
  farmbot_queue_waiting_badge: "{count} wartend",
  btn_farmbot_queue: "Warteschlange",
  farmbot_dz_gcode: "Fertig gesclicte .gcode-Datei hier ablegen",
  farmbot_dz_gcode3mf: "Fertig gesclicte .gcode.3mf-Datei hier ablegen",
  btn_farmbot_start_next: "Naechsten Druck starten",
  btn_edit: "Bearbeiten",
  btn_delete: "Loeschen",
  btn_show: "Anzeigen",
  btn_remove: "Entfernen",
  btn_enable: "Aktivieren",
  btn_disable: "Deaktivieren",
  empty_no_farmbots: "Noch kein FarmBot angelegt.",
  farmbot_disabled_hint: "(deaktiviert)",
  farmbot_manage_sub_suffix: " &middot; Arbeitstag {start}&ndash;{end} Uhr &middot; max. {days} Tage",
  sort_alpha: "Sortierung: A-Z",
  history_empty: "Noch keine Druckauftraege ueber das Dashboard gesendet.",
  farmbot_queue_modal_title_suffix: " - Warteschlange",
  farmbot_default_name: "FarmBot",
  loading_generic: "Wird geladen ...",
  field_current_file: "Aktuelle Datei",
  btn_abort_print: "Abbrechen",
  confirm_abort_print: "Laufenden Druck wirklich abbrechen? Dies kann nicht rueckgaengig gemacht werden.",
  toast_abort_sent: "Abbrechen angefordert.",
  toast_abort_failed: "Abbrechen fehlgeschlagen.",
  toast_abort_network_error: "Netzwerkfehler beim Abbrechen."
},
en: {
  layout_switch_title: "Card layout",
  btn_settings: "Settings",
  btn_back_to_operation: "Back to operation",
  btn_save: "Save",
  settings_language_title: "Language",
  settings_language_hint: "Interface language of the dashboard - takes effect immediately on all labels, buttons and hint texts. Error messages from the server stay in German regardless of this setting.",
  settings_printers_title: "Manage printers",
  settings_printers_hint: "Add, remove, assign to a room and change the display order. The camera view and all print functions remain in operation mode.",
  btn_add_printer: "+ Add printer",
  settings_farmbot_hint: "Standalone print-job queue(s) that are automatically assigned to a currently free printer matching the selected manufacturer/family - independent of any individual printer's own queue. When enabled, each FarmBot shows its own tile above the printers in operation mode.",
  btn_add_farmbot: "+ Add FarmBot",
  settings_groups_title: "Rooms / groups",
  settings_groups_hint: "Printers can be shown grouped by room in operation mode. Deleting a room does NOT delete any printers - they then appear under \"No room\".",
  placeholder_new_group_name: "Name of the new room (e.g. workshop)",
  btn_add_group: "+ Create room",
  settings_cameras_title: "External RTSP cameras",
  settings_cameras_hint: "In addition to the printers' built-in cameras, any number of other RTSP(S) cameras can be added (e.g. a room overview) - they then appear as their own tile in operation mode, in the assigned room (or under \"No room\"). Optionally with its own login (username/password). Requires FFmpeg (see README/LINUX-INSTALL.md), just like the RTSPS camera of the X1/P1/P2/H2/X2 series.",
  btn_add_camera: "+ Add camera",
  settings_mqtt_title: "MQTT devices (sensors/switches)",
  settings_mqtt_hint: "A second MQTT broker, independent of the printers, for freely defined sensors (display of a value, with a history chart) and switches (sending fixed on/off messages) - either per printer or standalone (see \"No printer\" when creating one).",
  field_broker_settings: "Broker settings",
  label_enabled: "Enabled",
  label_broker_address: "Broker address",
  label_port: "Port",
  label_username_optional: "Username (optional)",
  label_password_optional_unchanged: "Password (optional, leave blank = unchanged)",
  label_use_tls: "Use TLS",
  btn_save_broker_settings: "Save broker settings",
  field_sensors_switches: "Sensors & switches",
  settings_history_title: "Print history",
  label_history_max_jobs: "Maximum stored print jobs per printer (leave blank = unlimited)",
  hint_history_save: "Saved via the \"Save\" button above next to \"← Back to operation\" (see there) - applies only to this field.",
  modal_camera_add_title: "Add camera",
  label_name: "Name",
  label_rtsp_url: "RTSP(S) URL",
  hint_camera_credentials: "Without credentials in the URL itself - the two fields below are inserted automatically (including special characters).",
  label_password_optional: "Password (optional)",
  label_room_optional: "Room (optional)",
  option_no_room: "No room",
  btn_cancel: "Cancel",
  modal_add_printer_title: "Add new printer",
  label_printer_type: "Printer type",
  type_formlabs: "Formlabs (printer)",
  type_creality_other: "Creality (other Klipper printer)",
  label_device_ip: "IP address of the device",
  label_access_code: "Access code (LAN mode, printer display → settings)",
  label_serial: "Serial number",
  label_printer_family: "Printer family",
  hint_bambu_family: "Determines which connection setting is used for the first file-upload attempt (the X1 and A1 series need different, partly opposite settings). If the wrong one is chosen, the other setting is automatically tried on the second attempt - printing works either way, a correct choice only saves one failed attempt. There is no dedicated data yet for the H2, P1, P2 and X2 series - they currently use the same setting as the X1 series.",
  hint_formlabs: "Requires the locally running \"PreFormServer\" (Formlabs Local API, part of the PreForm installation) - see README.",
  label_api_key: "API key",
  label_use_https: "Use HTTPS",
  label_webcam_url_optional: "Webcam URL (optional)",
  hint_creality_moonraker: "Requires Moonraker on the printer (factory K1/K1C/K1 Max/K1 SE units must first be \"rooted\" via SSH) - see README.",
  label_api_key_optional_see_readme: "API key (usually not needed, see README)",
  label_moonraker_port: "Moonraker port",
  hint_ultimaker_api: "Uses the official, unauthenticated local Ultimaker API - no login/API key needed, see README.",
  label_port_optional: "Port (optional)",
  btn_add: "Add",
  modal_ams_title: "Check AMS assignment",
  btn_start_print: "Start print",
  modal_history_title: "Print history",
  btn_close: "Close",
  sort_newest_first: "Sort: newest first",
  modal_queue_title: "Queue",
  btn_bed_empty_send_next: "Bed empty - send next",
  dz_drop_to_queue: "Drop a file here to add it to the queue",
  dz_or: "or",
  dz_choose_file: "Choose file",
  modal_assign_title: "Assign job",
  label_target_printer: "Target printer",
  btn_assign: "Assign",
  btn_start_next_print: "Start next print",
  hint_farmbot_manual_reorder: "The order can be changed manually with ▲/▼ - it will be re-sorted automatically again the next time a file is uploaded.",
  dz_drop_to_farmbot_queue: "Drop a file here to add it to this FarmBot's queue",
  modal_farmbot_bed_title: "Free up print bed",
  btn_other_printer: "Other printer",
  btn_bed_free: "Bed free",
  label_name_suffix_optional: "Name suffix (optional)",
  label_manufacturer: "Manufacturer",
  hint_farmbot_ultimaker: "Only Ultimaker printers already paired with the dashboard are considered (see \"Manage printers\").",
  label_workday_from: "Workday from",
  label_workday_to: "Workday to",
  label_max_queue_days: "Maximum wait time in the queue (days)",
  hint_max_queue_days: "Jobs that reach this wait time are processed with priority, regardless of print duration, the next time the order is recalculated automatically.",
  temp_nozzle: "Nozzle",
  temp_bed: "Bed",
  temp_chamber: "Chamber",
  tooltip_show_camera: "Show camera",
  tooltip_history: "Print history",
  ams_filament_title: "AMS / filament",
  empty_no_printers: "No printers added yet.",
  btn_add_printer_empty: "+ Add printer",
  dz_hint_developer_mode: "Requires Developer Mode / LAN mode on the printer",
  dz_hint_cura_export: "Exported from Cura, e.g. via \"Save to file\"",
  camera_type_badge: "Camera",
  switch_type_badge: "Switch",
  sensor_type_badge: "Sensor",
  btn_on: "On",
  btn_off: "Off",
  hint_octoprint_no_chamber: "OctoPrint does not provide a chamber temperature / no AMS equivalent.",
  hint_creality_chamber: "Connected via Moonraker. Chamber temperature only visible if a corresponding sensor is configured in the Klipper setup.",
  hint_ultimaker_no_chamber: "Ultimaker desktop printers have no chamber temperature sensor.",
  title_progress_thumb: "Preview of the current/last print job",
  farmbot_sub_ultimaker: "Ultimaker",
  farmbot_sub_bambu: "Bambu Lab &middot; {family}",
  farmbot_sub_suffix: " &middot; Workday {start}&ndash;{end} &middot; max. {days} days wait time",
  farmbot_fits_text: "{fits} of {total} jobs can theoretically still be started today (the last one may keep printing unattended beyond closing time).",
  farmbot_queue_empty: "Queue is empty.",
  farmbot_queue_waiting_badge: "{count} waiting",
  btn_farmbot_queue: "Queue",
  farmbot_dz_gcode: "Drop a sliced .gcode file here",
  farmbot_dz_gcode3mf: "Drop a sliced .gcode.3mf file here",
  btn_farmbot_start_next: "Start next print",
  btn_edit: "Edit",
  btn_delete: "Delete",
  btn_show: "Show",
  btn_remove: "Remove",
  btn_enable: "Enable",
  btn_disable: "Disable",
  empty_no_farmbots: "No FarmBot set up yet.",
  farmbot_disabled_hint: "(disabled)",
  farmbot_manage_sub_suffix: " &middot; Workday {start}&ndash;{end} &middot; max. {days} days",
  sort_alpha: "Sort: A-Z",
  history_empty: "No print jobs sent via the dashboard yet.",
  farmbot_queue_modal_title_suffix: " - Queue",
  farmbot_default_name: "FarmBot",
  loading_generic: "Loading ...",
  field_current_file: "Current file",
  btn_abort_print: "Abort",
  confirm_abort_print: "Really abort the running print? This cannot be undone.",
  toast_abort_sent: "Abort requested.",
  toast_abort_failed: "Failed to abort.",
  toast_abort_network_error: "Network error while aborting."
},
fr: {
  layout_switch_title: "Disposition des cartes",
  btn_settings: "Parametres",
  btn_back_to_operation: "Retour a l'exploitation",
  btn_save: "Enregistrer",
  settings_language_title: "Langue",
  settings_language_hint: "Langue de l'interface du tableau de bord - s'applique immediatement a tous les libelles, boutons et textes d'aide. Les messages d'erreur du serveur restent en allemand independamment de ce reglage.",
  settings_printers_title: "Gerer les imprimantes",
  settings_printers_hint: "Ajouter, supprimer, assigner a une piece et modifier l'ordre d'affichage. L'affichage camera et toutes les fonctions d'impression restent en mode exploitation.",
  btn_add_printer: "+ Ajouter une imprimante",
  settings_farmbot_hint: "File(s) d'attente de travaux d'impression autonome(s), assignee(s) automatiquement a une imprimante actuellement libre du fabricant/de la famille choisie - independamment de la file d'attente de chaque imprimante. Une fois active, chaque FarmBot affiche sa propre carte au-dessus des imprimantes en mode exploitation.",
  btn_add_farmbot: "+ Ajouter un FarmBot",
  settings_groups_title: "Pieces / groupes",
  settings_groups_hint: "Les imprimantes peuvent etre affichees groupees par piece en mode exploitation. Supprimer une piece ne supprime AUCUNE imprimante - elles apparaissent alors sous \"Sans piece\".",
  placeholder_new_group_name: "Nom de la nouvelle piece (p. ex. atelier)",
  btn_add_group: "+ Creer une piece",
  settings_cameras_title: "Cameras RTSP externes",
  settings_cameras_hint: "En plus des cameras integrees aux imprimantes, n'importe quelle autre camera RTSP(S) peut etre ajoutee (p. ex. une vue d'ensemble de la piece) - elle apparait alors comme sa propre carte en mode exploitation, dans la piece assignee (ou sous \"Sans piece\"). Avec identifiants propres si besoin (nom d'utilisateur/mot de passe). Necessite FFmpeg (voir README/LINUX-INSTALL.md), tout comme la camera RTSPS des series X1/P1/P2/H2/X2.",
  btn_add_camera: "+ Ajouter une camera",
  settings_mqtt_title: "Appareils MQTT (capteurs/interrupteurs)",
  settings_mqtt_hint: "Second courtier MQTT, independant des imprimantes, pour des capteurs librement definis (affichage d'une valeur, avec graphique d'historique) et des interrupteurs (envoi de messages marche/arret fixes) - soit par imprimante, soit autonome (voir \"Aucune imprimante\" lors de la creation).",
  field_broker_settings: "Parametres du courtier",
  label_enabled: "Active",
  label_broker_address: "Adresse du courtier",
  label_port: "Port",
  label_username_optional: "Nom d'utilisateur (optionnel)",
  label_password_optional_unchanged: "Mot de passe (optionnel, laisser vide = inchange)",
  label_use_tls: "Utiliser TLS",
  btn_save_broker_settings: "Enregistrer les parametres du courtier",
  field_sensors_switches: "Capteurs & interrupteurs",
  settings_history_title: "Historique d'impression",
  label_history_max_jobs: "Nombre maximal de travaux d'impression conserves par imprimante (vide = illimite)",
  hint_history_save: "Enregistre via le bouton \"Enregistrer\" en haut, pres de \"← Retour a l'exploitation\" (voir ci-dessus) - s'applique uniquement a ce champ.",
  modal_camera_add_title: "Ajouter une camera",
  label_name: "Nom",
  label_rtsp_url: "URL RTSP(S)",
  hint_camera_credentials: "Sans identifiants dans l'URL elle-meme - les deux champs ci-dessous sont inseres automatiquement (caracteres speciaux inclus).",
  label_password_optional: "Mot de passe (optionnel)",
  label_room_optional: "Piece (optionnel)",
  option_no_room: "Aucune piece",
  btn_cancel: "Annuler",
  modal_add_printer_title: "Ajouter une nouvelle imprimante",
  label_printer_type: "Type d'imprimante",
  type_formlabs: "Formlabs (imprimante)",
  type_creality_other: "Creality (autre imprimante Klipper)",
  label_device_ip: "Adresse IP de l'appareil",
  label_access_code: "Code d'acces (mode LAN, ecran de l'imprimante → parametres)",
  label_serial: "Numero de serie",
  label_printer_family: "Famille d'imprimante",
  hint_bambu_family: "Determine quel parametre de connexion est utilise lors de la premiere tentative de transfert de fichier (les series X1 et A1 necessitent des parametres differents, parfois opposes). En cas de mauvais choix, l'autre parametre est automatiquement essaye lors de la deuxieme tentative - l'impression fonctionne donc de toute facon, un bon choix ne fait qu'eviter un echec. Aucune donnee propre n'existe encore pour les series H2, P1, P2 et X2 - elles utilisent pour l'instant le meme parametre que la serie X1.",
  hint_formlabs: "Necessite le \"PreFormServer\" local (Formlabs Local API, inclus dans l'installation de PreForm) - voir README.",
  label_api_key: "Cle API",
  label_use_https: "Utiliser HTTPS",
  label_webcam_url_optional: "URL de la webcam (optionnel)",
  hint_creality_moonraker: "Necessite Moonraker sur l'imprimante (les K1/K1C/K1 Max/K1 SE de serie doivent d'abord etre \"rootes\" via SSH) - voir README.",
  label_api_key_optional_see_readme: "Cle API (generalement pas necessaire, voir README)",
  label_moonraker_port: "Port Moonraker",
  hint_ultimaker_api: "Utilise l'API locale officielle et non authentifiee d'Ultimaker - aucune connexion/cle API necessaire, voir README.",
  label_port_optional: "Port (optionnel)",
  btn_add: "Ajouter",
  modal_ams_title: "Verifier l'assignation AMS",
  btn_start_print: "Lancer l'impression",
  modal_history_title: "Historique d'impression",
  btn_close: "Fermer",
  sort_newest_first: "Tri : plus recent d'abord",
  modal_queue_title: "File d'attente",
  btn_bed_empty_send_next: "Plateau vide - envoyer le suivant",
  dz_drop_to_queue: "Deposer un fichier ici pour l'ajouter a la file d'attente",
  dz_or: "ou",
  dz_choose_file: "Choisir un fichier",
  modal_assign_title: "Assigner le travail",
  label_target_printer: "Imprimante cible",
  btn_assign: "Assigner",
  btn_start_next_print: "Lancer l'impression suivante",
  hint_farmbot_manual_reorder: "L'ordre peut etre modifie manuellement avec ▲/▼ - il sera automatiquement retrie lors du prochain fichier televerse.",
  dz_drop_to_farmbot_queue: "Deposer un fichier ici pour l'ajouter a la file d'attente de ce FarmBot",
  modal_farmbot_bed_title: "Liberer le plateau d'impression",
  btn_other_printer: "Autre imprimante",
  btn_bed_free: "Plateau libre",
  label_name_suffix_optional: "Complement de nom (optionnel)",
  label_manufacturer: "Fabricant",
  hint_farmbot_ultimaker: "Seules les imprimantes Ultimaker deja couplees au tableau de bord sont prises en compte (voir \"Gerer les imprimantes\").",
  label_workday_from: "Journee de travail de",
  label_workday_to: "Journee de travail a",
  label_max_queue_days: "Temps d'attente maximal dans la file (jours)",
  hint_max_queue_days: "Les travaux atteignant ce temps d'attente sont traites en priorite, independamment de leur duree d'impression, lors du prochain recalcul automatique de l'ordre.",
  temp_nozzle: "Buse",
  temp_bed: "Plateau",
  temp_chamber: "Chambre",
  tooltip_show_camera: "Afficher la camera",
  tooltip_history: "Historique d'impression",
  ams_filament_title: "AMS / filament",
  empty_no_printers: "Aucune imprimante ajoutee pour l'instant.",
  btn_add_printer_empty: "+ Ajouter une imprimante",
  dz_hint_developer_mode: "Necessite le mode developpeur / mode LAN sur l'imprimante",
  dz_hint_cura_export: "Exporte depuis Cura, p. ex. via \"Enregistrer dans un fichier\"",
  camera_type_badge: "Camera",
  switch_type_badge: "Interrupteur",
  sensor_type_badge: "Capteur",
  btn_on: "Marche",
  btn_off: "Arret",
  hint_octoprint_no_chamber: "OctoPrint ne fournit pas de temperature de chambre / pas d'equivalent AMS.",
  hint_creality_chamber: "Connecte via Moonraker. Temperature de chambre visible uniquement si un capteur correspondant est configure dans Klipper.",
  hint_ultimaker_no_chamber: "Les imprimantes de bureau Ultimaker n'ont pas de capteur de temperature de chambre.",
  title_progress_thumb: "Apercu du travail d'impression actuel/dernier",
  farmbot_sub_ultimaker: "Ultimaker",
  farmbot_sub_bambu: "Bambu Lab &middot; {family}",
  farmbot_sub_suffix: " &middot; Journee {start}&ndash;{end} &middot; max. {days} jours d'attente",
  farmbot_fits_text: "{fits} travaux sur {total} peuvent theoriquement encore etre lances aujourd'hui (le dernier peut continuer d'imprimer sans surveillance apres la fin de journee).",
  farmbot_queue_empty: "La file d'attente est vide.",
  farmbot_queue_waiting_badge: "{count} en attente",
  btn_farmbot_queue: "File d'attente",
  farmbot_dz_gcode: "Deposer ici un fichier .gcode decoupe",
  farmbot_dz_gcode3mf: "Deposer ici un fichier .gcode.3mf decoupe",
  btn_farmbot_start_next: "Lancer l'impression suivante",
  btn_edit: "Modifier",
  btn_delete: "Supprimer",
  btn_show: "Afficher",
  btn_remove: "Retirer",
  btn_enable: "Activer",
  btn_disable: "Desactiver",
  empty_no_farmbots: "Aucun FarmBot cree pour l'instant.",
  farmbot_disabled_hint: "(desactive)",
  farmbot_manage_sub_suffix: " &middot; Journee {start}&ndash;{end} &middot; max. {days} jours",
  sort_alpha: "Tri : A-Z",
  history_empty: "Aucun travail d'impression envoye via le tableau de bord pour l'instant.",
  farmbot_queue_modal_title_suffix: " - File d'attente",
  farmbot_default_name: "FarmBot",
  loading_generic: "Chargement ...",
  field_current_file: "Fichier actuel",
  btn_abort_print: "Annuler",
  confirm_abort_print: "Vraiment annuler l'impression en cours ? Cette action est irreversible.",
  toast_abort_sent: "Annulation demandee.",
  toast_abort_failed: "Echec de l'annulation.",
  toast_abort_network_error: "Erreur reseau lors de l'annulation."
},
es: {
  layout_switch_title: "Disposicion de tarjetas",
  btn_settings: "Ajustes",
  btn_back_to_operation: "Volver a la operacion",
  btn_save: "Guardar",
  settings_language_title: "Idioma",
  settings_language_hint: "Idioma de la interfaz del panel - se aplica de inmediato a todas las etiquetas, botones y textos de ayuda. Los mensajes de error del servidor permanecen en aleman independientemente de este ajuste.",
  settings_printers_title: "Gestionar impresoras",
  settings_printers_hint: "Anadir, eliminar, asignar a una sala y cambiar el orden de visualizacion. La vista de camara y todas las funciones de impresion permanecen en el modo de operacion.",
  btn_add_printer: "+ Anadir impresora",
  settings_farmbot_hint: "Cola(s) de trabajos de impresion independiente(s), asignada(s) automaticamente a una impresora actualmente libre del fabricante/familia seleccionados - independiente de la cola de cada impresora individual. Al activarse, cada FarmBot muestra su propia tarjeta encima de las impresoras en el modo de operacion.",
  btn_add_farmbot: "+ Anadir FarmBot",
  settings_groups_title: "Salas / grupos",
  settings_groups_hint: "Las impresoras pueden mostrarse agrupadas por sala en el modo de operacion. Eliminar una sala NO elimina ninguna impresora - estas aparecen entonces bajo \"Sin sala\".",
  placeholder_new_group_name: "Nombre de la nueva sala (p. ej. taller)",
  btn_add_group: "+ Crear sala",
  settings_cameras_title: "Camaras RTSP externas",
  settings_cameras_hint: "Ademas de las camaras integradas de las impresoras, se puede anadir cualquier otra camara RTSP(S) (p. ej. una vista general de la sala) - aparecera entonces como su propia tarjeta en el modo de operacion, en la sala asignada (o bajo \"Sin sala\"). Opcionalmente con su propio inicio de sesion (usuario/contrasena). Requiere FFmpeg (ver README/LINUX-INSTALL.md), igual que la camara RTSPS de la serie X1/P1/P2/H2/X2.",
  btn_add_camera: "+ Anadir camara",
  settings_mqtt_title: "Dispositivos MQTT (sensores/interruptores)",
  settings_mqtt_hint: "Un segundo broker MQTT, independiente de las impresoras, para sensores definidos libremente (muestra un valor, con grafico de historial) e interruptores (envian mensajes fijos de encendido/apagado) - ya sea por impresora o independiente (ver \"Sin impresora\" al crearlo).",
  field_broker_settings: "Ajustes del broker",
  label_enabled: "Activado",
  label_broker_address: "Direccion del broker",
  label_port: "Puerto",
  label_username_optional: "Nombre de usuario (opcional)",
  label_password_optional_unchanged: "Contrasena (opcional, dejar en blanco = sin cambios)",
  label_use_tls: "Usar TLS",
  btn_save_broker_settings: "Guardar ajustes del broker",
  field_sensors_switches: "Sensores e interruptores",
  settings_history_title: "Historial de impresion",
  label_history_max_jobs: "Numero maximo de trabajos de impresion guardados por impresora (en blanco = ilimitado)",
  hint_history_save: "Se guarda mediante el boton \"Guardar\" de arriba, junto a \"← Volver a la operacion\" (ver alli) - solo se aplica a este campo.",
  modal_camera_add_title: "Anadir camara",
  label_name: "Nombre",
  label_rtsp_url: "URL RTSP(S)",
  hint_camera_credentials: "Sin credenciales en la propia URL - los dos campos de abajo se insertan automaticamente (incluyendo caracteres especiales).",
  label_password_optional: "Contrasena (opcional)",
  label_room_optional: "Sala (opcional)",
  option_no_room: "Sin sala",
  btn_cancel: "Cancelar",
  modal_add_printer_title: "Anadir nueva impresora",
  label_printer_type: "Tipo de impresora",
  type_formlabs: "Formlabs (impresora)",
  type_creality_other: "Creality (otra impresora Klipper)",
  label_device_ip: "Direccion IP del dispositivo",
  label_access_code: "Codigo de acceso (modo LAN, pantalla de la impresora → ajustes)",
  label_serial: "Numero de serie",
  label_printer_family: "Familia de impresora",
  hint_bambu_family: "Determina que ajuste de conexion se usa en el primer intento de subida de archivo (las series X1 y A1 necesitan ajustes distintos, en parte opuestos). Si se elige el equivocado, se prueba automaticamente el otro ajuste en el segundo intento - la impresion funciona de todos modos, una eleccion correcta solo evita un intento fallido. Todavia no hay datos propios para las series H2, P1, P2 y X2 - por ahora usan el mismo ajuste que la serie X1.",
  hint_formlabs: "Requiere el \"PreFormServer\" local (Formlabs Local API, parte de la instalacion de PreForm) - ver README.",
  label_api_key: "Clave API",
  label_use_https: "Usar HTTPS",
  label_webcam_url_optional: "URL de la webcam (opcional)",
  hint_creality_moonraker: "Requiere Moonraker en la impresora (las unidades de fabrica K1/K1C/K1 Max/K1 SE deben \"rootearse\" primero via SSH) - ver README.",
  label_api_key_optional_see_readme: "Clave API (normalmente no necesaria, ver README)",
  label_moonraker_port: "Puerto de Moonraker",
  hint_ultimaker_api: "Usa la API local oficial y no autenticada de Ultimaker - no se necesita inicio de sesion/clave API, ver README.",
  label_port_optional: "Puerto (opcional)",
  btn_add: "Anadir",
  modal_ams_title: "Comprobar asignacion de AMS",
  btn_start_print: "Iniciar impresion",
  modal_history_title: "Historial de impresion",
  btn_close: "Cerrar",
  sort_newest_first: "Orden: mas reciente primero",
  modal_queue_title: "Cola",
  btn_bed_empty_send_next: "Cama vacia - enviar siguiente",
  dz_drop_to_queue: "Suelta un archivo aqui para anadirlo a la cola",
  dz_or: "o",
  dz_choose_file: "Elegir archivo",
  modal_assign_title: "Asignar trabajo",
  label_target_printer: "Impresora de destino",
  btn_assign: "Asignar",
  btn_start_next_print: "Iniciar siguiente impresion",
  hint_farmbot_manual_reorder: "El orden se puede cambiar manualmente con ▲/▼ - se reordenara automaticamente de nuevo con el siguiente archivo subido.",
  dz_drop_to_farmbot_queue: "Suelta un archivo aqui para anadirlo a la cola de este FarmBot",
  modal_farmbot_bed_title: "Liberar cama de impresion",
  btn_other_printer: "Otra impresora",
  btn_bed_free: "Cama libre",
  label_name_suffix_optional: "Sufijo de nombre (opcional)",
  label_manufacturer: "Fabricante",
  hint_farmbot_ultimaker: "Solo se consideran las impresoras Ultimaker ya emparejadas con el panel (ver \"Gestionar impresoras\").",
  label_workday_from: "Jornada laboral desde",
  label_workday_to: "Jornada laboral hasta",
  label_max_queue_days: "Tiempo maximo de espera en la cola (dias)",
  hint_max_queue_days: "Los trabajos que alcancen este tiempo de espera se procesan con prioridad, independientemente de su duracion de impresion, en el siguiente recalculo automatico del orden.",
  temp_nozzle: "Boquilla",
  temp_bed: "Cama",
  temp_chamber: "Camara",
  tooltip_show_camera: "Mostrar camara",
  tooltip_history: "Historial de impresion",
  ams_filament_title: "AMS / filamento",
  empty_no_printers: "Todavia no hay impresoras anadidas.",
  btn_add_printer_empty: "+ Anadir impresora",
  dz_hint_developer_mode: "Requiere el modo de desarrollador / modo LAN en la impresora",
  dz_hint_cura_export: "Exportado desde Cura, p. ej. mediante \"Guardar en archivo\"",
  camera_type_badge: "Camara",
  switch_type_badge: "Interruptor",
  sensor_type_badge: "Sensor",
  btn_on: "Encendido",
  btn_off: "Apagado",
  hint_octoprint_no_chamber: "OctoPrint no proporciona temperatura de camara / no hay equivalente a AMS.",
  hint_creality_chamber: "Conectado via Moonraker. La temperatura de camara solo es visible si hay un sensor correspondiente configurado en Klipper.",
  hint_ultimaker_no_chamber: "Las impresoras de escritorio Ultimaker no tienen sensor de temperatura de camara.",
  title_progress_thumb: "Vista previa del trabajo de impresion actual/ultimo",
  farmbot_sub_ultimaker: "Ultimaker",
  farmbot_sub_bambu: "Bambu Lab &middot; {family}",
  farmbot_sub_suffix: " &middot; Jornada {start}&ndash;{end} &middot; max. {days} dias de espera",
  farmbot_fits_text: "{fits} de {total} trabajos pueden iniciarse hoy en teoria (el ultimo puede seguir imprimiendo sin supervision mas alla del cierre).",
  farmbot_queue_empty: "La cola esta vacia.",
  farmbot_queue_waiting_badge: "{count} en espera",
  btn_farmbot_queue: "Cola",
  farmbot_dz_gcode: "Suelta aqui un archivo .gcode laminado",
  farmbot_dz_gcode3mf: "Suelta aqui un archivo .gcode.3mf laminado",
  btn_farmbot_start_next: "Iniciar siguiente impresion",
  btn_edit: "Editar",
  btn_delete: "Eliminar",
  btn_show: "Mostrar",
  btn_remove: "Quitar",
  btn_enable: "Activar",
  btn_disable: "Desactivar",
  empty_no_farmbots: "Todavia no se ha creado ningun FarmBot.",
  farmbot_disabled_hint: "(desactivado)",
  farmbot_manage_sub_suffix: " &middot; Jornada {start}&ndash;{end} &middot; max. {days} dias",
  sort_alpha: "Orden: A-Z",
  history_empty: "Todavia no se ha enviado ningun trabajo de impresion a traves del panel.",
  farmbot_queue_modal_title_suffix: " - Cola",
  farmbot_default_name: "FarmBot",
  loading_generic: "Cargando ...",
  field_current_file: "Archivo actual",
  btn_abort_print: "Cancelar",
  confirm_abort_print: "¿Cancelar realmente la impresion en curso? Esta accion no se puede deshacer.",
  toast_abort_sent: "Cancelacion solicitada.",
  toast_abort_failed: "Error al cancelar.",
  toast_abort_network_error: "Error de red al cancelar."
},
zh: {
  layout_switch_title: "卡片布局",
  btn_settings: "设置",
  btn_back_to_operation: "返回操作",
  btn_save: "保存",
  settings_language_title: "语言",
  settings_language_hint: "仪表盘的界面语言 - 立即应用于所有标签、按钮和提示文本。服务器的错误消息始终为德语，不受此设置影响。",
  settings_printers_title: "管理打印机",
  settings_printers_hint: "添加、删除、分配到房间以及更改显示顺序。摄像头显示和所有打印功能保留在操作模式中。",
  btn_add_printer: "+ 添加打印机",
  settings_farmbot_hint: "独立的打印任务队列，会自动分配给当前空闲且符合所选制造商/系列的打印机 - 与各打印机自身的队列无关。启用后，每个 FarmBot 会在操作模式下的打印机上方显示自己的卡片。",
  btn_add_farmbot: "+ 添加 FarmBot",
  settings_groups_title: "房间 / 分组",
  settings_groups_hint: "在操作模式下，打印机可以按房间分组显示。删除房间不会删除任何打印机 - 它们会显示在\"无房间\"下。",
  placeholder_new_group_name: "新房间名称（例如：车间）",
  btn_add_group: "+ 创建房间",
  settings_cameras_title: "外部 RTSP 摄像头",
  settings_cameras_hint: "除了打印机自带的摄像头外，还可以添加任意数量的其他 RTSP(S) 摄像头（例如房间全景）- 之后会在操作模式下作为独立卡片显示在所分配的房间（或\"无房间\"）中。如有需要可配置独立登录信息（用户名/密码）。需要 FFmpeg（参见 README/LINUX-INSTALL.md），与 X1/P1/P2/H2/X2 系列的 RTSPS 摄像头相同。",
  btn_add_camera: "+ 添加摄像头",
  settings_mqtt_title: "MQTT 设备（传感器/开关）",
  settings_mqtt_hint: "一个独立于打印机的第二个 MQTT 代理，用于自由定义的传感器（显示数值及历史图表）和开关（发送固定的开/关消息）- 可按打印机绑定，也可独立使用（创建时参见\"无打印机\"）。",
  field_broker_settings: "代理设置",
  label_enabled: "已启用",
  label_broker_address: "代理地址",
  label_port: "端口",
  label_username_optional: "用户名（可选）",
  label_password_optional_unchanged: "密码（可选，留空表示不更改）",
  label_use_tls: "使用 TLS",
  btn_save_broker_settings: "保存代理设置",
  field_sensors_switches: "传感器和开关",
  settings_history_title: "打印历史",
  label_history_max_jobs: "每台打印机保存的最大打印任务数（留空表示不限）",
  hint_history_save: "通过上方\"← 返回操作\"旁的\"保存\"按钮保存（参见那里）- 仅适用于此字段。",
  modal_camera_add_title: "添加摄像头",
  label_name: "名称",
  label_rtsp_url: "RTSP(S) 地址",
  hint_camera_credentials: "URL 本身不含凭据 - 下面两个字段会自动插入（含特殊字符）。",
  label_password_optional: "密码（可选）",
  label_room_optional: "房间（可选）",
  option_no_room: "无房间",
  btn_cancel: "取消",
  modal_add_printer_title: "添加新打印机",
  label_printer_type: "打印机类型",
  type_formlabs: "Formlabs（打印机）",
  type_creality_other: "Creality（其他 Klipper 打印机）",
  label_device_ip: "设备 IP 地址",
  label_access_code: "访问代码（LAN 模式，打印机显示屏 → 设置）",
  label_serial: "序列号",
  label_printer_family: "打印机系列",
  hint_bambu_family: "决定首次文件上传尝试时使用哪种连接设置（X1 和 A1 系列需要不同、部分相反的设置）。若选择错误，第二次尝试会自动使用另一种设置 - 因此打印总能成功，正确选择只是省去一次失败尝试。H2、P1、P2 和 X2 系列目前尚无专门数据 - 暂时使用与 X1 系列相同的设置。",
  hint_formlabs: "需要本地运行的\"PreFormServer\"（Formlabs Local API，PreForm 安装的一部分）- 参见 README。",
  label_api_key: "API 密钥",
  label_use_https: "使用 HTTPS",
  label_webcam_url_optional: "网络摄像头地址（可选）",
  hint_creality_moonraker: "需要在打印机上运行 Moonraker（原厂 K1/K1C/K1 Max/K1 SE 需先通过 SSH \"root\"）- 参见 README。",
  label_api_key_optional_see_readme: "API 密钥（通常不需要，参见 README）",
  label_moonraker_port: "Moonraker 端口",
  hint_ultimaker_api: "使用官方的、无需认证的本地 Ultimaker API - 不需要登录/API 密钥，参见 README。",
  label_port_optional: "端口（可选）",
  btn_add: "添加",
  modal_ams_title: "检查 AMS 分配",
  btn_start_print: "开始打印",
  modal_history_title: "打印历史",
  btn_close: "关闭",
  sort_newest_first: "排序：最新在前",
  modal_queue_title: "队列",
  btn_bed_empty_send_next: "打印舱已空 - 发送下一个",
  dz_drop_to_queue: "将文件拖放到此处以加入队列",
  dz_or: "或",
  dz_choose_file: "选择文件",
  modal_assign_title: "分配任务",
  label_target_printer: "目标打印机",
  btn_assign: "分配",
  btn_start_next_print: "开始下一个打印",
  hint_farmbot_manual_reorder: "可以用 ▲/▼ 手动调整顺序 - 下次上传文件时会自动重新排序。",
  dz_drop_to_farmbot_queue: "将文件拖放到此处以加入此 FarmBot 的队列",
  modal_farmbot_bed_title: "释放打印舱",
  btn_other_printer: "其他打印机",
  btn_bed_free: "打印舱空闲",
  label_name_suffix_optional: "名称后缀（可选）",
  label_manufacturer: "制造商",
  hint_farmbot_ultimaker: "仅考虑已与仪表盘配对的 Ultimaker 打印机（参见\"管理打印机\"）。",
  label_workday_from: "工作时间从",
  label_workday_to: "工作时间到",
  label_max_queue_days: "队列中的最长等待时间（天）",
  hint_max_queue_days: "达到此等待时间的任务，将在下次自动重新计算顺序时优先处理，不论其打印时长。",
  temp_nozzle: "喷嘴",
  temp_bed: "热床",
  temp_chamber: "机箱",
  tooltip_show_camera: "显示摄像头",
  tooltip_history: "打印历史",
  ams_filament_title: "AMS / 耗材",
  empty_no_printers: "尚未添加任何打印机。",
  btn_add_printer_empty: "+ 添加打印机",
  dz_hint_developer_mode: "需要在打印机上启用开发者模式 / LAN 模式",
  dz_hint_cura_export: "从 Cura 导出，例如通过\"保存到文件\"",
  camera_type_badge: "摄像头",
  switch_type_badge: "开关",
  sensor_type_badge: "传感器",
  btn_on: "开",
  btn_off: "关",
  hint_octoprint_no_chamber: "OctoPrint 不提供机箱温度 / 没有 AMS 对应功能。",
  hint_creality_chamber: "通过 Moonraker 连接。只有在 Klipper 配置中设置了相应传感器时，才会显示机箱温度。",
  hint_ultimaker_no_chamber: "Ultimaker 桌面打印机没有机箱温度传感器。",
  title_progress_thumb: "当前/最后一个打印任务的预览图",
  farmbot_sub_ultimaker: "Ultimaker",
  farmbot_sub_bambu: "Bambu Lab &middot; {family}",
  farmbot_sub_suffix: " &middot; 工作时间 {start}&ndash;{end} &middot; 最长等待 {days} 天",
  farmbot_fits_text: "理论上今天还能开始 {total} 个任务中的 {fits} 个（其中最后一个可以在下班后无人值守继续打印）。",
  farmbot_queue_empty: "队列为空。",
  farmbot_queue_waiting_badge: "{count} 个等待中",
  btn_farmbot_queue: "队列",
  farmbot_dz_gcode: "将已切片的 .gcode 文件拖放到此处",
  farmbot_dz_gcode3mf: "将已切片的 .gcode.3mf 文件拖放到此处",
  btn_farmbot_start_next: "开始下一个打印",
  btn_edit: "编辑",
  btn_delete: "删除",
  btn_show: "显示",
  btn_remove: "移除",
  btn_enable: "启用",
  btn_disable: "停用",
  empty_no_farmbots: "尚未创建任何 FarmBot。",
  farmbot_disabled_hint: "（已停用）",
  farmbot_manage_sub_suffix: " &middot; 工作时间 {start}&ndash;{end} &middot; 最长 {days} 天",
  sort_alpha: "排序：A-Z",
  history_empty: "尚未通过仪表盘发送任何打印任务。",
  farmbot_queue_modal_title_suffix: " - 队列",
  farmbot_default_name: "FarmBot",
  loading_generic: "正在加载...",
  field_current_file: "当前文件",
  btn_abort_print: "中止",
  confirm_abort_print: "确定要中止当前的打印任务吗？此操作无法撤销。",
  toast_abort_sent: "已发送中止请求。",
  toast_abort_failed: "中止失败。",
  toast_abort_network_error: "中止时发生网络错误。"
},
ja: {
  layout_switch_title: "カードレイアウト",
  btn_settings: "設定",
  btn_back_to_operation: "操作画面に戻る",
  btn_save: "保存",
  settings_language_title: "言語",
  settings_language_hint: "ダッシュボードの表示言語です - すべてのラベル、ボタン、ヒントテキストに即時反映されます。サーバーからのエラーメッセージはこの設定に関わらずドイツ語のままです。",
  settings_printers_title: "プリンターの管理",
  settings_printers_hint: "追加、削除、部屋への割り当て、表示順の変更ができます。カメラ表示とすべての印刷機能は操作モードのままです。",
  btn_add_printer: "+ プリンターを追加",
  settings_farmbot_hint: "選択したメーカー/ファミリーに合う、現在空いているプリンターに自動的に割り当てられる独立した印刷ジョブの待機列です - 各プリンター自身の待機列とは独立しています。有効にすると、操作モードでプリンターの上に各 FarmBot 専用のカードが表示されます。",
  btn_add_farmbot: "+ FarmBot を追加",
  settings_groups_title: "部屋 / グループ",
  settings_groups_hint: "操作モードではプリンターを部屋ごとにグループ化して表示できます。部屋を削除してもプリンターは削除されません - その後は「部屋なし」に表示されます。",
  placeholder_new_group_name: "新しい部屋の名前（例：工房）",
  btn_add_group: "+ 部屋を作成",
  settings_cameras_title: "外部 RTSP カメラ",
  settings_cameras_hint: "プリンター内蔵カメラに加えて、任意の RTSP(S) カメラを追加できます（例：部屋全体の様子）- 操作モードでは割り当てられた部屋（または「部屋なし」）に専用カードとして表示されます。必要に応じて専用のログイン情報（ユーザー名/パスワード）を設定できます。X1/P1/P2/H2/X2 シリーズの RTSPS カメラと同様に FFmpeg が必要です（README/LINUX-INSTALL.md 参照）。",
  btn_add_camera: "+ カメラを追加",
  settings_mqtt_title: "MQTT デバイス（センサー/スイッチ）",
  settings_mqtt_hint: "プリンターとは独立した、自由に定義できるセンサー（値の表示、履歴グラフ付き）とスイッチ（固定のオン/オフメッセージ送信）用の第二の MQTT ブローカーです - プリンターごと、または独立（作成時に「プリンターなし」を参照）のいずれかで使用できます。",
  field_broker_settings: "ブローカー設定",
  label_enabled: "有効",
  label_broker_address: "ブローカーアドレス",
  label_port: "ポート",
  label_username_optional: "ユーザー名（任意）",
  label_password_optional_unchanged: "パスワード（任意、空欄のままなら変更なし）",
  label_use_tls: "TLS を使用",
  btn_save_broker_settings: "ブローカー設定を保存",
  field_sensors_switches: "センサー＆スイッチ",
  settings_history_title: "印刷履歴",
  label_history_max_jobs: "プリンターごとに保存する印刷ジョブの最大数（空欄なら無制限）",
  hint_history_save: "上部の「← 操作画面に戻る」の横にある「保存」ボタンで保存されます（そちら参照）- この項目にのみ適用されます。",
  modal_camera_add_title: "カメラを追加",
  label_name: "名前",
  label_rtsp_url: "RTSP(S) URL",
  hint_camera_credentials: "URL 自体には認証情報を含めません - 下の2つの項目が自動的に（特殊文字含めて）組み込まれます。",
  label_password_optional: "パスワード（任意）",
  label_room_optional: "部屋（任意）",
  option_no_room: "部屋なし",
  btn_cancel: "キャンセル",
  modal_add_printer_title: "新しいプリンターを追加",
  label_printer_type: "プリンターの種類",
  type_formlabs: "Formlabs（プリンター）",
  type_creality_other: "Creality（その他の Klipper プリンター）",
  label_device_ip: "デバイスの IP アドレス",
  label_access_code: "アクセスコード（LAN モード、プリンターのディスプレイ → 設定）",
  label_serial: "シリアル番号",
  label_printer_family: "プリンターファミリー",
  hint_bambu_family: "最初のファイルアップロード時にどの接続設定を使うかを決めます（X1 シリーズと A1 シリーズでは異なる、場合によっては正反対の設定が必要です）。選択を誤った場合は2回目の試行で自動的に別の設定が試されます - いずれにしても印刷は実行されますが、正しく選べば失敗を1回減らせます。H2、P1、P2、X2 シリーズについては独自のデータがまだなく、現時点では X1 シリーズと同じ設定を使用します。",
  hint_formlabs: "ローカルで動作する「PreFormServer」（Formlabs Local API、PreForm インストールの一部）が必要です - README を参照してください。",
  label_api_key: "API キー",
  label_use_https: "HTTPS を使用",
  label_webcam_url_optional: "ウェブカメラ URL（任意）",
  hint_creality_moonraker: "プリンター上で Moonraker が必要です（出荷時の K1/K1C/K1 Max/K1 SE はまず SSH で「root 化」が必要）- README を参照してください。",
  label_api_key_optional_see_readme: "API キー（通常は不要、README を参照）",
  label_moonraker_port: "Moonraker のポート",
  hint_ultimaker_api: "公式の認証不要なローカル Ultimaker API を使用します - ログインや API キーは不要です、README を参照してください。",
  label_port_optional: "ポート（任意）",
  btn_add: "追加",
  modal_ams_title: "AMS の割り当てを確認",
  btn_start_print: "印刷を開始",
  modal_history_title: "印刷履歴",
  btn_close: "閉じる",
  sort_newest_first: "並び順：新しい順",
  modal_queue_title: "待機列",
  btn_bed_empty_send_next: "プレート空 - 次を送信",
  dz_drop_to_queue: "ここにファイルをドロップして待機列に追加",
  dz_or: "または",
  dz_choose_file: "ファイルを選択",
  modal_assign_title: "ジョブを割り当て",
  label_target_printer: "対象プリンター",
  btn_assign: "割り当て",
  btn_start_next_print: "次の印刷を開始",
  hint_farmbot_manual_reorder: "▲/▼ で順序を手動変更できます - 次にファイルがアップロードされると自動的に再ソートされます。",
  dz_drop_to_farmbot_queue: "ここにファイルをドロップしてこの FarmBot の待機列に追加",
  modal_farmbot_bed_title: "印刷プレートを解放",
  btn_other_printer: "別のプリンター",
  btn_bed_free: "プレート空き",
  label_name_suffix_optional: "名前の補足（任意）",
  label_manufacturer: "メーカー",
  hint_farmbot_ultimaker: "ダッシュボードに既に接続済みの Ultimaker プリンターのみが対象です（「プリンターの管理」参照）。",
  label_workday_from: "稼働時間（開始）",
  label_workday_to: "稼働時間（終了）",
  label_max_queue_days: "待機列での最大待機時間（日数）",
  hint_max_queue_days: "この待機時間に達したジョブは、次回の順序の自動再計算時に印刷時間に関わらず優先的に処理されます。",
  temp_nozzle: "ノズル",
  temp_bed: "ベッド",
  temp_chamber: "チャンバー",
  tooltip_show_camera: "カメラを表示",
  tooltip_history: "印刷履歴",
  ams_filament_title: "AMS / フィラメント",
  empty_no_printers: "まだプリンターが登録されていません。",
  btn_add_printer_empty: "+ プリンターを追加",
  dz_hint_developer_mode: "プリンターのデベロッパーモード / LAN モードが必要です",
  dz_hint_cura_export: "Cura からのエクスポート、例：「ファイルに保存」経由",
  camera_type_badge: "カメラ",
  switch_type_badge: "スイッチ",
  sensor_type_badge: "センサー",
  btn_on: "オン",
  btn_off: "オフ",
  hint_octoprint_no_chamber: "OctoPrint はチャンバー温度を提供しません / AMS に相当する機能はありません。",
  hint_creality_chamber: "Moonraker 経由で接続されています。チャンバー温度は Klipper の設定で対応するセンサーが設定されている場合のみ表示されます。",
  hint_ultimaker_no_chamber: "Ultimaker のデスクトッププリンターにはチャンバー温度センサーがありません。",
  title_progress_thumb: "現在/直前の印刷ジョブのプレビュー",
  farmbot_sub_ultimaker: "Ultimaker",
  farmbot_sub_bambu: "Bambu Lab &middot; {family}",
  farmbot_sub_suffix: " &middot; 稼働時間 {start}&ndash;{end} &middot; 最大待機 {days} 日",
  farmbot_fits_text: "理論上、本日中に {total} 件中 {fits} 件のジョブを開始できます（最後の1件は終業後も無人のまま印刷を継続できます）。",
  farmbot_queue_empty: "待機列は空です。",
  farmbot_queue_waiting_badge: "{count} 件待機中",
  btn_farmbot_queue: "待機列",
  farmbot_dz_gcode: "スライス済みの .gcode ファイルをここにドロップ",
  farmbot_dz_gcode3mf: "スライス済みの .gcode.3mf ファイルをここにドロップ",
  btn_farmbot_start_next: "次の印刷を開始",
  btn_edit: "編集",
  btn_delete: "削除",
  btn_show: "表示",
  btn_remove: "削除（登録解除）",
  btn_enable: "有効化",
  btn_disable: "無効化",
  empty_no_farmbots: "まだ FarmBot が作成されていません。",
  farmbot_disabled_hint: "（無効）",
  farmbot_manage_sub_suffix: " &middot; 稼働時間 {start}&ndash;{end} &middot; 最大 {days} 日",
  sort_alpha: "並び順：A-Z",
  history_empty: "まだダッシュボード経由で送信された印刷ジョブはありません。",
  farmbot_queue_modal_title_suffix: " - 待機列",
  farmbot_default_name: "FarmBot",
  loading_generic: "読み込み中...",
  field_current_file: "現在のファイル",
  btn_abort_print: "中止",
  confirm_abort_print: "実行中の印刷を本当に中止しますか？この操作は元に戻せません。",
  toast_abort_sent: "中止をリクエストしました。",
  toast_abort_failed: "中止に失敗しました。",
  toast_abort_network_error: "中止時にネットワークエラーが発生しました。"
},
tr: {
  layout_switch_title: "Kart duzeni",
  btn_settings: "Ayarlar",
  btn_back_to_operation: "Calismaya geri don",
  btn_save: "Kaydet",
  settings_language_title: "Dil",
  settings_language_hint: "Panelin arayuz dili - tum etiketlere, dugmelere ve ipucu metinlerine hemen uygulanir. Sunucudan gelen hata mesajlari bu ayardan bagimsiz olarak Almanca kalir.",
  settings_printers_title: "Yazicilari yonet",
  settings_printers_hint: "Ekle, kaldir, bir odaya ata ve goruntuleme sirasini degistir. Kamera gorunumu ve tum yazdirma islevleri calisma modunda kalir.",
  btn_add_printer: "+ Yazici ekle",
  settings_farmbot_hint: "Secilen uretici/aile ile eslesen, su anda bos olan bir yaziciya otomatik olarak atanan bagimsiz yazdirma gorevi kuyrugu/kuyruklari - her yazicinin kendi kuyrugundan bagimsizdir. Etkinlestirildiginde, calisma modunda yazicilarin ustunde her FarmBot icin ayri bir kart gorunur.",
  btn_add_farmbot: "+ FarmBot ekle",
  settings_groups_title: "Odalar / gruplar",
  settings_groups_hint: "Yazicilar calisma modunda odaya gore gruplanarak gosterilebilir. Bir odanin silinmesi HICBIR yaziciyi silmez - bu yazicilar daha sonra \"Oda yok\" altinda gorunur.",
  placeholder_new_group_name: "Yeni odanin adi (orn. atolye)",
  btn_add_group: "+ Oda olustur",
  settings_cameras_title: "Harici RTSP kameralar",
  settings_cameras_hint: "Yazicilara ait kameralara ek olarak, istenilen sayida baska RTSP(S) kamera eklenebilir (orn. oda genel gorunumu) - bunlar daha sonra calisma modunda, atanan odada (veya \"Oda yok\" altinda) kendi karti olarak gorunur. Gerekirse kendi oturum bilgileriyle (kullanici adi/sifre). X1/P1/P2/H2/X2 serisinin RTSPS kamerasi gibi FFmpeg gerektirir (bkz. README/LINUX-INSTALL.md).",
  btn_add_camera: "+ Kamera ekle",
  settings_mqtt_title: "MQTT cihazlari (sensorler/anahtarlar)",
  settings_mqtt_hint: "Yazicilardan bagimsiz, ozgurce tanimlanabilen sensorler (bir degerin gosterimi, gecmis grafigiyle) ve anahtarlar (sabit acma/kapama mesajlari gonderir) icin ikinci bir MQTT broker'i - yaziciya bagli veya bagimsiz olarak (olusturulurken \"Yazici yok\" secenegine bakin).",
  field_broker_settings: "Broker ayarlari",
  label_enabled: "Etkin",
  label_broker_address: "Broker adresi",
  label_port: "Port",
  label_username_optional: "Kullanici adi (istege bagli)",
  label_password_optional_unchanged: "Sifre (istege bagli, bos birakilirsa degismez)",
  label_use_tls: "TLS kullan",
  btn_save_broker_settings: "Broker ayarlarini kaydet",
  field_sensors_switches: "Sensorler ve anahtarlar",
  settings_history_title: "Yazdirma gecmisi",
  label_history_max_jobs: "Yazici basina saklanan maksimum yazdirma gorevi sayisi (bos = sinirsiz)",
  hint_history_save: "Yukarida \"← Calismaya geri don\" yanindaki \"Kaydet\" dugmesiyle kaydedilir (bkz. orada) - yalnizca bu alan icin gecerlidir.",
  modal_camera_add_title: "Kamera ekle",
  label_name: "Ad",
  label_rtsp_url: "RTSP(S) URL",
  hint_camera_credentials: "URL'nin kendisinde kimlik bilgisi olmadan - asagidaki iki alan otomatik olarak (ozel karakterler dahil) eklenir.",
  label_password_optional: "Sifre (istege bagli)",
  label_room_optional: "Oda (istege bagli)",
  option_no_room: "Oda yok",
  btn_cancel: "Vazgec",
  modal_add_printer_title: "Yeni yazici ekle",
  label_printer_type: "Yazici turu",
  type_formlabs: "Formlabs (yazici)",
  type_creality_other: "Creality (diger Klipper yazici)",
  label_device_ip: "Cihazin IP adresi",
  label_access_code: "Erisim kodu (LAN modu, yazici ekrani → ayarlar)",
  label_serial: "Seri numarasi",
  label_printer_family: "Yazici ailesi",
  hint_bambu_family: "Ilk dosya yukleme denemesinde hangi baglanti ayarinin kullanilacagini belirler (X1 ve A1 serisi farkli, kismen zit ayarlar gerektirir). Yanlis secim yapilirsa, ikinci denemede diger ayar otomatik olarak denenir - yazdirma her halde calisir, dogru secim sadece bir basarisiz denemeyi onler. H2, P1, P2 ve X2 serisi icin henuz kendi verisi yoktur - su an icin X1 serisiyle ayni ayari kullanirlar.",
  hint_formlabs: "Yerel olarak calisan \"PreFormServer\" (Formlabs Local API, PreForm kurulumunun bir parcasi) gerektirir - bkz. README.",
  label_api_key: "API anahtari",
  label_use_https: "HTTPS kullan",
  label_webcam_url_optional: "Webcam URL'si (istege bagli)",
  hint_creality_moonraker: "Yazicida Moonraker gerektirir (fabrika K1/K1C/K1 Max/K1 SE cihazlari once SSH ile \"root\" edilmelidir) - bkz. README.",
  label_api_key_optional_see_readme: "API anahtari (genellikle gerekli degildir, bkz. README)",
  label_moonraker_port: "Moonraker portu",
  hint_ultimaker_api: "Resmi, kimlik dogrulamasi gerektirmeyen yerel Ultimaker API'sini kullanir - oturum acma/API anahtari gerekmez, bkz. README.",
  label_port_optional: "Port (istege bagli)",
  btn_add: "Ekle",
  modal_ams_title: "AMS atamasini kontrol et",
  btn_start_print: "Yazdirmayi baslat",
  modal_history_title: "Yazdirma gecmisi",
  btn_close: "Kapat",
  sort_newest_first: "Siralama: once en yeni",
  modal_queue_title: "Kuyruk",
  btn_bed_empty_send_next: "Tabla bos - sonrakini gonder",
  dz_drop_to_queue: "Kuyruga eklemek icin dosyayi buraya birakin",
  dz_or: "veya",
  dz_choose_file: "Dosya sec",
  modal_assign_title: "Gorevi ata",
  label_target_printer: "Hedef yazici",
  btn_assign: "Ata",
  btn_start_next_print: "Sonraki yazdirmayi baslat",
  hint_farmbot_manual_reorder: "Sira ▲/▼ ile elle degistirilebilir - bir sonraki yuklenen dosyada otomatik olarak yeniden siralanir.",
  dz_drop_to_farmbot_queue: "Bu FarmBot'un kuyruguna eklemek icin dosyayi buraya birakin",
  modal_farmbot_bed_title: "Yazdirma tablasini bosalt",
  btn_other_printer: "Diger yazici",
  btn_bed_free: "Tabla bos",
  label_name_suffix_optional: "Ad eki (istege bagli)",
  label_manufacturer: "Uretici",
  hint_farmbot_ultimaker: "Yalnizca panel ile zaten eslestirilmis Ultimaker yazicilar dikkate alinir (bkz. \"Yazicilari yonet\").",
  label_workday_from: "Calisma gunu baslangici",
  label_workday_to: "Calisma gunu bitisi",
  label_max_queue_days: "Kuyrukta maksimum bekleme suresi (gun)",
  hint_max_queue_days: "Bu bekleme suresine ulasan gorevler, siranin bir sonraki otomatik yeniden hesaplanmasinda yazdirma suresinden bagimsiz olarak oncelikli islenir.",
  temp_nozzle: "Nozul",
  temp_bed: "Tabla",
  temp_chamber: "Hazne",
  tooltip_show_camera: "Kamerayi goster",
  tooltip_history: "Yazdirma gecmisi",
  ams_filament_title: "AMS / Filament",
  empty_no_printers: "Henuz yazici eklenmedi.",
  btn_add_printer_empty: "+ Yazici ekle",
  dz_hint_developer_mode: "Yazicida Gelistirici Modu / LAN modu gerektirir",
  dz_hint_cura_export: "Cura'dan disa aktarildi, orn. \"Dosyaya kaydet\" ile",
  camera_type_badge: "Kamera",
  switch_type_badge: "Anahtar",
  sensor_type_badge: "Sensor",
  btn_on: "Acik",
  btn_off: "Kapali",
  hint_octoprint_no_chamber: "OctoPrint hazne sicakligi saglamaz / AMS esdegeri yoktur.",
  hint_creality_chamber: "Moonraker uzerinden baglanmistir. Hazne sicakligi yalnizca Klipper kurulumunda ilgili bir sensor yapilandirilmissa gorunur.",
  hint_ultimaker_no_chamber: "Ultimaker masaustu yazicilarin hazne sicaklik sensoru yoktur.",
  title_progress_thumb: "Guncel/son yazdirma gorevinin onizlemesi",
  farmbot_sub_ultimaker: "Ultimaker",
  farmbot_sub_bambu: "Bambu Lab &middot; {family}",
  farmbot_sub_suffix: " &middot; Calisma gunu {start}&ndash;{end} &middot; maks. {days} gun bekleme",
  farmbot_fits_text: "{total} gorevden {fits} tanesi teorik olarak bugun hala baslatilabilir (bunlardan sonuncusu mesai disinda gozetimsiz yazdirmaya devam edebilir).",
  farmbot_queue_empty: "Kuyruk bos.",
  farmbot_queue_waiting_badge: "{count} bekliyor",
  btn_farmbot_queue: "Kuyruk",
  farmbot_dz_gcode: "Dilimlenmis .gcode dosyasini buraya birakin",
  farmbot_dz_gcode3mf: "Dilimlenmis .gcode.3mf dosyasini buraya birakin",
  btn_farmbot_start_next: "Sonraki yazdirmayi baslat",
  btn_edit: "Duzenle",
  btn_delete: "Sil",
  btn_show: "Goster",
  btn_remove: "Kaldir",
  btn_enable: "Etkinlestir",
  btn_disable: "Devre disi birak",
  empty_no_farmbots: "Henuz FarmBot olusturulmadi.",
  farmbot_disabled_hint: "(devre disi)",
  farmbot_manage_sub_suffix: " &middot; Calisma gunu {start}&ndash;{end} &middot; maks. {days} gun",
  sort_alpha: "Siralama: A-Z",
  history_empty: "Henuz panel uzerinden gonderilmis bir yazdirma gorevi yok.",
  farmbot_queue_modal_title_suffix: " - Kuyruk",
  farmbot_default_name: "FarmBot",
  loading_generic: "Yukleniyor ...",
  field_current_file: "Guncel dosya",
  btn_abort_print: "Iptal",
  confirm_abort_print: "Devam eden yazdirma gercekten iptal edilsin mi? Bu islem geri alinamaz.",
  toast_abort_sent: "Iptal talebi gonderildi.",
  toast_abort_failed: "Iptal basarisiz oldu.",
  toast_abort_network_error: "Iptal sirasinda ag hatasi olustu."
}
};

// native-script Namen fuer den Sprachwaehler (auch fuer das Erststart-
// Fenster, siehe showFirstRunLanguagePicker() - dort DARF nicht uebersetzt
// werden, da die Zielsprache beim ersten Aufruf noch unbekannt ist).
const LANGUAGE_NAMES = {
  de: "Deutsch",
  en: "English",
  fr: "Francais",
  es: "Espanol",
  zh: "中文",
  ja: "日本語",
  tr: "Turkce"
};

function t(key, vars){
  let entry = (I18N[currentLang] && I18N[currentLang][key]);
  if(entry === undefined) entry = (I18N.de && I18N.de[key]);
  if(entry === undefined) return key;
  if(vars){
    for(const k in vars){
      entry = entry.split('{' + k + '}').join(vars[k]);
    }
  }
  return entry;
}

// Wendet die aktuelle Sprache auf alle statisch im HTML vorhandenen,
// mit data-i18n(-placeholder|-title) markierten Elemente an. Dynamisch
// per JS erzeugte Inhalte (Kacheln, Modals mit generierten Listen) nutzen
// stattdessen direkt t() im jeweiligen Template-String und muessen daher
// nicht hier erfasst werden - sie werden beim naechsten Neuaufbau (z. B.
// naechster refresh()-Zyklus) automatisch in der neuen Sprache gezeichnet.
function applyTranslations(){
  document.documentElement.setAttribute('lang', currentLang);
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.getAttribute('data-i18n'));
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    el.setAttribute('placeholder', t(el.getAttribute('data-i18n-placeholder')));
  });
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    el.setAttribute('title', t(el.getAttribute('data-i18n-title')));
  });
}

async function changeLanguage(lang, skipSave){
  if(!I18N[lang]) return;
  currentLang = lang;
  applyTranslations();
  // v2.8.0: alle bereits gezeichneten dynamischen Bereiche neu aufbauen,
  // damit die per t() erzeugten Texte sofort in der neuen Sprache
  // erscheinen, statt erst beim naechsten periodischen refresh().
  try{ refresh(); }catch(e){}
  try{ if(typeof refreshPrinterManageList === 'function' && lastPrinterList) refreshPrinterManageList(lastPrinterList, lastGroupList); }catch(e){}
  try{ if(typeof refreshGroupsManageList === 'function' && lastGroupList) refreshGroupsManageList(lastGroupList); }catch(e){}
  try{ if(typeof refreshCamerasManageList === 'function' && lastCamsList) refreshCamerasManageList(lastCamsList); }catch(e){}
  try{ if(typeof refreshFarmbotManageList === 'function' && lastFarmbotList) refreshFarmbotManageList(lastFarmbotList); }catch(e){}
  if(!skipSave){
    try{
      await fetch('/api/settings', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({language: lang})
      });
    }catch(e){}
  }
}

function populateLanguageSelect(){
  const sel = document.getElementById('languageSelect');
  if(!sel) return;
  sel.innerHTML = Object.keys(LANGUAGE_NAMES).map(code =>
    `<option value="${code}" ${code === currentLang ? 'selected' : ''}>${LANGUAGE_NAMES[code]}</option>`
  ).join('');
}

// v2.8.0: Erststart-Sprachauswahl - erscheint als allererstes, bevor
// irgendetwas anderes auf der Seite geladen wird, wenn beim Programmstart
// noch keine config.json existierte (siehe CONFIG_WAS_FRESH/first_run im
// Python-Teil). Nutzt bewusst NUR die nativen Sprachnamen (LANGUAGE_NAMES)
// statt uebersetzter Button-Texte, da die Zielsprache hier per Definition
// noch nicht feststeht.
function showFirstRunLanguagePicker(){
  const overlay = document.createElement('div');
  overlay.id = 'firstRunLangOverlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:9999;display:flex;align-items:center;justify-content:center;';
  const box = document.createElement('div');
  box.style.cssText = 'background:var(--bg-card,#1e1e24);color:var(--text,#eee);border-radius:12px;padding:28px 32px;max-width:360px;text-align:center;box-shadow:0 10px 40px rgba(0,0,0,0.5);';
  box.innerHTML = '<div style="font-size:15px;margin-bottom:16px;">Sprache / Language / Langue / Idioma / 语言 / 言語 / Dil</div>';
  const list = document.createElement('div');
  list.style.cssText = 'display:flex;flex-direction:column;gap:8px;';
  Object.keys(LANGUAGE_NAMES).forEach(code => {
    const btn = document.createElement('button');
    btn.className = 'btn';
    btn.style.width = '100%';
    btn.textContent = LANGUAGE_NAMES[code];
    btn.onclick = async () => {
      overlay.remove();
      await changeLanguage(code);
    };
    list.appendChild(btn);
  });
  box.appendChild(list);
  overlay.appendChild(box);
  document.body.appendChild(overlay);
}

const CAM_ICON = `<svg viewBox="0 0 24 24"><path d="M4 7h3l1.5-2h7L17 7h3a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2zm8 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"/></svg>`;
const HIST_ICON = `<svg viewBox="0 0 24 24"><path d="M13 3a9 9 0 1 0 8.94 10h-2.02A7 7 0 1 1 13 5v4l5-4-5-4z"/><path d="M12 8v5l4 2-.75 1.3L11 14V8z"/></svg>`;
const FILE_ICON = `<svg viewBox="0 0 24 24"><path d="M6 2h9l5 5v15H6zm8 1.5V8h4.5z"/></svg>`;
// MK6 v1.2.0: Warteschlangen-Symbol (Listen-Icon) fuer die Kachel.
const QUEUE_ICON = `<svg viewBox="0 0 24 24"><path d="M3 5h18v2H3zm0 6h18v2H3zm0 6h12v2H3z"/></svg>`;

// v2.2.14: formatiert die vom Backend gelieferten Rohsekunden
// ("duration_sec", siehe _extract_print_duration_seconds() in app.py)
// als kurze "Xh Ymin"-Anzeige fuer Verlaufs-/Warteschlangeneintraege.
// Liefert eine leere Zeichenkette, wenn keine Dauer bekannt ist (aeltere
// Eintraege ohne "duration_sec", oder wenn sich aus der Datei keine
// Schaetzung extrahieren liess) - der Aufrufer zeigt dann einfach keinen
// Zeit-Hinweis an, statt "unbekannt" o. ae. anzuzeigen.
function formatDuration(sec){
  if(sec === undefined || sec === null || isNaN(sec)) return '';
  const totalMin = Math.max(0, Math.round(sec / 60));
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return h > 0 ? `${h}h ${m}min` : `${m}min`;
}

// MK6 v1.2.0: nur fuer Bambu/Ultimaker relevant (nur diese unterstuetzen
// Druckauftraege per Dashboard-Upload, siehe PrintQueueStore-Kommentar) -
// die anderen Kartentypen bekommen bewusst KEIN Warteschlangen-Symbol.
function renderQueueIcon(p){
  const badge = p.queue_count ? `<span class="queue-badge">${p.queue_count}</span>` : '';
  return `<div class="queue-icon" title="Warteschlange" onclick="openQueueModal('${p.id}')">${QUEUE_ICON}${badge}</div>`;
}

const FL_LABELS = {
  formlabs:      { badge: 'Formlabs Drucker', file: 'Aktueller Druckauftrag', showMaterial: true  },
  formlabs_wash: { badge: 'Formlabs Wash L',  file: 'Aktueller Waschzyklus',  showMaterial: false },
  formlabs_cure: { badge: 'Formlabs Cure L',  file: 'Aktueller Haertezyklus', showMaterial: false }
};

const CREALITY_TYPES = ['creality_k1', 'creality_k1c', 'creality_k1max', 'creality_k1se', 'creality_other'];
const CREALITY_LABELS = {
  creality_k1:    'Creality K1',
  creality_k1c:   'Creality K1C',
  creality_k1max: 'Creality K1 Max',
  creality_k1se:  'Creality K1 SE',
  creality_other: 'Creality (Klipper)'
};

// v2.9.0: Druckertypen, fuer die das Dashboard einen laufenden Druck
// abbrechen kann (siehe DashboardApp.abort_print() im Python-Teil fuer
// die Begruendung, warum Formlabs bewusst aussen vor bleibt).
const ABORT_SUPPORTED_TYPES = ['bambu', 'octoprint', 'ultimaker', ...CREALITY_TYPES];

// Abbrechen-Knopf: nur fuer unterstuetzte Druckertypen UND nur, wenn
// aktuell wirklich etwas laeuft/pausiert ist (siehe stateClass()) -
// sonst wuerde ein Klick nur eine fuer den Nutzer verwirrende
// Fehlermeldung des Druckers ("kein Druckauftrag aktiv") ausloesen.
function abortButtonHtml(p){
  if(!ABORT_SUPPORTED_TYPES.includes(p.type)) return '';
  if(!['running', 'paused'].includes(stateClass(p.gcode_state))) return '';
  return `<button class="btn-mini btn-delete" onclick="abortPrint('${p.id}')">${t('btn_abort_print')}</button>`;
}

async function abortPrint(printerId){
  if(!confirm(t('confirm_abort_print'))) return;
  try{
    const res = await fetch('/api/printers/' + printerId + '/print/abort', { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if(!res.ok){
      showToast(data.error || t('toast_abort_failed'), 'err');
      return;
    }
    showToast(t('toast_abort_sent'), 'ok');
    refresh();
  }catch(e){
    showToast(t('toast_abort_network_error'), 'err');
  }
}

function toggleTypeFields(){
  const type = document.getElementById('f_type').value;
  document.getElementById('bambuFields').style.display = (type === 'bambu') ? 'block' : 'none';
  document.getElementById('octoprintFields').style.display = (type === 'octoprint') ? 'block' : 'none';
  document.getElementById('crealityFields').style.display = CREALITY_TYPES.includes(type) ? 'block' : 'none';
  document.getElementById('ultimakerFields').style.display = (type === 'ultimaker') ? 'block' : 'none';
  document.getElementById('formlabsHint').style.display =
    (type === 'formlabs' || type === 'formlabs_wash' || type === 'formlabs_cure') ? 'block' : 'none';
}

function openAddModal(){
  document.getElementById('addError').style.display='none';
  ['f_name','f_ip','f_code','f_serial','f_apikey','f_port','f_webcam',
   'f_creality_apikey','f_creality_port','f_creality_webcam',
   'f_ultimaker_port','f_ultimaker_webcam'].forEach(id => document.getElementById(id).value='');
  document.getElementById('f_https').checked = false;
  document.getElementById('f_bambu_family').value = 'x1';
  document.getElementById('f_type').value = 'bambu';
  toggleTypeFields();
  document.getElementById('addModal').classList.add('show');
}
function closeAddModal(){ document.getElementById('addModal').classList.remove('show'); }

async function submitAdd(){
  const type = document.getElementById('f_type').value;
  const body = {
    type: type,
    name: document.getElementById('f_name').value.trim(),
    ip: document.getElementById('f_ip').value.trim(),
  };
  if(type === 'bambu'){
    body.access_code = document.getElementById('f_code').value.trim();
    body.serial = document.getElementById('f_serial').value.trim();
    body.bambu_family = document.getElementById('f_bambu_family').value;
  } else if(type === 'octoprint'){
    body.api_key = document.getElementById('f_apikey').value.trim();
    body.port = document.getElementById('f_port').value.trim() || 80;
    body.https = document.getElementById('f_https').checked;
    body.webcam_url = document.getElementById('f_webcam').value.trim();
  } else if(CREALITY_TYPES.includes(type)){
    body.api_key = document.getElementById('f_creality_apikey').value.trim();
    body.port = document.getElementById('f_creality_port').value.trim() || 7125;
    body.webcam_url = document.getElementById('f_creality_webcam').value.trim();
  } else if(type === 'ultimaker'){
    body.port = document.getElementById('f_ultimaker_port').value.trim() || 80;
    body.webcam_url = document.getElementById('f_ultimaker_webcam').value.trim();
  }

  const res = await fetch('/api/printers', {
    method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
  });
  const data = await res.json();
  if(!res.ok){
    const err = document.getElementById('addError');
    err.textContent = data.error || 'Fehler beim Hinzufuegen.';
    err.style.display='block';
    return;
  }
  closeAddModal();
  // v2.3.0: die "+ Drucker hinzufuegen"-Schaltflaeche ist jetzt nur noch
  // im Einstellungen-Modus erreichbar - dort muss die Verwaltungsliste
  // selbst aktualisiert werden, refresh() allein wuerde nur die (dort
  // ausgeblendete) Bedienansicht aktualisieren.
  if(settingsMode) refreshSettingsPanel();
  else refresh();
}

// ----------------------------------------------------------------------
// v2.2.15: MQTT-Sensoren & Schalter komplett ueber die Web-Oberflaeche
// verwalten (Broker-Einstellungen + je Drucker Sensor-/Schalter-
// Eintraege) - vorher nur per manueller config.json-Bearbeitung
// moeglich. mqttEditState haelt fest, ob das Formular gerade einen
// bestehenden Eintrag bearbeitet (dann PUT statt POST beim Absenden).
// ----------------------------------------------------------------------
let mqttEditState = null; // { printerId, extraId } oder null (= "neu anlegen")

function toggleMqttKindFields(){
  const kind = document.getElementById('mq_kind').value;
  document.getElementById('mqttSensorFields').style.display = (kind === 'sensor') ? 'block' : 'none';
  document.getElementById('mqttSwitchFields').style.display = (kind === 'switch') ? 'block' : 'none';
}

function populateMqttPrinterSelect(selectedId){
  const sel = document.getElementById('mq_printer');
  // v2.5.0: zusaetzliche Option fuer einen Sensor/Schalter OHNE
  // Druckerzuordnung (leerer Wert) - behebt den Fehler, dass sich ohne
  // mindestens einen bestehenden Drucker ueberhaupt kein Sensor/Schalter
  // anlegen liess (siehe submitMqttExtra()).
  sel.innerHTML = '<option value="">Kein Drucker (eigenstaendig)</option>' +
    lastPrinterList.map(p => `<option value="${p.id}">${p.name}</option>`).join('');
  sel.value = selectedId || '';
}

async function renderMqttExtrasList(){
  const list = document.getElementById('mqttExtrasList');
  const rows = [];
  lastPrinterList.forEach(p => {
    (p.extras || []).forEach(e => {
      const displayLabel = { generic: 'Sensoren-Bereich', temperature: 'Temperaturen-Bereich', humidity: 'Feuchte-Bereich' }[e.display] || 'Sensoren-Bereich';
      const sub = (e.kind === 'switch')
        ? `Schalter &middot; Befehls-Topic: ${e.command_topic}`
        : `Sensor &middot; Topic: ${e.topic}${e.unit ? ' &middot; Einheit: ' + e.unit : ''} &middot; Anzeige: ${displayLabel}`;
      rows.push(`<div class="mqtt-extra-row">
        <div class="mqtt-extra-info">
          <div><b>${e.label}</b> (${p.name})</div>
          <div class="mqtt-extra-sub">${sub}</div>
        </div>
        <div>
          <button class="btn-mini" onclick="startEditMqttExtra('${p.id}','${e.id}')">${t('btn_edit')}</button>
          <button class="btn-mini btn-delete" onclick="deleteMqttExtra('${p.id}','${e.id}')">${t('btn_delete')}</button>
        </div>
      </div>`);
    });
  });
  // v2.5.0: eigenstaendige (druckerunabhaengige) Eintraege - frisch vom
  // Server geladen (nicht aus lastStandaloneExtrasList, damit die Liste
  // auch direkt nach dem Anlegen/Bearbeiten/Loeschen sofort aktuell ist,
  // ohne auf den naechsten regulaeren refresh()-Zyklus zu warten).
  try{
    const res = await fetch('/api/standalone_extras');
    lastStandaloneExtrasList = await res.json();
  } catch(e){ /* Liste bleibt auf dem letzten bekannten Stand */ }
  lastStandaloneExtrasList.forEach(e => {
    const displayLabel = { generic: 'Sensoren-Bereich', temperature: 'Temperaturen-Bereich', humidity: 'Feuchte-Bereich' }[e.display] || 'Sensoren-Bereich';
    const sub = (e.kind === 'switch')
      ? `Schalter &middot; Befehls-Topic: ${e.command_topic}`
      : `Sensor &middot; Topic: ${e.topic}${e.unit ? ' &middot; Einheit: ' + e.unit : ''} &middot; Anzeige: ${displayLabel}`;
    // v2.5.0: eigenstaendige Eintraege koennen, analog zu Druckern und
    // externen Kameras, einem Raum zugewiesen werden, damit sie sich im
    // Bedien-Modus sinnvoll einsortieren - ueber ein Dropdown direkt in
    // dieser Zeile (lastGroupList ist bereits ueber refreshSettingsPanel()
    // befuellt, bevor dieser Dialog aus dem Einstellungen-Modus heraus
    // geoeffnet werden kann).
    const groupOptions = '<option value="">Ohne Raum</option>' + lastGroupList.map(g =>
      `<option value="${g.id}" ${e.group_id === g.id ? 'selected' : ''}>${g.name}</option>`).join('');
    rows.push(`<div class="mqtt-extra-row">
      <div class="mqtt-extra-info">
        <div><b>${e.label}</b> (kein Drucker)</div>
        <div class="mqtt-extra-sub">${sub}</div>
      </div>
      <div>
        <select onchange="assignStandaloneExtraGroup('${e.id}', this.value)">${groupOptions}</select>
        <button class="btn-mini" onclick="startEditMqttExtra('','${e.id}')">${t('btn_edit')}</button>
        <button class="btn-mini btn-delete" onclick="deleteMqttExtra('','${e.id}')">${t('btn_delete')}</button>
      </div>
    </div>`);
  });
  list.innerHTML = rows.length ? rows.join('') : 'Noch keine Sensoren/Schalter angelegt.';
}

async function refreshMqttDiscovered(){
  const list = document.getElementById('mqttDiscoveredList');
  try{
    const res = await fetch('/api/extras_mqtt/discovered');
    const topics = await res.json();
    if(!topics || topics.length === 0){
      list.innerHTML = 'Noch keine Nachrichten vom Broker empfangen.';
      return;
    }
    list.innerHTML = topics.map(t =>
      `<div class="mqtt-discovered-row" onclick="useDiscoveredTopic('${t.topic}')">
        <span>${t.topic}</span><span>${t.value}</span>
      </div>`
    ).join('');
  } catch(e){
    list.innerHTML = 'Themenliste konnte nicht geladen werden.';
  }
}

function useDiscoveredTopic(topic){
  // Nur beim Sensor sinnvoll (Schalter-Topics werden von diesem
  // Dashboard selbst veroeffentlicht, nicht empfangen) - schaltet bei
  // Bedarf automatisch auf "Sensor" um, damit das richtige Feld sichtbar ist.
  document.getElementById('mq_kind').value = 'sensor';
  toggleMqttKindFields();
  document.getElementById('mq_topic').value = topic;
}

// v2.5.1: laedt die Broker-Einstellungen in die jetzt INLINE im
// "MQTT-Geraete"-Abschnitt sitzenden Felder und baut die Eintragsliste
// auf - wird von refreshSettingsPanel() aufgerufen (wie
// refreshPrinterManageList()/refreshGroupsManageList()/
// refreshCamerasManageList()), nicht mehr erst beim Oeffnen eines
// eigenen Modals (das gab es vor v2.5.1 nur fuer den MQTT-Bereich, als
// einzigen Abschnitt mit abweichendem Bedienkonzept).
async function refreshMqttSettingsSection(){
  renderMqttExtrasList();
  try{
    const res = await fetch('/api/extras_mqtt');
    const cfg = await res.json();
    document.getElementById('mq_enabled').checked = !!cfg.enabled;
    document.getElementById('mq_host').value = cfg.host || '';
    document.getElementById('mq_port').value = cfg.port || 1883;
    document.getElementById('mq_user').value = cfg.username || '';
    document.getElementById('mq_pass').value = '';
    document.getElementById('mq_tls').checked = !!cfg.tls;
  } catch(e){
    // Broker-Einstellungen konnten nicht geladen werden - Formular
    // bleibt leer, Sensor-/Schalter-Verwaltung funktioniert trotzdem.
  }
}

async function saveExtrasMqttSettings(){
  const body = {
    enabled: document.getElementById('mq_enabled').checked,
    host: document.getElementById('mq_host').value.trim(),
    port: document.getElementById('mq_port').value.trim() || 1883,
    username: document.getElementById('mq_user').value.trim(),
    tls: document.getElementById('mq_tls').checked,
  };
  const pass = document.getElementById('mq_pass').value;
  if(pass !== '') body.password = pass; // leer gelassen = Passwort unveraendert (siehe Backend)

  let data;
  try{
    const res = await fetch('/api/extras_mqtt', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
    });
    data = await res.json();
    if(!res.ok){
      showToast(data.error || 'Fehler beim Speichern der Broker-Einstellungen.', 'err');
      return;
    }
  } catch(e){
    showToast('Netzwerkfehler beim Speichern der Broker-Einstellungen.', 'err');
    return;
  }
  document.getElementById('mq_pass').value = '';
  document.getElementById('mqttStatusHint').textContent =
    'Gespeichert - Verbindung wird neu aufgebaut. Empfangene Topics erscheinen nach kurzer Zeit im Anlegen-Dialog.';
}

function resetMqttExtraForm(){
  document.getElementById('mq_kind').value = 'sensor';
  document.getElementById('mq_label').value = '';
  document.getElementById('mq_topic').value = '';
  document.getElementById('mq_unit').value = '';
  document.getElementById('mq_display').value = 'generic';
  document.getElementById('mq_cmd_topic').value = '';
  document.getElementById('mq_payload_on').value = '';
  document.getElementById('mq_payload_off').value = '';
  document.getElementById('mq_kind').disabled = false;
  document.getElementById('mq_printer').disabled = false;
  toggleMqttKindFields();
}

// v2.5.1: oeffnet das Modal fuer einen NEUEN Eintrag - Gegenstueck zu
// startEditMqttExtra() weiter unten (Bearbeiten). Ersetzt das bisherige
// openMqttModal(), das zusaetzlich noch die Broker-Einstellungen und die
// komplette Liste geladen hat - beides sitzt seit v2.5.1 bereits inline
// im Einstellungen-Modus (siehe refreshMqttSettingsSection()).
function openAddMqttExtraModal(){
  mqttEditState = null;
  document.getElementById('mqttError').style.display = 'none';
  document.getElementById('mqttExtraModalTitle').textContent = 'Sensor/Schalter hinzufuegen';
  document.getElementById('mqttSubmitBtn').textContent = 'Hinzufuegen';
  resetMqttExtraForm();
  populateMqttPrinterSelect();
  refreshMqttDiscovered();
  document.getElementById('mqttExtraModal').classList.add('show');
}

function closeMqttExtraModal(){
  document.getElementById('mqttExtraModal').classList.remove('show');
  mqttEditState = null;
}

function startEditMqttExtra(printerId, extraId){
  // v2.5.0: printerId === '' bedeutet "eigenstaendiger Eintrag ohne
  // Drucker" - dann wird in lastStandaloneExtrasList statt in einem
  // bestimmten Drucker nachgeschlagen (siehe renderMqttExtrasList()).
  let e;
  if(printerId){
    const p = lastPrinterList.find(x => x.id === printerId);
    e = p && (p.extras || []).find(x => x.id === extraId);
  } else {
    e = lastStandaloneExtrasList.find(x => x.id === extraId);
  }
  if(!e) return;
  mqttEditState = { printerId, extraId };
  document.getElementById('mqttError').style.display = 'none';
  resetMqttExtraForm();
  populateMqttPrinterSelect(printerId);
  document.getElementById('mq_printer').disabled = true; // Zuordnung zum Drucker aendert sich beim Bearbeiten nicht
  document.getElementById('mq_kind').value = e.kind;
  document.getElementById('mq_kind').disabled = true; // Art (Sensor/Schalter) laesst sich nachtraeglich nicht wechseln
  toggleMqttKindFields();
  document.getElementById('mq_label').value = e.label || '';
  if(e.kind === 'switch'){
    document.getElementById('mq_cmd_topic').value = e.command_topic || '';
    document.getElementById('mq_payload_on').value = e.payload_on || '';
    document.getElementById('mq_payload_off').value = e.payload_off || '';
  } else {
    document.getElementById('mq_topic').value = e.topic || '';
    document.getElementById('mq_unit').value = e.unit || '';
    document.getElementById('mq_display').value = e.display || 'generic';
  }
  document.getElementById('mqttExtraModalTitle').textContent = 'Eintrag bearbeiten';
  document.getElementById('mqttSubmitBtn').textContent = 'Aktualisieren';
  refreshMqttDiscovered();
  document.getElementById('mqttExtraModal').classList.add('show');
}

async function submitMqttExtra(){
  const kind = document.getElementById('mq_kind').value;
  const body = {
    kind: kind,
    label: document.getElementById('mq_label').value.trim(),
  };
  if(kind === 'sensor'){
    body.topic = document.getElementById('mq_topic').value.trim();
    body.unit = document.getElementById('mq_unit').value.trim();
    body.display = document.getElementById('mq_display').value;
  } else {
    body.command_topic = document.getElementById('mq_cmd_topic').value.trim();
    body.payload_on = document.getElementById('mq_payload_on').value.trim();
    body.payload_off = document.getElementById('mq_payload_off').value.trim();
  }

  const err = document.getElementById('mqttError');
  let res;
  // v2.5.0: ein leerer printerId-Wert ("Kein Drucker (eigenstaendig)")
  // fuehrt jetzt zum neuen, druckerunabhaengigen Endpunkt statt zu einer
  // wortlosen Fehlermeldung - behebt den gemeldeten Fehler, dass sich
  // ohne Drucker-Zuordnung gar kein Sensor/Schalter anlegen liess.
  if(mqttEditState){
    res = mqttEditState.printerId
      ? await fetch('/api/printers/' + mqttEditState.printerId + '/extras/' + mqttEditState.extraId, {
          method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
        })
      : await fetch('/api/standalone_extras/' + mqttEditState.extraId, {
          method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
        });
  } else {
    const printerId = document.getElementById('mq_printer').value;
    res = printerId
      ? await fetch('/api/printers/' + printerId + '/extras', {
          method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
        })
      : await fetch('/api/standalone_extras', {
          method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
        });
  }
  const data = await res.json();
  if(!res.ok){
    err.textContent = data.error || 'Fehler beim Speichern.';
    err.style.display = 'block';
    return;
  }
  err.style.display = 'none';
  closeMqttExtraModal();
  await refresh();
  renderMqttExtrasList();
}

async function deleteMqttExtra(printerId, extraId){
  if(!confirm('Diesen Eintrag wirklich loeschen?')) return;
  if(printerId){
    await fetch('/api/printers/' + printerId + '/extras/' + extraId, { method:'DELETE' });
  } else {
    await fetch('/api/standalone_extras/' + extraId, { method:'DELETE' });
  }
  if(mqttEditState && mqttEditState.printerId === printerId && mqttEditState.extraId === extraId){
    closeMqttExtraModal();
  }
  await refresh();
  renderMqttExtrasList();
}

// v2.5.0: Raum-Zuweisung eines eigenstaendigen Sensors/Schalters - siehe
// renderMqttExtrasList() fuer das Dropdown, das dies aufruft.
async function assignStandaloneExtraGroup(extraId, groupId){
  await fetch('/api/standalone_extras/' + extraId + '/group', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ group_id: groupId || null })
  });
  await refresh();
  renderMqttExtrasList();
}

async function deletePrinter(id){
  if(!confirm('Diesen Drucker wirklich entfernen?')) return;
  await fetch('/api/printers/' + id, { method:'DELETE' });
  // v2.3.0: wird jetzt nur noch aus dem Einstellungen-Modus heraus
  // aufgerufen (siehe refreshPrinterManageList()) - dort muss die
  // Verwaltungsliste selbst aktualisiert werden, refresh() allein wuerde
  // nur die (dort ausgeblendete) Bedienansicht aktualisieren.
  if(settingsMode) refreshSettingsPanel();
  else refresh();
}

function openCam(id){
  openCamUrl('/camera/' + id + '?_=' + Date.now());
}

// v2.3.0: aus openCam(id) herausgezogen, damit dasselbe Anzeige-Modal
// (inkl. Klartext-Fehleranzeige, siehe Kommentar unten) auch fuer die neuen,
// vom Drucker unabhaengigen externen RTSP-Kameras genutzt werden kann
// (siehe openExternalCam()) - reiner Code-Reuse, Verhalten fuer openCam(id)
// selbst unveraendert.
function openCamUrl(url){
  const img = document.getElementById('camImg');
  const errBox = document.getElementById('camError');
  errBox.style.display = 'none';
  errBox.textContent = '';
  img.style.display = '';
  // MK6 v2.2.22: bei Fehlern (z. B. "LAN Only Liveview" am Drucker nicht
  // aktiviert, FFmpeg fehlt, ...) liefert /camera/<id> seit der RTSPS-
  // Unterstuetzung fuer X1/P1/P2/H2/X2 einen kurzen Klartext-Fehler statt
  // eines Bildes - der bricht das <img> mit "onerror" ab. Statt nur ein
  // kaputtes Bild-Icon zu zeigen, wird derselbe Pfad dann noch einmal per
  // fetch() als Text abgerufen (schnelle, kurze Fehlerantwort - kein
  // zweiter Dauerstream) und die eigentliche, konkrete Fehlermeldung
  // angezeigt.
  img.onerror = function(){
    img.style.display = 'none';
    fetch(url).then(function(r){
      return r.text().then(function(t){ return {status: r.status, text: t}; });
    }).then(function(res){
      errBox.textContent = res.text || ('Kamera-Stream konnte nicht geladen werden (HTTP ' + res.status + ').');
      errBox.style.display = '';
    }).catch(function(){
      errBox.textContent = 'Kamera-Stream konnte nicht geladen werden.';
      errBox.style.display = '';
    });
  };
  img.src = url;
  document.getElementById('camModal').classList.add('show');
}
function closeCam(){
  const img = document.getElementById('camImg');
  document.getElementById('camModal').classList.remove('show');
  img.onerror = null;
  img.src = '';
  document.getElementById('camError').style.display = 'none';
}

// MK6: Druckauftrags-Verlauf (Untermenue je Drucker-Kachel) -----------
let historyModalPrinterId = null;
// MK6 v1.2.0: 'date' (Backend liefert bereits neueste zuerst) oder 'alpha'
// (Dateiname A-Z) - rein clientseitig, kein erneuter Server-Request noetig.
let historySortMode = 'date';
let lastHistoryEntries = [];

async function openHistoryModal(printerId){
  historyModalPrinterId = printerId;
  historySortMode = 'date';
  document.getElementById('historyModalBody').innerHTML = '<div class="history-empty">Wird geladen ...</div>';
  document.getElementById('historyModal').classList.add('show');
  await refreshHistoryModal();
}

function closeHistoryModal(){
  document.getElementById('historyModal').classList.remove('show');
  document.getElementById('historyModalBody').innerHTML = '';
  historyModalPrinterId = null;
}

async function refreshHistoryModal(){
  const printerId = historyModalPrinterId;
  if(!printerId) return;
  const body = document.getElementById('historyModalBody');
  let entries;
  try{
    const res = await fetch('/api/printers/' + printerId + '/history');
    entries = await res.json();
  } catch(e){
    body.innerHTML = '<div class="history-empty">Verlauf konnte nicht geladen werden.</div>';
    return;
  }
  if(historyModalPrinterId !== printerId) return; // Modal wurde inzwischen geschlossen/gewechselt
  lastHistoryEntries = entries || [];
  renderHistoryEntries();
}

function toggleHistorySort(){
  historySortMode = (historySortMode === 'date') ? 'alpha' : 'date';
  renderHistoryEntries();
}

function renderHistoryEntries(){
  const printerId = historyModalPrinterId;
  const body = document.getElementById('historyModalBody');
  const sortBtn = document.getElementById('historySortBtn');
  if(sortBtn){
    sortBtn.textContent = (historySortMode === 'date') ? t('sort_newest_first') : t('sort_alpha');
  }
  if(!lastHistoryEntries.length){
    body.innerHTML = `<div class="history-empty">${t('history_empty')}</div>`;
    return;
  }
  // 'date': Backend liefert bereits neueste zuerst - unveraendert uebernehmen.
  // 'alpha': Kopie sortieren, damit lastHistoryEntries (Backend-Reihenfolge)
  // beim naechsten Umschalten zurueck auf 'date' erhalten bleibt.
  const entries = (historySortMode === 'alpha')
    ? [...lastHistoryEntries].sort((a, b) => a.filename.localeCompare(b.filename, 'de'))
    : lastHistoryEntries;
  body.innerHTML = entries.map(e => {
    const thumb = e.has_image
      ? `<img class="history-thumb" src="/api/printers/${printerId}/history/${e.job_id}/thumbnail" alt="">`
      : `<div class="history-thumb-placeholder">${FILE_ICON}</div>`;
    const durText = formatDuration(e.duration_sec);
    const durHtml = durText ? ` &middot; Druckzeit ca. ${durText}` : '';
    return `
      <div class="history-item">
        ${thumb}
        <div class="history-body">
          <div class="history-filename">${e.filename}</div>
          <div class="history-date">${e.sent_at}${durHtml}</div>
        </div>
        <div class="history-actions">
          <button class="btn-mini" onclick="reprintHistoryEntry('${printerId}','${e.job_id}')">Erneut drucken</button>
          <button class="btn-mini" onclick="addHistoryEntryToQueue('${printerId}','${e.job_id}')">In Warteschlange</button>
          <button class="btn-mini" onclick="openAssignModal('history','${printerId}','${e.job_id}')">${t('btn_assign')}</button>
          <button class="btn-mini btn-delete" onclick="deleteHistoryEntry('${printerId}','${e.job_id}')">${t('btn_delete')}</button>
        </div>
      </div>`;
  }).join('');
}

async function deleteHistoryEntry(printerId, jobId){
  if(!confirm('Diesen Druckauftrag wirklich aus dem Verlauf entfernen?')) return;
  try{
    const res = await fetch('/api/printers/' + printerId + '/history/' + jobId, { method:'DELETE' });
    if(!res.ok){
      const data = await res.json().catch(() => ({}));
      showToast(data.error || 'Fehler beim Loeschen.', 'err');
      return;
    }
  } catch(e){
    showToast('Netzwerkfehler beim Loeschen.', 'err');
    return;
  }
  await refreshHistoryModal();
}

async function reprintHistoryEntry(printerId, jobId){
  try{
    const res = await fetch('/api/printers/' + printerId + '/history/' + jobId + '/reprint', { method: 'POST' });
    const data = await res.json();
    if(!res.ok){
      showToast(data.error || 'Fehler beim erneuten Senden.', 'err');
      return;
    }
    // MK6 v1.2.0: Drucker war beschaeftigt - Auftrag wurde in die
    // Warteschlange gelegt, statt sofort erneut gesendet zu werden.
    if(data.mode === 'queued'){
      closeHistoryModal();
      showToast('Drucker ist beschaeftigt - Auftrag wurde in die Warteschlange gelegt.', 'ok');
      return;
    }
    if(data.mode === 'ultimaker'){
      closeHistoryModal();
      showToast('Druckauftrag wird erneut gesendet ...', 'ok');
      // Kein echtes DOM-Element noetig - pollUltimakerProgress() will
      // darauf am Ende nur die 'uploading'-Klasse entfernen.
      await pollUltimakerProgress(printerId, data.job_id, { classList: { add(){}, remove(){} } });
    } else {
      closeHistoryModal();
      openAmsModal(printerId, data);
    }
  } catch(e){
    showToast('Netzwerkfehler beim erneuten Senden.', 'err');
  }
}

async function addHistoryEntryToQueue(printerId, jobId){
  try{
    const res = await fetch('/api/printers/' + printerId + '/history/' + jobId + '/queue', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({})
    });
    const data = await res.json();
    if(!res.ok){
      showToast(data.error || 'Fehler beim Hinzufuegen zur Warteschlange.', 'err');
      return;
    }
    showToast('In die Warteschlange gelegt.', 'ok');
  } catch(e){
    showToast('Netzwerkfehler beim Hinzufuegen zur Warteschlange.', 'err');
  }
}

// MK6 v1.2.0: Warteschlange (Untermenue je Drucker-Kachel) ------------
let queueModalPrinterId = null;
let queueModalHasEntries = false;  // v2.0.1: fuer updateQueueSendButtonState()

async function openQueueModal(printerId){
  queueModalPrinterId = printerId;
  queueModalHasEntries = false;
  document.getElementById('queueModalBody').innerHTML = '<div class="history-empty">Wird geladen ...</div>';
  document.getElementById('queueModal').classList.add('show');
  await refreshQueueModal();
}

function closeQueueModal(){
  document.getElementById('queueModal').classList.remove('show');
  document.getElementById('queueModalBody').innerHTML = '';
  queueModalPrinterId = null;
}

// v2.0.1: Aktiviert/deaktiviert den "Druckraum leer"-Knopf anhand des
// zuletzt bekannten Druckerstatus (aus lastPrinterList, siehe refresh())
// - bei Bambu Lab wird dafuer EXPLIZIT der Status FINISH, IDLE oder (seit
// v2.1.1) FAILED verlangt (nicht nur "nicht am Drucken"), siehe
// DashboardApp.is_ready_for_next_print() fuer die serverseitige
// Gegenpruefung, die in jedem Fall zusaetzlich greift. Wird sowohl nach
// jedem Laden/Aendern der Warteschlange als auch bei jedem regulaeren
// 2,5-Sekunden-Status-Poll aufgerufen (siehe refresh()), damit der Knopf
// automatisch aktiv wird, sobald der laufende Druck fertig ist oder
// fehlgeschlagen ist, ohne dass der Nutzer das Modal schliessen/neu
// oeffnen muss.
// v2.1.1 - BUGFIX: vorher fehlte "FAILED" in dieser Liste (obwohl
// BAMBU_READY_FOR_NEXT_STATES es serverseitig bereits erlaubte) - ein
// fehlgeschlagener Druck liess den Knopf dauerhaft deaktiviert stehen,
// die Warteschlange war damit blockiert, bis ein neuer Druck ausserhalb
// der Warteschlange gestartet wurde.
function updateQueueSendButtonState(){
  const btn = document.getElementById('queueSendNextBtn');
  const hint = document.getElementById('queueSendHint');
  if(!btn || !queueModalPrinterId) return;
  const p = lastPrinterList.find(x => x.id === queueModalPrinterId);
  const state = (p && p.gcode_state) ? String(p.gcode_state).toUpperCase() : '';
  const isBambu = p && p.type === 'bambu';
  const ready = isBambu ? ['FINISH', 'IDLE', 'FAILED'].includes(state) : !PRINTER_BUSY_STATES_JS.includes(state);

  if(!queueModalHasEntries){
    btn.disabled = true;
    hint.textContent = 'Die Warteschlange ist leer.';
  } else if(!ready){
    btn.disabled = true;
    hint.textContent = isBambu
      ? `Warten, bis der Drucker fertig ist (aktueller Status: ${state || 'unbekannt'}).`
      : `Warten, bis der Drucker fertig ist (aktueller Status: ${state || 'unbekannt'}).`;
  } else {
    btn.disabled = false;
    hint.textContent = '';
  }
}

async function refreshQueueModal(){
  const printerId = queueModalPrinterId;
  if(!printerId) return;
  const body = document.getElementById('queueModalBody');
  let entries;
  try{
    const res = await fetch('/api/printers/' + printerId + '/queue');
    entries = await res.json();
  } catch(e){
    body.innerHTML = '<div class="history-empty">Warteschlange konnte nicht geladen werden.</div>';
    queueModalHasEntries = false;
    updateQueueSendButtonState();
    return;
  }
  if(queueModalPrinterId !== printerId) return; // Modal wurde inzwischen geschlossen/gewechselt
  queueModalHasEntries = !!(entries && entries.length);
  updateQueueSendButtonState();
  if(!entries || entries.length === 0){
    body.innerHTML = '<div class="history-empty">Die Warteschlange ist leer.</div>';
    return;
  }
  // Aeltester (=naechster) Auftrag zuerst - siehe PrintQueueStore-Kommentar.
  body.innerHTML = entries.map((e, i) => {
    const thumb = e.has_image
      ? `<img class="history-thumb" src="/api/printers/${printerId}/queue/${e.job_id}/thumbnail" alt="">`
      : `<div class="history-thumb-placeholder">${FILE_ICON}</div>`;
    const label = (i === 0) ? '<b>Naechster:</b> ' : '';
    const durText = formatDuration(e.duration_sec);
    const durHtml = durText ? ` &middot; Druckzeit ca. ${durText}` : '';
    return `
      <div class="history-item queue-item">
        <div class="queue-order-btns">
          <button class="btn-mini" ${i === 0 ? 'disabled' : ''} title="Nach oben" onclick="moveQueueEntry('${printerId}','${e.job_id}',-1)">&uarr;</button>
          <button class="btn-mini" ${i === entries.length - 1 ? 'disabled' : ''} title="Nach unten" onclick="moveQueueEntry('${printerId}','${e.job_id}',1)">&darr;</button>
        </div>
        ${thumb}
        <div class="history-body">
          <div class="history-filename">${label}${e.filename}</div>
          <div class="history-date">In Warteschlange seit ${e.added_at}${durHtml}</div>
        </div>
        <div class="history-actions">
          <button class="btn-mini" onclick="openAssignModal('queue','${printerId}','${e.job_id}')">${t('btn_assign')}</button>
          <button class="btn-mini btn-delete" onclick="deleteQueueEntry('${printerId}','${e.job_id}')">${t('btn_delete')}</button>
        </div>
      </div>`;
  }).join('');
}

async function moveQueueEntry(printerId, jobId, direction){
  let entries;
  try{
    const res = await fetch('/api/printers/' + printerId + '/queue');
    entries = await res.json();
  } catch(e){
    showToast('Netzwerkfehler beim Umsortieren.', 'err');
    return;
  }
  const ids = entries.map(e => e.job_id);
  const idx = ids.indexOf(jobId);
  const newIdx = idx + direction;
  if(idx < 0 || newIdx < 0 || newIdx >= ids.length) return;
  [ids[idx], ids[newIdx]] = [ids[newIdx], ids[idx]];
  try{
    const res = await fetch('/api/printers/' + printerId + '/queue/reorder', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({order: ids})
    });
    if(!res.ok){
      const data = await res.json().catch(() => ({}));
      showToast(data.error || 'Reihenfolge konnte nicht geaendert werden.', 'err');
      return;
    }
  } catch(e){
    showToast('Netzwerkfehler beim Umsortieren.', 'err');
    return;
  }
  await refreshQueueModal();
}

async function deleteQueueEntry(printerId, jobId){
  if(!confirm('Diesen Auftrag wirklich aus der Warteschlange entfernen?')) return;
  try{
    const res = await fetch('/api/printers/' + printerId + '/queue/' + jobId, { method:'DELETE' });
    if(!res.ok){
      const data = await res.json().catch(() => ({}));
      showToast(data.error || 'Fehler beim Loeschen.', 'err');
      return;
    }
  } catch(e){
    showToast('Netzwerkfehler beim Loeschen.', 'err');
    return;
  }
  await refreshQueueModal();
}

// MK6 v2.1.0: gemeinsame Upload-Logik fuer "Datei auswaehlen" (addFileToQueue)
// UND Drag&Drop (dzDropQueue) im Warteschlangen-Modal - vermeidet doppelten
// Code fuer beide Wege, eine Datei in die Warteschlange zu legen.
async function uploadFileToQueue(printerId, file){
  if(!file || !printerId) return;
  const form = new FormData();
  form.append('file', file);
  try{
    const res = await fetch('/api/printers/' + printerId + '/queue', { method:'POST', body: form });
    const data = await res.json();
    if(!res.ok){
      showToast(data.error || 'Fehler beim Hinzufuegen zur Warteschlange.', 'err');
    } else {
      showToast('Datei wurde in die Warteschlange gelegt.', 'ok');
    }
  } catch(e){
    showToast('Netzwerkfehler beim Hochladen.', 'err');
  }
  await refreshQueueModal();
}

async function addFileToQueue(printerId, fileInput){
  const file = fileInput.files && fileInput.files[0];
  if(!file || !printerId) return;
  try{
    await uploadFileToQueue(printerId, file);
  } finally {
    fileInput.value = '';
  }
}

// MK6 v2.1.0: Drag&Drop einer Datei auf die Drop-Zone im Warteschlangen-Modal -
// analog zu dzDrop()/dzDropUltimaker() auf der Drucker-Kachel selbst. Die
// erwartete Dateiendung haengt vom Druckertyp des gerade geoeffneten Modals ab.
async function dzDropQueue(ev){
  ev.preventDefault();
  const zone = ev.currentTarget;
  zone.classList.remove('dragover');
  const printerId = queueModalPrinterId;
  if(!printerId) return;
  const files = ev.dataTransfer.files;
  if(!files || files.length === 0) return;
  const file = files[0];

  const p = lastPrinterList.find(x => x.id === printerId);
  const isUltimaker = p && p.type === 'ultimaker';
  const name = file.name.toLowerCase();
  const okExt = isUltimaker ? name.endsWith('.gcode') : name.endsWith('.gcode.3mf');
  if(!okExt){
    showToast(isUltimaker ? 'Nur .gcode-Dateien werden unterstuetzt.' : 'Nur .gcode.3mf-Dateien werden unterstuetzt.', 'err');
    return;
  }

  zone.classList.add('uploading');
  try{
    await uploadFileToQueue(printerId, file);
  } finally {
    zone.classList.remove('uploading');
  }
}

async function sendNextQueued(printerId){
  if(!printerId) return;
  try{
    const res = await fetch('/api/printers/' + printerId + '/queue/next', { method: 'POST' });
    const data = await res.json();
    if(!res.ok){
      showToast(data.error || 'Naechster Auftrag konnte nicht gesendet werden.', 'err');
      return;
    }
    closeQueueModal();
    if(data.mode === 'ultimaker'){
      showToast('Naechster Druckauftrag wird gesendet ...', 'ok');
      await pollUltimakerProgress(printerId, data.job_id, { classList: { add(){}, remove(){} } });
    } else {
      openAmsModal(printerId, data);
    }
  } catch(e){
    showToast('Netzwerkfehler beim Senden.', 'err');
  }
}

// MK6 v1.2.0: Auftrag (Verlauf oder Warteschlange) einem anderen Drucker
// im Dashboard zuweisen -----------------------------------------------
let assignContext = null; // {kind: 'history'|'queue', printerId, jobId}

function openAssignModal(kind, printerId, jobId){
  assignContext = { kind, printerId, jobId };
  const sourceP = lastPrinterList.find(p => p.id === printerId);
  const sourceType = sourceP ? sourceP.type : null;
  // MK6 v2.1.0: bei Bambu Lab darf nur einem Drucker DERSELBEN Druckerfamilie
  // zugewiesen werden (z.B. nur A1 untereinander, nur X1 untereinander) -
  // analog zur Pruefung in _validate_assign_target() im Backend.
  const sourceFamily = sourceP ? sourceP.bambu_family : null;
  const sel = document.getElementById('assignTargetSelect');
  sel.innerHTML = lastPrinterList
    .filter(p => p.id !== printerId && p.type === sourceType &&
                 (sourceType !== 'bambu' || p.bambu_family === sourceFamily))
    .map(p => `<option value="${p.id}">${p.name} (${p.type === 'bambu' ? 'Bambu Lab' : 'Ultimaker'})</option>`)
    .join('');
  if(!sel.options.length){
    showToast(sourceType === 'bambu'
      ? 'Kein anderer Bambu-Lab-Drucker derselben Druckerfamilie im Dashboard vorhanden.'
      : 'Kein anderer passender Drucker im Dashboard vorhanden.', 'err');
    assignContext = null;
    return;
  }
  document.getElementById('assignModal').classList.add('show');
}

function closeAssignModal(){
  document.getElementById('assignModal').classList.remove('show');
  assignContext = null;
}

async function confirmAssign(){
  if(!assignContext) return;
  const targetId = document.getElementById('assignTargetSelect').value;
  const { kind, printerId, jobId } = assignContext;
  const url = (kind === 'queue')
    ? `/api/printers/${printerId}/queue/${jobId}/assign`
    : `/api/printers/${printerId}/history/${jobId}/queue`;
  try{
    const res = await fetch(url, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({target_printer_id: targetId})
    });
    const data = await res.json();
    if(!res.ok){
      showToast(data.error || 'Zuweisung fehlgeschlagen.', 'err');
      return;
    }
    showToast('Auftrag wurde zugewiesen.', 'ok');
    closeAssignModal();
    if(kind === 'queue') await refreshQueueModal();
    else await refreshHistoryModal();
  } catch(e){
    showToast('Netzwerkfehler bei der Zuweisung.', 'err');
  }
}

async function extraCommand(printerId, extraId, action){
  await fetch(`/api/printers/${printerId}/extras/${extraId}/command`, {
    method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action})
  });
}

// v2.5.0: wie extraCommand(), fuer einen eigenstaendigen (nicht an einen
// Drucker gebundenen) Schalter - siehe cardForStandaloneExtra().
async function standaloneExtraCommand(extraId, action){
  await fetch(`/api/standalone_extras/${extraId}/command`, {
    method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action})
  });
}

// v2.0.1: JS-Spiegel von PRINTER_BUSY_STATES (app.py) - fuer
// updateQueueSendButtonState() (nicht-Bambu-Zweig). Bei Aenderung dort
// auch hier nachziehen.
const PRINTER_BUSY_STATES_JS = ['RUNNING','PRINTING','WASHING','CURING','BUSY','OPERATIONAL','PAUSE','PAUSED'];

function stateClass(state){
  if(!state) return '';
  const s = String(state).toUpperCase();
  if(['RUNNING','PRINTING','WASHING','CURING','BUSY','OPERATIONAL'].includes(s)) return 'running';
  if(['PAUSE','PAUSED'].includes(s)) return 'paused';
  return '';
}

function formatRemaining(totalMinutes){
  if(totalMinutes === undefined || totalMinutes === null) return '';
  const mins = Math.max(0, Math.round(totalMinutes));
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if(h > 0){
    return `${h} h ${m} min verbleibend`;
  }
  return `${m} min verbleibend`;
}

// v2.1.0: rundet eine Temperaturangabe auf HOECHSTENS 2 Nachkommastellen
// (weniger, falls die Zahl von sich aus glatt ist - "23" statt "23.00").
// Manche Backends (v. a. Bambu-MQTT) liefern Temperaturen mit deutlich
// mehr Nachkommastellen, als fuer die Anzeige sinnvoll ist.
function formatTemp(v){
  if(v === undefined || v === null) return '–';
  const n = Math.round(v * 100) / 100;
  return Number.isFinite(n) ? n : '–';
}

// v2.2.0: kleines Verlaufsdiagramm je Temperaturanzeige -----------------
// Rein client-seitig im Browser-Speicher (kein Backend-Persistieren, kein
// zusaetzlicher API-Endpunkt noetig) - fuellt sich aus den ohnehin schon
// alle 2,5 Sekunden abgerufenen Status-Werten (siehe refresh()). Geht beim
// Neuladen der Seite verloren, das ist fuer eine kleine "Trend"-Anzeige
// bewusst in Ordnung (kein Anspruch auf dauerhafte Temperaturhistorie).
const tempHistory = {}; // printerId -> { [feldname]: number[] }
const TEMP_HISTORY_MAX_POINTS = 40; // ~100 Sekunden bei 2,5s-Poll-Takt

function recordTempHistory(printerId, field, value){
  if(value === undefined || value === null) return;
  const n = Number(value);
  if(!Number.isFinite(n)) return;
  if(!tempHistory[printerId]) tempHistory[printerId] = {};
  const bucket = tempHistory[printerId];
  const arr = bucket[field] || (bucket[field] = []);
  arr.push(n);
  if(arr.length > TEMP_HISTORY_MAX_POINTS) arr.shift();
}

// Baut ein kleines Inline-SVG-Liniendiagramm aus den zuletzt erfassten
// Werten - bewusst ohne externe Chart-Bibliothek (das Dashboard bleibt
// eine einzelne Datei / PyInstaller-onefile-tauglich, siehe Kommentar am
// Dateianfang). Liefert einen leeren String, solange weniger als 2 Punkte
// vorliegen (noch keine sinnvolle Linie moeglich, z. B. direkt nach dem
// Start des Dashboards).
// v2.2.2: "cssClass" waehlt die Farbe der Linie aus (siehe CSS -
// "temp-spark" = rot fuer Temperaturen, "humidity-spark" = blau fuer die
// AMS-Luftfeuchtigkeit) - beide nutzen denselben currentColor-Mechanismus,
// nur die jeweilige Klasse setzt eine andere Textfarbe.
function sparklineSvg(values, cssClass){
  if(!values || values.length < 2) return '';
  const w = 54, h = 18, pad = 2;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = (max - min) || 1; // vermeidet Division durch 0 bei konstanter Temperatur
  const step = (w - pad * 2) / (values.length - 1);
  const points = values.map((v, i) => {
    const x = pad + i * step;
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return `<svg class="${cssClass || 'temp-spark'}" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}">` +
         `<polyline points="${points}" fill="none" stroke="currentColor" stroke-width="1.5" ` +
         `stroke-linejoin="round" stroke-linecap="round"/></svg>`;
}

// Gemeinsamer Baustein fuer alle Temperatur-Chips (Bambu/OctoPrint/
// Creality/Ultimaker) - erfasst den aktuellen Wert in tempHistory UND
// rendert Chip + Sparkline in einem Aufwasch, damit das nicht in jeder
// Karten-Renderfunktion einzeln dupliziert werden muss.
function tempChip(printerId, field, label, value){
  recordTempHistory(printerId, field, value);
  const history = (tempHistory[printerId] && tempHistory[printerId][field]) || [];
  // v2.8.0: label wird ueber den Feldnamen uebersetzt (I18N), statt den
  // vom Aufrufer uebergebenen deutschen Text direkt zu verwenden - der
  // dritte Parameter bleibt aus Kompatibilitaetsgruenden erhalten
  // (Fallback, falls field unbekannt ist), wird aber im Normalfall nicht
  // mehr benutzt.
  const key = {nozzle: 'temp_nozzle', bed: 'temp_bed', chamber: 'temp_chamber'}[field];
  const text = key ? t(key) : label;
  return `<div class="temp-chip">${text} <b>${formatTemp(value)}&deg;C</b>${sparklineSvg(history)}</div>`;
}

// v2.2.0: kleines Vorschaubild des aktuellen/zuletzt gestarteten
// Druckauftrags neben dem Fortschrittsbalken - Quelle ist der neueste
// Verlaufseintrag dieses Druckers (current_thumb_job_id/
// current_thumb_has_image, siehe DashboardApp.all_status()), also
// dieselbe Vorschau wie im Verlaufs-Fenster. Bleibt leer, wenn (noch)
// kein ueber das Dashboard gesendeter Auftrag im Verlauf existiert -
// betrifft z. B. OctoPrint/Creality/Formlabs (kein Versand ueber das
// Dashboard moeglich) oder einen frisch angelegten Drucker.
function progressThumb(p){
  if(!p.current_thumb_has_image || !p.current_thumb_job_id) return '';
  return `<img class="progress-thumb" src="/api/printers/${p.id}/history/${p.current_thumb_job_id}/thumbnail" ` +
         `alt="" title="${t('title_progress_thumb')}">`;
}

// v2.2.3: Woertliche Einordnung der Bambu-Feuchte-Stufe (1 = trocken/gut
// bis 5 = feucht/schlecht - dieselbe Skala wie zuvor nur im Tooltip
// genannt). NUTZER-FEEDBACK v2.2.2: der Rohwert allein ("4") war ohne
// Hover auf den Massstab nicht als "eher schlecht" erkennbar - deshalb
// jetzt ZUSAETZLICH als sichtbares Wort neben der Zahl, nicht nur im
// Tooltip. "severity" steuert zusaetzlich die Ampelfarbe der Punkte
// (siehe humidityScale()).
const HUMIDITY_LEVELS = {
  1: { label: 'trocken',      severity: 'good' },
  2: { label: 'leicht feucht', severity: 'good' },
  3: { label: 'mittel',       severity: 'mid'  },
  4: { label: 'feucht',       severity: 'bad'  },
  5: { label: 'sehr feucht',  severity: 'bad'  },
};

// v2.2.2 (erweitert in v2.2.3 um Ampelfarbe + Wort-Label): kleiner 1-5-
// Massstab neben dem Feuchte-Rohwert, damit die Zahl allein eingeordnet
// werden kann. Fuenf Punkte, gefuellt bis einschliesslich der aktuellen
// Stufe UND in Ampelfarbe (gruen=trocken/gut, gelb=mittel, rot=feucht/
// schlecht) statt einheitlich blau - damit "gut oder schlecht" auch ohne
// Hover sofort erkennbar ist. Ein Tooltip nennt die Skala zusaetzlich in
// Worten.
function humidityScale(value){
  if(value === undefined || value === null) return '';
  const level = HUMIDITY_LEVELS[value];
  const severity = level ? level.severity : '';
  const dots = [1, 2, 3, 4, 5].map(i =>
    `<span class="humidity-dot${i <= value ? ' filled ' + severity : ''}"></span>`
  ).join('');
  return `<span class="humidity-scale" title="Feuchte-Stufe: 1 = trocken/gut, 5 = feucht/schlecht">${dots}</span>`;
}

// v2.2.3: sichtbares Wort-Label ("trocken"/"feucht"/...) direkt neben dem
// Zahlenwert, in derselben Ampelfarbe wie der Massstab - siehe
// HUMIDITY_LEVELS oben fuer den Hintergrund dieser Ergaenzung.
function humidityLabel(value){
  const level = HUMIDITY_LEVELS[value];
  if(!level) return '';
  return `<span class="humidity-label ${level.severity}">${level.label}</span>`;
}

// v2.2.1: Chip fuer die AMS-Luftfeuchtigkeit - nutzt bewusst dieselbe
// tempHistory-Infrastruktur wie tempChip() (generischer Werteverlauf,
// nicht spezifisch fuer Temperaturen), da eine Sparkline hier identisch
// funktioniert. Der Rohwert ist eine Bambu-eigene Stufe von 1 (trocken)
// bis 5 (feucht), KEIN Prozentwert - daher ohne Einheit angezeigt, dafuer
// seit v2.2.2 mit humidityScale() als Einordnungshilfe direkt daneben.
// v2.2.2: Sparkline-Linie in Blau (eigene CSS-Klasse "humidity-spark"),
// auf ausdruecklichen Nutzerwunsch von der roten Temperatur-Sparkline
// unterschieden.
// v2.2.7: Nutzer meldete bei einem H2S (AMS 2 Pro), dass der Drucker
// selbst 44% Luftfeuchte anzeigt, das Dashboard aber nur die Stufe "1"
// zeigte - fuer sich genommen nicht falsch, aber ohne die 1-5-Skala im
// Kopf nicht einzuordnen. Recherche ergab: das AMS 2 Pro liefert
// zusaetzlich zur Stufe ("humidity") den tatsaechlichen Prozentwert im
// Feld "humidity_raw" (aeltere AMS-Einheiten liefern dieses Feld gar
// nicht). Ist rawPercent vorhanden, wird JETZT der selbsterklaerende
// Prozentwert als Hauptanzeige verwendet (und auch im Verlaufsdiagramm
// aufgezeichnet) - Wort-Label und Ampel-Punkte bleiben dabei an der
// vom Drucker gelieferten Stufe ("value") ausgerichtet, da nur diese
// die vom Hersteller vorgesehene gut/mittel/schlecht-Einordnung traegt.
// v2.2.12: Nutzer bemerkte eine widerspruechliche Anzeige zwischen zwei
// Druckern - u. a. einen H2-Wert von 41% als "trocken", aber einen
// X1-Wert von 24% als "feucht" (obwohl 24% RH fuer sich genommen eher
// trockener wirkt als 41%). Ursache: Wort-Label und Ampel-Punkte wurden
// bisher IMMER aus der 1-5-Stufe ("value") abgeleitet, auch wenn
// zusaetzlich ein Prozentwert ("rawPercent") vorlag - beide Felder sind
// aber laut Recherche (maziggy/bambuddy Issue #3140) NICHT notwendig
// gleich skaliert: es gibt einen dokumentierten Bug/Eigenheit, wonach die
// 1-5-Rohstufe je nach AMS-Generation in ANDERER Reihenfolge gemeldet
// wird (mal 1=trocken...5=feucht, mal umgekehrt) - welche Richtung ein
// konkretes Geraet tatsaechlich meldet, ist nicht zuverlaessig bekannt
// und wird hier bewusst NICHT geraten (siehe UEBERGABE.md fuer die volle
// Herleitung). Ist ein Prozentwert vorhanden, ist er die praezisere,
// selbsterklaerende Angabe (kein Rate-Massstab noetig) - Wort-Label und
// Punkte werden deshalb JETZT NUR NOCH angezeigt, wenn KEIN Prozentwert
// vorliegt (aeltere AMS-Einheiten ohne humidity_raw). Damit widersprechen
// sich Anzeige und Einordnung nicht mehr.
function humidityChip(printerId, field, label, value, rawPercent){
  const hasRaw = (rawPercent !== undefined && rawPercent !== null);
  const recordedValue = hasRaw ? rawPercent : value;
  recordTempHistory(printerId, field, recordedValue);
  const history = (tempHistory[printerId] && tempHistory[printerId][field]) || [];
  const display = hasRaw ? `${rawPercent}%` : ((value === undefined || value === null) ? '–' : value);
  const levelKnown = !hasRaw && (value !== undefined && value !== null && HUMIDITY_LEVELS[value]);
  return `<div class="temp-chip">${label} <b>${display}</b>${levelKnown ? humidityLabel(value) : ''}${levelKnown ? humidityScale(value) : ''}` +
         `${sparklineSvg(history, 'humidity-spark')}</div>`;
}

// v2.2.16: Chip fuer einen MQTT-Extra-Sensor mit "display": "temperature"
// oder "humidity" (siehe Backend-Feld in _validate_extra_fields()) -
// nutzt bewusst dieselbe tempHistory/sparklineSvg-Infrastruktur wie
// tempChip()/humidityChip() oben, damit ein eigener MQTT-Temperatur-
// oder Feuchtesensor GENAUSO aussieht und sich GENAUSO verhaelt wie die
// vom Drucker selbst gelieferten Werte (Nutzerwunsch: "genau wie die vom
// Drucker uebermittelten Sensordaten"). Der Feld-Schluessel fuer
// tempHistory ist "extra_<id>" - eigener Namensraum, kollidiert also
// nicht mit den festen Feldern "nozzle"/"bed"/"chamber"/"ams_humidity_*".
// Der Rohwert kommt als Text vom zweiten MQTT-Broker (ExtrasMqttManager)
// und wird nur dann als Zahl behandelt/aufgezeichnet, wenn er sich auch
// tatsaechlich in eine Zahl umwandeln laesst (z. B. "23.4") - ein
// nicht-numerischer Sensorwert wird stattdessen unveraendert als Text
// angezeigt, OHNE Sparkline (die braeuchte zwingend Zahlen).
function extraChip(printerId, extra){
  const field = 'extra_' + extra.id;
  const raw = extra.value;
  const num = (raw === undefined || raw === null || raw === '') ? NaN : Number(raw);
  const isNumeric = Number.isFinite(num);
  if(isNumeric) recordTempHistory(printerId, field, num);
  const history = (tempHistory[printerId] && tempHistory[printerId][field]) || [];
  const shown = isNumeric ? formatTemp(num) : ((raw === undefined || raw === null || raw === '') ? '–' : raw);
  const unitSuffix = extra.unit ? extra.unit : '';
  const sparkClass = (extra.display === 'humidity') ? 'humidity-spark' : 'temp-spark';
  return `<div class="temp-chip">${extra.label} <b>${shown}${unitSuffix}</b>${isNumeric ? sparklineSvg(history, sparkClass) : ''}</div>`;
}

// Liefert die Chips ALLER Sensor-Extras eines Druckers, deren "display"
// auf "temperature" oder "humidity" gesetzt ist - zum Einfuegen direkt in
// die bestehende "Temperaturen"-Zeile jeder Karte (renderBambuCard etc.),
// bzw. bei Formlabs (kein eigener Temperaturen-Bereich) fuer eine
// eigens dafuer eingeblendete Zeile. renderExtras() unten blendet
// dieselben Eintraege bewusst aus dem generischen "Sensoren & Schalter"-
// Bereich aus, damit nichts doppelt erscheint.
function extraTempChips(printerId, extras){
  if(!extras || extras.length === 0) return '';
  return extras
    .filter(e => e.kind === 'sensor' && (e.display === 'temperature' || e.display === 'humidity'))
    .map(e => extraChip(printerId, e))
    .join('');
}

function renderAms(printerId, ams, amsUnits, bambuFamily){
  if(!ams || ams.length === 0){
    return '<div class="empty-ams">Kein AMS erkannt / keine Fach-Daten.</div>';
  }
  const slots = ams.map(t => {
    const remain = (t.remain === undefined || t.remain === null || t.remain < 0) ? '–' : t.remain + '%';
    const width = (t.remain && t.remain > 0) ? t.remain : 0;
    return `<div class="ams-slot">
      <div class="ams-swatch" style="background:${t.color}"></div>
      <div class="ams-meta">${t.type}</div>
      <div class="ams-track"><div class="ams-fill" style="width:${width}%; background:${t.color}"></div></div>
      <div class="ams-remain">${remain}</div>
    </div>`;
  }).join('');
  // v2.2.5: Bei der A1-Familie wird das "AMS Lite" verbaut, das (anders
  // als das vollwertige AMS der X1-Serie) KEINEN Feuchtesensor besitzt.
  // Auf ausdruecklichen Nutzerwunsch wird die Feuchteanzeige deshalb bei
  // bambuFamily === 'a1' GRUNDSAETZLICH unterdrueckt - unabhaengig davon,
  // ob/was das AMS Lite an "humidity"-Rohwert meldet (manche Firmware-
  // Staende liefern dort einen bedeutungslosen Platzhalterwert statt gar
  // kein Feld, siehe _apply_print_report() - der reine "Feld vorhanden?"-
  // Filter unten reicht bei der A1-Familie also nicht aus). Analog zur
  // bereits bestehenden Kammertemperatur-Ausblendung fuer A1 (v2.2.0).
  const isA1 = bambuFamily === 'a1';
  // v2.2.1: Luftfeuchtigkeit je AMS-Einheit, mit Verlaufsdiagramm - nur
  // Einheiten mit tatsaechlich vorhandenem Wert werden angezeigt (manche
  // AMS-Firmwarestaende liefern das Feld nicht, siehe _apply_print_report()).
  // v2.2.7: Einheit auch anzeigen, wenn NUR humidity_raw (Prozentwert,
  // AMS 2 Pro) vorhanden ist, ohne die aeltere Stufe "humidity".
  const units = isA1 ? [] : (amsUnits || []).filter(u =>
    (u.humidity !== undefined && u.humidity !== null) ||
    (u.humidity_raw !== undefined && u.humidity_raw !== null)
  );
  const humidityRow = units.length
    ? `<div class="temps ams-humidity-row">${units.map(u =>
        humidityChip(printerId, `ams_humidity_${u.id}`, `Feuchte AMS ${u.id}`, u.humidity, u.humidity_raw)
      ).join('')}</div>`
    : '';
  return slots + humidityRow;
}

function renderExtras(printerId, extras){
  if(!extras || extras.length === 0) return '';
  // v2.2.16: Sensoren mit "display": "temperature"/"humidity" erscheinen
  // stattdessen direkt in der Temperaturen-Zeile (siehe extraTempChips())
  // - hier ausblenden, damit sie nicht zusaetzlich ein zweites Mal im
  // generischen "Sensoren & Schalter"-Bereich auftauchen. Schalter sind
  // von dieser Unterscheidung nicht betroffen (kein "display"-Feld,
  // bleiben immer hier).
  const visible = extras.filter(e => !(e.kind === 'sensor' && (e.display === 'temperature' || e.display === 'humidity')));
  if(visible.length === 0) return '';
  return `<div class="extras-section">
    <div class="field-label">Sensoren &amp; Schalter</div>
    <div class="extras-row">
      ${visible.map(e => {
        if(e.kind === 'switch'){
          return `<div class="extra-switch">
            <span>${e.label}</span>
            <button class="btn-mini" onclick="extraCommand('${printerId}','${e.id}','on')">${t('btn_on')}</button>
            <button class="btn-mini off" onclick="extraCommand('${printerId}','${e.id}','off')">${t('btn_off')}</button>
          </div>`;
        }
        // v2.5.1: zeigt jetzt IMMER ein Verlaufsdiagramm (Sparkline), nicht
        // nur bei "display": "temperature"/"humidity" (siehe extraChip()
        // oben, dieselbe tempHistory-Infrastruktur, eigener Feld-
        // Namensraum "extra_<id>") - nur bei tatsaechlich numerischem Wert
        // (ein Text-Sensorwert wird weiterhin ohne Diagramm angezeigt).
        const raw = e.value;
        const num = (raw === undefined || raw === null || raw === '') ? NaN : Number(raw);
        const isNumeric = Number.isFinite(num);
        if(isNumeric) recordTempHistory(printerId, 'extra_' + e.id, num);
        const history = (tempHistory[printerId] && tempHistory[printerId]['extra_' + e.id]) || [];
        const val = isNumeric ? formatTemp(num) : ((raw === undefined || raw === null || raw === '') ? '–' : raw);
        return `<div class="extra-sensor"><span>${e.label}</span><b>${val}${e.unit ? ' ' + e.unit : ''}</b>${isNumeric ? sparklineSvg(history) : ''}</div>`;
      }).join('')}
    </div>
  </div>`;
}

// MK6 v1.2.0: letzte Druckerliste aus refresh() - wird ohne erneuten
// Netzwerk-Request fuer den Zuweisen-Dialog (openAssignModal()) genutzt,
// damit dort eine aktuelle Auswahl an Ziel-Druckern zur Verfuegung steht.
let lastPrinterList = [];

// v2.3.0: zuletzt vom Server geladene Raumliste - analog zu lastPrinterList
// fuer Stellen, die ohne erneuten Request darauf zugreifen (z. B. das
// Zuweisen-Dropdown in refreshPrinterManageList()).
let lastGroupList = [];
// v2.3.0: wie lastGroupList, fuer renameGroup()/editRtspCamera() - dort
// wird NICHT der Name/die URL als eingebetteter JS-String-Literal-Wert
// ins onclick-Attribut geschrieben (koennte bei Anfuehrungszeichen im
// Namen das HTML-Attribut vorzeitig beenden), sondern nur die ID - der
// aktuelle Name/die URL wird beim Aufruf aus dieser Liste nachgeschlagen.
let lastCamsList = [];

// v2.5.0: wie lastCamsList, fuer eigenstaendige (nicht an einen Drucker
// gebundene) MQTT-Sensoren/Schalter - siehe cardForStandaloneExtra() und
// die Verwaltung im "MQTT-Geraete"-Abschnitt des Einstellungen-Modus
// (renderMqttExtrasList()).
let lastStandaloneExtrasList = [];

function cardForPrinter(p){
  if(p.type === 'octoprint') return renderOctoPrintCard(p);
  if(p.type === 'formlabs' || p.type === 'formlabs_wash' || p.type === 'formlabs_cure') return renderFormlabsCard(p);
  if(CREALITY_TYPES.includes(p.type)) return renderCrealityCard(p);
  if(p.type === 'ultimaker') return renderUltimakerCard(p);
  return renderBambuCard(p);
}

// v2.4.0: Kachel fuer eine externe RTSP-Kamera - erscheint (seit v2.4.0,
// anstelle des vorherigen gemeinsamen "Kameras"-Knopfs/-Modals) direkt als
// eigenes Grid-Element neben den Drucker-Karten, im jeweils zugewiesenen
// Raum. Zeigt bewusst nur Name + Kamera-Symbol (keine Druckfunktionen).
function cardForCamera(c){
  return `
    <div class="camera-card">
      <div>
        <span class="name">${c.name}</span>
        <span class="type-badge">${t('camera_type_badge')}</span>
      </div>
      <div class="cam-icon" title="${t('tooltip_show_camera')}" onclick="openExternalCam('${c.id}')">${CAM_ICON}</div>
    </div>`;
}

// v2.5.0: Kachel fuer einen eigenstaendigen (nicht an einen Drucker
// gebundenen) MQTT-Sensor/Schalter - erscheint, analog zur Kamera-Kachel,
// direkt als eigenes Grid-Element im jeweils zugewiesenen Raum. Ein
// Schalter zeigt dieselben Ein/Aus-Knoepfe wie im druckergebundenen Fall
// (siehe renderExtras()), nur ueber standaloneExtraCommand() statt
// extraCommand() (anderer, druckerunabhaengiger Endpunkt).
function cardForStandaloneExtra(e){
  if(e.kind === 'switch'){
    return `
      <div class="camera-card">
        <div>
          <span class="name">${e.label}</span>
          <span class="type-badge">${t('switch_type_badge')}</span>
        </div>
        <div>
          <button class="btn-mini" onclick="standaloneExtraCommand('${e.id}','on')">${t('btn_on')}</button>
          <button class="btn-mini off" onclick="standaloneExtraCommand('${e.id}','off')">${t('btn_off')}</button>
        </div>
      </div>`;
  }
  // v2.5.1: Verlaufsdiagramm (Sparkline) auch fuer eigenstaendige Sensoren
  // - dieselbe tempHistory-Infrastruktur wie bei druckergebundenen Extras
  // (renderExtras()), nur unter einem eigenen, druckerunabhaengigen
  // "Pseudo-Drucker"-Schluessel "__standalone__" einsortiert, damit sich
  // eigenstaendige und druckergebundene Sensor-IDs nicht ueberschneiden
  // koennen.
  const raw = e.value;
  const num = (raw === undefined || raw === null || raw === '') ? NaN : Number(raw);
  const isNumeric = Number.isFinite(num);
  if(isNumeric) recordTempHistory('__standalone__', 'extra_' + e.id, num);
  const history = (tempHistory['__standalone__'] && tempHistory['__standalone__']['extra_' + e.id]) || [];
  const val = isNumeric ? formatTemp(num) : ((raw === undefined || raw === null || raw === '') ? '–' : raw);
  // v2.5.6: Sparkline-Farbe wie bei druckergebundenen Extras (siehe
  // extraChip() oben) nach "display" waehlen, statt immer die Default-
  // Farbe (temp-spark/rot) zu nehmen - ein eigenstaendiger Sensor mit
  // "display": "humidity" soll genauso blau sein wie derselbe Sensor,
  // waere er einem Drucker zugeordnet.
  const sparkClass = (e.display === 'humidity') ? 'humidity-spark' : 'temp-spark';
  return `
    <div class="camera-card">
      <div>
        <span class="name">${e.label}</span>
        <span class="type-badge">${t('sensor_type_badge')}</span>
      </div>
      <div><b>${val}${e.unit ? ' ' + e.unit : ''}</b>${isNumeric ? sparklineSvg(history, sparkClass) : ''}</div>
    </div>`;
}

async function refresh(){
  const [printers, groups, cams, standaloneExtras] = await Promise.all([
    fetch('/api/status').then(r => r.json()),
    fetch('/api/groups').then(r => r.json()).catch(() => lastGroupList),
    fetch('/api/rtsp-cameras').then(r => r.json()).catch(() => lastCamsList),
    fetch('/api/standalone_extras').then(r => r.json()).catch(() => lastStandaloneExtrasList)
  ]);
  lastPrinterList = printers;
  lastGroupList = groups;
  lastCamsList = cams;
  lastStandaloneExtrasList = standaloneExtras;
  // v2.6.0: FarmBot-Feld(er) oberhalb der Raeume - eigener, von Raeumen
  // unabhaengiger Abruf (siehe renderFarmbotPanel()/#farmbotPanel).
  refreshFarmbotPanel();
  if(farmbotQueueModalId) refreshFarmbotQueueModal();
  // v2.0.1: haelt den "Druckraum leer"-Knopf live aktuell, falls die
  // Warteschlange gerade offen ist (z. B. der Nutzer wartet darauf, dass
  // ein Bambu-Lab-Drucker fertig wird, ohne das Modal zu schliessen).
  if(queueModalPrinterId) updateQueueSendButtonState();
  const list = document.getElementById('printerList');

  if(printers.length === 0 && cams.length === 0 && standaloneExtras.length === 0){
    list.innerHTML = `<div class="empty-state">
      ${t('empty_no_printers')}
      <div><button class="btn" onclick="enterSettingsMode()">${t('btn_add_printer_empty')}</button></div>
    </div>`;
    return;
  }

  // v2.3.0/v2.4.0/v2.5.0: ohne angelegte Raeume unveraendertes Verhalten
  // (flache Liste, sortiert nach "order", Drucker vor Kameras vor
  // eigenstaendigen Sensoren/Schaltern) - mit Raeumen wird nach Raum
  // gruppiert angezeigt (Drucker, Kameras UND eigenstaendige Sensoren/
  // Schalter koennen alle einem Raum zugewiesen werden), leere Raeume
  // werden im Bedien-Modus nicht angezeigt (siehe Kommentar bei
  // .room-header/.room-group).
  const byOrder = (a, b) => (a.order || 0) - (b.order || 0);
  if(groups.length === 0){
    list.innerHTML = printers.slice().sort(byOrder).map(cardForPrinter).join('') +
                      cams.slice().sort(byOrder).map(cardForCamera).join('') +
                      standaloneExtras.slice().sort(byOrder).map(cardForStandaloneExtra).join('');
    return;
  }
  const printersByGroup = {};
  printers.forEach(p => {
    const gid = p.group_id || '__none__';
    (printersByGroup[gid] = printersByGroup[gid] || []).push(p);
  });
  const camsByGroup = {};
  cams.forEach(c => {
    const gid = c.group_id || '__none__';
    (camsByGroup[gid] = camsByGroup[gid] || []).push(c);
  });
  const standaloneByGroup = {};
  standaloneExtras.forEach(e => {
    const gid = e.group_id || '__none__';
    (standaloneByGroup[gid] = standaloneByGroup[gid] || []).push(e);
  });
  let html = '';
  groups.forEach(g => {
    const pMembers = (printersByGroup[g.id] || []).slice().sort(byOrder);
    const cMembers = (camsByGroup[g.id] || []).slice().sort(byOrder);
    const eMembers = (standaloneByGroup[g.id] || []).slice().sort(byOrder);
    if(pMembers.length === 0 && cMembers.length === 0 && eMembers.length === 0) return;
    html += `<div class="room-header">${g.name}</div>`;
    html += `<div class="room-group">${pMembers.map(cardForPrinter).join('')}${cMembers.map(cardForCamera).join('')}${eMembers.map(cardForStandaloneExtra).join('')}</div>`;
  });
  const pUngrouped = (printersByGroup['__none__'] || []).slice().sort(byOrder);
  const cUngrouped = (camsByGroup['__none__'] || []).slice().sort(byOrder);
  const eUngrouped = (standaloneByGroup['__none__'] || []).slice().sort(byOrder);
  if(pUngrouped.length || cUngrouped.length || eUngrouped.length){
    html += `<div class="room-header">Ohne Raum</div>`;
    html += `<div class="room-group">${pUngrouped.map(cardForPrinter).join('')}${cUngrouped.map(cardForCamera).join('')}${eUngrouped.map(cardForStandaloneExtra).join('')}</div>`;
  }
  list.innerHTML = html;
}

// v2.5.2: Hinweis, wenn die MQTT-Verbindung zu diesem Bambu-Drucker
// gerade nicht steht ("connected": false) - vorher blieben die zuletzt
// empfangenen Duese-/Bett-/Kammer-Werte beim Verbindungsabbruch
// UNVERAENDERT stehen (siehe PrinterConnection._on_disconnect() in
// app.py - setzt bewusst nur "connected", nicht die einzelnen
// Messwerte, zurueck), ohne das irgendwo kenntlich zu machen. Gemeldeter
// Fall: Status-Punkt dauerhaft rot, Temperaturen wirkten trotzdem wie
// "live", weil es sich um eingefrorene alte Werte handelte - die Kamera
// (voellig unabhaengig von dieser MQTT-Verbindung, siehe
// bambu_rtsp_mjpeg_generator()) zeigte parallel ein echtes Live-Bild,
// was den Eindruck "der Drucker ist doch erreichbar" verstaerkte.
function renderBambuCard(p){
  const online = p.connected;
  const pct = p.progress || 0;
  const remMin = formatRemaining(p.remaining_min);
  return `
    <div class="printer-card">
      <div class="card-head">
        <div>
          <span class="status-dot ${online ? 'online' : ''}"></span>
          <span class="name">${p.name}</span>
          <span class="ip">${p.ip}</span>
          <span class="type-badge">Bambu Lab</span>
        </div>
        <div class="head-right">
          <span class="state-badge ${stateClass(p.gcode_state)}">${p.gcode_state || 'UNKNOWN'}</span>
          <div class="cam-icon" title="${t('tooltip_show_camera')}" onclick="openCam('${p.id}')">${CAM_ICON}</div>
          <div class="hist-icon" title="${t('tooltip_history')}" onclick="openHistoryModal('${p.id}')">${HIST_ICON}</div>
          ${renderQueueIcon(p)}
        </div>
      </div>
      <div class="card-body">
        <div>
          <div class="field-label" data-i18n="field_current_file">Aktuelle Datei</div>
          <div class="file-name">${p.file_name || '-'} ${remMin ? ' &middot; ' + remMin : ''}</div>

          <div class="field-label">Fortschritt</div>
          <div class="progress-row">
            ${progressThumb(p)}
            <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
            <div class="progress-pct">${pct}%</div>
            ${abortButtonHtml(p)}
          </div>

          <div class="field-label">Temperaturen</div>
          ${online ? '' : `<div class="hint-text" style="margin-top:0;">
            Nicht verbunden - die folgenden Werte sind die zuletzt bekannten
            ${p.last_update ? '(Stand ' + p.last_update + ')' : ''}, KEINE
            Live-Daten mehr.
          </div>`}
          <div class="temps">
            ${p.bambu_family === 'a1' ? '' : tempChip(p.id, 'chamber', 'Kammer', p.chamber_temp)}
            ${tempChip(p.id, 'nozzle', 'Duese', p.nozzle_temp)}
            ${tempChip(p.id, 'bed', 'Bett', p.bed_temp)}
            ${extraTempChips(p.id, p.extras)}
          </div>
        </div>
        <div>
          <div class="ams-title">${t('ams_filament_title')}</div>
          ${renderAms(p.id, p.ams, p.ams_units, p.bambu_family)}
          ${renderDropZone(p.id)}
        </div>
      </div>
      ${renderExtras(p.id, p.extras)}
    </div>`;
}

function renderDropZone(printerId){
  return `
    <div class="drop-zone" id="dz-${printerId}"
         ondragover="dzDragOver(event)"
         ondragleave="dzDragLeave(event)"
         ondrop="dzDrop(event,'${printerId}')">
      Fertig gesclicte .gcode.3mf-Datei hier ablegen zum Drucken
      <div class="dz-hint">${t('dz_hint_developer_mode')}</div>
    </div>`;
}

function dzDragOver(ev){
  ev.preventDefault();
  ev.currentTarget.classList.add('dragover');
}
function dzDragLeave(ev){
  ev.currentTarget.classList.remove('dragover');
}

// Merkt sich Zuordnungs-Modal-Zustand fuer den aktuell offenen Vorgang
let amsModalJobId = null;
let amsModalPrinterId = null;
let amsModalTotalFilaments = 0;

async function dzDrop(ev, printerId){
  ev.preventDefault();
  const zone = ev.currentTarget;
  zone.classList.remove('dragover');
  const files = ev.dataTransfer.files;
  if(!files || files.length === 0) return;
  const file = files[0];

  if(!file.name.toLowerCase().endsWith('.gcode.3mf')){
    showToast('Nur .gcode.3mf-Dateien werden unterstuetzt.', 'err');
    return;
  }

  zone.classList.add('uploading');
  const form = new FormData();
  form.append('file', file);
  try{
    const res = await fetch('/api/printers/' + printerId + '/print/prepare', { method:'POST', body: form });
    const data = await res.json();
    if(!res.ok){
      showToast(data.error || 'Fehler beim Vorbereiten des Druckauftrags.', 'err');
      return;
    }
    // MK6 v1.2.0: Drucker war beschaeftigt - Datei wurde automatisch in
    // die Warteschlange gelegt, statt den AMS-Dialog zu oeffnen.
    if(data.mode === 'queued'){
      showToast('Drucker ist beschaeftigt - Datei wurde in die Warteschlange gelegt.', 'ok');
      return;
    }
    openAmsModal(printerId, data);
  } catch(e){
    showToast('Netzwerkfehler beim Hochladen.', 'err');
  } finally {
    zone.classList.remove('uploading');
  }
}

// Grobe Zuordnung Hex-Farbe -> deutscher Farbname (naechster Treffer per
// RGB-Abstand). Eine exakte Farbe laesst sich nicht immer 1:1 in ein Wort
// uebersetzen - das ist eine bewusste, für die Anzeige ausreichende
// Näherung, keine Farbmanagement-Software. Der exakte Hex-Wert bleibt bei
// Bedarf als Tooltip (title-Attribut) abrufbar.
const NAMED_COLORS = [
  ['Schwarz', '000000'], ['Weiss', 'FFFFFF'], ['Grau', '808080'],
  ['Hellgrau', 'D3D3D3'], ['Dunkelgrau', '404040'],
  ['Rot', 'FF0000'], ['Dunkelrot', '8B0000'], ['Rosa', 'FFC0CB'],
  ['Pink', 'FF1493'], ['Magenta', 'FF00FF'],
  ['Orange', 'FFA500'], ['Gelb', 'FFFF00'], ['Hellgelb', 'FFFFE0'],
  ['Braun', '8B4513'], ['Beige', 'F5F5DC'],
  ['Gruen', '008000'], ['Hellgruen', '90EE90'], ['Dunkelgruen', '006400'],
  ['Olivgruen', '808000'],
  ['Tuerkis', '40E0D0'], ['Cyan', '00FFFF'],
  ['Blau', '0000FF'], ['Hellblau', 'ADD8E6'], ['Dunkelblau', '00008B'],
  ['Marineblau', '000080'],
  ['Lila', '800080'], ['Violett', '8A2BE2'],
  ['Gold', 'FFD700'], ['Silber', 'C0C0C0'], ['Kupfer', 'B87333'],
];

function hexToRgb(hex){
  const h = (hex || '').replace('#', '');
  return {
    r: parseInt(h.substring(0, 2), 16) || 0,
    g: parseInt(h.substring(2, 4), 16) || 0,
    b: parseInt(h.substring(4, 6), 16) || 0,
  };
}

function colorNameFor(hex){
  const target = hexToRgb(hex);
  let best = 'unbekannt', bestDist = Infinity;
  for(const [name, h] of NAMED_COLORS){
    const c = hexToRgb(h);
    const dist = (c.r - target.r) ** 2 + (c.g - target.g) ** 2 + (c.b - target.b) ** 2;
    if(dist < bestDist){ bestDist = dist; best = name; }
  }
  return best;
}

function openAmsModal(printerId, data){
  amsModalJobId = data.job_id;
  amsModalPrinterId = printerId;
  // WICHTIG (v1.6.2): Anzahl ALLER im Projekt definierten Filamente
  // (nicht nur der hier angezeigten, ggf. gefilterten) - wird beim
  // Zusammenbauen des finalen ams_mapping-Arrays in confirmAmsModal()
  // gebraucht, siehe dortiger Kommentar.
  amsModalTotalFilaments = data.total_filaments || (data.filaments ? data.filaments.length : 0);

  document.getElementById('amsModalFilename').textContent = data.filename;
  resetAmsProgress();

  const rows = document.getElementById('amsModalRows');
  if(!data.filaments || data.filaments.length === 0){
    rows.innerHTML = `<div class="hint-text">Konnte keine Filament-Infos aus der Datei lesen - der Druck kann ohne AMS-Zuordnung (externe Spule) gestartet werden.</div>`;
  } else if(!data.ams_trays || data.ams_trays.length === 0){
    rows.innerHTML = `<div class="hint-text">Keine aktuellen AMS-Fach-Daten vom Drucker verfuegbar - der Druck kann ohne automatische Zuordnung gestartet werden (am Display manuell waehlen).</div>`
      + data.filaments.map((f, i) => amsRowHtml(f, i, [])).join('');
  } else {
    rows.innerHTML = data.filaments.map((f, i) => amsRowHtml(f, i, data.ams_trays)).join('');
  }

  document.getElementById('amsModal').classList.add('show');
}

function amsRowHtml(filament, i, amsTrays){
  const suggested = (filament.suggested_tray === undefined) ? -1 : filament.suggested_tray;
  const suggestedTray = amsTrays.find(t => t.flat_index === suggested) || null;
  const hasSuggestion = suggested !== -1 && suggestedTray !== null;
  const filamentColorName = colorNameFor(filament.color);
  const filamentHexTitle = '#' + (filament.color || '').toUpperCase();

  // v2.2.20 hatte hier AMS-HT-Faecher noch ausgeblendet (unverifizierter
  // Mapping-Wert); seit v2.2.21 (verifizierter Wert, siehe
  // _slot_to_flat_index()) werden sie wieder ganz normal wie jedes
  // andere AMS-Fach behandelt - keine Sonderbehandlung mehr noetig.
  const suggestionLabel = hasSuggestion
    ? `AMS-Fach ${suggestedTray.flat_index} &middot; ${suggestedTray.type || '-'} &middot; <span title="${'#' + (suggestedTray.color || '').toUpperCase()}">${colorNameFor(suggestedTray.color)}</span>`
    : `Extern / manuell am Display (keine passende Farbe im AMS gefunden)`;

  // "Andere Wahl"-Dropdown: alle AMS-Faecher AUSSER dem bereits vorgeschlagenen,
  // plus immer die Option "Extern / manuell".
  const otherTrays = amsTrays.filter(t => t.flat_index !== suggested);
  const otherOptions = [`<option value="-1">Extern / manuell am Display</option>`]
    .concat(otherTrays.map(t => {
      const remain = (t.remain === undefined || t.remain === null || t.remain < 0) ? '?' : t.remain + '%';
      const trayColorName = colorNameFor(t.color);
      return `<option value="${t.flat_index}">AMS-Fach ${t.flat_index} &middot; ${t.type || '-'} &middot; ${trayColorName} &middot; ${remain}</option>`;
    })).join('');

  const groupName = 'ams-choice-' + i;
  return `
    <div class="ams-row" data-filament-index="${i}" data-true-index="${filament.index}" data-suggested="${suggested}">
      <div class="ams-swatch" style="background:#${filament.color}" title="${filamentHexTitle}"></div>
      <div class="ams-row-body">
        <div class="ams-row-label" title="${filamentHexTitle}">Filament ${i + 1} <span class="ams-row-type">(${filament.type || '-'} &middot; ${filamentColorName})</span></div>
        <label class="ams-radio">
          <input type="radio" name="${groupName}" value="suggested" checked onchange="amsRowToggle(${i})">
          <span>Vorschlag aus Datei verwenden: <b>${suggestionLabel}</b></span>
        </label>
        <label class="ams-radio">
          <input type="radio" name="${groupName}" value="other" onchange="amsRowToggle(${i})">
          <span>Anderes Material aus dem AMS waehlen:</span>
          <select class="ams-row-select" id="ams-other-${i}" disabled>${otherOptions}</select>
        </label>
      </div>
    </div>`;
}

function amsRowToggle(i){
  const select = document.getElementById('ams-other-' + i);
  const row = select.closest('.ams-row');
  const chosen = row.querySelector(`input[name="ams-choice-${i}"]:checked`).value;
  select.disabled = chosen !== 'other';
}

function closeAmsModal(){
  document.getElementById('amsModal').classList.remove('show');
  document.getElementById('amsModalRows').innerHTML = '';
  resetAmsProgress();
}

function resetAmsProgress(){
  document.getElementById('amsProgressWrap').style.display = 'none';
  document.getElementById('amsProgressBar').style.width = '0%';
  document.getElementById('amsProgressLabel').textContent = '';
  document.getElementById('amsModalConfirmBtn').disabled = false;
  document.getElementById('amsModalConfirmBtn').textContent = 'Drucken starten';
  document.getElementById('amsModalCancelBtn').disabled = false;
}

function setAmsProgress(percent, label){
  document.getElementById('amsProgressWrap').style.display = 'block';
  document.getElementById('amsProgressBar').style.width = Math.max(0, Math.min(100, percent)) + '%';
  document.getElementById('amsProgressLabel').textContent = label;
}

function formatBytes(n){
  if(n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + ' MB';
  if(n >= 1024) return (n / 1024).toFixed(0) + ' KB';
  return n + ' B';
}

async function cancelAmsModal(){
  const jobId = amsModalJobId;
  const printerId = amsModalPrinterId;
  closeAmsModal();
  amsModalJobId = null;
  amsModalPrinterId = null;
  amsModalTotalFilaments = 0;
  if(jobId){
    try{ await fetch('/api/printers/' + printerId + '/print/cancel', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({job_id: jobId})
    }); } catch(e){ /* Aufraeumen ist best-effort */ }
  }
}

async function confirmAmsModal(){
  const jobId = amsModalJobId;
  const printerId = amsModalPrinterId;
  if(!jobId) return;

  const rows = document.querySelectorAll('#amsModalRows .ams-row');
  // WICHTIG (v1.6.2 - Bugfix "Zuordnungstabelle des AMS konnte nicht
  // abgerufen werden" bei Mehrfarb-Drucken): Der Drucker erwartet ein
  // ams_mapping-Array, dessen POSITIONEN den originalen Projekt-
  // Filament-IDs entsprechen (aus der .3mf), NICHT die Position in
  // dieser (ggf. gefilterten) Anzeige-Liste. Deshalb wird hier ein
  // VOLLSTAENDIG GROSSES Array (Laenge = amsModalTotalFilaments)
  // gebaut, mit -1 ("extern/manuell") an allen nicht angezeigten
  // Positionen, und jedes angezeigte Filament wird an seiner ECHTEN
  // Position (data-true-index, aus dem Backend uebernommen) einsortiert
  // - nicht an der Position in der Anzeige-Reihenfolge.
  const mapping = new Array(amsModalTotalFilaments || rows.length).fill(-1);
  rows.forEach(row => {
    const i = row.dataset.filamentIndex;
    const trueIndex = parseInt(row.dataset.trueIndex, 10);
    const suggested = parseInt(row.dataset.suggested, 10);
    const chosen = row.querySelector(`input[name="ams-choice-${i}"]:checked`).value;
    const value = (chosen === 'suggested') ? suggested : parseInt(document.getElementById('ams-other-' + i).value, 10);
    if(!Number.isNaN(trueIndex) && trueIndex >= 0 && trueIndex < mapping.length){
      mapping[trueIndex] = value;
    }
  });

  const btn = document.getElementById('amsModalConfirmBtn');
  btn.disabled = true;
  btn.textContent = 'Wird gesendet ...';
  document.getElementById('amsModalCancelBtn').disabled = true;
  setAmsProgress(0, 'Wird gestartet ...');

  try{
    const res = await fetch('/api/printers/' + printerId + '/print/confirm', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({job_id: jobId, mapping: mapping})
    });
    const data = await res.json();
    if(!res.ok){
      resetAmsProgress();
      showToast(data.error || 'Fehler beim Starten des Druckauftrags.', 'err');
      return;
    }
    await pollAmsProgress(printerId, jobId);
  } catch(e){
    resetAmsProgress();
    showToast('Netzwerkfehler beim Senden.', 'err');
  }
}

async function pollAmsProgress(printerId, jobId){
  while(amsModalJobId === jobId){
    await new Promise(r => setTimeout(r, 400));
    let data;
    try{
      const res = await fetch('/api/printers/' + printerId + '/print/progress/' + jobId);
      if(!res.ok){
        resetAmsProgress();
        showToast('Fortschritt konnte nicht abgefragt werden.', 'err');
        return;
      }
      data = await res.json();
    } catch(e){
      resetAmsProgress();
      showToast('Netzwerkfehler beim Abfragen des Fortschritts.', 'err');
      return;
    }

    if(data.phase === 'uploading'){
      setAmsProgress(data.percent, `Wird auf den Drucker geladen ... ${data.percent}% (${formatBytes(data.sent)} / ${formatBytes(data.total)})`);
    } else if(data.phase === 'done'){
      setAmsProgress(100, 'Fertig.');
      const ams = data.ams;
      if(ams && ams.total > 0){
        showToast(`Druckauftrag gesendet (${ams.matched}/${ams.total} Filamente AMS-zugeordnet).`, 'ok');
      } else {
        showToast('Druckauftrag gesendet (ohne AMS-Zuordnung).', 'ok');
      }
      amsModalJobId = null;
      amsModalPrinterId = null;
      amsModalTotalFilaments = 0;
      closeAmsModal();
      return;
    } else if(data.phase === 'error'){
      resetAmsProgress();
      showToast(data.error || 'Fehler beim Senden des Druckauftrags.', 'err');
      // Modal + Job bleiben erhalten - "Drucken starten" erneut moeglich,
      // ohne die Datei nochmal hochladen oder die Zuordnung neu waehlen
      // zu muessen (siehe DashboardApp.start_confirm_print_job()).
      return;
    }
  }
}

// Toasts: unabhaengig vom alle 2,5s neu gerenderten Drucker-Grid, damit
// Erfolgs-/Fehlermeldungen nicht durch refresh() sofort wieder
// verschwinden.
function showToast(message, kind){
  const container = document.getElementById('toastContainer');
  const el = document.createElement('div');
  el.className = 'toast ' + (kind === 'err' ? 'err' : 'ok');
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), 7000);
}

function renderOctoPrintCard(p){
  const online = p.connected;
  const pct = p.progress || 0;
  const remMin = formatRemaining(p.remaining_min);
  return `
    <div class="printer-card">
      <div class="card-head">
        <div>
          <span class="status-dot ${online ? 'online' : ''}"></span>
          <span class="name">${p.name}</span>
          <span class="ip">${p.ip}</span>
          <span class="type-badge">OctoPrint</span>
        </div>
        <div class="head-right">
          <span class="state-badge ${stateClass(p.gcode_state)}">${p.gcode_state || 'UNKNOWN'}</span>
          <div class="cam-icon" title="${t('tooltip_show_camera')}" onclick="openCam('${p.id}')">${CAM_ICON}</div>
          <div class="hist-icon" title="${t('tooltip_history')}" onclick="openHistoryModal('${p.id}')">${HIST_ICON}</div>
        </div>
      </div>
      <div class="card-body">
        <div>
          <div class="field-label" data-i18n="field_current_file">Aktuelle Datei</div>
          <div class="file-name">${p.file_name || '-'} ${remMin ? ' &middot; ' + remMin : ''}</div>

          <div class="field-label">Fortschritt</div>
          <div class="progress-row">
            ${progressThumb(p)}
            <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
            <div class="progress-pct">${pct}%</div>
            ${abortButtonHtml(p)}
          </div>

          <div class="field-label">Temperaturen</div>
          <div class="temps">
            ${tempChip(p.id, 'nozzle', 'Duese', p.nozzle_temp)}
            ${tempChip(p.id, 'bed', 'Bett', p.bed_temp)}
            ${extraTempChips(p.id, p.extras)}
          </div>
          ${p.error ? `<div class="error-hint">${p.error}</div>` : ''}
        </div>
        <div>
          <div class="field-label">Hinweis</div>
          <div class="hint-text" style="margin:0;">${t('hint_octoprint_no_chamber')}</div>
        </div>
      </div>
      ${renderExtras(p.id, p.extras)}
    </div>`;
}

function renderCrealityCard(p){
  const online = p.connected;
  const pct = p.progress || 0;
  const label = CREALITY_LABELS[p.type] || 'Creality (Klipper)';
  const hasChamber = (p.chamber_temp !== undefined && p.chamber_temp !== null);
  return `
    <div class="printer-card">
      <div class="card-head">
        <div>
          <span class="status-dot ${online ? 'online' : ''}"></span>
          <span class="name">${p.name}</span>
          <span class="ip">${p.ip}</span>
          <span class="type-badge">${label}</span>
        </div>
        <div class="head-right">
          <span class="state-badge ${stateClass(p.gcode_state)}">${p.gcode_state || 'UNKNOWN'}</span>
          <div class="cam-icon" title="${t('tooltip_show_camera')}" onclick="openCam('${p.id}')">${CAM_ICON}</div>
          <div class="hist-icon" title="${t('tooltip_history')}" onclick="openHistoryModal('${p.id}')">${HIST_ICON}</div>
        </div>
      </div>
      <div class="card-body">
        <div>
          <div class="field-label" data-i18n="field_current_file">Aktuelle Datei</div>
          <div class="file-name">${p.file_name || '-'}</div>

          <div class="field-label">Fortschritt</div>
          <div class="progress-row">
            ${progressThumb(p)}
            <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
            <div class="progress-pct">${pct}%</div>
            ${abortButtonHtml(p)}
          </div>

          <div class="field-label">Temperaturen</div>
          <div class="temps">
            ${hasChamber ? tempChip(p.id, 'chamber', 'Kammer', p.chamber_temp) : ''}
            ${tempChip(p.id, 'nozzle', 'Duese', p.nozzle_temp)}
            ${tempChip(p.id, 'bed', 'Bett', p.bed_temp)}
            ${extraTempChips(p.id, p.extras)}
          </div>
          ${p.error ? `<div class="error-hint">${p.error}</div>` : ''}
        </div>
        <div>
          <div class="field-label">Hinweis</div>
          <div class="hint-text" style="margin:0;">${t('hint_creality_chamber')}</div>
        </div>
      </div>
      ${renderExtras(p.id, p.extras)}
    </div>`;
}

function renderUltimakerCard(p){
  const online = p.connected;
  const pct = p.progress || 0;
  const remMin = formatRemaining(p.remaining_min);
  return `
    <div class="printer-card">
      <div class="card-head">
        <div>
          <span class="status-dot ${online ? 'online' : ''}"></span>
          <span class="name">${p.name}</span>
          <span class="ip">${p.ip}</span>
          <span class="type-badge">Ultimaker</span>
        </div>
        <div class="head-right">
          <span class="state-badge ${stateClass(p.gcode_state)}">${p.gcode_state || 'UNKNOWN'}</span>
          <div class="cam-icon" title="${t('tooltip_show_camera')}" onclick="openCam('${p.id}')">${CAM_ICON}</div>
          <div class="hist-icon" title="${t('tooltip_history')}" onclick="openHistoryModal('${p.id}')">${HIST_ICON}</div>
          ${renderQueueIcon(p)}
        </div>
      </div>
      <div class="card-body">
        <div>
          <div class="field-label" data-i18n="field_current_file">Aktuelle Datei</div>
          <div class="file-name">${p.file_name || '-'} ${remMin ? ' &middot; ' + remMin : ''}</div>

          <div class="field-label">Fortschritt</div>
          <div class="progress-row">
            ${progressThumb(p)}
            <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
            <div class="progress-pct">${pct}%</div>
            ${abortButtonHtml(p)}
          </div>

          <div class="field-label">Temperaturen</div>
          <div class="temps">
            ${tempChip(p.id, 'nozzle', 'Duese', p.nozzle_temp)}
            ${tempChip(p.id, 'bed', 'Bett', p.bed_temp)}
            ${extraTempChips(p.id, p.extras)}
          </div>
          ${p.error ? `<div class="error-hint">${p.error}</div>` : ''}
        </div>
        <div>
          <div class="field-label">Druckauftrag senden</div>
          ${renderUltimakerDropZone(p.id, !!p.ultimaker_paired)}
          <div class="hint-text" style="margin-top:8px;">${t('hint_ultimaker_no_chamber')}</div>
        </div>
      </div>
      ${renderExtras(p.id, p.extras)}
    </div>`;
}

function renderUltimakerDropZone(printerId, paired){
  if(!paired){
    return `
      <div class="drop-zone dz-disabled">
        Kopplung mit dem Drucker erforderlich, bevor Druckauftraege
        gesendet werden koennen.
        <div class="dz-hint">
          <button type="button" class="btn-mini" onclick="pairUltimaker('${printerId}')">Jetzt koppeln</button>
        </div>
      </div>`;
  }
  return `
    <div class="drop-zone" id="dz-${printerId}"
         ondragover="dzDragOver(event)"
         ondragleave="dzDragLeave(event)"
         ondrop="dzDropUltimaker(event,'${printerId}')">
      Fertig gesclicte .gcode-Datei hier ablegen zum Drucken
      <div class="dz-hint">${t('dz_hint_cura_export')}</div>
    </div>`;
}

async function pairUltimaker(printerId){
  showToast('Kopplungsanfrage gesendet - bitte am Drucker-Display bestaetigen...', 'ok');
  try{
    const res = await fetch('/api/printers/' + printerId + '/ultimaker/pair/start', { method: 'POST' });
    const data = await res.json();
    if(!res.ok){
      showToast(data.error || 'Kopplungsanfrage fehlgeschlagen.', 'err');
      return;
    }
  } catch(e){
    showToast('Netzwerkfehler bei der Kopplungsanfrage.', 'err');
    return;
  }

  // Server-seitiges Zeitlimit liegt bei 120s - hier etwas grosszuegiger,
  // damit ein knapp verpasster letzter Poll nicht faelschlich als
  // Netzwerkfehler statt als Ablauf gemeldet wird.
  const deadline = Date.now() + 130000;
  while(Date.now() < deadline){
    await new Promise(r => setTimeout(r, 2000));
    try{
      const res = await fetch('/api/printers/' + printerId + '/ultimaker/pair/status');
      const data = await res.json();
      if(!res.ok){
        showToast(data.error || 'Kopplung fehlgeschlagen.', 'err');
        return;
      }
      if(data.status === 'authorized'){
        showToast('Kopplung erfolgreich - Druckauftraege koennen jetzt gesendet werden.', 'ok');
        refresh();
        return;
      }
      if(data.status === 'unauthorized'){
        showToast('Kopplung am Drucker-Display abgelehnt.', 'err');
        return;
      }
      // status === 'pending' -> weiter warten
    } catch(e){
      showToast('Netzwerkfehler beim Pruefen der Kopplung.', 'err');
      return;
    }
  }
  showToast('Kopplung abgelaufen (keine Bestaetigung am Display) - bitte erneut versuchen.', 'err');
}

async function dzDropUltimaker(ev, printerId){
  ev.preventDefault();
  const zone = ev.currentTarget;
  zone.classList.remove('dragover');
  const files = ev.dataTransfer.files;
  if(!files || files.length === 0) return;
  const file = files[0];

  if(!file.name.toLowerCase().endsWith('.gcode')){
    showToast('Nur fertig gesclicte .gcode-Dateien werden unterstuetzt.', 'err');
    return;
  }

  zone.classList.add('uploading');
  const form = new FormData();
  form.append('file', file);
  let jobId = null;
  try{
    const res = await fetch('/api/printers/' + printerId + '/ultimaker/print', { method: 'POST', body: form });
    const data = await res.json();
    if(!res.ok){
      showToast(data.error || 'Fehler beim Senden des Druckauftrags.', 'err');
      zone.classList.remove('uploading');
      return;
    }
    // MK6 v1.2.0: Drucker war beschaeftigt - Datei wurde automatisch in
    // die Warteschlange gelegt, statt sofort gedruckt zu werden.
    if(data.mode === 'queued'){
      showToast('Drucker ist beschaeftigt - Datei wurde in die Warteschlange gelegt.', 'ok');
      zone.classList.remove('uploading');
      return;
    }
    jobId = data.job_id;
  } catch(e){
    showToast('Netzwerkfehler beim Hochladen.', 'err');
    zone.classList.remove('uploading');
    return;
  }
  await pollUltimakerProgress(printerId, jobId, zone);
}

async function pollUltimakerProgress(printerId, jobId, zone){
  while(true){
    await new Promise(r => setTimeout(r, 400));
    let data;
    try{
      const res = await fetch('/api/printers/' + printerId + '/print/progress/' + jobId);
      if(!res.ok) break;
      data = await res.json();
    } catch(e){
      break;
    }
    if(data.phase === 'error'){
      showToast(data.error || 'Fehler beim Senden des Druckauftrags.', 'err');
      break;
    }
    if(data.phase === 'done'){
      showToast('Druckauftrag gesendet.', 'ok');
      break;
    }
  }
  zone.classList.remove('uploading');
}

function renderFormlabsCard(p){
  const online = p.connected;
  const pct = p.progress || 0;
  const labels = FL_LABELS[p.type] || FL_LABELS.formlabs;
  // v2.2.16: Formlabs hat (anders als Bambu/OctoPrint/Creality/Ultimaker)
  // von Haus aus KEINE eigene Temperaturen-Zeile - wird nur eingeblendet,
  // wenn tatsaechlich mindestens ein MQTT-Extra-Sensor mit "display":
  // "temperature"/"humidity" an diesem Drucker haengt (sonst leere
  // Ueberschrift ohne Inhalt).
  const extraTemps = extraTempChips(p.id, p.extras);
  return `
    <div class="printer-card">
      <div class="card-head">
        <div>
          <span class="status-dot ${online ? 'online' : ''}"></span>
          <span class="name">${p.name}</span>
          <span class="ip">${p.ip}</span>
          <span class="type-badge">${labels.badge}</span>
        </div>
        <div class="head-right">
          <span class="state-badge ${stateClass(p.device_status)}">${p.device_status || 'UNKNOWN'}</span>
          <div class="hist-icon" title="${t('tooltip_history')}" onclick="openHistoryModal('${p.id}')">${HIST_ICON}</div>
        </div>
      </div>
      <div class="card-body single-col">
        <div>
          <div class="field-label">${labels.file}</div>
          <div class="file-name">${p.file_name || '-'}</div>

          <div class="field-label">Fortschritt</div>
          <div class="progress-row">
            ${progressThumb(p)}
            <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
            <div class="progress-pct">${pct}%</div>
          </div>

          ${labels.showMaterial ? `
          <div class="field-label">Geladenes Harz / Material</div>
          <div class="file-name">${p.material || '-'}</div>
          ` : ''}

          ${extraTemps ? `
          <div class="field-label">Temperaturen</div>
          <div class="temps">${extraTemps}</div>
          ` : ''}

          ${p.error ? `<div class="error-hint">${p.error}</div>` : ''}
        </div>
      </div>
      ${renderExtras(p.id, p.extras)}
    </div>`;
}

async function loadVersion(){
  try{
    const res = await fetch('/api/version');
    const data = await res.json();
    document.getElementById('verBadge').textContent = 'v' + data.version;
  } catch(e){ /* Version ist rein informativ - Fehler hier ignorieren */ }
}

// MK6: Kartenlayout 1/2/3/4-spaltig (4 seit v2.4.0), Auswahl wird lokal im
// Browser gemerkt (localStorage) - reine Anzeige-Praeferenz, kein Server-/
// config.json-Zustand, da jeder Nutzer/Browser sein eigenes Layout haben kann.
function getLayoutCols(){
  try{
    const v = parseInt(localStorage.getItem('dashboardLayoutCols'), 10);
    return [1,2,3,4].includes(v) ? v : 1;
  } catch(e){ return 1; }
}
function setLayoutCols(cols){
  const list = document.getElementById('printerList');
  list.classList.remove('cols-2','cols-3','cols-4');
  if(cols === 2) list.classList.add('cols-2');
  if(cols === 3) list.classList.add('cols-3');
  if(cols === 4) list.classList.add('cols-4');
  document.querySelectorAll('.layout-btn').forEach(b=>{
    b.classList.toggle('active', parseInt(b.dataset.cols,10) === cols);
  });
  try{ localStorage.setItem('dashboardLayoutCols', String(cols)); } catch(e){ /* z.B. privater Modus - Auswahl bleibt dann nur fuer diese Sitzung aktiv */ }
}

// v2.4.0: kein gemeinsames Kameras-Modal mehr - externe RTSP-Kameras
// erscheinen als eigene Kachel (siehe cardForCamera()); die Anzeige selbst
// laeuft weiterhin ueber dasselbe Kamera-Modal wie die Drucker-Kamera
// (openCamUrl()).
function openExternalCam(camId){
  openCamUrl('/camera/rtsp/' + camId + '?_=' + Date.now());
}

// ----------------------------------------------------------------------
// v2.3.0: Einstellungen-Modus - Drucker-/Raum-/Kamera-Verwaltung sowie
// Verlaufs-Einstellung. Siehe #settingsPanel-Markup sowie die Backend-
// Routen /api/groups, /api/rtsp-cameras, /api/printers/reorder,
// /api/printers/<id>/group, /api/settings.
// ----------------------------------------------------------------------
let settingsMode = false;

function enterSettingsMode(){
  settingsMode = true;
  document.getElementById('operatorControls').style.display = 'none';
  document.getElementById('settingsModeControls').style.display = 'flex';
  document.getElementById('printerList').style.display = 'none';
  // v2.6.0: FarmBot-Feld(er) gehoeren zum Bedien-Modus, nicht zur
  // Einstellungen-Verwaltung (dafuer gibt es den eigenen Abschnitt
  // "FarmBot" im Einstellungen-Modus) - siehe #farmbotPanel.
  document.getElementById('farmbotPanel').style.display = 'none';
  document.getElementById('settingsPanel').style.display = 'block';
  refreshSettingsPanel();
}
function exitSettingsMode(){
  settingsMode = false;
  document.getElementById('operatorControls').style.display = 'flex';
  document.getElementById('settingsModeControls').style.display = 'none';
  document.getElementById('printerList').style.display = '';
  document.getElementById('farmbotPanel').style.display = '';
  document.getElementById('settingsPanel').style.display = 'none';
  refresh();
}

async function refreshSettingsPanel(){
  let printers, groups, cams, settings;
  try{
    [printers, groups, cams, settings] = await Promise.all([
      fetch('/api/status').then(r => r.json()),
      fetch('/api/groups').then(r => r.json()),
      fetch('/api/rtsp-cameras').then(r => r.json()),
      fetch('/api/settings').then(r => r.json()),
    ]);
  } catch(e){
    showToast('Einstellungen konnten nicht geladen werden.', 'err');
    return;
  }
  lastPrinterList = printers;
  lastGroupList = groups;
  refreshPrinterManageList(printers, groups);
  refreshGroupsManageList(groups);
  refreshCamerasManageList(cams, groups);
  // v2.6.0: FarmBot-Verwaltung - eigener Abruf, unabhaengig von den
  // obigen Listen (siehe refreshFarmbotManageList()).
  fetch('/api/farmbots').then(r => r.json()).then(refreshFarmbotManageList)
    .catch(() => showToast('FarmBot-Liste konnte nicht geladen werden.', 'err'));
  // v2.5.1: MQTT-Bereich jetzt inline statt in einem eigenen Modal - wird
  // hier wie die anderen Verwaltungslisten mit aktualisiert (lastGroupList
  // ist zu diesem Zeitpunkt bereits befuellt, siehe renderMqttExtrasList()
  // fuer die dortige Raum-Zuweisung eigenstaendiger Eintraege).
  refreshMqttSettingsSection();
  const histInput = document.getElementById('historyMaxJobsInput');
  histInput.value = (settings.history_max_jobs === null || settings.history_max_jobs === undefined)
    ? '' : settings.history_max_jobs;
  // v2.8.0: Sprachauswahl im Einstellungsbereich immer passend zur
  // aktuell aktiven Sprache anzeigen (falls z. B. ueber eine andere
  // Sitzung/Geraet geaendert).
  if(settings.language && settings.language !== currentLang){
    currentLang = settings.language;
    applyTranslations();
  }
  populateLanguageSelect();
}

function refreshPrinterManageList(printers, groups){
  const el = document.getElementById('printerManageList');
  if(!printers.length){
    el.innerHTML = `<div class="hint-text">${t('empty_no_printers')}</div>`;
    return;
  }
  const sorted = printers.slice().sort((a,b) => (a.order||0) - (b.order||0));
  const groupOptions = currentGroupId => groups.map(gr =>
    `<option value="${gr.id}" ${currentGroupId === gr.id ? 'selected' : ''}>${gr.name}</option>`).join('');
  el.innerHTML = sorted.map((p, i) => `
    <div class="manage-row">
      <div class="queue-order-btns">
        <button class="btn-mini" ${i === 0 ? 'disabled' : ''} title="Nach oben" onclick="movePrinterOrder('${p.id}',-1)">&uarr;</button>
        <button class="btn-mini" ${i === sorted.length - 1 ? 'disabled' : ''} title="Nach unten" onclick="movePrinterOrder('${p.id}',1)">&darr;</button>
      </div>
      <div class="manage-info">
        ${p.name}
        <div class="manage-sub">${p.ip} &middot; ${p.type}</div>
      </div>
      <div class="manage-actions">
        <select onchange="assignPrinterGroup('${p.id}', this.value)">
          <option value="">Kein Raum</option>
          ${groupOptions(p.group_id)}
        </select>
        <button class="btn-mini btn-delete" title="${t('btn_remove')}" onclick="deletePrinter('${p.id}')">&times;</button>
      </div>
    </div>`).join('');
}

async function movePrinterOrder(printerId, direction){
  const ids = lastPrinterList.slice().sort((a,b) => (a.order||0) - (b.order||0)).map(p => p.id);
  const idx = ids.indexOf(printerId);
  const newIdx = idx + direction;
  if(idx < 0 || newIdx < 0 || newIdx >= ids.length) return;
  [ids[idx], ids[newIdx]] = [ids[newIdx], ids[idx]];
  try{
    const res = await fetch('/api/printers/reorder', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({order: ids})
    });
    if(!res.ok){
      const data = await res.json().catch(() => ({}));
      showToast(data.error || 'Reihenfolge konnte nicht geaendert werden.', 'err');
      return;
    }
  } catch(e){
    showToast('Netzwerkfehler beim Umsortieren.', 'err');
    return;
  }
  refreshSettingsPanel();
}

async function assignPrinterGroup(printerId, groupId){
  try{
    const res = await fetch('/api/printers/' + printerId + '/group', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({group_id: groupId || null})
    });
    if(!res.ok){
      const data = await res.json().catch(() => ({}));
      showToast(data.error || 'Raum konnte nicht zugewiesen werden.', 'err');
    }
  } catch(e){
    showToast('Netzwerkfehler bei der Raum-Zuweisung.', 'err');
  }
  refreshSettingsPanel();
}

function refreshGroupsManageList(groups){
  const el = document.getElementById('groupsManageList');
  if(!groups.length){
    el.innerHTML = '<div class="hint-text">Noch keine Raeume angelegt.</div>';
    return;
  }
  const sorted = groups.slice().sort((a,b) => (a.order||0) - (b.order||0));
  el.innerHTML = sorted.map((g, i) => `
    <div class="manage-row">
      <div class="queue-order-btns">
        <button class="btn-mini" ${i === 0 ? 'disabled' : ''} title="Nach oben" onclick="moveGroupOrder('${g.id}',-1)">&uarr;</button>
        <button class="btn-mini" ${i === sorted.length - 1 ? 'disabled' : ''} title="Nach unten" onclick="moveGroupOrder('${g.id}',1)">&darr;</button>
      </div>
      <div class="manage-info">${g.name}</div>
      <div class="manage-actions">
        <button class="btn-mini" title="Umbenennen" onclick="renameGroup('${g.id}')">Umbenennen</button>
        <button class="btn-mini btn-delete" title="${t('btn_remove')}" onclick="deleteGroup('${g.id}')">&times;</button>
      </div>
    </div>`).join('');
}

async function createGroup(){
  const input = document.getElementById('newGroupName');
  const name = input.value.trim();
  if(!name){ showToast('Bitte einen Namen fuer den Raum eingeben.', 'err'); return; }
  try{
    const res = await fetch('/api/groups', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name})
    });
    if(!res.ok){
      const data = await res.json().catch(() => ({}));
      showToast(data.error || 'Raum konnte nicht angelegt werden.', 'err');
      return;
    }
  } catch(e){
    showToast('Netzwerkfehler beim Anlegen des Raums.', 'err');
    return;
  }
  input.value = '';
  refreshSettingsPanel();
}

async function renameGroup(groupId){
  const current = lastGroupList.find(g => g.id === groupId);
  const name = window.prompt('Neuer Name fuer den Raum:', current ? current.name : '');
  if(name === null) return;
  const trimmed = name.trim();
  if(!trimmed) return;
  try{
    const res = await fetch('/api/groups/' + groupId, {
      method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name: trimmed})
    });
    if(!res.ok){
      const data = await res.json().catch(() => ({}));
      showToast(data.error || 'Raum konnte nicht umbenannt werden.', 'err');
      return;
    }
  } catch(e){
    showToast('Netzwerkfehler beim Umbenennen.', 'err');
    return;
  }
  refreshSettingsPanel();
}

async function deleteGroup(groupId){
  if(!window.confirm('Diesen Raum wirklich entfernen? Zugewiesene Drucker werden NICHT geloescht, ' +
                      'nur die Raum-Zuordnung wird entfernt (erscheinen danach unter "Ohne Raum").')) return;
  try{
    await fetch('/api/groups/' + groupId, { method:'DELETE' });
  } catch(e){
    showToast('Netzwerkfehler beim Entfernen des Raums.', 'err');
  }
  refreshSettingsPanel();
}

async function moveGroupOrder(groupId, direction){
  const ids = lastGroupList.slice().sort((a,b) => (a.order||0) - (b.order||0)).map(g => g.id);
  const idx = ids.indexOf(groupId);
  const newIdx = idx + direction;
  if(idx < 0 || newIdx < 0 || newIdx >= ids.length) return;
  [ids[idx], ids[newIdx]] = [ids[newIdx], ids[idx]];
  try{
    const res = await fetch('/api/groups/reorder', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({order: ids})
    });
    if(!res.ok){
      const data = await res.json().catch(() => ({}));
      showToast(data.error || 'Reihenfolge konnte nicht geaendert werden.', 'err');
      return;
    }
  } catch(e){
    showToast('Netzwerkfehler beim Umsortieren.', 'err');
    return;
  }
  refreshSettingsPanel();
}

function refreshCamerasManageList(cams, groups){
  lastCamsList = cams;
  const el = document.getElementById('camerasManageList');
  if(!cams.length){
    el.innerHTML = '<div class="hint-text">Noch keine externen Kameras hinterlegt.</div>';
    return;
  }
  const groupOptions = currentGroupId => groups.map(gr =>
    `<option value="${gr.id}" ${currentGroupId === gr.id ? 'selected' : ''}>${gr.name}</option>`).join('');
  el.innerHTML = cams.slice().sort((a,b) => (a.order||0) - (b.order||0)).map(c => `
    <div class="manage-row">
      <div class="manage-info">
        ${c.name}
        <div class="manage-sub">${c.url}${c.username ? ' &middot; Anmeldung hinterlegt' : ''}</div>
      </div>
      <div class="manage-actions">
        <select onchange="assignCameraGroup('${c.id}', this.value)">
          <option value="">Kein Raum</option>
          ${groupOptions(c.group_id)}
        </select>
        <button class="btn-mini" title="${t('btn_show')}" onclick="openExternalCam('${c.id}')">${t('btn_show')}</button>
        <button class="btn-mini" title="${t('btn_edit')}" onclick="openCameraModal('${c.id}')">${t('btn_edit')}</button>
        <button class="btn-mini btn-delete" title="${t('btn_remove')}" onclick="deleteRtspCamera('${c.id}')">&times;</button>
      </div>
    </div>`).join('');
}

async function assignCameraGroup(camId, groupId){
  try{
    const res = await fetch('/api/rtsp-cameras/' + camId + '/group', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({group_id: groupId || null})
    });
    if(!res.ok){
      const data = await res.json().catch(() => ({}));
      showToast(data.error || 'Raum konnte nicht zugewiesen werden.', 'err');
    }
  } catch(e){
    showToast('Netzwerkfehler bei der Raum-Zuweisung.', 'err');
  }
  refreshSettingsPanel();
}

// v2.4.0: EIN Modal fuer Anlegen UND Bearbeiten einer externen RTSP-
// Kamera (statt der vorherigen window.prompt()-Kette) - noetig, weil seit
// v2.4.0 zusaetzlich Benutzername/Passwort UND eine Raum-Auswahl erfasst
// werden sollen, was per prompt() nicht mehr vernuenftig bedienbar waere.
// camId gesetzt = Bearbeiten (Felder vorausgefuellt aus lastCamsList),
// sonst Anlegen.
let cameraModalEditId = null;

function openCameraModal(camId){
  cameraModalEditId = camId || null;
  const cam = camId ? lastCamsList.find(c => c.id === camId) : null;
  document.getElementById('cameraModalTitle').textContent = cam ? 'Kamera bearbeiten' : 'Kamera hinzufuegen';
  document.getElementById('cameraModalError').style.display = 'none';
  document.getElementById('cam_name').value = cam ? cam.name : '';
  document.getElementById('cam_url').value = cam ? cam.url : '';
  document.getElementById('cam_username').value = cam ? (cam.username || '') : '';
  document.getElementById('cam_password').value = cam ? (cam.password || '') : '';
  const groupSelect = document.getElementById('cam_group');
  groupSelect.innerHTML = '<option value="">Kein Raum</option>' +
    lastGroupList.map(g => `<option value="${g.id}" ${cam && cam.group_id === g.id ? 'selected' : ''}>${g.name}</option>`).join('');
  document.getElementById('cameraModal').classList.add('show');
}
function closeCameraModal(){
  document.getElementById('cameraModal').classList.remove('show');
  cameraModalEditId = null;
}

async function submitCameraModal(){
  const name = document.getElementById('cam_name').value.trim();
  const url = document.getElementById('cam_url').value.trim();
  const username = document.getElementById('cam_username').value.trim();
  const password = document.getElementById('cam_password').value;
  const groupId = document.getElementById('cam_group').value;
  const errBox = document.getElementById('cameraModalError');
  errBox.style.display = 'none';
  if(!name || !url){
    errBox.textContent = 'Name und RTSP(S)-URL sind Pflichtfelder.';
    errBox.style.display = 'block';
    return;
  }
  const isEdit = !!cameraModalEditId;
  // v2.4.0: beim Anlegen nimmt POST /api/rtsp-cameras group_id direkt
  // entgegen (ein Request genuegt); PUT (Bearbeiten) aendert die Raum-
  // Zuordnung bewusst NICHT mit, um ein versehentliches Leeren beim
  // Weglassen des Felds auszuschliessen - dafuer dort die eigene Route
  // (wie bei Druckern/assignPrinterGroup), daher der zweite Aufruf unten.
  const body = isEdit ? { name, url, username, password } : { name, url, username, password, group_id: groupId || null };
  const endpoint = isEdit ? '/api/rtsp-cameras/' + cameraModalEditId : '/api/rtsp-cameras';
  let res, data;
  try{
    res = await fetch(endpoint, {
      method: isEdit ? 'PUT' : 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
    });
    data = await res.json().catch(() => ({}));
  } catch(e){
    errBox.textContent = 'Netzwerkfehler beim Speichern der Kamera.';
    errBox.style.display = 'block';
    return;
  }
  if(!res.ok){
    errBox.textContent = data.error || 'Kamera konnte nicht gespeichert werden.';
    errBox.style.display = 'block';
    return;
  }
  if(isEdit){
    await fetch('/api/rtsp-cameras/' + cameraModalEditId + '/group', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({group_id: groupId || null})
    });
  }
  closeCameraModal();
  refreshSettingsPanel();
}

async function deleteRtspCamera(camId){
  if(!window.confirm('Diese Kamera wirklich entfernen?')) return;
  try{
    await fetch('/api/rtsp-cameras/' + camId, { method:'DELETE' });
  } catch(e){
    showToast('Netzwerkfehler beim Entfernen der Kamera.', 'err');
  }
  refreshSettingsPanel();
}

async function saveHistorySettings(){
  const raw = document.getElementById('historyMaxJobsInput').value.trim();
  let value = null;
  if(raw !== ''){
    const n = parseInt(raw, 10);
    if(isNaN(n) || n < 0){
      showToast("Bitte eine positive ganze Zahl oder leer lassen (unbegrenzt).", 'err');
      return;
    }
    value = n;
  }
  try{
    const res = await fetch('/api/settings', {
      method:'PUT', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({history_max_jobs: value})
    });
    if(!res.ok){
      const data = await res.json().catch(() => ({}));
      showToast(data.error || 'Einstellung konnte nicht gespeichert werden.', 'err');
      return;
    }
    showToast('Einstellung gespeichert.', 'ok');
  } catch(e){
    showToast('Netzwerkfehler beim Speichern.', 'err');
  }
}

// ----------------------------------------------------------------------
// v2.6.0 NEUES FEATURE: FarmBot - eigenstaendige, drucker-unabhaengige
// Warteschlange mit automatischer Terminierung und Zuweisung an einen
// freien Drucker der gewaehlten Hersteller-/Familienauswahl. Siehe
// DashboardApp-Abschnitt "FarmBot" in app.py fuer den vollstaendigen
// Ablauf und die Begruendung der einzelnen Entscheidungen.
// ----------------------------------------------------------------------
let lastFarmbotList = [];

async function refreshFarmbotPanel(){
  let farmbots;
  try{
    farmbots = await fetch('/api/farmbots').then(r => r.json());
  } catch(e){
    return; // best effort - ein fehlender Abruf soll refresh() nicht blockieren
  }
  lastFarmbotList = farmbots;
  const el = document.getElementById('farmbotPanel');
  if(!el) return;
  const enabled = farmbots.filter(f => f.enabled);
  if(enabled.length === 0){
    el.innerHTML = '';
    return;
  }
  el.innerHTML = enabled.map(cardForFarmbot).join('');
}

function cardForFarmbot(fb){
  const isUltimaker = fb.manufacturer === 'ultimaker';
  const sub = (isUltimaker ? t('farmbot_sub_ultimaker') : t('farmbot_sub_bambu', {family: (fb.bambu_family || '').toUpperCase()}))
    + t('farmbot_sub_suffix', {start: fb.work_start, end: fb.work_end, days: fb.max_queue_days});
  const fitsText = fb.queue_count
    ? t('farmbot_fits_text', {fits: fb.fits_in_workday, total: fb.queue_count})
    : t('farmbot_queue_empty');
  return `
    <div class="farmbot-card">
      <div class="card-head">
        <div>
          <div class="name">${fb.display_name}</div>
          <div class="farmbot-sub">${sub}</div>
        </div>
        <div class="farmbot-actions">
          <span class="type-badge">${t('farmbot_queue_waiting_badge', {count: fb.queue_count})}</span>
          <button class="btn-mini" onclick="openFarmbotQueueModal('${fb.id}')">${t('btn_farmbot_queue')}</button>
        </div>
      </div>
      <div class="hint-text">${fitsText}</div>
      <div class="drop-zone" id="farmbot-dz-${fb.id}"
           ondragover="dzDragOver(event)" ondragleave="dzDragLeave(event)"
           ondrop="farmbotDzDrop(event,'${fb.id}')">
        ${isUltimaker ? t('farmbot_dz_gcode') : t('farmbot_dz_gcode3mf')}
      </div>
      <div class="modal-actions" style="padding-top:12px;">
        <button class="btn" onclick="farmbotStartNext('${fb.id}')">${t('btn_farmbot_start_next')}</button>
      </div>
    </div>`;
}

// v2.6.0: gemeinsame Upload-Logik fuer Drag&Drop direkt auf die Karte,
// Drag&Drop in das Warteschlangen-Modal UND den Datei-Auswahl-Button dort
// - siehe farmbotDzDrop()/farmbotDzDropIntoModal()/addFileToFarmbotQueue().
async function uploadFileToFarmbot(farmbotId, file, zoneEl){
  const fb = lastFarmbotList.find(f => f.id === farmbotId);
  const wantsGcode = fb && fb.manufacturer === 'ultimaker';
  const lower = file.name.toLowerCase();
  if(wantsGcode ? !lower.endsWith('.gcode') : !lower.endsWith('.gcode.3mf')){
    showToast(wantsGcode
      ? 'Nur fertig gesclicte .gcode-Dateien werden unterstuetzt (Export aus Cura).'
      : 'Nur fertig gesclicte .gcode.3mf-Dateien werden unterstuetzt (Export aus Bambu Studio/OrcaSlicer).', 'err');
    return;
  }
  if(zoneEl) zoneEl.classList.add('uploading');
  const form = new FormData();
  form.append('file', file);
  try{
    const res = await fetch('/api/farmbots/' + farmbotId + '/jobs', { method:'POST', body: form });
    const data = await res.json();
    if(!res.ok){
      showToast(data.error || 'Fehler beim Hinzufuegen zur FarmBot-Warteschlange.', 'err');
      return;
    }
    showToast('Zur FarmBot-Warteschlange hinzugefuegt.', 'ok');
  } catch(e){
    showToast('Netzwerkfehler beim Hochladen.', 'err');
    return;
  } finally {
    if(zoneEl) zoneEl.classList.remove('uploading');
  }
  await refreshFarmbotPanel();
  if(farmbotQueueModalId === farmbotId) await refreshFarmbotQueueModal();
}

async function farmbotDzDrop(ev, farmbotId){
  ev.preventDefault();
  const zone = ev.currentTarget;
  zone.classList.remove('dragover');
  const files = ev.dataTransfer.files;
  if(!files || files.length === 0) return;
  await uploadFileToFarmbot(farmbotId, files[0], zone);
}

async function farmbotDzDropIntoModal(ev){
  ev.preventDefault();
  const zone = ev.currentTarget;
  zone.classList.remove('dragover');
  const files = ev.dataTransfer.files;
  if(!files || files.length === 0 || !farmbotQueueModalId) return;
  await uploadFileToFarmbot(farmbotQueueModalId, files[0], zone);
}

async function addFileToFarmbotQueue(farmbotId, inputEl){
  const file = inputEl.files[0];
  inputEl.value = '';
  if(!file) return;
  await uploadFileToFarmbot(farmbotId, file, null);
}

// v2.6.0: Warteschlangen-Modal eines FarmBot - Aufbau/Verhalten bewusst
// angelehnt an das Warteschlangen-Modal eines einzelnen Druckers
// (openQueueModal()/refreshQueueModal()), aber OHNE manuelle Umsortier-
// Pfeile (die Reihenfolge wird hier immer automatisch neu berechnet,
// siehe DashboardApp._reorder_farmbot_queue()).
let farmbotQueueModalId = null;

async function openFarmbotQueueModal(farmbotId){
  farmbotQueueModalId = farmbotId;
  const fb = lastFarmbotList.find(f => f.id === farmbotId);
  document.getElementById('farmbotQueueModalTitle').textContent =
    (fb ? fb.display_name : t('farmbot_default_name')) + t('farmbot_queue_modal_title_suffix');
  document.getElementById('farmbotQueueModalBody').innerHTML = `<div class="history-empty">${t('loading_generic')}</div>`;
  document.getElementById('farmbotQueueModal').classList.add('show');
  await refreshFarmbotQueueModal();
}

function closeFarmbotQueueModal(){
  document.getElementById('farmbotQueueModal').classList.remove('show');
  document.getElementById('farmbotQueueModalBody').innerHTML = '';
  farmbotQueueModalId = null;
}

async function refreshFarmbotQueueModal(){
  const farmbotId = farmbotQueueModalId;
  if(!farmbotId) return;
  const body = document.getElementById('farmbotQueueModalBody');
  const hint = document.getElementById('farmbotQueueHint');
  const btn = document.getElementById('farmbotQueueNextBtn');
  let entries;
  try{
    entries = await fetch('/api/farmbots/' + farmbotId + '/jobs').then(r => r.json());
  } catch(e){
    body.innerHTML = '<div class="history-empty">Warteschlange konnte nicht geladen werden.</div>';
    return;
  }
  if(farmbotQueueModalId !== farmbotId) return; // Modal wurde inzwischen geschlossen/gewechselt
  btn.disabled = !(entries && entries.length);
  hint.textContent = (entries && entries.length) ? '' : 'Die Warteschlange ist leer.';
  if(!entries || entries.length === 0){
    body.innerHTML = '<div class="history-empty">Die Warteschlange ist leer.</div>';
    return;
  }
  // Aeltester (=naechster) Auftrag zuerst - siehe PrintQueueStore-Kommentar.
  // v2.7.0: Pfeile fuer haendische Umsortierung (siehe moveFarmbotQueueEntry())
  // - wird beim naechsten Datei-Upload automatisch wieder ueberschrieben
  // (siehe Hinweistext unten und DashboardApp.add_farmbot_job()).
  body.innerHTML = entries.map((e, i) => {
    const thumb = e.has_image
      ? `<img class="history-thumb" src="/api/farmbots/${farmbotId}/jobs/${e.job_id}/thumbnail" alt="">`
      : `<div class="history-thumb-placeholder">${FILE_ICON}</div>`;
    const label = (i === 0) ? '<b>Naechster:</b> ' : '';
    const durText = formatDuration(e.duration_sec);
    const durHtml = durText ? ` &middot; Druckzeit ca. ${durText}` : ' &middot; Druckzeit unbekannt (wird ans Ende gestellt)';
    return `
      <div class="history-item queue-item">
        <div class="queue-order-btns">
          <button class="btn-mini" ${i === 0 ? 'disabled' : ''} title="Nach oben" onclick="moveFarmbotQueueEntry('${farmbotId}','${e.job_id}',-1)">&uarr;</button>
          <button class="btn-mini" ${i === entries.length - 1 ? 'disabled' : ''} title="Nach unten" onclick="moveFarmbotQueueEntry('${farmbotId}','${e.job_id}',1)">&darr;</button>
        </div>
        ${thumb}
        <div class="history-body">
          <div class="history-filename">${label}${e.filename}</div>
          <div class="history-date">In Warteschlange seit ${e.added_at}${durHtml}</div>
        </div>
        <div class="history-actions">
          <button class="btn-mini btn-delete" onclick="deleteFarmbotQueueEntry('${farmbotId}','${e.job_id}')">${t('btn_delete')}</button>
        </div>
      </div>`;
  }).join('');
}

// v2.7.0: haendische Umsortierung der FarmBot-Warteschlange, auf
// ausdruecklichen Nutzerwunsch - Aufbau identisch zu moveQueueEntry()
// (Warteschlange eines einzelnen Druckers). Die so gewaehlte Reihenfolge
// bleibt bestehen, bis der naechste Auftrag hinzugefuegt wird - DANACH
// sortiert DashboardApp.add_farmbot_job() automatisch wieder neu (siehe
// _reorder_farmbot_queue()), unveraendert wie seit v2.6.0.
async function moveFarmbotQueueEntry(farmbotId, jobId, direction){
  let entries;
  try{
    entries = await fetch('/api/farmbots/' + farmbotId + '/jobs').then(r => r.json());
  } catch(e){
    showToast('Netzwerkfehler beim Umsortieren.', 'err');
    return;
  }
  const ids = entries.map(e => e.job_id);
  const idx = ids.indexOf(jobId);
  const newIdx = idx + direction;
  if(idx < 0 || newIdx < 0 || newIdx >= ids.length) return;
  [ids[idx], ids[newIdx]] = [ids[newIdx], ids[idx]];
  try{
    const res = await fetch('/api/farmbots/' + farmbotId + '/jobs/reorder', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({order: ids})
    });
    if(!res.ok){
      const data = await res.json().catch(() => ({}));
      showToast(data.error || 'Reihenfolge konnte nicht geaendert werden.', 'err');
      return;
    }
  } catch(e){
    showToast('Netzwerkfehler beim Umsortieren.', 'err');
    return;
  }
  await refreshFarmbotQueueModal();
}

async function deleteFarmbotQueueEntry(farmbotId, jobId){
  try{
    const res = await fetch('/api/farmbots/' + farmbotId + '/jobs/' + jobId, { method:'DELETE' });
    if(!res.ok){
      const data = await res.json().catch(() => ({}));
      showToast(data.error || 'Warteschlangen-Eintrag konnte nicht geloescht werden.', 'err');
      return;
    }
  } catch(e){
    showToast('Netzwerkfehler beim Loeschen.', 'err');
    return;
  }
  await refreshFarmbotPanel();
  if(farmbotQueueModalId === farmbotId) await refreshFarmbotQueueModal();
}

// v2.6.0: "Naechsten Druck starten" - zweistufig: pick_farmbot_job()
// (serverseitig OHNE Seiteneffekt) ermittelt Auftrag + Zieldrucker und
// meldet, ob eine Kamera-Bestaetigung "Druckraum frei" noetig ist (siehe
// DashboardApp.pick_farmbot_job() - nur wenn der Zieldrucker zuvor etwas
// fertig gedruckt hat); erst danach fuehrt farmbotDoAssign() die
// tatsaechliche Zuweisung/den Druckstart aus (assign_farmbot_job()).
let farmbotPendingPick = null;

async function farmbotStartNext(farmbotId, excludePrinterIds){
  let data;
  try{
    const res = await fetch('/api/farmbots/' + farmbotId + '/pick', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ exclude_printer_ids: excludePrinterIds || [] })
    });
    data = await res.json();
    if(!res.ok){
      showToast(data.error || 'Aktuell kein naechster Druck moeglich.', 'err');
      return;
    }
  } catch(e){
    showToast('Netzwerkfehler.', 'err');
    return;
  }
  farmbotPendingPick = {
    farmbotId: farmbotId,
    jobId: data.job_id,
    printerId: data.printer_id,
    excludePrinterIds: (excludePrinterIds || []).slice(),
  };
  if(data.needs_bed_confirm){
    openFarmbotBedModal(data);
  } else {
    await farmbotDoAssign();
  }
}

// v2.6.0: Kamera-Bestaetigung "Druckraum frei" - nur wenn der Zieldrucker
// zuvor etwas fertig gedruckt hat (siehe pick_farmbot_job()). "Anderer
// Drucker" wiederholt die Auswahl unter Ausschluss dieses Druckers.
function openFarmbotBedModal(data){
  document.getElementById('farmbotBedModalHint').textContent =
    `"${data.filename}" soll auf "${data.printer_name}" gedruckt werden - dieser Drucker hat zuvor bereits ` +
    `etwas fertig gedruckt. Bitte zunaechst den Druckraum leeren, dann bestaetigen - oder einen anderen ` +
    `Drucker waehlen lassen.`;
  const img = document.getElementById('farmbotBedCamImg');
  img.onerror = function(){ img.style.display = 'none'; };
  img.style.display = '';
  img.src = '/camera/' + data.printer_id + '?_=' + Date.now();
  document.getElementById('farmbotBedModal').classList.add('show');
}

function closeFarmbotBedModal(){
  const img = document.getElementById('farmbotBedCamImg');
  img.onerror = null;
  img.src = '';
  document.getElementById('farmbotBedModal').classList.remove('show');
}

async function farmbotBedOtherPrinter(){
  if(!farmbotPendingPick) return;
  const { farmbotId, printerId, excludePrinterIds } = farmbotPendingPick;
  farmbotPendingPick = null;
  closeFarmbotBedModal();
  await farmbotStartNext(farmbotId, excludePrinterIds.concat([printerId]));
}

async function farmbotBedConfirmFree(){
  closeFarmbotBedModal();
  await farmbotDoAssign();
}

async function farmbotDoAssign(){
  if(!farmbotPendingPick) return;
  const { farmbotId, jobId, printerId } = farmbotPendingPick;
  farmbotPendingPick = null;
  let data;
  try{
    const res = await fetch('/api/farmbots/' + farmbotId + '/assign', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ job_id: jobId, printer_id: printerId })
    });
    data = await res.json();
    if(!res.ok){
      showToast(data.error || 'Fehler beim Starten des Druckauftrags.', 'err');
      return;
    }
  } catch(e){
    showToast('Netzwerkfehler beim Starten.', 'err');
    return;
  }
  if(data.mode === 'bambu'){
    // v2.6.0: Zuordnung erfolgt bewusst HIER (nach Drucker-Auswahl UND
    // Bestaetigung der Verfuegbarkeit) - siehe assign_farmbot_job(). Der
    // bestehende AMS-Dialog kuemmert sich um den Rest (confirmAmsModal()
    // sendet an /api/printers/<id>/print/confirm, identisch zum manuellen
    // Drag&Drop-Upload).
    openAmsModal(data.printer_id, data);
  } else {
    showToast('Druck gestartet.', 'ok');
  }
  await refreshFarmbotPanel();
  if(farmbotQueueModalId === farmbotId) await refreshFarmbotQueueModal();
}

// v2.6.0: FarmBot-Verwaltung im Einstellungen-Modus (Anlegen/Bearbeiten/
// Loeschen/Aktivieren) - Aufbau angelehnt an refreshCamerasManageList()/
// openCameraModal().
function refreshFarmbotManageList(farmbots){
  lastFarmbotList = farmbots;
  const el = document.getElementById('farmbotManageList');
  if(!farmbots.length){
    el.innerHTML = `<div class="hint-text">${t('empty_no_farmbots')}</div>`;
    return;
  }
  el.innerHTML = farmbots.map(fb => `
    <div class="manage-row">
      <div class="manage-info">
        ${fb.display_name}${fb.enabled ? '' : ` <span class="hint-text">(${t('farmbot_disabled_hint')})</span>`}
        <div class="manage-sub">
          ${fb.manufacturer === 'bambu' ? t('farmbot_sub_bambu', {family: (fb.bambu_family || '').toUpperCase()}) : t('farmbot_sub_ultimaker')}
          ${t('farmbot_manage_sub_suffix', {start: fb.work_start, end: fb.work_end, days: fb.max_queue_days})}
        </div>
      </div>
      <div class="manage-actions">
        <button class="btn-mini" onclick="toggleFarmbotEnabled('${fb.id}', ${!fb.enabled})">${fb.enabled ? t('btn_disable') : t('btn_enable')}</button>
        <button class="btn-mini" title="${t('btn_edit')}" onclick="startEditFarmbot('${fb.id}')">${t('btn_edit')}</button>
        <button class="btn-mini btn-delete" title="${t('btn_remove')}" onclick="deleteFarmbot('${fb.id}')">&times;</button>
      </div>
    </div>`).join('');
}

async function toggleFarmbotEnabled(farmbotId, newEnabled){
  const fb = lastFarmbotList.find(f => f.id === farmbotId);
  if(!fb) return;
  await saveFarmbotFields(farmbotId, Object.assign({}, fb, { enabled: newEnabled }));
}

let farmbotModalEditId = null;

function toggleFarmbotManufacturerFields(){
  const isUltimaker = document.getElementById('fb_manufacturer').value === 'ultimaker';
  document.getElementById('farmbotBambuFields').style.display = isUltimaker ? 'none' : '';
  document.getElementById('farmbotUltimakerHint').style.display = isUltimaker ? '' : 'none';
}

function openAddFarmbotModal(){
  farmbotModalEditId = null;
  document.getElementById('farmbotModalTitle').textContent = 'FarmBot hinzufuegen';
  document.getElementById('farmbotModalError').style.display = 'none';
  document.getElementById('fb_name_suffix').value = '';
  document.getElementById('fb_enabled').checked = true;
  document.getElementById('fb_manufacturer').value = 'bambu';
  document.getElementById('fb_bambu_family').value = 'x1';
  document.getElementById('fb_work_start').value = '08:00';
  document.getElementById('fb_work_end').value = '18:00';
  document.getElementById('fb_max_queue_days').value = '3';
  toggleFarmbotManufacturerFields();
  document.getElementById('farmbotModal').classList.add('show');
}

function startEditFarmbot(farmbotId){
  const fb = lastFarmbotList.find(f => f.id === farmbotId);
  if(!fb) return;
  farmbotModalEditId = farmbotId;
  document.getElementById('farmbotModalTitle').textContent = 'FarmBot bearbeiten';
  document.getElementById('farmbotModalError').style.display = 'none';
  document.getElementById('fb_name_suffix').value = fb.name_suffix || '';
  document.getElementById('fb_enabled').checked = !!fb.enabled;
  document.getElementById('fb_manufacturer').value = fb.manufacturer;
  document.getElementById('fb_bambu_family').value = fb.bambu_family || 'x1';
  document.getElementById('fb_work_start').value = fb.work_start;
  document.getElementById('fb_work_end').value = fb.work_end;
  document.getElementById('fb_max_queue_days').value = fb.max_queue_days;
  toggleFarmbotManufacturerFields();
  document.getElementById('farmbotModal').classList.add('show');
}

function closeFarmbotModal(){
  document.getElementById('farmbotModal').classList.remove('show');
  farmbotModalEditId = null;
}

function collectFarmbotModalFields(){
  return {
    name_suffix: document.getElementById('fb_name_suffix').value.trim(),
    enabled: document.getElementById('fb_enabled').checked,
    manufacturer: document.getElementById('fb_manufacturer').value,
    bambu_family: document.getElementById('fb_bambu_family').value,
    work_start: document.getElementById('fb_work_start').value.trim(),
    work_end: document.getElementById('fb_work_end').value.trim(),
    max_queue_days: document.getElementById('fb_max_queue_days').value.trim(),
  };
}

async function submitFarmbotModal(){
  const data = collectFarmbotModalFields();
  const errBox = document.getElementById('farmbotModalError');
  errBox.style.display = 'none';
  const isEdit = !!farmbotModalEditId;
  let res, resData;
  try{
    res = await fetch(isEdit ? '/api/farmbots/' + farmbotModalEditId : '/api/farmbots', {
      method: isEdit ? 'PUT' : 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)
    });
    resData = await res.json().catch(() => ({}));
  } catch(e){
    errBox.textContent = 'Netzwerkfehler beim Speichern.';
    errBox.style.display = 'block';
    return;
  }
  if(!res.ok){
    errBox.textContent = resData.error || 'FarmBot konnte nicht gespeichert werden.';
    errBox.style.display = 'block';
    return;
  }
  closeFarmbotModal();
  showToast('Gespeichert.', 'ok');
  refreshSettingsPanel();
}

async function saveFarmbotFields(farmbotId, data){
  try{
    const res = await fetch('/api/farmbots/' + farmbotId, {
      method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)
    });
    if(!res.ok){
      const resData = await res.json().catch(() => ({}));
      showToast(resData.error || 'Aenderung konnte nicht gespeichert werden.', 'err');
      return;
    }
  } catch(e){
    showToast('Netzwerkfehler beim Speichern.', 'err');
    return;
  }
  refreshSettingsPanel();
}

async function deleteFarmbot(farmbotId){
  try{
    const res = await fetch('/api/farmbots/' + farmbotId, { method:'DELETE' });
    if(!res.ok){
      const data = await res.json().catch(() => ({}));
      showToast(data.error || 'FarmBot konnte nicht entfernt werden.', 'err');
      return;
    }
  } catch(e){
    showToast('Netzwerkfehler beim Entfernen.', 'err');
    return;
  }
  showToast('FarmBot entfernt.', 'ok');
  refreshSettingsPanel();
}

// v2.8.0: Sprache muss vor dem ersten refresh()/applyTranslations()-Lauf
// feststehen, da sonst Kacheln kurz in der falschen Sprache aufblitzen
// wuerden. Bei frischer Installation (noch keine config.json beim
// Programmstart, siehe CONFIG_WAS_FRESH/first_run) wird stattdessen
// zunaechst die Sprachauswahl gezeigt - erst danach startet der normale
// Seitenaufbau (inkl. periodischem refresh()).
async function initLanguageAndStart(){
  let settings = {};
  try{
    settings = await fetch('/api/settings').then(r => r.json());
  }catch(e){}
  if(settings && settings.language && I18N[settings.language]){
    currentLang = settings.language;
  }
  applyTranslations();
  populateLanguageSelect();
  setLayoutCols(getLayoutCols());
  loadVersion();
  if(settings && settings.first_run){
    showFirstRunLanguagePicker();
  }
  refresh();
  setInterval(refresh, 2500);
}
initLanguageAndStart();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    host = dash.cfg["server"].get("host", "0.0.0.0")
    port = int(dash.cfg["server"].get("port", 8000))
    print(f"Dashboard laeuft auf http://{host}:{port}  (im lokalen Netz erreichbar ueber die IP dieses PCs)")
    app.run(host=host, port=port, debug=False, threaded=True)
