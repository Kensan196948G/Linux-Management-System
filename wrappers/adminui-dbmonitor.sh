#!/bin/bash
# ============================================================
# adminui-dbmonitor.sh - MySQL/PostgreSQL 監視ラッパースクリプト
#
# 実行ユーザー: svc-adminui (sudo 経由)
# 用途: DBサーバーの詳細統計・プロセス・スロークエリ取得
#
# 使用方法:
#   ./adminui-dbmonitor.sh mysql status
#   ./adminui-dbmonitor.sh mysql processlist
#   ./adminui-dbmonitor.sh mysql variables
#   ./adminui-dbmonitor.sh mysql databases
#   ./adminui-dbmonitor.sh postgresql status
#   ./adminui-dbmonitor.sh postgresql connections
#   ./adminui-dbmonitor.sh postgresql databases
#   ./adminui-dbmonitor.sh postgresql activity
# ============================================================
set -euo pipefail
IFS=$'\n\t'

# ============================================================
# 許可リスト
# ============================================================
ALLOWED_DBS=("mysql" "postgresql")
ALLOWED_MYSQL_CMDS=("status" "processlist" "variables" "databases")
ALLOWED_PG_CMDS=("status" "connections" "databases" "activity")

# ============================================================
# 入力検証
# ============================================================
if [[ $# -lt 2 ]]; then
    echo '{"status":"error","message":"Usage: adminui-dbmonitor.sh <db_type> <command>"}' >&2
    exit 1
fi

DB_TYPE="$1"
DB_CMD="$2"

# DB タイプ検証
VALID_DB=false
for db in "${ALLOWED_DBS[@]}"; do
    if [[ "$DB_TYPE" == "$db" ]]; then
        VALID_DB=true
        break
    fi
done

if [[ "$VALID_DB" != "true" ]]; then
    echo "{\"status\":\"error\",\"message\":\"DB type not allowed: ${DB_TYPE}\"}" >&2
    exit 1
fi

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# ============================================================
# MySQL 処理
# ============================================================
if [[ "$DB_TYPE" == "mysql" ]]; then
    # MySQL コマンド検証
    VALID_CMD=false
    for cmd in "${ALLOWED_MYSQL_CMDS[@]}"; do
        if [[ "$DB_CMD" == "$cmd" ]]; then
            VALID_CMD=true
            break
        fi
    done

    if [[ "$VALID_CMD" != "true" ]]; then
        echo "{\"status\":\"error\",\"message\":\"MySQL command not allowed: ${DB_CMD}\"}" >&2
        exit 1
    fi

    # MySQL が利用可能か確認
    if ! command -v mysql >/dev/null 2>&1; then
        echo "{\"status\":\"unavailable\",\"message\":\"mysql client not installed\",\"timestamp\":\"${TIMESTAMP}\"}"
        exit 0
    fi

    case "$DB_CMD" in
        "status")
            # MySQL サービス状態と基本情報
            IS_RUNNING=false
            if systemctl is-active mysql >/dev/null 2>&1 || systemctl is-active mysqld >/dev/null 2>&1; then
                IS_RUNNING=true
            fi

            VERSION=$(mysql --version 2>/dev/null | head -1 || echo "unknown")
            UPTIME=""
            CONNECTIONS=""
            QUERIES=""

            if [[ "$IS_RUNNING" == "true" ]]; then
                # mysqladmin で統計取得（認証不要の場合）
                STATS=$(mysqladmin status 2>/dev/null || echo "")
                if [[ -n "$STATS" ]]; then
                    UPTIME=$(echo "$STATS" | grep -oP 'Uptime:\s*\K[0-9]+' || echo "")
                    CONNECTIONS=$(echo "$STATS" | grep -oP 'Threads:\s*\K[0-9]+' || echo "")
                    QUERIES=$(echo "$STATS" | grep -oP 'Queries per second avg:\s*\K[0-9.]+' || echo "")
                fi
            fi

            echo "{\"status\":\"ok\",\"db_type\":\"mysql\",\"running\":${IS_RUNNING},\"version\":\"${VERSION}\",\"uptime_seconds\":\"${UPTIME}\",\"threads\":\"${CONNECTIONS}\",\"queries_per_sec\":\"${QUERIES}\",\"timestamp\":\"${TIMESTAMP}\"}"
            ;;

        "processlist")
            # プロセス一覧（SHOW PROCESSLIST）
            if ! mysql -e "SHOW PROCESSLIST\G" 2>/dev/null; then
                echo "{\"status\":\"error\",\"message\":\"Cannot connect to MySQL (authentication required)\",\"processes\":[],\"timestamp\":\"${TIMESTAMP}\"}"
            fi
            ;;

        "variables")
            # 主要な変数を取得
            VARS=$(mysql -e "SHOW VARIABLES WHERE Variable_name IN ('max_connections','innodb_buffer_pool_size','query_cache_size','slow_query_log','long_query_time','datadir','socket');" 2>/dev/null | python3 -c "
import sys, json
rows = {}
for line in sys.stdin:
    parts = line.strip().split('\t')
    if len(parts) == 2:
        rows[parts[0]] = parts[1]
print(json.dumps({'status':'ok','db_type':'mysql','variables':rows,'timestamp':'${TIMESTAMP}'}))
" 2>/dev/null || echo "{\"status\":\"error\",\"message\":\"Cannot connect to MySQL\",\"variables\":{},\"timestamp\":\"${TIMESTAMP}\"}")
            echo "$VARS"
            ;;

        "databases")
            # データベース一覧
            DBS=$(mysql -e "SHOW DATABASES;" 2>/dev/null | python3 -c "
import sys, json
dbs = [line.strip() for line in sys.stdin if line.strip() and line.strip() != 'Database']
print(json.dumps({'status':'ok','db_type':'mysql','databases':dbs,'count':len(dbs),'timestamp':'${TIMESTAMP}'}))
" 2>/dev/null || echo "{\"status\":\"error\",\"message\":\"Cannot connect to MySQL\",\"databases\":[],\"timestamp\":\"${TIMESTAMP}\"}")
            echo "$DBS"
            ;;
    esac
fi

# ============================================================
# PostgreSQL 処理
# ============================================================
if [[ "$DB_TYPE" == "postgresql" ]]; then
    # PostgreSQL コマンド検証
    VALID_CMD=false
    for cmd in "${ALLOWED_PG_CMDS[@]}"; do
        if [[ "$DB_CMD" == "$cmd" ]]; then
            VALID_CMD=true
            break
        fi
    done

    if [[ "$VALID_CMD" != "true" ]]; then
        echo "{\"status\":\"error\",\"message\":\"PostgreSQL command not allowed: ${DB_CMD}\"}" >&2
        exit 1
    fi

    # PostgreSQL が利用可能か確認
    if ! command -v psql >/dev/null 2>&1; then
        echo "{\"status\":\"unavailable\",\"message\":\"psql client not installed\",\"timestamp\":\"${TIMESTAMP}\"}"
        exit 0
    fi

    # psql を postgres ユーザーとして実行
    PSQL_AVAILABLE=false
    if sudo -u postgres psql -c '\q' >/dev/null 2>&1; then
        PSQL_AVAILABLE=true
    fi

    case "$DB_CMD" in
        "status")
            IS_RUNNING=false
            if systemctl is-active postgresql >/dev/null 2>&1; then
                IS_RUNNING=true
            fi

            VERSION=$(psql --version 2>/dev/null | head -1 || echo "unknown")
            PG_VERSION=""
            CONNECTIONS=""

            if [[ "$PSQL_AVAILABLE" == "true" ]]; then
                PG_VERSION=$(sudo -u postgres psql -t -c "SELECT version();" 2>/dev/null | head -1 | xargs || echo "")
                CONNECTIONS=$(sudo -u postgres psql -t -c "SELECT count(*) FROM pg_stat_activity;" 2>/dev/null | head -1 | xargs || echo "0")
            fi

            echo "{\"status\":\"ok\",\"db_type\":\"postgresql\",\"running\":${IS_RUNNING},\"version\":\"${VERSION}\",\"pg_version\":\"${PG_VERSION}\",\"active_connections\":\"${CONNECTIONS}\",\"timestamp\":\"${TIMESTAMP}\"}"
            ;;

        "connections")
            if [[ "$PSQL_AVAILABLE" != "true" ]]; then
                echo "{\"status\":\"error\",\"message\":\"Cannot connect to PostgreSQL\",\"connections\":[],\"timestamp\":\"${TIMESTAMP}\"}"
                exit 0
            fi

            RESULT=$(sudo -u postgres psql -t -c "SELECT datname, usename, application_name, client_addr, state, query_start, wait_event_type FROM pg_stat_activity ORDER BY query_start DESC LIMIT 50;" 2>/dev/null | python3 -c "
import sys, json
conns = []
for line in sys.stdin:
    parts = [p.strip() for p in line.split('|')]
    if len(parts) >= 6 and parts[0]:
        conns.append({
            'datname': parts[0],
            'usename': parts[1] if len(parts) > 1 else '',
            'application': parts[2] if len(parts) > 2 else '',
            'client_addr': parts[3] if len(parts) > 3 else '',
            'state': parts[4] if len(parts) > 4 else '',
            'query_start': parts[5] if len(parts) > 5 else '',
        })
print(json.dumps({'status':'ok','db_type':'postgresql','connections':conns,'count':len(conns),'timestamp':'${TIMESTAMP}'}))
" 2>/dev/null || echo "{\"status\":\"error\",\"message\":\"Query failed\",\"connections\":[],\"timestamp\":\"${TIMESTAMP}\"}")
            echo "$RESULT"
            ;;

        "databases")
            if [[ "$PSQL_AVAILABLE" != "true" ]]; then
                echo "{\"status\":\"error\",\"message\":\"Cannot connect to PostgreSQL\",\"databases\":[],\"timestamp\":\"${TIMESTAMP}\"}"
                exit 0
            fi

            RESULT=$(sudo -u postgres psql -t -c "SELECT datname, pg_size_pretty(pg_database_size(datname)), datallowconn FROM pg_database ORDER BY datname;" 2>/dev/null | python3 -c "
import sys, json
dbs = []
for line in sys.stdin:
    parts = [p.strip() for p in line.split('|')]
    if len(parts) >= 3 and parts[0]:
        dbs.append({'name': parts[0], 'size': parts[1], 'allow_conn': parts[2] == 't'})
print(json.dumps({'status':'ok','db_type':'postgresql','databases':dbs,'count':len(dbs),'timestamp':'${TIMESTAMP}'}))
" 2>/dev/null || echo "{\"status\":\"error\",\"message\":\"Query failed\",\"databases\":[],\"timestamp\":\"${TIMESTAMP}\"}")
            echo "$RESULT"
            ;;

        "activity")
            if [[ "$PSQL_AVAILABLE" != "true" ]]; then
                echo "{\"status\":\"error\",\"message\":\"Cannot connect to PostgreSQL\",\"activity\":[],\"timestamp\":\"${TIMESTAMP}\"}"
                exit 0
            fi

            RESULT=$(sudo -u postgres psql -t -c "SELECT pid, usename, datname, state, wait_event_type, left(query, 100) as query FROM pg_stat_activity WHERE state != 'idle' ORDER BY query_start DESC LIMIT 20;" 2>/dev/null | python3 -c "
import sys, json
activities = []
for line in sys.stdin:
    parts = [p.strip() for p in line.split('|')]
    if len(parts) >= 5 and parts[0]:
        activities.append({
            'pid': parts[0],
            'usename': parts[1] if len(parts) > 1 else '',
            'datname': parts[2] if len(parts) > 2 else '',
            'state': parts[3] if len(parts) > 3 else '',
            'wait_event': parts[4] if len(parts) > 4 else '',
            'query': parts[5] if len(parts) > 5 else '',
        })
print(json.dumps({'status':'ok','db_type':'postgresql','activity':activities,'count':len(activities),'timestamp':'${TIMESTAMP}'}))
" 2>/dev/null || echo "{\"status\":\"error\",\"message\":\"Query failed\",\"activity\":[],\"timestamp\":\"${TIMESTAMP}\"}")
            echo "$RESULT"
            ;;
    esac
fi
