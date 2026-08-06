#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

systemctl --user disable --now powerdeck-agent.service 2>/dev/null || true
rm -f "${HOME}/.config/systemd/user/powerdeck-agent.service"
rm -f "${HOME}/.local/share/applications/org.powerdeck.PowerDeck.desktop"
systemctl --user daemon-reload

sudo "${project_root}/scripts/uninstall-dev-daemon.sh"

echo "PowerDeck local v0.1 candidate removed."
