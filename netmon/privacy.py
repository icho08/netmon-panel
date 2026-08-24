#!/usr/bin/env python3
"""
Privacy / screenshare masking for netmon panel.

Three levels instead of a single on/off switch:

    LIVE   - nothing hidden (normal monitoring)
    SAFE   - comfortable for a call: identifying bits of addresses and the
             public IP are redacted, but the panel stays *useful*
             (process names, ports, states, rates, ages, sorting all work)
    STRICT - hard privacy: addresses, locations and process names are
             replaced by stable anonymous aliases so rows are still
             distinguishable without leaking anything.

Everything here is pure string work - no GTK - so it can be unit tested and
reused by any renderer.
"""
import hashlib
import re

LIVE = "live"
SAFE = "safe"
STRICT = "strict"

MODES = (LIVE, SAFE, STRICT)

MODE_LABEL = {
    LIVE: "LIVE",
    SAFE: "SAFE",
    STRICT: "STRICT",
}

MODE_ICON = {
    LIVE: "\U0001F441",   # eye
    SAFE: "\U0001F576",   # sunglasses
    STRICT: "\U0001F512",  # lock
}

MODE_TOOLTIP = {
    LIVE: "Privacy: LIVE - everything visible.\nClick or press S for screenshare mode.",
    SAFE: "Privacy: SAFE - IPs and precise location redacted,\n"
          "process names, ports, rates and sorting still visible.\n"
          "Click or press S for STRICT.",
    STRICT: "Privacy: STRICT - addresses, locations and app names\n"
            "replaced with anonymous aliases.\nClick or press S to go back to LIVE.",
}

DOT = "\u2022"
HIDDEN = DOT * 6

# where the chosen mode is remembered between runs
STATE_FILE = "/tmp/.netmon_privacy"

_ipv4_port_re = re.compile(r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3}):(\S+)$')
_ipv6_port_re = re.compile(r'^\[([0-9a-fA-F:]+)\]:(\S+)$')

_LOCAL_PREFIXES = ("127.", "0.0.0.0", "192.168.", "10.", "*:", "[::1]", "::1")

_ALIAS_ADJ = ("alpha", "bravo", "delta", "echo", "gamma", "kilo", "nova", "orion")


def next_mode(mode):
    """Cycle LIVE -> SAFE -> STRICT -> LIVE."""
    try:
        return MODES[(MODES.index(mode) + 1) % len(MODES)]
    except ValueError:
        return LIVE


def load_mode():
    """Restore the last used mode (defaults to LIVE)."""
    try:
        with open(STATE_FILE) as fh:
            mode = fh.read().strip()
        return mode if mode in MODES else LIVE
    except Exception:
        return LIVE


def save_mode(mode):
    try:
        with open(STATE_FILE, "w") as fh:
            fh.write(mode)
    except Exception:
        pass


def _alias(value, prefix="app"):
    """Stable, human-readable anonymous alias for a value."""
    if not value:
        return f"{prefix}-?"
    digest = hashlib.md5(value.encode()).hexdigest()
    word = _ALIAS_ADJ[int(digest[:4], 16) % len(_ALIAS_ADJ)]
    return f"{prefix}-{word}{int(digest[4:6], 16) % 100:02d}"


def is_local_addr(addr):
    return bool(addr) and addr.startswith(_LOCAL_PREFIXES)


def mask_addr(addr, mode):
    """Mask an 'ip:port' pair.

    SAFE   keeps the first octet and the port  -> 203.x.x.x:443
    STRICT hides the host and keeps the port   -> host-nova42:443
    Loopback / LAN addresses are never masked (they leak nothing).
    """
    if mode == LIVE or not addr:
        return addr
    if is_local_addr(addr):
        return addr

    m = _ipv4_port_re.match(addr)
    if m:
        a, _b, _c, _d, port = m.groups()
        if mode == SAFE:
            return f"{a}.{DOT}.{DOT}.{DOT}:{port}"
        return f"{_alias(addr.rsplit(':', 1)[0], 'host')}:{port}"

    m = _ipv6_port_re.match(addr)
    if m:
        host, port = m.groups()
        if mode == SAFE:
            return f"[{host.split(':')[0]}:{DOT}{DOT}]:{port}"
        return f"{_alias(host, 'host')}:{port}"

    if ":" in addr:
        host, port = addr.rsplit(":", 1)
        return f"{HIDDEN if mode == SAFE else _alias(host, 'host')}:{port}"
    return HIDDEN


def mask_public_ip(ip, mode):
    if mode == LIVE or not ip or ip == "unknown":
        return ip
    parts = ip.split(".")
    if mode == SAFE and len(parts) == 4:
        return f"{parts[0]}.{DOT}.{DOT}.{DOT}"
    return HIDDEN


def mask_location(label, mode):
    """SAFE keeps the country, STRICT hides everything."""
    if mode == LIVE or not label:
        return label
    if label in ("local", "\u2026", "?", ""):
        return label
    if mode == SAFE:
        return label.split(",")[-1].strip()
    return HIDDEN


def mask_proc(name, mode):
    """Process names survive SAFE (they're what makes the panel useful)."""
    if mode in (LIVE, SAFE) or not name:
        return name
    return _alias(name)


def color_seed(name, mode):
    """Keep per-process colours stable, even when the name is aliased."""
    return name if mode != STRICT else _alias(name)


def show_tooltips(mode):
    """Tooltips would happily re-leak the raw value on hover."""
    return mode == LIVE


def allow_kill(mode):
    """Killing a process pops a dialog with its name in it."""
    return mode != STRICT
