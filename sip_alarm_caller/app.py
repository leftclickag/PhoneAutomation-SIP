"""SIP Alarm Caller: HTTP-Trigger -> TTS -> pjsua-Anruf.

Die Anrufe wiederholen sich, bis Home Assistant POST /stop schickt oder die
maximale Rundenzahl erreicht ist. Eine Taste am Telefon beendet den Lauf nicht:
viele Mobilnetze liefern die Taste nicht an den SIP-Client zurueck.

Steuerung: pjsua (PJSIP) laeuft als Unterprozess mit Telnet-CLI. Anruf- und
Registrierungsereignisse werden aus dem stdout-Log geparst:
- "Call N state changed to CONFIRMED/DISCONNCTD"          (pjsua_app.c)
- "registration success/failed, status=N"                 (pjsua_acc.c)

Ob jemand abgenommen hat, wird zusaetzlich am Pegel des zurueckkommenden
Audios erkannt. Die Zeile CONFIRMED fehlt auf manchen Leitungen.
"""
import asyncio
import json
import os
import re
import socket
import struct
import wave

import aiohttp
from aiohttp import web

OPTIONS = json.load(open("/data/options.json"))
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
HA_API = "http://supervisor/core"
MSG_WAV = "/tmp/message.wav"
REC_WAV = "/tmp/rx.wav"
CLI_PORT = 5556

RE_REG = re.compile(r"registration (success|failed), status=(\d+)", re.I)
RE_ANSI = re.compile(r"\x1b\[[0-9;]*m")
RE_CALL_STATE = re.compile(r"Call (\d+) state changed to (\S+)")
RE_CALL_END = re.compile(r"Call (\d+) is DISCONNECTED")


def log(*a):
    print(*a, flush=True)


def wav_format(header):
    """(rate, channels, data_offset) from a WAV header, or None while the header is incomplete."""
    if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
        return None
    pos, rate, channels, data_off = 12, None, None, None
    while pos + 8 <= len(header):
        chunk, size = header[pos:pos + 4], int.from_bytes(header[pos + 4:pos + 8], "little")
        if chunk == b"fmt " and pos + 8 + 16 <= len(header):
            channels = int.from_bytes(header[pos + 8:pos + 10], "little")
            rate = int.from_bytes(header[pos + 12:pos + 16], "little")
        elif chunk == b"data":
            data_off = pos + 8
            break
        if size < 0 or pos + 8 + size > len(header):
            break
        pos += 8 + size + (size & 1)
    if rate and channels and data_off is not None:
        return rate, channels, data_off
    return None


class InbandEar:
    """Reads the remote-audio WAV pjsua is writing and reports its peak level."""

    def __init__(self, path, events):
        self.path = path
        self.events = events
        self.task = None

    def start(self):
        self.task = asyncio.create_task(self._run())

    async def stop(self):
        if self.task is None:
            return
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass
        self.task = None

    async def _run(self):
        fmt = None
        pos = 0
        buf = b""
        loud = 0
        reported = asyncio.get_event_loop().time()
        while True:
            try:
                size = os.path.getsize(self.path)
            except OSError:
                await asyncio.sleep(0.1)
                continue
            if fmt is None:
                with open(self.path, "rb") as f:
                    fmt = wav_format(f.read(4096))
                if fmt is None:
                    await asyncio.sleep(0.1)
                    continue
                rate, channels, data_off = fmt
                width = channels * 2
                pos = size - ((size - data_off) % width)
                log("Messe Gegensprech-Audio (", rate, "Hz ).")
                continue
            rate, channels, data_off = fmt
            width = channels * 2
            frame_n = max(1, int(rate * 0.04))
            frame_bytes = frame_n * width
            if size < pos:
                pos, buf = data_off, b""
            if size - pos > rate * width:
                pos = size - rate * width
                pos -= (pos - data_off) % width
                buf = b""
            if size == pos:
                await asyncio.sleep(0.05)
                continue
            with open(self.path, "rb") as f:
                f.seek(pos)
                chunk = f.read(size - pos)
            pos += len(chunk)
            buf += chunk
            while len(buf) >= frame_bytes:
                frame, buf = buf[:frame_bytes], buf[frame_bytes:]
                samples = struct.unpack("<" + "h" * (len(frame) // 2), frame)
                if channels > 1:
                    samples = samples[0::channels]
                peak = max(abs(s) for s in samples)
                if peak > loud:
                    loud = peak
                now = asyncio.get_event_loop().time()
                if now - reported >= 2:
                    log("Rueckaudio Pegel", loud)
                    await self.events.put({"type": "LEVEL", "param": loud})
                    loud = 0
                    reported = now


def write_silence(path, seconds=1):
    """Platzhalter-WAV (8 kHz mono s16), damit pjsua beim Start einen Player anlegen kann."""
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 8000 * seconds)


# ---------------------------------------------------------------- pjsua

class Pjsua:
    def __init__(self):
        self.events = asyncio.Queue()
        self.proc = None
        self.telnet = None
        self.wav = None
        self.log_task = None
        self.saw_log = False

    def args(self):
        o = OPTIONS
        auth = o.get("sip_auth_user") or o["sip_user"]
        transport = o["sip_transport"]
        tparam = "" if transport == "udp" else f";transport={transport}"
        args = [
            "pjsua",
            f"--id=sip:{o['sip_user']}@{o['sip_server']}{tparam}",
            f"--registrar=sip:{o['sip_server']}{tparam}",
            "--realm=*",
            f"--username={auth}",
            f"--password={o['sip_password']}",
            "--null-audio",
            f"--play-file={self.wav}",
            "--auto-play",
            f"--rec-file={REC_WAV}",
            "--auto-rec",
            "--max-calls=1",
            "--no-vad",
            "--ec-tail=0",
            "--log-level=5",
            "--app-log-level=5",
            # stdout is a pipe, so pjsua block-buffers logs. Without this, CONFIRMED
            # never reaches us and the call looks unanswered.
            "--stdout-no-buf",
            "--use-cli",
            f"--cli-telnet-port={CLI_PORT}",
            "--no-cli-console",
        ]
        if transport == "tcp":
            args.append("--no-udp")
        elif transport == "tls":
            args.append("--use-tls")
        if o.get("sip_outbound_proxy"):
            args.append(f"--proxy=sip:{o['sip_outbound_proxy']}{tparam}")
        return args

    async def start(self, wav):
        self.wav = wav
        self.saw_log = False
        # The addon container cannot allocate a pty (Errno 5). pjsua is started
        # with --stdout-no-buf so its log still arrives through this pipe.
        self.proc = await asyncio.create_subprocess_exec(
            *self.args(),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT)
        self.log_task = asyncio.create_task(self._read_log(self.proc.stdout))
        for _ in range(60):
            if self.proc.returncode is not None:
                raise RuntimeError(f"pjsua wurde beendet (rc={self.proc.returncode})")
            try:
                telnet_reader, self.telnet = await asyncio.open_connection("127.0.0.1", CLI_PORT)
                break
            except OSError:
                await asyncio.sleep(0.5)
        else:
            raise RuntimeError("pjsua-CLI (Telnet) nicht erreichbar")
        asyncio.create_task(self._drain_telnet(telnet_reader))
        log("pjsua gestartet, warte auf SIP-Registrierung ...")
        for _ in range(20):
            try:
                ev = await asyncio.wait_for(self.events.get(), 0.5)
            except asyncio.TimeoutError:
                if self.proc.returncode is not None:
                    raise RuntimeError("pjsua wurde beendet")
                continue
            if ev.get("type") == "REG_OK":
                log("SIP-Registrierung erfolgreich.")
                break
            if ev.get("type") == "REG_FAIL":
                log("WARNUNG: SIP-Registrierung fehlgeschlagen (Status", ev.get("param"), "). Anruf wird trotzdem versucht.")
                break
        else:
            if self.saw_log:
                log("Keine Registrierungszeile gesehen. Der Anruf wird trotzdem versucht.")
            else:
                log("Keine Ausgabe von pjsua gesehen. Der Anruf wird trotzdem versucht.")

    async def restart(self, wav):
        await self.stop()
        self.events = asyncio.Queue()
        await self.start(wav)

    async def stop(self):
        self.telnet = None
        while not self.events.empty():
            self.events.get_nowait()
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), 5)
            except asyncio.TimeoutError:
                self.proc.kill()
                await self.proc.wait()
        self.proc = None
        if self.log_task:
            self.log_task.cancel()
            try:
                await self.log_task
            except asyncio.CancelledError:
                pass
            self.log_task = None

    async def _read_log(self, reader):
        while True:
            line = await reader.readline()
            if not line:
                break
            text = RE_ANSI.sub("", line.decode("utf-8", "replace")).rstrip()
            if not text:
                continue
            self.saw_log = True
            if any(k in text for k in ("registr", "Call ", "DTMF", "DISCONN")) and "password" not in text.lower():
                log("pjsua:", text)
            m = RE_REG.search(text)
            if m:
                await self.events.put({"type": "REG_OK" if m.group(1) == "success" else "REG_FAIL", "param": m.group(2)})
                continue
            m = RE_CALL_STATE.search(text)
            if m:
                state = m.group(2).strip(".,)")
                t = {
                    "CONFIRMED": "CALL_ESTABLISHED",
                    "DISCONNCTD": "CALL_CLOSED",
                    "DISCONNECTED": "CALL_CLOSED",
                }.get(state)
                if t:
                    await self.events.put({"type": t})
                continue
            if RE_CALL_END.search(text):
                await self.events.put({"type": "CALL_CLOSED"})

    async def _drain_telnet(self, reader):
        while await reader.read(4096):
            pass

    async def command(self, cmd):
        if self.telnet is None:
            return
        try:
            self.telnet.write((cmd + "\r\n").encode())
            await self.telnet.drain()
        except Exception as e:
            log("pjsua-CLI-Fehler:", e)

    async def hangup(self):
        await self.command("call hangup_all")

    def drain_events(self):
        while not self.events.empty():
            self.events.get_nowait()


# ---------------------------------------------------------------- TTS

async def make_audio(message):
    """TTS ueber HA, auf 8kHz mono WAV konvertieren, mehrfach wiederholt."""
    headers = {"Authorization": f"Bearer {SUPERVISOR_TOKEN}"}
    body = {"engine_id": OPTIONS["tts_engine"], "message": message, "language": OPTIONS["tts_language"]}
    async with aiohttp.ClientSession(headers=headers) as s:
        async with s.post(f"{HA_API}/api/tts_get_url", json=body) as r:
            r.raise_for_status()
            path = (await r.json())["path"]
        async with s.get(HA_API + path) as r:
            r.raise_for_status()
            open("/tmp/tts_raw", "wb").write(await r.read())
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-loglevel", "error", "-i", "/tmp/tts_raw",
        "-ar", "8000", "-ac", "1", "-sample_fmt", "s16", "/tmp/tts_one.wav")
    if await proc.wait() != 0:
        raise RuntimeError("ffmpeg fehlgeschlagen")
    with wave.open("/tmp/tts_one.wav") as w:
        params, frames = w.getparams(), w.readframes(w.getnframes())
    silence = b"\x00\x00" * 8000 * 2  # 2 s Pause
    with wave.open(MSG_WAV, "wb") as out:
        out.setparams(params)
        out.writeframes(silence + (frames + silence) * OPTIONS["message_repeats"])
    return len(frames) / 16000 * OPTIONS["message_repeats"] + 2 * (OPTIONS["message_repeats"] + 1)


# ---------------------------------------------------------------- Anruflogik

class Caller:
    def __init__(self, sip):
        self.sip = sip
        self.task = None
        self.stopping = False

    def running(self):
        return self.task is not None and not self.task.done()

    async def trigger(self, message):
        if self.running():
            return False
        self.stopping = False
        self.task = asyncio.create_task(self.run(message))
        return True

    async def stop(self):
        self.stopping = True
        task = self.task if self.running() else None
        if task is not None:
            task.cancel()
        await self.sip.hangup()
        if task is None:
            log("Anrufe gestoppt.")
            return
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def run(self, message):
        o = OPTIONS
        try:
            try:
                duration = await make_audio(message or o["default_message"])
            except Exception as e:
                log("TTS-Fehler:", e)
                return
            try:
                await self.sip.restart(MSG_WAV)
            except Exception as e:
                log("pjsua-Start fehlgeschlagen:", e)
                return
            for rnd in range(1, o["max_rounds"] + 1):
                for number in o["numbers"]:
                    if self.stopping:
                        log("Anrufe gestoppt.")
                        return
                    log(f"Runde {rnd}: rufe {number} an")
                    await self.call(number, duration)
                if self.stopping:
                    log("Anrufe gestoppt.")
                    return
                if rnd == o["max_rounds"]:
                    break
                log(f"Naechste Runde in {o['retry_interval']} Sekunden. Stoppen ueber den Knopf in Home Assistant.")
                await asyncio.sleep(o["retry_interval"])
            log("Maximale Anzahl Runden erreicht.")
        except asyncio.CancelledError:
            log("Anrufe gestoppt.")
            raise

    async def call(self, number, duration):
        """One call. Plays the message, then hangs up. /stop ends the whole run."""
        o = OPTIONS
        self.sip.drain_events()
        tparam = "" if o["sip_transport"] == "udp" else f";transport={o['sip_transport']}"
        target = number if number.startswith("sip:") else f'sip:{number}@{o["sip_server"]}{tparam}'
        await self.sip.command(f"call new {target}")
        # CONFIRMED often never shows up on this trunk, so answer detection also
        # uses the return-audio level. The ear starts at dial time.
        ear = InbandEar(REC_WAV, self.sip.events)
        ear.start()
        answered = False
        deadline = asyncio.get_event_loop().time() + o["ring_timeout"]
        try:
            while True:
                if self.stopping:
                    log("Anruf abgebrochen.")
                    return
                timeout = deadline - asyncio.get_event_loop().time()
                if timeout <= 0:
                    log("Nachricht fertig, lege auf." if answered else "Niemand hat abgenommen.")
                    return
                try:
                    ev = await asyncio.wait_for(self.sip.events.get(), timeout)
                except asyncio.TimeoutError:
                    log("Nachricht fertig, lege auf." if answered else "Niemand hat abgenommen.")
                    return
                t = ev.get("type")
                if not answered and (t == "CALL_ESTABLISHED" or (t == "LEVEL" and ev.get("param", 0) >= 1000)):
                    answered = True
                    deadline = asyncio.get_event_loop().time() + duration + 5
                    log("Anruf verbunden, spiele Nachricht.")
                elif t == "CALL_CLOSED":
                    log("Gegenstelle hat aufgelegt." if answered else "Anruf beendet, bevor er verbunden war.")
                    return
        finally:
            # Uncancel before the awaits, otherwise this cleanup is skipped and
            # the phone keeps playing until the task dies.
            task = asyncio.current_task()
            uncancel = getattr(task, "uncancel", None)
            while task is not None and uncancel and task.cancelling():
                uncancel()
            try:
                await ear.stop()
                await self.sip.hangup()
                await asyncio.sleep(2)
            except Exception as e:
                log("Auflegen fehlgeschlagen:", e)


# ---------------------------------------------------------------- HTTP-API

def make_app(caller):
    def authorized(request):
        token = OPTIONS.get("api_token")
        return not token or request.headers.get("Authorization") == f"Bearer {token}"

    async def alarm(request):
        if not authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            data = await request.json()
        except ValueError:
            data = {}
        started = await caller.trigger(data.get("message"))
        return web.json_response({"started": started, "already_running": not started})

    async def stop(request):
        if not authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        await caller.stop()
        return web.json_response({"stopped": True})

    async def status(request):
        return web.json_response({"running": caller.running()})

    app = web.Application()
    app.add_routes([web.post("/alarm", alarm), web.post("/stop", stop), web.get("/status", status)])
    return app


async def main():
    o = OPTIONS
    if not o["sip_server"] or not o["numbers"]:
        raise SystemExit("sip_server und numbers muessen in der App-Konfiguration gesetzt sein.")
    sip = Pjsua()
    # Start mit Platzhalter-WAV: Registrierung und Konfigurationsfehler erscheinen frueh im Log.
    write_silence("/tmp/init.wav")
    try:
        await sip.start("/tmp/init.wav")
    except Exception as e:
        log("WARNUNG: erster pjsua-Start fehlgeschlagen:", e, "- wird bei Ausloesung erneut versucht.")
    caller = Caller(sip)
    runner = web.AppRunner(make_app(caller))
    await runner.setup()
    v4 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    v4.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    v4.bind(("0.0.0.0", 8099))
    await web.SockSite(runner, v4).start()
    try:
        v6 = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        v6.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        v6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        v6.bind(("::", 8099))
        await web.SockSite(runner, v6).start()
    except OSError as e:
        log("IPv6-Port 8099 nicht gebunden:", e)
    log("SIP Alarm Caller 0.2.7 bereit auf Port 8099")
    await asyncio.Event().wait()


asyncio.run(main())
