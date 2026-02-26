#!/bin/bash
# adminui-service-stop.sh - サービス停止ラッパー（要承認操作）
#
# 用途: 許可されたサービスのみを安全に停止（完全停止、再起動ではない）
# 権限: root 権限必要（systemctl stop）
# セキュリティ: 承認フロー経由でのみ呼び出し可能

set -euo pipefail

log() { logger -t adminui-service-stop -p user.info "$*"; echo "[$(date -Iseconds)] $*" >&2; }
error() { logger -t adminui-service-stop -p user.err "ERROR: $*"; echo "[$(date -Iseconds)] ERROR: $*" >&2; }

if [ "$#" -ne 1 ]; then
    echo '{"status":"error","message":"Usage: adminui-service-stop.sh <service_name>"}' >&2
    exit 1
fi

SERVICE_NAME="$1"

# ===================================================================
# 許可サービスリスト（allowlist）
# ===================================================================
ALLOWED_SERVICES=("nginx" "apache2" "mysql" "postgresql" "redis")

# 特殊文字チェック
if echo "$SERVICE_NAME" | grep -qE '[;|&$`><*?()\[\]{}]'; then
    echo '{"status":"error","message":"Invalid characters in service name"}' >&2
    exit 1
fi

# allowlist チェック
ALLOWED=false
for service in "${ALLOWED_SERVICES[@]}"; do
    if [ "$service" = "$SERVICE_NAME" ]; then
        ALLOWED=true
        break
    fi
done

if [ "$ALLOWED" = false ]; then
    echo "{\"status\":\"error\",\"message\":\"Service not allowed: ${SERVICE_NAME}\"}" >&2
    exit 1
fi

log "Stopping service: ${SERVICE_NAME}"

if systemctl stop "${SERVICE_NAME}" 2>/dev/null; then
    STATUS=$(systemctl is-active "${SERVICE_NAME}" 2>/dev/null | head -1 || echo "inactive")
    echo "{\"status\":\"success\",\"service\":\"${SERVICE_NAME}\",\"result\":\"stopped\",\"active_state\":\"${STATUS}\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    log "Service stopped successfully: ${SERVICE_NAME}"
else
    echo "{\"status\":\"error\",\"message\":\"Failed to stop service: ${SERVICE_NAME}\"}"
    error "Failed to stop service: ${SERVICE_NAME}"
    exit 1
fi
