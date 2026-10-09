"""Key Finder: iTags anlernen, piepen lassen, per Signalstärke suchen."""

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from . import categories, mappage, rssi, service  # noqa: E402
from .bluez import BlueZ, IMMEDIATE_ALERT, ITAG_SERVICE, LINK_LOSS  # noqa: E402
from .locations import LocationStore  # noqa: E402
from .store import TagStore  # noqa: E402

APP_ID = "io.github.miscde.KeyFinder"
BEEP_S = 10            # so lange piept der Tag, dann wird er abgeschaltet
TICK_MS = 500
TAG_WORDS = ("itag", "tag", "find", "key", "smart", "track", "anti", "lost")

CSS = b"""
.rssi-big { font-size: 48px; font-weight: 800; }
.trend { font-size: 22px; font-weight: 700; }
levelbar.signal block.filled { background-color: @accent_bg_color; }
.tile { padding: 12px; }
.tile-name { font-weight: 700; }
.tile-value { font-size: 22px; font-weight: 800; }
flowboxchild { padding: 0; border-radius: 12px; }
.tile-emoji { font-size: 76px; opacity: 0.16; filter: grayscale(100%); }
.detail-emoji { font-size: 56px; opacity: 0.55; filter: grayscale(100%); }
.cat-grid button { min-width: 40px; min-height: 40px; padding: 0; font-size: 22px; }
.map-pin { font-size: 34px; }
.cat-grid button:checked { background-color: alpha(@accent_bg_color, 0.35); }
"""


class Square(Gtk.Widget):
    """Hält sein Kind quadratisch: Höhe = zugeteilte Breite."""

    def __init__(self, child):
        super().__init__()
        self.child = child
        child.set_parent(self)

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, orientation, for_size):
        cmin, cnat, _b, _b2 = self.child.measure(orientation, for_size)
        if orientation == Gtk.Orientation.VERTICAL and for_size > 0:
            return max(cmin, for_size), max(cnat, for_size), -1, -1
        return cmin, max(cnat, 150), -1, -1

    def do_size_allocate(self, width, height, baseline):
        self.child.allocate(width, height, baseline, None)

    def do_dispose(self):
        if self.child:
            self.child.unparent()
            self.child = None


def looks_like_tag(dev):
    if {IMMEDIATE_ALERT, LINK_LOSS, ITAG_SERVICE} & set(dev["uuids"]):
        return True
    return any(w in dev["name"].lower() for w in TAG_WORDS)


def dbm(value):
    return "–" if value is None else f"{value} dBm".replace("-", "−")


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Key Finder")
        self.set_default_size(360, 680)
        self.bluez = BlueZ()
        self.tracker = rssi.SignalTracker()
        self.store = TagStore()
        self.locations = LocationStore()
        self.beeping = {}      # Adresse -> GLib-Timeout zum Abschalten
        self.busy = set()      # Adressen mit laufendem Verbindungsaufbau

        self.toasts = Adw.ToastOverlay()
        self.nav = Adw.NavigationView()
        self.toasts.set_child(self.nav)
        self.set_content(self.toasts)

        self.nav.add(self._build_main_page())
        self.nav.connect("popped", self._on_popped)
        self.detail = None
        self.learn = None

        self.bluez.connect("rssi", lambda _b, addr, value: self.tracker.add(addr, value))
        self.bluez.connect("adapter-changed", lambda _b: self._update_banner())
        self.bluez.start_discovery()
        self.connect("close-request", self._on_close)
        GLib.timeout_add(TICK_MS, self._tick)
        self._rebuild_tags()
        self._update_banner()
        service.sync(self.store)   # Dienst passend zu den gespeicherten Tags

    def _on_popped(self, _nav, page):
        if self.detail and page is self.detail.page:
            self.detail = None
        elif page is getattr(self, "learn_page", None):
            self.learn = None

    # --- Hauptseite: angelernte Tags -----------------------------------

    def _build_main_page(self):
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Tag anlernen")
        add.connect("clicked", lambda _b: self.open_learn())
        header.pack_end(add)
        view.add_top_bar(header)

        self.banner = Adw.Banner(title="Bluetooth ist ausgeschaltet",
                                 button_label="Einschalten")
        self.banner.connect("button-clicked", lambda _b: self.bluez.power_on(self._power_done))
        view.add_top_bar(self.banner)

        self.main_stack = Gtk.Stack()
        empty = Adw.StatusPage(icon_name="bluetooth-symbolic",
                               title="Noch kein Tag angelernt",
                               description="Tag einschalten, nah ans Handy halten und anlernen.")
        btn = Gtk.Button(label="Tag anlernen", halign=Gtk.Align.CENTER)
        btn.add_css_class("pill")
        btn.add_css_class("suggested-action")
        btn.connect("clicked", lambda _b: self.open_learn())
        empty.set_child(btn)
        self.main_stack.add_named(empty, "empty")

        self.tag_list = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                                    min_children_per_line=2, max_children_per_line=3,
                                    column_spacing=12, row_spacing=12,
                                    activate_on_single_click=True, valign=Gtk.Align.START)
        self.tag_list.connect("child-activated", lambda _f, child: self.open_detail(child.address))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                      margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        box.append(self.tag_list)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        scroller.set_child(Adw.Clamp(child=box, maximum_size=600))
        self.main_stack.add_named(scroller, "list")

        view.set_content(self.main_stack)
        return Adw.NavigationPage(child=view, title="Key Finder", tag="main")

    def _rebuild_tags(self):
        self.tag_list.remove_all()
        self.tag_rows = {}
        for tag in self.store.tags:
            tile = self._build_tile(tag)
            self.tag_list.append(tile)
            self.tag_rows[tag["address"]] = tile
        self.main_stack.set_visible_child_name("list" if self.store.tags else "empty")
        self._update_tags()

    def _build_tile(self, tag):
        """Quadratische Kachel: Name, Signal, Nähe, Pegel und Glocke."""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.add_css_class("tile")
        name = Gtk.Label(label=tag["name"], xalign=0, wrap=True, lines=2,
                         wrap_mode=Pango.WrapMode.WORD_CHAR, ellipsize=Pango.EllipsizeMode.END)
        name.add_css_class("tile-name")
        value = Gtk.Label(xalign=0, vexpand=True, valign=Gtk.Align.END)
        value.add_css_class("tile-value")
        status = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        status.add_css_class("dim-label")
        bar = Gtk.LevelBar(min_value=0, max_value=1, hexpand=True, valign=Gtk.Align.CENTER)
        bar.add_css_class("signal")
        btn = self._beep_button(tag["address"])
        btn.add_css_class("circular")
        bottom = Gtk.Box(spacing=8, margin_top=6)
        bottom.append(bar)
        bottom.append(btn)
        for w in (name, value, status, bottom):
            card.append(w)

        # Symbol als blasses Wasserzeichen hinter dem Inhalt
        mark = Gtk.Label(label=categories.emoji(tag.get("category")), halign=Gtk.Align.END,
                         valign=Gtk.Align.CENTER, margin_end=8, can_target=False)
        mark.add_css_class("tile-emoji")
        layers = Gtk.Overlay(child=mark)
        layers.add_overlay(card)
        frame = Gtk.Box()
        frame.add_css_class("card")
        layers.set_hexpand(True)
        frame.append(layers)

        child = Gtk.FlowBoxChild(child=Square(frame))
        child.address = tag["address"]
        child.value, child.status, child.bar, child.btn = value, status, bar, btn
        return child

    def _status_word(self, address):
        if address in self.busy:
            return "verbinde …"
        if address in self.beeping:
            return "piept"
        dev = self.bluez.device(address)
        if dev and dev["connected"]:
            return "verbunden"
        return rssi.proximity(self.tracker.current(address))

    def _beep_button(self, address):
        btn = Gtk.Button(icon_name="audio-volume-high-symbolic", valign=Gtk.Align.CENTER,
                         tooltip_text="Piepen")
        btn.add_css_class("flat")
        btn.connect("clicked", lambda _b: self.toggle_beep(address))
        btn.address = address
        return btn

    def _sync_beep_button(self, btn):
        beeping = btn.address in self.beeping
        btn.set_icon_name("media-playback-stop-symbolic" if beeping
                          else "audio-volume-high-symbolic")
        btn.set_tooltip_text("Piepen beenden" if beeping else "Piepen")
        btn.set_sensitive(btn.address not in self.busy)

    def _status_text(self, address):
        value = self.tracker.current(address)
        dev = self.bluez.device(address)
        if address in self.busy:
            return "verbinde …"
        if address in self.beeping:
            return "piept"
        if dev and dev["connected"]:
            return "verbunden"
        if value is None:
            return "nicht in Reichweite"
        return f"{dbm(value)} · {rssi.proximity(value)}"

    def _update_tags(self):
        for address, tile in self.tag_rows.items():
            value = self.tracker.current(address)
            tile.value.set_label(dbm(value))
            tile.status.set_label(self._status_word(address))
            self._sync_beep_button(tile.btn)
            tile.bar.set_value(rssi.fraction(value))

    def _update_banner(self):
        if not self.bluez.ready:
            self.banner.set_revealed(False)
        elif not self.bluez.adapter_path:
            self.banner.set_title("Kein Bluetooth-Adapter gefunden")
            self.banner.set_button_label(None)
            self.banner.set_revealed(True)
        else:
            self.banner.set_title("Bluetooth ist ausgeschaltet")
            self.banner.set_button_label("Einschalten")
            self.banner.set_revealed(not self.bluez.powered)

    def _power_done(self, error):
        if error:
            self.toast(f"Bluetooth ließ sich nicht einschalten: {error}")
        else:
            self.bluez.start_discovery()

    # --- Piepen --------------------------------------------------------

    def toggle_beep(self, address):
        if address in self.busy:
            return
        if address in self.beeping:
            self.stop_beep(address)
            return
        self.busy.add(address)
        self._update_all()

        def done(error):
            self.busy.discard(address)
            if error:
                self.toast(error)
            else:
                self.beeping[address] = GLib.timeout_add_seconds(
                    BEEP_S, self._beep_timeout, address)
            self._update_all()
        self.bluez.beep(address, 2, done)

    def _beep_timeout(self, address):
        self.beeping.pop(address, None)   # Quelle endet mit return False
        self.stop_beep(address)
        return False

    def stop_beep(self, address):
        source = self.beeping.pop(address, None)
        if source:
            GLib.source_remove(source)
        self.bluez.beep(address, 0, lambda error: self._update_all(), disconnect=True)
        self._update_all()
        return False

    # --- Suchseite -----------------------------------------------------

    def open_detail(self, address):
        tag = self.store.get(address)
        if not tag:
            return
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        menu = Gio.Menu()
        menu.append("Bearbeiten", "tag.rename")
        menu.append("Entfernen", "tag.remove")
        header.pack_end(Gtk.MenuButton(icon_name="view-more-symbolic", menu_model=menu))
        view.add_top_bar(header)

        actions = Gio.SimpleActionGroup()
        for name, func in (("rename", self._rename), ("remove", self._remove)):
            action = Gio.SimpleAction(name=name)
            action.connect("activate", lambda _a, _p, f=func: f(address))
            actions.add_action(action)
        view.insert_action_group("tag", actions)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, valign=Gtk.Align.CENTER,
                      margin_start=24, margin_end=24, margin_top=24, margin_bottom=24)
        d = self.detail = type("Detail", (), {})()
        d.address = address
        d.icon = Gtk.Label(label=categories.emoji(tag.get("category")))
        d.icon.add_css_class("detail-emoji")
        d.value = Gtk.Label(label="–")
        d.value.add_css_class("rssi-big")
        d.prox = Gtk.Label()
        d.prox.add_css_class("title-3")
        d.bar = Gtk.LevelBar(min_value=0, max_value=1, height_request=14)
        d.bar.add_css_class("signal")
        d.trend = Gtk.Label()
        d.trend.add_css_class("trend")
        hint = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER,
                         label="Langsam durch die Räume gehen: „wärmer“ heißt, du kommst "
                               "näher. Das Handy dabei nicht abdecken.")
        hint.add_css_class("dim-label")
        d.beep = Gtk.Button(label="Piepen", halign=Gtk.Align.CENTER, width_request=200)
        d.beep.add_css_class("pill")
        d.beep.add_css_class("suggested-action")
        d.beep.connect("clicked", lambda _b: self.toggle_beep(address))
        d.map = Gtk.Button(label="Auf der Karte", halign=Gtk.Align.CENTER, width_request=200)
        d.map.add_css_class("pill")
        d.map.connect("clicked", lambda _b: self.open_map(address))
        d.where = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        d.where.add_css_class("dim-label")
        d.where.add_css_class("caption")
        track = Adw.SwitchRow(title="Standort merken",
                              subtitle="Merkt sich im Hintergrund, wo der Tag zuletzt war",
                              active=bool(tag.get("track")))
        track.connect("notify::active", lambda row, _p: self._set_track(address, row.get_active()))
        group = Adw.PreferencesGroup(margin_top=8)
        group.add(track)
        for w in (d.icon, d.value, d.prox, d.bar, d.trend, hint, d.beep, d.map, d.where, group):
            box.append(w)

        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        scroller.set_child(Adw.Clamp(child=box, maximum_size=480))
        view.set_content(scroller)
        # ohne Tag: ein zweites Öffnen während der Zurück-Animation wäre sonst
        # ein doppelter Tag und libadwaita würde die Seite verweigern
        d.page = Adw.NavigationPage(child=view, title=tag["name"])
        self.nav.push(d.page)
        self._update_detail()

    def _update_detail(self):
        d = self.detail
        if not d:
            return
        value = self.tracker.current(d.address)
        d.value.set_label(dbm(value))
        dev = self.bluez.device(d.address)
        if value is None and dev and dev["connected"]:
            d.prox.set_label("verbunden")
        else:
            d.prox.set_label(rssi.proximity(value))
        d.bar.set_value(rssi.fraction(value))
        trend = self.tracker.trend(d.address)
        text = {rssi.WARMER: "▲ wärmer", rssi.COLDER: "▼ kälter",
                rssi.STEADY: "● gleich", rssi.UNKNOWN: ""}[trend]
        d.trend.set_label(text)
        for cls in ("success", "error", "dim-label"):
            d.trend.remove_css_class(cls)
        d.trend.add_css_class({rssi.WARMER: "success", rssi.COLDER: "error"}.get(trend, "dim-label"))
        entry = self.locations.get(d.address)
        d.map.set_sensitive(bool(entry and entry.get("lat") is not None))
        tag = self.store.get(d.address) or {}
        d.where.set_label(mappage.summary(entry) if (entry or tag.get("track"))
                          else "„Standort merken“ einschalten, um den letzten Ort zu sehen")
        if d.address in self.busy:
            d.beep.set_label("Verbinde …")
            d.beep.set_sensitive(False)
        else:
            d.beep.set_sensitive(True)
            d.beep.set_label("Stopp" if d.address in self.beeping else "Piepen")

    def _set_track(self, address, on):
        self.store.set_track(address, on)
        self._update_detail()

        def done(error):
            if error:
                self.toast("Hintergrunddienst ließ sich nicht schalten")
        service.sync(self.store, done, restart=True)

    def open_map(self, address):
        entry = self.locations.get(address)
        tag = self.store.get(address)
        if tag and entry and entry.get("lat") is not None:
            self.nav.push(mappage.build(tag, entry, self))

    def _rename(self, address):
        tag = self.store.get(address)

        def save(name, category):
            self.store.rename(address, name, category)
            self._rebuild_tags()
            if self.detail and self.detail.address == address:
                self.detail.page.set_title(name)
                self.detail.icon.set_label(categories.emoji(category))
        self.ask_name("Tag bearbeiten", tag["name"], "Speichern", save,
                      category=tag.get("category"))

    def _remove(self, address):
        tag = self.store.get(address)
        dialog = Adw.AlertDialog(heading=f"„{tag['name']}“ entfernen?",
                                 body="Der Tag kann jederzeit neu angelernt werden.")
        dialog.add_response("cancel", "Abbrechen")
        dialog.add_response("remove", "Entfernen")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(_d, response):
            if response == "remove":
                if address in self.beeping:
                    self.stop_beep(address)
                self.store.remove(address)
                self.locations.remove(address)
                self.locations.save()
                service.sync(self.store, restart=True)
                self._rebuild_tags()
                self.nav.pop_to_tag("main")
        dialog.connect("response", on_response)
        dialog.present(self)

    # --- Anlernen ------------------------------------------------------

    def open_learn(self):
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                      margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        hint = Gtk.Label(wrap=True, xalign=0,
                         label="Tag einschalten (Taste kurz drücken) und direkt neben das "
                               "Handy legen. Er steht dann ganz oben. Mit der Glocke "
                               "lässt sich prüfen, ob es der richtige ist.")
        box.append(hint)
        self.learn_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.learn_list.add_css_class("boxed-list")
        self.learn_list.set_sort_func(self._learn_sort)
        self.learn_list.set_placeholder(Gtk.Label(label="Suche Geräte …", margin_top=24,
                                                  margin_bottom=24))
        self.learn_list.connect("row-activated", lambda _l, row: self._learn_pick(row))
        box.append(self.learn_list)
        self.learn_all = Adw.SwitchRow(title="Auch andere Geräte zeigen",
                                       subtitle="Falls der Tag nicht erkannt wird")
        self.learn_all.connect("notify::active", lambda *_: self._update_learn())
        group = Adw.PreferencesGroup()
        group.add(self.learn_all)
        box.append(group)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        scroller.set_child(Adw.Clamp(child=box, maximum_size=600))
        view.set_content(scroller)
        page = Adw.NavigationPage(child=view, title="Tag anlernen")
        self.learn_page = page
        self.learn = {}
        self.learn_sorted_at = 0
        self.nav.push(page)
        self._update_learn()

    def _learn_sort(self, a, b):
        def key(row):
            value = row.value if row.value is not None else -200
            return (not row.probable, -(value // 5))
        return (key(a) > key(b)) - (key(a) < key(b))

    def _update_learn(self):
        if self.learn is None:
            return
        show_all = self.learn_all.get_active()
        visible = set()
        for dev in self.bluez.devices():
            address = dev["address"].upper()
            value = self.tracker.current(address)
            if value is None and dev["rssi"] is not None:
                value = int(dev["rssi"])
            if value is None or self.store.get(address):
                continue
            probable = looks_like_tag(dev)
            if not probable and not show_all:
                continue
            visible.add(address)
            row = self.learn.get(address)
            fresh = row is None
            if fresh:
                row = Adw.ActionRow(activatable=True)
                row.address = address
                row.btn = self._beep_button(address)
                row.add_suffix(row.btn)
                self.learn[address] = row
            row.value, row.probable = value, probable
            row.dev_name = dev["name"] if dev["has_name"] else ""
            if fresh:   # erst jetzt, die Sortierung braucht value/probable
                self.learn_list.append(row)
            row.set_title(GLib.markup_escape_text(row.dev_name or "Unbekanntes Gerät"))
            if address in self.busy or address in self.beeping:
                status = self._status_text(address)
            else:
                status = f"{dbm(value)} · {rssi.proximity(value)}"
            row.set_subtitle(f"{status} · {address}")
            self._sync_beep_button(row.btn)
        for address in list(self.learn):
            if address not in visible:
                self.learn_list.remove(self.learn.pop(address))
        now = GLib.get_monotonic_time()
        if now - self.learn_sorted_at > 2_000_000:   # Reihenfolge nicht ständig umwerfen
            self.learn_sorted_at = now
            self.learn_list.invalidate_sort()

    def _learn_pick(self, row):
        address = row.address
        default = row.dev_name if row.dev_name and row.dev_name.lower() != "itag" else "Schlüssel"

        def save(name, category):
            if address in self.beeping:
                self.stop_beep(address)
            self.store.add(address, name, category)
            self._rebuild_tags()
            self.nav.pop_to_tag("main")
            self.toast(f"„{name}“ angelernt")
        self.ask_name("Tag anlernen", default, "Anlernen", save)

    # --- Allgemeines ---------------------------------------------------

    def ask_name(self, heading, default, action_label, on_save, category=None):
        """Name und Symbol abfragen; on_save(name, category)."""
        dialog = Adw.AlertDialog(heading=heading, body="Wie soll der Tag heißen?")
        entry = Gtk.Entry(text=default, activates_default=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(entry)
        chosen = Gtk.Label(xalign=0, margin_top=6)
        chosen.add_css_class("dim-label")
        box.append(chosen)

        grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                           min_children_per_line=6, max_children_per_line=8,
                           column_spacing=4, row_spacing=4)
        grid.add_css_class("cat-grid")
        state = {"cat": category or categories.guess(default), "manual": bool(category)}
        buttons = {}
        group = None
        for cid, label, emoji, _words in categories.CATEGORIES:
            btn = Gtk.ToggleButton(label=emoji, tooltip_text=label)
            btn.add_css_class("flat")
            if group:
                btn.set_group(group)
            group = group or btn
            buttons[cid] = btn
            grid.append(btn)

        def show(cid):
            state["cat"] = cid
            chosen.set_label(f"Symbol: {categories.label(cid)}")
            if not buttons[cid].get_active():
                buttons[cid].set_active(True)

        def on_toggled(btn, cid):
            if btn.get_active() and state["cat"] != cid:
                state["manual"] = True
                show(cid)
        for cid, btn in buttons.items():
            btn.connect("toggled", on_toggled, cid)

        def on_name_changed(_e):
            if not state["manual"]:   # Vorschlag folgt dem Namen, bis selbst gewählt
                guessed = categories.guess(entry.get_text())
                if guessed != state["cat"]:
                    state["cat"] = guessed
                    buttons[guessed].set_active(True)
                    chosen.set_label(f"Symbol: {categories.label(guessed)}")
        entry.connect("changed", on_name_changed)
        show(state["cat"])

        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                      propagate_natural_height=True, max_content_height=220)
        scroller.set_child(grid)
        box.append(scroller)
        dialog.set_extra_child(box)
        dialog.add_response("cancel", "Abbrechen")
        dialog.add_response("save", action_label)
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")

        def on_response(_d, response):
            name = entry.get_text().strip()
            if response == "save" and name:
                on_save(name, state["cat"])
        dialog.connect("response", on_response)
        dialog.present(self)
        entry.grab_focus()

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(text), timeout=4))

    def _update_all(self):
        self._update_tags()
        self._update_detail()
        self._update_learn()

    def _tick(self):
        self.locations.reload()   # der Dienst schreibt neue Orte
        self._update_all()
        return True

    def _on_close(self, _w):
        # Synchron: sonst endet der Prozess, bevor der Tag still ist, und BlueZ
        # hält die Verbindung (und damit das Piepen) weiter.
        for address in list(self.beeping):
            GLib.source_remove(self.beeping.pop(address))
            self.bluez.beep_off_sync(address)
        self.bluez.stop_discovery()
        return False


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_startup(self):
        Adw.Application.do_startup(self)
        css = Gtk.CssProvider()
        css.load_from_data(CSS, len(CSS))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        win = self.get_active_window() or Window(self)
        win.present()


def main():
    return App().run(sys.argv)
