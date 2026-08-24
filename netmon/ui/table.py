#!/usr/bin/env python3
"""
Table/rows rendering for netmon panel.

There is a single render path: privacy masking is applied per-cell while
rendering, so sorting, row count, hover, rates and ages behave identically
whether you are on a call or not.
"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango

from ..config import COL_PX, STATE_CSS, proc_color, flag_emoji
from .. import privacy
from .cells import text_cell, pill_cell, kill_cell, _fixed_cell


class TableView:
    def __init__(self, panel, on_kill_clicked):
        self.panel = panel
        self.on_kill_clicked = on_kill_clicked
        self.rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.chips_box = Gtk.Box(spacing=8)
        self.chips_box.get_style_context().add_class("chips-row")
        self.chips_box.set_halign(Gtk.Align.CENTER)
        self._last_conns = []

    def get_rows_widget(self):
        scroller = Gtk.ScrolledWindow()
        scroller.set_propagate_natural_height(True)
        scroller.set_min_content_height(20)
        scroller.set_max_content_height(400)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_overlay_scrolling(False)
        scroller.add(self.rows_box)
        return scroller

    def get_chips_widget(self):
        return self.chips_box

    def _fmt_rate(self, bytes_per_sec):
        if bytes_per_sec is None or bytes_per_sec <= 0:
            return "-"
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec:.0f}B/s"
        if bytes_per_sec < 1024 * 1024:
            return f"{bytes_per_sec / 1024:.1f}KB/s"
        return f"{bytes_per_sec / (1024 * 1024):.1f}MB/s"

    def update_chips(self, conns, mode=privacy.LIVE):
        for child in self.chips_box.get_children():
            self.chips_box.remove(child)
        counts = {}
        for c in conns:
            counts[c["proc"]] = counts.get(c["proc"], 0) + 1
        for p, c in sorted(counts.items(), key=lambda kv: -kv[1])[:5]:
            shown = privacy.mask_proc(p, mode)
            chip = Gtk.Label()
            chip.set_markup(
                f'<span foreground="{proc_color(privacy.color_seed(p, mode))}">'
                f'{GLib.markup_escape_text(shown)}</span>'
                f'<span foreground="#6b7394"> \u00b7 {c}</span>'
            )
            chip.get_style_context().add_class("chip")
            self.chips_box.pack_start(chip, False, False, 0)
        self.chips_box.show_all()

    def render_rows(self, conns, sort_key, sort_reverse, mode=privacy.LIVE):
        self._last_conns = conns
        tips = privacy.show_tooltips(mode)
        killable = privacy.allow_kill(mode)

        for child in self.rows_box.get_children():
            self.rows_box.remove(child)

        sort_key_fn = {
            "proc": lambda c: c["proc"].lower(),
            "loc": lambda c: c["loc_label"].lower(),
            "state": lambda c: c["state"],
            "proto": lambda c: c["proto"],
            "rate": lambda c: c["rate"],
            "age": lambda c: c["age"],
        }.get(sort_key, lambda c: c["age"])
        sorted_conns = sorted(conns, key=sort_key_fn, reverse=sort_reverse)[:30]

        for i, c in enumerate(sorted_conns):
            row = Gtk.Box(spacing=10)
            row.get_style_context().add_class("row-even" if i % 2 == 0 else "row-odd")

            proc_shown = privacy.mask_proc(c["proc"], mode)
            new_prefix = '<span foreground="#86efac">\u25c6 </span>' if c["is_new"] else ""
            proc_label = Gtk.Label(xalign=0)
            proc_label.set_markup(
                f'{new_prefix}'
                f'<span foreground="{proc_color(privacy.color_seed(c["proc"], mode))}">\u25cf</span> '
                f'<span foreground="#dbe4ff">{GLib.markup_escape_text(proc_shown)}</span>'
            )
            proc_label.set_ellipsize(Pango.EllipsizeMode.END)
            if tips:
                proc_label.set_tooltip_text(c["proc"] + (" (new)" if c["is_new"] else ""))
            row.pack_start(_fixed_cell(COL_PX["proc"], proc_label), False, False, 0)

            local = privacy.mask_addr(c["local"], mode)
            remote = privacy.mask_addr(c["remote"], mode)
            local_classes = ("cell",) if local == c["local"] else ("cell", "cell-masked")
            remote_classes = ("cell",) if remote == c["remote"] else ("cell", "cell-masked")
            row.pack_start(
                text_cell(local, COL_PX["local"], local_classes,
                          tooltip=c["local"] if tips else None),
                False, False, 0)
            row.pack_start(
                text_cell(remote, COL_PX["remote"], remote_classes,
                          tooltip=c["remote"] if tips else None),
                False, False, 0)

            loc_shown = privacy.mask_location(c["loc_label"], mode)
            flag = flag_emoji(c["loc_cc"]) if mode != privacy.STRICT else ""
            loc_text = f"{flag} {loc_shown}".strip() if flag else loc_shown
            if c["loc_label"] in ("local", "\u2026"):
                loc_classes = ("cell", "cell-muted")
            elif loc_shown != c["loc_label"]:
                loc_classes = ("cell", "cell-masked")
            else:
                loc_classes = ("cell",)
            row.pack_start(
                text_cell(loc_text, COL_PX["loc"], loc_classes,
                          tooltip=c["loc_label"] if tips else None),
                False, False, 0)

            state_variant = STATE_CSS.get(c["state"], "state-other")
            row.pack_start(pill_cell(c["state"], COL_PX["state"], state_variant, "state-pill"),
                           False, False, 0)
            row.pack_start(pill_cell(c["proto"], COL_PX["proto"], c["proto"]), False, False, 0)

            rate_classes = ("cell",) if c["rate"] > 0 else ("cell", "cell-dim")
            row.pack_start(text_cell(self._fmt_rate(c["rate"]), COL_PX["rate"], rate_classes),
                           False, False, 0)
            row.pack_start(text_cell(f"{c['age']}s", COL_PX["age"], ("cell", "cell-dim")),
                           False, False, 0)

            row.pack_start(
                kill_cell(proc_shown, c["pid"] if killable else None,
                          self.on_kill_clicked,
                          disabled_tip="Locked while STRICT privacy is on"
                          if not killable else None),
                False, False, 0)

            row_evbox = Gtk.EventBox()
            row_evbox.add(row)
            self.rows_box.pack_start(row_evbox, False, False, 0)

        if not sorted_conns:
            empty = Gtk.Label(label="\u2014 no active connections \u2014", xalign=0)
            empty.get_style_context().add_class("cell-muted")
            empty.set_margin_top(6)
            empty.set_margin_bottom(6)
            self.rows_box.pack_start(empty, False, False, 4)

        self.rows_box.show_all()
