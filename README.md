# netmon-panel

A live network-connections overlay for Wayland compositors (Hyprland, Sway, etc.), pinned to the wallpaper layer via `gtk-layer-shell`. Shows every active connection on your machine — process, local/remote address, geolocated location with a flag, connection state, protocol, live bandwidth, and age — right on your desktop.

![screenshot placeholder — eh](docs/screenshot.png)

## Features

- **Per-connection detail**: process name + pid, local/remote address, protocol (TCP/UDP), connection state (`ESTAB`, `LISTEN`, `TIME-WAIT`, etc.)
- **Geolocation**: remote IPs are resolved to city + country via [ip-api.com](https://ip-api.com), shown with a flag emoji, cached in-memory so repeat IPs don't re-query
- **Live bandwidth**: per-connection transfer rate, computed from `ss -i` counters between polls
- **New-connection flagging**: connections younger than 5s get a small marker so a freshly-opened socket catches your eye
- **All-states toggle**: default view is established connections only; click `ESTAB`/`ALL` in the header to also see listening sockets, `TIME-WAIT`, etc.
- **Click-to-sort**: click any sortable column header (`PROC`, `LOCATION`, `STATE`, `PROTO`, `RATE`, `AGE`) to sort by it, click again to reverse
- **Kill switch**: a small ✕ per row to `SIGTERM` a connection's owning process, with a confirmation prompt
- **Top talkers**: a chip row summarizing which processes hold the most connections right now
- **VPN indicator**: flags whether your default route is going through a `tun`/`wg`/`ppp`/`utun` interface
- **Draggable**: grab the header bar to reposition the panel; position is persisted to `/tmp/.netmon_pos` and restored on restart
- **Zero native deps beyond stdlib** aside from GTK/GObject bindings — no Python packages to pip install

## Requirements

A Wayland compositor with layer-shell support (Hyprland, Sway, etc.) is recommended for the overlay behavior; it falls back to a plain always-below window if `gtk-layer-shell` isn't available.

Arch Linux:
```bash
sudo pacman -S python-gobject gtk3 gtk-layer-shell iproute2 curl
```

Debian/Ubuntu:
```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1 iproute2 curl
```

Fedora:
```bash
sudo dnf install python3-gobject gtk3 gtk-layer-shell iproute2 curl
```

> `ss -i` bandwidth counters (`bytes_acked`/`bytes_received`) are populated for TCP sockets on most kernels; UDP rows will show `-` for rate since the kernel doesn't expose the same counters for them. Exact `ss` output formatting can vary slightly by `iproute2` version — if a column ever looks wrong, that's the first thing to check.

## Install

```bash
git clone https://github.com/icho08/netmon-panel.git
mkdir -p ~/.config/hypr/scripts
cp netmon-panel/netmon_panel.py ~/.config/hypr/scripts/netmon_panel.py
cp netmon-panel/netmon-toggle.sh ~/.config/hypr/scripts/netmon-toggle.sh
chmod +x ~/.config/hypr/scripts/netmon_panel.py ~/.config/hypr/scripts/netmon-toggle.sh
```

Pick one of two ways to start it — don't set up both, see the note below:

**Option A — always on, starts with your session:**
```
exec-once = python3 ~/.config/hypr/scripts/netmon_panel.py
```

**Option B — toggle on/off with a keybind**, using `netmon-toggle.sh` (start it, and the same key kills it):
```
bind = $mainMod, N, exec, ~/.config/hypr/scripts/netmon-toggle.sh
```

> Don't combine A and B. The toggle script tracks the panel via a pidfile (`/tmp/.netmon_panel.pid`) that it writes itself when *it* launches the panel — if you `exec-once` the panel directly, that pidfile never gets created, so the first keybind press will just spawn a second panel instead of closing the running one. If you want it running on startup *and* toggleable, use `exec-once = ~/.config/hypr/scripts/netmon-toggle.sh` instead (it'll start the panel and write the pidfile the same way the keybind does).

Or run it manually to try it out first:

```bash
python3 ~/.config/hypr/scripts/netmon_panel.py
```

## Usage

| Action | How |
|---|---|
| Move the panel | Click-drag the header bar |
| Toggle established-only vs. all states | Click the `ESTAB` / `ALL` label in the header |
| Sort by a column | Click `PROC`, `LOCATION`, `STATE`, `PROTO`, `RATE`, or `AGE`; click again to reverse |
| Kill a connection's process | Click the ✕ at the end of a row, confirm |
| See full local/remote address | Hover a row (tooltip) |
| Show/hide the whole panel | Run `netmon-toggle.sh` (or its keybind, if you set one up) |

The panel polls `ss` every 2 seconds and refreshes the "updated Ns ago" indicator every second.

## Configuration

Everything's plain constants at the top of `netmon_panel.py` — no config file, edit and restart:

- `COL_PX` — fixed pixel width per column, if you want to widen/narrow anything
- `PROC_PALETTE` — the color rotation used for per-process dots/chips (colors are hashed from the process name, so a given process keeps the same color across restarts)
- `CSS` (the big triple-quoted block) — colors, radii, fonts; swap `"JetBrainsMono Nerd Font"` for whatever you have installed
- `POS_FILE` — where the dragged position is persisted
- `PIDFILE` in `netmon-toggle.sh` (`/tmp/.netmon_panel.pid`) — where the toggle script tracks whether the panel is running; safe to delete manually if it ever gets out of sync (e.g. panel crashed without the toggle script closing it)

## Known limitations

- Killing a process you don't own, or seeing its pid at all, requires the script to have permission to see it (root, or same user) — rows without a visible pid have the kill button disabled.
- Geolocation depends on a third-party free API (`ip-api.com`) with rate limits; if you hammer it, lookups will start failing silently and fall back to `?`.
- No historical data — this is a live snapshot view, not a logger. If you want history, point it at a proper tool (`nethogs`, `bmon`, `vnstat`) alongside this.
