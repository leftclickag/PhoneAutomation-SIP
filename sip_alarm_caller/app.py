"""SIP Alarm Caller: HTTP-Trigger -> TTS -> pjsua-Anruf, Wiederholung bis DTMF-Quittierung.

Steuerung: pjsua (PJSIP) laeuft als Unterprozess mit Telnet-CLI. Anruf-/Registrierungs-
Ereignisse werden aus dem stdout-Log (Log-Level 5) geparst:
- "Call N state changed to CONFIRMED/DISCONNCTD"  (pjsua_app.c, on_call_state)
- "Received DTMF digit X, vol=..."                (pjmedia/stream.c, RFC 2833, Level 5)
- "registration success/failed, status=N"         (pjsua_acc.c, on_reg_state)
"""
import asyncio
import json
import os
import re
import socket
import wave

import aiohttp
from aiohttp import web

OPTIONS = json.load(open("/data/options.json"))
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
HA_API = "http://supervisor/core"
MSG_WAV = "/tmp/message.wav"
CLI_PORT = 5556

RE_REG = re.compile(r"registration (success|failed), status=(\d+)")
RE_CALL_STATE = re.compile(r"Call (\d+) state changed to (\S+)")
RE_DTMF = re.compile(r"Received DTMF digit (\S),|Incoming DTMF digit (\S)")


def log(*a):
    print(*a, flush=True)


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
            "--max-calls=1",
            "--log-level=5",
            "--app-log-level=5",
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
        self.proc = await asyncio.create_subprocess_exec(
            *self.args(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT)
        asyncio.create_task(self._read_log(self.proc.stdout))
        for _ in range(60):
            if self.proc.returncode is not None:
                raise RuntimeError(f"pjsua wurde beendet (rc={self.proc.returncode})")
            try:
                reader, self.telnet = await asyncio.open_connection("127.0.0.1", CLI_PORT)
                break
            except OSError:
                await asyncio.sleep(0.5)
        else:
            raise RuntimeError("pjsua-CLI (Telnet) nicht erreichbar")
        asyncio.create_task(self._drain_telnet(reader))
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
            log("Keine Registrierungs-Rueckmeldung erhalten, fahre trotzdem fort.")

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

    async def _read_log(self, reader):
        while True:
            line = await reader.readline()
            if not line:
                break
            text = line.decode("utf-8", "replace").rstrip()
            m = RE_REG.search(text)
            if m:
                log("pjsua:", text)
                await self.events.put({"type": "REG_OK" if m.group(1) == "success" else "REG_FAIL", "param": m.group(2)})
                continue
            m = RE_CALL_STATE.search(text)
            if m:
                t = {"CONFIRMED": "CALL_ESTABLISHED", "DISCONNCTD": "CALL_CLOSED"}.get(m.group(2))
                if t:
                    log("pjsua:", text)
                    await self.events.put({"type": t})
                continue
            m = RE_DTMF.search(text)
            if m:
                digit = m.group(1) or m.group(2)
                log("pjsua:", text)
                await self.events.put({"type": "DTMF", "param": digit})

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
        self.acked = asyncio.Event()

    def running(self):
        return self.task is not None and not self.task.done()

    async def trigger(self, message):
        if self.running():
            return False
        self.acked.clear()
        self.task = asyncio.create_task(self.run(message))
        return True

    async def stop(self):
        if self.running():
            self.task.cancel()
        await self.sip.hangup()
        self.acked.clear()

    async def run(self, message):
        o = OPTIONS
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
                log(f"Runde {rnd}: rufe {number} an")
                if await self.call(number, duration):
                    log("Quittiert, beende Anrufe.")
                    return
            await asyncio.sleep(o["retry_interval"])
        log("Maximale Anzahl Runden erreicht.")

    async def call(self, number, duration):
        """True wenn Quittierung per DTMF erfolgte."""
        o = OPTIONS
        self.sip.drain_events()
        tparam = "" if o["sip_transport"] == "udp" else f";transport={o['sip_transport']}"
        target = number if number.startswith("sip:") else f'sip:{number}@{o["sip_server"]}{tparam}'
        await self.sip.command(f"call new {target}")
        established = False
        deadline = asyncio.get_event_loop().time() + o["ring_timeout"]
        try:
            while True:
                timeout = deadline - asyncio.get_event_loop().time()
                if timeout <= 0:
                    return False
                try:
                    ev = await asyncio.wait_for(self.sip.events.get(), timeout)
                except asyncio.TimeoutError:
                    return False
                t = ev.get("type")
                if t == "CALL_ESTABLISHED" and not established:
                    established = True
                    deadline = asyncio.get_event_loop().time() + duration + 5
                elif t == "DTMF" and ev.get("param") == o["ack_digit"]:
                    return True
                elif t == "CALL_CLOSED":
                    return False
        finally:
            await self.sip.hangup()
            await asyncio.sleep(2)


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
    log("SIP Alarm Caller bereit auf Port 8099")
    await asyncio.Event().wait()


asyncio.run(main())
