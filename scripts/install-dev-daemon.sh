#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this installer with sudo." >&2
    exit 1
fi

if ! /usr/bin/python -c 'import dbus_next' >/dev/null 2>&1; then
    echo "Missing system package: python-dbus-next" >&2
    echo "Install it with: sudo pacman -S --needed python-dbus-next polkit" >&2
    exit 1
fi

cat > /usr/local/bin/powerdeckd <<EOF
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="${project_root}/src"
exec /usr/bin/python -m powerdeck_daemon.system_service "\$@"
EOF
chmod 0755 /usr/local/bin/powerdeckd

install -Dm0644 \
    "${project_root}/data/systemd/powerdeckd.service" \
    /etc/systemd/system/powerdeckd.service

install -Dm0644 \
    "${project_root}/data/dbus-1/system-services/org.powerdeck.System1.service" \
    /usr/local/share/dbus-1/system-services/org.powerdeck.System1.service

install -Dm0644 \
    "${project_root}/data/dbus-1/system.d/org.powerdeck.System1.conf" \
    /usr/share/dbus-1/system.d/org.powerdeck.System1.conf

install -Dm0644 \
    "${project_root}/data/polkit-1/actions/org.powerdeck.system.policy" \
    /usr/share/polkit-1/actions/org.powerdeck.system.policy

systemctl daemon-reload
systemctl reload dbus.service 2>/dev/null || true
systemctl enable --now powerdeckd.service
systemctl restart powerdeckd.service

echo
echo "PowerDeck system daemon installed from:"
echo "  ${project_root}"
echo
systemctl --no-pager --full status powerdeckd.service || true
