"""Explain network problems between the computer and the follower arm.

Used only for log messages: it reads the NetworkManager connection that owns
the follower port, the interface's live state, and the controller's own network
settings, and never changes anything. Fixing the port is bcd-netcheck's job.
"""

import ipaddress
import json
import subprocess
from pathlib import Path

import trossen_arm


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
        return (
            f"no link on follower port {dev}: bcd-netcheck resets the port while this lasts; "
            "if it persists, check the follower arm's power and its ethernet cable"
        )

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
    return f"{dev} has link and {want}, but the arm at {arm_ip} isn't answering (still booting, or its IP changed); bcd-netcheck resets the port while this lasts"


def controller_problems(driver: trossen_arm.TrossenArmDriver, arm_ip: str, host_address: str) -> list[str]:
    """Return what's wrong with the controller's stored network settings (empty if nothing).

    The controller must use a manual IP of ``arm_ip`` on the same subnet as
    ``host_address`` (the port's address, e.g. ``192.168.2.10/24``). A wrong
    setting takes effect at the controller's next reboot, so catch it now.
    """
    problems = []
    if driver.get_ip_method() != trossen_arm.IPMethod.manual:
        problems.append(f"IP method is {driver.get_ip_method().name}, not manual")
    if driver.get_manual_ip() != arm_ip:
        problems.append(f"manual IP is {driver.get_manual_ip()}, not {arm_ip}")
    try:
        host_net = ipaddress.ip_interface(host_address).network
        arm_net = ipaddress.ip_interface(f"{arm_ip}/{driver.get_subnet()}").network
        if arm_net != host_net:
            problems.append(f"subnet {driver.get_subnet()} puts the arm on {arm_net}, not the port's {host_net}")
    except ValueError as e:
        problems.append(f"unreadable subnet: {e}")
    return problems


def port_address(connection: str) -> str | None:
    """Return the static address of ``connection`` (e.g. ``192.168.2.10/24``), or None."""
    try:
        return _run("nmcli", "-g", "ipv4.addresses", "con", "show", connection) or None
    except (OSError, subprocess.SubprocessError):
        return None
