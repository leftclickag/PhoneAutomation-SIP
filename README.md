English | [Deutsch](README.de.md)

# PhoneAutomation-SIP

Home Assistant app by Leftclick AG. When an alarm fires (for example from [Alarmo](https://github.com/nielsfaber/alarmo)), it calls a phone through your own SIP provider, speaks a text-to-speech message, and repeats the calls until someone acknowledges with a keypress. An alternative to Twilio without a fee per call.

> **Status: the call works, acknowledgement is not confirmed yet.** The app installs on Home Assistant and places a real SIP call. Pressing the acknowledge key has not been confirmed to stop the retries. Do not use it as the only alarm path. Open checks are in [Checklist](#checklist).

The app lives in [`sip_alarm_caller/`](sip_alarm_caller/). Configuration and the Home Assistant wiring are in [`sip_alarm_caller/DOCS.md`](sip_alarm_caller/DOCS.md).

## Installation

> **Name change:** From Home Assistant 2026.2, "add-ons" are called **Apps** in the UI (the store is the App Store, and local apps appear under Local apps). From Supervisor 2026.6 the local folder on the device is **`local_apps`** instead of `addons`. Both names are covered below. Use the path that matches your version. These steps are for Home Assistant OS or Supervised. Home Assistant Container and Core cannot run apps.

### Option A: Public repository (preferred)

1. Open Home Assistant → **Settings → Apps** → **Install app**. The App Store opens.
2. Open the **⋯ menu** at the top right → **Repositories**.
3. Paste `https://github.com/leftclickag/PhoneAutomation-SIP` → **Add**.
4. Back in the store, hard-reload the page (**Ctrl+F5**), open **SIP Alarm Caller** → **Install**.

### Option B: Local copy over SSH

The **Terminal & SSH** app must be installed (Settings → Apps). Then:

1. Copy the app files from [`sip_alarm_caller/`](sip_alarm_caller/) (`config.yaml`, `Dockerfile`, `run.sh`, `app.py`, `DOCS.md`) into a `sip_alarm_caller` folder in the device's local apps directory:

   ```
   /local_apps/sip_alarm_caller/config.yaml
   /local_apps/sip_alarm_caller/Dockerfile
   /local_apps/sip_alarm_caller/run.sh
   /local_apps/sip_alarm_caller/app.py
   /local_apps/sip_alarm_caller/DOCS.md
   ```

   From the SSH app terminal, for example:

   ```bash
   mkdir -p /local_apps/sip_alarm_caller
   # Copy the files, for example with scp from your PC:
   # scp C:\GitHub\PhoneAutomation-SIP\sip_alarm_caller\* root@homeassistant.local:/local_apps/sip_alarm_caller/
   ls /local_apps/sip_alarm_caller
   ```

   The folder must sit **directly** in `local_apps`. A nested path such as `local_apps/PhoneAutomation-SIP/sip_alarm_caller/` is ignored. On installations older than Supervisor 2026.6 the folder is `/addons` instead of `/local_apps`. Copy into that directory if `local_apps` does not exist.

2. Open Home Assistant → **Settings → Apps → Install app** (App Store).
3. **⋯ menu** → **Check for updates**.
4. **Hard-reload with Ctrl+F5**. The store often keeps the previous list.
5. A **Local apps** section appears at the top with **SIP Alarm Caller** → open it → **Install**. The first start builds the Docker image from the Dockerfile.
6. If step 5 does not show the app, reboot the device (Settings → System) and check again.

### Option B via Samba

If the **Samba share** app is running, open `\\homeassistant.local\local_apps` in Explorer (older Samba versions: `\\homeassistant.local\addons`. Both names point at the same folder) and create `sip_alarm_caller` with the five files above. The File Editor and Studio Code Server only see `/config`, not `local_apps`. Use Samba or SSH to copy.

### After installation (both options)

1. Open the app → **Configuration**: enter the SIP account (`sip_server`, `sip_user`, `sip_password`) and the target numbers as `+41791234567`. Check `tts_engine` (default `tts.piper`, see DOCS.md) → **Save**.
2. Press **Start** (and enable start on boot).
3. Open **Log** and confirm the SIP registration succeeded.
4. A broken app configuration is **skipped silently** by the store. If the app does not appear, open **Settings → System → Logs**, choose **Supervisor** in the top-right dropdown, and look for warnings about `sip_alarm_caller`.

## Requirements

- **Home Assistant OS** (or Supervised). Aimed at Home Assistant Green (`aarch64`). `amd64` is listed as well. Home Assistant Container and Core cannot install apps.
- **A SIP account that can place outbound calls:** server, user, and password. The provider must allow calls to the destination networks, support G.711 (PCMA/PCMU), and allow the caller ID you need.
- **Text-to-speech** in Home Assistant. The local **Piper** app is the recommended choice. Any other TTS entity works too, including Home Assistant Cloud.
- **Network:** the app uses the host network. Outbound SIP (usually UDP/TCP 5060 or TLS 5061) and the provider's RTP audio ports must be reachable.

## What is still assumed

These points were assumed while writing the app and still need a check on a real system. Tick them off in the [checklist](#checklist).

1. **pjsua control.** The SIP engine is **pjsua** (PJSIP), started with a telnet CLI (`--use-cli`, `--cli-telnet-port`) and log level 5. Call and registration events are parsed from the log (`Call N state changed to`, `registration success/failed`). SIP DTMF is the line `Incoming DTMF on call N: X, using … method`. pjsua's stdout is a pipe, so the app starts it with `--stdout-no-buf`. Without that flag the answer and keypress lines stay buffered and the app never sees them.
2. **Packages.** `pjsua`, `py3-aiohttp`, and `ffmpeg` are in Alpine 3.24, which is the Home Assistant base image. **baresip is not** (it exists only in Alpine edge/testing), which is why the app uses pjsua.
3. **TTS through the HA API.** `POST http://supervisor/core/api/tts_get_url` with `homeassistant_api: true` returns a `path` that can be downloaded from the same proxy.
4. **Piper defaults.** The entity `tts.piper` and the language `de_DE` are placeholders. The real entity name is under Settings → Devices & services → Wyoming Protocol.
5. **Acknowledgement.** The configured key (default `1`) should stop the retries. It is accepted both as SIP DTMF (RFC 2833/4733 or SIP INFO) and as a tone in the audio coming back from the phone, because many mobile networks only forward the key as sound.
6. **PhoneStar / Swisscom.** Provider-specific settings (server, registration, proxy, transport, number format) are not built in. The app expects a normal SIP registration and numbers in international form (`+41...`).
7. **Who can trigger a call.** Port 8099 is published on the host. Without `api_token`, any device on the LAN can start calls. Set a token before real use.
8. **One call at a time.** One alarm run places one call at a time. Numbers are dialed in order, not in parallel.

## Suggested test

1. Install Piper and confirm a TTS entity.
2. Install the app, enter the SIP account and your own number, start it, and read the log.
3. Run `rest_command.sip_alarm_call` from Developer Tools. Do you hear the message? Does key 1 stop the calls?
4. Only then connect Alarmo, and test the repeats and `/stop`.
5. Keep an independent path as well, such as a push notification from the Home Assistant Companion app.

## Checklist

Checklist for this app on a real Home Assistant system. Check an item by changing `- [ ]` to `- [x]` once that behavior has been seen working. Add a new line the same way.

Checked items below are ones already observed while installing and placing calls. Anything still open has not been confirmed, including the acknowledge key.

### Done

- [x] The image builds on Home Assistant OS (`aarch64`) with `pjsua` from Alpine 3.24
- [x] The app process starts and listens on port 8099
- [x] `rest_command.sip_alarm_call` to `http://127.0.0.1:8099/alarm` places an outbound call
- [x] The phone rings and the spoken message is played
- [x] Missed acknowledgement causes another call after the retry pause

### Still to confirm

- [ ] After a rebuild of version 0.2.4, the log contains `SIP Alarm Caller 0.2.4 bereit auf Port 8099`
- [ ] When the phone is answered, the log contains `Anruf verbunden, warte auf Taste 1`
- [ ] Pressing 1 stops the retries
- [ ] The log contains `Quittiert mit Taste 1` or `Tastenton erkannt: 1`
- [ ] `rest_command.sip_alarm_stop` hangs up and ends the alarm run
- [ ] An Alarmo trigger starts the calls, and clearing the alarm stops them
- [ ] With `api_token` set, a request without the bearer token is rejected
- [ ] TCP and TLS transports register and place a call
- [ ] Several numbers are dialed one after another in one round

## License

[MIT](LICENSE). Use is at your own risk. There is no warranty, including for use as an alarm system.

&copy; Leftclick AG
