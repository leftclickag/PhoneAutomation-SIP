[English](https://github.com/leftclickag/PhoneAutomation-SIP/blob/main/sip_alarm_caller/DOCS.md) | Deutsch

# SIP Alarm Caller

Ruft bei einem Alarm per SIP-Trunk (z.B. PhoneStar) an und spricht einen TTS-Text.
Wiederholt die Anrufe, bis jemand die Quittiertaste (Standard `1`) drückt.

Home Assistant zeigt im Dokumentations-Tab die englische `DOCS.md`. Diese Datei ist die deutsche Fassung.

## Konfiguration

| Option | Bedeutung |
|---|---|
| `sip_server` | SIP-Domain/Registrar des Anbieters |
| `sip_user` / `sip_password` / `sip_auth_user` | SIP-Zugangsdaten (`sip_auth_user` nur, falls abweichend) |
| `sip_outbound_proxy` | optional |
| `numbers` | Zielnummern im Format `+41791234567`, werden der Reihe nach angerufen |
| `tts_engine` | TTS-Entity in HA, z.B. `tts.piper` (Piper-App installieren) |
| `ring_timeout` | Sekunden, bis ein Anruf als unbeantwortet gilt |
| `retry_interval` / `max_rounds` | Pause zwischen Runden / maximale Runden |
| `ack_digit` | Taste, die die Wiederholungen beendet, Standard `1` |
| `api_token` | optional, dann `Authorization: Bearer <token>` nötig |

## Home-Assistant-Einbindung

In `configuration.yaml` `127.0.0.1` verwenden, nicht `localhost`. Home Assistant löst `localhost` oft als IPv6 (`::1`) auf. Die App hört auf IPv4, deshalb endet `localhost` mit „Client error occurred when calling resource“. `127.0.0.1` trifft den Host direkt, weil Home Assistant Core und diese App im Host-Netz laufen.

Die App muss laufen. Im Log muss `bereit auf Port 8099` stehen. Fehlt `sip_server` oder `numbers`, beendet sich die App vorher und der Port bleibt zu. Ist `api_token` gesetzt, denselben Wert im Header `Authorization` mitschicken.

```yaml
rest_command:
  sip_alarm_call:
    url: "http://127.0.0.1:8099/alarm"
    method: POST
    content_type: "application/json"
    payload: '{"message": "{{ message }}"}'
    # headers:
    #   Authorization: "Bearer DEIN_API_TOKEN"
  sip_alarm_stop:
    url: "http://127.0.0.1:8099/stop"
    method: POST
    # headers:
    #   Authorization: "Bearer DEIN_API_TOKEN"
```

Automationen:

```yaml
automation:
  - alias: Alarm -> Anruf
    trigger:
      - platform: state
        entity_id: alarm_control_panel.alarmo
        to: triggered
    action:
      - service: rest_command.sip_alarm_call
        data:
          message: "Achtung! Es wurde eingebrochen. Alarm! Taste 1 drücken zum Quittieren."

  - alias: Alarm aus -> Anrufe stoppen
    trigger:
      - platform: state
        entity_id: alarm_control_panel.alarmo
        from: triggered
    action:
      - service: rest_command.sip_alarm_stop
```

Test ohne Alarm: Entwicklerwerkzeuge → Aktionen → `rest_command.sip_alarm_call`.
