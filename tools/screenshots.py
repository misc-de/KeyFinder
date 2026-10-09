"""Erzeugt die README-Bilder mit erfundenen Tags (Aufruf über tools/screenshots.sh)."""

import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = sys.argv[1]
WORK = sys.argv[2]

TAGS = [  # 01–03 sendet das Fake-BlueZ, 04 bleibt fürs Anlernen frei, 05–07 sind weg
    ("AA:00:00:00:00:01", "Haustür", "schluessel", True),
    ("AA:00:00:00:00:07", "Autoschlüssel", "auto", True),
    ("AA:00:00:00:00:03", "Rucksack", "rucksack", False),
    ("AA:00:00:00:00:02", "Geldbörse", "geldboerse", False),
    ("AA:00:00:00:00:05", "Fahrrad", "fahrrad", False),
    ("AA:00:00:00:00:06", "Hund Bello", "hund", False),
]
os.makedirs(os.path.dirname(os.environ["KEYFINDER_CONFIG"]), exist_ok=True)
with open(os.environ["KEYFINDER_CONFIG"], "w") as f:
    json.dump({"tags": [{"address": a, "name": n, "category": c, "track": t}
                        for a, n, c, t in TAGS]}, f)
os.makedirs(os.environ["KEYFINDER_DATA"], exist_ok=True)
now = time.time()
with open(os.path.join(os.environ["KEYFINDER_DATA"], "locations.json"), "w") as f:
    json.dump({"AA:00:00:00:00:01": {"seen": now - 1500, "rssi": -72, "lat": 50.94130,
                                     "lon": 6.95828, "accuracy": 25, "fix_time": now - 1440}}, f)

fake = subprocess.Popen([sys.executable, os.path.join(ROOT, "tests", "fake_bluez.py"),
                         os.path.join(WORK, "fake.log")], stdout=subprocess.PIPE, text=True)
assert "ready" in fake.stdout.readline()

import gi  # noqa: E402
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Graphene, Gsk, Gtk  # noqa: E402
from keyfinder import app as kapp, rssi  # noqa: E402


def run(sec):
    ctx = GLib.MainContext.default()
    end = time.monotonic() + sec
    while time.monotonic() < end:
        ctx.iteration(False)
        time.sleep(0.01)


def shot(win, name, tries=40):
    w, h = win.get_width(), win.get_height()
    snap = Gtk.Snapshot()
    Gtk.WidgetPaintable(widget=win).snapshot(snap, w, h)
    node = snap.to_node()
    if node is None:
        if not tries:
            sys.exit(f"{name}: kein Bild")
        run(0.25)
        return shot(win, name, tries - 1)
    r = Gsk.CairoRenderer()
    r.realize(None)
    r.render_texture(node, Graphene.Rect().init(0, 0, w, h)).save_to_png(
        os.path.join(OUT, name + ".png"))
    r.unrealize()
    print("  ", name, flush=True)


def steps(a):
    Gtk.Settings.get_default().props.gtk_decoration_layout = ""   # Phone: keine Fensterknöpfe
    win = a.get_active_window()
    win.set_default_size(360, 720)
    run(3)
    shot(win, "tags")

    win.open_detail("AA:00:00:00:00:01")
    win.tracker.trend = lambda _a: rssi.WARMER     # Momentaufnahme beim Näherkommen
    run(1.5)
    shot(win, "search")

    win.open_map("AA:00:00:00:00:01")
    run(8)                                         # Kacheln laden
    shot(win, "map")
    win.nav.pop_to_tag("main")
    run(1)

    win.open_learn()
    run(2.5)
    row = next(iter(win.learn.values()))
    win._learn_pick(row)
    run(1)
    dialog = win.get_visible_dialog()
    dialog.get_extra_child().get_first_child().set_text("Fahrradschloss")
    run(1.5)
    shot(win, "learn")
    dialog.force_close()
    win.close()
    run(0.5)
    a.quit()


application = kapp.App()
application.connect("activate", lambda a: GLib.idle_add(lambda: steps(a) and False))
application.run([])
fake.terminate()
