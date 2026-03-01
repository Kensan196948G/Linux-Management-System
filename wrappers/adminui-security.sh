#!/bin/bash
# adminui-security.sh — セキュリティ監査ラッパー
# 実行ユーザー: svc-adminui (sudo 経由)
set -euo pipefail

SUBCOMMAND="${1:-}"
ALLOWED=("audit-report" "failed-logins" "sudo-logs" "open-ports" "listening-services")

# allowlist チェック
VALID=0
for cmd in "${ALLOWED[@]}"; do
    if [[ "$SUBCOMMAND" == "$cmd" ]]; then
        VALID=1
        break
    fi
done

if [[ "$VALID" -eq 0 ]]; then
    echo '{"status":"error","message":"Subcommand not allowed"}' >&2
    exit 1
fi

# 特殊文字チェック
if [[ "$SUBCOMMAND" =~ [';|&$()' '`><*?{}[\]'] ]]; then
    echo '{"status":"error","message":"Invalid characters in subcommand"}' >&2
    exit 1
fi

AUTH_LOG="/var/log/auth.log"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

case "$SUBCOMMAND" in
    audit-report)
        AUTH_COUNT=0
        ACCEPTED=0
        FAILED=0
        SUDO_COUNT=0
        LAST_LOGIN=""

        if [[ -r "$AUTH_LOG" ]]; then
            AUTH_COUNT=$(wc -l < "$AUTH_LOG" 2>/dev/null || echo 0)
            ACCEPTED=$(grep -c "Accepted" "$AUTH_LOG" 2>/dev/null || echo 0)
            FAILED=$(grep -c "Failed" "$AUTH_LOG" 2>/dev/null || echo 0)
            SUDO_COUNT=$(grep -c "sudo:" "$AUTH_LOG" 2>/dev/null || echo 0)
        fi

        LAST_LOGIN=$(last -1 -w 2>/dev/null | head -1 || echo "N/A")
        # JSON エスケープ
        LAST_LOGIN="${LAST_LOGIN//\"/\\\"}"
        LAST_LOGIN="${LAST_LOGIN//	/ }"

        cat <<EOF
{"status":"success","auth_log_lines":${AUTH_COUNT},"accepted_logins":${ACCEPTED},"failed_logins":${FAILED},"sudo_count":${SUDO_COUNT},"last_login":"${LAST_LOGIN}","timestamp":"${TIMESTAMP}"}
EOF
        ;;

    failed-logins)
        ENTRIES="[]"
        if [[ -r "$AUTH_LOG" ]]; then
            # 失敗ログインを取得（最大50件）
            LINES=$(grep -E "Failed password|Invalid user" "$AUTH_LOG" 2>/dev/null | tail -50 || true)
            if [[ -n "$LINES" ]]; then
                # JSON配列として出力
                JSON_LINES=""
                while IFS= read -r line; do
                    ESCAPED="${line//\\/\\\\}"
                    ESCAPED="${ESCAPED//\"/\\\"}"
                    if [[ -n "$JSON_LINES" ]]; then
                        JSON_LINES="${JSON_LINES},\"${ESCAPED}\""
                    else
                        JSON_LINES="\"${ESCAPED}\""
                    fi
                done <<< "$LINES"
                ENTRIES="[${JSON_LINES}]"
            fi
        fi
        cat <<EOF
{"status":"success","entries":${ENTRIES},"timestamp":"${TIMESTAMP}"}
EOF
        ;;

    sudo-logs)
        ENTRIES="[]"
        if [[ -r "$AUTH_LOG" ]]; then
            LINES=$(grep "sudo:" "$AUTH_LOG" 2>/dev/null | tail -50 || true)
            if [[ -n "$LINES" ]]; then
                JSON_LINES=""
                while IFS= read -r line; do
                    ESCAPED="${line//\\/\\\\}"
                    ESCAPED="${ESCAPED//\"/\\\"}"
                    if [[ -n "$JSON_LINES" ]]; then
                        JSON_LINES="${JSON_LINES},\"${ESCAPED}\""
                    else
                        JSON_LINES="\"${ESCAPED}\""
                    fi
                done <<< "$LINES"
                ENTRIES="[${JSON_LINES}]"
            fi
        fi
        cat <<EOF
{"status":"success","entries":${ENTRIES},"timestamp":"${TIMESTAMP}"}
EOF
        ;;

    open-ports)
        OUTPUT=$(ss -tlnp 2>&1 || netstat -tlnp 2>/dev/null || echo "unavailable")
        ESCAPED="${OUTPUT//\\/\\\\}"
        ESCAPED="${ESCAPED//\"/\\\"}"
        ESCAPED="${ESCAPED//$'\n'/\\n}"
        cat <<EOF
{"status":"success","output":"${ESCAPED}","timestamp":"${TIMESTAMP}"}
EOF
        ;;

    listening-services)
        OUTPUT=$(ss -ulnp 2>&1 || echo "unavailable")
        ESCAPED="${OUTPUT//\\/\\\\}"
        ESCAPED="${ESCAPED//\"/\\\"}"
        ESCAPED="${ESCAPED//$'\n'/\\n}"
        cat <<EOF
{"status":"success","output":"${ESCAPED}","timestamp":"${TIMESTAMP}"}
EOF
        ;;
esac
