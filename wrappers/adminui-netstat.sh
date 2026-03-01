#!/usr/bin/env bash
# adminui-netstat.sh - ネットワーク統計ラッパー
# セキュリティ: shell=False, allowlist による制御
set -euo pipefail

readonly ALLOWED_COMMANDS=("connections" "listening" "stats" "routes")

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

# ss コマンド優先チェック
HAS_SS=false
if command -v ss >/dev/null 2>&1; then
    HAS_SS=true
fi

case "${SUBCOMMAND}" in
    connections)
        # アクティブ接続一覧
        if [[ "${HAS_SS}" == "true" ]]; then
            OUTPUT=$(ss -tnp 2>/dev/null || echo "")
        elif command -v netstat >/dev/null 2>&1; then
            OUTPUT=$(netstat -tnp 2>/dev/null || echo "")
        else
            echo '{"error":"neither ss nor netstat is available"}'
            exit 0
        fi
        ESCAPED=$(printf '%s' "${OUTPUT}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
        echo "{\"connections\":${ESCAPED},\"tool\":\"$([ "${HAS_SS}" == "true" ] && echo "ss" || echo "netstat")\"}"
        ;;
    listening)
        # リスニングポート一覧
        if [[ "${HAS_SS}" == "true" ]]; then
            OUTPUT=$(ss -tlnp 2>/dev/null || echo "")
        elif command -v netstat >/dev/null 2>&1; then
            OUTPUT=$(netstat -tlnp 2>/dev/null || echo "")
        else
            echo '{"error":"neither ss nor netstat is available"}'
            exit 0
        fi
        ESCAPED=$(printf '%s' "${OUTPUT}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
        echo "{\"listening\":${ESCAPED},\"tool\":\"$([ "${HAS_SS}" == "true" ] && echo "ss" || echo "netstat")\"}"
        ;;
    stats)
        # ネットワーク統計サマリ
        if [[ "${HAS_SS}" == "true" ]]; then
            OUTPUT=$(ss -s 2>/dev/null || echo "")
        elif command -v netstat >/dev/null 2>&1; then
            OUTPUT=$(netstat -s 2>/dev/null | head -50 || echo "")
        else
            echo '{"error":"neither ss nor netstat is available"}'
            exit 0
        fi
        ESCAPED=$(printf '%s' "${OUTPUT}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
        echo "{\"stats\":${ESCAPED},\"tool\":\"$([ "${HAS_SS}" == "true" ] && echo "ss" || echo "netstat")\"}"
        ;;
    routes)
        # ルーティングテーブル
        if command -v ip >/dev/null 2>&1; then
            OUTPUT=$(ip route 2>/dev/null || echo "")
            ESCAPED=$(printf '%s' "${OUTPUT}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
            echo "{\"routes\":${ESCAPED},\"tool\":\"ip\"}"
        elif command -v route >/dev/null 2>&1; then
            OUTPUT=$(route -n 2>/dev/null || echo "")
            ESCAPED=$(printf '%s' "${OUTPUT}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
            echo "{\"routes\":${ESCAPED},\"tool\":\"route\"}"
        else
            echo '{"error":"ip command not available"}'
            exit 0
        fi
        ;;
esac
