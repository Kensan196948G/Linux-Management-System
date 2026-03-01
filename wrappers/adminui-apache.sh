#!/bin/bash
# ==============================================================================
# adminui-apache.sh - Apache Webserver 管理ラッパー（読み取り専用）
#
# 機能:
#   Apache HTTP Server の状態・設定・仮想ホスト・モジュール情報を取得する。
#   全操作は読み取り専用。設定の変更は行わない。
#
# 使用方法:
#   adminui-apache.sh <subcommand>
#
# サブコマンド:
#   status      - Apache サービス状態 (systemctl status / apache2ctl -t)
#   vhosts      - 仮想ホスト一覧 (apache2ctl -S)
#   modules     - ロード済みモジュール一覧 (apache2ctl -M)
#   config-check - 設定ファイル構文チェック (apache2ctl -t)
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - 許可サブコマンドのみ実行（allowlist方式）
#   - 読み取り専用（設定変更・再起動等は行わない）
# ==============================================================================

set -euo pipefail

ALLOWED_SUBCOMMANDS=("status" "vhosts" "modules" "config-check" "config" "logs")

error_json() {
    echo "{\"status\": \"error\", \"message\": \"$1\"}" >&2
    exit 1
}

if [ "$#" -ne 1 ]; then
    error_json "Usage: adminui-apache.sh <subcommand>"
fi

SUBCOMMAND="$1"

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

# apache2ctl / apache2 コマンドの存在チェック
APACHE2CTL=""
if command -v apache2ctl >/dev/null 2>&1; then
    APACHE2CTL="apache2ctl"
elif command -v apachectl >/dev/null 2>&1; then
    APACHE2CTL="apachectl"
fi

APACHE2BIN=""
if command -v apache2 >/dev/null 2>&1; then
    APACHE2BIN="apache2"
elif command -v httpd >/dev/null 2>&1; then
    APACHE2BIN="httpd"
fi

case "$SUBCOMMAND" in
    status)
        # Apache サービス状態を取得
        SERVICE_NAME=""
        if systemctl list-units --type=service 2>/dev/null | grep -q "apache2"; then
            SERVICE_NAME="apache2"
        elif systemctl list-units --type=service 2>/dev/null | grep -q "httpd"; then
            SERVICE_NAME="httpd"
        fi

        if [ -z "$SERVICE_NAME" ]; then
            echo "{\"status\": \"unavailable\", \"message\": \"Apache service not found\", \"timestamp\": \"${TIMESTAMP}\"}"
            exit 0
        fi

        # systemctl status（--no-pager でページャーなし）
        ACTIVE_STATE=$(systemctl is-active "${SERVICE_NAME}" 2>/dev/null || echo "unknown")
        ENABLED_STATE=$(systemctl is-enabled "${SERVICE_NAME}" 2>/dev/null || echo "unknown")

        # バージョン取得
        VERSION="unknown"
        if [ -n "$APACHE2BIN" ]; then
            VERSION=$("$APACHE2BIN" -v 2>/dev/null | head -1 | sed 's/Server version: //' || echo "unknown")
        elif [ -n "$APACHE2CTL" ]; then
            VERSION=$("$APACHE2CTL" -v 2>/dev/null | head -1 | sed 's/Server version: //' || echo "unknown")
        fi

        echo "{\"status\": \"success\", \"service\": \"${SERVICE_NAME}\", \"active\": \"${ACTIVE_STATE}\", \"enabled\": \"${ENABLED_STATE}\", \"version\": \"${VERSION}\", \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    vhosts)
        # 仮想ホスト一覧
        if [ -z "$APACHE2CTL" ]; then
            echo "{\"status\": \"unavailable\", \"message\": \"apache2ctl not found\", \"vhosts\": [], \"timestamp\": \"${TIMESTAMP}\"}"
            exit 0
        fi

        VHOSTS_OUTPUT=$("$APACHE2CTL" -S 2>&1 || true)
        # JSON エスケープ（ダブルクォート・バックスラッシュをエスケープ）
        VHOSTS_ESCAPED=$(echo "$VHOSTS_OUTPUT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo "\"${VHOSTS_OUTPUT}\"")

        echo "{\"status\": \"success\", \"vhosts_raw\": ${VHOSTS_ESCAPED}, \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    modules)
        # ロード済みモジュール一覧
        if [ -z "$APACHE2CTL" ]; then
            echo "{\"status\": \"unavailable\", \"message\": \"apache2ctl not found\", \"modules\": [], \"timestamp\": \"${TIMESTAMP}\"}"
            exit 0
        fi

        MODULES_OUTPUT=$("$APACHE2CTL" -M 2>&1 || true)
        MODULES_ESCAPED=$(echo "$MODULES_OUTPUT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo "\"${MODULES_OUTPUT}\"")

        echo "{\"status\": \"success\", \"modules_raw\": ${MODULES_ESCAPED}, \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    config-check)
        # 設定ファイル構文チェック
        if [ -z "$APACHE2CTL" ]; then
            echo "{\"status\": \"unavailable\", \"message\": \"apache2ctl not found\", \"timestamp\": \"${TIMESTAMP}\"}"
            exit 0
        fi

        CHECK_OUTPUT=$("$APACHE2CTL" -t 2>&1 || true)
        # Syntax OK かどうか判定
        if echo "$CHECK_OUTPUT" | grep -q "Syntax OK"; then
            SYNTAX_OK="true"
        else
            SYNTAX_OK="false"
        fi

        CHECK_ESCAPED=$(echo "$CHECK_OUTPUT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo "\"${CHECK_OUTPUT}\"")

        echo "{\"status\": \"success\", \"syntax_ok\": ${SYNTAX_OK}, \"output\": ${CHECK_ESCAPED}, \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    config)
        # /etc/apache2/apache2.conf の内容を取得
        CONFIG_FILE="/etc/apache2/apache2.conf"
        if [[ ! -f "$CONFIG_FILE" ]]; then
            # httpd の場合
            if [[ -f "/etc/httpd/conf/httpd.conf" ]]; then
                CONFIG_FILE="/etc/httpd/conf/httpd.conf"
            else
                echo "{\"status\": \"unavailable\", \"message\": \"Apache config file not found\", \"timestamp\": \"${TIMESTAMP}\"}"
                exit 0
            fi
        fi
        CONFIG_CONTENT=$(cat "$CONFIG_FILE" 2>/dev/null || echo "")
        CONFIG_ESCAPED=$(echo "$CONFIG_CONTENT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo "\"\"")
        echo "{\"status\": \"success\", \"config\": ${CONFIG_ESCAPED}, \"config_file\": \"${CONFIG_FILE}\", \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    logs)
        # /var/log/apache2/error.log の末尾N行
        LINES="${2:-50}"
        SAFE_LINES=$(python3 -c "n=int('$LINES') if '$LINES'.isdigit() else 50; print(max(1, min(200, n)))" 2>/dev/null || echo "50")
        LOG_FILE="/var/log/apache2/error.log"
        if [[ ! -f "$LOG_FILE" ]]; then
            if [[ -f "/var/log/httpd/error_log" ]]; then
                LOG_FILE="/var/log/httpd/error_log"
            else
                echo "{\"status\": \"success\", \"logs\": \"\", \"message\": \"Log file not found\", \"lines\": 0, \"timestamp\": \"${TIMESTAMP}\"}"
                exit 0
            fi
        fi
        LOG_CONTENT=$(tail -n "$SAFE_LINES" "$LOG_FILE" 2>/dev/null || echo "")
        LOG_ESCAPED=$(echo "$LOG_CONTENT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo "\"\"")
        LINE_COUNT=$(echo "$LOG_CONTENT" | wc -l)
        echo "{\"status\": \"success\", \"logs\": ${LOG_ESCAPED}, \"lines\": ${LINE_COUNT}, \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    *)
        error_json "Unexpected subcommand: $SUBCOMMAND"
        ;;
esac
