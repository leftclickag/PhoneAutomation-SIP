[English](README.md) | Deutsch

# PhoneAutomation-SIP

Home-Assistant-App der Leftclick AG. Ruft bei einem Alarm (z.B. aus [Alarmo](https://github.com/nielsfaber/alarmo)) über einen eigenen SIP-Anbieter (z.B. PhoneStar, Swisscom) an, spricht einen Text per Text-to-Speech und wiederholt die Anrufe, bis jemand per Tastendruck quittiert. Eine Alternative zu Twilio ohne Kosten pro Anruf.

> **Status: der Anruf funktioniert, die Quittierung ist noch nicht bestätigt.** Die App lässt sich in Home Assistant installieren und baut einen echten SIP-Anruf auf. Dass die Quittiertaste die Wiederholungen beendet, ist noch nicht bestätigt. Nicht als alleinigen Alarmweg verwenden. Offene Punkte stehen in der [Checkliste](#checkliste).

Die App liegt in [`sip_alarm_caller/`](sip_alarm_caller/). Konfiguration und Home-Assistant-Einbindung stehen in [`sip_alarm_caller/DOCS.md`](sip_alarm_caller/DOCS.md) (Englisch) und [`sip_alarm_caller/DOCS.de.md`](sip_alarm_caller/DOCS.de.md).

## Installation

> **Namenshinweis:** Ab Home Assistant 2026.2 heißen „Add-ons" in der Oberfläche **„Apps"** (der Store heißt „App Store", lokale Apps erscheinen unter „Local apps"). Ab Supervisor 2026.6 heißt der lokale Ordner auf dem Gerät **`local_apps`** statt `addons`. Beide Namen sind unten berücksichtigt. Je nach Home-Assistant-Version den jeweils aktuellen Pfad verwenden. Die folgenden Schritte gelten für Home Assistant OS bzw. Supervised. Home Assistant Container und Core unterstützen keine Apps.

### Variante A: Öffentliches Repo (empfohlen)

1. Home Assistant öffnen → **Einstellungen → Apps** → dort **„Install app"** anklicken → der **App Store** öffnet sich.
2. Oben rechts aufs **⋯-Menü** klicken → **Repositories**.
3. URL `https://github.com/leftclickag/PhoneAutomation-SIP` einfügen → **Hinzufügen**.
4. Zurück im Store: Seite ggf. mit **Strg+F5** neu laden, dann **SIP Alarm Caller** öffnen → **Installieren**.

### Variante B: Lokal per SSH

Voraussetzung: Die App **„Terminal & SSH"** ist installiert (Einstellungen → Apps). Dann:

1. Die Dateien aus [`sip_alarm_caller/`](sip_alarm_caller/) (`config.yaml`, `Dockerfile`, `run.sh`, `app.py`, `DOCS.md`) in einen Ordner `sip_alarm_caller` im lokalen Ordner des Geräts kopieren. Die Struktur muss so aussehen:

   ```
   /local_apps/sip_alarm_caller/config.yaml
   /local_apps/sip_alarm_caller/Dockerfile
   /local_apps/sip_alarm_caller/run.sh
   /local_apps/sip_alarm_caller/app.py
   /local_apps/sip_alarm_caller/DOCS.md
   ```

   Im Terminal der SSH-App z.B.:

   ```bash
   mkdir -p /local_apps/sip_alarm_caller
   # Dateien übertragen, z.B. per scp vom eigenen PC:
   # scp C:\GitHub\PhoneAutomation-SIP\sip_alarm_caller\* root@homeassistant.local:/local_apps/sip_alarm_caller/
   ls /local_apps/sip_alarm_caller
   ```

   Der Ordner muss **direkt** in `local_apps` liegen. Ein verschachtelter Pfad wie `local_apps/PhoneAutomation-SIP/sip_alarm_caller/` wird nicht gefunden. Bei älteren Installationen (vor Supervisor 2026.6) heißt der Ordner `/addons` statt `/local_apps`. Dort hinein kopieren, falls `local_apps` nicht existiert.

2. Home Assistant öffnen → **Einstellungen → Apps → „Install app"** (App Store).
3. Oben rechts im **⋯-Menü** → **Nach Updates suchen**.
4. **Seite mit Strg+F5 hart neu laden.** Der Store cachet sonst oft noch den alten Stand.
5. Ein neuer Abschnitt **„Local apps"** erscheint (ganz oben) mit **SIP Alarm Caller** → anklicken → **Installieren**. Der erste Start baut das Docker-Image aus dem Dockerfile.
6. Klappt Schritt 5 nicht: Gerät neu starten (Einstellungen → System) und erneut prüfen.

### Variante B alternativ: Lokal per Samba-Freigabe

Wenn die App **„Samba share"** läuft, im Windows-Explorer `\\homeassistant.local\local_apps` öffnen (ältere Samba-App-Versionen: `\\homeassistant.local\addons`. Beide Namen zeigen auf denselben Ordner), dort den Ordner `sip_alarm_caller` mit den Dateien anlegen wie oben. Der Datei-Editor und Studio Code Server sehen nur `/config`, **nicht** `local_apps`. Zum Kopieren Samba oder SSH verwenden.

### Nach der Installation (gilt für beide Varianten)

1. App öffnen → Tab **Konfiguration**: SIP-Zugangsdaten eintragen (`sip_server`, `sip_user`, `sip_password`), Zielnummern im Format `+41791234567`, ggf. `tts_engine` prüfen (Standard `tts.piper`, siehe DOCS.md) → **Speichern**.
2. **Start** drücken (und „Beim Booten starten" aktivieren).
3. Tab **Log** öffnen und prüfen, ob die SIP-Registrierung erfolgreich ist.
4. Fehlerhafte App-Konfiguration wird im Store **still übersprungen**. Im Zweifel unter **Einstellungen → System → Logs → Dropdown oben rechts → „Supervisor"** nach Warnungen zu `sip_alarm_caller` suchen.

## Voraussetzungen

- **Home Assistant OS** (oder Supervised). Gedacht für den Home Assistant Green (`aarch64`), `amd64` ist zusätzlich eingetragen. Home Assistant Container und Core unterstützen keine Apps.
- **SIP-Zugang** mit ausgehenden Anrufen: Server, User und Passwort. Der Anbieter muss Anrufe in die Zielnetze erlauben, G.711 (PCMA/PCMU) unterstützen und die gewünschte Absendernummer zulassen.
- **Text-to-Speech** in Home Assistant, empfohlen die **Piper**-App (lokal, deutschsprachige Stimmen). Jede andere TTS-Entity funktioniert ebenfalls, z.B. Home Assistant Cloud.
- **Netzwerk:** Die App läuft im Host-Netzwerk. Ausgehend müssen SIP (meist UDP/TCP 5060 bzw. TLS 5061) und die RTP-Audioports des Anbieters erreichbar sein.

## Was noch angenommen ist

Diese Punkte sind beim Schreiben angenommen worden und müssen auf einem echten System geprüft werden. Abhaken in der [Checkliste](#checkliste).

1. **pjsua-Steuerung.** Die SIP-Engine ist **pjsua** (PJSIP), gestartet mit Telnet-CLI (`--use-cli`, `--cli-telnet-port`) und Log-Level 5. Anruf- und Registrierungsereignisse werden aus dem Log geparst (`Call N state changed to`, `registration success/failed`). DTMF über SIP steht in der Zeile `Incoming DTMF on call N: X, using … method`. Weil die Ausgabe von pjsua in eine Pipe geht, startet die App es mit `--stdout-no-buf`. Ohne dieses Flag bleiben Antwort- und Tasten-Zeilen im Puffer und die App sieht sie nicht.
2. **Pakete.** `pjsua`, `py3-aiohttp` und `ffmpeg` sind in Alpine 3.24 enthalten, der Basis des Home-Assistant-Images. **baresip ist dort nicht verfügbar** (nur in Alpine edge/testing). Deshalb verwendet die App pjsua.
3. **TTS über die HA-API.** `POST http://supervisor/core/api/tts_get_url` mit `homeassistant_api: true` liefert ein Feld `path`, das sich vom gleichen Proxy herunterladen lässt.
4. **Piper-Standardwerte.** Die Entity `tts.piper` und die Sprache `de_DE` sind Platzhalter. Der tatsächliche Name steht unter Einstellungen → Geräte & Dienste → Wyoming-Protokoll.
5. **Quittierung.** Die eingestellte Taste (Standard `1`) soll die Wiederholungen beenden. Erkannt wird sie als SIP-DTMF (RFC 2833/4733 oder SIP INFO) und als Ton im zurückkommenden Audio, weil viele Mobilnetze die Taste nur hörbar übertragen.
6. **PhoneStar / Swisscom.** Anbieterspezifische Einstellungen (Server, Registrierung, Proxy, Transport, Rufnummernformat) sind nicht hinterlegt. Die App erwartet eine normale SIP-Registrierung und Nummern im internationalen Format (`+41...`).
7. **Wer einen Anruf auslösen kann.** Port 8099 ist am Host erreichbar. Ohne `api_token` kann jedes Gerät im LAN Anrufe starten. Vor dem echten Einsatz einen Token setzen.
8. **Ein Anruf gleichzeitig.** Ein Alarmlauf führt immer nur einen Anruf. Die Nummern werden nacheinander angerufen, nicht parallel.

## Empfohlener Test

1. Piper installieren und eine TTS-Entity prüfen.
2. App installieren, SIP-Daten und die eigene Nummer eintragen, starten und das Log lesen.
3. `rest_command.sip_alarm_call` aus den Entwicklerwerkzeugen auslösen. Hört man den Text? Beendet Taste 1 die Anrufe?
4. Erst danach Alarmo anbinden und Wiederholungen sowie `/stop` testen.
5. Zusätzlich einen unabhängigen Weg behalten, z.B. die Push-Benachrichtigung der Home-Assistant-Companion-App.

## Checkliste

Checkliste für diese App auf einem echten Home-Assistant-System. Ein Punkt gilt als erledigt, wenn `- [ ]` zu `- [x]` geändert wurde, nachdem das Verhalten tatsächlich funktioniert hat. Neue Punkte auf dieselbe Art ergänzen.

Abgehakte Punkte wurden beim Installieren und Anrufen bereits beobachtet. Offene Punkte, einschliesslich der Quittiertaste, sind noch nicht bestätigt.

### Erledigt

- [x] Das Image baut auf Home Assistant OS (`aarch64`) mit `pjsua` aus Alpine 3.24
- [x] Der Prozess startet und lauscht auf Port 8099
- [x] `rest_command.sip_alarm_call` auf `http://127.0.0.1:8099/alarm` baut einen ausgehenden Anruf auf
- [x] Das Telefon klingelt und die Ansage wird abgespielt
- [x] Ohne Quittierung folgt nach der Pause ein weiterer Anruf

### Noch zu bestätigen

- [ ] Nach einem Rebuild von Version 0.2.4 enthält das Log `SIP Alarm Caller 0.2.4 bereit auf Port 8099`
- [ ] Nach dem Abheben enthält das Log `Anruf verbunden, warte auf Taste 1`
- [ ] Taste 1 beendet die Wiederholungen
- [ ] Das Log enthält `Quittiert mit Taste 1` oder `Tastenton erkannt: 1`
- [ ] `rest_command.sip_alarm_stop` legt auf und beendet den Alarmlauf
- [ ] Ein Alarmo-Auslöser startet die Anrufe, das Deaktivieren des Alarms stoppt sie
- [ ] Mit gesetztem `api_token` wird ein Aufruf ohne Bearer-Token abgelehnt
- [ ] Die Transporte TCP und TLS registrieren sich und bauen einen Anruf auf
- [ ] Mehrere Nummern werden in einer Runde nacheinander angerufen

## Lizenz

[MIT](LICENSE). Die Nutzung erfolgt auf eigenes Risiko. Es gibt keine Gewährleistung, auch nicht für die Zuverlässigkeit als Alarmierungssystem.

&copy; Leftclick AG
