#!/bin/bash
# adminui-logs.sh - ログ閲覧ラッパー
#
# 用途: journalctl を使用した安全なログ閲覧
# 権限: root 権限必要（全ログへのアクセス）
# 呼び出し: sudo /usr/local/sbin/adminui-logs.sh <service_name> [lines]
#
# セキュリティ原則:
# - allowlist 方式
# - 入力検証必須
# - ログ出力行数制限

set -euo pipefail

# ログ出力
log() {
    logger -t adminui-logs -p user.info "$*"
    echo "[$(date -Iseconds)] $*" >&2
}

# エラーログ
error() {
    logger -t adminui-logs -p user.err "ERROR: $*"
    echo "[$(date -Iseconds)] ERROR: $*" >&2
}

# 使用方法
usage() {
    echo "Usage: $0 <service_name> [lines]" >&2
    echo "" >&2
    echo "Arguments:" >&2
    echo "  service_name: Service to view logs (required)" >&2
    echo "  lines:        Number of lines to display (optional, default: 100, max: 1000)" >&2
    echo "" >&2
    echo "Allowed services:" >&2
    for service in "${ALLOWED_SERVICES[@]}"; do
        echo "  - $service" >&2
    done
    exit 1
}

# ===================================================================
# 許可サービスリスト（allowlist）
# ===================================================================
ALLOWED_SERVICES=(
    "nginx"
    "postgresql"
    "redis"
    "sshd"
    "systemd"
)

# ===================================================================
# 禁止文字パターン
# ===================================================================
# shellcheck disable=SC2016
FORBIDDEN_CHARS='[;|&$()` ><*?{}[\]]'

# ===================================================================
# デフォルト設定
# ===================================================================
DEFAULT_LINES=100
MAX_LINES=1000

# ===================================================================
# 入力検証
# ===================================================================

# 引数チェック
if [ $# -lt 1 ] || [ $# -gt 2 ]; then
    error "Invalid number of arguments: expected 1-2, got $#"
    usage
fi

SERVICE_NAME="$1"
LINES="${2:-$DEFAULT_LINES}"

# 実行前ログ
log "Log view requested: service=$SERVICE_NAME, lines=$LINES, caller=${SUDO_USER:-$USER}"

# サービス名の検証
if [ -z "$SERVICE_NAME" ]; then
    error "Service name is empty"
    exit 1
fi

if [ ${#SERVICE_NAME} -gt 64 ]; then
    error "Service name too long"
    exit 1
fi

if [[ "$SERVICE_NAME" =~ $FORBIDDEN_CHARS ]]; then
    error "Forbidden character detected in service name"
    exit 1
fi

if [[ ! "$SERVICE_NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    error "Invalid service name format"
    exit 1
fi

# allowlist チェック
SERVICE_ALLOWED=false
for allowed in "${ALLOWED_SERVICES[@]}"; do
    if [ "$SERVICE_NAME" = "$allowed" ]; then
        SERVICE_ALLOWED=true
        break
    fi
done

if [ "$SERVICE_ALLOWED" = false ]; then
    error "Service not in allowlist: $SERVICE_NAME"
    log "SECURITY: Unauthorized log view attempt - service=$SERVICE_NAME, caller=${SUDO_USER:-$USER}"
    echo "{\"status\": \"error\", \"message\": \"Service not allowed: $SERVICE_NAME\"}"
    exit 1
fi

# 行数の検証
if [[ ! "$LINES" =~ ^[0-9]+$ ]]; then
    error "Invalid lines parameter: must be a number"
    exit 1
fi

if [ "$LINES" -lt 1 ]; then
    LINES=1
elif [ "$LINES" -gt "$MAX_LINES" ]; then
    log "WARN: Requested lines ($LINES) exceeds max ($MAX_LINES), capping to $MAX_LINES"
    LINES=$MAX_LINES
fi

# ===================================================================
# ログ取得実行
# ===================================================================

log "Log view authorized: service=$SERVICE_NAME, lines=$LINES"

# journalctl でログを取得（配列渡し）
if OUTPUT=$(journalctl -u "$SERVICE_NAME" -n "$LINES" --no-pager 2>&1); then
    # ログ行数をカウント
    LINE_COUNT=$(echo "$OUTPUT" | wc -l)
    log "Log retrieval successful: service=$SERVICE_NAME, lines=$LINE_COUNT"

    # JSON 形式で出力
    echo "{"
    echo "  \"status\": \"success\","
    echo "  \"service\": \"$SERVICE_NAME\","
    echo "  \"lines_requested\": $LINES,"
    echo "  \"lines_returned\": $LINE_COUNT,"
    echo "  \"logs\": ["

    # ログを JSON 配列として出力
    FIRST=true
    while IFS= read -r line; do
        if [ "$FIRST" = false ]; then
            echo ","
        fi
        FIRST=false

        # JSON エスケープ（簡易版）
        ESCAPED_LINE=$(echo "$line" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g' | sed 's/\t/\\t/g')
        echo -n "    \"$ESCAPED_LINE\""
    done <<< "$OUTPUT"

    echo ""
    echo "  ],"
    echo "  \"timestamp\": \"$(date -Iseconds)\""
    echo "}"

    exit 0
else
    error "Failed to retrieve logs for service: $SERVICE_NAME"
    echo "{\"status\": \"error\", \"service\": \"$SERVICE_NAME\", \"message\": \"Failed to retrieve logs\"}"
    exit 1
fi
