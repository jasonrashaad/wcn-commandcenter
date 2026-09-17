#!/bin/bash
# Deploy wcn-commandcenter to the Pi. Dry-run by default, like the other WCN deploy scripts.
#   ./deploy.sh            # show what would change
#   ./deploy.sh --apply    # rsync, install the user unit + labwc autostart line, restart
set -euo pipefail
HOST="${CC_HOST:-wcn-raspberrypi}"
DEST="wcn-commandcenter"
cd "$(dirname "$0")"

RSYNC=(rsync -az --delete --exclude .git --exclude .gitignore --exclude .DS_Store \
       --exclude wcn-commandcenter.env --exclude __pycache__ ./ "$HOST:$DEST/")

if [ "${1:-}" != "--apply" ]; then
  echo "DRY RUN → $HOST:~/$DEST/   (pass --apply to do it)"
  "${RSYNC[@]}" -n -v --itemize-changes | grep -vE '^\.d|/$' || true
  exit 0
fi

"${RSYNC[@]}"
ssh "$HOST" bash -s <<'REMOTE'
set -e
cd ~/wcn-commandcenter
python3 -m py_compile server.py
chmod +x kiosk.sh
[ -f wcn-commandcenter.env ] || cp wcn-commandcenter.env.example wcn-commandcenter.env
mkdir -p ~/.config/systemd/user ~/.config/labwc
cp wcn-commandcenter.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now wcn-commandcenter >/dev/null
systemctl --user restart wcn-commandcenter
A=~/.config/labwc/autostart; touch "$A"; chmod +x "$A"
grep -q "wcn-commandcenter/kiosk.sh" "$A" || printf '\n# wcn-commandcenter — office TV channel. labwc-pi runs with -m, so this merges with\n# /etc/xdg/labwc/autostart rather than replacing it. See ~/wcn-commandcenter/README.md\n/usr/bin/lwrespawn %s/wcn-commandcenter/kiosk.sh &\n' "$HOME" >> "$A"
# Relaunch the kiosk: lwrespawn (if the session is up) brings it back on the new code.
RT="/run/user/$(id -u)"
if pgrep -f "wcn-commandcenter/kiosk.s[h]" >/dev/null; then
  pkill -f "wcn-commandcenter-chromiu[m]" 2>/dev/null || true      # lwrespawn relaunches it
elif [ -S "$RT/wayland-0" ]; then
  # First install into a running session: autostart has not run yet, start it ourselves.
  WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR="$RT" setsid nohup \
    /usr/bin/lwrespawn "$HOME/wcn-commandcenter/kiosk.sh" >/dev/null 2>&1 < /dev/null &
fi
sleep 6
echo "server: $(systemctl --user is-active wcn-commandcenter)   kiosk procs: $(pgrep -fc 'wcn-commandcenter-chromiu[m]' || echo 0)"
curl -sf http://127.0.0.1:8787/api/state | python3 -c 'import sys,json; s=json.load(sys.stdin); print({k: s[k].get("ok") for k in ("gallery","studio","fleet","jellyfin","photos","sys")})'
REMOTE
