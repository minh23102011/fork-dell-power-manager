#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PROJECT=$(CDPATH= cd -- "$ROOT/.." && pwd)

DAEMON="$ROOT/target/release/powerdeckd-native"
AGENT="$ROOT/target/release/powerdeck-agent-native"
CLI="$ROOT/target/release/powerdeckctl-native"
GUI="$ROOT/qt/build/powerdeck-native"
SYSTEM_UNIT=/etc/systemd/system/powerdeckd.service
SYSTEM_BACKUP=/etc/systemd/system/powerdeckd.service.powerdeck-legacy
USER_UNIT="$HOME/.config/systemd/user/powerdeck-agent.service"
USER_BACKUP="$HOME/.config/systemd/user/powerdeck-agent.service.powerdeck-legacy"

for file in "$DAEMON" "$AGENT" "$CLI" "$GUI"; do
    if [ ! -f "$file" ]; then
        printf '%s\n' "missing build/install input: $file" >&2
        printf '%s\n' "run $ROOT/scripts/build-release.sh first" >&2
        exit 1
    fi
done

printf '%s\n' '==> Saving legacy unit backups when present'
if [ -f "$SYSTEM_UNIT" ] && [ ! -f "$SYSTEM_BACKUP" ]; then
    sudo cp -a "$SYSTEM_UNIT" "$SYSTEM_BACKUP"
fi
mkdir -p "$HOME/.config/systemd/user"
if [ -f "$USER_UNIT" ] && [ ! -f "$USER_BACKUP" ]; then
    cp -a "$USER_UNIT" "$USER_BACKUP"
fi

printf '%s\n' '==> Installing native binaries'
sudo install -Dm755 "$DAEMON" /usr/lib/powerdeck/powerdeckd
sudo install -Dm755 "$AGENT" /usr/lib/powerdeck/powerdeck-agent
sudo install -Dm755 "$CLI" /usr/bin/powerdeckctl
sudo install -Dm755 "$GUI" /usr/bin/powerdeck

printf '%s\n' '==> Installing compatibility CLI names'
sudo ln -sfn powerdeckctl /usr/bin/powerdeck-daemonctl
sudo ln -sfn powerdeckctl /usr/bin/powerdeck-thermalctl
sudo ln -sfn powerdeckctl /usr/bin/powerdeck-agentctl

printf '%s\n' '==> Installing native service integration'
sudo install -Dm644 "$PROJECT/data/systemd/powerdeckd.service" "$SYSTEM_UNIT"
install -Dm644 "$PROJECT/data/systemd/user/powerdeck-agent.service" "$USER_UNIT"
sudo install -Dm644 \
    "$PROJECT/data/dbus-1/system.d/org.powerdeck.System1.conf" \
    /etc/dbus-1/system.d/org.powerdeck.System1.conf
sudo install -Dm644 \
    "$PROJECT/data/dbus-1/system-services/org.powerdeck.System1.service" \
    /usr/share/dbus-1/system-services/org.powerdeck.System1.service
sudo install -Dm644 \
    "$PROJECT/data/dbus-1/services/org.powerdeck.Agent1.service" \
    /usr/share/dbus-1/services/org.powerdeck.Agent1.service
sudo install -Dm644 \
    "$PROJECT/data/polkit-1/actions/org.powerdeck.system.policy" \
    /usr/share/polkit-1/actions/org.powerdeck.system.policy
sudo install -Dm644 \
    "$PROJECT/data/applications/org.powerdeck.PowerDeck.desktop" \
    /usr/share/applications/org.powerdeck.PowerDeck.desktop

printf '%s\n' '==> Removing obsolete native migration drop-ins'
sudo rm -f /etc/systemd/system/powerdeckd.service.d/50-native.conf
rm -f "$HOME/.config/systemd/user/powerdeck-agent.service.d/50-native.conf"

printf '%s\n' '==> Reloading and starting native services'
sudo systemctl daemon-reload
systemctl --user daemon-reload
sudo systemctl enable --now powerdeckd.service
systemctl --user enable --now powerdeck-agent.service

printf '%s\n' '==> Native development install complete'
printf '%s\n' 'GUI: powerdeck'
printf '%s\n' 'CLI: powerdeckctl status'
printf '%s\n' "Rollback installer state: $ROOT/scripts/dev-uninstall.sh"
