#!/bin/bash
# ==============================================================================
# adminui-servers.sh - サーバー管理ラッパー（読み取り専用）
#
# 機能:
#   nginx/apache2/mysql/postgresql/redis の状態・バージョン・設定を取得する。
#   全操作は読み取り専用。サービスの起動・停止・変更は行わない。
#
# 使用方法:
#   adminui-servers.sh status [server]   - 全サーバーまたは指定サーバーの状態
#   adminui-servers.sh version <server>  - バージョン情報
#   adminui-servers.sh config <server>   - 設定ファイルの基本情報
#
# 許可サーバー:
#   nginx, apache2, mysql, postgresql, redis
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - サーバー名は allowlist チェック済み
#   - 設定ファイルのパスもホワイトリスト管理
# ==============================================================================

set -euo pipefail

# ==============================================================================
# 定数
# ==============================================================================

ALLOWED_SERVERS=("nginx" "apache2" "mysql" "postgresql" "redis")

# 設定ファイルのallowlist（パストラバーサル対策）
declare -A CONFIG_FILES=(
    ["nginx"]="/etc/nginx/nginx.conf"
    ["apache2"]="/etc/apache2/apache2.conf"
    ["mysql"]="/etc/mysql/mysql.conf.d/mysqld.cnf"
    ["postgresql"]="/etc/postgresql"
    ["redis"]="/etc/redis/redis.conf"
)

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

# サーバー名 allowlist チェック
check_server_allowed() {
    local server="$1"
    local allowed=false
    for s in "${ALLOWED_SERVERS[@]}"; do
        if [[ "$server" == "$s" ]]; then
            allowed=true
            break
        fi
    done
    if ! $allowed; then
        error_json "Server not allowed: ${server}. Allowed: ${ALLOWED_SERVERS[*]}"
        exit 1
    fi
}

# サービス状態を JSON で返す
get_service_status_json() {
    local service="$1"
    local active_state running_state pid main_pid load_state

    if ! command -v systemctl &>/dev/null; then
        printf '{"service":"%s","active":"unknown","status":"systemctl not available"}' "$service"
        return
    fi

    # systemctl show で状態取得（プロセス外部起動のため情報が安定）
    active_state=$(systemctl show "${service}" --property=ActiveState 2>/dev/null | cut -d= -f2 || echo "unknown")
    running_state=$(systemctl show "${service}" --property=SubState 2>/dev/null | cut -d= -f2 || echo "unknown")
    load_state=$(systemctl show "${service}" --property=LoadState 2>/dev/null | cut -d= -f2 || echo "unknown")
    main_pid=$(systemctl show "${service}" --property=MainPID 2>/dev/null | cut -d= -f2 || echo "0")

    # 有効化状態（stdout を確実に1行に正規化）
    local enabled_state
    enabled_state=$(systemctl is-enabled "${service}" 2>/dev/null | head -1)
    [ -z "${enabled_state}" ] && enabled_state="unknown"

    printf '{"service":"%s","active_state":"%s","sub_state":"%s","load_state":"%s","main_pid":%s,"enabled":"%s"}' \
        "$service" "$active_state" "$running_state" "$load_state" "$main_pid" "$enabled_state"
}

# ==============================================================================
# 引数チェック
# ==============================================================================

if [[ $# -lt 1 ]]; then
    error_json "Usage: adminui-servers.sh <subcommand> [server]"
    exit 1
fi

SUBCOMMAND="$1"

# ==============================================================================
# サブコマンド実行
# ==============================================================================

case "$SUBCOMMAND" in

    # ------------------------------------------------------------------
    # status [server]: サービス状態
    # ------------------------------------------------------------------
    status)
        if [[ $# -eq 1 ]]; then
            # 全サーバーの状態を一括取得
            results=""
            for server in "${ALLOWED_SERVERS[@]}"; do
                status_json=$(get_service_status_json "$server")
                if [[ -n "$results" ]]; then
                    results="${results},"
                fi
                results="${results}${status_json}"
            done
            printf '{"status":"success","servers":[%s],"timestamp":"%s"}\n' \
                "$results" "$(timestamp)"
        else
            # 特定サーバーの状態
            SERVER="$2"
            check_server_allowed "$SERVER"
            status_json=$(get_service_status_json "$SERVER")
            printf '{"status":"success","server":%s,"timestamp":"%s"}\n' \
                "$status_json" "$(timestamp)"
        fi
        ;;

    # ------------------------------------------------------------------
    # version <server>: バージョン情報
    # ------------------------------------------------------------------
    version)
        if [[ $# -ne 2 ]]; then
            error_json "Usage: adminui-servers.sh version <server>"
            exit 1
        fi

        SERVER="$2"
        check_server_allowed "$SERVER"

        version_string="unknown"

        case "$SERVER" in
            nginx)
                if command -v nginx &>/dev/null; then
                    version_string=$(nginx -v 2>&1 | head -1 | sed 's/.*nginx\///' || echo "unknown")
                fi
                ;;
            apache2)
                if command -v apache2 &>/dev/null; then
                    version_string=$(apache2 -v 2>/dev/null | head -1 | sed 's/Server version: //' || echo "unknown")
                elif command -v httpd &>/dev/null; then
                    version_string=$(httpd -v 2>/dev/null | head -1 | sed 's/Server version: //' || echo "unknown")
                fi
                ;;
            mysql)
                if command -v mysql &>/dev/null; then
                    version_string=$(mysql --version 2>/dev/null | head -1 || echo "unknown")
                fi
                ;;
            postgresql)
                if command -v psql &>/dev/null; then
                    version_string=$(psql --version 2>/dev/null | head -1 || echo "unknown")
                fi
                ;;
            redis)
                if command -v redis-server &>/dev/null; then
                    version_string=$(redis-server --version 2>/dev/null | head -1 || echo "unknown")
                fi
                ;;
        esac

        # 特殊文字エスケープ
        version_string=$(printf '%s' "$version_string" | sed 's/"/\\"/g')

        printf '{"status":"success","server":"%s","version":"%s","timestamp":"%s"}\n' \
            "$SERVER" "$version_string" "$(timestamp)"
        ;;

    # ------------------------------------------------------------------
    # config <server>: 設定ファイル情報（パスのみ、内容は返さない）
    # ------------------------------------------------------------------
    config)
        if [[ $# -ne 2 ]]; then
            error_json "Usage: adminui-servers.sh config <server>"
            exit 1
        fi

        SERVER="$2"
        check_server_allowed "$SERVER"

        config_path="${CONFIG_FILES[$SERVER]:-}"
        if [[ -z "$config_path" ]]; then
            error_json "No config path defined for: $SERVER"
            exit 1
        fi

        # ファイル/ディレクトリの存在チェック
        if [[ -f "$config_path" ]]; then
            file_size=$(stat -c%s "$config_path" 2>/dev/null || echo 0)
            file_modified=$(stat -c%Y "$config_path" 2>/dev/null || echo 0)
            printf '{"status":"success","server":"%s","config_path":"%s","exists":true,"type":"file","size":%s,"modified":%s,"timestamp":"%s"}\n' \
                "$SERVER" "$config_path" "$file_size" "$file_modified" "$(timestamp)"
        elif [[ -d "$config_path" ]]; then
            dir_count=$(find "$config_path" -name "*.conf" 2>/dev/null | wc -l || echo 0)
            printf '{"status":"success","server":"%s","config_path":"%s","exists":true,"type":"directory","conf_file_count":%s,"timestamp":"%s"}\n' \
                "$SERVER" "$config_path" "$dir_count" "$(timestamp)"
        else
            printf '{"status":"success","server":"%s","config_path":"%s","exists":false,"timestamp":"%s"}\n' \
                "$SERVER" "$config_path" "$(timestamp)"
        fi
        ;;

    *)
        error_json "Unknown subcommand: $SUBCOMMAND. Allowed: status, version, config"
        exit 1
        ;;

esac

exit 0
