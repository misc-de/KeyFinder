"""Categories for the symbol on a tile, guessed from the tag's name.

Bluetooth does not tell what a tag is attached to, so the user picks the
category; it is suggested from words in the name, in English, German, French
and Spanish.
"""

import re

from .i18n import _

DEFAULT = "other"

# (id, label, emoji, keywords) – labels are translated with _() when shown.
CATEGORIES = [
    ("car", "Car", "🚗", ("car", "auto", "wagen", "pkw", "kfz", "voiture", "coche", "carro",
                         "golf", "tesla")),
    ("motorbike", "Motorbike", "🏍️", ("motorbike", "motorcycle", "motorrad", "moped", "mofa",
                                     "vespa", "moto")),
    ("bicycle", "Bicycle", "🚲", ("bicycle", "bike", "fahrrad", "rad", "velo", "vélo", "bici",
                                 "bicicleta")),
    ("scooter", "Scooter", "🛴", ("scooter", "roller", "tretroller", "trottinette", "patinete")),
    ("keys", "Keys", "🔑", ("key", "door", "office", "schlüssel", "schluessel", "tür", "büro",
                           "wohnung", "garage", "clé", "clef", "porte", "llave", "puerta")),
    ("house", "House", "🏠", ("house", "home", "garden", "haus", "keller", "garten", "zuhause",
                             "maison", "casa")),
    ("backpack", "Backpack", "🎒", ("backpack", "school", "rucksack", "ranzen", "schulranzen",
                                   "schule", "sac à dos", "école", "mochila", "escuela")),
    ("handbag", "Handbag", "👜", ("handbag", "bag", "purse", "handtasche", "tasche", "beutel",
                                 "sac", "bolso")),
    ("briefcase", "Briefcase", "💼", ("briefcase", "work", "aktentasche", "arbeit", "cartable",
                                     "travail", "maletín", "trabajo")),
    ("wallet", "Wallet", "👛", ("wallet", "money", "geldbörse", "portemonnaie", "portmonee",
                               "brieftasche", "geld", "börse", "portefeuille", "argent",
                               "cartera", "billetera", "dinero")),
    ("suitcase", "Suitcase", "🧳", ("suitcase", "luggage", "travel", "koffer", "gepäck", "reise",
                                   "trolley", "valise", "bagage", "voyage", "maleta",
                                   "equipaje", "viaje")),
    ("laptop", "Laptop", "💻", ("laptop", "notebook", "macbook", "rechner", "ordinateur",
                               "portátil", "portatil")),
    ("phone", "Phone", "📱", ("phone", "smartphone", "tablet", "ipad", "handy", "téléphone",
                             "teléfono", "móvil", "movil")),
    ("headphones", "Headphones", "🎧", ("headphones", "headset", "airpods", "earbuds",
                                       "kopfhörer", "casque", "écouteurs", "auriculares")),
    ("camera", "Camera", "📷", ("camera", "photo", "gopro", "kamera", "foto", "appareil",
                               "cámara")),
    ("remote", "Remote control", "🎮", ("remote", "controller", "gamepad", "fernbedienung",
                                       "konsole", "télécommande", "mando")),
    ("watch", "Watch", "⌚", ("watch", "uhr", "montre", "reloj")),
    ("glasses", "Glasses", "👓", ("glasses", "sunglasses", "brille", "sonnenbrille", "lunettes",
                                 "gafas")),
    ("umbrella", "Umbrella", "☂️", ("umbrella", "schirm", "regenschirm", "parapluie",
                                   "paraguas")),
    ("jacket", "Jacket", "🧥", ("jacket", "coat", "jacke", "mantel", "kleidung", "veste",
                               "manteau", "chaqueta", "abrigo")),
    ("tools", "Tools", "🔧", ("tool", "drill", "werkzeug", "bohrer", "outil", "herramienta")),
    ("sport", "Sport", "⚽", ("sport", "ball", "football", "fitness", "gym", "fußball",
                             "ballon", "deporte", "balón")),
    ("instrument", "Instrument", "🎸", ("instrument", "guitar", "music", "gitarre", "geige",
                                       "musik", "guitare", "musique", "guitarra", "música")),
    ("dog", "Dog", "🐕", ("dog", "puppy", "leash", "hund", "welpe", "leine", "chien", "perro")),
    ("cat", "Cat", "🐈", ("cat", "kitty", "katze", "kater", "mieze", "chat", "gato")),
    ("pet", "Pet", "🐾", ("pet", "animal", "horse", "tier", "haustier", "pferd", "hase",
                         "cheval", "caballo")),
    ("child", "Child", "🧒", ("child", "kid", "son", "daughter", "kind", "sohn", "tochter",
                             "enfant", "fils", "fille", "niño", "niña", "hijo", "hija")),
    ("baby", "Baby", "👶", ("baby", "stroller", "kinderwagen", "buggy", "bébé", "poussette",
                           "bebé", "carrito")),
    ("toy", "Toy", "🧸", ("toy", "teddy", "spielzeug", "kuscheltier", "jouet", "peluche",
                         "juguete")),
    ("book", "Book", "📖", ("book", "diary", "buch", "kalender", "notizbuch", "livre", "cahier",
                           "libro")),
    ("gift", "Gift", "🎁", ("gift", "present", "geschenk", "überraschung", "cadeau", "regalo")),
    ("other", "Other", "🏷️", ()),
]

BY_ID = {c[0]: c for c in CATEGORIES}

# German ids of version 0.1.0, rewritten when tags.json is read.
LEGACY = {
    "auto": "car", "motorrad": "motorbike", "fahrrad": "bicycle", "schluessel": "keys",
    "haus": "house", "rucksack": "backpack", "handtasche": "handbag",
    "aktentasche": "briefcase", "geldboerse": "wallet", "koffer": "suitcase",
    "handy": "phone", "kopfhoerer": "headphones", "kamera": "camera",
    "fernbedienung": "remote", "uhr": "watch", "brille": "glasses", "schirm": "umbrella",
    "jacke": "jacket", "werkzeug": "tools", "hund": "dog", "katze": "cat", "haustier": "pet",
    "kind": "child", "spielzeug": "toy", "buch": "book", "geschenk": "gift",
    "sonstiges": "other",
}


def migrate(cid):
    cid = LEGACY.get(cid, cid)
    return cid if cid in BY_ID else None


def _position(word, text):
    """Where the keyword starts in the name, or None.

    Short words count only at the start of a word ("rad" not in "Paradies"),
    longer ones anywhere ("Wohnungsschlüssel").
    """
    if len(word) < 5:
        m = re.search(r"(?:^|[^\w])(" + re.escape(word) + ")", text)
        return m.start(1) if m else None
    i = text.find(word)
    return i if i >= 0 else None


def guess(name):
    """The word that comes first in the name wins; on a tie the longer one
    ("Autoschlüssel" is a car, "Cartera" a wallet and not a car)."""
    text = (name or "").lower()
    best = None
    for order, (cid, _label, _emoji, words) in enumerate(CATEGORIES):
        for word in words:
            pos = _position(word, text)
            if pos is not None:
                key = (pos, -len(word), order)
                if best is None or key < best[0]:
                    best = (key, cid)
    return best[1] if best else DEFAULT


def emoji(cid):
    return BY_ID.get(cid, BY_ID[DEFAULT])[2]


def label(cid):
    return _(BY_ID.get(cid, BY_ID[DEFAULT])[1])
