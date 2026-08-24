#!/usr/bin/env python3
"""
Network utilities for netmon panel.
"""
import subprocess
import re
import time
import ipaddress
import urllib.request
import json
import os
import signal

from .config import (
    POS_FILE, _first_seen, _prev_bytes,
    _addr_re, _proc_re, _bytes_acked_re, _bytes_recv_re,
    STATE_CSS, KNOWN_STATES, proc_color
)


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


def is_private_ip(host):
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return True


def _fmt_rate(bytes_per_sec):
    if bytes_per_sec is None or bytes_per_sec <= 0:
        return "-"
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.0f}B/s"
    if bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.1f}KB/s"
    return f"{bytes_per_sec / (1024 * 1024):.1f}MB/s"


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

        from .geo import get_location
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