# PhoneAutomation-SIP

Home-Assistant-Add-on der Leftclick AG: Ruft bei einem Alarm (z.B. aus [Alarmo](https://github.com/nielsfaber/alarmo)) über einen eigenen SIP-Anbieter (z.B. PhoneStar, Swisscom) an, spricht einen Text per Text-to-Speech und wiederholt die Anrufe, bis jemand per Tastendruck quittiert. Eine Alternative zu Twilio ohne Kosten pro Nachricht.

> **Status: experimentell und ungetestet.** Der Code ist geschrieben, aber noch nicht gegen einen echten SIP-Trunk, nicht in einem Docker-Build und nicht in Home Assistant gelaufen. Nicht als alleiniges Alarmierungssystem verwenden, bis es erfolgreich getestet wurde.

Das Add-on liegt in [`sip_alarm_caller/`](sip_alarm_caller/). Konfiguration und Home-Assistant-Einbindung stehen in [`sip_alarm_caller/DOCS.md`](sip_alarm_caller/DOCS.md).

## Installation

- **Öffentliches Repo:** In Home Assistant unter Einstellungen → Add-ons → Add-on-Store → Repositories die URL `https://github.com/leftclickag/PhoneAutomation-SIP` hinzufügen.
- **Lokal (auch bei privatem Repo):** Den Ordner `sip_alarm_caller/` nach `/addons/` auf dem Home-Assistant-Gerät kopieren (z.B. über das Samba- oder SSH-Add-on). Er erscheint dann unter „Lokale Add-ons".

## Voraussetzungen

- **Home Assistant OS** (oder Supervised) mit Add-on-Unterstützung. Gedacht für den Home Assistant Green (`aarch64`), `amd64` ist zusätzlich eingetragen. Home Assistant Container und Core unterstützen keine Add-ons.
- **SIP-Zugang** mit Outbound-Calls: Server/Domain, User und Passwort. Der Anbieter muss Anrufe in die Zielnetze erlauben, G.711 (PCMA/PCMU) unterstützen und je nach Bedarf eine eigene Absendernummer (CLIP) zulassen.
- **Text-to-Speech** in Home Assistant, empfohlen das **Piper-Add-on** (lokal, kostenlos, deutsche Stimmen). Alternativ funktioniert jede TTS-Entity, z.B. Home Assistant Cloud.
- **Netzwerk:** Das Add-on läuft im Host-Netzwerk. Ausgehend müssen SIP (meist UDP/TCP 5060 bzw. TLS 5061) und die RTP-Audioports des Anbieters erreichbar sein.

## Annahmen (nicht verifiziert)

Folgendes wurde beim Schreiben angenommen und muss beim ersten Test geprüft werden:

1. **baresip-Steuerung:** Die Steuerung läuft über das Modul `ctrl_tcp`. Event-Namen (`CALL_ESTABLISHED`, `CALL_DTMF_START`, `CALL_CLOSED`), Modulnamen (`aufile`, `nullaudio`, `g711`, `menu`, `account`, `ctrl_tcp`), der Modulpfad `/usr/lib/baresip/modules` und die Config-Syntax (`audio_source aufile,...`, Account-Zeile mit `auth_user`, `auth_pass`, `outbound`) stammen aus dem Gedächtnis und können je nach baresip-Version abweichen.
2. **Pakete:** Im Alpine-Basis-Image von Home Assistant sind `baresip`, `py3-aiohttp` und `ffmpeg` installierbar. Ein Docker-Build wurde nicht ausgeführt.
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
