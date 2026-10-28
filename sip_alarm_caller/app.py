"""SIP Alarm Caller: HTTP-Trigger -> TTS -> baresip-Anruf, Wiederholung bis DTMF-Quittierung."""
import asyncio
import json
import os
import wave

import aiohttp
from aiohttp import web

OPTIONS = json.load(open("/data/options.json"))
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
HA_API = "http://supervisor/core"
BARESIP_DIR = "/data/baresip"
MSG_WAV = "/tmp/message.wav"
CTRL_PORT = 4444


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- baresip

def write_baresip_config():
    o = OPTIONS
    os.makedirs(BARESIP_DIR, exist_ok=True)
    user = o["sip_user"]
    auth = o.get("sip_auth_user") or user
    acc = f'<sip:{user}@{o["sip_server"]};transport={o["sip_transport"]}>;auth_user={auth};auth_pass={o["sip_password"]};regint=300'
    if o.get("sip_outbound_proxy"):
        acc += f';outbound="sip:{o["sip_outbound_proxy"]};transport={o["sip_transport"]}"'
    with open(f"{BARESIP_DIR}/accounts", "w") as f:
        f.write(acc + "\n")
    with open(f"{BARESIP_DIR}/config", "w") as f:
        f.write(
            "module_path /usr/lib/baresip/modules\n"
            "module g711.so\nmodule aufile.so\nmodule nullaudio.so\n"
            "module menu.so\nmodule account.so\nmodule ctrl_tcp.so\n"
            f"ctrl_tcp_listen 127.0.0.1:{CTRL_PORT}\n"
            f"audio_source aufile,{MSG_WAV}\n"
            "audio_player nullaudio,\naudio_alert nullaudio,\n"
            "audio_codecs PCMA,PCMU\n"
        )


def netstring(obj):
    data = json.dumps(obj).encode()
    return str(len(data)).encode() + b":" + data + b","


class Baresip:
    def __init__(self):
        self.events = asyncio.Queue()
        self.writer = None
        self.proc = None

    async def start(self):
        write_baresip_config()
        self.proc = await asyncio.create_subprocess_exec("baresip", "-f", BARESIP_DIR)
        for _ in range(30):
            try:
                reader, self.writer = await asyncio.open_connection("127.0.0.1", CTRL_PORT)
                break
            except OSError:
                await asyncio.sleep(1)
        else:
            raise RuntimeError("baresip ctrl_tcp nicht erreichbar")
        asyncio.create_task(self._read(reader))

    async def _read(self, reader):
        while True:
            length = b""
            while True:
                c = await reader.readexactly(1)
                if c == b":":
                    break
                length += c
            payload = await reader.readexactly(int(length) + 1)
            try:
                msg = json.loads(payload[:-1])
            except ValueError:
                continue
            if msg.get("event"):
                log("baresip event:", msg.get("type"), msg.get("param", ""))
                await self.events.put(msg)

    async def command(self, cmd, params=""):
        self.writer.write(netstring({"command": cmd, "params": params}))
        await self.writer.drain()

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
            await self.sip.command("hangup")
        self.acked.clear()

    async def run(self, message):
        o = OPTIONS
        try:
            duration = await make_audio(message or o["default_message"])
        except Exception as e:
            log("TTS-Fehler:", e)
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
        target = number if number.startswith("sip:") else f'sip:{number}@{o["sip_server"]}'
        await self.sip.command("dial", target)
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
                elif t == "CALL_DTMF_START" and ev.get("param") == o["ack_digit"]:
                    return True
                elif t == "CALL_CLOSED":
                    return False
        finally:
            await self.sip.command("hangup")
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
    if not OPTIONS["sip_server"] or not OPTIONS["numbers"]:
        raise SystemExit("sip_server und numbers muessen in der Add-on-Konfiguration gesetzt sein.")
    sip = Baresip()
    await sip.start()
    runner = web.AppRunner(make_app(Caller(sip)))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8099).start()
    log("SIP Alarm Caller bereit auf Port 8099")
    await asyncio.Event().wait()


asyncio.run(main())
