#!/usr/bin/env bash
# ==============================================================================
# adminui-mysql.sh - MySQL/MariaDB 管理ラッパー（読み取り専用）
#
# 機能:
#   MySQL/MariaDB の状態・データベース・ユーザー・プロセス・変数・ログを取得
#   全操作は読み取り専用。設定の変更は行わない。
#
# 使用方法:
#   adminui-mysql.sh <subcommand> [args...]
#
# サブコマンド:
#   status      - MySQL サービス状態・バージョン
#   databases   - データベース一覧
#   users       - ユーザー一覧（パスワードハッシュ除外）
#   processlist - プロセスリスト
#   variables   - システム変数（重要なもの）
#   logs        - エラーログ（第2引数: 行数、デフォルト50）
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行（bash 内では変数展開を最小化）
#   - 許可サブコマンドのみ実行（allowlist方式）
#   - 読み取り専用（設定変更・再起動等は行わない）
# ==============================================================================

set -euo pipefail

readonly ALLOWED_SUBCOMMANDS=("status" "databases" "users" "processlist" "variables" "logs")

# エラー出力ヘルパー
error_json() {
    printf '{"status":"error","message":"%s"}\n' "$1" >&2
    exit 1
}

if [ "$#" -lt 1 ]; then
    error_json "Usage: adminui-mysql.sh <subcommand> [args...]"
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
    error_json "Unknown subcommand: ${SUBCOMMAND}"
fi

# MySQL/MariaDB コマンドの存在チェック
MYSQL_BIN=""
if command -v mysql >/dev/null 2>&1; then
    MYSQL_BIN="mysql"
elif command -v mariadb >/dev/null 2>&1; then
    MYSQL_BIN="mariadb"
fi

MYSQLADMIN_BIN=""
if command -v mysqladmin >/dev/null 2>&1; then
    MYSQLADMIN_BIN="mysqladmin"
elif command -v mariadb-admin >/dev/null 2>&1; then
    MYSQLADMIN_BIN="mariadb-admin"
fi

# 未インストール時は unavailable を返す
if [ -z "$MYSQL_BIN" ] && [ -z "$MYSQLADMIN_BIN" ]; then
    printf '{"status":"unavailable","message":"mysql/mariadb is not installed"}\n'
    exit 0
fi

case "$SUBCOMMAND" in
    status)
        # MySQL サービス状態
        SVC_STATUS="unknown"
        if command -v systemctl >/dev/null 2>&1; then
            if systemctl is-active --quiet mysql 2>/dev/null || systemctl is-active --quiet mariadb 2>/dev/null; then
                SVC_STATUS="running"
            else
                SVC_STATUS="stopped"
            fi
        fi

        # バージョン取得
        VERSION="unknown"
        if [ -n "$MYSQL_BIN" ]; then
            VERSION=$("$MYSQL_BIN" --version 2>/dev/null || echo "unknown")
        fi

        printf '{"status":"%s","version":"%s"}\n' "$SVC_STATUS" "$VERSION"
        ;;

    databases)
        # データベース一覧
        if [ -z "$MYSQL_BIN" ]; then
            printf '{"status":"unavailable","message":"mysql client not found"}\n'
            exit 0
        fi
        OUTPUT=$("$MYSQL_BIN" --defaults-extra-file=/dev/null -u root --batch --skip-column-names \
            -e "SHOW DATABASES;" 2>/dev/null || echo "")
        if [ -z "$OUTPUT" ]; then
            printf '{"databases":[]}\n'
        else
            ESCAPED=$(printf '%s' "$OUTPUT" | python3 -c "
import sys, json
lines = [l for l in sys.stdin.read().splitlines() if l]
print(json.dumps({'databases': lines}))
")
            printf '%s\n' "$ESCAPED"
        fi
        ;;

    users)
        # ユーザー一覧（パスワードハッシュ除外）
        if [ -z "$MYSQL_BIN" ]; then
            printf '{"status":"unavailable","message":"mysql client not found"}\n'
            exit 0
        fi
        OUTPUT=$("$MYSQL_BIN" --defaults-extra-file=/dev/null -u root --batch --skip-column-names \
            -e "SELECT User, Host, account_locked FROM mysql.user;" 2>/dev/null || echo "")
        ESCAPED=$(printf '%s' "$OUTPUT" | python3 -c "
import sys, json
users = []
for line in sys.stdin.read().splitlines():
    if line.strip():
        parts = line.split('\t')
        if len(parts) >= 3:
            users.append({'user': parts[0], 'host': parts[1], 'account_locked': parts[2]})
        elif len(parts) == 2:
            users.append({'user': parts[0], 'host': parts[1], 'account_locked': 'N'})
print(json.dumps({'users': users}))
")
        printf '%s\n' "$ESCAPED"
        ;;

    processlist)
        # プロセスリスト
        if [ -z "$MYSQL_BIN" ]; then
            printf '{"status":"unavailable","message":"mysql client not found"}\n'
            exit 0
        fi
        OUTPUT=$("$MYSQL_BIN" --defaults-extra-file=/dev/null -u root --batch \
            -e "SHOW PROCESSLIST;" 2>/dev/null || echo "")
        ESCAPED=$(printf '%s' "$OUTPUT" | python3 -c "
import sys, json
lines = sys.stdin.read().splitlines()
if not lines:
    print(json.dumps({'processes': []}))
    sys.exit()
headers = lines[0].split('\t') if lines else []
processes = []
for line in lines[1:]:
    if line.strip():
        parts = line.split('\t')
        row = dict(zip(headers, parts))
        processes.append(row)
print(json.dumps({'processes': processes}))
")
        printf '%s\n' "$ESCAPED"
        ;;

    variables)
        # システム変数（重要なもの）
        if [ -z "$MYSQL_BIN" ]; then
            printf '{"status":"unavailable","message":"mysql client not found"}\n'
            exit 0
        fi
        OUTPUT=$("$MYSQL_BIN" --defaults-extra-file=/dev/null -u root --batch --skip-column-names \
            -e "SHOW GLOBAL VARIABLES WHERE Variable_name IN (
                'version','max_connections','innodb_buffer_pool_size',
                'query_cache_size','slow_query_log','long_query_time',
                'character_set_server','collation_server','datadir',
                'max_allowed_packet','wait_timeout','interactive_timeout'
            );" 2>/dev/null || echo "")
        ESCAPED=$(printf '%s' "$OUTPUT" | python3 -c "
import sys, json
variables = {}
for line in sys.stdin.read().splitlines():
    if line.strip():
        parts = line.split('\t', 1)
        if len(parts) == 2:
            variables[parts[0]] = parts[1]
print(json.dumps({'variables': variables}))
")
        printf '%s\n' "$ESCAPED"
        ;;

    logs)
        # エラーログ
        LINES="${2:-50}"
        # LINES を整数に制限
        if ! [[ "$LINES" =~ ^[0-9]+$ ]]; then
            LINES=50
        fi
        if [ "$LINES" -gt 200 ]; then
            LINES=200
        fi
        if [ "$LINES" -lt 1 ]; then
            LINES=50
        fi

        LOG_FILE=""
        # MySQL デフォルトエラーログパス候補
        for candidate in "/var/log/mysql/error.log" "/var/log/mysqld.log" "/var/log/mysql.log"; do
            if [ -f "$candidate" ]; then
                LOG_FILE="$candidate"
                break
            fi
        done

        if [ -n "$LOG_FILE" ]; then
            OUTPUT=$(tail -n "$LINES" "$LOG_FILE" 2>/dev/null || echo "")
        else
            OUTPUT=$(journalctl -u mysql -u mariadb --no-pager -n "$LINES" 2>/dev/null || echo "")
        fi

        ESCAPED=$(printf '%s' "$OUTPUT" | python3 -c "
import sys, json
print(json.dumps({'logs': sys.stdin.read(), 'lines': int('$LINES')}))
")
        printf '%s\n' "$ESCAPED"
        ;;
esac
