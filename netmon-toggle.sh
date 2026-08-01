#!/usr/bin/env bash
# netmon-toggle.sh — start/stop netmon_panel.py, tracked via a pidfile.
# Bind this to a key instead of (or in addition to) autostarting the
# panel directly, so one keypress can spawn it and the next kills it.

PIDFILE="/tmp/.netmon_panel.pid"
PANEL="$HOME/.config/hypr/scripts/netmon_panel.py"

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  kill "$(cat "$PIDFILE")"
  rm -f "$PIDFILE"
else
  python3 "$PANEL" &
  echo $! >"$PIDFILE"
fi