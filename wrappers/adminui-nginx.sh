#!/usr/bin/env bash
# ==============================================================================
# adminui-nginx.sh - Nginx Webサーバー管理ラッパー（読み取り専用）
#
# 使用方法:
#   adminui-nginx.sh status         - Nginx サービス状態
#   adminui-nginx.sh config         - 設定ダンプ (nginx -T)
#   adminui-nginx.sh vhosts         - バーチャルホスト一覧
#   adminui-nginx.sh connections    - 接続状況
#   adminui-nginx.sh logs [lines]   - アクセスログ末尾N行 (デフォルト50)
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - 許可サブコマンドのみ実行（allowlist方式）
#   - 読み取り専用（設定変更・再起動等は行わない）
# ==============================================================================

set -euo pipefail

ALLOWED_SUBCOMMANDS=("status" "config" "vhosts" "connections" "logs")

error_json() {
    local message="$1"
    printf '{"status":"error","message":"%s","timestamp":"%s"}\n' \
        "$message" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
}

timestamp() {
    date -u '+%Y-%m-%dT%H:%M:%SZ'
}

json_escape() {
    python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null
}

if [[ $# -lt 1 ]]; then
    error_json "Usage: adminui-nginx.sh <subcommand> [args]"
    exit 1
fi

SUBCOMMAND="$1"

ALLOWED=false
for cmd in "${ALLOWED_SUBCOMMANDS[@]}"; do
    if [[ "$SUBCOMMAND" == "$cmd" ]]; then
        ALLOWED=true
        break
    fi
done

if ! $ALLOWED; then
    error_json "Unknown subcommand: $SUBCOMMAND. Allowed: ${ALLOWED_SUBCOMMANDS[*]}"
    exit 1
fi

# nginx がインストールされているか確認
if ! command -v nginx &>/dev/null; then
    printf '{"status":"unavailable","message":"nginx not installed","timestamp":"%s"}\n' "$(timestamp)"
    exit 0
fi

case "$SUBCOMMAND" in

    # ------------------------------------------------------------------
    # status: Nginx サービス状態
    # ------------------------------------------------------------------
    status)
        ACTIVE=$(systemctl is-active nginx 2>/dev/null || echo "unknown")
        ENABLED=$(systemctl is-enabled nginx 2>/dev/null || echo "unknown")
        VERSION=$(nginx -v 2>&1 | head -1 | sed 's/nginx version: //' || echo "unknown")
        printf '{"status":"success","service":"nginx","active":"%s","enabled":"%s","version":"%s","timestamp":"%s"}\n' \
            "$ACTIVE" "$ENABLED" "$VERSION" "$(timestamp)"
        ;;

    # ------------------------------------------------------------------
    # config: 設定ダンプ (nginx -T)
    # ------------------------------------------------------------------
    config)
        CONFIG_OUTPUT=$(nginx -T 2>&1 || true)
        CONFIG_ESCAPED=$(printf '%s' "$CONFIG_OUTPUT" | json_escape)
        printf '{"status":"success","config":%s,"timestamp":"%s"}\n' \
            "$CONFIG_ESCAPED" "$(timestamp)"
        ;;

    # ------------------------------------------------------------------
    # vhosts: /etc/nginx/sites-enabled/ のファイル一覧
    # ------------------------------------------------------------------
    vhosts)
        SITES_DIR="/etc/nginx/sites-enabled"
        if [[ ! -d "$SITES_DIR" ]]; then
            printf '{"status":"success","vhosts":[],"message":"sites-enabled directory not found","timestamp":"%s"}\n' \
                "$(timestamp)"
            exit 0
        fi
        VHOSTS_JSON=$(python3 -c "
import os, json
sites_dir = '$SITES_DIR'
files = []
try:
    for f in sorted(os.listdir(sites_dir)):
        fpath = os.path.join(sites_dir, f)
        files.append({'name': f, 'path': fpath, 'is_symlink': os.path.islink(fpath)})
except Exception as e:
    files = []
print(json.dumps(files))
" 2>/dev/null || echo "[]")
        printf '{"status":"success","vhosts":%s,"timestamp":"%s"}\n' \
            "$VHOSTS_JSON" "$(timestamp)"
        ;;

    # ------------------------------------------------------------------
    # connections: 接続状況
    # ------------------------------------------------------------------
    connections)
        CONN_OUTPUT=$(ss -tnp 2>/dev/null | grep nginx || netstat -tnp 2>/dev/null | grep nginx || echo "")
        CONN_ESCAPED=$(printf '%s' "$CONN_OUTPUT" | json_escape)
        printf '{"status":"success","connections_raw":%s,"timestamp":"%s"}\n' \
            "$CONN_ESCAPED" "$(timestamp)"
        ;;

    # ------------------------------------------------------------------
    # logs: アクセスログ末尾N行
    # ------------------------------------------------------------------
    logs)
        LINES="${2:-50}"
        # 安全な行数に制限
        SAFE_LINES=$(python3 -c "n=int('$LINES') if '$LINES'.isdigit() else 50; print(max(1, min(200, n)))" 2>/dev/null || echo "50")
        LOG_FILE="/var/log/nginx/access.log"
        if [[ ! -f "$LOG_FILE" ]]; then
            printf '{"status":"success","logs":"","message":"Log file not found: %s","lines":0,"timestamp":"%s"}\n' \
                "$LOG_FILE" "$(timestamp)"
            exit 0
        fi
        LOG_CONTENT=$(tail -n "$SAFE_LINES" "$LOG_FILE" 2>/dev/null || echo "")
        LOG_ESCAPED=$(printf '%s' "$LOG_CONTENT" | json_escape)
        LINE_COUNT=$(printf '%s' "$LOG_CONTENT" | wc -l)
        printf '{"status":"success","logs":%s,"lines":%s,"timestamp":"%s"}\n' \
            "$LOG_ESCAPED" "$LINE_COUNT" "$(timestamp)"
        ;;

    *)
        error_json "Unexpected subcommand: $SUBCOMMAND"
        exit 1
        ;;

esac

exit 0
