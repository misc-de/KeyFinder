"""Hintergrunddienst: merkt sich, wo die Tags mit „Standort merken“ zuletzt waren.

Jede Minute 10 s Bluetooth-Suche. GPS wird nur angefragt, wenn ein Tag
gerade in der Nähe ist und die letzte Ortung älter als 5 Minuten ist, oder
sofort, wenn ein Tag verschwunden ist – das ist die Position, die beim
Suchen zählt. Ohne Tags mit Option beendet sich der Dienst.
"""

import sys
import time

from gi.repository import GLib

from .locations import LocationStore
from .store import TagStore

SCAN_EVERY_S = 60
SCAN_FOR_S = 10
FIX_EVERY_S = 300
FIX_TIMEOUT_S = 120
GOOD_ENOUGH_M = 50


class Tracker:
    def __init__(self, bluez, locator, locations=None, tags_path=None, clock=time.time,
                 on_empty=None):
        self.bluez = bluez
        self.locator = locator
        self.locations = locations or LocationStore()
        self.tags_path = tags_path
        self.clock = clock
        self.on_empty = on_empty or (lambda: None)
        self.tracked = set()
        self.present = set()      # in der letzten Suche gesehen
        self.seen_now = {}        # in der laufenden Suche: Adresse -> RSSI
        self.waiting = set()      # bekommen die nächste Ortung
        self.best = None          # Genauigkeit der besten Ortung dieser Runde
        self.fix_timer = None
        bluez.connect("rssi", self._on_rssi)
        locator.connect("fix", self._on_fix)
        locator.connect("failed", self._on_failed)

    def reload_tags(self):
        store = TagStore(self.tags_path)
        self.tracked = {t["address"] for t in store.tags if t.get("track")}
        return self.tracked

    # --- eine Runde ----------------------------------------------------

    def begin_scan(self):
        self.locations.reload()
        if not self.reload_tags():
            self.on_empty()
            return False
        self.seen_now = {}
        self.bluez.start_discovery()
        return True

    def _on_rssi(self, _bluez, address, value):
        address = address.upper()
        if address in self.tracked:
            self.seen_now[address] = value
            self.locations.seen(address, value, self.clock())

    def end_scan(self):
        self.bluez.stop_discovery()
        now = self.clock()
        present = set(self.seen_now)
        lost = (self.present - present) & self.tracked
        stale = {a for a in present
                 if now - (self.locations.get(a) or {}).get("fix_time", 0) > FIX_EVERY_S}
        self.present = present
        if lost or stale:
            self.request_fix(lost | stale | present)
        self.locations.save()

    # --- Ortung --------------------------------------------------------

    def request_fix(self, addresses):
        self.waiting |= addresses
        if self.fix_timer is None:
            self.best = None
            self.locator.start()
            self.fix_timer = GLib.timeout_add_seconds(FIX_TIMEOUT_S, self._fix_timeout)

    def _on_fix(self, _locator, lat, lon, accuracy):
        if not self.waiting:
            return
        if self.best is None or accuracy < self.best:
            self.best = accuracy
            now = self.clock()
            for address in self.waiting:
                self.locations.fix(address, lat, lon, accuracy, now)
            self.locations.save()
        if accuracy <= GOOD_ENOUGH_M:
            self._finish_fix()

    def _on_failed(self, _locator, message):
        print("keyfinder-tracker: keine Ortung:", message, flush=True)
        self._finish_fix()

    def _fix_timeout(self):
        self.fix_timer = None   # Quelle endet mit return False
        self._finish_fix()
        return False

    def _finish_fix(self):
        if self.fix_timer is not None:
            GLib.source_remove(self.fix_timer)
            self.fix_timer = None
        self.waiting = set()
        self.locator.stop()


def claim_name():
    """Nur ein Dienst gleichzeitig (App-Start, Autostart, systemd)."""
    from gi.repository import Gio
    from .service import TRACKER_NAME
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    (reply,) = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
                             "org.freedesktop.DBus", "RequestName",
                             GLib.Variant("(su)", (TRACKER_NAME, 4)),   # DO_NOT_QUEUE
                             GLib.VariantType("(u)"), Gio.DBusCallFlags.NONE, 5000,
                             None).unpack()
    return reply == 1, bus      # bus festhalten, sonst geht der Name verloren


def main():
    from .bluez import BlueZ
    from .geo import Locator

    owner, _bus = claim_name()
    if not owner:
        print("keyfinder-tracker: läuft schon", flush=True)
        return 0
    loop = GLib.MainLoop()
    bluez = BlueZ()
    tracker = Tracker(bluez, Locator(), on_empty=loop.quit)

    def cycle():
        if tracker.begin_scan():
            GLib.timeout_add_seconds(SCAN_FOR_S, lambda: tracker.end_scan() and False)
        return True

    def quit_(*_args):
        tracker.locations.save()
        loop.quit()
        return False

    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 15, quit_)   # SIGTERM
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 2, quit_)    # SIGINT
    # Erste Runde, sobald BlueZ den Adapter gemeldet hat.
    GLib.timeout_add_seconds(2, lambda: cycle() and False)
    GLib.timeout_add_seconds(SCAN_EVERY_S, cycle)
    if not tracker.reload_tags():
        print("keyfinder-tracker: kein Tag mit „Standort merken“, nichts zu tun", flush=True)
        return 0
    loop.run()
    tracker.locator.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
