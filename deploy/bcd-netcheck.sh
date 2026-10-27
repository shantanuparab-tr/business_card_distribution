#!/usr/bin/env bash
# Keep each arm's ethernet port working. Run as root by bcd-netcheck.timer every
# 15 s; installed to /usr/local/sbin/bcd-netcheck.
#
#   bcd-netcheck [CONNECTION=ARM_IP...]     (default: trossen-follower=192.168.2.4)
#
# For each NetworkManager connection, the port is healthy if a program holds a
# TCP session to the arm, or the arm answers ping. Otherwise:
#   - link up but another profile (or no address) on the port: bring the
#     connection back up. This undoes e.g. an old setup's `nmcli con up`.
#   - no link, or link and address but the arm is silent: reset the port in
#     software, backing off while it stays down. The igc NICs on the booth PC
#     can drop the 100 Mbps link to the controller and never renegotiate, and a
#     flooded link can leave stale neighbor entries and queues behind; both
#     clear with a reset. Most resets toggle the link; every third one rebinds
#     the NIC's driver, a full reset of that one port.
# If the arm is simply powered off, the resets are harmless and back off to one
# every 5 minutes.
set -uo pipefail

STATE_DIR=/run/bcd-netcheck
# Consecutive bad checks after which a reset is attempted (15 s apart), then
# every RESET_EVERY checks while it stays bad.
RESET_AT=(2 4 8)
RESET_EVERY=20
# The controller's TCP server; a live session means the arm is fine.
ARM_TCP_PORT=50001

[[ $# -gt 0 ]] || set -- trossen-follower=192.168.2.4
mkdir -p "$STATE_DIR"

has_link() { [[ "$(cat "/sys/class/net/$1/carrier" 2>/dev/null)" == 1 ]]; }

arm_answers() {
    local dev=$1 ip=$2
    [[ -n "$ip" ]] || return 0
    [[ -n "$(ss -Htn state established dst "$ip" dport = ":$ARM_TCP_PORT" 2>/dev/null)" ]] && return 0
    ping -c 2 -W 1 -I "$dev" "$ip" >/dev/null 2>&1
}

should_reset() {
    local n=$1 at
    for at in "${RESET_AT[@]}"; do [[ $n -eq $at ]] && return 0; done
    [[ $n -gt ${RESET_AT[-1]} && $(( n % RESET_EVERY )) -eq 0 ]]
}

toggle_link() {
    local dev=$1
    ip neigh flush dev "$dev" 2>/dev/null
    ip link set dev "$dev" down && sleep 2 && ip link set dev "$dev" up
}

rebind_driver() {
    local dev=$1 pci drv
    pci=$(basename "$(readlink -f "/sys/class/net/$dev/device")") || return 1
    drv=$(basename "$(readlink -f "/sys/class/net/$dev/device/driver")") || return 1
    echo "$pci" > "/sys/bus/pci/drivers/$drv/unbind" || return 1
    sleep 2
    echo "$pci" > "/sys/bus/pci/drivers/$drv/bind" || return 1
    # udev gives the port its name back; wait for it before touching it again.
    for _ in $(seq 10); do [[ -e "/sys/class/net/$dev" ]] && return 0; sleep 1; done
    return 1
}

for arg in "$@"; do
    con=${arg%%=*}
    arm_ip=${arg#*=}; [[ "$arg" == *=* ]] || arm_ip=
    state="$STATE_DIR/$con"

    if ! dev=$(nmcli -g connection.interface-name con show "$con" 2>/dev/null) || [[ -z "$dev" ]]; then
        echo "connection '$con' not found or not bound to an interface" >&2
        continue
    fi
    want=$(nmcli -g ipv4.addresses con show "$con")

    if has_link "$dev"; then
        active=$(nmcli -g GENERAL.CONNECTION dev show "$dev" 2>/dev/null)
        if [[ "$active" != "$con" ]] || ! ip -4 -o addr show dev "$dev" | grep -qF " inet $want "; then
            echo "$dev: active connection '${active:-none}', expected '$con' with $want; reactivating"
            nmcli con up "$con" >/dev/null && echo "$dev: '$con' is up"
        fi
        if arm_answers "$dev" "$arm_ip"; then
            [[ -f "$state" ]] && echo "$dev: arm at $arm_ip is answering again"
            rm -f "$state"
            continue
        fi
        problem="link and $want, but the arm at $arm_ip isn't answering"
    else
        problem="no link"
    fi

    read -r fails resets < "$state" 2>/dev/null || { fails=0; resets=0; }
    fails=$(( fails + 1 ))
    if should_reset "$fails"; then
        resets=$(( resets + 1 ))
        if (( resets % 3 == 0 )); then
            echo "$dev: $problem for $fails checks; resetting the NIC driver"
            rebind_driver "$dev" || echo "$dev: driver reset failed" >&2
        else
            echo "$dev: $problem for $fails checks; toggling the link"
            toggle_link "$dev" || echo "$dev: link toggle failed" >&2
        fi
        # Give the PHY time to renegotiate, then put the port back on its connection.
        for _ in $(seq 10); do has_link "$dev" && break; sleep 1; done
        if has_link "$dev"; then
            nmcli con up "$con" >/dev/null && echo "$dev: link is back; '$con' is up"
        else
            echo "$dev: still no link after the reset (is the arm powered and cabled?)"
        fi
    fi
    echo "$fails $resets" > "$state"
done
