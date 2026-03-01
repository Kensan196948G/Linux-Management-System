#!/usr/bin/env bash
# adminui-bind.sh - BIND DNS サーバー管理ラッパー
# セキュリティ: shell=False, allowlist による制御
set -euo pipefail

readonly ALLOWED_COMMANDS=("status" "zones" "config" "logs")

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

# BIND の存在確認
BIND_AVAILABLE=false
if command -v named >/dev/null 2>&1 || command -v named-checkconf >/dev/null 2>&1; then
    BIND_AVAILABLE=true
fi

if [[ "${BIND_AVAILABLE}" == "false" ]]; then
    echo '{"status":"unavailable","message":"BIND (named) is not installed"}'
    exit 0
fi

# BIND サービス名検出（named または bind9）
BIND_SERVICE=""
if command -v systemctl >/dev/null 2>&1; then
    if systemctl list-units --type=service --all 2>/dev/null | grep -q "named.service"; then
        BIND_SERVICE="named"
    elif systemctl list-units --type=service --all 2>/dev/null | grep -q "bind9.service"; then
        BIND_SERVICE="bind9"
    fi
fi

case "${SUBCOMMAND}" in
    status)
        # BIND サービス状態
        if [[ -n "${BIND_SERVICE}" ]] && command -v systemctl >/dev/null 2>&1; then
            if systemctl is-active --quiet "${BIND_SERVICE}" 2>/dev/null; then
                STATUS="running"
            else
                STATUS="stopped"
            fi
        else
            STATUS="unknown"
        fi

        VERSION=$(named -v 2>/dev/null | head -1 || echo "unknown")
        ESCAPED_VERSION=$(printf '%s' "${VERSION}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
        ESCAPED_SERVICE=$(printf '%s' "${BIND_SERVICE:-unknown}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
        echo "{\"status\":\"${STATUS}\",\"version\":${ESCAPED_VERSION},\"service\":${ESCAPED_SERVICE}}"
        ;;
    zones)
        # ゾーン一覧（rndc dumpdb または設定ファイル解析）
        ZONES_OUTPUT=""
        if command -v rndc >/dev/null 2>&1; then
            ZONES_OUTPUT=$(rndc zonestatus 2>/dev/null || rndc status 2>/dev/null || echo "")
        fi
        if [[ -z "${ZONES_OUTPUT}" ]]; then
            # 設定ファイルからゾーンを抽出
            NAMED_CONF=""
            for f in /etc/named.conf /etc/bind/named.conf /etc/named/named.conf; do
                if [[ -r "${f}" ]]; then
                    NAMED_CONF="${f}"
                    break
                fi
            done
            if [[ -n "${NAMED_CONF}" ]]; then
                ZONES_OUTPUT=$(grep -E '^\s*zone\s+"' "${NAMED_CONF}" 2>/dev/null | sed 's/.*zone\s*"\([^"]*\)".*/\1/' || echo "")
            fi
        fi
        ESCAPED=$(printf '%s' "${ZONES_OUTPUT}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
        echo "{\"zones\":${ESCAPED}}"
        ;;
    config)
        # 設定確認 (named-checkconf)
        if command -v named-checkconf >/dev/null 2>&1; then
            if OUTPUT=$(named-checkconf 2>&1); then
                ESCAPED=$(printf '%s' "${OUTPUT}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
                echo "{\"valid\":true,\"output\":${ESCAPED}}"
            else
                ESCAPED=$(printf '%s' "${OUTPUT}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
                echo "{\"valid\":false,\"output\":${ESCAPED}}"
            fi
        else
            echo '{"valid":null,"output":"named-checkconf not available"}'
        fi
        ;;
    logs)
        # DNS ログ
        LINES="${2:-50}"
        # LINES を整数に制限
        if ! [[ "${LINES}" =~ ^[0-9]+$ ]]; then
            LINES=50
        fi
        if [[ "${LINES}" -gt 200 ]]; then
            LINES=200
        fi
        if [[ "${LINES}" -lt 1 ]]; then
            LINES=50
        fi

        LOG_OUTPUT=""
        # ログファイル探索
        for logfile in /var/log/named/named.log /var/log/named.log /var/log/syslog /var/log/messages; do
            if [[ -r "${logfile}" ]]; then
                LOG_OUTPUT=$(tail -n "${LINES}" "${logfile}" 2>/dev/null || echo "")
                break
            fi
        done

        # journalctl フォールバック
        if [[ -z "${LOG_OUTPUT}" ]] && command -v journalctl >/dev/null 2>&1; then
            if [[ -n "${BIND_SERVICE}" ]]; then
                LOG_OUTPUT=$(journalctl -u "${BIND_SERVICE}" --no-pager -n "${LINES}" 2>/dev/null || echo "")
            fi
        fi

        ESCAPED=$(printf '%s' "${LOG_OUTPUT}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
        echo "{\"logs\":${ESCAPED},\"lines\":${LINES}}"
        ;;
esac
