#!/usr/bin/env bash
# ==============================================================================
# adminui-routing.sh - ルーティング・ゲートウェイ情報取得ラッパー（読み取り専用）
#
# 使用方法:
#   adminui-routing.sh routes      - ルーティングテーブル (ip route show)
#   adminui-routing.sh gateways    - デフォルトゲートウェイ情報
#   adminui-routing.sh arp         - ARP テーブル (ip neigh show)
#   adminui-routing.sh interfaces  - インターフェース詳細 (ip addr show)
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - iproute2 は標準インストール済み想定
#   - JSON 形式出力
# ==============================================================================

set -euo pipefail

# ==============================================================================
# 定数
# ==============================================================================

ALLOWED_SUBCOMMANDS=("routes" "gateways" "arp" "interfaces")

# ==============================================================================
# ユーティリティ
# ==============================================================================

error_json() {
    local message="$1"
    printf '{"status":"error","message":"%s","timestamp":"%s"}\n' \
        "$message" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
}

timestamp() {
    date -u '+%Y-%m-%dT%H:%M:%SZ'
}

# ip コマンドの存在確認
check_ip_command() {
    if ! command -v ip &>/dev/null; then
        error_json "ip command not found (install iproute2)"
        exit 1
    fi
}

# ==============================================================================
# 引数チェック
# ==============================================================================

if [[ $# -lt 1 ]]; then
    error_json "Usage: adminui-routing.sh <subcommand>"
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

# ==============================================================================
# サブコマンド実行
# ==============================================================================

case "$SUBCOMMAND" in

    # ------------------------------------------------------------------
    # routes: ルーティングテーブル (ip route show)
    # ------------------------------------------------------------------
    routes)
        check_ip_command

        routes_text=$(ip route show 2>/dev/null || echo "")
        routes_json=$(printf '%s\n' "$routes_text" | python3 -c "
import sys, json, re

routes = []
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    parts = line.split()
    route = {'destination': parts[0] if parts else ''}
    i = 1
    while i < len(parts):
        key = parts[i]
        if key in ('via', 'dev', 'proto', 'scope', 'metric', 'src'):
            if i + 1 < len(parts):
                route[key] = parts[i + 1]
                i += 2
            else:
                i += 1
        else:
            i += 1
    routes.append(route)
print(json.dumps(routes))
" 2>/dev/null || echo "[]")

        printf '{"status":"success","routes":%s,"timestamp":"%s"}\n' \
            "$routes_json" "$(timestamp)"
        ;;

    # ------------------------------------------------------------------
    # gateways: デフォルトゲートウェイ情報
    # ------------------------------------------------------------------
    gateways)
        check_ip_command

        gw_text=$(ip route show default 2>/dev/null || echo "")
        gw_json=$(printf '%s\n' "$gw_text" | python3 -c "
import sys, json

gateways = []
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    parts = line.split()
    gw = {'destination': parts[0] if parts else 'default'}
    i = 1
    while i < len(parts):
        key = parts[i]
        if key in ('via', 'dev', 'proto', 'metric', 'onlink'):
            if i + 1 < len(parts) and key != 'onlink':
                gw[key] = parts[i + 1]
                i += 2
            else:
                gw[key] = True
                i += 1
        else:
            i += 1
    gateways.append(gw)
print(json.dumps(gateways))
" 2>/dev/null || echo "[]")

        printf '{"status":"success","gateways":%s,"timestamp":"%s"}\n' \
            "$gw_json" "$(timestamp)"
        ;;

    # ------------------------------------------------------------------
    # arp: ARP テーブル (ip neigh show)
    # ------------------------------------------------------------------
    arp)
        check_ip_command

        arp_text=$(ip neigh show 2>/dev/null || echo "")
        arp_json=$(printf '%s\n' "$arp_text" | python3 -c "
import sys, json

entries = []
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    parts = line.split()
    entry = {'ip': parts[0] if parts else ''}
    i = 1
    while i < len(parts):
        key = parts[i]
        if key == 'dev' and i + 1 < len(parts):
            entry['dev'] = parts[i + 1]
            i += 2
        elif key == 'lladdr' and i + 1 < len(parts):
            entry['mac'] = parts[i + 1]
            i += 2
        elif key in ('REACHABLE','STALE','DELAY','PROBE','FAILED','NOARP','PERMANENT','INCOMPLETE'):
            entry['state'] = key
            i += 1
        else:
            i += 1
    entries.append(entry)
print(json.dumps(entries))
" 2>/dev/null || echo "[]")

        printf '{"status":"success","arp":%s,"timestamp":"%s"}\n' \
            "$arp_json" "$(timestamp)"
        ;;

    # ------------------------------------------------------------------
    # interfaces: インターフェース詳細 (ip addr show)
    # ------------------------------------------------------------------
    interfaces)
        check_ip_command

        # ip -j addr show はiproute2 >= 4.12.0 でサポート
        if ip -j addr show &>/dev/null 2>&1; then
            ifaces_json=$(ip -j addr show 2>/dev/null || echo "[]")
            printf '{"status":"success","interfaces":%s,"timestamp":"%s"}\n' \
                "$ifaces_json" "$(timestamp)"
        else
            # フォールバック: テキストパース
            ifaces_text=$(ip addr show 2>/dev/null || echo "")
            ifaces_json=$(printf '%s\n' "$ifaces_text" | python3 -c "
import sys, json, re

interfaces = []
current = None
for line in sys.stdin:
    line = line.rstrip()
    # 新しいインターフェース行: '1: lo: <LOOPBACK,UP,LOWER_UP>'
    m = re.match(r'^(\d+): (\S+): <([^>]*)>', line)
    if m:
        if current is not None:
            interfaces.append(current)
        current = {
            'ifindex': int(m.group(1)),
            'ifname': m.group(2).rstrip('@:'),
            'flags': m.group(3).split(','),
            'addr_info': []
        }
    elif current is not None:
        # inet/inet6 行
        m4 = re.match(r'\s+inet (\S+) .* scope (\S+)', line)
        if m4:
            current['addr_info'].append({'family': 'inet', 'local': m4.group(1).split('/')[0], 'prefixlen': m4.group(1).split('/')[1] if '/' in m4.group(1) else '32', 'scope': m4.group(2)})
        m6 = re.match(r'\s+inet6 (\S+) scope (\S+)', line)
        if m6:
            current['addr_info'].append({'family': 'inet6', 'local': m6.group(1).split('/')[0], 'prefixlen': m6.group(1).split('/')[1] if '/' in m6.group(1) else '128', 'scope': m6.group(2)})
if current is not None:
    interfaces.append(current)
print(json.dumps(interfaces))
" 2>/dev/null || echo "[]")
            printf '{"status":"success","interfaces":%s,"timestamp":"%s"}\n' \
                "$ifaces_json" "$(timestamp)"
        fi
        ;;

    *)
        error_json "Unexpected subcommand: $SUBCOMMAND"
        exit 1
        ;;

esac

exit 0
