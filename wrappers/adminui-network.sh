#!/bin/bash
# ==============================================================================
# adminui-network.sh - ネットワーク情報取得ラッパー（読み取り専用）
#
# 機能:
#   ネットワークインターフェース・接続状態・ルーティングを取得する。
#   全操作は読み取り専用。システムへの変更は行わない。
#
# 使用方法:
#   adminui-network.sh <subcommand>
#
# サブコマンド:
#   interfaces   - ネットワークインターフェース一覧 (ip addr show)
#   stats        - インターフェース統計 (ip -s link show)
#   connections  - アクティブな接続 (ss -tlnp)
#   routes       - ルーティングテーブル (ip route show)
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - 許可サブコマンドのみ実行（allowlist方式）
#   - ユーザー入力は受け付けない（引数 = サブコマンドのみ）
# ==============================================================================

set -euo pipefail

# ==============================================================================
# 定数
# ==============================================================================

ALLOWED_SUBCOMMANDS=("interfaces" "stats" "connections" "routes")

# ==============================================================================
# ユーティリティ
# ==============================================================================

output_json() {
    local status="$1"
    local data_key="$2"
    local data="$3"
    local message="${4:-}"

    if [[ -n "$message" ]]; then
        printf '{"status":"%s","%s":%s,"message":"%s","timestamp":"%s"}\n' \
            "$status" "$data_key" "$data" "$message" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    else
        printf '{"status":"%s","%s":%s,"timestamp":"%s"}\n' \
            "$status" "$data_key" "$data" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    fi
}

error_json() {
    local message="$1"
    printf '{"status":"error","message":"%s","timestamp":"%s"}\n' \
        "$message" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
}

# ==============================================================================
# サブコマンド検証
# ==============================================================================

if [[ $# -ne 1 ]]; then
    error_json "Usage: adminui-network.sh <subcommand>"
    exit 1
fi

SUBCOMMAND="$1"

# allowlist チェック
ALLOWED=false
for cmd in "${ALLOWED_SUBCOMMANDS[@]}"; do
    if [[ "$SUBCOMMAND" == "$cmd" ]]; then
        ALLOWED=true
        break
    fi
done

if ! $ALLOWED; then
    error_json "Unknown subcommand: ${SUBCOMMAND}. Allowed: ${ALLOWED_SUBCOMMANDS[*]}"
    exit 1
fi

# ==============================================================================
# サブコマンド実行
# ==============================================================================

case "$SUBCOMMAND" in

    # ------------------------------------------------------------------
    # interfaces: インターフェース一覧
    # ------------------------------------------------------------------
    interfaces)
        if ! command -v ip &>/dev/null; then
            error_json "ip command not found"
            exit 1
        fi

        # ip -j addr show で JSON 出力（iproute2 >= 4.12.0）
        if ip -j addr show &>/dev/null 2>&1; then
            interfaces_json=$(ip -j addr show 2>/dev/null || echo "[]")
        else
            # フォールバック: テキスト解析
            interfaces_json="[]"
        fi

        output_json "success" "interfaces" "$interfaces_json"
        ;;

    # ------------------------------------------------------------------
    # stats: インターフェース統計
    # ------------------------------------------------------------------
    stats)
        if ! command -v ip &>/dev/null; then
            error_json "ip command not found"
            exit 1
        fi

        if ip -j -s link show &>/dev/null 2>&1; then
            stats_json=$(ip -j -s link show 2>/dev/null || echo "[]")
        else
            stats_json="[]"
        fi

        output_json "success" "stats" "$stats_json"
        ;;

    # ------------------------------------------------------------------
    # connections: アクティブな接続 (ss -tlnp)
    # ------------------------------------------------------------------
    connections)
        if ! command -v ss &>/dev/null; then
            error_json "ss command not found (install iproute2)"
            exit 1
        fi

        # ss -tlnp: TCP listening, numeric, with process info
        # JSON 形式で出力（ss >= iproute2 5.x で -j フラグ対応）
        if ss -j -tlnp &>/dev/null 2>&1; then
            conn_json=$(ss -j -tlnp 2>/dev/null || echo "[]")
        else
            # フォールバック: テキスト形式を JSON に変換
            conn_json=$(ss -tlnp 2>/dev/null | awk '
                NR==1 { next }  # ヘッダをスキップ
                {
                    state=$1; recv=$2; send=$3; local_addr=$4; peer_addr=$5;
                    process=""
                    if (NF >= 6) { process=$6 }
                    printf "{\"state\":\"%s\",\"recv_q\":%s,\"send_q\":%s,\"local_address\":\"%s\",\"peer_address\":\"%s\",\"process\":\"%s\"},",
                        state, recv, send, local_addr, peer_addr, process
                }
            ' | sed 's/,$//' | { read -r line; echo "[$line]"; })
        fi

        output_json "success" "connections" "${conn_json:-[]}"
        ;;

    # ------------------------------------------------------------------
    # routes: ルーティングテーブル
    # ------------------------------------------------------------------
    routes)
        if ! command -v ip &>/dev/null; then
            error_json "ip command not found"
            exit 1
        fi

        if ip -j route show &>/dev/null 2>&1; then
            routes_json=$(ip -j route show 2>/dev/null || echo "[]")
        else
            routes_json="[]"
        fi

        output_json "success" "routes" "$routes_json"
        ;;

    *)
        error_json "Unexpected subcommand: $SUBCOMMAND"
        exit 1
        ;;

esac

exit 0
