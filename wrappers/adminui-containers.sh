#!/bin/bash
# Docker/Podman コンテナ管理ラッパー
# セキュリティ: allowlist方式、コンテナ名バリデーション必須
set -euo pipefail

COMMAND="${1:-}"
CONTAINER_NAME="${2:-}"

ALLOWED_COMMANDS=("list" "inspect" "start" "stop" "restart" "logs" "stats" "images" "prune-stopped")

# コマンド allowlist 検証
if [[ ! " ${ALLOWED_COMMANDS[*]} " =~ " ${COMMAND} " ]]; then
    echo "Error: Command not allowed: ${COMMAND}" >&2
    exit 1
fi

# コンテナ名バリデーション (list/images/prune-stopped は引数不要)
if [[ "${COMMAND}" != "list" && "${COMMAND}" != "images" && "${COMMAND}" != "prune-stopped" ]]; then
    if [[ -z "${CONTAINER_NAME}" ]] || [[ ! "${CONTAINER_NAME}" =~ ^[a-zA-Z0-9_.-]{1,128}$ ]]; then
        echo "Error: Invalid container name" >&2
        exit 1
    fi
fi

# docker か podman を自動検出
RUNTIME=""
if command -v docker &>/dev/null; then
    RUNTIME="docker"
elif command -v podman &>/dev/null; then
    RUNTIME="podman"
else
    echo "Error: Neither docker nor podman found" >&2
    exit 2
fi

case "${COMMAND}" in
    list)           ${RUNTIME} ps --all --format json 2>/dev/null || ${RUNTIME} ps --all --format "{{json .}}" ;;
    inspect)        ${RUNTIME} inspect "${CONTAINER_NAME}" ;;
    start)          ${RUNTIME} start "${CONTAINER_NAME}" ;;
    stop)           ${RUNTIME} stop "${CONTAINER_NAME}" ;;
    restart)        ${RUNTIME} restart "${CONTAINER_NAME}" ;;
    logs)
        TAIL_ARG="${3:-100}"
        if ! [[ "${TAIL_ARG}" =~ ^[0-9]+$ ]] || [[ "${TAIL_ARG}" -lt 1 ]] || [[ "${TAIL_ARG}" -gt 10000 ]]; then
            echo "Error: Invalid tail value" >&2
            exit 1
        fi
        ${RUNTIME} logs --tail="${TAIL_ARG}" "${CONTAINER_NAME}" 2>&1 ;;
    stats)          ${RUNTIME} stats --no-stream --format json "${CONTAINER_NAME}" 2>/dev/null || echo '{}' ;;
    images)         ${RUNTIME} images --format json 2>/dev/null || ${RUNTIME} images --format "{{json .}}" ;;
    prune-stopped)  ${RUNTIME} container prune -f ;;
esac
