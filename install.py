"""One-shot installer for the Jarvis voice setup.

Installs the Python bits, downloads the voice models, copies everything into
~/.claude, wires the speak-out-loud hook, and starts listening.

Run:  python install.py
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE = os.path.join(os.path.expanduser("~"), ".claude")
VOICE = os.path.join(CLAUDE, "voice")
HOOKS = os.path.join(CLAUDE, "hooks")
SETTINGS = os.path.join(CLAUDE, "settings.json")

PACKAGES = [
    "kokoro-onnx", "soundfile", "sounddevice",
    # webrtcvad-wheels, not webrtcvad: the original builds from source and
    # wants Visual C++ Build Tools, which nobody has by default.
    "webrtcvad-wheels",
    "openwakeword", "pynput", "numpy",
    # the on/off icon in the taskbar (menu bar on Mac)
    "pystray", "pillow",
]
IS_MAC = platform.system() == "Darwin"
# name -> (url, smallest size that could possibly be the real file)
MODELS = {
    "kokoro-v1.0.onnx": (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
        300_000_000),
    "voices-v1.0.bin": (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
        25_000_000),
}


def say(msg):
    print(f"  {msg}", flush=True)


def step(n, msg):
    print(f"\n[{n}/6] {msg}", flush=True)


def download(name, url, dest, expect_min):
    """Download to a .part file, then rename. Never leave a half file in place.

    The old version wrote straight to the real name, so a dropped connection
    left a truncated model that every later run happily skipped as "already
    here" - and the voice then died with no message at all.
    """
    path = os.path.join(dest, name)
    part = path + ".part"
    if os.path.exists(path) and os.path.getsize(path) >= expect_min:
        say(f"{name} already here")
        return
    say(f"downloading {name} - a few minutes, please leave it running")
    try:
        urllib.request.urlretrieve(url, part)
        if os.path.getsize(part) < expect_min:
            raise OSError(f"only got {os.path.getsize(part):,} bytes")
        os.replace(part, path)
    except Exception as err:
        for leftover in (part, path):
            try:
                os.remove(leftover)
            except OSError:
                pass
        say(f"download failed ({err})")
        say("Check your internet and run this again - nothing is half-written.")
        sys.exit(1)


# Words that appear in half the devices on a machine and identify nothing.
VAGUE = {"microphone", "mic", "input", "output", "audio", "sound", "device",
         "headset", "speakers", "default", "built-in", "external", "array"}


def mic_fragment(name):
    """The most identifying word in a device name, for matching it again later.

    Windows writes Bluetooth device names with backslashes, percent signs and
    even line breaks in them, so pull out only real words and prefer one that
    isn't shared by every device on the machine.
    """
    words = re.findall(r"[A-Za-z0-9-]{3,}", name.splitlines()[0])
    useful = [w for w in words if w.lower() not in VAGUE]
    return max(useful or words, key=len, default="")


def choose_mic():
    """Ask which microphone to listen on and write it into the installed wake.py.

    The system default is often not the headset - a USB audio interface or a
    webcam usually wins - so asking beats assuming.
    """
    import sounddevice as sd

    mics = [(i, d["name"].strip()) for i, d in enumerate(sd.query_devices())
            if d["max_input_channels"] > 0]
    if not mics:
        say("no microphones found - leaving it on the system default")
        return

    print("\n  Which microphone will you talk into?\n")
    for n, (_, name) in enumerate(mics, start=1):
        print(f"    {n}. {name}")
    print("    0. Just use the system default\n")

    try:
        picked = int(input("  Number: ").strip() or "0")
    except ValueError:
        picked = 0
    if not 1 <= picked <= len(mics):
        say("using the system default")
        return

    name = mics[picked - 1][1]
    fragment = mic_fragment(name)
    if not fragment:
        say("couldn't read that device's name - using the system default")
        return

    path = os.path.join(VOICE, "wake.py")
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    # repr() so quotes and backslashes survive; a lambda replacement so re.sub
    # never tries to interpret backslashes in the device name as group refs.
    line = f"MIC = {fragment!r}  # matches: {name.splitlines()[0][:40]}"
    source = re.sub(r"^MIC = .*$", lambda _: line, source, count=1, flags=re.M)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(source)
    say(f"listening on: {name.splitlines()[0][:40]}")


def choose_voice():
    """Offer the paid voice. The key is typed here and written straight to disk."""
    key_file = os.path.join(VOICE, "elevenlabs.key")
    if os.path.exists(key_file):
        say("ElevenLabs key already saved - leaving it alone")
        return

    print("\n  Which voice should Claude answer in?\n")
    print("    1. Free - runs on this computer, costs nothing, sounds good")
    print("    2. ElevenLabs - sounds more human, charges per message\n")
    if (input("  Number: ").strip() or "1") != "2":
        say("using the free voice")
        return

    print("\n  Paste your ElevenLabs API key.")
    print("  Find it at elevenlabs.io under Developers, then API Keys.\n")
    key = input("  Key: ").strip()
    if not key:
        say("nothing entered - staying on the free voice")
        return
    with open(key_file, "w", encoding="utf-8") as fh:
        fh.write(key)
    os.chmod(key_file, 0o600)
    say("ElevenLabs it is - the key is saved locally and never leaves this machine")


def turn_on_at_login():
    """Otherwise the first reboot quietly kills it and nobody knows why."""
    try:
        subprocess.run([sys.executable, os.path.join(VOICE, "autostart.py")], check=True)
    except subprocess.CalledProcessError:
        say("couldn't set it to start at login - run autostart.py yourself later")


def check_node():
    """The speaking hook runs under Node. Without it Claude is silent, with no
    error the user would ever see, so say so now rather than never."""
    if shutil.which("node"):
        return True
    say("Node.js isn't installed, so Claude won't be able to speak.")
    say("Get it from nodejs.org, then run this again.")
    say("Carrying on - the listening half will still work.")
    return False


def main():
    has_node = check_node()

    step(1, "Installing the Python pieces")
    pip = [sys.executable, "-m", "pip", "install", "-q"]
    if subprocess.run(pip + PACKAGES, check=False).returncode:
        # Most Macs ship a "managed" Python that refuses plain installs, and a
        # system-wide Windows Python refuses without admin. Both want --user.
        say("retrying as a personal install")
        if subprocess.run(pip + ["--user", "--break-system-packages"] + PACKAGES,
                          check=False).returncode:
            say("couldn't install the Python pieces.")
            say("Install Python from python.org, then run this again.")
            sys.exit(1)
        # pip may have created a folder this process never saw, so make the
        # imports further down actually find it.
        import importlib
        import site
        site.main()
        importlib.invalidate_caches()
    say("done")

    step(2, "Copying the voice files into ~/.claude")
    os.makedirs(VOICE, exist_ok=True)
    os.makedirs(HOOKS, exist_ok=True)
    for name in ("server.py", "wake.py", "speak.py", "start.py",
                 "autostart.py", "tray.py"):
        shutil.copy2(os.path.join(HERE, name), os.path.join(VOICE, name))
    shutil.copy2(os.path.join(HERE, "speak-reply.mjs"), os.path.join(HOOKS, "speak-reply.mjs"))
    # The hook needs the interpreter that actually has the packages, which is
    # often not the plain "python3" it would otherwise find on PATH.
    launcher = sys.executable
    if not IS_MAC:
        windowless = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.exists(windowless):
            launcher = windowless
    with open(os.path.join(VOICE, "python-path"), "w", encoding="utf-8") as fh:
        fh.write(launcher)
    say(VOICE)

    choose_mic()
    choose_voice()
    turn_on_at_login()

    step(3, "Downloading the voice model (about 350MB)")
    for name, (url, expect_min) in MODELS.items():
        download(name, url, VOICE, expect_min)

    step(4, "Downloading the wake word model")
    import openwakeword.utils
    try:
        openwakeword.utils.download_models()
    except Exception as err:
        say(f"couldn't download the wake word model ({err}) - run this again")
        sys.exit(1)
    say("'hey jarvis' is ready")

    step(5, "Wiring the speak-out-loud hook")
    settings = {}
    if os.path.exists(SETTINGS):
        # utf-8-sig because a settings file saved by Notepad carries a BOM,
        # which plain utf-8 chokes on. A broken file shouldn't stop the install.
        try:
            with open(SETTINGS, encoding="utf-8-sig") as fh:
                text = fh.read().strip()
            settings = json.loads(text) if text else {}
        except (json.JSONDecodeError, OSError) as err:
            say(f"couldn't read settings.json ({err})")
            say("Fix or delete that file, then run this again. Nothing was changed.")
            sys.exit(1)
    hooks = settings.setdefault("hooks", {})
    stop = hooks.setdefault("Stop", [])
    already = any("speak-reply" in json.dumps(entry) for entry in stop)
    if not already:
        stop.append({"hooks": [{
            "type": "command",
            "command": "node ~/.claude/hooks/speak-reply.mjs",
            "timeout": 30,
            "statusMessage": "Speaking...",
        }]})
        # Write beside it and rename, so an interrupted install can never leave
        # a half-written settings.json that stops Claude Code from starting.
        temp = SETTINGS + ".new"
        with open(temp, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
        os.replace(temp, SETTINGS)
        say("hook added")
    else:
        say("hook was already there")

    step(6, "Starting it up")
    subprocess.run([sys.executable, os.path.join(VOICE, "start.py")], check=False)

    print("\nInstalled.\n")
    python_cmd = "python3" if IS_MAC else "python"
    print(f'To start it again later:  {python_cmd} "{os.path.join(VOICE, "start.py")}"')
    print("Say 'hey Jarvis' and talk. Say it again to cut Claude off.\n")
    print("Restart Claude Code once, so it picks up the speaking hook.\n")
    if IS_MAC:
        print("You also need Wispr Flow running. One setting to change: open Flow,")
        print("go to Settings, and set its shortcut to Ctrl+Option+Space.")
        print("Flow's default is the Fn key, which no software can press.\n")
    else:
        print("You also need Wispr Flow running, with its shortcut left on Ctrl+Win.\n")
    where = "the menu bar" if IS_MAC else "the taskbar, under the ^ arrow"
    print(f"A microphone icon sits in {where}. Green means it's listening;")
    print("click it to turn the whole thing on or off.\n")
    if IS_MAC:
        print("First run only: macOS asks for Microphone and Accessibility")
        print("permission. Say yes to both, or it can't hear you or press keys.\n")


if __name__ == "__main__":
    main()
