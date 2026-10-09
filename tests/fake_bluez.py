"""Minimales BlueZ für Tests auf dem Session-Bus (nur was KeyFinder braucht).

Aufruf: python3 fake_bluez.py <logdatei>
Jede GATT-Schreiboperation und jeder Connect/Disconnect landet als JSON-Zeile im Log.
"""

import json
import sys

from gi.repository import Gio, GLib

ADAPTER_PATH = "/org/bluez/hci0"
U = "0000{:04x}-0000-1000-8000-00805f9b34fb".format

DEVICES = {
    # Adresse: (Name, UUIDs, Grund-RSSI, hat Immediate Alert, nur "request")
    "AA:00:00:00:00:01": ("iTAG", [U(0x1802), U(0x1803), U(0xFFE0)], -50, True, False),
    "AA:00:00:00:00:02": ("Fernseher", [U(0x180A)], -80, False, False),
    "AA:00:00:00:00:03": ("Smart Tag", [U(0xFFE0)], -70, False, False),
    "AA:00:00:00:00:04": ("iTAG", [U(0x1802)], -60, True, True),
}

XML = """
<node>
  <interface name="org.freedesktop.DBus.ObjectManager">
    <method name="GetManagedObjects"><arg type="a{oa{sa{sv}}}" direction="out"/></method>
    <signal name="InterfacesAdded"><arg type="o"/><arg type="a{sa{sv}}"/></signal>
    <signal name="InterfacesRemoved"><arg type="o"/><arg type="as"/></signal>
  </interface>
  <interface name="org.bluez.Adapter1">
    <property name="Powered" type="b" access="readwrite"/>
    <property name="Discovering" type="b" access="read"/>
    <method name="StartDiscovery"/><method name="StopDiscovery"/>
    <method name="SetDiscoveryFilter"><arg type="a{sv}" direction="in"/></method>
  </interface>
  <interface name="org.bluez.Device1">
    <property name="Connected" type="b" access="read"/>
    <property name="ServicesResolved" type="b" access="read"/>
    <method name="Connect"/><method name="Disconnect"/>
  </interface>
  <interface name="org.bluez.GattCharacteristic1">
    <method name="WriteValue"><arg type="ay" direction="in"/><arg type="a{sv}" direction="in"/></method>
  </interface>
</node>
"""


class Fake:
    def __init__(self, log_path):
        self.log = open(log_path, "a", buffering=1)
        self.node = Gio.DBusNodeInfo.new_for_xml(XML)
        self.objects = {}       # Pfad -> {Interface: {Name: Variant}}
        self.registrations = {}
        self.tick = 0
        self.discovery_timer = None
        self.bus = None

    def write_log(self, **entry):
        self.log.write(json.dumps(entry) + "\n")

    # --- Objektverwaltung ---------------------------------------------

    def iface(self, name):
        return self.node.lookup_interface(name)

    def add(self, path, ifaces, announce=True):
        self.objects[path] = ifaces
        regs = []
        for name in ifaces:
            info = self.iface(name)
            if info:
                regs.append(self.bus.register_object(path, info, self.on_call,
                                                     self.on_get, self.on_set))
        self.registrations[path] = regs
        if announce:
            self.bus.emit_signal(None, "/", "org.freedesktop.DBus.ObjectManager",
                                 "InterfacesAdded", GLib.Variant("(oa{sa{sv}})", (path, ifaces)))

    def remove(self, path):
        ifaces = self.objects.pop(path)
        for reg in self.registrations.pop(path):
            self.bus.unregister_object(reg)
        self.bus.emit_signal(None, "/", "org.freedesktop.DBus.ObjectManager",
                             "InterfacesRemoved", GLib.Variant("(oas)", (path, list(ifaces))))

    def set_prop(self, path, iface, name, variant):
        self.objects[path][iface][name] = variant
        self.bus.emit_signal(None, path, "org.freedesktop.DBus.Properties", "PropertiesChanged",
                             GLib.Variant("(sa{sv}as)", (iface, {name: variant}, [])))

    @staticmethod
    def dev_path(address):
        return f"{ADAPTER_PATH}/dev_{address.replace(':', '_')}"

    def setup(self, bus):
        self.bus = bus
        root = bus.register_object("/", self.iface("org.freedesktop.DBus.ObjectManager"),
                                   self.on_call, None, None)
        assert root
        self.add(ADAPTER_PATH, {"org.bluez.Adapter1": {
            "Address": GLib.Variant("s", "00:11:22:33:44:55"),
            "Powered": GLib.Variant("b", True),
            "Discovering": GLib.Variant("b", False),
        }}, announce=False)

    # --- Methoden -----------------------------------------------------

    def on_call(self, _conn, _sender, path, iface, method, params, invocation):
        try:
            result = getattr(self, f"do_{method}")(path, iface, *params.unpack())
            invocation.return_value(result)
        except GLib.Error as e:
            invocation.return_gerror(e)
        except FakeError as e:
            invocation.return_dbus_error(e.name, e.text)

    def do_GetManagedObjects(self, _path, _iface):
        return GLib.Variant("(a{oa{sa{sv}}})", (self.objects,))

    def on_get(self, _conn, _sender, path, iface, name):
        return self.objects[path][iface][name]

    def on_set(self, _conn, _sender, path, iface, name, value):
        self.write_log(op="set", path=path, name=name, value=value.unpack())
        self.set_prop(path, iface, name, value)
        return True

    def do_SetDiscoveryFilter(self, _path, _iface, flt):
        self.write_log(op="filter", filter=flt)
        return None

    def do_StartDiscovery(self, path, _iface):
        self.write_log(op="start_discovery")
        self.set_prop(path, "org.bluez.Adapter1", "Discovering", GLib.Variant("b", True))
        if self.discovery_timer is None:
            self.discovery_timer = GLib.timeout_add(100, self.advertise)
        return None

    def do_StopDiscovery(self, path, _iface):
        self.write_log(op="stop_discovery")
        if self.discovery_timer:
            GLib.source_remove(self.discovery_timer)
            self.discovery_timer = None
        return None

    def advertise(self):
        """Tags tauchen beim ersten Durchlauf auf, danach schwankt das RSSI."""
        self.tick += 1
        for address, (name, uuids, base, *_rest) in DEVICES.items():
            path = self.dev_path(address)
            rssi = base + (self.tick % 5) - 2
            if path not in self.objects:
                self.add(path, {"org.bluez.Device1": {
                    "Address": GLib.Variant("s", address),
                    "Name": GLib.Variant("s", name),
                    "Alias": GLib.Variant("s", name),
                    "Adapter": GLib.Variant("o", ADAPTER_PATH),
                    "UUIDs": GLib.Variant("as", uuids),
                    "RSSI": GLib.Variant("n", rssi),
                    "Connected": GLib.Variant("b", False),
                    "ServicesResolved": GLib.Variant("b", False),
                }})
            elif not self.objects[path]["org.bluez.Device1"]["Connected"].unpack():
                self.set_prop(path, "org.bluez.Device1", "RSSI", GLib.Variant("n", rssi))
        return True

    def do_Connect(self, path, _iface):
        address = self.objects[path]["org.bluez.Device1"]["Address"].unpack()
        self.write_log(op="connect", address=address)
        self.set_prop(path, "org.bluez.Device1", "Connected", GLib.Variant("b", True))
        GLib.timeout_add(200, self.resolve, path, address)
        return None

    def resolve(self, path, address):
        _name, _uuids, _base, has_alert, _only_request = DEVICES[address]
        services = [(0x1803, "service0001")]
        if has_alert:
            services.append((0x1802, "service0002"))
        for uuid, sname in services:
            spath = f"{path}/{sname}"
            self.add(spath, {"org.bluez.GattService1": {
                "UUID": GLib.Variant("s", U(uuid)),
                "Device": GLib.Variant("o", path),
            }})
            self.add(f"{spath}/char0001", {"org.bluez.GattCharacteristic1": {
                "UUID": GLib.Variant("s", U(0x2A06)),
                "Service": GLib.Variant("o", spath),
            }})
        self.set_prop(path, "org.bluez.Device1", "ServicesResolved", GLib.Variant("b", True))
        return False

    def do_Disconnect(self, path, _iface):
        address = self.objects[path]["org.bluez.Device1"]["Address"].unpack()
        self.write_log(op="disconnect", address=address)
        for sub in [p for p in self.objects if p.startswith(path + "/")]:
            self.remove(sub)
        self.set_prop(path, "org.bluez.Device1", "ServicesResolved", GLib.Variant("b", False))
        self.set_prop(path, "org.bluez.Device1", "Connected", GLib.Variant("b", False))
        return None

    def do_WriteValue(self, path, _iface, value, opts):
        device = path.split("/service")[0]
        address = self.objects[device]["org.bluez.Device1"]["Address"].unpack()
        service = self.objects[path.rsplit("/", 1)[0]]["org.bluez.GattService1"]["UUID"].unpack()
        wtype = opts.get("type", "request")
        if DEVICES[address][4] and wtype == "command":
            raise FakeError("org.bluez.Error.NotSupported", "Operation is not supported")
        self.write_log(op="write", address=address, service=service[4:8],
                       value=list(value), type=wtype)
        return None


class FakeError(Exception):
    def __init__(self, name, text):
        super().__init__(text)
        self.name, self.text = name, text


def main():
    fake = Fake(sys.argv[1])
    loop = GLib.MainLoop()
    Gio.bus_own_name(Gio.BusType.SESSION, "org.bluez", Gio.BusNameOwnerFlags.NONE,
                     lambda bus, _n: fake.setup(bus),
                     lambda _b, _n: print("fake_bluez: ready", flush=True),
                     lambda _b, _n: loop.quit())
    loop.run()


if __name__ == "__main__":
    main()
