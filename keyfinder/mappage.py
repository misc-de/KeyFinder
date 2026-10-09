"""Kartenseite: letzter bekannter Ort eines Tags mit Umkreis (libshumate, OSM)."""

import math
import time

from gi.repository import Adw, Gdk, Gtk

from . import categories
from .locations import circle, radius

try:
    import gi
    gi.require_version("Shumate", "1.0")
    from gi.repository import Shumate
except (ImportError, ValueError):
    Shumate = None


def when_text(ts, now=None):
    """„heute 14:32“, „gestern 09:10“ oder „12.10. 14:32“."""
    now = now or time.time()
    t, n = time.localtime(ts), time.localtime(now)
    clock = time.strftime("%H:%M", t)
    days = (time.mktime(n[:3] + (0, 0, 0) + n[6:]) - time.mktime(t[:3] + (0, 0, 0) + t[6:]))
    days = round(days / 86400)
    if days == 0:
        return f"heute {clock}"
    if days == 1:
        return f"gestern {clock}"
    return time.strftime("%d.%m. ", t) + clock


def distance_text(meters):
    if meters < 1000:
        return f"{int(meters / 10.0 + 0.5) * 10 or 10} m"
    return f"{meters / 1000:.1f} km".replace(".", ",")


def summary(entry):
    """Eine Zeile für die Suchansicht."""
    if not entry or entry.get("seen") is None:
        return "Noch kein Ort gespeichert"
    seen = when_text(entry["seen"])
    r = radius(entry)
    if r is None:
        return f"Zuletzt gesehen {seen}, ohne Standort"
    return f"Zuletzt gesehen {seen} · Umkreis ca. {distance_text(r)}"


def zoom_for(lat, meters, pixels=110):
    """Zoomstufe, bei der der Umkreis etwa `pixels` Pixel Radius hat."""
    per_px = meters / pixels
    z = math.log2(156543.03 * math.cos(math.radians(lat)) / max(per_px, 0.01))
    return max(3.0, min(18.0, z))


def build(tag, entry, parent):
    lat, lon = entry["lat"], entry["lon"]
    r = radius(entry)
    view = Adw.ToolbarView()
    view.add_top_bar(Adw.HeaderBar())
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    if Shumate:
        smap = Shumate.SimpleMap(vexpand=True)
        registry = Shumate.MapSourceRegistry.new_with_defaults()
        smap.set_map_source(registry.get_by_id(Shumate.MAP_SOURCE_OSM_MAPNIK))
        viewport = smap.get_viewport()

        area = Shumate.PathLayer.new(viewport)
        fill = Gdk.RGBA()
        fill.parse("rgba(53,132,228,0.22)")
        stroke = Gdk.RGBA()
        stroke.parse("rgba(28,113,216,0.9)")
        area.set_fill(True)
        area.set_closed(True)
        area.set_fill_color(fill)
        area.set_stroke_color(stroke)
        area.set_stroke_width(2)
        for plat, plon in circle(lat, lon, r):
            area.add_node(Shumate.Coordinate.new_full(plat, plon))
        smap.add_overlay_layer(area)

        markers = Shumate.MarkerLayer.new(viewport)
        mark = Shumate.Marker()
        pin = Gtk.Label(label=categories.emoji(tag.get("category")))
        pin.add_css_class("map-pin")
        mark.set_child(pin)
        mark.set_location(lat, lon)
        markers.add_marker(mark)
        smap.add_overlay_layer(markers)

        viewport.set_zoom_level(zoom_for(lat, r))
        smap.get_map().center_on(lat, lon)
        box.append(smap)
    else:
        box.append(Adw.StatusPage(icon_name="mark-location-symbolic", vexpand=True,
                                  title="Kartenansicht nicht verfügbar",
                                  description="libshumate fehlt (gir1.2-shumate-1.0)."))

    info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=12,
                   margin_bottom=12, margin_start=16, margin_end=16)
    head = Gtk.Label(xalign=0, wrap=True,
                     label=f"Zuletzt gesehen {when_text(entry['seen'])} · "
                           f"Umkreis ca. {distance_text(r)}")
    head.add_css_class("heading")
    info.append(head)
    gap = abs(entry.get("fix_time", 0) - entry.get("seen", 0))
    detail = (f"Ortung auf ±{distance_text(entry.get('accuracy', 0))}"
              + (f", {int(gap // 60)} min neben der Sichtung" if gap >= 60 else ""))
    note = Gtk.Label(xalign=0, wrap=True, label=detail)
    note.add_css_class("dim-label")
    info.append(note)
    open_btn = Gtk.Button(label="In Karten öffnen", halign=Gtk.Align.START, margin_top=6)
    open_btn.add_css_class("pill")
    open_btn.connect("clicked", lambda _b: Gtk.UriLauncher.new(
        f"geo:{lat:.6f},{lon:.6f};u={r}").launch(parent, None, None, None))
    info.append(open_btn)
    box.append(info)

    view.set_content(box)
    return Adw.NavigationPage(child=view, title=tag["name"])
