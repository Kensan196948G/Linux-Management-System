#!/bin/bash
# ==============================================================================
# adminui-fail2ban.sh - Fail2ban 管理ラッパースクリプト
#
# 機能:
#   fail2ban-client を安全に呼び出す allowlist ベースのラッパー
#
# 使用方法:
#   adminui-fail2ban.sh <command> [jail] [ip]
#
# コマンド:
#   status       - fail2ban サービス全体の状態
#   jail-list    - jail 一覧（改行区切り）
#   jail-status  - 特定 jail の詳細状態（jail 名必須）
#   banned-ips   - 特定 jail の禁止 IP 一覧（jail 名必須）
#   unban        - IP を unban（jail 名・IP 必須）
#   ban          - IP を ban（jail 名・IP 必須）
#   reload       - fail2ban 設定をリロード
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - allowlist 方式: 許可コマンドのみ実行
#   - jail 名バリデーション: ^[a-zA-Z0-9_-]{1,64}$
#   - IP バリデーション: IPv4/IPv6 正規表現のみ
# ==============================================================================

set -euo pipefail

COMMAND="${1:-}"
JAIL="${2:-}"
IP="${3:-}"

ALLOWED_COMMANDS=("status" "jail-list" "jail-status" "banned-ips" "unban" "ban" "reload")

# ==============================================================================
# コマンド allowlist チェック
# ==============================================================================

ALLOWED=false
for cmd in "${ALLOWED_COMMANDS[@]}"; do
    if [[ "${cmd}" == "${COMMAND}" ]]; then
        ALLOWED=true
        break
    fi
done

if [[ "${ALLOWED}" == "false" ]]; then
    echo "Error: Command not allowed: ${COMMAND}" >&2
    exit 1
fi

# ==============================================================================
# jail 名バリデーション
# ==============================================================================

if [[ -n "${JAIL}" && ! "${JAIL}" =~ ^[a-zA-Z0-9_-]{1,64}$ ]]; then
    echo "Error: Invalid jail name" >&2
    exit 1
fi

# ==============================================================================
# IP アドレスバリデーション (IPv4/IPv6)
# ==============================================================================

if [[ -n "${IP}" ]]; then
    if [[ ! "${IP}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] && \
       [[ ! "${IP}" =~ ^[0-9a-fA-F:]{2,39}$ ]]; then
        echo "Error: Invalid IP address" >&2
        exit 1
    fi
fi

# ==============================================================================
# jail 名・IP が必要なコマンドの引数チェック
# ==============================================================================

case "${COMMAND}" in
    jail-status|banned-ips)
        if [[ -z "${JAIL}" ]]; then
            echo "Error: jail name required for command: ${COMMAND}" >&2
            exit 1
        fi
        ;;
    unban|ban)
        if [[ -z "${JAIL}" || -z "${IP}" ]]; then
            echo "Error: jail name and IP required for command: ${COMMAND}" >&2
            exit 1
        fi
        ;;
esac

# ==============================================================================
# fail2ban-client の存在確認
# ==============================================================================

if ! command -v fail2ban-client &>/dev/null; then
    echo "Error: fail2ban-client not found" >&2
    exit 2
fi

# ==============================================================================
# コマンド実行
# ==============================================================================

case "${COMMAND}" in
    status)
        fail2ban-client status
        ;;
    jail-list)
        fail2ban-client status | grep "Jail list" | sed 's/.*Jail list:\s*//' | tr ',' '\n' | tr -d ' '
        ;;
    jail-status)
        fail2ban-client status "${JAIL}"
        ;;
    banned-ips)
        fail2ban-client status "${JAIL}" | grep "Banned IP" | awk '{print $NF}'
        ;;
    unban)
        fail2ban-client set "${JAIL}" unbanip "${IP}"
        ;;
    ban)
        fail2ban-client set "${JAIL}" banip "${IP}"
        ;;
    reload)
        fail2ban-client reload
        ;;
esac
