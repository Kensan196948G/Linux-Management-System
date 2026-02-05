#!/bin/bash
# adminui-status.sh - システム状態取得ラッパー
#
# 用途: CPU/メモリ/ディスク使用率の安全な取得
# 権限: root 権限不要（情報取得のみ）
# 呼び出し: sudo /usr/local/sbin/adminui-status.sh

set -euo pipefail

# ログ出力
log() {
    logger -t adminui-status -p user.info "$*"
    echo "[$(date -Iseconds)] $*" >&2
}

# エラーログ
# shellcheck disable=SC2317
error() {
    logger -t adminui-status -p user.err "ERROR: $*"
    echo "[$(date -Iseconds)] ERROR: $*" >&2
}

# 実行前ログ
log "System status check started by UID=$UID"

# JSON 出力開始
echo "{"

# CPU 使用率
echo '  "cpu": {'
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1}')
echo "    \"usage_percent\": $CPU_USAGE,"

# CPU コア数
CPU_CORES=$(nproc)
echo "    \"cores\": $CPU_CORES,"

# ロードアベレージ
LOAD_AVG=$(uptime | awk -F'load average:' '{print $2}' | sed 's/^ //')
echo "    \"load_average\": \"$LOAD_AVG\""
echo '  },'

# メモリ使用率
echo '  "memory": {'
MEM_INFO=$(free -m | awk 'NR==2{printf "\"total\": %s, \"used\": %s, \"free\": %s, \"usage_percent\": %.2f", $2, $3, $4, $3*100/$2}')
echo "    $MEM_INFO"
echo '  },'

# ディスク使用率
echo '  "disk": ['
FIRST=true
df -h --output=source,fstype,size,used,avail,pcent,target | tail -n +2 | while read -r line; do
    SOURCE=$(echo "$line" | awk '{print $1}')
    FSTYPE=$(echo "$line" | awk '{print $2}')
    SIZE=$(echo "$line" | awk '{print $3}')
    USED=$(echo "$line" | awk '{print $4}')
    AVAIL=$(echo "$line" | awk '{print $5}')
    PCENT=$(echo "$line" | awk '{print $6}' | sed 's/%//')
    TARGET=$(echo "$line" | awk '{print $7}')

    # システムディレクトリのみ（/dev/loop などを除外）
    if [[ "$SOURCE" =~ ^/dev/(sd|nvme|vd|hd) ]] || [[ "$TARGET" == "/" ]] || [[ "$TARGET" == "/home" ]] || [[ "$TARGET" == "/var" ]]; then
        if [ "$FIRST" = false ]; then
            echo ","
        fi
        FIRST=false
        echo -n "    {\"source\": \"$SOURCE\", \"fstype\": \"$FSTYPE\", \"size\": \"$SIZE\", \"used\": \"$USED\", \"available\": \"$AVAIL\", \"usage_percent\": $PCENT, \"mountpoint\": \"$TARGET\"}"
    fi
done
echo ""
echo '  ],'

# システム稼働時間
echo '  "uptime": {'
UPTIME=$(uptime -p | sed 's/up //')
UPTIME_SECONDS=$(awk '{print int($1)}' /proc/uptime)
echo "    \"human_readable\": \"$UPTIME\","
echo "    \"seconds\": $UPTIME_SECONDS"
echo '  },'

# タイムスタンプ
TIMESTAMP=$(date -Iseconds)
echo "  \"timestamp\": \"$TIMESTAMP\""

# JSON 出力終了
echo "}"

# 成功ログ
log "System status check completed successfully"

exit 0
