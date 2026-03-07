#!/bin/bash
# ==============================================================================
# adminui-network-config.sh - ネットワーク設定変更ラッパー（承認フロー経由）
#
# 機能:
#   ネットワークインターフェースのIP・DNS・ゲートウェイ設定変更。
#   全変更操作は承認フロー経由で実行される。
#
# 使用方法:
#   adminui-network-config.sh set-ip <interface> <ip/cidr> <gateway>
#   adminui-network-config.sh set-dns <dns1> [dns2]
#   adminui-network-config.sh get-interfaces
#   adminui-network-config.sh get-interface <interface>
#   adminui-network-config.sh get-routes
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - Allowlist方式: 許可アクション・インターフェース名のみ実行
#   - IPアドレス形式バリデーション
#   - 危険文字を含む入力を拒否
# ==============================================================================

set -euo pipefail

# ==============================================================================
# 定数
# ==============================================================================

ALLOWED_ACTIONS=("set-ip" "set-dns" "get-interfaces" "get-interface" "get-routes")

# インターフェース名の許可パターン: eth0, ens3, enp2s0, lo, wlan0 等
INTERFACE_PATTERN='^[a-z][a-z0-9]{0,15}$'

# 禁止文字
FORBIDDEN_CHARS=(';' '|' '&' '$' '(' ')' '`' '>' '<' '*' '?' '{' '}' '[' ']' '\' '"' "'" ' ' '\n' '\t')

# ==============================================================================
# ユーティリティ
# ==============================================================================

error_json() {
    local message="$1"
    printf '{"status":"error","message":"%s","timestamp":"%s"}\n' \
        "$message" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
}

success_json() {
    local data="$1"
    printf '{"status":"success",%s,"timestamp":"%s"}\n' \
        "$data" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
}

# 危険文字チェック
validate_no_forbidden_chars() {
    local input="$1"
    local label="$2"
    # 禁止文字の正規表現チェック
    if echo "$input" | grep -qP '[;|&$(){}`><*?{}\[\]\\"\x27\s]'; then
        error_json "Forbidden characters in ${label}: ${input}"
        exit 1
    fi
}

# インターフェース名バリデーション
validate_interface_name() {
    local iface="$1"
    validate_no_forbidden_chars "$iface" "interface_name"
    if ! echo "$iface" | grep -qP "$INTERFACE_PATTERN"; then
        error_json "Invalid interface name: ${iface}. Must match ${INTERFACE_PATTERN}"
        exit 1
    fi
}

# IPv4アドレスバリデーション
validate_ipv4() {
    local ip="$1"
    validate_no_forbidden_chars "$ip" "ip_address"
    # 基本的なIPv4形式チェック（CIDR含む）
    if ! echo "$ip" | grep -qP '^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(/\d{1,2})?$'; then
        error_json "Invalid IPv4 address format: ${ip}"
        exit 1
    fi
    # octet範囲チェック（Python使用）
    if ! python3 -c "import ipaddress; ipaddress.ip_interface('$ip')" 2>/dev/null; then
        error_json "Invalid IP address or CIDR: ${ip}"
        exit 1
    fi
}

# ゲートウェイアドレスバリデーション（CIDR不要）
validate_gateway() {
    local gw="$1"
    validate_no_forbidden_chars "$gw" "gateway"
    if ! echo "$gw" | grep -qP '^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'; then
        error_json "Invalid gateway address: ${gw}"
        exit 1
    fi
    if ! python3 -c "import ipaddress; ipaddress.ip_address('$gw')" 2>/dev/null; then
        error_json "Invalid gateway address: ${gw}"
        exit 1
    fi
}

# ==============================================================================
# 引数検証
# ==============================================================================

if [[ $# -lt 1 ]]; then
    error_json "Usage: adminui-network-config.sh <action> [args...]"
    exit 1
fi

ACTION="$1"

# allowlist チェック
ALLOWED=false
for a in "${ALLOWED_ACTIONS[@]}"; do
    if [[ "$ACTION" == "$a" ]]; then
        ALLOWED=true
        break
    fi
done

if ! $ALLOWED; then
    error_json "Unknown action: ${ACTION}. Allowed: ${ALLOWED_ACTIONS[*]}"
    exit 1
fi

# ==============================================================================
# アクション実行
# ==============================================================================

case "$ACTION" in

    # ------------------------------------------------------------------
    # get-interfaces: インターフェース一覧取得
    # ------------------------------------------------------------------
    get-interfaces)
        if ! command -v ip &>/dev/null; then
            error_json "ip command not found"
            exit 1
        fi

        if ip -j addr show &>/dev/null 2>&1; then
            interfaces_json=$(ip -j addr show 2>/dev/null || echo "[]")
        else
            interfaces_json="[]"
        fi

        printf '{"status":"success","interfaces":%s,"timestamp":"%s"}\n' \
            "$interfaces_json" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        ;;

    # ------------------------------------------------------------------
    # get-interface: 特定インターフェース詳細取得
    # ------------------------------------------------------------------
    get-interface)
        if [[ $# -lt 2 ]]; then
            error_json "Usage: get-interface <interface_name>"
            exit 1
        fi
        IFACE="$2"
        validate_interface_name "$IFACE"

        if ! command -v ip &>/dev/null; then
            error_json "ip command not found"
            exit 1
        fi

        if ip link show "$IFACE" &>/dev/null 2>&1; then
            iface_json=$(ip -j addr show dev "$IFACE" 2>/dev/null || echo "[]")
            printf '{"status":"success","interface":%s,"timestamp":"%s"}\n' \
                "$iface_json" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        else
            error_json "Interface not found: ${IFACE}"
            exit 1
        fi
        ;;

    # ------------------------------------------------------------------
    # get-routes: ルーティングテーブル取得
    # ------------------------------------------------------------------
    get-routes)
        if ! command -v ip &>/dev/null; then
            error_json "ip command not found"
            exit 1
        fi

        if ip -j route show &>/dev/null 2>&1; then
            routes_json=$(ip -j route show 2>/dev/null || echo "[]")
        else
            routes_json="[]"
        fi

        printf '{"status":"success","routes":%s,"timestamp":"%s"}\n' \
            "$routes_json" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        ;;

    # ------------------------------------------------------------------
    # set-ip: IPアドレス・ゲートウェイ設定変更
    # 使用法: set-ip <interface> <ip/cidr> <gateway>
    # ------------------------------------------------------------------
    set-ip)
        if [[ $# -lt 4 ]]; then
            error_json "Usage: set-ip <interface> <ip/cidr> <gateway>"
            exit 1
        fi
        IFACE="$2"
        IP_CIDR="$3"
        GATEWAY="$4"

        validate_interface_name "$IFACE"
        validate_ipv4 "$IP_CIDR"
        validate_gateway "$GATEWAY"

        if ! command -v ip &>/dev/null; then
            error_json "ip command not found"
            exit 1
        fi

        # インターフェース存在確認
        if ! ip link show "$IFACE" &>/dev/null 2>&1; then
            error_json "Interface not found: ${IFACE}"
            exit 1
        fi

        # 既存IPアドレスを削除して新しいIPを設定
        # 注意: 配列形式で実行（shell=False相当）
        ip addr flush dev "$IFACE" 2>/dev/null || true
        ip addr add "$IP_CIDR" dev "$IFACE"
        ip link set "$IFACE" up

        # デフォルトルート更新
        ip route del default 2>/dev/null || true
        ip route add default via "$GATEWAY" dev "$IFACE"

        printf '{"status":"success","message":"IP configuration updated","interface":"%s","ip_cidr":"%s","gateway":"%s","timestamp":"%s"}\n' \
            "$IFACE" "$IP_CIDR" "$GATEWAY" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        ;;

    # ------------------------------------------------------------------
    # set-dns: DNS設定変更
    # 使用法: set-dns <dns1> [dns2]
    # ------------------------------------------------------------------
    set-dns)
        if [[ $# -lt 2 ]]; then
            error_json "Usage: set-dns <dns1> [dns2]"
            exit 1
        fi
        DNS1="$2"
        DNS2="${3:-}"

        validate_ipv4 "$DNS1"
        if [[ -n "$DNS2" ]]; then
            validate_ipv4 "$DNS2"
        fi

        # /etc/resolv.conf の既存nameserverを置き換え
        # バックアップ作成
        cp /etc/resolv.conf /etc/resolv.conf.bak."$(date -u '+%Y%m%dT%H%M%SZ')" 2>/dev/null || true

        # nameserver行を更新（既存のsearch/domainは保持）
        TMPFILE=$(mktemp)
        grep -v '^nameserver' /etc/resolv.conf > "$TMPFILE" 2>/dev/null || true
        echo "nameserver $DNS1" >> "$TMPFILE"
        if [[ -n "$DNS2" ]]; then
            echo "nameserver $DNS2" >> "$TMPFILE"
        fi
        mv "$TMPFILE" /etc/resolv.conf

        MSG="DNS updated: ${DNS1}"
        if [[ -n "$DNS2" ]]; then
            MSG="${MSG}, ${DNS2}"
        fi

        printf '{"status":"success","message":"%s","dns1":"%s","dns2":"%s","timestamp":"%s"}\n' \
            "$MSG" "$DNS1" "${DNS2}" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        ;;

    *)
        error_json "Unexpected action: $ACTION"
        exit 1
        ;;

esac

exit 0
