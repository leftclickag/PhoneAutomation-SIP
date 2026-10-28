# SIP Alarm Caller

Ruft bei einem Alarm per SIP-Trunk (z.B. PhoneStar) an und spricht einen TTS-Text.
Wiederholt die Anrufe, bis jemand die Quittiertaste (Standard `1`) drückt.

## Konfiguration

| Option | Bedeutung |
|---|---|
| `sip_server` | SIP-Domain/Registrar laut PhoneStar |
| `sip_user` / `sip_password` / `sip_auth_user` | SIP-Zugangsdaten (`sip_auth_user` nur, falls abweichend) |
| `sip_outbound_proxy` | optional |
| `numbers` | Zielnummern im Format `+41791234567`, werden der Reihe nach angerufen |
| `tts_engine` | TTS-Entity in HA, z.B. `tts.piper` (Piper-Add-on installieren) |
| `ring_timeout` | Sekunden, bis ein Anruf als unbeantwortet gilt |
| `retry_interval` / `max_rounds` | Pause zwischen Runden / maximale Runden |
| `api_token` | optional, dann `Authorization: Bearer <token>` nötig |

## Home-Assistant-Einbindung

`configuration.yaml`:

```yaml
rest_command:
  sip_alarm_call:
    url: "http://localhost:8099/alarm"
    method: POST
    content_type: "application/json"
    payload: '{"message": "{{ message }}"}'
  sip_alarm_stop:
    url: "http://localhost:8099/stop"
    method: POST
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

Test ohne Alarm: Developer Tools -> Aktionen -> `rest_command.sip_alarm_call`.
