#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v pacman >/dev/null 2>&1; then
    echo "PowerDeck's local installer currently supports Arch-style systems." >&2
    echo "Install the dependencies for your distribution manually, then rerun." >&2
    exit 1
fi

required_packages=(
    python
    python-dbus-next
    python-gobject
    gtk4
    libadwaita
    polkit
    brightnessctl
    power-profiles-daemon
)

echo "Installing required PowerDeck system packages..."
sudo pacman -S --needed "${required_packages[@]}"

"${project_root}/scripts/check-dependencies.sh" --required-only

if ! command -v wpctl >/dev/null 2>&1; then
    echo >&2
    echo "Optional dependency missing: wpctl" >&2
    echo "Audio mute support will be disabled." >&2
    echo "Install it on Arch/CachyOS with:" >&2
    echo "  sudo pacman -S --needed wireplumber" >&2
fi

if ! command -v niri >/dev/null 2>&1; then
    echo >&2
    echo "Optional dependency missing: niri" >&2
    echo "Automatic refresh-rate switching will be disabled." >&2
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
    "${project_root}/scripts/run-agent.sh" \
    "${project_root}/scripts/check-dependencies.sh"

systemctl --user daemon-reload
systemctl --user enable --now powerdeck-agent.service

echo
echo "PowerDeck v0.1 candidate installed."
echo "Launch: ${project_root}/powerdeck"
echo "Agent:  systemctl --user status powerdeck-agent.service"
echo
echo "Optional feature check:"
"${project_root}/scripts/check-dependencies.sh" --optional-only || true
