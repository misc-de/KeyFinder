"""Signalstärke glätten und daraus Nähe und Tendenz (wärmer/kälter) ableiten.

BlueZ meldet RSSI nur bei Änderung, deshalb wird über Zeitfenster gerechnet
und nicht über eine feste Zahl von Messwerten.
"""

import time
from collections import deque
from statistics import median

WINDOW_S = 2.0          # aktueller Wert = Median der letzten 2 s
TREND_BACK_S = 6.0      # verglichen mit dem Median von 2–6 s davor
TREND_DB = 3.0          # ab dieser Differenz: wärmer/kälter
LOST_AFTER_S = 15.0     # so lange ohne Meldung = nicht in Reichweite
KEEP_S = 30.0

WARMER, COLDER, STEADY, UNKNOWN = "wärmer", "kälter", "gleich", "unbekannt"


def proximity(rssi):
    """Gleiche Stufen wie BT-Scanner."""
    if rssi is None:
        return "nicht in Reichweite"
    if rssi >= -55:
        return "sehr nah"
    if rssi >= -67:
        return "nah"
    if rssi >= -78:
        return "mittel"
    return "weit"


def fraction(rssi):
    """0…1 für einen Pegelbalken (−100 dBm … −40 dBm)."""
    if rssi is None:
        return 0.0
    return max(0.0, min(1.0, (rssi + 100) / 60.0))


class SignalTracker:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.samples = {}

    def add(self, address, rssi):
        now = self.clock()
        q = self.samples.setdefault(address.upper(), deque())
        q.append((now, rssi))
        while q and now - q[0][0] > KEEP_S:
            q.popleft()

    def _window(self, address, start, end):
        now = self.clock()
        q = self.samples.get(address.upper(), ())
        return [r for t, r in q if start <= now - t < end]

    def last_seen(self, address):
        q = self.samples.get(address.upper())
        return self.clock() - q[-1][0] if q else None

    def current(self, address):
        """Geglätteter Wert in dBm oder None, wenn zu lange nichts kam."""
        age = self.last_seen(address)
        if age is None or age > LOST_AFTER_S:
            return None
        recent = self._window(address, 0, WINDOW_S)
        if recent:
            return round(median(recent))
        # Keine Änderung in letzter Zeit: letzter Wert gilt weiter.
        return self.samples[address.upper()][-1][1]

    def trend(self, address):
        now_val = self.current(address)
        if now_val is None:
            return UNKNOWN
        before = self._window(address, WINDOW_S, TREND_BACK_S)
        if not before:
            return UNKNOWN
        diff = now_val - median(before)
        if diff >= TREND_DB:
            return WARMER
        if diff <= -TREND_DB:
            return COLDER
        return STEADY
