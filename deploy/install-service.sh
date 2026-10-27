#!/usr/bin/env bash
# Install (or remove) the bcd-replay systemd service so the booth starts at boot.
#
#   deploy/install-service.sh              install, enable, and start now
#   deploy/install-service.sh --uninstall  stop, disable, and remove
#
# Run it as your normal user from anywhere; it calls sudo where needed.
set -euo pipefail

UNIT=bcd-replay.service
DEST=/etc/systemd/system/$UNIT
NETCHECK=/usr/local/sbin/bcd-netcheck
FOLLOWER_CON=trossen-follower
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="$(id -un)"

if [[ "${1:-}" == "--uninstall" ]]; then
    sudo systemctl disable --now "$UNIT" bcd-netcheck.timer || true
    sudo rm -f "$DEST" "$NETCHECK" /etc/systemd/system/bcd-netcheck.{service,timer}
    sudo systemctl daemon-reload
    echo "Removed $UNIT"
    exit 0
fi

for name in idle give quirky; do
    [[ -f "$DIR/trajectories/${name}_motion.csv" ]] || {
        echo "Missing trajectories/${name}_motion.csv; record it first: uv run bcd-record $name" >&2
        exit 1
    }
done

# The service runs the venv directly (no uv at boot), so make sure it is built.
(cd "$DIR" && uv sync)

# The follower port: static 192.168.2.10/24, no gateway (it must never carry the
# default route), no IPv6 chatter, and the only profile that autoconnects on it.
if FOLLOWER_DEV=$(nmcli -g connection.interface-name con show "$FOLLOWER_CON" 2>/dev/null) \
        && [[ -n "$FOLLOWER_DEV" ]]; then
    sudo nmcli con modify "$FOLLOWER_CON" \
        ipv4.method manual ipv4.addresses 192.168.2.10/24 ipv4.gateway "" ipv4.dns "" \
        ipv4.never-default yes ipv6.method disabled \
        connection.autoconnect yes connection.autoconnect-priority 100
    for uuid in $(nmcli -g UUID con show); do
        name=$(nmcli -g connection.id con show "$uuid")
        [[ "$name" != "$FOLLOWER_CON" ]] || continue
        [[ "$(nmcli -g connection.interface-name con show "$uuid")" == "$FOLLOWER_DEV" ]] || continue
        [[ "$(nmcli -g connection.autoconnect con show "$uuid")" == yes ]] || continue
        echo "Stopping profile '$name' from autoconnecting on $FOLLOWER_DEV"
        sudo nmcli con modify "$uuid" connection.autoconnect no
    done
    sudo nmcli con up "$FOLLOWER_CON" >/dev/null 2>&1 \
        || echo "Note: '$FOLLOWER_CON' isn't up yet (no link on $FOLLOWER_DEV?); bcd-netcheck brings it up."
else
    echo "No NetworkManager connection '$FOLLOWER_CON' bound to a port; create it first (README, Hardware and network)." >&2
    exit 1
fi

sed -e "s|@USER@|$USER_NAME|g" -e "s|@DIR@|$DIR|g" "$DIR/deploy/bcd-replay.service.in" \
    | sudo tee "$DEST" >/dev/null
# Root helper that puts the follower port back on its connection if another
# profile takes it over. Copied out of the repo so root never runs a user-editable file.
sudo install -m 755 "$DIR/deploy/bcd-netcheck.sh" "$NETCHECK"
sudo install -m 644 "$DIR/deploy/bcd-netcheck.service" "$DIR/deploy/bcd-netcheck.timer" /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now bcd-netcheck.timer
sudo systemctl enable "$UNIT"
# restart, not start: a running service must pick up the new code (the arm parks first).
sudo systemctl restart "$UNIT"

echo
echo "Installed and started $UNIT (runs as $USER_NAME from $DIR)."
echo "Installed bcd-netcheck.timer (keeps the follower port up; resets it if the link or arm goes silent)."
echo "  Port log: journalctl -u bcd-netcheck.service -f"
echo "  Logs:    journalctl -u $UNIT -f"
echo "  Stop:    sudo systemctl stop $UNIT     (the arm parks first)"
echo "  Remove:  $0 --uninstall"
