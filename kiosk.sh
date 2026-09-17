#!/bin/bash
# Command Center — kiosk launcher. Started by labwc via ~/.config/labwc/autostart
# (wrapped in lwrespawn, so a Chromium crash just brings it back).
# Runs inside the labwc session, so WAYLAND_DISPLAY is already set.

URL="http://127.0.0.1:${WCN_CC_PORT:-8787}/"
OUT="${WCN_CC_OUTPUT:-HDMI-A-2}"
MODE="${WCN_CC_MODE:-1920x1080@60}"

# The TV advertises 4096x2160@30; a Pi 4 has no business compositing Chromium
# there. 1080p60 is crisp at desk distance and leaves headroom for video.
# At cold boot the output is not always configured when autostart fires, so
# keep asking until wlr-randr agrees (seen 2026-09-16: one early call, ignored).
for _ in $(seq 1 30); do
  wlr-randr --output "$OUT" --mode "$MODE" >/dev/null 2>&1
  sleep 1
  wlr-randr 2>/dev/null | grep -q "${MODE%@*} px.*(current)" && break
done

# HDMI-CEC: the Samsung remote. Claim a Playback address on whichever adapter
# has a real physical address (the connected port), announce ourselves as the
# active source so the TV routes remote keys here (and switches input to us),
# and keep a follower running so the TV's status queries get answered. The
# kernel's rc-cec keymap then delivers the remote as ordinary key events.
for dev in /dev/cec1 /dev/cec0; do
  [ -c "$dev" ] || continue
  pa=$(cec-ctl -d "$dev" 2>/dev/null | awk '/Physical Address/ {print $4; exit}')
  [ -n "$pa" ] && [ "$pa" != "f.f.f.f" ] || continue
  cec-ctl -d "$dev" --playback --osd-name "Command Center" >/dev/null 2>&1
  cec-ctl -d "$dev" --active-source phys-addr="$pa" >/dev/null 2>&1
  pgrep -x cec-follower >/dev/null || { cec-follower -d "$dev" >/dev/null 2>&1 & }
  # OK/Back/Play arrive as keycodes XKB cannot carry; remap them (see cec-keymap.py).
  python3 "$(dirname "$0")/cec-keymap.py" >/dev/null 2>&1 || true
  break
done

# Wait for the server (systemd --user starts it in parallel with the session).
for _ in $(seq 1 60); do
  curl -sf "${URL}api/state" >/dev/null 2>&1 && break
  sleep 1
done

exec chromium \
  --kiosk "$URL" \
  --ozone-platform=wayland \
  --user-data-dir="$HOME/.cache/wcn-commandcenter-chromium" \
  --noerrdialogs --disable-infobars --no-first-run \
  --disable-session-crashed-bubble --disable-features=TranslateUI \
  --autoplay-policy=no-user-gesture-required \
  --check-for-update-interval=31536000 \
  --password-store=basic \
  --hide-scrollbars \
  --start-fullscreen
