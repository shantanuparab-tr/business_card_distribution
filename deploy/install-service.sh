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
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="$(id -un)"

if [[ "${1:-}" == "--uninstall" ]]; then
    sudo systemctl disable --now "$UNIT" || true
    sudo rm -f "$DEST"
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

sed -e "s|@USER@|$USER_NAME|g" -e "s|@DIR@|$DIR|g" "$DIR/deploy/bcd-replay.service.in" \
    | sudo tee "$DEST" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now "$UNIT"

echo
echo "Installed and started $UNIT (runs as $USER_NAME from $DIR)."
echo "  Logs:    journalctl -u $UNIT -f"
echo "  Stop:    sudo systemctl stop $UNIT     (the arm parks first)"
echo "  Remove:  $0 --uninstall"
