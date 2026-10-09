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

from gi.repository import GLib, GObject  # noqa: E402

from keyfinder import locations, mappage, service, tracker  # noqa: E402
from keyfinder.locations import LocationStore  # noqa: E402
from keyfinder.store import TagStore  # noqa: E402

TAG = "AA:00:00:00:00:01"
OTHER = "AA:00:00:00:00:02"
FAKE_SYSTEMCTL = str(HERE / "fake-bin" / "systemctl")


def spin(cond, timeout=5.0):
    ctx = GLib.MainContext.default()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        ctx.iteration(False)
        if cond():
            return True
        time.sleep(0.005)
    return False


class RadiusTest(unittest.TestCase):
    def test_radius_parts(self):
        e = {"seen": 1000, "rssi": -60, "lat": 50.9, "lon": 6.9, "accuracy": 20,
             "fix_time": 1000}
        self.assertEqual(locations.radius(e), 20 + 15)
        e["fix_time"] = 1100            # 100 s später geortet: Weg dazwischen
        self.assertEqual(locations.radius(e), 20 + 15 + 140)
        e["fix_time"] = 1000 + 10 ** 6  # gedeckelt
        self.assertEqual(locations.radius(e), 20 + 15 + locations.MAX_DRIFT_M)
        self.assertIsNone(locations.radius({"seen": 1}))
        self.assertIsNone(locations.radius(None))

    def test_circle_is_closed_and_round(self):
        pts = locations.circle(50.0, 7.0, 1000, points=36)
        self.assertEqual(pts[0], pts[-1])
        for lat, lon in pts:
            dy = (lat - 50.0) * 111_320
            dx = (lon - 7.0) * 111_320 * 0.6427876   # cos(50°)
            self.assertAlmostEqual((dx * dx + dy * dy) ** 0.5, 1000, delta=1)

    def test_texts(self):
        now = time.mktime((2026, 10, 9, 18, 0, 0, 0, 0, -1))
        self.assertEqual(mappage.when_text(now - 3600, now), "heute 17:00")
        self.assertEqual(mappage.when_text(now - 86400, now), "gestern 18:00")
        self.assertEqual(mappage.when_text(now - 3 * 86400, now), "06.10. 18:00")
        self.assertEqual(mappage.distance_text(123), "120 m")
        self.assertEqual(mappage.distance_text(2345), "2,3 km")
        self.assertEqual(mappage.summary(None), "Noch kein Ort gespeichert")
        self.assertIn("ohne Standort", mappage.summary({"seen": now}))
        self.assertGreater(mappage.zoom_for(50, 50), mappage.zoom_for(50, 5000))


class LocationStoreTest(unittest.TestCase):
    def test_roundtrip_and_reload(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x" / "locations.json"
            a = LocationStore(path)
            a.seen(TAG.lower(), -60, 10)
            a.fix(TAG, 1.0, 2.0, 30, 11)
            a.save()
            b = LocationStore(path)
            self.assertEqual(b.get(TAG), {"seen": 10, "rssi": -60, "lat": 1.0, "lon": 2.0,
                                          "accuracy": 30, "fix_time": 11})
            self.assertFalse(b.reload())          # unverändert
            time.sleep(0.01)
            a.remove(TAG)
            a.save()
            self.assertTrue(b.reload())
            self.assertIsNone(b.get(TAG))


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "systemctl.log"
        self.env = {"KEYFINDER_SYSTEMCTL": os.environ.get("KEYFINDER_SYSTEMCTL"),
                    "FAKE_SYSTEMCTL_LOG": os.environ.get("FAKE_SYSTEMCTL_LOG")}
        os.environ["KEYFINDER_SYSTEMCTL"] = FAKE_SYSTEMCTL
        os.environ["FAKE_SYSTEMCTL_LOG"] = str(self.log)
        self.store = TagStore(Path(self.tmp.name) / "tags.json")
        self.store.add(TAG, "Auto")

    def tearDown(self):
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def lines(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_off_without_tracked_tags(self):
        self.assertEqual(service.sync_blocking(self.store), 0)
        self.assertEqual(self.lines(), ["--user disable --now keyfinder-tracker.service"])

    def test_on_and_restart(self):
        self.store.set_track(TAG, True)
        service.sync_blocking(self.store)
        service.sync_blocking(self.store, restart=True)
        self.assertEqual(self.lines(), ["--user enable --now keyfinder-tracker.service",
                                        "--user enable keyfinder-tracker.service",
                                        "--user restart keyfinder-tracker.service"])

    def test_async_reports_failure(self):
        os.environ["FAKE_SYSTEMCTL_EXIT"] = "1"
        try:
            box = []
            self.store.set_track(TAG, True)
            service.sync(self.store, box.append)
            self.assertTrue(spin(lambda: box))
            self.assertTrue(box[0])
        finally:
            os.environ.pop("FAKE_SYSTEMCTL_EXIT")

    def test_async_ok(self):
        box = []
        service.sync(self.store, box.append, restart=True)
        self.assertTrue(spin(lambda: box))
        self.assertEqual(box, [None])

    def test_launcher_sync_service(self):
        env = dict(os.environ, KEYFINDER_CONFIG=str(self.store.path))
        self.store.set_track(TAG, True)
        r = subprocess.run([sys.executable, str(HERE.parent / "bin" / "keyfinder"),
                            "--sync-service"], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.lines(), ["--user enable --now keyfinder-tracker.service"])


@unittest.skipUnless(os.environ.get("KEYFINDER_BUS") == "session",
                     "nur über tests/run-tests.sh (privater Session-Bus)")
class FlatpakServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.spawn_log = d / "spawn.log"
        self.saved = {k: os.environ.get(k) for k in
                      ("KEYFINDER_FLATPAK", "KEYFINDER_AUTOSTART_DIR", "KEYFINDER_SPAWN",
                       "FAKE_SPAWN_LOG")}
        os.environ.update(KEYFINDER_FLATPAK="1", KEYFINDER_AUTOSTART_DIR=str(d / "autostart"),
                          KEYFINDER_SPAWN=str(HERE / "fake-bin" / "spawn"),
                          FAKE_SPAWN_LOG=str(self.spawn_log))
        self.store = TagStore(d / "tags.json")
        self.store.add(TAG, "Auto")

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def spawned(self):
        spin(lambda: self.spawn_log.exists(), 2)
        return self.spawn_log.read_text().splitlines() if self.spawn_log.exists() else []

    def test_on_writes_autostart_and_spawns(self):
        self.store.set_track(TAG, True)
        box = []
        service.sync(self.store, box.append)
        self.assertTrue(spin(lambda: box))
        self.assertEqual(box, [None])
        text = service.autostart_file().read_text()
        self.assertIn("Exec=flatpak run --command=keyfinder io.github.miscde.KeyFinder --tracker",
                      text)
        self.assertEqual(self.spawned(), ["keyfinder --tracker"])

    def test_off_removes_autostart(self):
        self.store.set_track(TAG, True)
        service.sync_blocking(self.store)
        self.store.set_track(TAG, False)
        self.assertEqual(service.sync_blocking(self.store), 0)
        self.assertFalse(service.autostart_file().exists())

    def test_no_second_spawn_while_running(self):
        owner, _bus = tracker.claim_name()
        self.assertTrue(owner)
        self.assertFalse(tracker.claim_name()[0])     # zweiter Dienst zieht sich zurück
        self.assertTrue(service.tracker_running())
        self.store.set_track(TAG, True)
        service.sync_blocking(self.store)
        time.sleep(0.3)
        self.assertFalse(self.spawn_log.exists())
        _bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                       "ReleaseName", GLib.Variant("(s)", (service.TRACKER_NAME,)), None,
                       0, 2000, None)


class FakeBlueZ(GObject.Object):
    __gsignals__ = {"rssi": (GObject.SignalFlags.RUN_FIRST, None, (str, int))}

    def __init__(self):
        super().__init__()
        self.scans = 0

    def start_discovery(self):
        self.scans += 1

    def stop_discovery(self):
        pass


class FakeLocator(GObject.Object):
    __gsignals__ = {"fix": (GObject.SignalFlags.RUN_FIRST, None, (float, float, float)),
                    "failed": (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    def __init__(self):
        super().__init__()
        self.starts = self.stops = 0

    def start(self):
        self.starts += 1

    def stop(self):
        self.stops += 1


class TrackerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.tags = TagStore(d / "tags.json")
        self.tags.add(TAG, "Auto")
        self.tags.add(OTHER, "Rucksack")
        self.tags.set_track(TAG, True)
        self.now = [1000.0]
        self.bz, self.loc = FakeBlueZ(), FakeLocator()
        self.empty = []
        self.tr = tracker.Tracker(self.bz, self.loc, LocationStore(d / "loc.json"),
                                  tags_path=d / "tags.json", clock=lambda: self.now[0],
                                  on_empty=lambda: self.empty.append(1))

    def tearDown(self):
        self.tr._finish_fix()
        self.tmp.cleanup()

    def scan(self, *seen):
        self.assertTrue(self.tr.begin_scan())
        for address, value in seen:
            self.bz.emit("rssi", address, value)
        self.tr.end_scan()

    def test_first_sighting_requests_fix_and_stores_it(self):
        self.scan((TAG.lower(), -60), (OTHER, -50))
        self.assertEqual(self.loc.starts, 1)
        self.assertIsNone(self.tr.locations.get(OTHER))   # nicht getrackt
        self.loc.emit("fix", 50.0, 7.0, 300.0)
        self.loc.emit("fix", 50.1, 7.1, 800.0)              # schlechter: ignoriert
        e = LocationStore(self.tr.locations.path).get(TAG)
        self.assertEqual((e["lat"], e["accuracy"], e["seen"], e["rssi"]), (50.0, 300.0, 1000, -60))
        self.assertEqual(self.loc.stops, 0)                 # wartet auf Besseres
        self.loc.emit("fix", 50.2, 7.2, 20.0)
        self.assertEqual(self.tr.locations.get(TAG)["lat"], 50.2)
        self.assertEqual(self.loc.stops, 1)                 # gut genug: GPS aus

    def test_no_new_fix_while_fresh_then_again_when_old(self):
        self.scan((TAG, -60))
        self.loc.emit("fix", 50.0, 7.0, 10.0)
        self.now[0] += 120
        self.scan((TAG, -62))
        self.assertEqual(self.loc.starts, 1)
        self.assertEqual(self.tr.locations.get(TAG)["seen"], 1120)
        self.now[0] += tracker.FIX_EVERY_S
        self.scan((TAG, -61))
        self.assertEqual(self.loc.starts, 2)

    def test_lost_tag_gets_final_fix(self):
        self.scan((TAG, -70))
        self.loc.emit("fix", 50.0, 7.0, 10.0)
        self.now[0] += 60
        self.scan()                                          # nicht mehr da
        self.assertEqual(self.loc.starts, 2)
        self.now[0] += 30
        self.loc.emit("fix", 50.5, 7.5, 15.0)
        e = self.tr.locations.get(TAG)
        self.assertEqual((e["lat"], e["seen"], e["fix_time"]), (50.5, 1000, 1090))
        self.assertEqual(locations.radius(e), 15 + 30 + round(1.4 * 90))
        self.now[0] += 60
        self.scan()                                          # bleibt weg: keine Ortung mehr
        self.assertEqual(self.loc.starts, 2)

    def test_failed_fix_keeps_sighting(self):
        self.scan((TAG, -60))
        self.loc.emit("failed", "AccessDenied")
        self.assertEqual(self.loc.stops, 1)
        self.assertEqual(LocationStore(self.tr.locations.path).get(TAG)["rssi"], -60)

    def test_stops_without_tracked_tags(self):
        self.tags.set_track(TAG, False)
        self.assertFalse(self.tr.begin_scan())
        self.assertEqual(self.empty, [1])
        self.assertEqual(self.bz.scans, 0)


@unittest.skipUnless(os.environ.get("KEYFINDER_BUS") == "session",
                     "nur über tests/run-tests.sh (privater Session-Bus)")
class LocatorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "geo.log"
        self.log.touch()

    def tearDown(self):
        self.fake.terminate()
        self.fake.wait()
        self.fake.stdout.close()
        self.tmp.cleanup()

    def start_fake(self, accuracies):
        self.fake = subprocess.Popen([sys.executable, str(HERE / "fake_geoclue.py"),
                                      str(self.log), "50.94", "6.96", accuracies],
                                     stdout=subprocess.PIPE, text=True)
        self.assertIn("ready", self.fake.stdout.readline())

    def ops(self):
        return [json.loads(x)["op"] for x in self.log.read_text().splitlines()]

    def test_fix_flow(self):
        from keyfinder.geo import Locator
        self.start_fake("200,30")
        loc = Locator()
        fixes = []
        loc.connect("fix", lambda _l, la, lo, acc: fixes.append((la, lo, acc)))
        loc.start()
        self.assertTrue(spin(lambda: len(fixes) == 2))
        self.assertEqual(fixes, [(50.94, 6.96, 200.0), (50.94, 6.96, 30.0)])
        loc.stop()
        self.assertTrue(spin(lambda: "DeleteClient" in self.ops()))
        self.assertEqual(self.ops()[:4], ["CreateClient", "set", "set", "Start"])
        self.assertIn("Stop", self.ops())

    def test_start_failure_is_reported(self):
        from keyfinder import geo
        self.start_fake("10")
        old = geo.DESKTOP_ID
        geo.DESKTOP_ID = "falsch"
        try:
            loc = geo.Locator()
            errors = []
            loc.connect("failed", lambda _l, m: errors.append(m))
            loc.start()
            self.assertTrue(spin(lambda: errors))
            self.assertIn("no id", errors[0])
            self.assertFalse(loc.running)
        finally:
            geo.DESKTOP_ID = old


if __name__ == "__main__":
    unittest.main()
