"""BlueZ over D-Bus (Gio), no extra Python packages.

The main thread keeps a mirror of BlueZ's objects (GetManagedObjects plus
signals). Connecting and GATT writes run in a helper thread with synchronous
calls; the result comes back through GLib.idle_add.
"""

import os
import threading
import time

from gi.repository import Gio, GLib, GObject

from .i18n import _

BLUEZ = "org.bluez"
ADAPTER = "org.bluez.Adapter1"
DEVICE = "org.bluez.Device1"
SERVICE = "org.bluez.GattService1"
CHAR = "org.bluez.GattCharacteristic1"
PROPS = "org.freedesktop.DBus.Properties"
OBJMGR = "org.freedesktop.DBus.ObjectManager"


def uuid16(value):
    return f"0000{value:04x}-0000-1000-8000-00805f9b34fb"


IMMEDIATE_ALERT = uuid16(0x1802)
LINK_LOSS = uuid16(0x1803)
ALERT_LEVEL = uuid16(0x2A06)
ITAG_SERVICE = uuid16(0xFFE0)

CONNECT_TIMEOUT_MS = 25000
RESOLVE_TIMEOUT_S = 15.0


class BeepError(Exception):
    pass


def _bus_type():
    if os.environ.get("KEYFINDER_BUS") == "session":
        return Gio.BusType.SESSION
    return Gio.BusType.SYSTEM


def find_alert_chars(objects, device_path):
    """Returns (immediate_alert_char, link_loss_char) below the device."""
    services = {}
    for path, ifaces in objects.items():
        if SERVICE in ifaces and path.startswith(device_path + "/"):
            services[path] = ifaces[SERVICE].get("UUID", "").lower()
    immediate = link_loss = None
    for path, ifaces in sorted(objects.items()):
        char = ifaces.get(CHAR)
        if not char or char.get("UUID", "").lower() != ALERT_LEVEL:
            continue
        service_uuid = services.get(char.get("Service", ""))
        if service_uuid == IMMEDIATE_ALERT and immediate is None:
            immediate = path
        elif service_uuid == LINK_LOSS and link_loss is None:
            link_loss = path
    return immediate, link_loss


class BlueZ(GObject.Object):
    __gsignals__ = {
        # adapter found, switched on or off
        "adapter-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        # device new, changed or gone (address)
        "device-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        # new signal value (address, dBm)
        "rssi": (GObject.SignalFlags.RUN_FIRST, None, (str, int)),
    }

    def __init__(self):
        super().__init__()
        self.objects = {}
        self.adapter_path = None
        self.ready = False     # meaningful only after BlueZ's first answer
        self.discovering_wanted = False
        self.bus = Gio.bus_get_sync(_bus_type(), None)
        self.bus.signal_subscribe(BLUEZ, OBJMGR, "InterfacesAdded", None, None,
                                  Gio.DBusSignalFlags.NONE, self._on_added)
        self.bus.signal_subscribe(BLUEZ, OBJMGR, "InterfacesRemoved", None, None,
                                  Gio.DBusSignalFlags.NONE, self._on_removed)
        self.bus.signal_subscribe(BLUEZ, PROPS, "PropertiesChanged", None, None,
                                  Gio.DBusSignalFlags.NONE, self._on_props)
        Gio.bus_watch_name_on_connection(self.bus, BLUEZ, Gio.BusNameWatcherFlags.NONE,
                                         self._on_bluez_appeared, self._on_bluez_vanished)

    # --- mirror of BlueZ's objects --------------------------------------

    def _on_bluez_appeared(self, _conn, _name, _owner):
        self.bus.call(BLUEZ, "/", OBJMGR, "GetManagedObjects", None,
                      GLib.VariantType("(a{oa{sa{sv}}})"), Gio.DBusCallFlags.NONE,
                      -1, None, self._on_managed_objects)

    def _on_bluez_vanished(self, _conn, _name):
        self.ready = True
        self.objects = {}
        self.adapter_path = None
        self.emit("adapter-changed")

    def _on_managed_objects(self, bus, result):
        try:
            (objects,) = bus.call_finish(result).unpack()
        except GLib.Error as e:
            print("keyfinder: GetManagedObjects:", e.message)
            return
        self.objects = objects
        self.ready = True
        self._pick_adapter()
        for path, ifaces in objects.items():
            if DEVICE in ifaces:
                self._device_touched(path, ifaces[DEVICE])

    def _pick_adapter(self):
        adapters = sorted(p for p, i in self.objects.items() if ADAPTER in i)
        new = adapters[0] if adapters else None
        if new != self.adapter_path:
            self.adapter_path = new
            if new and self.discovering_wanted:
                self.start_discovery()
        self.emit("adapter-changed")

    def _on_added(self, _c, _s, _p, _i, _sig, params):
        path, ifaces = params.unpack()
        self.objects.setdefault(path, {}).update(ifaces)
        if ADAPTER in ifaces:
            self._pick_adapter()
        if DEVICE in ifaces:
            self._device_touched(path, ifaces[DEVICE])

    def _on_removed(self, _c, _s, _p, _i, _sig, params):
        path, ifaces = params.unpack()
        entry = self.objects.get(path, {})
        address = entry.get(DEVICE, {}).get("Address")
        for iface in ifaces:
            entry.pop(iface, None)
        if not entry:
            self.objects.pop(path, None)
        if ADAPTER in ifaces:
            self._pick_adapter()
        if address and DEVICE in ifaces:
            self.emit("device-changed", address)

    def _on_props(self, _c, _s, path, _i, _sig, params):
        iface, changed, invalidated = params.unpack()
        entry = self.objects.get(path)
        if entry is None or iface not in entry:
            return
        entry[iface].update(changed)
        for name in invalidated:
            entry[iface].pop(name, None)
        if iface == ADAPTER and path == self.adapter_path:
            self.emit("adapter-changed")
        elif iface == DEVICE:
            self._device_touched(path, changed)

    def _device_touched(self, path, changed):
        address = self.objects.get(path, {}).get(DEVICE, {}).get("Address")
        if not address:
            return
        if "RSSI" in changed:
            self.emit("rssi", address, int(changed["RSSI"]))
        self.emit("device-changed", address)

    # --- queries --------------------------------------------------------

    @property
    def powered(self):
        if not self.adapter_path:
            return False
        return bool(self.objects[self.adapter_path][ADAPTER].get("Powered"))

    def devices(self):
        """All known devices of this adapter as a list of dicts."""
        result = []
        for path, ifaces in self.objects.items():
            dev = ifaces.get(DEVICE)
            if not dev or dev.get("Adapter") != self.adapter_path:
                continue
            result.append({
                "path": path,
                "address": dev.get("Address", ""),
                "name": dev.get("Alias") or dev.get("Name") or "",
                "has_name": "Name" in dev,
                "rssi": dev.get("RSSI"),
                "uuids": [u.lower() for u in dev.get("UUIDs", [])],
                "connected": bool(dev.get("Connected")),
            })
        return result

    def device(self, address):
        for dev in self.devices():
            if dev["address"].upper() == address.upper():
                return dev
        return None

    # --- Adapter -------------------------------------------------------

    def power_on(self, callback=None):
        if not self.adapter_path:
            return
        self.bus.call(BLUEZ, self.adapter_path, PROPS, "Set",
                      GLib.Variant("(ssv)", (ADAPTER, "Powered", GLib.Variant("b", True))),
                      None, Gio.DBusCallFlags.NONE, -1, None,
                      lambda bus, res: self._finish(bus, res, "Power on", callback))

    def start_discovery(self):
        self.discovering_wanted = True
        if not self.adapter_path:
            return
        # With a filter set BlueZ reports every RSSI change (otherwise only from 8 dB).
        flt = {"Transport": GLib.Variant("s", "le"),
               "DuplicateData": GLib.Variant("b", True)}
        self.bus.call(BLUEZ, self.adapter_path, ADAPTER, "SetDiscoveryFilter",
                      GLib.Variant("(a{sv})", (flt,)), None, Gio.DBusCallFlags.NONE,
                      -1, None, self._after_filter)

    def _after_filter(self, bus, result):
        self._finish(bus, result, "SetDiscoveryFilter")
        if self.adapter_path and self.discovering_wanted:
            self.bus.call(BLUEZ, self.adapter_path, ADAPTER, "StartDiscovery", None, None,
                          Gio.DBusCallFlags.NONE, -1, None,
                          lambda b, r: self._finish(b, r, "StartDiscovery"))

    def stop_discovery(self):
        self.discovering_wanted = False
        if self.adapter_path:
            self.bus.call(BLUEZ, self.adapter_path, ADAPTER, "StopDiscovery", None, None,
                          Gio.DBusCallFlags.NONE, -1, None,
                          lambda b, r: self._finish(b, r, "StopDiscovery"))

    @staticmethod
    def _finish(bus, result, what, callback=None):
        error = None
        try:
            bus.call_finish(result)
        except GLib.Error as e:
            if "InProgress" not in e.message and "NotReady" not in e.message:
                print(f"keyfinder: {what}: {e.message}")
            error = e.message
        if callback:
            callback(error)

    # --- beeping (helper thread) ----------------------------------------

    def beep(self, address, level, callback, disconnect=False):
        """level 0 = off, 1 = mild, 2 = high. callback(error_or_None) in the main thread."""
        def worker():
            try:
                self._beep_sync(address, level, disconnect)
                error = None
            except BeepError as e:
                error = str(e)
            except GLib.Error as e:
                error = _friendly(e.message)
            if error:
                self._disconnect_sync(address)
            GLib.idle_add(callback, error)
        threading.Thread(target=worker, daemon=True).start()

    def beep_off_sync(self, address):
        try:
            self._beep_sync(address, 0, True)
        except (BeepError, GLib.Error):
            self._disconnect_sync(address)

    def _disconnect_sync(self, address):
        try:
            for path, ifaces in self._managed().items():
                dev = ifaces.get(DEVICE)
                if dev and dev.get("Connected") and dev.get("Address", "").upper() == address.upper():
                    self._call(path, DEVICE, "Disconnect")
        except GLib.Error:
            pass

    def _call(self, path, iface, method, args=None, reply=None, timeout=-1):
        return self.bus.call_sync(BLUEZ, path, iface, method, args,
                                  GLib.VariantType(reply) if reply else None,
                                  Gio.DBusCallFlags.NONE, timeout, None)

    def _managed(self):
        (objects,) = self._call("/", OBJMGR, "GetManagedObjects",
                                reply="(a{oa{sa{sv}}})").unpack()
        return objects

    def _device_prop(self, path, name):
        try:
            (value,) = self._call(path, PROPS, "Get", GLib.Variant("(ss)", (DEVICE, name)),
                                  reply="(v)").unpack()
            return value
        except GLib.Error:
            return None

    def _beep_sync(self, address, level, disconnect):
        objects = self._managed()
        path = None
        for p, ifaces in objects.items():
            dev = ifaces.get(DEVICE)
            if dev and dev.get("Address", "").upper() == address.upper():
                path = p
                break
        if path is None:
            raise BeepError(_("The tag is out of range right now."))
        if level == 0 and not objects[path][DEVICE].get("Connected"):
            return  # not connected = not beeping (link loss is switched off)

        if not objects[path][DEVICE].get("Connected"):
            try:
                self._call(path, DEVICE, "Connect", timeout=CONNECT_TIMEOUT_MS)
            except GLib.Error:
                time.sleep(0.5)  # iTags like to abort the first attempt
                self._call(path, DEVICE, "Connect", timeout=CONNECT_TIMEOUT_MS)

        deadline = time.monotonic() + RESOLVE_TIMEOUT_S
        while not self._device_prop(path, "ServicesResolved"):
            if time.monotonic() > deadline:
                raise BeepError(_("Connected, but the tag does not report its services."))
            time.sleep(0.1)

        immediate, link_loss = find_alert_chars(self._managed(), path)
        if immediate is None:
            raise BeepError(_("This device cannot beep (no Immediate Alert service)."))
        if link_loss:
            # Otherwise the tag starts beeping by itself whenever the link drops.
            try:
                self._write(link_loss, 0, "request")
            except GLib.Error:
                pass
        try:
            self._write(immediate, level, "command")
        except GLib.Error:
            self._write(immediate, level, "request")

        if disconnect:
            try:
                self._call(path, DEVICE, "Disconnect")
            except GLib.Error:
                pass

    def _write(self, char_path, value, write_type):
        opts = {"type": GLib.Variant("s", write_type)}
        self._call(char_path, CHAR, "WriteValue",
                   GLib.Variant("(aya{sv})", (bytes([value]), opts)), timeout=10000)

    def disconnect(self, address):
        dev = self.device(address)
        if dev and dev["connected"]:
            self.bus.call(BLUEZ, dev["path"], DEVICE, "Disconnect", None, None,
                          Gio.DBusCallFlags.NONE, -1, None,
                          lambda b, r: self._finish(b, r, "Disconnect"))


def _friendly(message):
    m = message.lower()
    if "timeout" in m or "timed out" in m or "abort" in m or "page-timeout" in m:
        return _("The tag does not answer – too far away or battery empty?")
    if "notready" in m or "not ready" in m:
        return _("Bluetooth is not ready.")
    if "inprogress" in m or "in progress" in m:
        return _("Already connecting, please wait a moment.")
    return message.split(":", 1)[-1].strip() or message
