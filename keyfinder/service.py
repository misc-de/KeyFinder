"""Hintergrunddienst ein- oder ausschalten, abgeleitet aus den gespeicherten Tags.

Läuft genau dann, wenn mindestens ein Tag „Standort merken“ hat. Die App ruft
das nach jeder Änderung und beim Start auf, install.sh nach jedem Update,
damit der Zustand nie an einem Handgriff außerhalb der App hängt.

Zwei Wege: native Installation über eine systemd-User-Unit; im Flatpak (kein
systemctl in der Sandbox) über einen Autostart-Eintrag für die Anmeldung und
flatpak-spawn für sofort. Ausgeschaltet beendet sich der Dienst selbst, sobald
er keinen Tag mit Option mehr findet (spätestens nach einer Runde).
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
Name=Key Finder (Hintergrund)
Comment=Merkt sich, wo Tags mit „Standort merken“ zuletzt waren
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
    # Im Flatpak zeigt XDG_CONFIG_HOME in ~/.var/app; Autostart liest ~/.config.
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
    """Schaltet Autostart und startet den Dienst; liefert Fehler oder None."""
    path = autostart_file()
    try:
        if wanted(store):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(AUTOSTART_ENTRY)
            if not tracker_running():
                spawn = os.environ.get("KEYFINDER_SPAWN", "flatpak-spawn").split()
                # eigene Sandbox: überlebt das Schließen der App
                Gio.Subprocess.new(spawn + ["keyfinder", "--tracker"],
                                   Gio.SubprocessFlags.STDOUT_SILENCE
                                   | Gio.SubprocessFlags.STDERR_SILENCE)
        else:
            path.unlink(missing_ok=True)
    except (OSError, GLib.Error) as e:
        print("keyfinder: Hintergrunddienst:", e, flush=True)
        return str(e)
    return None


def systemctl():
    return os.environ.get("KEYFINDER_SYSTEMCTL", "systemctl")


def wanted(store):
    return any(t.get("track") for t in store.tags)


def command(store, restart=False):
    if wanted(store):
        if restart:   # liest die geänderte Tag-Liste sofort ein
            return [[systemctl(), "--user", "enable", UNIT],
                    [systemctl(), "--user", "restart", UNIT]]
        return [[systemctl(), "--user", "enable", "--now", UNIT]]
    return [[systemctl(), "--user", "disable", "--now", UNIT]]


def sync(store, callback=None, restart=False):
    """Asynchron (für die App); callback(error_or_None)."""
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
        except Exception as e:  # systemctl fehlt
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
                    callback((err or "").strip() or "systemctl fehlgeschlagen")
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
