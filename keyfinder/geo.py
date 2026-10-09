"""The phone's position from GeoClue.

GeoClue ties a client to the D-Bus connection that created it, so everything
runs over one held connection. On Phosh the shell is GeoClue's agent and asks
the user for permission.
"""

import os

from gi.repository import Gio, GLib, GObject

GEOCLUE = "org.freedesktop.GeoClue2"
CLIENT = "org.freedesktop.GeoClue2.Client"
LOCATION = "org.freedesktop.GeoClue2.Location"
PROPS = "org.freedesktop.DBus.Properties"
DESKTOP_ID = "io.github.miscde.KeyFinder"
ACCURACY_EXACT = 8


def _bus_type():
    if os.environ.get("KEYFINDER_BUS") == "session":
        return Gio.BusType.SESSION
    return Gio.BusType.SYSTEM


class Locator(GObject.Object):
    """start() asks for positions until stop(); each one arrives as 'fix'."""

    __gsignals__ = {
        # latitude, longitude, accuracy in m
        "fix": (GObject.SignalFlags.RUN_FIRST, None, (float, float, float)),
        "failed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, bus=None):
        super().__init__()
        self.bus = bus or Gio.bus_get_sync(_bus_type(), None)
        self.client = None
        self.running = False
        self.sub = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.bus.call(GEOCLUE, "/org/freedesktop/GeoClue2/Manager",
                      "org.freedesktop.GeoClue2.Manager", "CreateClient", None,
                      GLib.VariantType("(o)"), Gio.DBusCallFlags.NONE, 20000, None,
                      self._got_client)

    def _fail(self, message):
        self.running = False
        self.emit("failed", message)

    def _got_client(self, bus, result):
        try:
            (self.client,) = bus.call_finish(result).unpack()
        except GLib.Error as e:
            return self._fail(e.message)
        if not self.running:      # stop() came in between
            self._delete(self.client)
            self.client = None
            return
        self.sub = bus.signal_subscribe(GEOCLUE, CLIENT, "LocationUpdated", self.client, None,
                                        Gio.DBusSignalFlags.NONE, self._on_location)
        try:
            for name, value in (("DesktopId", GLib.Variant("s", DESKTOP_ID)),
                                ("RequestedAccuracyLevel", GLib.Variant("u", ACCURACY_EXACT))):
                bus.call_sync(GEOCLUE, self.client, PROPS, "Set",
                              GLib.Variant("(ssv)", (CLIENT, name, value)),
                              None, Gio.DBusCallFlags.NONE, 5000, None)
        except GLib.Error as e:
            return self._fail(e.message)
        # Start may wait for the user's permission, hence asynchronous.
        bus.call(GEOCLUE, self.client, CLIENT, "Start", None, None,
                 Gio.DBusCallFlags.NONE, 120000, None, self._started)

    def _started(self, bus, result):
        try:
            bus.call_finish(result)
        except GLib.Error as e:
            self._fail(e.message)

    def _on_location(self, bus, _sender, _path, _iface, _signal, params):
        _old, new = params.unpack()
        try:
            values = {}
            for name in ("Latitude", "Longitude", "Accuracy"):
                (values[name],) = bus.call_sync(
                    GEOCLUE, new, PROPS, "Get", GLib.Variant("(ss)", (LOCATION, name)),
                    GLib.VariantType("(v)"), Gio.DBusCallFlags.NONE, 5000, None).unpack()
        except GLib.Error as e:
            print("keyfinder: reading position:", e.message, flush=True)
            return
        self.emit("fix", values["Latitude"], values["Longitude"], values["Accuracy"])

    def stop(self):
        self.running = False
        if self.sub is not None:
            self.bus.signal_unsubscribe(self.sub)
            self.sub = None
        if self.client:
            client = self.client
            self.client = None
            self.bus.call(GEOCLUE, client, CLIENT, "Stop", None, None,
                          Gio.DBusCallFlags.NONE, 5000, None,
                          lambda b, r: (_ignore(b, r), self._delete(client)))

    def _delete(self, client):
        self.bus.call(GEOCLUE, "/org/freedesktop/GeoClue2/Manager",
                      "org.freedesktop.GeoClue2.Manager", "DeleteClient",
                      GLib.Variant("(o)", (client,)), None, Gio.DBusCallFlags.NONE,
                      5000, None, _ignore)


def _ignore(bus, result):
    try:
        bus.call_finish(result)
    except GLib.Error:
        pass
