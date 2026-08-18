"""A little icon in the taskbar to turn the voice on and off.

Green means it's listening, grey means it isn't. Click the icon for the menu.

Run:  pythonw tray.py
"""
import os
import platform
import socket
import subprocess
import sys
import threading
import time

import pystray
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
START = os.path.join(HERE, "start.py")
AUTOSTART = os.path.join(HERE, "autostart.py")
IS_MAC = platform.system() == "Darwin"

# wake.py holds this port while it's running, so it doubles as the on/off light.
WAKE_PORT = 5213

ON = (74, 222, 128)     # green
OFF = (120, 120, 128)   # grey


def listening():
    """Free port means nothing is listening."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", WAKE_PORT))
        return False
    except OSError:
        return True
    finally:
        probe.close()


def icon_image(colour):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # A microphone: rounded capsule on a stand.
    draw.rounded_rectangle((24, 10, 40, 38), radius=8, fill=colour)
    draw.arc((18, 26, 46, 48), start=0, end=180, fill=colour, width=5)
    draw.line((32, 46, 32, 54), fill=colour, width=5)
    draw.line((24, 54, 40, 54), fill=colour, width=5)
    return img


def run(script, *args):
    launcher = sys.executable
    if not IS_MAC:
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        launcher = pythonw if os.path.exists(pythonw) else sys.executable
    kwargs = {} if IS_MAC else {"creationflags": subprocess.CREATE_NO_WINDOW}
    subprocess.run([launcher, script, *args], check=False, **kwargs)


def toggle(icon, item):
    run(START, "--stop") if listening() else run(START)
    time.sleep(1.5)
    refresh(icon)


def autostart_on(icon, item):
    run(AUTOSTART)


def autostart_off(icon, item):
    run(AUTOSTART, "--off")


def quit_all(icon, item):
    run(START, "--stop")
    icon.stop()


def refresh(icon):
    on = listening()
    icon.icon = icon_image(ON if on else OFF)
    icon.title = "Jarvis: listening" if on else "Jarvis: off"


def watch(icon):
    """Keep the colour honest even if something else starts or stops it."""
    icon.visible = True
    while True:
        refresh(icon)
        time.sleep(3)


if __name__ == "__main__":
    tray = pystray.Icon(
        "jarvis",
        icon_image(ON if listening() else OFF),
        "Jarvis",
        menu=pystray.Menu(
            pystray.MenuItem(
                lambda item: "Turn off" if listening() else "Turn on",
                toggle, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start when I log in", autostart_on),
            pystray.MenuItem("Don't start when I log in", autostart_off),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", quit_all),
        ),
    )
    threading.Thread(target=watch, args=(tray,), daemon=True).start()
    tray.run()
