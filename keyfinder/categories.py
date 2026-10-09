"""Kategorien für das Symbol in der Kachel, mit Vorschlag aus dem Namen.

Bluetooth verrät nicht, woran ein Tag hängt, deshalb wählt der Nutzer die
Kategorie; vorgeschlagen wird sie anhand von Wörtern im vergebenen Namen.
"""

import re

DEFAULT = "sonstiges"

# (id, Bezeichnung, Emoji, Stichwörter). Reihenfolge = Vorrang beim Raten:
# „Autoschlüssel“ soll Auto werden, nicht Schlüssel.
CATEGORIES = [
    ("auto", "Auto", "🚗", ("auto", "car", "wagen", "pkw", "kfz", "golf", "tesla")),
    ("motorrad", "Motorrad", "🏍️", ("motorrad", "moped", "mofa", "vespa")),
    ("fahrrad", "Fahrrad", "🚲", ("fahrrad", "rad", "bike", "velo")),
    ("scooter", "Roller", "🛴", ("roller", "scooter", "tretroller")),
    ("schluessel", "Schlüssel", "🔑", ("schlüssel", "schluessel", "key", "tür", "büro",
                                       "wohnung", "garage")),
    ("haus", "Haus", "🏠", ("haus", "home", "keller", "garten", "zuhause")),
    ("rucksack", "Rucksack", "🎒", ("rucksack", "ranzen", "schulranzen", "schule")),
    ("handtasche", "Handtasche", "👜", ("handtasche", "tasche", "beutel")),
    ("aktentasche", "Aktentasche", "💼", ("aktentasche", "arbeit", "laptoptasche")),
    ("geldboerse", "Geldbörse", "👛", ("geldbörse", "portemonnaie", "portmonee", "brieftasche",
                                      "wallet", "geld", "börse")),
    ("koffer", "Koffer", "🧳", ("koffer", "gepäck", "reise", "trolley")),
    ("laptop", "Laptop", "💻", ("laptop", "notebook", "macbook", "rechner")),
    ("handy", "Handy", "📱", ("handy", "phone", "smartphone", "tablet", "ipad")),
    ("kopfhoerer", "Kopfhörer", "🎧", ("kopfhörer", "headset", "airpods", "earbuds")),
    ("kamera", "Kamera", "📷", ("kamera", "camera", "foto", "gopro")),
    ("fernbedienung", "Fernbedienung", "🎮", ("fernbedienung", "controller", "gamepad",
                                             "konsole")),
    ("uhr", "Uhr", "⌚", ("uhr", "watch")),
    ("brille", "Brille", "👓", ("brille", "sonnenbrille")),
    ("schirm", "Regenschirm", "☂️", ("schirm", "regenschirm")),
    ("jacke", "Jacke", "🧥", ("jacke", "mantel", "kleidung")),
    ("werkzeug", "Werkzeug", "🔧", ("werkzeug", "werkzeugkoffer", "bohrer", "tool")),
    ("sport", "Sport", "⚽", ("sport", "ball", "fußball", "turn", "fitness", "golfbag")),
    ("instrument", "Instrument", "🎸", ("gitarre", "instrument", "geige", "musik")),
    ("hund", "Hund", "🐕", ("hund", "dog", "welpe", "leine")),
    ("katze", "Katze", "🐈", ("katze", "kater", "cat", "mieze")),
    ("haustier", "Haustier", "🐾", ("tier", "haustier", "pferd", "hase")),
    ("kind", "Kind", "🧒", ("kind", "sohn", "tochter", "junior")),
    ("baby", "Baby", "👶", ("baby", "kinderwagen", "buggy")),
    ("spielzeug", "Spielzeug", "🧸", ("spielzeug", "teddy", "kuscheltier")),
    ("buch", "Buch", "📖", ("buch", "kalender", "notizbuch")),
    ("geschenk", "Geschenk", "🎁", ("geschenk", "überraschung")),
    ("sonstiges", "Sonstiges", "🏷️", ()),
]

BY_ID = {c[0]: c for c in CATEGORIES}


def _matches(word, text):
    # Kurze Wörter nur am Wortanfang („rad“ nicht in „Paradies“),
    # lange überall („Wohnungsschlüssel“).
    if len(word) < 5:
        return re.search(r"(?:^|[^\w])" + re.escape(word), text) is not None
    return word in text


def guess(name):
    text = (name or "").lower()
    for cid, _label, _emoji, words in CATEGORIES:
        if any(_matches(w, text) for w in words):
            return cid
    return DEFAULT


def emoji(cid):
    return BY_ID.get(cid, BY_ID[DEFAULT])[2]


def label(cid):
    return BY_ID.get(cid, BY_ID[DEFAULT])[1]
