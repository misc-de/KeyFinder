import json
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "tools"))

from keyfinder import categories, i18n, mappage, rssi  # noqa: E402
from strings import source_strings  # noqa: E402

PLACEHOLDER = re.compile(r"\{\w+\}|%[a-zA-Z]")


class CatalogTest(unittest.TestCase):
    def test_every_language_has_every_string(self):
        wanted = source_strings()
        self.assertGreater(len(wanted), 50)
        for code in i18n.LANGUAGES:
            if code == i18n.DEFAULT:
                continue
            with self.subTest(code=code):
                catalog = i18n.load_catalog(code)
                self.assertEqual(sorted(wanted - set(catalog)), [], "missing")
                self.assertEqual(sorted(set(catalog) - wanted), [], "no longer used")

    def test_placeholders_match(self):
        for code in ("de", "fr", "es"):
            for key, value in i18n.load_catalog(code).items():
                if key == "%m/%d":    # date pattern: own order allowed
                    self.assertEqual(sorted(PLACEHOLDER.findall(value)), ["%d", "%m"])
                    continue
                with self.subTest(code=code, key=key):
                    self.assertEqual(sorted(PLACEHOLDER.findall(key)),
                                     sorted(PLACEHOLDER.findall(value)))


class SwitchTest(unittest.TestCase):
    def tearDown(self):
        i18n.setup("en")

    def test_switch_changes_texts(self):
        i18n.setup("de")
        self.assertEqual(i18n._("Beep"), "Piepen")
        self.assertEqual(rssi.proximity(-50), "sehr nah")
        self.assertEqual(categories.label("car"), "Auto")
        i18n.setup("fr")
        self.assertEqual(i18n._("Beep"), "Sonner")
        i18n.setup("es")
        self.assertEqual(categories.label("dog"), "Perro")
        i18n.setup("en")
        self.assertEqual(i18n._("Beep"), "Beep")

    def test_unknown_falls_back_to_english(self):
        self.assertEqual(i18n.setup("xx"), "en")
        self.assertEqual(i18n._("not in any catalog"), "not in any catalog")

    def test_system_language(self):
        saved = {k: os.environ.get(k) for k in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")}
        try:
            for k in saved:
                os.environ.pop(k, None)
            os.environ["LANG"] = "fr_FR.UTF-8"
            self.assertEqual(i18n.system_language(), "fr")
            os.environ["LANGUAGE"] = "nl:es"
            self.assertEqual(i18n.system_language(), "es")
            os.environ["LANGUAGE"] = "nl"
            self.assertEqual(i18n.system_language(), "en")
            os.environ.pop("LANGUAGE")
            os.environ["LC_ALL"] = "C.UTF-8"           # C is skipped
            self.assertEqual(i18n.system_language(), "fr")
            self.assertEqual(i18n.setup("system"), "fr")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_numbers_and_dates(self):
        now = time.mktime((2026, 10, 9, 18, 0, 0, 0, 0, -1))
        i18n.setup("de")
        self.assertEqual(mappage.distance_text(2345), "2,3 km")
        self.assertEqual(mappage.when_text(now - 3 * 86400, now), "06.10. 18:00")
        self.assertEqual(mappage.when_text(now - 60, now), "heute 17:59")
        i18n.setup("en")
        self.assertEqual(mappage.distance_text(2345), "2.3 km")
        self.assertEqual(mappage.when_text(now - 3 * 86400, now), "10/06 18:00")


class SettingsTest(unittest.TestCase):
    def test_language_is_saved_next_to_tags(self):
        from keyfinder import settings
        with tempfile.TemporaryDirectory() as d:
            saved = os.environ.get("KEYFINDER_CONFIG")
            os.environ["KEYFINDER_CONFIG"] = str(Path(d) / "tags.json")
            try:
                self.assertEqual(settings.load()["language"], "system")
                settings.set_value("language", "es")
                self.assertEqual(settings.load()["language"], "es")
                self.assertEqual(json.loads((Path(d) / "settings.json").read_text()),
                                 {"language": "es"})
            finally:
                if saved is None:
                    os.environ.pop("KEYFINDER_CONFIG")
                else:
                    os.environ["KEYFINDER_CONFIG"] = saved


if __name__ == "__main__":
    unittest.main()
