# Installation auf Linux/OpenWrt-Geraeten (z. B. GL.iNet-Router)

Diese Anleitung beschreibt die Installation/Aktualisierung des Dashboards
als reine Python-Quelldateien auf einem Linux-Geraet ohne PyInstaller-exe
(z. B. einem GL.iNet-Router mit OpenWrt). Sie entstand aus einer echten
Installation auf einem GL.iNet GL-MT2500 (Brume 2), OpenWrt 21.02, und
deckt die dabei tatsaechlich aufgetretenen Stolpersteine ab. Fuer Windows/
macOS-exe-Builds siehe stattdessen README Abschnitt 0.

## 1. Voraussetzungen

- **Python 3.9 oder neuer** auf dem Zielgeraet. Pruefen mit:
  ```
  python3 --version
  ```
  Aeltere Python-Versionen (vor 3.10) sind seit v2.2.27 wieder
  unterstuetzt (siehe UEBERGABE.md v2.2.27) - mit v2.2.26 und frueheren
  MK6-Versionen kann es bei sehr altem Python zu einem `TypeError` beim
  Start kommen.
- `flask` und `paho-mqtt` per `pip3 install flask paho-mqtt` (oder ueber
  den Paketmanager des Geraets, falls vorhanden). Keine weiteren
  Python-Abhaengigkeiten noetig.
- SSH-Zugriff auf das Geraet sowie `scp` auf dem eigenen Rechner
  (unter Windows seit Windows 10 standardmaessig vorhanden, unter
  macOS/Linux ebenfalls).
- Fuer die Kamera der X1/P1/P2/H2/X2-Serie (optional, siehe Abschnitt 4):
  ein zweiter Rechner MIT Internetzugang, falls das Zielgeraet selbst
  offline betrieben wird.

## 2. Dateien uebertragen

Auf dem Zielgeraet einen Ordner anlegen und die Python-Dateien dorthin
kopieren (Beispielpfad `/root/drucker-dashboard/`):

```
scp app.py ftps_upload_helper.py config.example.json root@<GERAET-IP>:/root/drucker-dashboard/
```

`config.example.json` auf dem Geraet nach `config.json` umbenennen und
mit den eigenen Druckerdaten fuellen (siehe README Abschnitt 2) - oder,
bei einer Aktualisierung einer bestehenden Installation, die vorhandene
`config.json` unveraendert lassen und **nur** `app.py` (und ggf.
`ftps_upload_helper.py`) ueberschreiben.

## 3. Manuell testen

```
cd /root/drucker-dashboard
python3 app.py
```

Erreichbar danach unter `http://<GERAET-IP>:8000`. Erscheint ein
Traceback statt der ueblichen Start-Meldungen, zuerst Abschnitt 6
(Fehlerbehebung) pruefen. Mit Strg+C beenden, sobald der manuelle Test
erfolgreich war.

## 4. Kamera der X1/P1/P2/H2/X2-Serie: FFmpeg hinzufuegen (optional)

Die A1-Kamera sowie alle anderen Funktionen brauchen KEIN FFmpeg. Nur
die RTSPS-Kamera der Serien X1/P1/P2/H2/X2 braucht eine `ffmpeg`-
Binaerdatei direkt neben `app.py` im selben Ordner (ohne Dateiendung).

**Wichtig:** Die meisten vorgefertigten FFmpeg-"static"-Builds im Netz
(z. B. von johnvansickle.com) sind entweder zu alt (haben noch kein
`-tls_verify` fuer RTSPS-Verbindungen, siehe UEBERGABE.md v2.2.24/v2.2.26
fuer den Hintergrund) oder dynamisch gegen glibc gelinkt (z. B. die
Builds von BtbN/FFmpeg-Builds) - **OpenWrt nutzt aber musl-libc**, und
ein glibc-gelinktes FFmpeg schlaegt dort beim Start mit einer
irrefuehrenden Meldung wie `./ffmpeg: not found` fehl, obwohl die Datei
vorhanden ist (der im Programm eingetragene dynamische Linker-Pfad, z. B.
`/lib/ld-linux-aarch64.so.1`, existiert auf dem System schlicht nicht).

Die empfohlene Quelle fuer ein aktuelles UND echtes (musl-kompatibles)
statisches FFmpeg: [mwader/static-ffmpeg](https://github.com/wader/static-ffmpeg)
- laut eigener Dokumentation "hardened static PIE binaries with no
external dependencies", ausdruecklich fuer u. a. OpenWrt geeignet.
Verteilt wird das nur als Docker-Image, daher folgende Schritte auf
einem **beliebigen Rechner mit Internetzugang und Docker Desktop**
(Windows, macOS oder Linux - die Befehle sind identisch, nur PowerShell
statt Terminal unter Windows):

1. Docker Desktop installieren, falls noch nicht vorhanden:
   https://www.docker.com/products/docker-desktop/
2. In einem neuen, leeren Ordner eine Datei `Dockerfile` (ohne
   Dateiendung) mit folgendem Inhalt anlegen:
   ```
   FROM alpine
   COPY --from=mwader/static-ffmpeg:9.0.2 /ffmpeg /ffprobe /
   ENTRYPOINT ["cp", "/ffmpeg", "/ffprobe", "/out"]
   ```
   (Versionsnummer `9.0.2` bei Bedarf gegen eine neuere ersetzen - auf
   https://hub.docker.com/r/mwader/static-ffmpeg/tags nachsehen.)
3. Im selben Ordner (PowerShell bzw. Terminal) - **das Ziel ist IMMER
   `linux/arm64`, unabhaengig von der eigenen Rechner-Architektur**
   (GL.iNet-Router mit MediaTek-Chip nutzen ueblicherweise AArch64 -
   auf dem Zielgeraet selbst mit `uname -m` bestaetigen, "aarch64"
   bedeutet `linux/arm64` ist richtig):
   ```
   docker build --platform linux/arm64 -t ffmpeg-extract .
   mkdir out
   docker run --rm --platform linux/arm64 -v "${PWD}/out:/out" ffmpeg-extract
   ```
   (Unter PowerShell funktioniert `${PWD}` genauso wie unter macOS/
   Linux-Terminal mit `$PWD`.)
4. Die entstandene Datei `./out/ffmpeg` auf das Zielgeraet uebertragen:
   ```
   scp ./out/ffmpeg root@<GERAET-IP>:/root/drucker-dashboard/ffmpeg
   ```
5. Auf dem Zielgeraet ausfuehrbar machen und pruefen:
   ```
   chmod +x /root/drucker-dashboard/ffmpeg
   /root/drucker-dashboard/ffmpeg -version
   ```
   Erscheint die Versionsausgabe (z. B. `ffmpeg version 9.0.2-static`)
   ohne Fehler, ist alles bereit.

## 5. Autostart einrichten (procd)

Damit das Dashboard einen Geraete-Neustart uebersteht, ein eigenes
procd-Init-Skript anlegen, z. B. `/etc/init.d/drucker-dashboard`:

```sh
#!/bin/sh /etc/rc.common

START=95
USE_PROCD=1

start_service() {
    procd_open_instance
    procd_set_param command /usr/bin/python3 /root/drucker-dashboard/app.py
    procd_set_param respawn
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
}
```

Danach ausfuehrbar machen und aktivieren (erst `enable` sorgt dafuer,
dass es auch nach einem kompletten Geraete-Neustart automatisch
startet - ein einzelner `restart`-Aufruf reicht dafuer NICHT):

```
chmod +x /etc/init.d/drucker-dashboard
/etc/init.d/drucker-dashboard enable
/etc/init.d/drucker-dashboard start
```

Pruefen, ob der Autostart tatsaechlich aktiviert ist:
```
/etc/init.d/drucker-dashboard enabled; echo $?
```
(`0` = aktiviert.)

Nach Aenderungen an `app.py` reicht anschliessend:
```
/etc/init.d/drucker-dashboard restart
```
- ein kompletter Geraete-Neustart ist fuer gewoehnliche Updates nicht
noetig.

## 6. Fehlerbehebung

- **Traceback beim Start, z. B. `TypeError: unsupported operand
  type(s) for |`:** zu altes Python - siehe Abschnitt 1, mit v2.2.27
  behoben, ggf. `app.py` aktualisieren.
- **`./ffmpeg: not found`, obwohl die Datei vorhanden ist
  (`ls -la` zeigt sie):** falsches FFmpeg-Build (dynamisch gegen glibc
  gelinkt statt echt statisch) - siehe Abschnitt 4, mwader/static-ffmpeg
  verwenden statt anderer Quellen.
- **Kamera-Fenster bleibt leer/ohne Fehler, Konsole zeigt
  `[MK6-FFMPEG]`-Fehlerzeilen wie "Option tls_verify not found":**
  FFmpeg-Version zu alt (vor Mitte 2025) - neueres Build besorgen
  (Abschnitt 4).
- **Dashboard nach Geraete-Neustart nicht erreichbar, SSH zeigt aber
  keinen Fehler beim manuellen Start:** Autostart-Skript fehlt oder ist
  nicht aktiviert - siehe Abschnitt 5.
- Allgemein: Server-Konsole bzw. `logread -f | grep -i mk6` nach Zeilen
  mit dem Praefix `[MK6-FFMPEG]` oder `[MK6]` durchsuchen - das
  Dashboard protokolliert die meisten Kamera-/Druckstart-Probleme dort
  mit konkreten Details statt nur "funktioniert nicht".
