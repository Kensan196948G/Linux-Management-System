#!/bin/bash
set -euo pipefail

# adminui-firewall-write.sh - UFW ルール管理ラッパー
# サブコマンド: allow-port, deny-port, delete-rule
# セキュリティ: ポート番号allowlist（1-65535の整数のみ）、プロトコルallowlist

SUBCOMMAND="${1:-}"

# 許可プロトコル
ALLOWED_PROTOCOLS=("tcp" "udp" "any")

validate_port() {
    local port="$1"
    if [[ ! "$port" =~ ^[0-9]+$ ]]; then
        echo '{"status": "error", "message": "Invalid port: must be integer"}' >&2
        exit 1
    fi
    if [[ "$port" -lt 1 || "$port" -gt 65535 ]]; then
        echo '{"status": "error", "message": "Invalid port: out of range (1-65535)"}' >&2
        exit 1
    fi
}

validate_protocol() {
    local proto="$1"
    local found=0
    for allowed in "${ALLOWED_PROTOCOLS[@]}"; do
        if [[ "$proto" == "$allowed" ]]; then
            found=1
            break
        fi
    done
    if [[ "$found" -eq 0 ]]; then
        echo '{"status": "error", "message": "Invalid protocol: must be tcp/udp/any"}' >&2
        exit 1
    fi
}

validate_rule_num() {
    local num="$1"
    if [[ ! "$num" =~ ^[0-9]+$ ]]; then
        echo '{"status": "error", "message": "Invalid rule number: must be integer"}' >&2
        exit 1
    fi
    if [[ "$num" -lt 1 || "$num" -gt 999 ]]; then
        echo '{"status": "error", "message": "Invalid rule number: out of range (1-999)"}' >&2
        exit 1
    fi
}

case "$SUBCOMMAND" in
    allow-port)
        PORT="${2:-}"
        PROTOCOL="${3:-tcp}"
        validate_port "$PORT"
        validate_protocol "$PROTOCOL"
        if [[ "$PROTOCOL" == "any" ]]; then
            ufw allow "${PORT}"
        else
            ufw allow "${PORT}/${PROTOCOL}"
        fi
        echo "{\"status\": \"success\", \"message\": \"Port ${PORT}/${PROTOCOL} allowed\", \"port\": ${PORT}, \"protocol\": \"${PROTOCOL}\"}"
        ;;
    deny-port)
        PORT="${2:-}"
        PROTOCOL="${3:-tcp}"
        validate_port "$PORT"
        validate_protocol "$PROTOCOL"
        if [[ "$PROTOCOL" == "any" ]]; then
            ufw deny "${PORT}"
        else
            ufw deny "${PORT}/${PROTOCOL}"
        fi
        echo "{\"status\": \"success\", \"message\": \"Port ${PORT}/${PROTOCOL} denied\", \"port\": ${PORT}, \"protocol\": \"${PROTOCOL}\"}"
        ;;
    delete-rule)
        RULE_NUM="${2:-}"
        validate_rule_num "$RULE_NUM"
        echo "y" | ufw delete "${RULE_NUM}"
        echo "{\"status\": \"success\", \"message\": \"Rule ${RULE_NUM} deleted\", \"rule_num\": ${RULE_NUM}}"
        ;;
    *)
        echo "{\"status\": \"error\", \"message\": \"Unknown subcommand: ${SUBCOMMAND}. Use: allow-port, deny-port, delete-rule\"}" >&2
        exit 1
        ;;
esac
