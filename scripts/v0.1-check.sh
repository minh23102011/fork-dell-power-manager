#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${project_root}/src${PYTHONPATH:+:${PYTHONPATH}}"

echo "== quality gate =="
"${project_root}/.venv/bin/python" -m ruff check "${project_root}"
"${project_root}/.venv/bin/python" -m mypy "${project_root}/src"
"${project_root}/.venv/bin/python" -m pytest "${project_root}"
"${project_root}/.venv/bin/python" -m compileall -q "${project_root}/src"

echo
echo "== system daemon =="
/usr/bin/python -m powerdeck_daemon.daemonctl ping
/usr/bin/python - <<'PY'
import asyncio
import json

from powerdeck_daemon.client import SystemClient

async def main() -> None:
    client = await SystemClient.connect()
    try:
        payload = {
            "thermal": await client.get_thermal_state(),
            "battery": await client.get_charge_state(),
            "cpu": await client.get_cpu_state(),
        }
    finally:
        client.disconnect()
    print(json.dumps(payload, indent=2, sort_keys=True))

asyncio.run(main())
PY

echo
echo "== session tools =="
for command in niri brightnessctl powerprofilesctl wpctl; do
    if command -v "${command}" >/dev/null 2>&1; then
        echo "${command}: available"
    else
        echo "${command}: unavailable"
    fi
done

echo
echo "== user agent =="
if systemctl --user is-active --quiet powerdeck-agent.service; then
    echo "powerdeck-agent.service: active"
    /usr/bin/python -m powerdeck_agent.agentctl status
else
    echo "powerdeck-agent.service: not active"
    echo "Run ./scripts/install-local-v0.1.sh after the quality gate."
fi

echo
echo "Read-only checks passed."
echo "Open ./powerdeck for controlled write tests."
