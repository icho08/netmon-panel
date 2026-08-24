#!/usr/bin/env python3
"""
Geolocation utilities for netmon panel.
"""
import urllib.request
import json
import threading

from .config import _geo_cache, _geo_pending, _geo_lock, flag_emoji
from .network import is_private_ip


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
    return {"label": "\u2026", "cc": None}