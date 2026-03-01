#!/bin/bash
# adminui-bandwidth.sh - 帯域幅監視ラッパースクリプト
# vnstat / ifstat / ip コマンドを使用した読み取り専用ネットワーク帯域幅監視
#
# 使い方:
#   adminui-bandwidth.sh list                    - インターフェース一覧
#   adminui-bandwidth.sh summary [IFACE]         - 帯域幅サマリ（全体/特定）
#   adminui-bandwidth.sh daily [IFACE]           - 日別帯域幅統計
#   adminui-bandwidth.sh hourly [IFACE]          - 時間別帯域幅統計
#   adminui-bandwidth.sh live [IFACE]            - リアルタイム帯域幅
#   adminui-bandwidth.sh top                     - トップトラフィック

set -euo pipefail

# ===================================================================
# allowlist: 許可インターフェース名パターン
# ===================================================================
is_valid_iface() {
    local iface="$1"
    # 英数字・ハイフン・アンダースコア・ドット のみ許可 (最大32文字)
    if [[ ! "$iface" =~ ^[a-zA-Z0-9._-]{1,32}$ ]]; then
        echo '{"status":"error","message":"Invalid interface name"}' >&2
        exit 1
    fi
    # 実際に存在するインターフェースのみ許可
    if ! ip link show "$iface" &>/dev/null; then
        echo "{\"status\":\"error\",\"message\":\"Interface not found: $iface\"}" >&2
        exit 1
    fi
}

# ===================================================================
# vnstat の有無チェック
# ===================================================================
has_vnstat() { command -v vnstat &>/dev/null; }
has_ifstat() { command -v ifstat &>/dev/null; }
has_nethogs() { command -v nethogs &>/dev/null; }

# インターフェース一覧（ip link show）
cmd_list() {
    if ! command -v ip &>/dev/null; then
        echo '{"status":"unavailable","message":"ip command not found"}'
        exit 0
    fi
    local ifaces=()
    while IFS= read -r line; do
        ifaces+=("\"$line\"")
    done < <(ip -o link show | awk -F': ' '{print $2}' | grep -v '^lo$' || true)
    local iface_json
    iface_json=$(printf '%s,' "${ifaces[@]}" 2>/dev/null | sed 's/,$//')
    echo "{\"status\":\"ok\",\"interfaces\":[${iface_json}],\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
}

# サマリ統計（vnstat）
cmd_summary() {
    local iface="${1:-}"
    if ! has_vnstat; then
        # vnstat がなければ ip -s link で代替
        if [[ -n "$iface" ]]; then
            is_valid_iface "$iface"
            local rx tx
            rx=$(ip -s link show "$iface" | awk '/RX:/{getline; print $1}' || echo 0)
            tx=$(ip -s link show "$iface" | awk '/TX:/{getline; print $1}' || echo 0)
            echo "{\"status\":\"ok\",\"source\":\"ip\",\"interface\":\"$iface\",\"rx_bytes\":$rx,\"tx_bytes\":$tx,\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
        else
            echo '{"status":"unavailable","message":"vnstat not installed. Install with: sudo apt-get install vnstat","timestamp":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}'
        fi
        return
    fi
    local out
    if [[ -n "$iface" ]]; then
        is_valid_iface "$iface"
        out=$(vnstat --json d -i "$iface" 2>/dev/null || echo '{}')
    else
        out=$(vnstat --json 2>/dev/null || echo '{}')
    fi
    echo "{\"status\":\"ok\",\"source\":\"vnstat\",\"data\":$out,\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
}

# 日別統計
cmd_daily() {
    local iface="${1:-}"
    if ! has_vnstat; then
        echo '{"status":"unavailable","message":"vnstat not installed","timestamp":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}'
        return
    fi
    local out
    if [[ -n "$iface" ]]; then
        is_valid_iface "$iface"
        out=$(vnstat --json d -i "$iface" 2>/dev/null || echo '{}')
    else
        out=$(vnstat --json d 2>/dev/null || echo '{}')
    fi
    echo "{\"status\":\"ok\",\"period\":\"daily\",\"source\":\"vnstat\",\"data\":$out,\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
}

# 時間別統計
cmd_hourly() {
    local iface="${1:-}"
    if ! has_vnstat; then
        echo '{"status":"unavailable","message":"vnstat not installed","timestamp":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}'
        return
    fi
    local out
    if [[ -n "$iface" ]]; then
        is_valid_iface "$iface"
        out=$(vnstat --json h -i "$iface" 2>/dev/null || echo '{}')
    else
        out=$(vnstat --json h 2>/dev/null || echo '{}')
    fi
    echo "{\"status\":\"ok\",\"period\":\"hourly\",\"source\":\"vnstat\",\"data\":$out,\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
}

# リアルタイム計測（1秒間 ip -s link サンプリング）
cmd_live() {
    local iface="${1:-}"
    if [[ -z "$iface" ]]; then
        iface=$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<NF;i++) if($i=="dev") print $(i+1)}' || echo "")
        if [[ -z "$iface" ]]; then
            echo '{"status":"error","message":"Cannot detect default interface"}'
            exit 1
        fi
    fi
    is_valid_iface "$iface"
    local rx1 tx1 rx2 tx2
    rx1=$(cat "/sys/class/net/${iface}/statistics/rx_bytes" 2>/dev/null || echo 0)
    tx1=$(cat "/sys/class/net/${iface}/statistics/tx_bytes" 2>/dev/null || echo 0)
    sleep 1
    rx2=$(cat "/sys/class/net/${iface}/statistics/rx_bytes" 2>/dev/null || echo 0)
    tx2=$(cat "/sys/class/net/${iface}/statistics/tx_bytes" 2>/dev/null || echo 0)
    local rx_bps=$(( rx2 - rx1 ))
    local tx_bps=$(( tx2 - tx1 ))
    echo "{\"status\":\"ok\",\"interface\":\"$iface\",\"rx_bps\":$rx_bps,\"tx_bps\":$tx_bps,\"rx_kbps\":$(( rx_bps / 1024 )),\"tx_kbps\":$(( tx_bps / 1024 )),\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
}

# トップネットワーク統計（ss -s / ip -s link で代替）
cmd_top() {
    local ifaces=()
    local result="["
    local first=true
    while IFS= read -r iface; do
        [[ "$iface" == "lo" ]] && continue
        local rx tx
        rx=$(cat "/sys/class/net/${iface}/statistics/rx_bytes" 2>/dev/null || echo 0)
        tx=$(cat "/sys/class/net/${iface}/statistics/tx_bytes" 2>/dev/null || echo 0)
        if [[ "$first" == "true" ]]; then first=false; else result+=","; fi
        result+="{\"interface\":\"$iface\",\"rx_bytes\":$rx,\"tx_bytes\":$tx}"
    done < <(ls /sys/class/net/ 2>/dev/null || true)
    result+="]"
    echo "{\"status\":\"ok\",\"interfaces\":$result,\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
}

# 帯域使用履歴（vnstat 全期間サマリ）
cmd_history() {
    local iface="${1:-eth0}"
    is_valid_iface "$iface"
    if ! has_vnstat; then
        cat /proc/net/dev 2>/dev/null || true
        return
    fi
    local out
    out=$(vnstat -i "$iface" --json 2>/dev/null || vnstat -i "$iface" 2>/dev/null || echo '{}')
    echo "{\"status\":\"ok\",\"period\":\"history\",\"source\":\"vnstat\",\"data\":$out,\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
}

# 月次統計
cmd_monthly() {
    local iface="${1:-eth0}"
    is_valid_iface "$iface"
    if ! has_vnstat; then
        cat /proc/net/dev 2>/dev/null || true
        return
    fi
    local out
    out=$(vnstat -i "$iface" -m --json 2>/dev/null || vnstat -i "$iface" -m 2>/dev/null || echo '{}')
    echo "{\"status\":\"ok\",\"period\":\"monthly\",\"source\":\"vnstat\",\"data\":$out,\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
}

# アラート設定（設定ファイルから読む、なければデフォルト値）
cmd_alert_config() {
    local config_file="/etc/adminui/bandwidth-alert.json"
    if [[ -f "$config_file" ]]; then
        cat "$config_file"
    else
        echo '{"threshold_gb": 100, "alert_email": "", "enabled": false}'
    fi
}

# ===================================================================
# サブコマンドディスパッチ
# ===================================================================
SUBCMD="${1:-list}"
shift || true

case "$SUBCMD" in
    list)      cmd_list "$@" ;;
    summary)   cmd_summary "${1:-}" ;;
    daily)     cmd_daily "${1:-}" ;;
    hourly)    cmd_hourly "${1:-}" ;;
    live)      cmd_live "${1:-}" ;;
    top)       cmd_top "$@" ;;
    history)   cmd_history "${1:-eth0}" ;;
    monthly)   cmd_monthly "${1:-eth0}" ;;
    alert-config) cmd_alert_config ;;
    *)
        echo "{\"status\":\"error\",\"message\":\"Unknown subcommand: $SUBCMD\"}" >&2
        exit 1
        ;;
esac
