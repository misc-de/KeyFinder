"""App settings in ~/.config/keyfinder/settings.json (next to tags.json)."""

import json

from .store import config_path

DEFAULTS = {"language": "system"}


def path():
    return config_path().parent / "settings.json"


def load():
    data = dict(DEFAULTS)
    try:
        data.update(json.loads(path().read_text()))
    except (OSError, ValueError, TypeError):
        pass
    return data


def save(data):
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(p)


def set_value(key, value):
    data = load()
    data[key] = value
    save(data)
