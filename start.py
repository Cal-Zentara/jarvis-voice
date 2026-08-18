"""Starts the voice server and the wake word listener, stopping old copies first.

Run:  python start.py            turn listening on
      python start.py --stop     turn listening off
      python start.py --quit     off, and close the taskbar icon too

The taskbar icon is deliberately left alone by --stop: it's the thing you use to
turn listening back on, so killing it would strand you.
"""
import os
import platform
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
VOICE_PARTS = ("server.py", "wake.py")
TRAY = "tray.py"
IS_MAC = platform.system() == "Darwin"


def kill(name):
    if IS_MAC:
        subprocess.run(["pkill", "-f", name], check=False)
        return
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
         f"Where-Object {{ $_.CommandLine -like '*{name}*' }} | "
         "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
        check=False,
    )


def launch(name):
    path = os.path.join(HERE, name)
    if IS_MAC:
        # No pythonw on macOS, so detach and throw the output away.
        subprocess.Popen([sys.executable, path],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return
    launcher = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    subprocess.Popen([launcher, path], creationflags=subprocess.CREATE_NO_WINDOW)


def running(name):
    if IS_MAC:
        return subprocess.run(["pgrep", "-f", name], check=False,
                              stdout=subprocess.DEVNULL).returncode == 0
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
         f"Where-Object {{ $_.CommandLine -like '*{name}*' }} | Measure-Object | "
         "Select-Object -ExpandProperty Count"],
        check=False, capture_output=True, text=True).stdout.strip()
    return out.isdigit() and int(out) > 0


MUTED = os.path.join(HERE, "muted")


def stop(include_tray=False):
    # Tells the Claude Code hook not to start the server back up on the next
    # reply. Without this, turning it "off" only lasts until Claude speaks.
    open(MUTED, "w").close()
    for name in VOICE_PARTS:
        kill(name)
    if include_tray:
        kill(TRAY)
    print("stopped")


def start():
    stop()
    try:
        os.remove(MUTED)
    except OSError:
        pass
    time.sleep(1)
    for name in VOICE_PARTS:
        launch(name)
    if not running(TRAY):
        launch(TRAY)
    print("running. say 'hey Jarvis' and talk.")


if __name__ == "__main__":
    if "--quit" in sys.argv:
        stop(include_tray=True)
    elif "--stop" in sys.argv:
        stop()
    else:
        start()
