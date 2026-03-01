#!/usr/bin/env bash
# ==============================================================================
# adminui-postgresql.sh - PostgreSQL 管理ラッパー（読み取り専用）
#
# 機能:
#   PostgreSQL の状態・データベース一覧・ユーザー・接続状況・設定・ログを取得する。
#   全操作は読み取り専用。設定の変更は行わない。
#
# 使用方法:
#   adminui-postgresql.sh <subcommand> [lines]
#
# サブコマンド:
#   status    - PostgreSQL サービス状態・バージョン
#   databases - データベース一覧（pg_database）
#   users     - ロール/ユーザー一覧（pg_roles）
#   activity  - 現在の接続・クエリ（pg_stat_activity）
#   config    - 設定パラメータ（pg_settings 主要項目）
#   logs      - PostgreSQL ログ
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - 許可サブコマンドのみ実行（allowlist方式）
#   - 読み取り専用（設定変更・再起動等は行わない）
# ==============================================================================

set -euo pipefail

readonly ALLOWED_SUBCOMMANDS=("status" "databases" "users" "activity" "config" "logs")

error_json() {
    echo "{\"status\": \"error\", \"message\": \"$1\"}" >&2
    exit 1
}

if [ "$#" -lt 1 ]; then
    error_json "Usage: adminui-postgresql.sh <subcommand> [lines]"
fi

SUBCOMMAND="$1"

# allowlist 検証
ALLOWED=false
for cmd in "${ALLOWED_SUBCOMMANDS[@]}"; do
    if [ "$cmd" = "$SUBCOMMAND" ]; then
        ALLOWED=true
        break
    fi
done

if ! $ALLOWED; then
    error_json "Unknown subcommand: $SUBCOMMAND. Allowed: ${ALLOWED_SUBCOMMANDS[*]}"
fi

TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

# PostgreSQL の存在確認
if ! command -v pg_isready >/dev/null 2>&1 && ! command -v psql >/dev/null 2>&1; then
    echo "{\"status\": \"unavailable\", \"message\": \"PostgreSQL is not installed\", \"timestamp\": \"${TIMESTAMP}\"}"
    exit 0
fi

# psql でクエリを実行するヘルパー（-U postgres, -t: tuples-only, -A: unaligned）
run_psql() {
    psql -U postgres -t -A -c "$1" 2>/dev/null || echo ""
}

# JSON エスケープヘルパー
escape_json() {
    python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo '""'
}

case "$SUBCOMMAND" in
    status)
        # PostgreSQL サービス状態を取得
        SERVICE_NAME=""
        if systemctl list-units --type=service 2>/dev/null | grep -q "postgresql"; then
            SERVICE_NAME=$(systemctl list-units --type=service 2>/dev/null | grep "postgresql" | awk '{print $1}' | head -1)
        fi

        if [ -z "$SERVICE_NAME" ]; then
            # systemctl で見つからない場合でも pg_isready で確認
            if command -v pg_isready >/dev/null 2>&1; then
                READY_OUTPUT=$(pg_isready 2>/dev/null || echo "not accepting connections")
                READY_ESCAPED=$(echo "$READY_OUTPUT" | escape_json)
                echo "{\"status\": \"unavailable\", \"message\": \"PostgreSQL service not found in systemctl\", \"pg_ready\": ${READY_ESCAPED}, \"timestamp\": \"${TIMESTAMP}\"}"
            else
                echo "{\"status\": \"unavailable\", \"message\": \"PostgreSQL service not found\", \"timestamp\": \"${TIMESTAMP}\"}"
            fi
            exit 0
        fi

        ACTIVE_STATE=$(systemctl is-active "${SERVICE_NAME}" 2>/dev/null || echo "unknown")
        ENABLED_STATE=$(systemctl is-enabled "${SERVICE_NAME}" 2>/dev/null || echo "unknown")

        # バージョン取得
        VERSION="unknown"
        if command -v psql >/dev/null 2>&1; then
            VERSION=$(psql -U postgres -t -A -c "SELECT version();" 2>/dev/null | head -1 || echo "unknown")
        elif command -v pg_isready >/dev/null 2>&1; then
            VERSION=$(pg_isready --version 2>/dev/null || echo "unknown")
        fi
        VERSION_ESCAPED=$(echo "$VERSION" | escape_json)

        # pg_isready チェック
        READY="unknown"
        if command -v pg_isready >/dev/null 2>&1; then
            if pg_isready >/dev/null 2>&1; then
                READY="accepting connections"
            else
                READY="not accepting connections"
            fi
        fi

        echo "{\"status\": \"success\", \"service\": \"${SERVICE_NAME}\", \"active\": \"${ACTIVE_STATE}\", \"enabled\": \"${ENABLED_STATE}\", \"version\": ${VERSION_ESCAPED}, \"ready\": \"${READY}\", \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    databases)
        # データベース一覧（pg_database）
        OUTPUT=$(run_psql "SELECT datname, pg_size_pretty(pg_database_size(datname)), datcollate, datctype FROM pg_database ORDER BY datname;")
        if [ -z "$OUTPUT" ]; then
            echo "{\"status\": \"unavailable\", \"message\": \"Cannot connect to PostgreSQL\", \"databases_raw\": \"\", \"timestamp\": \"${TIMESTAMP}\"}"
            exit 0
        fi
        ESCAPED=$(echo "$OUTPUT" | escape_json)
        echo "{\"status\": \"success\", \"databases_raw\": ${ESCAPED}, \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    users)
        # ロール/ユーザー一覧（pg_roles）
        OUTPUT=$(run_psql "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolcanlogin, rolconnlimit FROM pg_roles ORDER BY rolname;")
        if [ -z "$OUTPUT" ]; then
            echo "{\"status\": \"unavailable\", \"message\": \"Cannot connect to PostgreSQL\", \"users_raw\": \"\", \"timestamp\": \"${TIMESTAMP}\"}"
            exit 0
        fi
        ESCAPED=$(echo "$OUTPUT" | escape_json)
        echo "{\"status\": \"success\", \"users_raw\": ${ESCAPED}, \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    activity)
        # 現在の接続・クエリ（pg_stat_activity）
        OUTPUT=$(run_psql "SELECT pid, usename, application_name, client_addr, state, LEFT(query, 100) AS query FROM pg_stat_activity WHERE state IS NOT NULL ORDER BY pid;")
        if [ -z "$OUTPUT" ]; then
            echo "{\"status\": \"unavailable\", \"message\": \"Cannot connect to PostgreSQL\", \"activity_raw\": \"\", \"timestamp\": \"${TIMESTAMP}\"}"
            exit 0
        fi
        ESCAPED=$(echo "$OUTPUT" | escape_json)

        # 接続数カウント
        CONN_COUNT=$(run_psql "SELECT count(*) FROM pg_stat_activity WHERE state IS NOT NULL;" | tr -d ' ' || echo "0")

        echo "{\"status\": \"success\", \"activity_raw\": ${ESCAPED}, \"connection_count\": ${CONN_COUNT:-0}, \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    config)
        # 設定パラメータ（pg_settings 主要項目）
        OUTPUT=$(run_psql "SELECT name, setting, unit, short_desc FROM pg_settings WHERE name IN ('max_connections','shared_buffers','work_mem','maintenance_work_mem','effective_cache_size','wal_level','archive_mode','log_destination','listen_addresses','port') ORDER BY name;")
        if [ -z "$OUTPUT" ]; then
            echo "{\"status\": \"unavailable\", \"message\": \"Cannot connect to PostgreSQL\", \"config_raw\": \"\", \"timestamp\": \"${TIMESTAMP}\"}"
            exit 0
        fi
        ESCAPED=$(echo "$OUTPUT" | escape_json)
        echo "{\"status\": \"success\", \"config_raw\": ${ESCAPED}, \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    logs)
        # ログ行数パラメータ
        LINES="${2:-50}"
        if ! echo "$LINES" | grep -qE '^[0-9]+$'; then
            LINES=50
        fi
        if [ "$LINES" -gt 200 ]; then
            LINES=200
        fi
        if [ "$LINES" -lt 1 ]; then
            LINES=50
        fi

        OUTPUT=""
        # PostgreSQL ログファイルを探す
        LOG_DIR=""
        for d in "/var/log/postgresql" "/var/lib/pgsql/data/pg_log" "/var/lib/postgresql/data/pg_log"; do
            if [ -d "$d" ]; then
                LOG_DIR="$d"
                break
            fi
        done

        if [ -n "$LOG_DIR" ]; then
            LOG_FILE=$(find "${LOG_DIR}" -maxdepth 1 -name "*.log" -type f -printf "%T@ %p\n" 2>/dev/null | sort -rn | head -1 | awk '{print $2}' || echo "")
            if [ -n "$LOG_FILE" ]; then
                OUTPUT=$(tail -n "$LINES" "$LOG_FILE" 2>/dev/null || echo "")
            fi
        fi

        # ファイルが見つからない場合は journalctl を使用
        if [ -z "$OUTPUT" ]; then
            OUTPUT=$(journalctl -u "postgresql*" --no-pager -n "$LINES" 2>/dev/null || echo "")
        fi

        ESCAPED=$(echo "$OUTPUT" | escape_json)
        echo "{\"status\": \"success\", \"logs\": ${ESCAPED}, \"lines\": ${LINES}, \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    *)
        error_json "Unexpected subcommand: $SUBCOMMAND"
        ;;
esac
