#!/bin/bash
set -euo pipefail

ACTION="${1:-}"
ALLOWED_ACTIONS=("list" "units" "unit-logs" "boot-logs" "kernel-logs" "priority-logs")

if [[ ! " ${ALLOWED_ACTIONS[*]} " =~ " ${ACTION} " ]]; then
    echo "Error: Invalid action: ${ACTION}" >&2
    exit 1
fi

validate_input() {
    local input="$1"
    if echo "$input" | grep -qP '[;|&$()` ><*?{}\[\]\\]'; then
        echo "Error: Forbidden characters in input" >&2
        exit 1
    fi
}

case "${ACTION}" in
    list)
        LINES="${2:-100}"
        validate_input "${LINES}"
        journalctl -n "${LINES}" --no-pager --output=short-iso 2>/dev/null || echo "journalctl not available"
        ;;
    units)
        systemctl list-units --no-pager --plain --no-legend 2>/dev/null | head -200 || echo "systemctl not available"
        ;;
    unit-logs)
        UNIT="${2:-}"
        validate_input "${UNIT}"
        # ユニット名: 英数字/.-_@のみ許可
        if ! echo "${UNIT}" | grep -qP '^[a-zA-Z0-9._@:-]+$'; then
            echo "Error: Invalid unit name" >&2
            exit 1
        fi
        journalctl -u "${UNIT}" -n 100 --no-pager --output=short-iso 2>/dev/null || echo "Unit not found"
        ;;
    boot-logs)
        journalctl -b --no-pager -n 200 --output=short-iso 2>/dev/null || echo "journalctl not available"
        ;;
    kernel-logs)
        journalctl -k --no-pager -n 100 --output=short-iso 2>/dev/null || echo "journalctl not available"
        ;;
    priority-logs)
        PRIORITY="${2:-err}"
        ALLOWED_PRIORITIES=("emerg" "alert" "crit" "err" "warning" "notice" "info" "debug")
        if [[ ! " ${ALLOWED_PRIORITIES[*]} " =~ " ${PRIORITY} " ]]; then
            echo "Error: Invalid priority" >&2
            exit 1
        fi
        journalctl -p "${PRIORITY}" --no-pager -n 100 --output=short-iso 2>/dev/null || echo "journalctl not available"
        ;;
esac
