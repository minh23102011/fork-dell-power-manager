#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PROJECT=$(CDPATH= cd -- "$ROOT/.." && pwd)
DAEMON="$ROOT/target/release/powerdeckd-native"
AGENT="$ROOT/target/release/powerdeck-agent-native"
GUI="$ROOT/qt/build/powerdeck-native"
SYSTEM_DROPIN="$ROOT/data/systemd/powerdeckd.service.d/50-native.conf"
USER_DROPIN="$ROOT/data/systemd/user/powerdeck-agent.service.d/50-native.conf"
DESKTOP="$ROOT/data/applications/org.powerdeck.PowerDeck.Native.desktop"

for file in "$DAEMON" "$AGENT" "$GUI" "$SYSTEM_DROPIN" "$USER_DROPIN" "$DESKTOP"; do
    if [ ! -f "$file" ]; then
        printf '%s\n' "missing build/install input: $file" >&2
        printf '%s\n' "run $ROOT/scripts/build-release.sh first" >&2
        exit 1
    fi
done

printf '%s\n' '==> Installing native binaries'
sudo install -Dm755 "$DAEMON" /usr/local/libexec/powerdeck/powerdeckd-native
install -Dm755 "$AGENT" "$HOME/.local/libexec/powerdeck/powerdeck-agent-native"
sudo install -Dm755 "$GUI" /usr/local/bin/powerdeck-native

printf '%s\n' '==> Installing reversible systemd overrides'
sudo install -Dm644 "$SYSTEM_DROPIN" /etc/systemd/system/powerdeckd.service.d/50-native.conf
install -Dm644 "$USER_DROPIN" "$HOME/.config/systemd/user/powerdeck-agent.service.d/50-native.conf"

printf '%s\n' '==> Installing native desktop entry'
install -Dm644 "$DESKTOP" "$HOME/.local/share/applications/org.powerdeck.PowerDeck.Native.desktop"

printf '%s\n' '==> Reloading and restarting PowerDeck services'
sudo systemctl daemon-reload
systemctl --user daemon-reload
sudo systemctl restart powerdeckd
systemctl --user restart powerdeck-agent

printf '%s\n' '==> Native development install complete'
printf '%s\n' 'Run: /usr/local/bin/powerdeck-native'
printf '%s\n' "Rollback: $PROJECT/native/scripts/dev-rollback.sh"
