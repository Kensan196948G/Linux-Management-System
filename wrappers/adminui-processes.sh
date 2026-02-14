#!/bin/bash
# adminui-processes.sh - プロセス一覧取得ラッパー
#
# 用途: ps コマンドを使用した安全なプロセス一覧取得
# 権限: root 権限不要（情報取得のみ）
# 呼び出し: /usr/local/sbin/adminui-processes.sh [options]
#
# セキュリティ原則:
# - allowlist 方式
# - 入力検証必須
# - 配列渡しによるコマンド実行

set -euo pipefail

# ログ出力
log() {
    logger -t adminui-processes -p user.info "$*"
    echo "[$(date -Iseconds)] $*" >&2
}

# エラーログ
error() {
    logger -t adminui-processes -p user.err "ERROR: $*"
    echo "[$(date -Iseconds)] ERROR: $*" >&2
}

# 使用方法
usage() {
    echo "Usage: $0 [OPTIONS]" >&2
    echo "" >&2
    echo "Options:" >&2
    echo "  --sort=<cpu|mem|pid|time>  Sort key (default: cpu)" >&2
    echo "  --limit=<N>                Limit to N processes (default: 100, max: 1000)" >&2
    echo "  --filter-user=<username>   Filter by user (allowlist)" >&2
    echo "  --min-cpu=<N>              Minimum CPU usage (0.0-100.0)" >&2
    echo "  --min-mem=<N>              Minimum memory usage (0.0-100.0)" >&2
    echo "" >&2
    echo "Allowed users:" >&2
    for user in "${ALLOWED_USERS[@]}"; do
        echo "  - $user" >&2
    done
    echo "" >&2
    echo "Allowed sort keys:" >&2
    for key in "${ALLOWED_SORTS[@]}"; do
        echo "  - $key" >&2
    done
    exit 1
}

# ===================================================================
# 許可リスト（allowlist）
# ===================================================================

ALLOWED_USERS=(
    "root"
    "www-data"
    "postgres"
    "redis"
    "nginx"
    "adminui"
)

ALLOWED_SORTS=(
    "cpu"
    "mem"
    "pid"
    "time"
)

# ===================================================================
# 禁止文字パターン
# ===================================================================
# shellcheck disable=SC2016
FORBIDDEN_CHARS='[;|&$()` ><*?{}[\]]'

# ===================================================================
# デフォルト設定
# ===================================================================
SORT_BY="cpu"
LIMIT=100
MAX_LIMIT=1000
FILTER_USER=""
MIN_CPU=0.0
MIN_MEM=0.0

# ===================================================================
# 入力パース
# ===================================================================

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sort=*)
            SORT_BY="${1#*=}"
            shift
            ;;
        --limit=*)
            LIMIT="${1#*=}"
            shift
            ;;
        --filter-user=*)
            FILTER_USER="${1#*=}"
            shift
            ;;
        --min-cpu=*)
            MIN_CPU="${1#*=}"
            shift
            ;;
        --min-mem=*)
            MIN_MEM="${1#*=}"
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            error "Unknown argument: $1"
            usage
            ;;
    esac
done

# 実行前ログ
log "Process list requested: sort=$SORT_BY, limit=$LIMIT, user=$FILTER_USER, min_cpu=$MIN_CPU, min_mem=$MIN_MEM, caller=${SUDO_USER:-$USER}"

# ===================================================================
# 入力検証関数
# ===================================================================

validate_sort_key() {
    local sort="$1"
    for allowed in "${ALLOWED_SORTS[@]}"; do
        if [ "$sort" = "$allowed" ]; then
            return 0
        fi
    done
    error "Invalid sort key: $sort"
    return 1
}

validate_user() {
    local user="$1"

    # 空チェック
    if [ -z "$user" ]; then
        return 0  # 空は許可（フィルタなし）
    fi

    # 長さチェック
    if [ ${#user} -gt 32 ]; then
        error "User name too long: $user"
        return 1
    fi

    # 特殊文字チェック
    if [[ "$user" =~ $FORBIDDEN_CHARS ]]; then
        error "Forbidden character in user name: $user"
        log "SECURITY: Forbidden character detected in user name - user=$user, caller=${SUDO_USER:-$USER}"
        return 1
    fi

    # フォーマットチェック
    if [[ ! "$user" =~ ^[a-zA-Z0-9_-]+$ ]]; then
        error "Invalid user name format: $user"
        return 1
    fi

    # allowlist チェック
    for allowed in "${ALLOWED_USERS[@]}"; do
        if [ "$user" = "$allowed" ]; then
            return 0
        fi
    done

    error "User not in allowlist: $user"
    log "SECURITY: Unauthorized user filter attempt - user=$user, caller=${SUDO_USER:-$USER}"
    return 1
}

validate_number() {
    local value="$1"
    local name="$2"

    if [[ ! "$value" =~ ^[0-9]+\.?[0-9]*$ ]]; then
        error "Invalid $name: must be a number"
        return 1
    fi

    return 0
}

# ===================================================================
# 入力検証実行
# ===================================================================

# ソートキー検証
if ! validate_sort_key "$SORT_BY"; then
    echo '{"status": "error", "message": "Invalid sort key"}'
    exit 1
fi

# ユーザー名検証
if ! validate_user "$FILTER_USER"; then
    echo "{\"status\": \"error\", \"message\": \"User not allowed: $FILTER_USER\"}"
    exit 1
fi

# limit 検証
if ! validate_number "$LIMIT" "limit"; then
    echo '{"status": "error", "message": "Invalid limit"}'
    exit 1
fi

if [ "$LIMIT" -lt 1 ]; then
    LIMIT=1
elif [ "$LIMIT" -gt "$MAX_LIMIT" ]; then
    log "WARN: Requested limit ($LIMIT) exceeds max ($MAX_LIMIT), capping to $MAX_LIMIT"
    LIMIT=$MAX_LIMIT
fi

# CPU使用率検証
if ! validate_number "$MIN_CPU" "min_cpu"; then
    echo '{"status": "error", "message": "Invalid min_cpu"}'
    exit 1
fi

if (( $(echo "$MIN_CPU < 0.0" | bc -l) )) || (( $(echo "$MIN_CPU > 100.0" | bc -l) )); then
    error "min_cpu out of range: $MIN_CPU"
    echo '{"status": "error", "message": "min_cpu out of range (0.0-100.0)"}'
    exit 1
fi

# メモリ使用率検証
if ! validate_number "$MIN_MEM" "min_mem"; then
    echo '{"status": "error", "message": "Invalid min_mem"}'
    exit 1
fi

if (( $(echo "$MIN_MEM < 0.0" | bc -l) )) || (( $(echo "$MIN_MEM > 100.0" | bc -l) )); then
    error "min_mem out of range: $MIN_MEM"
    echo '{"status": "error", "message": "min_mem out of range (0.0-100.0)"}'
    exit 1
fi

log "Input validation passed: sort=$SORT_BY, limit=$LIMIT, user=$FILTER_USER"

# ===================================================================
# ps コマンド構築
# ===================================================================

# ps コマンド引数（配列渡し）
PS_ARGS=("aux")

# ソートオプション
case "$SORT_BY" in
    cpu)
        PS_ARGS+=("--sort=-%cpu")
        ;;
    mem)
        PS_ARGS+=("--sort=-%mem")
        ;;
    pid)
        PS_ARGS+=("--sort=pid")
        ;;
    time)
        PS_ARGS+=("--sort=-time")
        ;;
esac

# ユーザーフィルタ
if [ -n "$FILTER_USER" ]; then
    PS_ARGS+=("--user" "$FILTER_USER")
fi

# ===================================================================
# プロセス情報取得
# ===================================================================

log "Executing ps command: ps ${PS_ARGS[*]}"

# ps コマンド実行
if ! OUTPUT=$(ps "${PS_ARGS[@]}" 2>&1); then
    error "Failed to execute ps command"
    echo '{"status": "error", "message": "Failed to retrieve process list"}'
    exit 1
fi

# ===================================================================
# JSON 出力構築
# ===================================================================

# プロセス数カウント
TOTAL_PROCESSES=$(echo "$OUTPUT" | tail -n +2 | wc -l)
RETURNED_PROCESSES=0

echo "{"
echo "  \"status\": \"success\","
echo "  \"total_processes\": $TOTAL_PROCESSES,"
echo "  \"sort_by\": \"$SORT_BY\","
echo "  \"filters\": {"
echo "    \"user\": \"$FILTER_USER\","
echo "    \"min_cpu\": $MIN_CPU,"
echo "    \"min_mem\": $MIN_MEM"
echo "  },"
echo "  \"processes\": ["

FIRST=true

# プロセス情報をパースしてJSONに変換
while IFS= read -r line; do
    # ヘッダー行をスキップ
    if [[ "$line" =~ ^USER ]]; then
        continue
    fi

    # 空行をスキップ
    if [ -z "$line" ]; then
        continue
    fi

    # フィールドをパース
    USER=$(echo "$line" | awk '{print $1}')
    PID=$(echo "$line" | awk '{print $2}')
    CPU=$(echo "$line" | awk '{print $3}')
    MEM=$(echo "$line" | awk '{print $4}')
    VSZ=$(echo "$line" | awk '{print $5}')
    RSS=$(echo "$line" | awk '{print $6}')
    TTY=$(echo "$line" | awk '{print $7}')
    STAT=$(echo "$line" | awk '{print $8}')
    START=$(echo "$line" | awk '{print $9}')
    TIME=$(echo "$line" | awk '{print $10}')
    COMMAND=$(echo "$line" | awk '{for(i=11;i<=NF;i++) printf "%s ", $i}' | sed 's/ $//')

    # CPU/メモリフィルタ適用
    if (( $(echo "$CPU < $MIN_CPU" | bc -l) )); then
        continue
    fi
    if (( $(echo "$MEM < $MIN_MEM" | bc -l) )); then
        continue
    fi

    # コマンドの切り詰め（最大200文字）
    if [ ${#COMMAND} -gt 200 ]; then
        COMMAND="${COMMAND:0:200}..."
    fi

    # 機密情報のマスキング（bash parameter expansion）
    while [[ "$COMMAND" =~ password=[^\ ]* ]]; do
        COMMAND="${COMMAND/password=[^ ]*/password=***}"
    done
    while [[ "$COMMAND" =~ token=[^\ ]* ]]; do
        COMMAND="${COMMAND/token=[^ ]*/token=***}"
    done
    while [[ "$COMMAND" =~ secret=[^\ ]* ]]; do
        COMMAND="${COMMAND/secret=[^ ]*/secret=***}"
    done

    # JSON エスケープ
    COMMAND=$(echo "$COMMAND" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g')
    TTY=$(echo "$TTY" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g')
    STAT=$(echo "$STAT" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g')

    # JSON 出力
    if [ "$FIRST" = false ]; then
        echo ","
    fi
    FIRST=false

    echo -n "    {\"pid\": $PID, \"user\": \"$USER\", \"cpu_percent\": $CPU, \"mem_percent\": $MEM, \"vsz\": $VSZ, \"rss\": $RSS, \"tty\": \"$TTY\", \"stat\": \"$STAT\", \"start\": \"$START\", \"time\": \"$TIME\", \"command\": \"$COMMAND\"}"

    RETURNED_PROCESSES=$((RETURNED_PROCESSES + 1))

    # limit 到達チェック
    if [ "$RETURNED_PROCESSES" -ge "$LIMIT" ]; then
        break
    fi
done <<< "$OUTPUT"

echo ""
echo "  ],"
echo "  \"returned_processes\": $RETURNED_PROCESSES,"
echo "  \"timestamp\": \"$(date -Iseconds)\""
echo "}"

# 成功ログ
log "Process list retrieved successfully: total=$TOTAL_PROCESSES, returned=$RETURNED_PROCESSES"

exit 0
