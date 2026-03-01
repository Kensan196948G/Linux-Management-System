#!/usr/bin/env bash
# adminui-dhcp.sh - ISC DHCP Server 管理ラッパー
# セキュリティ: shell=False, allowlist による制御
set -euo pipefail

readonly ALLOWED_COMMANDS=("status" "leases" "config" "pools" "logs")
readonly DHCP_SERVICE="isc-dhcp-server"
readonly LEASES_FILE="/var/lib/dhcp/dhcpd.leases"
readonly CONF_FILE="/etc/dhcp/dhcpd.conf"

SUBCOMMAND="${1:-}"

if [[ -z "${SUBCOMMAND}" ]]; then
    echo '{"error":"subcommand required"}' >&2
    exit 1
fi

# allowlist チェック
found=false
for cmd in "${ALLOWED_COMMANDS[@]}"; do
    if [[ "${SUBCOMMAND}" == "${cmd}" ]]; then
        found=true
        break
    fi
done

if [[ "${found}" == "false" ]]; then
    echo "{\"error\":\"subcommand not allowed: ${SUBCOMMAND}\"}" >&2
    exit 1
fi

# isc-dhcp-server の存在確認
DHCPD_BIN=""
if command -v dhcpd >/dev/null 2>&1; then
    DHCPD_BIN="dhcpd"
fi

if [[ -z "${DHCPD_BIN}" ]]; then
    echo '{"status":"unavailable","message":"isc-dhcp-server is not installed"}'
    exit 0
fi

case "${SUBCOMMAND}" in
    status)
        # DHCP サービス状態
        if command -v systemctl >/dev/null 2>&1; then
            if systemctl is-active --quiet "${DHCP_SERVICE}" 2>/dev/null; then
                STATUS="running"
            else
                STATUS="stopped"
            fi
        else
            STATUS="unknown"
        fi

        VERSION=$(dhcpd --version 2>&1 | head -1 || echo "unknown")
        ESCAPED_VER=$(echo "${VERSION}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))")
        echo "{\"status\":\"${STATUS}\",\"version\":${ESCAPED_VER},\"service\":\"${DHCP_SERVICE}\"}"
        ;;
    leases)
        # アクティブリース一覧
        if [[ ! -f "${LEASES_FILE}" ]]; then
            echo '{"leases":[],"message":"leases file not found"}'
            exit 0
        fi
        OUTPUT=$(python3 - "${LEASES_FILE}" <<'PYEOF'
import sys, json, re

leases_file = sys.argv[1]
leases = []
current = {}

with open(leases_file, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        line = line.strip()
        m = re.match(r'^lease\s+([\d.]+)\s+\{', line)
        if m:
            current = {"ip": m.group(1)}
        elif line.startswith("hardware ethernet"):
            current["mac"] = line.split()[2].rstrip(";")
        elif line.startswith("client-hostname"):
            current["hostname"] = line.split('"')[1] if '"' in line else ""
        elif line.startswith("ends"):
            parts = line.split()
            if len(parts) >= 3:
                current["expires"] = parts[2] + " " + (parts[3].rstrip(";") if len(parts) > 3 else "")
        elif line.startswith("binding state"):
            current["state"] = line.split()[2].rstrip(";")
        elif line == "}":
            if current.get("ip") and current.get("state") == "active":
                leases.append(current)
            current = {}

print(json.dumps({"leases": leases, "total": len(leases)}))
PYEOF
)
        echo "${OUTPUT}"
        ;;
    config)
        # DHCP 設定サマリ
        if [[ ! -f "${CONF_FILE}" ]]; then
            echo '{"subnets":[],"message":"dhcpd.conf not found"}'
            exit 0
        fi
        OUTPUT=$(python3 - "${CONF_FILE}" <<'PYEOF'
import sys, json, re

conf_file = sys.argv[1]
subnets = []
current = None

with open(conf_file, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        line = line.strip()
        m = re.match(r'^subnet\s+([\d.]+)\s+netmask\s+([\d.]+)', line)
        if m:
            current = {"subnet": m.group(1), "netmask": m.group(2), "ranges": []}
        elif current is not None:
            r = re.match(r'^range\s+([\d.]+)\s+([\d.]+)', line)
            if r:
                current["ranges"].append({"start": r.group(1), "end": r.group(2)})
            elif line.startswith("option routers"):
                current["router"] = line.split(None, 2)[2].rstrip(";")
            elif line.startswith("option domain-name-servers"):
                current["dns"] = line.split(None, 2)[2].rstrip(";")
            elif line == "}":
                subnets.append(current)
                current = None

print(json.dumps({"subnets": subnets, "total": len(subnets)}))
PYEOF
)
        echo "${OUTPUT}"
        ;;
    pools)
        # アドレスプール情報
        if [[ ! -f "${CONF_FILE}" ]]; then
            echo '{"pools":[],"message":"dhcpd.conf not found"}'
            exit 0
        fi
        OUTPUT=$(python3 - "${CONF_FILE}" <<'PYEOF'
import sys, json, re

conf_file = sys.argv[1]
pools = []
subnet = None
pool = None

with open(conf_file, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        line = line.strip()
        m = re.match(r'^subnet\s+([\d.]+)\s+netmask\s+([\d.]+)', line)
        if m:
            subnet = m.group(1) + "/" + m.group(2)
        elif re.match(r'^pool\s*\{', line):
            pool = {"subnet": subnet or "unknown", "ranges": [], "allow": [], "deny": []}
        elif pool is not None:
            r = re.match(r'^range\s+([\d.]+)\s+([\d.]+)', line)
            if r:
                pool["ranges"].append({"start": r.group(1), "end": r.group(2)})
            elif line.startswith("allow"):
                pool["allow"].append(line.rstrip(";"))
            elif line.startswith("deny"):
                pool["deny"].append(line.rstrip(";"))
            elif line == "}":
                pools.append(pool)
                pool = None

print(json.dumps({"pools": pools, "total": len(pools)}))
PYEOF
)
        echo "${OUTPUT}"
        ;;
    logs)
        # DHCP ログ
        LINES="${2:-50}"
        # LINES を整数に制限
        if ! [[ "${LINES}" =~ ^[0-9]+$ ]]; then
            LINES=50
        fi
        if [[ "${LINES}" -gt 200 ]]; then
            LINES=200
        fi
        if [[ "${LINES}" -lt 1 ]]; then
            LINES=1
        fi

        LOG_OUTPUT=""
        if command -v journalctl >/dev/null 2>&1; then
            LOG_OUTPUT=$(journalctl -u "${DHCP_SERVICE}" --no-pager -n "${LINES}" 2>/dev/null || echo "")
        fi
        if [[ -z "${LOG_OUTPUT}" ]] && [[ -f "/var/log/syslog" ]]; then
            LOG_OUTPUT=$(grep -i "dhcp" "/var/log/syslog" | tail -n "${LINES}" 2>/dev/null || echo "")
        fi

        ESCAPED=$(echo "${LOG_OUTPUT}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
        echo "{\"logs\":${ESCAPED},\"lines\":${LINES}}"
        ;;
esac
