English | [Deutsch](https://github.com/leftclickag/PhoneAutomation-SIP/blob/main/sip_alarm_caller/DOCS.de.md)

# SIP Alarm Caller

Places a call over a SIP trunk (for example PhoneStar) when an alarm fires and speaks a TTS message.
Repeats the calls until someone presses **Stop alarm calls** in Home Assistant, or until `max_rounds` is reached.
A key on the phone does not stop the calls.

## Configuration

| Option | Meaning |
|---|---|
| `sip_server` | SIP domain / registrar from the provider |
| `sip_user` / `sip_password` / `sip_auth_user` | SIP credentials (`sip_auth_user` only when it differs from the user) |
| `sip_outbound_proxy` | optional |
| `numbers` | Destination numbers as `+41791234567`, dialed in order |
| `tts_engine` | TTS entity in Home Assistant, for example `tts.piper` (install the Piper app) |
| `ring_timeout` | Seconds before an unanswered call is given up |
| `retry_interval` / `max_rounds` | Pause between rounds / maximum rounds |
| `api_token` | optional; when set, requests need `Authorization: Bearer <token>` |

## Home Assistant wiring

In `configuration.yaml`, use `127.0.0.1`, not `localhost`. Home Assistant often resolves `localhost` to IPv6 (`::1`). The app listens on IPv4, so `localhost` fails with "Client error occurred when calling resource". `127.0.0.1` reaches the host directly, because Home Assistant Core and this app both use the host network.

The app must be running. The log must contain `bereit auf Port 8099`. If `sip_server` or `numbers` is missing, the app exits before it opens the port. If `api_token` is set, send the same value in the `Authorization` header.

```yaml
rest_command:
  sip_alarm_call:
    url: "http://127.0.0.1:8099/alarm"
    method: POST
    content_type: "application/json"
    payload: '{"message": "{{ message }}"}'
    # headers:
    #   Authorization: "Bearer YOUR_API_TOKEN"
  sip_alarm_stop:
    url: "http://127.0.0.1:8099/stop"
    method: POST
    # headers:
    #   Authorization: "Bearer YOUR_API_TOKEN"

template:
  - button:
      - name: Stop alarm calls
        unique_id: sip_alarm_caller_stop
        icon: mdi:phone-hangup
        press:
          - action: rest_command.sip_alarm_stop
```

Restart Home Assistant after saving. The button entity is `button.stop_alarm_calls`. Add it to a dashboard with a Button card. Pressing it hangs up and ends the retries. The spoken message is unchanged, so remove any "press 1" sentence from `default_message` in the app configuration. A previously saved message is kept until you edit it.

Automations:

```yaml
automation:
  - alias: Alarm -> call
    trigger:
      - platform: state
        entity_id: alarm_control_panel.alarmo
        to: triggered
    action:
      - action: rest_command.sip_alarm_call
        data:
          message: "Warning. An alarm was triggered."

  - alias: Alarm cleared -> stop calls
    trigger:
      - platform: state
        entity_id: alarm_control_panel.alarmo
        from: triggered
    action:
      - action: rest_command.sip_alarm_stop
```

Test without an alarm: Developer Tools → Actions → `rest_command.sip_alarm_call`. Then press **Stop alarm calls**.
