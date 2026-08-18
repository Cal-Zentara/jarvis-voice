"""Keeps the voice loaded in memory so speaking is instant.

Listens on 127.0.0.1:5210. POST the text to speak; it renders and plays it.
Started automatically by the speak hook if it isn't already running.

Two voices:
  - ElevenLabs, if an API key is set. Sounds more human, costs per character.
  - Kokoro, otherwise. Runs on this machine, free, no account.

Whichever you pick is the only one used. If ElevenLabs fails it stays silent
rather than switching voices on you mid-conversation.

To use ElevenLabs, put the key in ~/.claude/voice/elevenlabs.key (one line) or
set ELEVENLABS_API_KEY. Delete the file to go back to Kokoro.
"""
import json
import os
import platform
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import soundfile as sf

BASE = os.path.dirname(os.path.abspath(__file__))
PORT = 5210

# --- Kokoro (free, local) -------------------------------------------------
KOKORO_VOICE = "bm_george"

# --- ElevenLabs (paid, cloud) ---------------------------------------------
KEY_FILE = os.path.join(BASE, "elevenlabs.key")
# Rachel, a calm default. Swap for any voice_id from the ElevenLabs library.
ELEVEN_VOICE = "onwK4e9ZLuTAKqWW03F9"  # Daniel, British male
# Flash is the low-latency model. For a conversation, answering fast beats
# squeezing out the last bit of expressiveness.
ELEVEN_MODEL = "eleven_flash_v2_5"
ELEVEN_RATE = 24000  # raw PCM, so we can write a wav without any converter


def elevenlabs_key():
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if key:
        return key
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, encoding="utf-8") as fh:
            return fh.read().strip()
    return ""


KEY = elevenlabs_key()

kokoro = None
if not KEY:
    from kokoro_onnx import Kokoro
    kokoro = Kokoro(os.path.join(BASE, "kokoro-v1.0.onnx"),
                    os.path.join(BASE, "voices-v1.0.bin"))

lock = threading.Lock()
counter = 0

# While this file exists the listener stays deaf, so the mic never
# transcribes our own voice coming out of the headphones. Kept next to these
# files, not in the temp folder: on a Mac two processes can get different temp
# folders and never see each other's flag.
SPEAKING_FLAG = os.path.join(BASE, "claude-voice-speaking")
LOG = os.path.join(BASE, "server.log")


def log(msg):
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def render_elevenlabs(text, out):
    """Ask ElevenLabs for raw PCM and save it as a wav. Returns False on failure."""
    url = (f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE}"
           f"?output_format=pcm_{ELEVEN_RATE}")
    body = json.dumps({
        "text": text,
        "model_id": ELEVEN_MODEL,
        "voice_settings": {"stability": 0.4, "similarity_boost": 0.75, "style": 0.3,
                           # 1.0 is normal pace. 1.2 is ElevenLabs' maximum - above it the API
                           # returns a 400 and, with no fallback, you get silence.
                           "speed": 1.2},
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "xi-api-key": KEY,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            pcm = res.read()
    except (urllib.error.URLError, TimeoutError) as err:
        # Deliberately no fallback. Swapping voices mid-conversation is more
        # confusing than saying nothing, so a failure stays silent and logs.
        log(f"elevenlabs failed ({err}) - saying nothing")
        return False
    sf.write(out, np.frombuffer(pcm, dtype=np.int16), ELEVEN_RATE)
    return True


def render_kokoro(text, out):
    samples, rate = kokoro.create(text, voice=KOKORO_VOICE, speed=1.0, lang="en-gb")
    sf.write(out, samples, rate)


IS_MAC = platform.system() == "Darwin"


def play(path):
    """Play a wav and wait for it to finish. Mac has afplay; Windows doesn't."""
    if IS_MAC:
        subprocess.run(["afplay", path], check=False)
        return
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"$p=New-Object System.Media.SoundPlayer '{path}'; $p.PlaySync()"],
        check=False,
        # Without this a black console window flashes on every reply.
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def speak(text):
    global counter
    with lock:
        counter += 1
        out = os.path.join(tempfile.gettempdir(), f"claude-voice-{counter % 4}.wav")

        # Claim the flag before rendering, not after. Rendering takes a moment,
        # and a "hey Jarvis" landing in that gap used to start recording just as
        # the reply began playing - so the mic transcribed Claude's own voice.
        open(SPEAKING_FLAG, "w").close()
        try:
            if KEY:
                if not render_elevenlabs(text, out):
                    return
            else:
                render_kokoro(text, out)
            play(out)
        finally:
            try:
                os.remove(SPEAKING_FLAG)
            except OSError:
                pass


# A plain text POST from a web page reaches localhost with no preflight, so
# without these checks any site you visit could make this talk - and spend your
# ElevenLabs credit. Browsers always send Origin on a cross-site POST, and can't
# forge Host, so refusing both is enough.
MAX_CHARS = 2000


class Handler(BaseHTTPRequestHandler):
    def from_a_browser(self):
        if self.headers.get("Origin") or self.headers.get("Referer"):
            return True
        host = (self.headers.get("Host") or "").strip()
        return host not in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")

    def do_POST(self):
        if self.from_a_browser():
            self.send_response(403)
            self.end_headers()
            log("refused a request that didn't come from the hook")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        if not 0 < length <= MAX_CHARS * 4:  # utf-8 worst case
            self.send_response(400)
            self.end_headers()
            return
        text = self.rfile.read(length).decode("utf-8", "ignore").strip()[:MAX_CHARS]
        # Answer before speaking, so whoever called us isn't left waiting.
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
        if text:
            speak(text)

    def do_GET(self):
        if self.from_a_browser():
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ready")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    import traceback
    log(f"voice: {'ElevenLabs' if KEY else 'Kokoro (free, local)'}")
    # Threading, so a long reply being spoken doesn't block the next one from
    # even being accepted - the hook would time out and that reply be lost.
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
