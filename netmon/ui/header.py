#!/usr/bin/env python3
"""
Header bar component for netmon panel.
"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Pango

from ..config import COL_PX, SORTABLE
from .cells import vsep


class HeaderBar:
    def __init__(self, panel, on_drag_start, on_drag_end, on_drag_motion,
                 on_toggle_states, on_col_header_click):
        self.panel = panel
        self.on_drag_start = on_drag_start
        self.on_drag_end = on_drag_end
        self.on_drag_motion = on_drag_motion
        self.on_toggle_states = on_toggle_states
        self.on_col_header_click = on_col_header_click
        
        self._col_head_labels = {}
        self.state_toggle = None
        self.vpn_badge = None
        self.iface_label = None
        self.ip_value = None
        self.loc_value = None
        self.count_badge = None
        self.updated_label = None
        
        self.build()

    def build(self):
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        left_spacer = Gtk.Box()
        header_box.pack_start(left_spacer, True, True, 0)

        self.vpn_badge = Gtk.Label()
        self.vpn_badge.get_style_context().add_class("badge")
        header_box.pack_start(self.vpn_badge, False, False, 0)

        self.iface_label = Gtk.Label()
        self.iface_label.get_style_context().add_class("stat-label")
        header_box.pack_start(self.iface_label, False, False, 0)

        header_box.pack_start(vsep(), False, False, 2)

        ip_wrap = Gtk.Box(spacing=6)
        ip_key = Gtk.Label(label="IP")
        ip_key.get_style_context().add_class("stat-label")
        self.ip_value = Gtk.Label()
        self.ip_value.get_style_context().add_class("stat-value")
        ip_wrap.pack_start(ip_key, False, False, 0)
        ip_wrap.pack_start(self.ip_value, False, False, 0)
        header_box.pack_start(ip_wrap, False, False, 0)

        loc_wrap = Gtk.Box(spacing=6)
        loc_key = Gtk.Label(label="LOC")
        loc_key.get_style_context().add_class("stat-label")
        self.loc_value = Gtk.Label(label="\u2026")
        self.loc_value.get_style_context().add_class("stat-value")
        self.loc_value.set_ellipsize(Pango.EllipsizeMode.END)
        self.loc_value.set_max_width_chars(22)
        loc_wrap.pack_start(loc_key, False, False, 0)
        loc_wrap.pack_start(self.loc_value, False, False, 0)
        header_box.pack_start(loc_wrap, False, False, 0)

        header_box.pack_start(vsep(), False, False, 2)

        self.count_badge = Gtk.Label()
        self.count_badge.get_style_context().add_class("badge")
        self.count_badge.get_style_context().add_class("badge-count")
        header_box.pack_start(self.count_badge, False, False, 0)

        self.state_toggle = Gtk.Label(label="ESTAB")
        self.state_toggle.get_style_context().add_class("toggle-btn")
        toggle_evbox = Gtk.EventBox()
        toggle_evbox.add(self.state_toggle)
        toggle_evbox.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        toggle_evbox.connect("button-press-event", self.on_toggle_states)
        header_box.pack_start(toggle_evbox, False, False, 0)

        self.updated_label = Gtk.Label(label="updated 0s ago")
        self.updated_label.get_style_context().add_class("updated-label")
        header_box.pack_start(self.updated_label, False, False, 0)

        right_spacer = Gtk.Box()
        header_box.pack_start(right_spacer, True, True, 0)

        header_evbox = Gtk.EventBox()
        header_evbox.add(header_box)
        header_evbox.set_name("header")
        header_evbox.set_margin_top(10)
        header_evbox.set_margin_bottom(10)
        header_evbox.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        header_evbox.connect("button-press-event", self.on_drag_start)
        header_evbox.connect("button-release-event", self.on_drag_end)
        header_evbox.connect("motion-notify-event", self.on_drag_motion)

        self.header_evbox = header_evbox

    def build_col_header(self):
        col_header = Gtk.Box(spacing=6)
        col_header.get_style_context().add_class("col-header-row")
        for key, label_text in [
            ("proc", "PROC"), ("local", "LOCAL"), ("remote", "REMOTE"),
            ("loc", "LOCATION"), ("state", "STATE"), ("proto", "PROTO"),
            ("rate", "RATE"), ("age", "AGE"), ("kill", ""),
        ]:
            lbl = Gtk.Label(label=label_text, xalign=0)
            lbl.get_style_context().add_class("col-head")
            self._col_head_labels[key] = (lbl, label_text)
            from .cells import _fixed_cell
            cell = _fixed_cell(COL_PX[key], lbl)
            if key in SORTABLE:
                evbox = Gtk.EventBox()
                evbox.add(cell)
                evbox.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
                evbox.connect("button-press-event", self.on_col_header_click, key)
                col_header.pack_start(evbox, False, False, 0)
            else:
                col_header.pack_start(cell, False, False, 0)
        return col_header

    def update_sort_arrows(self, sort_key, sort_reverse):
        for key, (lbl, text) in self._col_head_labels.items():
            ctx = lbl.get_style_context()
            if key == sort_key:
                arrow = " \u25be" if sort_reverse else " \u25b4"
                lbl.set_label(f"{text}{arrow}" if text else "")
                ctx.add_class("col-head-active")
            else:
                lbl.set_label(text)
                ctx.remove_class("col-head-active")

    def update_vpn_status(self, vpn, iface):
        ctx = self.vpn_badge.get_style_context()
        ctx.remove_class("badge-vpn-on")
        ctx.remove_class("badge-vpn-off")
        ctx.add_class("badge-vpn-on" if vpn else "badge-vpn-off")
        self.vpn_badge.set_label("VPN ACTIVE" if vpn else "NO VPN")
        self.iface_label.set_label(f"({iface or 'n/a'})")

    def update_ip_location(self, pub_ip, loc_label, flag):
        self.ip_value.set_label(pub_ip)
        if pub_ip != "unknown":
            self.loc_value.set_label(f"{flag} {loc_label}".strip())
        else:
            self.loc_value.set_label("?")

    def update_count(self, count):
        self.count_badge.set_label(f"{count} connections")

    def update_toggle_state(self, show_all_states):
        ctx = self.state_toggle.get_style_context()
        if show_all_states:
            self.state_toggle.set_label("ALL")
            ctx.add_class("toggle-btn-active")
        else:
            self.state_toggle.set_label("ESTAB")
            ctx.remove_class("toggle-btn-active")

    def update_timestamp(self, secs):
        self.updated_label.set_label(f"updated {secs}s ago")

    def get_widget(self):
        return self.header_evbox