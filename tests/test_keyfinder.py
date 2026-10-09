import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from gi.repository import GLib  # noqa: E402

from keyfinder import rssi  # noqa: E402
from keyfinder.bluez import (ALERT_LEVEL, CHAR, IMMEDIATE_ALERT, LINK_LOSS,  # noqa: E402
                             SERVICE, BlueZ, find_alert_chars)
from keyfinder.store import TagStore  # noqa: E402

TAG = "AA:00:00:00:00:01"
TV = "AA:00:00:00:00:02"
NO_ALERT = "AA:00:00:00:00:03"
REQUEST_ONLY = "AA:00:00:00:00:04"


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class TrackerTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.tr = rssi.SignalTracker(clock=self.clock)

    def feed(self, values, step=0.5):
        for v in values:
            self.tr.add(TAG, v)
            self.clock.t += step

    def test_unknown_without_samples(self):
        self.assertIsNone(self.tr.current(TAG))
        self.assertEqual(self.tr.trend(TAG), rssi.UNKNOWN)

    def test_median_ignores_spikes(self):
        self.feed([-60, -60, -90, -61, -60], step=0.3)
        self.assertEqual(self.tr.current(TAG), -60)

    def test_warmer_and_colder(self):
        self.feed([-80] * 8 + [-65] * 4)
        self.assertEqual(self.tr.trend(TAG), rssi.WARMER)
        self.feed([-85] * 4)
        self.assertEqual(self.tr.trend(TAG), rssi.COLDER)

    def test_steady(self):
        self.feed([-70, -71, -69, -70, -71, -70, -69, -70, -71, -70])
        self.assertEqual(self.tr.trend(TAG), rssi.STEADY)

    def test_last_value_holds_then_lost(self):
        self.feed([-64])
        self.clock.t += 10
        self.assertEqual(self.tr.current(TAG), -64)
        self.clock.t += 6
        self.assertIsNone(self.tr.current(TAG))

    def test_address_case_insensitive(self):
        self.tr.add(TAG.lower(), -50)
        self.assertEqual(self.tr.current(TAG), -50)

    def test_proximity_matches_bt_scanner(self):
        self.assertEqual(rssi.proximity(-55), "very close")
        self.assertEqual(rssi.proximity(-67), "close")
        self.assertEqual(rssi.proximity(-78), "medium")
        self.assertEqual(rssi.proximity(-79), "far")
        self.assertEqual(rssi.proximity(None), "out of range")
        self.assertEqual(rssi.fraction(-200), 0.0)
        self.assertEqual(rssi.fraction(-10), 1.0)


class StoreTest(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sub" / "tags.json"
            s = TagStore(path)
            s.add(TAG.lower(), "Schlüssel")
            s.add(TV, "Rucksack")
            s.rename(TAG, "Haustür")
            s.remove(TV)
            again = TagStore(path)
            self.assertEqual(again.tags, [{"address": TAG, "name": "Haustür",
                                           "category": "house", "track": False}])

    def test_category_kept_and_old_files(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "tags.json"
            path.write_text(json.dumps({"tags": [{"address": TAG, "name": "Fahrrad"}]}))
            s = TagStore(path)
            self.assertEqual(s.get(TAG)["category"], "bicycle")   # old file: guessed
            s.rename(TAG, "Mein Rad", "suitcase")                  # a picked one stays
            self.assertEqual(TagStore(path).get(TAG)["category"], "suitcase")


class CategoryTest(unittest.TestCase):
    def test_guess(self):
        from keyfinder import categories as c
        cases = {"Autoschlüssel": "car", "Car keys": "car", "Haustür": "house",
                 "Wohnungsschlüssel": "keys", "Front door": "keys", "Fahrrad Lotte": "bicycle",
                 "Paradies": "other", "Rucksack": "backpack", "Geldbörse": "wallet",
                 "Cartera": "wallet", "Hund Bello": "dog", "E-Bike": "bicycle", "": "other",
                 "Mein Rad": "bicycle", "Koffer blau": "suitcase", "Clés voiture": "keys",
                 "Sac à dos": "backpack", "Llaves de casa": "keys", "Perro": "dog",
                 "Chat Minou": "cat", "Valise": "suitcase"}
        for name, expected in cases.items():
            self.assertEqual(c.guess(name), expected, name)

    def test_legacy_ids_are_migrated(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "tags.json"
            path.write_text(json.dumps({"tags": [
                {"address": TAG, "name": "Haustür", "category": "schluessel"},
                {"address": TV, "name": "Weg", "category": "gibtsnicht"}]}))
            s = TagStore(path)
            self.assertEqual(s.get(TAG)["category"], "keys")
            self.assertEqual(s.get(TV)["category"], "other")    # unknown: guessed

    def test_ids_unique_and_complete(self):
        from keyfinder import categories as c
        ids = [x[0] for x in c.CATEGORIES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn(c.DEFAULT, ids)
        self.assertEqual(c.emoji("nosuchthing"), c.emoji(c.DEFAULT))

    def test_broken_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "tags.json"
            path.write_text("{kaputt")
            self.assertEqual(TagStore(path).tags, [])


class FindCharsTest(unittest.TestCase):
    def test_distinguishes_services(self):
        dev = "/org/bluez/hci0/dev_X"
        objects = {
            f"{dev}/s1": {SERVICE: {"UUID": LINK_LOSS}},
            f"{dev}/s1/c1": {CHAR: {"UUID": ALERT_LEVEL, "Service": f"{dev}/s1"}},
            f"{dev}/s2": {SERVICE: {"UUID": IMMEDIATE_ALERT.upper()}},
            f"{dev}/s2/c1": {CHAR: {"UUID": ALERT_LEVEL, "Service": f"{dev}/s2"}},
            # the same pattern below another device must not count
            "/org/bluez/hci0/dev_Y/s2": {SERVICE: {"UUID": IMMEDIATE_ALERT}},
        }
        self.assertEqual(find_alert_chars(objects, dev), (f"{dev}/s2/c1", f"{dev}/s1/c1"))
        self.assertEqual(find_alert_chars(objects, "/org/bluez/hci0/dev_Z"), (None, None))


@unittest.skipUnless(os.environ.get("KEYFINDER_BUS") == "session",
                     "only through tests/run-tests.sh (private session bus)")
class BlueZTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "fake.log"
        self.log.touch()
        self.fake = subprocess.Popen([sys.executable, str(HERE / "fake_bluez.py"), str(self.log)],
                                     stdout=subprocess.PIPE, text=True)
        self.assertIn("ready", self.fake.stdout.readline())
        self.bz = BlueZ()
        self.rssi = []
        self.bz.connect("rssi", lambda _b, a, v: self.rssi.append((a, v)))
        self.wait(lambda: self.bz.adapter_path)

    def tearDown(self):
        self.fake.terminate()
        self.fake.wait()
        self.fake.stdout.close()
        self.tmp.cleanup()

    def wait(self, cond, timeout=5.0):
        ctx = GLib.MainContext.default()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            ctx.iteration(False)
            value = cond()
            if value:
                return value
            time.sleep(0.005)
        self.fail("timeout")

    def entries(self, op=None):
        lines = [json.loads(line) for line in self.log.read_text().splitlines()]
        return [e for e in lines if op is None or e["op"] == op]

    def beep(self, address, level, disconnect=False):
        box = []
        self.bz.beep(address, level, box.append, disconnect=disconnect)
        self.wait(lambda: box, timeout=8)
        return box[0]

    def start(self):
        self.bz.start_discovery()
        self.wait(lambda: len(self.bz.devices()) == 4)

    def test_discovery_with_filter_and_rssi(self):
        self.start()
        self.assertEqual(self.entries("filter")[0]["filter"],
                         {"Transport": "le", "DuplicateData": True})
        self.assertTrue(self.entries("start_discovery"))
        self.wait(lambda: any(a == TAG for a, _ in self.rssi[4:]))
        tag = self.bz.device(TAG.lower())
        self.assertEqual(tag["name"], "iTAG")
        self.assertIn(IMMEDIATE_ALERT, tag["uuids"])
        self.bz.stop_discovery()
        self.wait(lambda: self.entries("stop_discovery"))

    def test_beep_disables_link_loss_then_alerts(self):
        self.start()
        self.assertIsNone(self.beep(TAG, 2))
        writes = self.entries("write")
        self.assertEqual(writes[0], {"op": "write", "address": TAG, "service": "1803",
                                     "value": [0], "type": "request"})
        self.assertEqual(writes[1], {"op": "write", "address": TAG, "service": "1802",
                                     "value": [2], "type": "command"})
        self.wait(lambda: self.bz.device(TAG)["connected"])

        self.assertIsNone(self.beep(TAG, 0, disconnect=True))
        self.assertEqual(self.entries("write")[-1]["value"], [0])
        self.assertEqual(self.entries("disconnect")[-1]["address"], TAG)
        self.wait(lambda: not self.bz.device(TAG)["connected"])

    def test_fallback_to_write_with_response(self):
        self.start()
        self.assertIsNone(self.beep(REQUEST_ONLY, 2))
        self.assertEqual(self.entries("write")[-1]["type"], "request")
        self.assertEqual(self.entries("write")[-1]["value"], [2])

    def test_device_without_alert_reports_and_disconnects(self):
        self.start()
        error = self.beep(NO_ALERT, 2)
        self.assertIn("cannot beep", error)
        self.assertEqual(self.entries("disconnect")[-1]["address"], NO_ALERT)

    def test_out_of_range(self):
        self.assertIn("out of range", self.beep("AA:BB:CC:DD:EE:FF", 2))

    def test_stop_when_not_connected_does_nothing(self):
        self.start()
        self.assertIsNone(self.beep(TAG, 0, disconnect=True))
        self.assertEqual(self.entries("connect"), [])

    def test_beep_off_sync(self):
        self.start()
        self.beep(TAG, 2)
        self.bz.beep_off_sync(TAG)
        self.assertEqual(self.entries("write")[-1]["value"], [0])
        self.assertTrue(self.entries("disconnect"))

    def test_power_on(self):
        errors = []
        self.bz.power_on(errors.append)
        self.wait(lambda: errors)
        self.assertEqual(errors, [None])
        self.assertEqual(self.entries("set")[0]["name"], "Powered")


if __name__ == "__main__":
    unittest.main()
