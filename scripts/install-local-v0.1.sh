#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

sudo pacman -S --needed \
    python-dbus-next \
    python-gobject \
    gtk4 \
    libadwaita \
    polkit \
    brightnessctl \
    power-profiles-daemon

if ! command -v wpctl >/dev/null 2>&1; then
    echo "Warning: wpctl is unavailable; audio mute support will be disabled." >&2
fi

sudo "${project_root}/scripts/install-dev-daemon.sh"

mkdir -p "${HOME}/.config/systemd/user"
sed "s|@PROJECT_ROOT@|${project_root}|g" \
    "${project_root}/data/systemd/user/powerdeck-agent.service" \
    > "${HOME}/.config/systemd/user/powerdeck-agent.service"

mkdir -p "${HOME}/.local/share/applications"
sed "s|@PROJECT_ROOT@|${project_root}|g" \
    "${project_root}/data/applications/org.powerdeck.PowerDeck.desktop" \
    > "${HOME}/.local/share/applications/org.powerdeck.PowerDeck.desktop"

chmod +x \
    "${project_root}/powerdeck" \
    "${project_root}/scripts/run-agent.sh"

systemctl --user daemon-reload
systemctl --user enable --now powerdeck-agent.service

echo
echo "PowerDeck v0.1 candidate installed."
echo "Launch: ${project_root}/powerdeck"
echo "Agent:  systemctl --user status powerdeck-agent.service"
