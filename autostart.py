"""Makes the voice come back on its own after a reboot.

Windows: a shortcut in the Startup folder.
Mac: a LaunchAgent plist.

Run:  python autostart.py            turn it on
      python autostart.py --off      turn it off
"""
import os
import platform
import subprocess
import sys

VOICE = os.path.join(os.path.expanduser("~"), ".claude", "voice")
START = os.path.join(VOICE, "start.py")
IS_MAC = platform.system() == "Darwin"

LABEL = "com.zentara.jarvisvoice"
PLIST = os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents", LABEL + ".plist")
STARTUP = os.path.join(os.environ.get("APPDATA", ""),
                       "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
SHORTCUT = os.path.join(STARTUP, "Jarvis Voice.lnk")


def enable_mac():
    os.makedirs(os.path.dirname(PLIST), exist_ok=True)
    with open(PLIST, "w", encoding="utf-8") as fh:
        fh.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array><string>{sys.executable}</string><string>{START}</string></array>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
""")
    subprocess.run(["launchctl", "unload", PLIST], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["launchctl", "load", PLIST], check=False)
    print(f"on. it'll start itself at login.\n  {PLIST}")


def disable_mac():
    subprocess.run(["launchctl", "unload", PLIST], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.exists(PLIST):
        os.remove(PLIST)
    print("off. it won't start itself any more.")


def enable_windows():
    # pythonw so no console window appears at login.
    launcher = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{SHORTCUT}');"
          f"$s.TargetPath='{launcher}';"
          f"$s.Arguments='\"{START}\"';"
          f"$s.WorkingDirectory='{VOICE}';"
          f"$s.Description='Jarvis voice for Claude Code';"
          f"$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    print(f"on. it'll start itself at login.\n  {SHORTCUT}")


def disable_windows():
    if os.path.exists(SHORTCUT):
        os.remove(SHORTCUT)
    print("off. it won't start itself any more.")


if __name__ == "__main__":
    off = "--off" in sys.argv
    if IS_MAC:
        disable_mac() if off else enable_mac()
    else:
        disable_windows() if off else enable_windows()
