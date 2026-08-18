"""Speaks text piped in on stdin, using Kokoro running locally. No API, no credits."""
import os
import platform
import sys
import tempfile
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
VOICE = "bm_george"

text = sys.stdin.read().strip()
if not text:
    sys.exit(0)

from kokoro_onnx import Kokoro
import soundfile as sf

kokoro = Kokoro(os.path.join(BASE, "kokoro-v1.0.onnx"), os.path.join(BASE, "voices-v1.0.bin"))
samples, rate = kokoro.create(text, voice=VOICE, speed=1.0, lang="en-gb")

out = os.path.join(tempfile.gettempdir(), "claude-voice.wav")
sf.write(out, samples, rate)

if platform.system() == "Darwin":
    subprocess.run(["afplay", out], check=False)
else:
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"$p=New-Object System.Media.SoundPlayer '{out}'; $p.PlaySync()",
        ],
        check=False,
    )
