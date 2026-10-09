"""Paired tags in ~/.config/keyfinder/tags.json."""

import json
import os
from pathlib import Path

from . import categories


def config_path():
    if os.environ.get("KEYFINDER_CONFIG"):
        return Path(os.environ["KEYFINDER_CONFIG"])
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "keyfinder" / "tags.json"


class TagStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else config_path()
        self.tags = []
        try:
            data = json.loads(self.path.read_text())
            self.tags = [{"address": t["address"].upper(), "name": t["name"],
                          "category": (categories.migrate(t.get("category"))
                                       or categories.guess(t["name"])),
                          "track": bool(t.get("track"))}
                         for t in data.get("tags", [])]
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"tags": self.tags}, indent=2, ensure_ascii=False))
        tmp.replace(self.path)

    def get(self, address):
        for tag in self.tags:
            if tag["address"] == address.upper():
                return tag
        return None

    def add(self, address, name, category=None):
        category = category or categories.guess(name)
        tag = self.get(address)
        if tag:
            tag["name"], tag["category"] = name, category
        else:
            self.tags.append({"address": address.upper(), "name": name, "category": category,
                              "track": False})
        self.save()

    def rename(self, address, name, category=None):
        self.add(address, name, category)

    def set_track(self, address, track):
        tag = self.get(address)
        if tag:
            tag["track"] = bool(track)
            self.save()

    def remove(self, address):
        self.tags = [t for t in self.tags if t["address"] != address.upper()]
        self.save()
