#!/usr/bin/env python3
"""
Table/rows rendering for netmon panel.
"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango

from ..config import COL_PX, STATE_CSS, proc_color, flag_emoji, SCREENSHARE_MASK
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

    def update_chips(self, conns):
        for child in self.chips_box.get_children():
            self.chips_box.remove(child)
        counts = {}
        for c in conns:
            counts[c["proc"]] = counts.get(c["proc"], 0) + 1
        for p, c in sorted(counts.items(), key=lambda kv: -kv[1])[:5]:
            chip = Gtk.Label()
            chip.set_markup(
                f'<span foreground="{proc_color(p)}">{GLib.markup_escape_text(p)}</span>'
                f'<span foreground="#6b7394"> \u00b7 {c}</span>'
            )
            chip.get_style_context().add_class("chip")
            self.chips_box.pack_start(chip, False, False, 0)
        self.chips_box.show_all()

    def update_chips_masked(self, mask_proc=False):
        for child in self.chips_box.get_children():
            self.chips_box.remove(child)
        for _ in range(5):
            chip = Gtk.Label()
            if mask_proc:
                chip.set_markup(
                    f'<span foreground="#6b7394">******** \u00b7 **</span>'
                )
            else:
                chip.set_markup(
                    f'<span foreground="#6b7394">process_name \u00b7 **</span>'
                )
            chip.get_style_context().add_class("chip")
            self.chips_box.pack_start(chip, False, False, 0)
        self.chips_box.show_all()

    def render_rows(self, conns, sort_key, sort_reverse):
        self._last_conns = conns
        
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

            new_prefix = '<span foreground="#86efac">\u25c6 </span>' if c["is_new"] else ""
            proc_label = Gtk.Label(xalign=0)
            proc_label.set_markup(
                f'{new_prefix}<span foreground="{proc_color(c["proc"])}">\u25cf</span> '
                f'<span foreground="#dbe4ff">{GLib.markup_escape_text(c["proc"])}</span>'
            )
            proc_label.set_ellipsize(Pango.EllipsizeMode.END)
            tip = c["proc"] + (" (new)" if c["is_new"] else "")
            proc_label.set_tooltip_text(tip)
            row.pack_start(_fixed_cell(COL_PX["proc"], proc_label), False, False, 0)

            row.pack_start(text_cell(c["local"], COL_PX["local"], ("cell",), tooltip=c["local"]), False, False, 0)
            row.pack_start(text_cell(c["remote"], COL_PX["remote"], ("cell",), tooltip=c["remote"]), False, False, 0)

            flag = flag_emoji(c["loc_cc"])
            loc_text = f"{flag} {c['loc_label']}".strip() if flag else c["loc_label"]
            loc_classes = ("cell", "cell-muted") if c["loc_label"] in ("local", "\u2026") else ("cell",)
            row.pack_start(text_cell(loc_text, COL_PX["loc"], loc_classes, tooltip=c["loc_label"]), False, False, 0)

            state_variant = STATE_CSS.get(c["state"], "state-other")
            row.pack_start(pill_cell(c["state"], COL_PX["state"], state_variant, "state-pill"), False, False, 0)

            row.pack_start(pill_cell(c["proto"], COL_PX["proto"], c["proto"]), False, False, 0)

            rate_classes = ("cell",) if c["rate"] > 0 else ("cell", "cell-dim")
            row.pack_start(text_cell(self._fmt_rate(c["rate"]), COL_PX["rate"], rate_classes), False, False, 0)

            row.pack_start(text_cell(f"{c['age']}s", COL_PX["age"], ("cell", "cell-dim")), False, False, 0)

            row.pack_start(kill_cell(c["proc"], c["pid"], self.on_kill_clicked), False, False, 0)

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

    def render_rows_masked(self, conns=None, mask_config=None):
        if mask_config is None:
            mask_config = SCREENSHARE_MASK
            
        for child in self.rows_box.get_children():
            self.rows_box.remove(child)

        # Use actual connections if provided, otherwise show placeholder rows
        display_conns = conns if conns else [None] * 5

        for i, c in enumerate(display_conns[:5]):
            row = Gtk.Box(spacing=10)
            row.get_style_context().add_class("row-even" if i % 2 == 0 else "row-odd")

            # Process - mask based on config
            proc_label = Gtk.Label(xalign=0)
            if mask_config.get("proc", False):
                proc_label.set_markup(f'<span foreground="#6b7394">********</span>')
            else:
                proc_name = c["proc"] if c else "process_name"
                proc_label.set_markup(
                    f'<span foreground="{proc_color(proc_name)}">\u25cf</span> '
                    f'<span foreground="#dbe4ff">{GLib.markup_escape_text(proc_name)}</span>'
                )
            proc_label.set_ellipsize(Pango.EllipsizeMode.END)
            row.pack_start(_fixed_cell(COL_PX["proc"], proc_label), False, False, 0)

            # Local IP - mask based on config
            local_addr = "********" if mask_config.get("local", False) else (c["local"] if c else "local")
            # Remote IP - mask based on config
            remote_addr = "********" if mask_config.get("remote", True) else (c["remote"] if c else "remote")
            row.pack_start(text_cell(local_addr, COL_PX["local"], ("cell",)), False, False, 0)
            row.pack_start(text_cell(remote_addr, COL_PX["remote"], ("cell",)), False, False, 0)

            # Location - mask based on config
            loc_text = "********" if mask_config.get("loc", True) else (c["loc_label"] if c else "location")
            loc_classes = ("cell", "cell-muted") if mask_config.get("loc", True) else ("cell",)
            row.pack_start(text_cell(loc_text, COL_PX["loc"], loc_classes), False, False, 0)

            # State - mask based on config
            state = "******" if mask_config.get("state", False) else (c["state"] if c else "ESTAB")
            state_variant = STATE_CSS.get(state, "state-other") if not mask_config.get("state", False) else "state-other"
            row.pack_start(pill_cell(state, COL_PX["state"], state_variant, "state-pill"), False, False, 0)

            # Proto - mask based on config
            proto = "****" if mask_config.get("proto", False) else (c["proto"] if c else "tcp")
            row.pack_start(pill_cell(proto, COL_PX["proto"], proto), False, False, 0)

            # Rate - mask based on config
            if mask_config.get("rate", False):
                rate = "****"
                rate_classes = ("cell", "cell-dim")
            else:
                rate = self._fmt_rate(c["rate"]) if c and c["rate"] > 0 else "-"
                rate_classes = ("cell",) if c and c["rate"] > 0 else ("cell", "cell-dim")
            row.pack_start(text_cell(rate, COL_PX["rate"], rate_classes), False, False, 0)

            # Age - mask based on config
            age = "**s" if mask_config.get("age", False) else (f"{c['age']}s" if c else "0s")
            row.pack_start(text_cell(age, COL_PX["age"], ("cell", "cell-dim")), False, False, 0)

            # Kill button always masked in screenshare mode
            row.pack_start(kill_cell("********", None, self.on_kill_clicked), False, False, 0)

            row_evbox = Gtk.EventBox()
            row_evbox.add(row)
            self.rows_box.pack_start(row_evbox, False, False, 0)

        self.rows_box.show_all()