#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
port="${1:-8080}"

echo "PowerDeck README demo:"
echo "  http://127.0.0.1:${port}/README.html"
exec /usr/bin/python -m http.server \
    "${port}" \
    --bind 127.0.0.1 \
    --directory "${project_root}"
