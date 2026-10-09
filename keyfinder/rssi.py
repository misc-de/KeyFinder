"""Smooth the signal strength and derive proximity and trend (warmer/colder).

BlueZ reports RSSI only when it changes, so everything is computed over time
windows rather than over a fixed number of samples.
"""

import time
from collections import deque
from statistics import median

from .i18n import _

WINDOW_S = 2.0          # current value = median of the last 2 s
TREND_BACK_S = 6.0      # compared with the median of the 2–6 s before
TREND_DB = 3.0          # difference from which it is warmer/colder
LOST_AFTER_S = 15.0     # no report for this long = out of range
KEEP_S = 30.0

WARMER, COLDER, STEADY, UNKNOWN = "warmer", "colder", "steady", "unknown"

# Same steps as BT-Scanner.
VERY_CLOSE, CLOSE, MEDIUM, FAR, OUT_OF_RANGE = "very_close", "close", "medium", "far", "out"


def level(rssi):
    if rssi is None:
        return OUT_OF_RANGE
    if rssi >= -55:
        return VERY_CLOSE
    if rssi >= -67:
        return CLOSE
    if rssi >= -78:
        return MEDIUM
    return FAR


def proximity(rssi):
    """Proximity as text for the user."""
    return {VERY_CLOSE: _("very close"), CLOSE: _("close"), MEDIUM: _("medium"),
            FAR: _("far"), OUT_OF_RANGE: _("out of range")}[level(rssi)]


def fraction(rssi):
    """0…1 for a level bar (−100 dBm … −40 dBm)."""
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
        """Smoothed value in dBm, or None when nothing came for too long."""
        age = self.last_seen(address)
        if age is None or age > LOST_AFTER_S:
            return None
        recent = self._window(address, 0, WINDOW_S)
        if recent:
            return round(median(recent))
        # No change lately: the last value still holds.
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
