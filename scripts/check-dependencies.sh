#!/usr/bin/env bash
set -euo pipefail

mode="all"
case "${1:-}" in
    "")
        ;;
    --required-only)
        mode="required"
        ;;
    --optional-only)
        mode="optional"
        ;;
    *)
        echo "Usage: $0 [--required-only|--optional-only]" >&2
        exit 2
        ;;
esac

required_failures=0

print_result() {
    local label="$1"
    local status="$2"
    local detail="$3"

    printf "%-30s %-10s %s\n" "${label}" "${status}" "${detail}"
}

check_command() {
    local command_name="$1"
    local package_name="$2"

    if command -v "${command_name}" >/dev/null 2>&1; then
        print_result "${command_name}" "available" "$(command -v "${command_name}")"
        return 0
    fi

    print_result "${command_name}" "missing" "package: ${package_name}"
    return 1
}

check_python_runtime() {
    if /usr/bin/python - <<'PY' >/dev/null 2>&1
import dbus_next
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: F401
PY
    then
        print_result \
            "Python GTK/D-Bus runtime" \
            "available" \
            "/usr/bin/python"
        return 0
    fi

    print_result \
        "Python GTK/D-Bus runtime" \
        "missing" \
        "python-dbus-next, python-gobject, gtk4, libadwaita"
    return 1
}

check_required() {
    echo "Required dependencies"
    echo "---------------------"

    check_command "/usr/bin/python" "python" || required_failures=1
    check_python_runtime || required_failures=1
    check_command "pkaction" "polkit" || required_failures=1
    check_command "brightnessctl" "brightnessctl" || required_failures=1
    check_command "powerprofilesctl" "power-profiles-daemon" || required_failures=1
    check_command "systemctl" "systemd" || required_failures=1
}

check_optional() {
    echo "Optional feature dependencies"
    echo "-----------------------------"

    check_command "niri" "niri" || true
    check_command "wpctl" "wireplumber" || true
}

if [[ "${mode}" != "optional" ]]; then
    check_required
fi

if [[ "${mode}" == "all" ]]; then
    echo
fi

if [[ "${mode}" != "required" ]]; then
    check_optional
fi

if [[ "${required_failures}" -ne 0 ]]; then
    echo >&2
    echo "One or more required PowerDeck dependencies are missing." >&2
    exit 1
fi
