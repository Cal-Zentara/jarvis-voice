"""Say "hey Jarvis" and Wispr Flow starts listening. Stop talking and it submits.

Uses openWakeWord, the same kind of detector Alexa and Siri use, rather than
transcribing everything and looking for a word in the text. It only ever listens
for the one phrase, so it doesn't mishear ordinary conversation.

Once woken it hands over to Flow, which does the actual dictation, then stops
the take after you go quiet and presses Enter for you.

Started by start.py, alongside server.py which does the talking.
"""
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time

import numpy as np
import sounddevice as sd
import webrtcvad
from openwakeword.model import Model
from pynput import keyboard

MIC = None                  # None uses the system default; or a name fragment
RATE = 16000
CHUNK = 1280                # 80ms, what openWakeWord expects
WAKE_MODEL = "hey_jarvis"
THRESHOLD = 0.5             # lower catches more, and misfires more
FRAME_MS = 30
FRAME = RATE * FRAME_MS // 1000
SILENCE_MS = 1500           # go quiet this long and the take ends
GRACE_S = 2.5               # never end a take in the first couple of seconds
MIN_SPEECH_MS = 400         # and never end one you haven't spoken into
COOLDOWN_S = 1.0            # stay deaf briefly after a take
PASTE_WAIT_S = 2.5          # let Flow finish pasting before pressing Enter
MAX_RECORD_S = 45

# Written by server.py while Claude is talking, so we don't hear our own voice.
# Kept next to these files rather than in the temp folder: on a Mac the two
# processes can get different temp folders and never see each other's flag.
SPEAKING_FLAG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "claude-voice-speaking")
# If server.py is force-killed mid-sentence the flag survives, and without this
# the wake word would be deaf forever with nothing on screen to explain it.
FLAG_STALE_AFTER_S = 120
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wake.log")

IS_MAC = platform.system() == "Darwin"
controller = keyboard.Controller()


def log(msg):
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%H:%M:%S')}  {msg}\n")


# Wispr Flow's shortcut. Windows keeps the default Ctrl+Win. macOS defaults to
# the Fn key, which cannot be pressed from code at all - macOS delivers Fn as a
# modifier flag, not a key event, and pynput has no way to send one. So on Mac
# you change Flow's shortcut to this combo instead, once, in Flow's settings.
MAC_SHORTCUT = (keyboard.Key.ctrl, keyboard.Key.alt, keyboard.Key.space)
WINDOWS_SHORTCUT = (keyboard.Key.ctrl, keyboard.Key.cmd)


def tap():
    """One press of Wispr Flow's shortcut."""
    keys = MAC_SHORTCUT if IS_MAC else WINDOWS_SHORTCUT
    for key in keys:
        controller.press(key)
    time.sleep(0.06)
    for key in reversed(keys):
        controller.release(key)


def toggle():
    """Flow's lock shortcut is a double tap of the same key."""
    tap()
    time.sleep(0.12)
    tap()


def claude_is_talking():
    try:
        age = time.time() - os.path.getmtime(SPEAKING_FLAG)
    except OSError:
        return False
    if age < FLAG_STALE_AFTER_S:
        return True
    # Left behind by a crash. Clear it rather than staying deaf.
    try:
        os.remove(SPEAKING_FLAG)
        log("cleared a leftover speaking flag")
    except OSError:
        pass
    return False


def hush():
    """Cut Claude off mid-sentence by killing whatever is playing the audio."""
    if IS_MAC:
        subprocess.run(["pkill", "-f", "afplay"], check=False)
    else:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             # The pattern is split so it can't match this command's own
             # command line - otherwise this kills itself instead of the player.
             "$me = $PID; $pat = 'Sound' + 'Player'; "
             "Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | "
             "Where-Object { $_.ProcessId -ne $me -and $_.CommandLine -like \"*$pat*\" } | "
             "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
            check=False, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    log("hushed")


# Windows lists the same headset under several driver types. WDM-KS can't do
# the kind of streaming we need at all ("Blocking API not supported yet"), so
# rank the usable ones and never pick that.
HOST_ORDER = ("MME", "Windows WASAPI", "Windows DirectSound", "Core Audio")


def pick_mic():
    if not MIC:
        return None
    hosts = sd.query_hostapis()

    def rank(host_name):
        return HOST_ORDER.index(host_name) if host_name in HOST_ORDER else len(HOST_ORDER)

    matches = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] < 1 or MIC.lower() not in d["name"].lower():
            continue
        host = hosts[d["hostapi"]]["name"]
        if host not in HOST_ORDER:
            continue  # unusable driver, e.g. WDM-KS
        matches.append((rank(host), i, d, host))

    if not matches:
        log(f"mic '{MIC}' not found - using the system default")
        return None
    matches.sort(key=lambda m: m[0])
    _, index, device, host = matches[0]
    log(f"mic: {device['name'].strip()[:34]} via {host} (device {index})")
    return index


def dictate(stream, vad):
    """Flow is recording. Watch for the end of the sentence, then stop it."""
    silence_ms = 0
    speech_ms = 0
    started = time.time()
    buffer = b""
    while time.time() - started < MAX_RECORD_S:
        block, _ = stream.read(CHUNK)
        buffer += bytes(block)
        while len(buffer) >= FRAME * 2:
            frame, buffer = buffer[: FRAME * 2], buffer[FRAME * 2 :]
            if vad.is_speech(frame, RATE):
                speech_ms += FRAME_MS
                silence_ms = 0
            else:
                silence_ms += FRAME_MS
        # Give yourself time to draw breath after the wake word, and never end
        # a take you haven't actually said anything into.
        if time.time() - started < GRACE_S or speech_ms < MIN_SPEECH_MS:
            continue
        if silence_ms >= SILENCE_MS:
            break
    finish()


def finish():
    """Stop Flow recording and send. Always runs, even if the mic just died."""
    toggle()
    # Flow needs a moment to transcribe and paste before Enter means anything.
    time.sleep(PASTE_WAIT_S)
    controller.tap(keyboard.Key.enter)
    log("submitted")


def main():
    model = Model(wakeword_models=[WAKE_MODEL])
    vad = webrtcvad.Vad(2)
    log(f"listening for '{WAKE_MODEL.replace('_', ' ')}'")

    with sd.RawInputStream(samplerate=RATE, blocksize=CHUNK, channels=1,
                           dtype="int16", device=pick_mic()) as stream:
        while True:
            block, _ = stream.read(CHUNK)
            samples = np.frombuffer(bytes(block), dtype=np.int16)

            scores = model.predict(samples)
            if scores.get(WAKE_MODEL, 0) < THRESHOLD:
                continue

            # Saying it while Claude is talking means "be quiet", not "listen".
            if claude_is_talking():
                hush()
                model.reset()
                time.sleep(COOLDOWN_S)
                continue

            log("woke up")
            model.reset()
            toggle()
            try:
                dictate(stream, vad)
            except Exception:
                # Never leave Flow recording into whatever window is focused.
                finish()
                raise

            # Throw away everything recorded during the take, or the wake word
            # still sitting in the buffer wakes it straight back up.
            time.sleep(COOLDOWN_S)
            stream.stop()
            stream.start()
            model.reset()


if __name__ == "__main__":
    # One instance only, or two copies fight over the shortcut.
    guard = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        guard.bind(("127.0.0.1", 5213))
    except OSError:
        log("already running - not starting a second one")
        sys.exit(0)
    try:
        main()
    except KeyboardInterrupt:
        log("stopped")
    except Exception:
        # Under pythonw there's no console, so without this a crash leaves no
        # trace at all and the whole thing just appears to stop working.
        import traceback
        log("crashed:\n" + traceback.format_exc())
        raise
