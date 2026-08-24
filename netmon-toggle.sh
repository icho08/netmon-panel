#!/usr/bin/env bash
# netmon-toggle.sh — start/stop netmon panel, tracked via a pidfile.
# Bind this to a key instead of (or in addition to) autostarting the
# panel directly, so one keypress can spawn it and the next kills it.

PIDFILE="/tmp/.netmon_panel.pid"
# Entry point: main.py copied to ~/.config/hypr/scripts/netmon-panel (see README)
PANEL="$HOME/.config/hypr/scripts/netmon-panel"

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  kill "$(cat "$PIDFILE")"
  rm -f "$PIDFILE"
else
  python3 "$PANEL" &
  echo $! >"$PIDFILE"
fi