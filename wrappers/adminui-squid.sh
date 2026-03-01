#!/bin/bash
# ==============================================================================
# adminui-squid.sh - Squid Proxy Server 管理ラッパー（読み取り専用）
#
# 機能:
#   Squid プロキシサーバーの状態・キャッシュ統計・ログ・設定確認を取得する。
#   全操作は読み取り専用。設定変更は行わない。
#
# 使用方法:
#   adminui-squid.sh <subcommand> [lines]
#
# サブコマンド:
#   status       - Squid サービス状態 (systemctl status)
#   cache        - キャッシュ統計 (squidclient mgr:info / squid -k check)
#   logs         - アクセスログ (tail /var/log/squid/access.log)
#   config-check - 設定構文チェック (squid -k check)
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - 許可サブコマンドのみ実行（allowlist方式）
#   - 読み取り専用（設定変更・再起動等は行わない）
# ==============================================================================

set -euo pipefail

ALLOWED_SUBCOMMANDS=("status" "cache" "logs" "config-check")

error_json() {
    echo "{\"status\": \"error\", \"message\": \"$1\"}" >&2
    exit 1
}

if [ "$#" -lt 1 ]; then
    error_json "Usage: adminui-squid.sh <subcommand> [lines]"
fi

SUBCOMMAND="$1"
LINES="${2:-50}"

# lines パラメータの検証（数値のみ許可）
if ! [[ "$LINES" =~ ^[0-9]+$ ]]; then
    error_json "lines must be a positive integer"
fi
if [ "$LINES" -lt 1 ]; then LINES=1; fi
if [ "$LINES" -gt 200 ]; then LINES=200; fi

# allowlist 検証
ALLOWED=false
for cmd in "${ALLOWED_SUBCOMMANDS[@]}"; do
    if [ "$cmd" = "$SUBCOMMAND" ]; then
        ALLOWED=true
        break
    fi
done

if ! $ALLOWED; then
    error_json "Unknown subcommand: $SUBCOMMAND. Allowed: ${ALLOWED_SUBCOMMANDS[*]}"
fi

TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

json_escape() {
    python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo "\"(escape failed)\""
}

case "$SUBCOMMAND" in
    status)
        # Squid サービス状態を取得
        SERVICE_NAME=""
        if systemctl list-units --type=service 2>/dev/null | grep -q "squid"; then
            SERVICE_NAME="squid"
        fi

        if [ -z "$SERVICE_NAME" ]; then
            echo "{\"status\": \"unavailable\", \"message\": \"Squid service not found\", \"timestamp\": \"${TIMESTAMP}\"}"
            exit 0
        fi

        ACTIVE_STATE=$(systemctl is-active "${SERVICE_NAME}" 2>/dev/null || echo "unknown")
        ENABLED_STATE=$(systemctl is-enabled "${SERVICE_NAME}" 2>/dev/null || echo "unknown")

        # バージョン取得
        VERSION="unknown"
        if command -v squid >/dev/null 2>&1; then
            VERSION=$(squid --version 2>/dev/null | head -1 || echo "unknown")
        fi

        VERSION_ESCAPED=$(echo "$VERSION" | json_escape)
        echo "{\"status\": \"success\", \"service\": \"${SERVICE_NAME}\", \"active\": \"${ACTIVE_STATE}\", \"enabled\": \"${ENABLED_STATE}\", \"version\": ${VERSION_ESCAPED}, \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    cache)
        # キャッシュ統計 (squidclient mgr:info)
        if ! command -v squid >/dev/null 2>&1; then
            echo "{\"status\": \"unavailable\", \"message\": \"squid not found\", \"timestamp\": \"${TIMESTAMP}\"}"
            exit 0
        fi

        CACHE_OUTPUT=""
        if command -v squidclient >/dev/null 2>&1; then
            CACHE_OUTPUT=$(squidclient -h 127.0.0.1 mgr:info 2>/dev/null || echo "squidclient: connection failed (squid may not be running)")
        else
            CACHE_OUTPUT="squidclient not available. Install squid-common for cache statistics."
        fi

        CACHE_ESCAPED=$(echo "$CACHE_OUTPUT" | json_escape)
        echo "{\"status\": \"success\", \"cache_raw\": ${CACHE_ESCAPED}, \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    logs)
        # アクセスログ取得
        if ! command -v squid >/dev/null 2>&1; then
            echo "{\"status\": \"unavailable\", \"message\": \"squid not found\", \"timestamp\": \"${TIMESTAMP}\"}"
            exit 0
        fi

        LOG_OUTPUT=""

        if [ -f /var/log/squid/access.log ]; then
            LOG_OUTPUT=$(tail -n "${LINES}" /var/log/squid/access.log 2>/dev/null || echo "")
        elif [ -f /var/log/squid3/access.log ]; then
            LOG_OUTPUT=$(tail -n "${LINES}" /var/log/squid3/access.log 2>/dev/null || echo "")
        fi

        if [ -z "$LOG_OUTPUT" ]; then
            # journalctl でフォールバック
            LOG_OUTPUT=$(journalctl -u squid --no-pager -n "${LINES}" 2>/dev/null || echo "No Squid log entries found")
        fi

        LOG_ESCAPED=$(echo "$LOG_OUTPUT" | json_escape)
        echo "{\"status\": \"success\", \"logs_raw\": ${LOG_ESCAPED}, \"lines\": ${LINES}, \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    config-check)
        # 設定構文チェック (squid -k check)
        if ! command -v squid >/dev/null 2>&1; then
            echo "{\"status\": \"unavailable\", \"message\": \"squid not found\", \"timestamp\": \"${TIMESTAMP}\"}"
            exit 0
        fi

        CHECK_OUTPUT=$(squid -k check 2>&1 || true)
        # エラーがなければ空文字列または "squid: ERROR" を含まない
        if [ -z "$CHECK_OUTPUT" ] || ! echo "$CHECK_OUTPUT" | grep -qi "error\|fatal\|FATAL"; then
            SYNTAX_OK="true"
        else
            SYNTAX_OK="false"
        fi

        CHECK_ESCAPED=$(echo "$CHECK_OUTPUT" | json_escape)
        echo "{\"status\": \"success\", \"syntax_ok\": ${SYNTAX_OK}, \"output\": ${CHECK_ESCAPED}, \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    *)
        error_json "Unexpected subcommand: $SUBCOMMAND"
        ;;
esac
