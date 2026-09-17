# wcn-commandcenter

The office TV, made useful. A Raspberry Pi 4 (`wcn-raspberrypi`) drives the Samsung facing
the desk with an ambient channel: the WCN brand family, the curated ILBTYD Gallery reel
straight from the MediaCMS studio, a random pull from the PhotoPrism library, and a
fleet-pulse card. The Samsung remote drives it over HDMI-CEC.

Personal, public, and of no value to anyone else — much like the fleet it watches. Built
2026-09-16 as a mood project; kept because it turned out to be a decent lobby screen.

## What's on screen

Scene loop (~5 min): **brand → brand → gallery clip → brand → three photos → brand → pulse**.

- **Brand** — the `?` mark and its siblings (Evolutions, The Spark, Coach's Clipboard),
  each with its one-line truth. Black ground, off-white, self-hosted Raleway — the brand kit.
- **Reel** — one clip per visit from MediaCMS playlist `4cUEWvXJk` ("ILBTYD Gallery — *I do
  though.*"), resolved to its 720p h264 encoding over the LAN; falls back to the public
  manifest on `ilookbetterthanyourdad.com` if the studio is down. Landscape clips fill,
  portrait clips letterbox.
- **Photos** — a random batch from PhotoPrism filtered by `PHOTOPRISM_QUERY`, fresh every
  ten minutes, with a slow drift. Thumbnails are proxied through the Pi so no credential
  reaches the page.
- **Pulse** — reachability + latency for workbench, laundryroom, MediaCMS, Jellyfin and the
  two public sites; studio clip count; Pi temp/uptime; Jellyfin now-playing / recently
  added once it has a key.
- **Chrome** — six fleet dots, hostname, date, clock, on every scene.

Canon holds here too: zero third-party requests. Everything is local, LAN, or a WCN domain.

## Layout

    server.py                     stdlib Python. Serves web/ and /api/state on :8787.
                                  A background thread refreshes each source on its own TTL;
                                  the page always gets the last good snapshot per source.
    web/                          index.html · app.js (scene loop, remote) · style.css · assets/
    kiosk.sh                      forces 1080p60 (the TV offers 4096x2160@30 — no), claims the
                                  HDMI-CEC bus as "Command Center", waits for the server,
                                  launches Chromium --kiosk. Wrapped in lwrespawn by autostart.
    wcn-commandcenter.service     systemd --user unit (WantedBy=default.target)
    wcn-commandcenter.env.example copy to wcn-commandcenter.env on the Pi — gitignored
    deploy.sh                     rsync + install + restart. Dry-run by default.

Everything lands in `~/wcn-commandcenter/` on the Pi plus one line in
`~/.config/labwc/autostart`. **Nothing under `/etc`, no root, no sudo.** labwc-pi runs with
`-m`, so the user autostart merges with the system one instead of shadowing it.

## Deploy

    ./deploy.sh              # dry run
    ./deploy.sh --apply      # rsync, install unit + autostart line, restart server, relaunch kiosk

## Operate (on the Pi)

    systemctl --user status wcn-commandcenter
    tail -f ~/.cache/wcn-commandcenter.log        # journalctl --user is not readable on this box
    curl -s http://127.0.0.1:8787/api/state | python3 -m json.tool

From any LAN device:

    curl 'http://192.168.1.70:8787/api/cmd?scene=reel'     # reel | photos | pulse | brand
    curl  http://192.168.1.70:8787/api/refresh              # re-pull every source now

## The remote

The Pi registers on HDMI-CEC (Samsung: Anynet+) as a Playback device and declares itself
active source at kiosk start, so the TV switches to its input and forwards remote keys. The
kernel `rc-cec` keymap delivers them to Chromium as ordinary key events — no daemon in the
key path, no root (`/dev/cec*` is group `video`).

    Right / Down / OK      next (scene, or next photo)      Left / Up     previous
    Play-Pause             hold this scene (again to resume)  Back        resume
    r / p / b              reel / pulse / brand (keyboard only)

Every key the page sees is echoed to the log, so unmapped buttons can be identified.

## Remove

    systemctl --user disable --now wcn-commandcenter
    rm -rf ~/wcn-commandcenter ~/.config/systemd/user/wcn-commandcenter.service ~/.cache/wcn-commandcenter*
    # delete the kiosk line from ~/.config/labwc/autostart, then reboot

## Lessons the box taught (so nobody relearns them)

- `pkill -f <pattern>` over SSH kills the SSH shell itself if the pattern appears in its
  command line. Use the `patter[n]` trick.
- Killing labwc to "restart the session" drops to the lightdm greeter; autologin only fires
  at boot. Reboot instead.
- Unprivileged `systemctl reboot` is refused while a second (SSH) session is active — polkit.
- The output is not always configured when labwc autostart fires at cold boot; one
  `wlr-randr` call is silently ignored. Loop until it agrees.
