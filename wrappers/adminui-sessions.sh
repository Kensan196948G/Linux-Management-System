#!/bin/bash
set -euo pipefail

ACTION="${1:-}"
ALLOWED_ACTIONS=("active" "history" "failed" "wtmp-summary")

if [[ ! " ${ALLOWED_ACTIONS[*]} " =~ " ${ACTION} " ]]; then
    echo "Error: Invalid action: ${ACTION}" >&2
    exit 1
fi

case "${ACTION}" in
    active)
        # アクティブなセッション (who -u または w)
        who -u 2>/dev/null || w 2>/dev/null || echo "No active sessions"
        ;;
    history)
        # ログイン履歴 (last -n 50)
        last -n 50 --time-format=iso 2>/dev/null || last -n 50 2>/dev/null || echo "No login history"
        ;;
    failed)
        # ログイン失敗 (faillog または journalctl)
        if command -v faillog >/dev/null 2>&1; then
            faillog -a 2>/dev/null | head -50
        else
            journalctl -u sshd -n 50 --no-pager 2>/dev/null | grep -i "failed\|invalid\|error" | head -50 || echo "No failed logins found"
        fi
        ;;
    wtmp-summary)
        # ログイン統計サマリー (last -F | 最近のログイン状況)
        last -n 20 --time-format=iso 2>/dev/null | head -20 || last -n 20 2>/dev/null | head -20 || echo "No wtmp data"
        ;;
esac
