#!/usr/bin/env python3
"""
Cell rendering utilities for netmon panel.
"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Pango

from ..config import COL_PX


def _fixed_cell(width, widget):
    """Wrap a widget in a fixed-pixel-width box, left-aligned."""
    box = Gtk.Box()
    box.set_size_request(width, -1)
    widget.set_hexpand(True)
    box.pack_start(widget, True, True, 0)
    return box


def text_cell(text, width, css_classes=(), tooltip=None):
    label = Gtk.Label(label=text, xalign=0)
    label.set_ellipsize(Pango.EllipsizeMode.END)
    for c in css_classes:
        label.get_style_context().add_class(c)
    if tooltip:
        label.set_tooltip_text(tooltip)
    return _fixed_cell(width, label)


def pill_cell(text, width, variant, css_prefix="pill"):
    pill = Gtk.Label(label=text.upper())
    pill.get_style_context().add_class(css_prefix if css_prefix == "state-pill" else "pill")
    pill.get_style_context().add_class(variant)
    box = Gtk.Box()
    box.set_size_request(width, -1)
    box.pack_start(pill, False, False, 0)
    return box


def vsep():
    sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
    sep.get_style_context().add_class("hsep")
    return sep


def kill_cell(proc, pid, on_kill_clicked, disabled_tip=None):
    btn = Gtk.Button(label="\u2715")
    btn.get_style_context().add_class("kill-btn")
    btn.set_sensitive(pid is not None)
    if pid:
        btn.set_tooltip_text(f"Kill {proc} (pid {pid})")
    else:
        btn.set_tooltip_text(disabled_tip or "No permission to see pid")
    btn.connect("clicked", on_kill_clicked, proc, pid)
    box = Gtk.Box()
    box.set_size_request(COL_PX["kill"], -1)
    box.pack_start(btn, False, False, 0)
    return box