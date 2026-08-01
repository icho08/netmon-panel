#!/usr/bin/env python3
"""
netmon_panel.py — live network-request overlay, attached to the wallpaper layer.


"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk, Pango

HAS_LAYER_SHELL = True
try:
    gi.require_version('GtkLayerShell', '0.1')
    from gi.repository import GtkLayerShell
except (ImportError, ValueError):
    HAS_LAYER_SHELL = False

import subprocess
import re
import time
import hashlib
import threading
import json
import ipaddress
import urllib.request
import os
import signal

POS_FILE = "/tmp/.netmon_pos"


COL_PX = {
    "proc": 150, "local": 140, "remote": 140, "loc": 150,
    "state": 92, "proto": 60, "rate": 78, "age": 48, "kill": 30,
}

# which columns support click-to-sort
SORTABLE = {"proc", "loc", "state", "proto", "rate", "age"}

PROC_PALETTE = [
    "#7dd3fc", "#c4b5fd", "#fca5f1", "#86efac",
    "#fde68a", "#fdba74", "#a5b4fc", "#f9a8d4",
]

CSS = b"""
window { background-color: transparent; }

#panel {
    background-color: rgba(9, 10, 20, 0.99);
    border-radius: 20px;
}

label {
    color: #e8ecff;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-size: 12px;
}

.hsep {
    background-color: rgba(255,140,200,0.22);
    min-width: 1px;
    margin: 3px 0;
}

.col-head {
    color: #ff8ac8;
    font-size: 10.5px;
    font-weight: bold;
    letter-spacing: 0.5px;
}
.col-head-active { color: #fff0f8; }

.badge {
    padding: 5px 14px;
    font-weight: bold;
    font-size: 12px;
}
.badge-vpn-on {
    color: #86efac;
}
.badge-vpn-off {
    color: #ff8fa3;
}
.badge-count {
    color: #ff8ac8;
}

.toggle-btn {
    color: #9aa3c7;
    font-size: 10.5px;
    font-weight: bold;
    padding: 4px 10px;
    border-radius: 8px;
    background-color: rgba(255,255,255,0.04);
}
.toggle-btn:hover { background-color: rgba(255,140,200,0.1); }
.toggle-btn-active { color: #ff8ac8; background-color: rgba(255,140,200,0.14); }

.updated-label { color: #4d5578; font-size: 10px; }

.stat-label { color: #6b7394; font-size: 11px; }
.stat-value { color: #dbe4ff; font-size: 12px; }

.chip {
    padding: 4px 12px;
    font-size: 11px;
}

.pill { border-radius: 6px; padding: 2px 9px; font-size: 11px; font-weight: bold; }
.pill-tcp { background-color: rgba(125,211,252,0.15); color: #7dd3fc; }
.pill-udp { background-color: rgba(253,230,138,0.15); color: #fde68a; }

.state-pill { border-radius: 6px; padding: 2px 8px; font-size: 10px; font-weight: bold; }
.state-estab { background-color: rgba(134,239,172,0.15); color: #86efac; }
.state-listen { background-color: rgba(125,211,252,0.15); color: #7dd3fc; }
.state-timewait { background-color: rgba(255,255,255,0.05); color: #6b7394; }
.state-synsent { background-color: rgba(253,186,116,0.15); color: #fdba74; }
.state-closewait { background-color: rgba(255,143,163,0.15); color: #ff8fa3; }
.state-other { background-color: rgba(255,255,255,0.05); color: #9aa3c7; }

.kill-btn {
    color: #6b7394;
    font-size: 11px;
    font-weight: bold;
    border-radius: 6px;
    padding: 0px 6px;
    background-color: transparent;
    min-width: 0;
    min-height: 0;
}
.kill-btn:hover { color: #ff8fa3; background-color: rgba(255,143,163,0.12); }

.row-even, .row-odd {
    padding: 7px 10px;
    border-radius: 8px;
}
.row-even { background-color: rgba(255,255,255,0.035); }
.row-odd  { background-color: transparent; }
.row-even:hover, .row-odd:hover { background-color: rgba(255,138,200,0.06); }

.cell { font-size: 12px; }
.cell-muted { color: #6b7394; }
.cell-dim { color: #4d5578; }

.col-header-row { padding: 0 10px 10px 10px; }
.chips-row { padding: 2px 2px 0 2px; }

separator { background-color: rgba(255,140,200,0.18); min-height: 1px; margin: 2px 0 4px 0; }

/* keep the auto-appearing scrollbar slim and on-theme instead of the
   stock OS-styled widget popping in over the panel */
scrollbar { background-color: transparent; }
scrollbar slider {
    background-color: rgba(255,140,200,0.35);
    border-radius: 999px;
    min-width: 4px;
}
scrollbar slider:hover { background-color: rgba(255,140,200,0.6); }
"""

_first_seen = {}
_prev_bytes = {}
_addr_re = re.compile(r'(\[[0-9a-fA-F:]+\]:\d+|\d{1,3}(?:\.\d{1,3}){3}:\d+|\*:\d+)')
_proc_re = re.compile(r'users:\(\("([^"]+)",pid=(\d+)')
_bytes_acked_re = re.compile(r'bytes_acked:(\d+)')
_bytes_recv_re = re.compile(r'bytes_received:(\d+)')

_geo_cache = {}
_geo_pending = set()
_geo_lock = threading.Lock()

STATE_CSS = {
    "ESTAB": "state-estab",
    "LISTEN": "state-listen",
    "TIME-WAIT": "state-timewait",
    "SYN-SENT": "state-synsent",
    "SYN-RECV": "state-synsent",
    "CLOSE-WAIT": "state-closewait",
    "FIN-WAIT-1": "state-closewait",
    "FIN-WAIT-2": "state-closewait",
    "LAST-ACK": "state-closewait",
}
KNOWN_STATES = set(STATE_CSS.keys()) | {"UNCONN", "CLOSING", "CLOSE"}


def get_default_iface():
    try:
        out = subprocess.run(
            ["ip", "route", "get", "1.1.1.1"],
            capture_output=True, text=True, timeout=2
        ).stdout
        m = re.search(r"dev (\S+)", out)
        return m.group(1) if m else None
    except Exception:
        return None


def get_public_ip():
    try:
        out = subprocess.run(
            ["curl", "-s", "--max-time", "2", "https://api.ipify.org"],
            capture_output=True, text=True
        ).stdout
        return out.strip() or "unknown"
    except Exception:
        return "unknown"


def proc_color(name):
    idx = int(hashlib.md5(name.encode()).hexdigest(), 16) % len(PROC_PALETTE)
    return PROC_PALETTE[idx]


def is_private_ip(host):
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return True


def flag_emoji(cc):
    """Convert a 2-letter country code into a regional-indicator flag emoji."""
    if not cc or len(cc) != 2 or not cc.isalpha():
        return ""
    try:
        return "".join(chr(0x1F1E6 + (ord(ch.upper()) - 65)) for ch in cc)
    except Exception:
        return ""


def _fmt_rate(bytes_per_sec):
    if bytes_per_sec is None or bytes_per_sec <= 0:
        return "-"
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.0f}B/s"
    if bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.1f}KB/s"
    return f"{bytes_per_sec / (1024 * 1024):.1f}MB/s"


def _fetch_geo(ip):
    try:
        req = urllib.request.Request(
            f"http://ip-api.com/json/{ip}?fields=status,city,countryCode",
            headers={"User-Agent": "netmon-panel"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        if data.get("status") == "success":
            city = data.get("city") or ""
            cc = data.get("countryCode") or ""
            label = f"{city}, {cc}" if city else (cc or "?")
        else:
            cc = ""
            label = "?"
    except Exception:
        cc = ""
        label = "?"
    with _geo_lock:
        _geo_cache[ip] = {"label": label, "cc": cc}
        _geo_pending.discard(ip)


def get_location(host_port):
    """Returns {'label': str, 'cc': str|None}."""
    ip = host_port.rsplit(":", 1)[0].strip("[]")
    if ip in ("127.0.0.1", "::1", "*") or is_private_ip(ip):
        return {"label": "local", "cc": None}
    with _geo_lock:
        if ip in _geo_cache:
            return _geo_cache[ip]
        if ip not in _geo_pending:
            _geo_pending.add(ip)
            threading.Thread(target=_fetch_geo, args=(ip,), daemon=True).start()
    return {"label": "…", "cc": None}


def get_connections(show_all_states):
    """Returns a list of row dicts. Uses `ss -i` for bandwidth counters."""
    cmd = ["ss", "-tunepi"]
    if not show_all_states:
        cmd += ["state", "established"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True).stdout
    except Exception:
        return []

    now = time.time()
    raw = []
    current = None
    for line in out.splitlines()[1:]:
        if not line.strip():
            continue
        if line[0] in (" ", "\t"):
           
            if current is not None:
                ba = _bytes_acked_re.search(line)
                br = _bytes_recv_re.search(line)
                if ba:
                    current["bytes"] += int(ba.group(1))
                if br:
                    current["bytes"] += int(br.group(1))
            continue

        addrs = _addr_re.findall(line)
        if len(addrs) < 2:
            current = None
            continue
        local, remote = addrs[0], addrs[1]
        # only keep rows that have a real remote endpoint (skip bare
        # LISTEN sockets with "*:*" as remote, they're not "connections")
        if remote.startswith("*:") or remote.startswith("0.0.0.0:"):
            current = None
            continue

        parts = line.split()
        proto = "udp" if parts[0].lower().startswith("udp") else "tcp"
        state = "ESTAB"
        for tok in parts[:4]:
            if tok.upper() in KNOWN_STATES:
                state = tok.upper()
                break

        m = _proc_re.search(line)
        proc = m.group(1) if m else "-"
        pid = int(m.group(2)) if m else None

        current = {
            "proc": proc, "pid": pid, "local": local, "remote": remote,
            "proto": proto, "state": state, "bytes": 0,
        }
        raw.append(current)

    rows = []
    live_keys = set()
    for r in raw:
        key = f"{r['local']}-{r['remote']}"
        live_keys.add(key)
        if key not in _first_seen:
            _first_seen[key] = now
        age = now - _first_seen[key]

        prev = _prev_bytes.get(key)
        rate = 0.0
        if prev is not None:
            pbytes, pts = prev
            dt = now - pts
            if dt > 0 and r["bytes"] >= pbytes:
                rate = (r["bytes"] - pbytes) / dt
        _prev_bytes[key] = (r["bytes"], now)

        loc = get_location(r["remote"])
        rows.append({
            "key": key, "proc": r["proc"], "pid": r["pid"],
            "local": r["local"], "remote": r["remote"],
            "proto": r["proto"], "state": r["state"],
            "age": int(age), "is_new": age < 5,
            "rate": rate, "loc_label": loc["label"], "loc_cc": loc["cc"],
        })

    for k in list(_first_seen):
        if k not in live_keys:
            del _first_seen[k]
    for k in list(_prev_bytes):
        if k not in live_keys:
            del _prev_bytes[k]

    return rows


def load_saved_position():
    try:
        with open(POS_FILE) as f:
            top, right = f.read().strip().split(",")
            return int(top), int(right)
    except Exception:
        return 50, 20


def save_position(top, right):
    try:
        with open(POS_FILE, "w") as f:
            f.write(f"{top},{right}")
    except Exception:
        pass


def _fixed_cell(width, widget):
    """Wrap a widget in a fixed-pixel-width box, left-aligned. Widget must
    be packed with fill=True (and hexpand set) or GTK only grants it its
    natural-request size, which combined with ellipsize collapses to '…'
    regardless of the actual text."""
    box = Gtk.Box()
    box.set_size_request(width, -1)
    widget.set_hexpand(True)
    box.pack_start(widget, True, True, 0)
    return box


def _text_cell(text, width, css_classes=(), tooltip=None):
    label = Gtk.Label(label=text, xalign=0)
    label.set_ellipsize(Pango.EllipsizeMode.END)
    for c in css_classes:
        label.get_style_context().add_class(c)
    if tooltip:
        label.set_tooltip_text(tooltip)
    return _fixed_cell(width, label)


def _pill_cell(text, width, variant, css_prefix="pill"):
    pill = Gtk.Label(label=text.upper())
    pill.get_style_context().add_class(css_prefix if css_prefix == "state-pill" else "pill")
    pill.get_style_context().add_class(variant)
    # pills shouldn't stretch to fill the column — wrap in a non-filled
    # fixed cell of their own so the badge stays compact and left-aligned
    box = Gtk.Box()
    box.set_size_request(width, -1)
    box.pack_start(pill, False, False, 0)
    return box


def _vsep():
    sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
    sep.get_style_context().add_class("hsep")
    return sep


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

        # new state
        self._show_all_states = False
        self._sort_key = "age"
        self._sort_reverse = True
        self._last_conns = []
        self._last_refresh_ts = time.time()
        self._col_head_labels = {}

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

        # ---- header bar (draggable) ----
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        left_spacer = Gtk.Box()
        header_box.pack_start(left_spacer, True, True, 0)

        self.vpn_badge = Gtk.Label()
        self.vpn_badge.get_style_context().add_class("badge")
        header_box.pack_start(self.vpn_badge, False, False, 0)

        self.iface_label = Gtk.Label()
        self.iface_label.get_style_context().add_class("stat-label")
        header_box.pack_start(self.iface_label, False, False, 0)

        header_box.pack_start(_vsep(), False, False, 2)

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
        self.loc_value = Gtk.Label(label="…")
        self.loc_value.get_style_context().add_class("stat-value")
        self.loc_value.set_ellipsize(Pango.EllipsizeMode.END)
        self.loc_value.set_max_width_chars(22)
        loc_wrap.pack_start(loc_key, False, False, 0)
        loc_wrap.pack_start(self.loc_value, False, False, 0)
        header_box.pack_start(loc_wrap, False, False, 0)

        header_box.pack_start(_vsep(), False, False, 2)

        self.count_badge = Gtk.Label()
        self.count_badge.get_style_context().add_class("badge")
        self.count_badge.get_style_context().add_class("badge-count")
        header_box.pack_start(self.count_badge, False, False, 0)

        # all/established toggle
        self.state_toggle = Gtk.Label(label="ESTAB")
        self.state_toggle.get_style_context().add_class("toggle-btn")
        toggle_evbox = Gtk.EventBox()
        toggle_evbox.add(self.state_toggle)
        toggle_evbox.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        toggle_evbox.connect("button-press-event", self._on_toggle_states)
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
        header_evbox.connect("button-press-event", self._on_drag_start)
        header_evbox.connect("button-release-event", self._on_drag_end)
        header_evbox.connect("motion-notify-event", self._on_drag_motion)
        outer.add(header_evbox)

        # ---- top talkers (chips) ----
        self.chips_box = Gtk.Box(spacing=8)
        self.chips_box.get_style_context().add_class("chips-row")
        self.chips_box.set_halign(Gtk.Align.CENTER)
        outer.add(self.chips_box)

        outer.add(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # ---- table header ----
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
            cell = _fixed_cell(COL_PX[key], lbl)
            if key in SORTABLE:
                evbox = Gtk.EventBox()
                evbox.add(cell)
                evbox.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
                evbox.connect("button-press-event", self._on_col_header_click, key)
                col_header.pack_start(evbox, False, False, 0)
            else:
                col_header.pack_start(cell, False, False, 0)
        outer.add(col_header)
        self._update_sort_arrows()

        # ---- scrollable row list ----
        self.rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        scroller = Gtk.ScrolledWindow()
        scroller.set_propagate_natural_height(True)
        scroller.set_min_content_height(20)
        scroller.set_max_content_height(400)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_overlay_scrolling(False)
        scroller.add(self.rows_box)
        outer.add(scroller)

        self.refresh()
        GLib.timeout_add_seconds(2, self.refresh)
        GLib.timeout_add_seconds(1, self._tick_updated_label)

    def _on_screen_changed(self, widget, old_screen):
        screen = widget.get_screen()
        visual = screen.get_rgba_visual() if screen else None
        if visual:
            widget.set_visual(visual)

    # ---- dragging (throttled to ~60fps) ----
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

    def _on_close_clicked(self, widget, event):
        try:
            os.remove("/tmp/.netmon_panel.pid")
        except Exception:
            pass
        Gtk.main_quit()
        return True

    # ---- toggle / filter / sort handlers ----
    def _on_toggle_states(self, widget, event):
        self._show_all_states = not self._show_all_states
        ctx = self.state_toggle.get_style_context()
        if self._show_all_states:
            self.state_toggle.set_label("ALL")
            ctx.add_class("toggle-btn-active")
        else:
            self.state_toggle.set_label("ESTAB")
            ctx.remove_class("toggle-btn-active")
        self.refresh()
        return True

    def _on_col_header_click(self, widget, event, key):
        if self._sort_key == key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_key = key
            self._sort_reverse = True
        self._update_sort_arrows()
        self._render_rows()
        return True

    def _update_sort_arrows(self):
        for key, (lbl, text) in self._col_head_labels.items():
            ctx = lbl.get_style_context()
            if key == self._sort_key:
                arrow = " ▾" if self._sort_reverse else " ▴"
                lbl.set_label(f"{text}{arrow}" if text else "")
                ctx.add_class("col-head-active")
            else:
                lbl.set_label(text)
                ctx.remove_class("col-head-active")

    def _tick_updated_label(self):
        secs = int(time.time() - self._last_refresh_ts)
        self.updated_label.set_label(f"updated {secs}s ago")
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

    def _kill_cell(self, proc, pid):
        btn = Gtk.Button(label="✕")
        btn.get_style_context().add_class("kill-btn")
        btn.set_sensitive(pid is not None)
        btn.set_tooltip_text(f"Kill {proc} (pid {pid})" if pid else "No permission to see pid")
        btn.connect("clicked", self._on_kill_clicked, proc, pid)
        box = Gtk.Box()
        box.set_size_request(COL_PX["kill"], -1)
        box.pack_start(btn, False, False, 0)
        return box

    # ---- data refresh ----
    def refresh(self):
        iface = get_default_iface()
        vpn = bool(iface and re.match(r"^(tun|wg|ppp|utun)", iface))
        pub_ip = get_public_ip()
        conns = get_connections(self._show_all_states)
        self._last_conns = conns
        self._last_refresh_ts = time.time()

        ctx = self.vpn_badge.get_style_context()
        ctx.remove_class("badge-vpn-on")
        ctx.remove_class("badge-vpn-off")
        ctx.add_class("badge-vpn-on" if vpn else "badge-vpn-off")
        self.vpn_badge.set_label("VPN ACTIVE" if vpn else "NO VPN")
        self.iface_label.set_label(f"({iface or 'n/a'})")
        self.ip_value.set_label(pub_ip)
        if pub_ip != "unknown":
            loc = get_location(pub_ip)
            flag = flag_emoji(loc["cc"])
            self.loc_value.set_label(f"{flag} {loc['label']}".strip())
        else:
            self.loc_value.set_label("?")
        self.count_badge.set_label(f"{len(conns)} connections")
        self._tick_updated_label()

        # top talkers as chips
        for child in self.chips_box.get_children():
            self.chips_box.remove(child)
        counts = {}
        for c in conns:
            counts[c["proc"]] = counts.get(c["proc"], 0) + 1
        for p, c in sorted(counts.items(), key=lambda kv: -kv[1])[:5]:
            chip = Gtk.Label()
            chip.set_markup(
                f'<span foreground="{proc_color(p)}">{GLib.markup_escape_text(p)}</span>'
                f'<span foreground="#6b7394"> · {c}</span>'
            )
            chip.get_style_context().add_class("chip")
            self.chips_box.pack_start(chip, False, False, 0)
        self.chips_box.show_all()

        self._render_rows()
        return True

    def _render_rows(self):
        for child in self.rows_box.get_children():
            self.rows_box.remove(child)

        conns = self._last_conns

        sort_key_fn = {
            "proc": lambda c: c["proc"].lower(),
            "loc": lambda c: c["loc_label"].lower(),
            "state": lambda c: c["state"],
            "proto": lambda c: c["proto"],
            "rate": lambda c: c["rate"],
            "age": lambda c: c["age"],
        }.get(self._sort_key, lambda c: c["age"])
        sorted_conns = sorted(conns, key=sort_key_fn, reverse=self._sort_reverse)[:30]

        for i, c in enumerate(sorted_conns):
            row = Gtk.Box(spacing=10)
            row.get_style_context().add_class("row-even" if i % 2 == 0 else "row-odd")

            new_prefix = '<span foreground="#86efac">◆ </span>' if c["is_new"] else ""
            proc_label = Gtk.Label(xalign=0)
            proc_label.set_markup(
                f'{new_prefix}<span foreground="{proc_color(c["proc"])}">●</span> '
                f'<span foreground="#dbe4ff">{GLib.markup_escape_text(c["proc"])}</span>'
            )
            proc_label.set_ellipsize(Pango.EllipsizeMode.END)
            tip = c["proc"] + (" (new)" if c["is_new"] else "")
            proc_label.set_tooltip_text(tip)
            row.pack_start(_fixed_cell(COL_PX["proc"], proc_label), False, False, 0)

            row.pack_start(_text_cell(c["local"], COL_PX["local"], ("cell",), tooltip=c["local"]), False, False, 0)
            row.pack_start(_text_cell(c["remote"], COL_PX["remote"], ("cell",), tooltip=c["remote"]), False, False, 0)

            flag = flag_emoji(c["loc_cc"])
            loc_text = f"{flag} {c['loc_label']}".strip() if flag else c["loc_label"]
            loc_classes = ("cell", "cell-muted") if c["loc_label"] in ("local", "…") else ("cell",)
            row.pack_start(_text_cell(loc_text, COL_PX["loc"], loc_classes, tooltip=c["loc_label"]), False, False, 0)

            state_variant = STATE_CSS.get(c["state"], "state-other")
            row.pack_start(_pill_cell(c["state"], COL_PX["state"], state_variant, "state-pill"), False, False, 0)

            row.pack_start(_pill_cell(c["proto"], COL_PX["proto"], c["proto"]), False, False, 0)

            rate_classes = ("cell",) if c["rate"] > 0 else ("cell", "cell-dim")
            row.pack_start(_text_cell(_fmt_rate(c["rate"]), COL_PX["rate"], rate_classes), False, False, 0)

            row.pack_start(_text_cell(f"{c['age']}s", COL_PX["age"], ("cell", "cell-dim")), False, False, 0)

            row.pack_start(self._kill_cell(c["proc"], c["pid"]), False, False, 0)

            row_evbox = Gtk.EventBox()
            row_evbox.add(row)
            self.rows_box.pack_start(row_evbox, False, False, 0)

        if not sorted_conns:
            empty = Gtk.Label(label="— no active connections —", xalign=0)
            empty.get_style_context().add_class("cell-muted")
            empty.set_margin_top(6)
            empty.set_margin_bottom(6)
            self.rows_box.pack_start(empty, False, False, 4)

        self.rows_box.show_all()


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