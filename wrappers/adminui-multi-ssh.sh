#!/bin/bash
# マルチサーバーSSH実行ラッパー
# コマンドallowlist に定義済みのコマンドのみ実行を許可する
set -euo pipefail

COMMAND="${1:-}"
HOST="${2:-}"

ALLOWED_COMMANDS=(
    "hostname"
    "uptime"
    "df -h"
    "free -m"
    "uname -a"
    "systemctl is-active nginx"
    "systemctl is-active postgresql"
    "systemctl is-active redis"
    "systemctl is-active sshd"
    "cat /etc/os-release"
    "date"
)

# 引数の特殊文字チェック
for arg in "$@"; do
    if [[ "$arg" =~ [';|&$()>`><*?{}[\]'] ]]; then
        echo '{"status":"error","message":"Invalid characters in argument"}' >&2
        exit 1
    fi
done

# コマンドallowlist検証
ALLOWED=false
for allowed_cmd in "${ALLOWED_COMMANDS[@]}"; do
    if [[ "$COMMAND" == "$allowed_cmd" ]]; then
        ALLOWED=true
        break
    fi
done

if [[ "$ALLOWED" == false ]]; then
    echo '{"status":"error","message":"Command not in allowlist"}' >&2
    exit 1
fi

# ホスト名/IPの基本検証（英数字・ドット・ハイフンのみ）
if [[ ! "$HOST" =~ ^[a-zA-Z0-9._-]+$ ]]; then
    echo '{"status":"error","message":"Invalid host format"}' >&2
    exit 1
fi

SSH_KEY="/home/svc-adminui/.ssh/id_ed25519"

# 鍵ファイルが存在する場合のみ -i オプション付加
if [[ -f "$SSH_KEY" ]]; then
    ssh -o ConnectTimeout=5 \
        -o StrictHostKeyChecking=no \
        -o BatchMode=yes \
        -i "$SSH_KEY" \
        "$HOST" "$COMMAND" 2>&1
else
    ssh -o ConnectTimeout=5 \
        -o StrictHostKeyChecking=no \
        -o BatchMode=yes \
        "$HOST" "$COMMAND" 2>&1
fi
