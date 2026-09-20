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
APP_VERSION = "2.1.0"

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

from flask import Flask, jsonify, request, Response, render_template_string, redirect, send_file
from werkzeug.utils import secure_filename
import paho.mqtt.client as mqtt


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


CONFIG_PATH = os.path.join(base_dir(), "config.json")
LOCK = threading.Lock()

DEFAULT_CONFIG = {
    "server": {
        "host": "0.0.0.0",
        "port": 8000
    },
    "preform_server": "http://localhost:44388",
    "extras_mqtt": {
        "enabled": False,
        "host": "",
        "port": 1883,
        "username": "",
        "password": "",
        "tls": False
    },
    "printers": []
}

FORMLABS_TYPES = ("formlabs", "formlabs_wash", "formlabs_cure")
# Alle Creality-"Versionen" nutzen technisch dieselbe Anbindung (Moonraker-
# API, siehe CrealityConnection) - die verschiedenen Typwerte dienen nur
# der Beschriftung/Auswahl im Formular, nicht einer unterschiedlichen
# technischen Anbindung.
CREALITY_TYPES = ("creality_k1", "creality_k1c", "creality_k1max", "creality_k1se", "creality_other")
KNOWN_TYPES = ("bambu",) + FORMLABS_TYPES + ("octoprint",) + CREALITY_TYPES + ("ultimaker",)


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
# ----------------------------------------------------------------------
PRINT_HISTORY_MAX_JOBS = 30  # aelteste Eintraege werden je Drucker automatisch entfernt

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
# Bambu deshalb EXPLIZIT einen dieser beiden Zustaende: "FINISH" (Druck
# soeben abgeschlossen) oder "IDLE" (Drucker war zuvor gar nicht am
# Drucken - z. B. frisch gestarteter/verbundener Drucker mit bereits
# vorbefuellter Warteschlange).
BAMBU_READY_FOR_NEXT_STATES = {"FINISH", "IDLE"}


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

    MAX_JOBS_PER_PRINTER = PRINT_HISTORY_MAX_JOBS

    def __init__(self):
        self._lock = threading.Lock()

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

            entry = {
                "job_id": job_id,
                "filename": filename,
                "file_ext": ext,
                "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "has_image": has_image,
            }
            with self._lock:
                entries = self._load_index(printer_id)
                entries.insert(0, entry)
                removed = entries[self.MAX_JOBS_PER_PRINTER:]
                entries = entries[:self.MAX_JOBS_PER_PRINTER]
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

    Ablage: "<Ordner der exe/des Skripts>/print_queue/<drucker_id>/"."""

    def __init__(self):
        self._lock = threading.Lock()

    def dir_for(self, printer_id: str) -> str:
        d = os.path.join(base_dir(), "print_queue", printer_id)
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

            entry = {
                "job_id": job_id,
                "filename": filename,
                "file_ext": ext,
                "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "has_image": has_image,
                "history_ref": history_ref,
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
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("server", DEFAULT_CONFIG["server"])
    cfg.setdefault("preform_server", DEFAULT_CONFIG["preform_server"])
    cfg.setdefault("extras_mqtt", json.loads(json.dumps(DEFAULT_CONFIG["extras_mqtt"])))
    cfg.setdefault("printers", [])
    for p in cfg["printers"]:
        p.setdefault("extras", [])
        if p.get("type") == "bambu":
            p.setdefault("bambu_family", "x1")
    return cfg


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
            "ams": []
        }
        self._client = None
        self._stop = False
        self._paused = False
        self._last_pushall = 0.0

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
            except Exception:
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
        if rc == 0:
            self.status["connected"] = True
            topic = f"device/{self.cfg['serial']}/report"
            client.subscribe(topic)
            self._request_pushall(client)
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
        self.status["connected"] = False

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8", errors="ignore"))
        except Exception:
            return
        p = payload.get("print")
        if p:
            self._apply_print_report(p)
        if time.time() - self._last_pushall > self.PUSHALL_INTERVAL_SEC:
            self._request_pushall(client)

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
        if "chamber_temper" in p:
            s["chamber_temp"] = p["chamber_temper"]
        if "nozzle_temper" in p:
            s["nozzle_temp"] = p["nozzle_temper"]
        if "bed_temper" in p:
            s["bed_temp"] = p["bed_temper"]
        if "mc_remaining_time" in p:
            s["remaining_min"] = p["mc_remaining_time"]

        ams_root = p.get("ams", {}).get("ams")
        if isinstance(ams_root, list):
            slots = []
            for unit in ams_root:
                for tray in unit.get("tray", []):
                    slots.append({
                        "slot": f'{unit.get("id", "0")}-{tray.get("id", "0")}',
                        "type": tray.get("tray_type") or "-",
                        "color": _argb_to_css(tray.get("tray_color")),
                        "remain": tray.get("remain", -1)
                    })
            s["ams"] = slots

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
    # LAN-Modus aktiviert sein (Bambu Handy App -> Drucker -> Einstellungen
    # -> "Developer Mode" bzw. "LAN Only Mode"). Ohne das lehnt neuere
    # Firmware den project_file-Befehl ab. Siehe README, Abschnitt "Bambu
    # Lab: Druckauftrag per Drag & Drop senden".
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
        get AMS mapping table" - siehe UEBERGABE.md fuer Details."""
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
        payload = {
            "print": {
                "sequence_id": "0",
                "command": "project_file",
                "param": "Metadata/plate_1.gcode",
                "url": f"file:///sdcard/{remote_name}",
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
        req_topic = f"device/{self.cfg['serial']}/request"
        result = self._client.publish(req_topic, json.dumps(payload))
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError("MQTT-Befehl zum Druckstart konnte nicht gesendet werden.")


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
    Bambu dokumentiert)."""
    try:
        unit_str, tray_str = slot.split("-", 1)
        return int(unit_str) * 4 + int(tray_str)
    except Exception:
        return -1


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
    None statt zu raten, wenn nichts hinreichend gut passt."""
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
        self.history = PrintHistoryStore()
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
            "extras": []
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

    def _resolve_extras(self, printer_cfg):
        out = []
        for ex in printer_cfg.get("extras", []):
            item = dict(ex)
            if ex.get("kind") == "sensor":
                item["value"] = self.extras.get_value(ex.get("topic"))
            out.append(item)
        return out

    def all_status(self):
        out = []
        for p in self.cfg["printers"]:
            conn = self.connections.get(p["id"])
            item = {
                "id": p["id"],
                "name": p["name"],
                "ip": p["ip"],
                "type": p.get("type", "bambu"),
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

    def prepare_print_job(self, printer_id, local_path, remote_name, history_ref=None, queue_ref=None):
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
        ("FINISH" oder "IDLE"), siehe Kommentar dort. Uebergangszustaende
        wie "PREPARE"/"SLICING" gelten damit bewusst NICHT als bereit,
        obwohl sie nicht in PRINTER_BUSY_STATES stehen. Fuer alle anderen
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

    def send_ultimaker_print_now(self, printer_id, local_path, filename, history_ref=None, queue_ref=None):
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
                return False, ("Dieser Bambu-Lab-Drucker ist noch nicht fertig (Status muss FINISH "
                                "oder IDLE sein) - die Warteschlange kann erst fortgesetzt werden, "
                                "wenn der aktuelle Druck abgeschlossen ist."), None
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
  /* MK6: main = #printerList - Karten-Layout wahlweise 1/2/3-spaltig,
     siehe .cols-2/.cols-3 (per JS umgeschaltet, Wahl lokal gespeichert). */
  main{
    padding:28px 32px; max-width:1100px; margin:0 auto;
    display:grid; grid-template-columns:1fr; gap:22px; align-items:start;
  }
  main.cols-2{ max-width:1600px; grid-template-columns:repeat(2, 1fr); }
  main.cols-3{ max-width:2000px; grid-template-columns:repeat(3, 1fr); }
  @media(max-width:1150px){
    main.cols-3{ grid-template-columns:repeat(2, 1fr); max-width:1600px; }
  }
  @media(max-width:760px){
    main.cols-2, main.cols-3{ grid-template-columns:1fr; max-width:1100px; }
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
  }
  .temp-chip b{ color:var(--text); font-size:13px; }

  .ams-title{ font-size:11px; text-transform:uppercase; letter-spacing:0.6px; color:var(--text-dim); margin-bottom:10px;}
  .ams-slot{ display:flex; align-items:center; gap:10px; margin-bottom:9px; }
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

  .cam-modal .modal{ width:auto; padding:0; overflow:hidden; }
  .cam-modal img{ display:block; max-width:90vw; max-height:80vh; background:#000; }
  .cam-modal .cam-close{
    position:absolute; top:14px; right:20px; color:#fff; font-size:26px; cursor:pointer; z-index:60;
  }

  /* MK6: Druckauftrags-Verlauf */
  .history-modal{ width:460px; }
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
    display:flex; justify-content:flex-end; margin:-8px 0 10px 0; gap:8px;
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
  <div style="display:flex; align-items:center; gap:14px;">
    <!-- MK6: Layout-Umschalter 1/2/3-spaltig, siehe setLayoutCols()/getLayoutCols() -->
    <div class="layout-switch" title="Kartenlayout">
      <button type="button" class="layout-btn" data-cols="1" onclick="setLayoutCols(1)">1</button>
      <button type="button" class="layout-btn" data-cols="2" onclick="setLayoutCols(2)">2</button>
      <button type="button" class="layout-btn" data-cols="3" onclick="setLayoutCols(3)">3</button>
    </div>
    <button class="btn" onclick="openAddModal()">+ Drucker hinzufuegen</button>
  </div>
</header>

<main id="printerList"></main>

<!-- Modal: Drucker hinzufuegen -->
<div class="modal-backdrop" id="addModal">
  <div class="modal">
    <h2>Neuen Drucker hinzufuegen</h2>
    <div class="error-msg" id="addError"></div>

    <label>Druckertyp</label>
    <select id="f_type" onchange="toggleTypeFields()">
      <option value="bambu">Bambu Lab</option>
      <option value="formlabs">Formlabs (Drucker)</option>
      <option value="formlabs_wash">Formlabs Wash L</option>
      <option value="formlabs_cure">Formlabs Cure L</option>
      <option value="octoprint">OctoPrint</option>
      <option value="creality_k1">Creality K1</option>
      <option value="creality_k1c">Creality K1C</option>
      <option value="creality_k1max">Creality K1 Max</option>
      <option value="creality_k1se">Creality K1 SE</option>
      <option value="creality_other">Creality (sonstiger Klipper-Drucker)</option>
      <option value="ultimaker">Ultimaker</option>
    </select>

    <label>Name</label>
    <input id="f_name" placeholder="z. B. X1C Werkstatt">
    <label>IP-Adresse des Geraets</label>
    <input id="f_ip" placeholder="192.168.1.50">

    <div id="bambuFields">
      <label>Access Code (LAN-Modus, Drucker-Display &rarr; Einstellungen)</label>
      <input id="f_code" placeholder="8-stelliger Code">
      <label>Seriennummer</label>
      <input id="f_serial" placeholder="z. B. 01P00A123456789">
      <label>Druckerfamilie</label>
      <select id="f_bambu_family">
        <option value="x1">X1-Serie (X1C, X1E)</option>
        <option value="a1">A1-Serie (A1, A1 Mini)</option>
        <option value="h2">H2-Serie (H2S, H2D, H2D Pro, H2C)</option>
        <option value="p1">P1-Serie (P1P, P1S)</option>
        <option value="p2">P2-Serie (P2S)</option>
        <option value="x2">X2-Serie (X2D)</option>
      </select>
      <div class="hint-text">
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

    <div id="formlabsHint" class="hint-text">
      Benoetigt den lokal laufenden "PreFormServer" (Formlabs Local API,
      Teil der PreForm-Installation) - siehe README.
    </div>

    <div id="octoprintFields">
      <label>API-Key</label>
      <input id="f_apikey" placeholder="OctoPrint-Einstellungen &rarr; API">
      <label>Port</label>
      <input id="f_port" placeholder="80">
      <div class="checkbox-row">
        <input type="checkbox" id="f_https">
        <label style="margin:0;">HTTPS verwenden</label>
      </div>
      <label>Webcam-URL (optional)</label>
      <input id="f_webcam" placeholder="http://IP:8080/webcam/?action=stream">
    </div>

    <div id="crealityFields">
      <div class="hint-text">
        Benoetigt Moonraker auf dem Drucker (bei werkseitigen K1/K1C/K1 Max/
        K1 SE muss dafuer erst per SSH "gerootet" werden) - siehe README.
      </div>
      <label>API-Key (meist nicht noetig, siehe README)</label>
      <input id="f_creality_apikey" placeholder="optional">
      <label>Moonraker-Port</label>
      <input id="f_creality_port" placeholder="7125">
      <label>Webcam-URL (optional)</label>
      <input id="f_creality_webcam" placeholder="http://IP/webcam/?action=stream">
    </div>

    <div id="ultimakerFields">
      <div class="hint-text">
        Nutzt die offizielle, unauthentifizierte lokale Ultimaker-API -
        kein Login/API-Key noetig, siehe README.
      </div>
      <label>Port (optional)</label>
      <input id="f_ultimaker_port" placeholder="80">
      <label>Webcam-URL (optional)</label>
      <input id="f_ultimaker_webcam" placeholder="http://IP:8080/?action=stream">
    </div>

    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeAddModal()">Abbrechen</button>
      <button class="btn" onclick="submitAdd()">Hinzufuegen</button>
    </div>
  </div>
</div>

<!-- Modal: Kamera -->
<div class="modal-backdrop cam-modal" id="camModal">
  <span class="cam-close" onclick="closeCam()">&times;</span>
  <div class="modal">
    <img id="camImg" src="">
  </div>
</div>

<!-- Modal: AMS-Zuordnung pruefen/korrigieren vor dem Drucken -->
<div class="modal-backdrop" id="amsModal">
  <div class="modal ams-modal">
    <h2>AMS-Zuordnung pruefen</h2>
    <div class="file-name" id="amsModalFilename" style="margin-bottom:16px;"></div>
    <div id="amsModalRows"></div>
    <div class="ams-progress-wrap" id="amsProgressWrap" style="display:none;">
      <div class="ams-progress-track"><div class="ams-progress-bar" id="amsProgressBar" style="width:0%"></div></div>
      <div class="ams-progress-label" id="amsProgressLabel"></div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-ghost" id="amsModalCancelBtn" onclick="cancelAmsModal()">Abbrechen</button>
      <button class="btn" id="amsModalConfirmBtn" onclick="confirmAmsModal()">Drucken starten</button>
    </div>
  </div>
</div>

<!-- Modal: Druckauftrags-Verlauf (MK6) -->
<div class="modal-backdrop" id="historyModal">
  <div class="modal history-modal">
    <h2>Druckauftrags-Verlauf</h2>
    <div class="history-modal-tools">
      <button class="btn-mini" id="historySortBtn" onclick="toggleHistorySort()">Sortierung: Neueste zuerst</button>
    </div>
    <div id="historyModalBody"></div>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeHistoryModal()">Schliessen</button>
    </div>
  </div>
</div>

<!-- Modal: Warteschlange (MK6 v1.2.0) -->
<div class="modal-backdrop" id="queueModal">
  <div class="modal history-modal">
    <h2>Warteschlange</h2>
    <!-- v2.1.0: Datei kann per Drag & Drop hierher gezogen werden -
         genau wie auf die Drucker-Kachel selbst (dzDrop()/dzDropUltimaker()) -
         oder ueber den Datei-Auswahl-Button darin. -->
    <div class="drop-zone queue-drop-zone" id="queueDropZone"
         ondragover="dzDragOver(event)"
         ondragleave="dzDragLeave(event)"
         ondrop="dzDropQueue(event)">
      Datei hier ablegen, um sie in die Warteschlange zu legen
      <div class="dz-hint">
        oder
        <label class="btn-mini file-btn">
          Datei auswaehlen
          <input type="file" style="display:none" onchange="addFileToQueue(queueModalPrinterId, this)">
        </label>
      </div>
    </div>
    <div id="queueModalBody"></div>
    <!-- v2.0.1: Hinweistext + Deaktivierung siehe updateQueueSendButtonState() -->
    <div class="hint-text" id="queueSendHint" style="margin-top:10px;"></div>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeQueueModal()">Schliessen</button>
      <button class="btn" id="queueSendNextBtn" onclick="sendNextQueued(queueModalPrinterId)">Druckraum leer - naechsten senden</button>
    </div>
  </div>
</div>

<!-- Modal: Auftrag einem anderen Drucker zuweisen (MK6 v1.2.0) -->
<div class="modal-backdrop" id="assignModal">
  <div class="modal">
    <h2>Auftrag zuweisen</h2>
    <label>Ziel-Drucker</label>
    <select id="assignTargetSelect"></select>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeAssignModal()">Abbrechen</button>
      <button class="btn" onclick="confirmAssign()">Zuweisen</button>
    </div>
  </div>
</div>

<!-- Toasts (unabhaengig vom Drucker-Grid, ueberleben refresh()) -->
<div class="toast-container" id="toastContainer"></div>

<script>
const CAM_ICON = `<svg viewBox="0 0 24 24"><path d="M4 7h3l1.5-2h7L17 7h3a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2zm8 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"/></svg>`;
const HIST_ICON = `<svg viewBox="0 0 24 24"><path d="M13 3a9 9 0 1 0 8.94 10h-2.02A7 7 0 1 1 13 5v4l5-4-5-4z"/><path d="M12 8v5l4 2-.75 1.3L11 14V8z"/></svg>`;
const FILE_ICON = `<svg viewBox="0 0 24 24"><path d="M6 2h9l5 5v15H6zm8 1.5V8h4.5z"/></svg>`;
// MK6 v1.2.0: Warteschlangen-Symbol (Listen-Icon) fuer die Kachel.
const QUEUE_ICON = `<svg viewBox="0 0 24 24"><path d="M3 5h18v2H3zm0 6h18v2H3zm0 6h12v2H3z"/></svg>`;

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
  refresh();
}

async function deletePrinter(id){
  if(!confirm('Diesen Drucker wirklich entfernen?')) return;
  await fetch('/api/printers/' + id, { method:'DELETE' });
  refresh();
}

function openCam(id){
  document.getElementById('camImg').src = '/camera/' + id + '?_=' + Date.now();
  document.getElementById('camModal').classList.add('show');
}
function closeCam(){
  document.getElementById('camModal').classList.remove('show');
  document.getElementById('camImg').src = '';
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
    sortBtn.textContent = (historySortMode === 'date') ? 'Sortierung: Neueste zuerst' : 'Sortierung: A-Z';
  }
  if(!lastHistoryEntries.length){
    body.innerHTML = '<div class="history-empty">Noch keine Druckauftraege ueber das Dashboard gesendet.</div>';
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
    return `
      <div class="history-item">
        ${thumb}
        <div class="history-body">
          <div class="history-filename">${e.filename}</div>
          <div class="history-date">${e.sent_at}</div>
        </div>
        <div class="history-actions">
          <button class="btn-mini" onclick="reprintHistoryEntry('${printerId}','${e.job_id}')">Erneut drucken</button>
          <button class="btn-mini" onclick="addHistoryEntryToQueue('${printerId}','${e.job_id}')">In Warteschlange</button>
          <button class="btn-mini" onclick="openAssignModal('history','${printerId}','${e.job_id}')">Zuweisen</button>
          <button class="btn-mini btn-delete" onclick="deleteHistoryEntry('${printerId}','${e.job_id}')">Loeschen</button>
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
// - bei Bambu Lab wird dafuer EXPLIZIT der Status FINISH oder IDLE
// verlangt (nicht nur "nicht am Drucken"), siehe DashboardApp.
// is_ready_for_next_print() fuer die serverseitige Gegenpruefung, die in
// jedem Fall zusaetzlich greift. Wird sowohl nach jedem Laden/Aendern der
// Warteschlange als auch bei jedem regulaeren 2,5-Sekunden-Status-Poll
// aufgerufen (siehe refresh()), damit der Knopf automatisch aktiv wird,
// sobald der laufende Druck fertig ist, ohne dass der Nutzer das Modal
// schliessen/neu oeffnen muss.
function updateQueueSendButtonState(){
  const btn = document.getElementById('queueSendNextBtn');
  const hint = document.getElementById('queueSendHint');
  if(!btn || !queueModalPrinterId) return;
  const p = lastPrinterList.find(x => x.id === queueModalPrinterId);
  const state = (p && p.gcode_state) ? String(p.gcode_state).toUpperCase() : '';
  const isBambu = p && p.type === 'bambu';
  const ready = isBambu ? ['FINISH', 'IDLE'].includes(state) : !PRINTER_BUSY_STATES_JS.includes(state);

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
    return `
      <div class="history-item queue-item">
        <div class="queue-order-btns">
          <button class="btn-mini" ${i === 0 ? 'disabled' : ''} title="Nach oben" onclick="moveQueueEntry('${printerId}','${e.job_id}',-1)">&uarr;</button>
          <button class="btn-mini" ${i === entries.length - 1 ? 'disabled' : ''} title="Nach unten" onclick="moveQueueEntry('${printerId}','${e.job_id}',1)">&darr;</button>
        </div>
        ${thumb}
        <div class="history-body">
          <div class="history-filename">${label}${e.filename}</div>
          <div class="history-date">In Warteschlange seit ${e.added_at}</div>
        </div>
        <div class="history-actions">
          <button class="btn-mini" onclick="openAssignModal('queue','${printerId}','${e.job_id}')">Zuweisen</button>
          <button class="btn-mini btn-delete" onclick="deleteQueueEntry('${printerId}','${e.job_id}')">Loeschen</button>
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

function renderAms(ams){
  if(!ams || ams.length === 0){
    return '<div class="empty-ams">Kein AMS erkannt / keine Fach-Daten.</div>';
  }
  return ams.map(t => {
    const remain = (t.remain === undefined || t.remain === null || t.remain < 0) ? '–' : t.remain + '%';
    const width = (t.remain && t.remain > 0) ? t.remain : 0;
    return `<div class="ams-slot">
      <div class="ams-swatch" style="background:${t.color}"></div>
      <div class="ams-meta">${t.type}</div>
      <div class="ams-track"><div class="ams-fill" style="width:${width}%; background:${t.color}"></div></div>
      <div class="ams-remain">${remain}</div>
    </div>`;
  }).join('');
}

function renderExtras(printerId, extras){
  if(!extras || extras.length === 0) return '';
  return `<div class="extras-section">
    <div class="field-label">Sensoren &amp; Schalter</div>
    <div class="extras-row">
      ${extras.map(e => {
        if(e.kind === 'switch'){
          return `<div class="extra-switch">
            <span>${e.label}</span>
            <button class="btn-mini" onclick="extraCommand('${printerId}','${e.id}','on')">Ein</button>
            <button class="btn-mini off" onclick="extraCommand('${printerId}','${e.id}','off')">Aus</button>
          </div>`;
        }
        const val = (e.value === undefined || e.value === null || e.value === '') ? '–' : e.value;
        return `<div class="extra-sensor"><span>${e.label}</span><b>${val}${e.unit ? ' ' + e.unit : ''}</b></div>`;
      }).join('')}
    </div>
  </div>`;
}

// MK6 v1.2.0: letzte Druckerliste aus refresh() - wird ohne erneuten
// Netzwerk-Request fuer den Zuweisen-Dialog (openAssignModal()) genutzt,
// damit dort eine aktuelle Auswahl an Ziel-Druckern zur Verfuegung steht.
let lastPrinterList = [];

async function refresh(){
  const res = await fetch('/api/status');
  const printers = await res.json();
  lastPrinterList = printers;
  // v2.0.1: haelt den "Druckraum leer"-Knopf live aktuell, falls die
  // Warteschlange gerade offen ist (z. B. der Nutzer wartet darauf, dass
  // ein Bambu-Lab-Drucker fertig wird, ohne das Modal zu schliessen).
  if(queueModalPrinterId) updateQueueSendButtonState();
  const list = document.getElementById('printerList');

  if(printers.length === 0){
    list.innerHTML = `<div class="empty-state">
      Noch keine Drucker hinterlegt.
      <div><button class="btn" onclick="openAddModal()">+ Drucker hinzufuegen</button></div>
    </div>`;
    return;
  }

  list.innerHTML = printers.map(p => {
    if(p.type === 'octoprint') return renderOctoPrintCard(p);
    if(p.type === 'formlabs' || p.type === 'formlabs_wash' || p.type === 'formlabs_cure') return renderFormlabsCard(p);
    if(CREALITY_TYPES.includes(p.type)) return renderCrealityCard(p);
    if(p.type === 'ultimaker') return renderUltimakerCard(p);
    return renderBambuCard(p);
  }).join('');
}

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
          <div class="cam-icon" title="Kamera anzeigen" onclick="openCam('${p.id}')">${CAM_ICON}</div>
          <div class="hist-icon" title="Druckauftrags-Verlauf" onclick="openHistoryModal('${p.id}')">${HIST_ICON}</div>
          ${renderQueueIcon(p)}
          <div class="del-icon" title="Entfernen" onclick="deletePrinter('${p.id}')">&times;</div>
        </div>
      </div>
      <div class="card-body">
        <div>
          <div class="field-label">Aktuelle Datei</div>
          <div class="file-name">${p.file_name || '-'} ${remMin ? ' &middot; ' + remMin : ''}</div>

          <div class="field-label">Fortschritt</div>
          <div class="progress-row">
            <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
            <div class="progress-pct">${pct}%</div>
          </div>

          <div class="field-label">Temperaturen</div>
          <div class="temps">
            <div class="temp-chip">Kammer <b>${formatTemp(p.chamber_temp)}&deg;C</b></div>
            <div class="temp-chip">Duese <b>${formatTemp(p.nozzle_temp)}&deg;C</b></div>
            <div class="temp-chip">Bett <b>${formatTemp(p.bed_temp)}&deg;C</b></div>
          </div>
        </div>
        <div>
          <div class="ams-title">AMS / Filament</div>
          ${renderAms(p.ams)}
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
      <div class="dz-hint">Erfordert Developer Mode / LAN-Modus am Drucker</div>
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
          <div class="cam-icon" title="Kamera anzeigen" onclick="openCam('${p.id}')">${CAM_ICON}</div>
          <div class="hist-icon" title="Druckauftrags-Verlauf" onclick="openHistoryModal('${p.id}')">${HIST_ICON}</div>
          <div class="del-icon" title="Entfernen" onclick="deletePrinter('${p.id}')">&times;</div>
        </div>
      </div>
      <div class="card-body">
        <div>
          <div class="field-label">Aktuelle Datei</div>
          <div class="file-name">${p.file_name || '-'} ${remMin ? ' &middot; ' + remMin : ''}</div>

          <div class="field-label">Fortschritt</div>
          <div class="progress-row">
            <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
            <div class="progress-pct">${pct}%</div>
          </div>

          <div class="field-label">Temperaturen</div>
          <div class="temps">
            <div class="temp-chip">Duese <b>${formatTemp(p.nozzle_temp)}&deg;C</b></div>
            <div class="temp-chip">Bett <b>${formatTemp(p.bed_temp)}&deg;C</b></div>
          </div>
          ${p.error ? `<div class="error-hint">${p.error}</div>` : ''}
        </div>
        <div>
          <div class="field-label">Hinweis</div>
          <div class="hint-text" style="margin:0;">OctoPrint liefert keine Kammertemperatur / kein AMS-Aequivalent.</div>
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
          <div class="cam-icon" title="Kamera anzeigen" onclick="openCam('${p.id}')">${CAM_ICON}</div>
          <div class="hist-icon" title="Druckauftrags-Verlauf" onclick="openHistoryModal('${p.id}')">${HIST_ICON}</div>
          <div class="del-icon" title="Entfernen" onclick="deletePrinter('${p.id}')">&times;</div>
        </div>
      </div>
      <div class="card-body">
        <div>
          <div class="field-label">Aktuelle Datei</div>
          <div class="file-name">${p.file_name || '-'}</div>

          <div class="field-label">Fortschritt</div>
          <div class="progress-row">
            <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
            <div class="progress-pct">${pct}%</div>
          </div>

          <div class="field-label">Temperaturen</div>
          <div class="temps">
            ${hasChamber ? `<div class="temp-chip">Kammer <b>${formatTemp(p.chamber_temp)}&deg;C</b></div>` : ''}
            <div class="temp-chip">Duese <b>${formatTemp(p.nozzle_temp)}&deg;C</b></div>
            <div class="temp-chip">Bett <b>${formatTemp(p.bed_temp)}&deg;C</b></div>
          </div>
          ${p.error ? `<div class="error-hint">${p.error}</div>` : ''}
        </div>
        <div>
          <div class="field-label">Hinweis</div>
          <div class="hint-text" style="margin:0;">Ueber Moonraker angebunden. Kammertemperatur nur sichtbar, falls im Klipper-Setup ein entsprechender Sensor konfiguriert ist.</div>
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
          <div class="cam-icon" title="Kamera anzeigen" onclick="openCam('${p.id}')">${CAM_ICON}</div>
          <div class="hist-icon" title="Druckauftrags-Verlauf" onclick="openHistoryModal('${p.id}')">${HIST_ICON}</div>
          ${renderQueueIcon(p)}
          <div class="del-icon" title="Entfernen" onclick="deletePrinter('${p.id}')">&times;</div>
        </div>
      </div>
      <div class="card-body">
        <div>
          <div class="field-label">Aktuelle Datei</div>
          <div class="file-name">${p.file_name || '-'} ${remMin ? ' &middot; ' + remMin : ''}</div>

          <div class="field-label">Fortschritt</div>
          <div class="progress-row">
            <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
            <div class="progress-pct">${pct}%</div>
          </div>

          <div class="field-label">Temperaturen</div>
          <div class="temps">
            <div class="temp-chip">Duese <b>${formatTemp(p.nozzle_temp)}&deg;C</b></div>
            <div class="temp-chip">Bett <b>${formatTemp(p.bed_temp)}&deg;C</b></div>
          </div>
          ${p.error ? `<div class="error-hint">${p.error}</div>` : ''}
        </div>
        <div>
          <div class="field-label">Druckauftrag senden</div>
          ${renderUltimakerDropZone(p.id, !!p.ultimaker_paired)}
          <div class="hint-text" style="margin-top:8px;">Ultimaker-Desktopdrucker haben keinen Kammertemperatursensor.</div>
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
      <div class="dz-hint">Export aus Cura, z. B. ueber "Datei speichern"</div>
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
          <div class="hist-icon" title="Druckauftrags-Verlauf" onclick="openHistoryModal('${p.id}')">${HIST_ICON}</div>
          <div class="del-icon" title="Entfernen" onclick="deletePrinter('${p.id}')">&times;</div>
        </div>
      </div>
      <div class="card-body single-col">
        <div>
          <div class="field-label">${labels.file}</div>
          <div class="file-name">${p.file_name || '-'}</div>

          <div class="field-label">Fortschritt</div>
          <div class="progress-row">
            <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
            <div class="progress-pct">${pct}%</div>
          </div>

          ${labels.showMaterial ? `
          <div class="field-label">Geladenes Harz / Material</div>
          <div class="file-name">${p.material || '-'}</div>
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

// MK6: Kartenlayout 1/2/3-spaltig, Auswahl wird lokal im Browser gemerkt
// (localStorage) - reine Anzeige-Praeferenz, kein Server-/config.json-Zustand,
// da jeder Nutzer/Browser sein eigenes Layout haben kann.
function getLayoutCols(){
  try{
    const v = parseInt(localStorage.getItem('dashboardLayoutCols'), 10);
    return [1,2,3].includes(v) ? v : 1;
  } catch(e){ return 1; }
}
function setLayoutCols(cols){
  const list = document.getElementById('printerList');
  list.classList.remove('cols-2','cols-3');
  if(cols === 2) list.classList.add('cols-2');
  if(cols === 3) list.classList.add('cols-3');
  document.querySelectorAll('.layout-btn').forEach(b=>{
    b.classList.toggle('active', parseInt(b.dataset.cols,10) === cols);
  });
  try{ localStorage.setItem('dashboardLayoutCols', String(cols)); } catch(e){ /* z.B. privater Modus - Auswahl bleibt dann nur fuer diese Sitzung aktiv */ }
}

setLayoutCols(getLayoutCols());
loadVersion();
refresh();
setInterval(refresh, 2500);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    host = dash.cfg["server"].get("host", "0.0.0.0")
    port = int(dash.cfg["server"].get("port", 8000))
    print(f"Dashboard laeuft auf http://{host}:{port}  (im lokalen Netz erreichbar ueber die IP dieses PCs)")
    app.run(host=host, port=port, debug=False, threaded=True)
