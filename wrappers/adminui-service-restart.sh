#!/bin/bash
# adminui-service-restart.sh - サービス再起動ラッパー
#
# 用途: 許可されたサービスのみを安全に再起動
# 権限: root 権限必要（systemctl restart）
# 呼び出し: sudo /usr/local/sbin/adminui-service-restart.sh <service_name>
#
# セキュリティ原則:
# - allowlist 方式（許可リストのサービスのみ）
# - 入力検証必須（特殊文字拒否）
# - 配列渡し（shell 展開防止）
# - ログ記録必須

set -euo pipefail

# ログ出力
log() {
    logger -t adminui-service-restart -p user.info "$*"
    echo "[$(date -Iseconds)] $*" >&2
}

# エラーログ
error() {
    logger -t adminui-service-restart -p user.err "ERROR: $*"
    echo "[$(date -Iseconds)] ERROR: $*" >&2
}

# 使用方法
usage() {
    echo "Usage: $0 <service_name>" >&2
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
)

# ===================================================================
# 禁止文字パターン
# ===================================================================
# shellcheck disable=SC2016
FORBIDDEN_CHARS='[;|&$()` ><*?{}[\]]'

# ===================================================================
# 入力検証
# ===================================================================

# 引数チェック
if [ $# -ne 1 ]; then
    error "Invalid number of arguments: expected 1, got $#"
    usage
fi

SERVICE_NAME="$1"

# 実行前ログ
log "Service restart requested: service=$SERVICE_NAME, caller_uid=${SUDO_UID:-$UID}, caller_user=${SUDO_USER:-$USER}"

# 1. 空文字チェック
if [ -z "$SERVICE_NAME" ]; then
    error "Service name is empty"
    exit 1
fi

# 2. 文字列長チェック（最大64文字）
if [ ${#SERVICE_NAME} -gt 64 ]; then
    error "Service name too long: ${#SERVICE_NAME} characters (max 64)"
    exit 1
fi

# 3. 特殊文字チェック
if [[ "$SERVICE_NAME" =~ $FORBIDDEN_CHARS ]]; then
    error "Forbidden character detected in service name: $SERVICE_NAME"
    log "SECURITY: Injection attempt detected - service=$SERVICE_NAME, caller=${SUDO_USER:-$USER}"
    exit 1
fi

# 4. 英数字・ハイフン・アンダースコアのみ許可
if [[ ! "$SERVICE_NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    error "Invalid service name format: $SERVICE_NAME (only alphanumeric, -, _ allowed)"
    exit 1
fi

# 5. allowlist チェック（最重要）
SERVICE_ALLOWED=false
for allowed in "${ALLOWED_SERVICES[@]}"; do
    if [ "$SERVICE_NAME" = "$allowed" ]; then
        SERVICE_ALLOWED=true
        break
    fi
done

if [ "$SERVICE_ALLOWED" = false ]; then
    error "Service not in allowlist: $SERVICE_NAME"
    log "SECURITY: Unauthorized service restart attempt - service=$SERVICE_NAME, caller=${SUDO_USER:-$USER}"

    echo "{\"status\": \"error\", \"message\": \"Service not allowed: $SERVICE_NAME\"}"
    exit 1
fi

# ===================================================================
# サービス再起動実行
# ===================================================================

log "Service restart authorized: $SERVICE_NAME"

# サービスの存在確認
if ! systemctl list-unit-files | grep -q "^${SERVICE_NAME}.service"; then
    error "Service not found: ${SERVICE_NAME}.service"
    echo "{\"status\": \"error\", \"message\": \"Service not found: $SERVICE_NAME\"}"
    exit 1
fi

# 再起動前の状態確認
BEFORE_STATUS=$(systemctl is-active "$SERVICE_NAME" || echo "inactive")
log "Service status before restart: $BEFORE_STATUS"

# 再起動実行（配列渡しでshell展開を防止）
if systemctl restart "$SERVICE_NAME"; then
    # 再起動後の状態確認
    sleep 1
    AFTER_STATUS=$(systemctl is-active "$SERVICE_NAME" || echo "failed")

    log "Service restart successful: service=$SERVICE_NAME, status=$AFTER_STATUS"

    echo "{\"status\": \"success\", \"service\": \"$SERVICE_NAME\", \"before\": \"$BEFORE_STATUS\", \"after\": \"$AFTER_STATUS\"}"
    exit 0
else
    error "Service restart failed: $SERVICE_NAME"

    # エラー詳細の取得
    ERROR_DETAIL=$(systemctl status "$SERVICE_NAME" 2>&1 | tail -5 | tr '\n' ' ')

    echo "{\"status\": \"error\", \"service\": \"$SERVICE_NAME\", \"message\": \"Restart failed\", \"detail\": \"$ERROR_DETAIL\"}"
    exit 1
fi
