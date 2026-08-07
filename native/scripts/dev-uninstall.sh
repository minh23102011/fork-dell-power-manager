#!/bin/sh
set -eu

SYSTEM_UNIT=/etc/systemd/system/powerdeckd.service
SYSTEM_BACKUP=/etc/systemd/system/powerdeckd.service.powerdeck-legacy
USER_UNIT="$HOME/.config/systemd/user/powerdeck-agent.service"
USER_BACKUP="$HOME/.config/systemd/user/powerdeck-agent.service.powerdeck-legacy"

systemctl --user disable --now powerdeck-agent.service 2>/dev/null || true
sudo systemctl disable --now powerdeckd.service 2>/dev/null || true

sudo rm -f /usr/bin/powerdeck
sudo rm -f /usr/bin/powerdeckctl
sudo rm -f /usr/bin/powerdeck-daemonctl
sudo rm -f /usr/bin/powerdeck-thermalctl
sudo rm -f /usr/bin/powerdeck-agentctl
sudo rm -f /usr/lib/powerdeck/powerdeckd
sudo rm -f /usr/lib/powerdeck/powerdeck-agent

sudo rm -f /etc/dbus-1/system.d/org.powerdeck.System1.conf
sudo rm -f /usr/share/dbus-1/system-services/org.powerdeck.System1.service
sudo rm -f /usr/share/dbus-1/services/org.powerdeck.Agent1.service
sudo rm -f /usr/share/polkit-1/actions/org.powerdeck.system.policy
sudo rm -f /usr/share/applications/org.powerdeck.PowerDeck.desktop

if [ -f "$SYSTEM_BACKUP" ]; then
    sudo mv "$SYSTEM_BACKUP" "$SYSTEM_UNIT"
else
    sudo rm -f "$SYSTEM_UNIT"
fi

if [ -f "$USER_BACKUP" ]; then
    mv "$USER_BACKUP" "$USER_UNIT"
else
    rm -f "$USER_UNIT"
fi

sudo systemctl daemon-reload
systemctl --user daemon-reload

if [ -f "$SYSTEM_UNIT" ]; then
    sudo systemctl enable --now powerdeckd.service 2>/dev/null || true
fi
if [ -f "$USER_UNIT" ]; then
    systemctl --user enable --now powerdeck-agent.service 2>/dev/null || true
fi

printf '%s\n' 'PowerDeck native development install removed.'
printf '%s\n' 'Legacy unit backups were restored when they existed.'
