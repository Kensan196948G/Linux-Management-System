#!/bin/bash
# adminui-postfix.sh - Postfix メール管理ラッパー
# セキュリティ: shell=False, allowlist による制御
set -euo pipefail

readonly ALLOWED_COMMANDS=("status" "queue" "logs" "mailq" "queue-detail" "config" "stats")

SUBCOMMAND="${1:-}"

if [[ -z "${SUBCOMMAND}" ]]; then
    echo '{"error":"subcommand required"}' >&2
    exit 1
fi

# allowlist チェック
found=false
for cmd in "${ALLOWED_COMMANDS[@]}"; do
    if [[ "${SUBCOMMAND}" == "${cmd}" ]]; then
        found=true
        break
    fi
done

if [[ "${found}" == "false" ]]; then
    echo "{\"error\":\"subcommand not allowed: ${SUBCOMMAND}\"}" >&2
    exit 1
fi

# postfix の存在確認
POSTFIX_BIN=""
if command -v postfix >/dev/null 2>&1; then
    POSTFIX_BIN="postfix"
fi

if [[ -z "${POSTFIX_BIN}" ]]; then
    echo '{"status":"unavailable","message":"postfix is not installed"}'
    exit 0
fi

case "${SUBCOMMAND}" in
    status)
        # Postfix サービス状態
        if command -v systemctl >/dev/null 2>&1; then
            if systemctl is-active --quiet postfix 2>/dev/null; then
                STATUS="running"
            else
                STATUS="stopped"
            fi
        else
            STATUS="unknown"
        fi

        VERSION=$(postfix version 2>/dev/null | head -1 || echo "unknown")
        QUEUE_COUNT=0
        if command -v mailq >/dev/null 2>&1; then
            QUEUE_COUNT=$(mailq 2>/dev/null | grep -c "^[A-F0-9]" || true)
        fi
        echo "{\"status\":\"${STATUS}\",\"version\":\"${VERSION}\",\"queue_count\":${QUEUE_COUNT}}"
        ;;
    queue)
        # メールキュー
        if command -v mailq >/dev/null 2>&1; then
            OUTPUT=$(mailq 2>/dev/null || echo "")
            # JSON エスケープ
            ESCAPED=$(echo "${OUTPUT}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
            echo "{\"queue\":${ESCAPED}}"
        else
            echo '{"queue":"","error":"mailq not available"}'
        fi
        ;;
    logs)
        # Postfix ログ
        LINES="${2:-50}"
        # LINES を整数に制限
        if ! [[ "${LINES}" =~ ^[0-9]+$ ]]; then
            LINES=50
        fi
        if [[ "${LINES}" -gt 200 ]]; then
            LINES=200
        fi
        if [[ "${LINES}" -lt 1 ]]; then
            LINES=50
        fi

        LOG_FILE=""
        if [[ -f "/var/log/mail.log" ]]; then
            LOG_FILE="/var/log/mail.log"
        elif [[ -f "/var/log/maillog" ]]; then
            LOG_FILE="/var/log/maillog"
        fi

        if [[ -n "${LOG_FILE}" ]]; then
            OUTPUT=$(tail -n "${LINES}" "${LOG_FILE}" 2>/dev/null || echo "")
        else
            OUTPUT=$(journalctl -u postfix --no-pager -n "${LINES}" 2>/dev/null || echo "")
        fi
        ESCAPED=$(echo "${OUTPUT}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
        echo "{\"logs\":${ESCAPED},\"lines\":${LINES}}"
        ;;
    mailq)
        # mailq コマンド出力
        OUTPUT=$(mailq 2>/dev/null || echo "Mail queue is empty")
        ESCAPED=$(echo "${OUTPUT}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
        echo "{\"output\":${ESCAPED}}"
        ;;
    queue-detail)
        # Postfix キュー詳細 (postqueue -p)
        if command -v postqueue >/dev/null 2>&1; then
            OUTPUT=$(postqueue -p 2>&1 | head -100 || echo "")
        else
            OUTPUT=""
        fi
        ESCAPED=$(echo "${OUTPUT}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
        echo "{\"queue_detail\":${ESCAPED}}"
        ;;
    config)
        # Postfix 本番設定 (postconf -n)
        if command -v postconf >/dev/null 2>&1; then
            OUTPUT=$(postconf -n 2>&1 || echo "")
        else
            OUTPUT=""
        fi
        ESCAPED=$(echo "${OUTPUT}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
        echo "{\"config\":${ESCAPED}}"
        ;;
    stats)
        # Postfix 送受信統計 (mail.log から集計)
        SENT=0
        RECEIVED=0
        DEFERRED=0
        LOG_FILE=""
        if [[ -f "/var/log/mail.log" ]]; then
            LOG_FILE="/var/log/mail.log"
        elif [[ -f "/var/log/maillog" ]]; then
            LOG_FILE="/var/log/maillog"
        fi
        if [[ -n "${LOG_FILE}" ]]; then
            SENT=$(grep -c " status=sent " "${LOG_FILE}" 2>/dev/null || true)
            RECEIVED=$(grep -c " message-id=" "${LOG_FILE}" 2>/dev/null || true)
            DEFERRED=$(grep -c " status=deferred " "${LOG_FILE}" 2>/dev/null || true)
        fi
        echo "{\"sent\":${SENT},\"received\":${RECEIVED},\"deferred\":${DEFERRED}}"
        ;;
esac
