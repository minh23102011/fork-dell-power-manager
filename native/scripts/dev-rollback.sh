#!/bin/sh
set -eu

sudo rm -f /etc/systemd/system/powerdeckd.service.d/50-native.conf
rm -f "$HOME/.config/systemd/user/powerdeck-agent.service.d/50-native.conf"

sudo systemctl daemon-reload
systemctl --user daemon-reload
sudo systemctl restart powerdeckd
systemctl --user restart powerdeck-agent

printf '%s\n' 'PowerDeck runtime switched back to the original services.'
