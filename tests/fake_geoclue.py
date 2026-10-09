"""Minimales GeoClue2 für Tests auf dem Session-Bus.

Aufruf: python3 fake_geoclue.py <logdatei> <lat> <lon> <genauigkeit>[,<genauigkeit>…]
Nach Start liefert der Client nacheinander Positionen mit den angegebenen
Genauigkeiten (alle 100 ms). Aufrufe landen als JSON-Zeilen im Log.
"""

import json
import sys

from gi.repository import Gio, GLib

XML = """
<node>
  <interface name="org.freedesktop.GeoClue2.Manager">
    <method name="CreateClient"><arg type="o" direction="out"/></method>
    <method name="DeleteClient"><arg type="o" direction="in"/></method>
  </interface>
  <interface name="org.freedesktop.GeoClue2.Client">
    <property name="DesktopId" type="s" access="readwrite"/>
    <property name="RequestedAccuracyLevel" type="u" access="readwrite"/>
    <method name="Start"/><method name="Stop"/>
    <signal name="LocationUpdated"><arg type="o"/><arg type="o"/></signal>
  </interface>
  <interface name="org.freedesktop.GeoClue2.Location">
    <property name="Latitude" type="d" access="read"/>
    <property name="Longitude" type="d" access="read"/>
    <property name="Accuracy" type="d" access="read"/>
  </interface>
</node>
"""


class Fake:
    def __init__(self, log, lat, lon, accuracies):
        self.log = open(log, "a", buffering=1)
        self.lat, self.lon, self.accuracies = lat, lon, accuracies
        self.node = Gio.DBusNodeInfo.new_for_xml(XML)
        self.n = 0
        self.props = {}
        self.timers = {}
        self.bus = None

    def write(self, **e):
        self.log.write(json.dumps(e) + "\n")

    def iface(self, name):
        return self.node.lookup_interface(name)

    def setup(self, bus):
        self.bus = bus
        bus.register_object("/org/freedesktop/GeoClue2/Manager",
                            self.iface("org.freedesktop.GeoClue2.Manager"), self.call, None, None)

    def call(self, _c, _s, path, _i, method, params, inv):
        self.write(op=method, path=path)
        if method == "CreateClient":
            self.n += 1
            cpath = f"/org/freedesktop/GeoClue2/Client/{self.n}"
            self.props[cpath] = {}
            self.bus.register_object(cpath, self.iface("org.freedesktop.GeoClue2.Client"),
                                     self.call, self.get, self.set)
            return inv.return_value(GLib.Variant("(o)", (cpath,)))
        if method == "Start":
            if self.props[path].get("DesktopId") != "io.github.miscde.KeyFinder":
                return inv.return_dbus_error("org.freedesktop.DBus.Error.AccessDenied", "no id")
            queue = list(self.accuracies)
            self.timers[path] = GLib.timeout_add(100, self.emit_location, path, queue)
        if method == "Stop" and path in self.timers:
            GLib.source_remove(self.timers.pop(path))
        inv.return_value(None)

    def get(self, _c, _s, path, iface, name):
        return self.props[path][name]

    def set(self, _c, _s, path, _iface, name, value):
        self.write(op="set", name=name, value=value.unpack())
        self.props[path][name] = value.unpack()
        return True

    def emit_location(self, cpath, queue):
        if not queue:
            self.timers.pop(cpath, None)
            return False
        accuracy = queue.pop(0)
        self.n += 1
        lpath = f"/org/freedesktop/GeoClue2/Location/{self.n}"
        self.props[lpath] = {"Latitude": GLib.Variant("d", self.lat),
                             "Longitude": GLib.Variant("d", self.lon),
                             "Accuracy": GLib.Variant("d", accuracy)}
        self.bus.register_object(lpath, self.iface("org.freedesktop.GeoClue2.Location"),
                                 self.call, self.get, None)
        self.bus.emit_signal(None, cpath, "org.freedesktop.GeoClue2.Client", "LocationUpdated",
                             GLib.Variant("(oo)", ("/", lpath)))
        return True


def main():
    log, lat, lon, accs = sys.argv[1:5]
    fake = Fake(log, float(lat), float(lon), [float(a) for a in accs.split(",")])
    loop = GLib.MainLoop()
    Gio.bus_own_name(Gio.BusType.SESSION, "org.freedesktop.GeoClue2", Gio.BusNameOwnerFlags.NONE,
                     lambda bus, _n: fake.setup(bus),
                     lambda _b, _n: print("fake_geoclue: ready", flush=True),
                     lambda _b, _n: loop.quit())
    loop.run()


if __name__ == "__main__":
    main()
