#!/usr/bin/env python3
"""
Remap the HDMI-CEC remote keys the kernel hands us into codes Chromium can see.

The kernel's rc-cec keymap sends CEC "Select" as KEY_OK (352). XKB keymaps stop at
keycode 255, so the compositor drops it and the OK button does nothing. Arrows and
Exit sit below 255 and arrive fine. Rewriting the device's scancode→keycode table
via EVIOCSKEYCODE_V2 needs only the `input` group — no root, no ir-keytable.
Not persistent: kiosk.sh runs this at every start.
"""
import array, fcntl, glob, struct, sys

# CEC UI command → keycode. Anything below 256 survives XKB.
KEY_ENTER, KEY_EXIT, KEY_PLAYPAUSE = 28, 174, 164
MAP = {
    0x00: KEY_ENTER,      # Select  (was KEY_OK 352 → dropped)
    0x0D: KEY_EXIT,       # Exit/Return → Chromium "Close". NOT Escape: kiosk-mode Chromium
                          #   swallows Escape before the page sees it (learned the hard way).
    0x44: KEY_PLAYPAUSE,  # Play
    0x46: KEY_PLAYPAUSE,  # Pause
    0x61: KEY_PLAYPAUSE,  # Pause-Play function
}

EVIOCSKEYCODE_V2 = 0x40284504   # _IOW('E', 0x04, struct input_keymap_entry) — 40 bytes
EVIOCGNAME = lambda n: 0x80004506 | (n << 16)


def dev_name(path):
    buf = array.array("B", [0] * 64)
    with open(path, "rb") as f:
        fcntl.ioctl(f, EVIOCGNAME(64), buf)
    return buf.tobytes().split(b"\0", 1)[0].decode(errors="replace")


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else "vc4-hdmi"
    done = 0
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            name = dev_name(path)
        except OSError:
            continue
        if not name.startswith(want) or "Jack" in name:
            continue
        with open(path, "wb") as f:
            for scan, key in MAP.items():
                # struct input_keymap_entry { u8 flags; u8 len; u16 index; u32 keycode; u8 scancode[32]; }
                entry = struct.pack("<BBHI", 0, 4, 0, key) + struct.pack("<I", scan) + bytes(28)
                fcntl.ioctl(f, EVIOCSKEYCODE_V2, entry)
        print(f"{path} ({name}): remapped {len(MAP)} CEC keys")
        done += 1
    if not done:
        print("no vc4-hdmi input device found", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
