#!/usr/bin/env python3
"""
Main panel window for netmon.
"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk

HAS_LAYER_SHELL = True
try:
    gi.require_version('GtkLayerShell', '0.1')
    from gi.repository import GtkLayerShell
except (ImportError, ValueError):
    HAS_LAYER_SHELL = False

import os
import signal
import time

from ..config import CSS, POS_FILE
from ..network import get_default_iface, get_public_ip, get_connections, load_saved_position, save_position
from ..geo import get_location
from .header import HeaderBar
from .table import TableView


class NetPanel(Gtk.Window):
    def __init__(self):
        super().__init__(title="netmon")
        self.set_resizable(False)
        self.set_decorated(False)
        self.set_app_paintable(True)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.connect("screen-changed", self._on_screen_changed)

        self._margin_top, self._margin_right = load_saved_position()
        self._drag_origin = None
        self._drag_target = None
        self._drag_timer_id = None

        self._show_all_states = False
        self._sort_key = "age"
        self._sort_reverse = True
        self._last_conns = []
        self._last_refresh_ts = time.time()

        if HAS_LAYER_SHELL:
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.BACKGROUND)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, self._margin_top)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT, self._margin_right)
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)
        else:
            self.set_keep_below(True)
            self.move(1250, 60)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        outer.set_name("panel")
        outer.set_border_width(26)
        self.add(outer)

        self.header = HeaderBar(
            self,
            on_drag_start=self._on_drag_start,
            on_drag_end=self._on_drag_end,
            on_drag_motion=self._on_drag_motion,
            on_toggle_states=self._on_toggle_states,
            on_col_header_click=self._on_col_header_click,
        )
        outer.add(self.header.get_widget())

        outer.add(self.header.build_col_header())
        self.header.update_sort_arrows(self._sort_key, self._sort_reverse)

        outer.add(self.table.get_chips_widget())
        outer.add(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        outer.add(self.table.get_rows_widget())

        self.refresh()
        GLib.timeout_add_seconds(2, self.refresh)
        GLib.timeout_add_seconds(1, self._tick_updated_label)

    @property
    def table(self):
        if not hasattr(self, '_table'):
            self._table = TableView(self, self._on_kill_clicked)
        return self._table

    def _on_screen_changed(self, widget, old_screen):
        screen = widget.get_screen()
        visual = screen.get_rgba_visual() if screen else None
        if visual:
            widget.set_visual(visual)

    def _on_drag_start(self, widget, event):
        if event.button != 1:
            return False
        self._drag_origin = (event.x_root, event.y_root, self._margin_top, self._margin_right)
        self._drag_target = (self._margin_top, self._margin_right)
        self._drag_timer_id = GLib.timeout_add(16, self._flush_drag)
        window = widget.get_window()
        if window:
            window.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), "grabbing"))
        return True

    def _on_drag_motion(self, widget, event):
        if self._drag_origin is None:
            return False
        start_x, start_y, start_top, start_right = self._drag_origin
        dx = event.x_root - start_x
        dy = event.y_root - start_y
        new_top = max(0, int(start_top + dy))
        new_right = max(0, int(start_right - dx))
        self._drag_target = (new_top, new_right)
        return True

    def _flush_drag(self):
        if self._drag_origin is None:
            self._drag_timer_id = None
            return False
        if self._drag_target != (self._margin_top, self._margin_right):
            self._margin_top, self._margin_right = self._drag_target
            if HAS_LAYER_SHELL:
                GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, self._margin_top)
                GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT, self._margin_right)
        return True

    def _on_drag_end(self, widget, event):
        if self._drag_timer_id is not None:
            GLib.source_remove(self._drag_timer_id)
            self._drag_timer_id = None
        if self._drag_origin is not None:
            save_position(self._margin_top, self._margin_right)
        self._drag_origin = None
        window = widget.get_window()
        if window:
            window.set_cursor(None)
        return True

    def _on_toggle_states(self, widget, event):
        self._show_all_states = not self._show_all_states
        self.header.update_toggle_state(self._show_all_states)
        self.refresh()
        return True

    def _on_col_header_click(self, widget, event, key):
        if self._sort_key == key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_key = key
            self._sort_reverse = True
        self.header.update_sort_arrows(self._sort_key, self._sort_reverse)
        self.table.render_rows(self._last_conns, self._sort_key, self._sort_reverse)
        return True

    def _tick_updated_label(self):
        secs = int(time.time() - self._last_refresh_ts)
        self.header.update_timestamp(secs)
        return True

    def _on_kill_clicked(self, button, proc, pid):
        if not pid:
            return
        dialog = Gtk.MessageDialog(
            transient_for=self, flags=0, message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Kill {proc} (pid {pid})?",
        )
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass

    def refresh(self):
        iface = get_default_iface()
        vpn = bool(iface and __import__('re').match(r"^(tun|wg|ppp|utun)", iface))
        pub_ip = get_public_ip()
        conns = get_connections(self._show_all_states)
        self._last_conns = conns
        self._last_refresh_ts = time.time()

        self.header.update_vpn_status(vpn, iface)
        
        if pub_ip != "unknown":
            loc = get_location(pub_ip)
            flag = __import__('netmon.config', fromlist=['flag_emoji']).flag_emoji(loc["cc"])
            self.header.update_ip_location(pub_ip, loc["label"], flag)
        else:
            self.header.update_ip_location("unknown", "?", "")
            
        self.header.update_count(len(conns))
        self.header.update_timestamp(0)

        self.table.update_chips(conns)
        self.table.render_rows(conns, self._sort_key, self._sort_reverse)
        return True


def main():
    win = NetPanel()
    win.connect("destroy", Gtk.main_quit)

    style_provider = Gtk.CssProvider()
    style_provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()