"""Switch the background service on or off, derived from the saved tags.

It runs exactly when at least one tag has "Remember location" on. The app
calls this on every change and at start, install.sh after every update, so
the state never depends on a manual step outside the app.

Two ways: a native install uses a systemd user unit; inside Flatpak (no
systemctl in the sandbox) an autostart entry for the next login plus
flatpak-spawn for right now. Switched off, the service ends by itself as soon
as it finds no tag with the option (after one round at the latest).
"""

import os
import subprocess
from pathlib import Path

from gi.repository import Gio, GLib

UNIT = "keyfinder-tracker.service"
TRACKER_NAME = "io.github.miscde.KeyFinder.Tracker"
APP_ID = "io.github.miscde.KeyFinder"
AUTOSTART_ENTRY = f"""[Desktop Entry]
Type=Application
Name=Key Finder (background)
Comment=Remembers where tags were last seen
Exec=flatpak run --command=keyfinder {APP_ID} --tracker
X-Flatpak={APP_ID}
NoDisplay=true
X-GNOME-Autostart-enabled=true
"""


def in_flatpak():
    if "KEYFINDER_FLATPAK" in os.environ:
        return os.environ["KEYFINDER_FLATPAK"] == "1"
    return os.path.exists("/.flatpak-info")


def autostart_file():
    # In Flatpak XDG_CONFIG_HOME points into ~/.var/app; autostart reads ~/.config.
    base = os.environ.get("KEYFINDER_AUTOSTART_DIR") or os.path.expanduser("~/.config/autostart")
    return Path(base) / f"{TRACKER_NAME}.desktop"


def tracker_running():
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        (owned,) = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
                                 "org.freedesktop.DBus", "NameHasOwner",
                                 GLib.Variant("(s)", (TRACKER_NAME,)), GLib.VariantType("(b)"),
                                 Gio.DBusCallFlags.NONE, 2000, None).unpack()
        return owned
    except GLib.Error:
        return False


def _sync_flatpak(store):
    """Switches autostart and starts the service; returns an error or None."""
    path = autostart_file()
    try:
        if wanted(store):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(AUTOSTART_ENTRY)
            if not tracker_running():
                spawn = os.environ.get("KEYFINDER_SPAWN", "flatpak-spawn").split()
                # its own sandbox: survives closing the app
                Gio.Subprocess.new(spawn + ["keyfinder", "--tracker"],
                                   Gio.SubprocessFlags.STDOUT_SILENCE
                                   | Gio.SubprocessFlags.STDERR_SILENCE)
        else:
            path.unlink(missing_ok=True)
    except (OSError, GLib.Error) as e:
        print("keyfinder: background service:", e, flush=True)
        return str(e)
    return None


def systemctl():
    return os.environ.get("KEYFINDER_SYSTEMCTL", "systemctl")


def wanted(store):
    return any(t.get("track") for t in store.tags)


def command(store, restart=False):
    if wanted(store):
        if restart:   # reads the changed tag list right away
            return [[systemctl(), "--user", "enable", UNIT],
                    [systemctl(), "--user", "restart", UNIT]]
        return [[systemctl(), "--user", "enable", "--now", UNIT]]
    return [[systemctl(), "--user", "disable", "--now", UNIT]]


def sync(store, callback=None, restart=False):
    """Asynchronous (for the app); callback(error_or_None)."""
    if in_flatpak():
        error = _sync_flatpak(store)
        if callback:
            GLib.idle_add(lambda: callback(error) and False)
        return
    steps = command(store, restart)

    def run(i):
        if i == len(steps):
            if callback:
                callback(None)
            return
        try:
            proc = Gio.Subprocess.new(steps[i], Gio.SubprocessFlags.STDOUT_SILENCE
                                      | Gio.SubprocessFlags.STDERR_PIPE)
        except Exception as e:  # no systemctl
            if callback:
                callback(str(e))
            return

        def done(p, result):
            try:
                _out, err = p.communicate_utf8_finish(result)
            except Exception as e:
                err = str(e)
            if p.get_exit_status() != 0:
                print("keyfinder:", " ".join(steps[i][1:]), "→", (err or "").strip(), flush=True)
                if callback:
                    callback((err or "").strip() or "systemctl failed")
                return
            run(i + 1)
        proc.communicate_utf8_async(None, None, done)
    run(0)


def sync_blocking(store, restart=False):
    if in_flatpak():
        return 1 if _sync_flatpak(store) else 0
    for step in command(store, restart):
        result = subprocess.run(step, capture_output=True, text=True)
        if result.returncode != 0:
            print("keyfinder:", " ".join(step[1:]), "→", result.stderr.strip())
            return 1
    return 0
