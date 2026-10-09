"""Last known place per tag in ~/.local/share/keyfinder/locations.json.

An entry holds when the tag was last seen (seen, rssi) and the phone's
position from a fix shortly before or after that (lat, lon, accuracy,
fix_time). From these follows the area the tag is in.
"""

import json
import math
import os
import time
from pathlib import Path

WALK_M_PER_S = 1.4        # the phone moves between sighting and fix
MAX_DRIFT_M = 5000


def data_path():
    if os.environ.get("KEYFINDER_DATA"):
        return Path(os.environ["KEYFINDER_DATA"]) / "locations.json"
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / "keyfinder" / "locations.json"


def ble_range(rssi):
    """Rough Bluetooth range in metres for the steps of rssi.level()."""
    if rssi is None:
        return 60
    if rssi >= -55:
        return 5
    if rssi >= -67:
        return 15
    if rssi >= -78:
        return 30
    return 60


def radius(entry):
    """Radius of the area in metres, or None without a position."""
    if not entry or entry.get("lat") is None:
        return None
    drift = WALK_M_PER_S * abs(entry.get("fix_time", 0) - entry.get("seen", 0))
    return round(entry.get("accuracy", 0) + ble_range(entry.get("rssi"))
                 + min(drift, MAX_DRIFT_M))


def circle(lat, lon, meters, points=64):
    """Points (lat, lon) of a circle, for the map."""
    out = []
    dlat = meters / 111_320.0
    dlon = meters / (111_320.0 * max(0.01, math.cos(math.radians(lat))))
    for i in range(points + 1):
        a = 2 * math.pi * i / points
        out.append((lat + dlat * math.sin(a), lon + dlon * math.cos(a)))
    return out


class LocationStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else data_path()
        self.entries = {}
        self.mtime = None
        self.reload()

    def reload(self):
        """Read again if the file changed (the background service writes it)."""
        try:
            mtime = self.path.stat().st_mtime_ns
        except OSError:
            self.entries, self.mtime = {}, None
            return False
        if mtime == self.mtime:
            return False
        try:
            self.entries = {k.upper(): v for k, v in json.loads(self.path.read_text()).items()}
        except (OSError, ValueError, AttributeError):
            self.entries = {}
        self.mtime = mtime
        return True

    def get(self, address):
        return self.entries.get(address.upper())

    def seen(self, address, rssi, when=None):
        e = self.entries.setdefault(address.upper(), {})
        e["seen"] = when if when is not None else time.time()
        e["rssi"] = rssi

    def fix(self, address, lat, lon, accuracy, when=None):
        e = self.entries.setdefault(address.upper(), {})
        e.update(lat=lat, lon=lon, accuracy=accuracy,
                 fix_time=when if when is not None else time.time())

    def remove(self, address):
        self.entries.pop(address.upper(), None)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.entries, indent=1))
        tmp.replace(self.path)
        self.mtime = self.path.stat().st_mtime_ns
