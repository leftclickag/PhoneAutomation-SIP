# PhoneAutomation-SIP

Home-Assistant-Add-on der Leftclick AG: Ruft bei einem Alarm (z.B. aus [Alarmo](https://github.com/nielsfaber/alarmo)) über einen eigenen SIP-Anbieter (z.B. PhoneStar, Swisscom) an, spricht einen Text per Text-to-Speech und wiederholt die Anrufe, bis jemand per Tastendruck quittiert. Eine Alternative zu Twilio ohne Kosten pro Nachricht.

> **Status: experimentell und ungetestet.** Der Code ist geschrieben, aber noch nicht gegen einen echten SIP-Trunk, nicht in einem Docker-Build und nicht in Home Assistant gelaufen. Nicht als alleiniges Alarmierungssystem verwenden, bis es erfolgreich getestet wurde.

Das Add-on liegt in [`sip_alarm_caller/`](sip_alarm_caller/). Konfiguration und Home-Assistant-Einbindung stehen in [`sip_alarm_caller/DOCS.md`](sip_alarm_caller/DOCS.md).

## Installation

> **Namenshinweis:** Ab Home Assistant 2026.2 heißen „Add-ons" in der Oberfläche **„Apps"** (der Store heißt „App Store", lokale Apps erscheinen unter „Local apps"). Ab Supervisor 2026.6 heißt der lokale Ordner auf dem Gerät **`local_apps`** statt `addons`. Beide Namen sind unten berücksichtigt — je nach Home-Assistant-Version den jeweils aktuellen Pfad verwenden. Die folgenden Schritte gelten für Home Assistant OS bzw. Supervised; Home Assistant Container und Core unterstützen keine Apps/Add-ons.

### Variante A: Öffentliches Repo (empfohlen, wenn das Repo auf GitHub öffentlich ist)

1. Home Assistant öffnen → **Einstellungen → Apps** → dort **„Install app"** anklicken → der **App Store** öffnet sich.
2. Oben rechts aufs **⋯-Menü** klicken → **Repositories**.
3. URL `https://github.com/leftclickag/PhoneAutomation-SIP` einfügen → **Hinzufügen**.
4. Zurück im Store: Seite ggf. mit **Strg+F5** neu laden, dann **SIP Alarm Caller** öffnen → **Installieren**.

### Variante B: Lokal per SSH (funktioniert auch bei privatem Repo)

Voraussetzung: Die App **„Terminal & SSH"** ist installiert (Einstellungen → Apps). Dann:

1. Die 5 Dateien aus [`sip_alarm_caller/`](sip_alarm_caller/) (`config.yaml`, `Dockerfile`, `run.sh`, `app.py`, `DOCS.md`) in einen Ordner `sip_alarm_caller` im lokalen Ordner des Geräts kopieren. Die Struktur muss so aussehen:

   ```
   /local_apps/sip_alarm_caller/config.yaml
   /local_apps/sip_alarm_caller/Dockerfile
   /local_apps/sip_alarm_caller/run.sh
   /local_apps/sip_alarm_caller/app.py
   /local_apps/sip_alarm_caller/DOCS.md
   ```

   Im Terminal der SSH-App (mit Schlüssel bzw. Passwort angemeldet) z.B.:

   ```bash
   mkdir -p /local_apps/sip_alarm_caller
   # Dateien übertragen, z.B. per scp vom eigenen PC:
   # scp C:\GitHub\PhoneAutomation-SIP\sip_alarm_caller\* root@homeassistant.local:/local_apps/sip_alarm_caller/
   ls /local_apps/sip_alarm_caller
   ```

   **Wichtig:** Der Ordner muss **direkt** in `local_apps` liegen. Ein verschachtelter Pfad wie `local_apps/PhoneAutomation-SIP/sip_alarm_caller/` wird nicht gefunden. Bei älteren Installationen (vor Supervisor 2026.6) heißt der Ordner `/addons` statt `/local_apps` — dort hinein kopieren, falls `local_apps` nicht existiert.

2. Home Assistant öffnen → **Einstellungen → Apps → „Install app"** (App Store).
3. Oben rechts im **⋯-Menü** → **Nach Updates suchen**.
4. **Seite mit Strg+F5 hart neu laden** — der Store cachet sonst oft noch den alten Stand.
5. Ein neuer Abschnitt **„Local apps"** erscheint (ganz oben) mit **SIP Alarm Caller** → anklicken → **Installieren**. Der erste Start baut das Docker-Image aus dem Dockerfile, das dauert einen Moment.
6. Klappt Schritt 5 nicht: Gerät neu starten (Einstellungen → System) und erneut prüfen.

### Variante B alternativ: Lokal per Samba-Freigabe

Wenn die App **„Samba share"** läuft, im Windows-Explorer `\\homeassistant.local\local_apps` öffnen (ältere Samba-App-Versionen: `\\homeassistant.local\addons` — beide Namen zeigen auf denselben Ordner), dort den Ordner `sip_alarm_caller` mit den 5 Dateien anlegen wie oben. Achtung: Der Datei-Editor und Studio Code Server sehen nur `/config`, **nicht** `local_apps` — zum Kopieren Samba oder SSH verwenden.

### Nach der Installation (gilt für beide Varianten)

1. App öffnen → Tab **Konfiguration**: SIP-Zugangsdaten eintragen (`sip_server`, `sip_user`, `sip_password`), Zielnummern im Format `+41791234567`, ggf. `tts_engine` prüfen (Standard `tts.piper`, siehe DOCS.md) → **Speichern**.
2. **Start** drücken (und „Beim Booten starten" aktivieren).
3. Tab **Log** öffnen: Ist die SIP-Registrierung erfolgreich? (Siehe „Empfohlener Testablauf" unten.)
4. Fehlerhafte App-Konfiguration wird im Store **still übersprungen** — im Zweifel unter **Einstellungen → System → Logs → Dropdown oben rechts → „Supervisor"** nach Warnungen zu `sip_alarm_caller` suchen.

## Voraussetzungen

- **Home Assistant OS** (oder Supervised) mit Add-on-Unterstützung. Gedacht für den Home Assistant Green (`aarch64`), `amd64` ist zusätzlich eingetragen. Home Assistant Container und Core unterstützen keine Add-ons.
- **SIP-Zugang** mit Outbound-Calls: Server/Domain, User und Passwort. Der Anbieter muss Anrufe in die Zielnetze erlauben, G.711 (PCMA/PCMU) unterstützen und je nach Bedarf eine eigene Absendernummer (CLIP) zulassen.
- **Text-to-Speech** in Home Assistant, empfohlen das **Piper-Add-on** (lokal, kostenlos, deutsche Stimmen). Alternativ funktioniert jede TTS-Entity, z.B. Home Assistant Cloud.
- **Netzwerk:** Das Add-on läuft im Host-Netzwerk. Ausgehend müssen SIP (meist UDP/TCP 5060 bzw. TLS 5061) und die RTP-Audioports des Anbieters erreichbar sein.

## Annahmen (nicht verifiziert)

Folgendes wurde beim Schreiben angenommen und muss beim ersten Test geprüft werden:

1. **pjsua-Steuerung:** Die SIP-Engine ist **pjsua** (PJSIP), gestartet mit Telnet-CLI (`--use-cli`, `--cli-telnet-port`) und Log-Level 5. Anruf-, DTMF- und Registrierungsereignisse werden aus dem Log geparst („Call N state changed to", „Received DTMF digit", „registration success/failed"). Diese Log-Zeilen wurden im PJSIP-Quellcode (2.17) verifiziert, das Verhalten in der echten Telefonie-Umgebung ist ungetestet.
2. **Pakete:** `pjsua`, `py3-aiohttp` und `ffmpeg` sind in Alpine 3.24 (Basis des HA-Base-Images) enthalten. **baresip ist dort nicht verfügbar** (nur in Alpine edge/testing) — deshalb wurde auf pjsua umgestellt. Der Docker-Build auf dem Gerät muss den ersten echten Test ersetzen.
3. **TTS über die HA-API:** `POST http://supervisor/core/api/tts_get_url` mit `homeassistant_api: true` liefert ein Feld `path`, das sich vom gleichen Proxy herunterladen lässt.
4. **Piper-Standardwerte:** Die Entity `tts.piper` und die Sprache `de_DE` sind Platzhalter. Der tatsächliche Name steht in Home Assistant unter Einstellungen → Geräte & Dienste → Wyoming-Protokoll.
5. **Quittierung:** Eine Quittierung gilt nur, wenn die eingestellte Taste (Standard `1`) als DTMF-Signal ankommt. Das setzt voraus, dass der Anbieter DTMF als RFC 2833/4733 oder In-Band durchreicht.
6. **PhoneStar / Swisscom:** Die anbieterspezifischen Einstellungen (SIP-Server, Registrierung, Proxy, Transport, Rufnummernformat) sind nicht bekannt. Der Code nimmt Standard-SIP mit Registrierung und Nummern im internationalen Format (`+41...`) an.
7. **Erreichbarkeit der Schnittstelle:** Port 8099 wird am Host freigegeben und ist im lokalen Netz erreichbar. Ohne `api_token` kann jedes Gerät im Netz Anrufe auslösen. Für den produktiven Einsatz einen Token setzen.
8. **Mehrere Anrufe:** Es läuft immer nur ein Alarmablauf mit einem Anruf gleichzeitig. Die Nummern werden nacheinander angerufen, nicht parallel.

## Empfohlener Testablauf

1. Piper installieren und eine TTS-Entity prüfen.
2. Add-on installieren, SIP-Daten und eine eigene Nummer eintragen, starten und das Add-on-Log lesen (Registrierung erfolgreich?).
3. `rest_command.sip_alarm_call` aus den Entwicklerwerkzeugen auslösen. Hört man den Text? Funktioniert die Taste 1?
4. Erst danach Alarmo anbinden, Wiederholungen und `/stop` testen.
5. Zusätzlich einen unabhängigen Weg behalten, z.B. die Push-Benachrichtigung der HA-Companion-App.

## Lizenz

[MIT](LICENSE). Die Nutzung erfolgt auf eigenes Risiko, es gibt keine Gewährleistung, auch nicht für die Zuverlässigkeit als Alarmierungssystem.

&copy; Leftclick AG
