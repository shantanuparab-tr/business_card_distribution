#!/usr/bin/env bash
# Keep the arm ports on their own NetworkManager connections. Run as root by
# bcd-netcheck.timer every 30 s; installed to /usr/local/sbin/bcd-netcheck.
#
#   bcd-netcheck [CONNECTION...]     (default: trossen-follower)
#
# For each connection: if its interface has a link but that connection isn't the
# active one, or the interface lacks the connection's address, bring it back up.
# This undoes another profile grabbing the port (e.g. an old setup's
# `nmcli con up`). A port with no link is left alone: that's a cable or arm power
# problem, and bcd-replay's log names it.
set -uo pipefail

[[ $# -gt 0 ]] || set -- trossen-follower

for con in "$@"; do
    if ! dev=$(nmcli -g connection.interface-name con show "$con" 2>/dev/null) || [[ -z "$dev" ]]; then
        echo "connection '$con' not found or not bound to an interface" >&2
        continue
    fi
    [[ "$(cat "/sys/class/net/$dev/carrier" 2>/dev/null)" == 1 ]] || continue

    want=$(nmcli -g ipv4.addresses con show "$con")
    active=$(nmcli -g GENERAL.CONNECTION dev show "$dev" 2>/dev/null)
    if [[ "$active" != "$con" ]] || ! ip -4 -o addr show dev "$dev" | grep -qF " inet $want "; then
        echo "$dev: active connection '${active:-none}', expected '$con' with $want; reactivating"
        nmcli con up "$con" >/dev/null && echo "$dev: '$con' is up"
    fi
done
