#!/usr/bin/env python3
"""
Configuration constants for netmon panel.
"""
import re
import hashlib
import threading

POS_FILE = "/tmp/.netmon_pos"

COL_PX = {
    "proc": 150, "local": 140, "remote": 140, "loc": 150,
    "state": 92, "proto": 60, "rate": 78, "age": 48, "kill": 30,
}

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


def proc_color(name):
    idx = int(hashlib.md5(name.encode()).hexdigest(), 16) % len(PROC_PALETTE)
    return PROC_PALETTE[idx]


def flag_emoji(cc):
    if not cc or len(cc) != 2 or not cc.isalpha():
        return ""
    try:
        return "".join(chr(0x1F1E6 + (ord(ch.upper()) - 65)) for ch in cc)
    except Exception:
        return ""