"""Explain why the follower arm can't be reached, from the host side.

Used only for log messages: it reads the NetworkManager connection that owns
the follower port and the interface's live state, and never changes anything.
"""

import json
import subprocess
from pathlib import Path


def _run(*cmd: str) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=5).stdout.strip()


def diagnose(arm_ip: str, connection: str) -> str:
    """Return a one-line reason the arm at ``arm_ip`` on ``connection``'s port isn't reachable."""
    try:
        dev = _run("nmcli", "-g", "connection.interface-name", "con", "show", connection)
        want = _run("nmcli", "-g", "ipv4.addresses", "con", "show", connection)
    except (OSError, subprocess.SubprocessError):
        return f"NetworkManager connection '{connection}' not found; set up the follower port (see README)"
    if not dev:
        return f"connection '{connection}' isn't bound to an interface"

    carrier = Path(f"/sys/class/net/{dev}/carrier")
    try:
        has_link = carrier.read_text().strip() == "1"
    except OSError:
        return f"follower port {dev} doesn't exist"
    if not has_link:
        return f"no link on follower port {dev}: check the follower arm's power and its ethernet cable"

    try:
        info = json.loads(_run("ip", "-j", "-4", "addr", "show", "dev", dev))
        have = [f"{a['local']}/{a['prefixlen']}" for i in info for a in i.get("addr_info", [])]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        have = []
    if want not in have:
        return (
            f"follower port {dev} has link but {', '.join(have) or 'no address'} instead of {want}; "
            f"bcd-netcheck restores it within 30 s, or run: sudo nmcli con up {connection}"
        )
    return f"{dev} has link and {want}, but the arm at {arm_ip} isn't answering (still booting, or its IP changed)"
