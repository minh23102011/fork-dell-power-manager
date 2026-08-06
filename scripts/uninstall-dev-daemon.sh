#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this uninstaller with sudo." >&2
    exit 1
fi

systemctl disable --now powerdeckd.service 2>/dev/null || true

rm -f /usr/local/bin/powerdeckd
rm -f /etc/systemd/system/powerdeckd.service
rm -f /usr/local/share/dbus-1/system-services/org.powerdeck.System1.service
rm -f /usr/share/dbus-1/system.d/org.powerdeck.System1.conf
rm -f /usr/share/polkit-1/actions/org.powerdeck.system.policy

systemctl daemon-reload
systemctl reload dbus.service 2>/dev/null || true
systemctl reset-failed powerdeckd.service 2>/dev/null || true

echo "PowerDeck development daemon removed."
