#!/bin/bash
# ==============================================================================
# adminui-hardware.sh - ハードウェア情報取得ラッパー（読み取り専用）
#
# 機能:
#   ディスク・センサー・SMARTデータ・メモリ情報を取得する。
#   全操作は読み取り専用。
#
# 使用方法:
#   adminui-hardware.sh disks           - ディスク一覧 (lsblk -J)
#   adminui-hardware.sh disk_usage      - ディスク使用量 (df -h)
#   adminui-hardware.sh smart <device>  - SMART情報 (smartctl -j -a)
#   adminui-hardware.sh sensors         - CPU/MB温度センサー (sensors -j)
#   adminui-hardware.sh memory          - メモリ情報 (free -h)
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - デバイス名は allowlist チェック済み（/dev/ パス限定）
#   - sensors/smartctl がない場合はグレースフルフォールバック
# ==============================================================================

set -euo pipefail

# ==============================================================================
# 定数
# ==============================================================================

ALLOWED_SUBCOMMANDS=("disks" "disk_usage" "smart" "sensors" "memory")

# デバイスパス検証（/dev/sd[a-z], /dev/nvme[0-9]n[0-9], /dev/vd[a-z]）
validate_device() {
    local device="$1"
    # パストラバーサル・インジェクション対策: 厳格なパターンマッチ
    if [[ ! "$device" =~ ^/dev/(sd[a-z]|nvme[0-9]n[0-9]|vd[a-z]|xvd[a-z]|hd[a-z])$ ]]; then
        error_json "Invalid device path: $device. Must match /dev/sd[a-z], /dev/nvme[0-9]n[0-9], etc."
        exit 1
    fi
    # 実際に存在するかチェック
    if [[ ! -e "$device" ]]; then
        error_json "Device not found: $device"
        exit 1
    fi
}

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

# ==============================================================================
# 引数チェック
# ==============================================================================

if [[ $# -lt 1 ]]; then
    error_json "Usage: adminui-hardware.sh <subcommand> [device]"
    exit 1
fi

SUBCOMMAND="$1"

# allowlist チェック
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
    # disks: ブロックデバイス一覧 (lsblk -J)
    # ------------------------------------------------------------------
    disks)
        if ! command -v lsblk &>/dev/null; then
            error_json "lsblk command not found"
            exit 1
        fi

        # -J: JSON出力, -o: フィールド選択, -d: パーティションを除く（トップレベルのみ）
        if lsblk -J -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,LABEL,MODEL,SERIAL,VENDOR,ROTA,TRAN 2>/dev/null; then
            :
        else
            # フォールバック: 基本フィールドのみ
            disks_json=$(lsblk -J -o NAME,SIZE,TYPE,MOUNTPOINT 2>/dev/null || echo '{"blockdevices":[]}')
            printf '{"status":"success","disks":%s,"timestamp":"%s"}\n' \
                "$disks_json" "$(timestamp)"
        fi | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'blockdevices' in data:
    print(json.dumps({'status': 'success', 'disks': data['blockdevices'], 'timestamp': '$(timestamp)'}))
else:
    print(json.dumps({'status': 'success', 'disks': [], 'timestamp': '$(timestamp)'}))
" 2>/dev/null || printf '{"status":"success","disks":[],"timestamp":"%s"}\n' "$(timestamp)"
        ;;

    # ------------------------------------------------------------------
    # disk_usage: ディスク使用量 (df)
    # ------------------------------------------------------------------
    disk_usage)
        if ! command -v df &>/dev/null; then
            error_json "df command not found"
            exit 1
        fi

        # df -P: POSIX出力, -x: 除外するfstype
        usage_json=$(df -P -x tmpfs -x devtmpfs -x squashfs -x overlay 2>/dev/null | awk '
            NR==1 { next }  # ヘッダをスキップ
            {
                filesystem=$1; size=$2; used=$3; avail=$4; percent=$5; mountpoint=$6
                # % 記号を削除
                gsub(/%/, "", percent)
                printf "{\"filesystem\":\"%s\",\"size_kb\":%s,\"used_kb\":%s,\"avail_kb\":%s,\"use_percent\":%s,\"mountpoint\":\"%s\"},",
                    filesystem, size, used, avail, percent, mountpoint
            }
        ' | sed 's/,$//')

        printf '{"status":"success","usage":[%s],"timestamp":"%s"}\n' \
            "${usage_json:-}" "$(timestamp)"
        ;;

    # ------------------------------------------------------------------
    # smart <device>: SMART情報 (smartctl)
    # ------------------------------------------------------------------
    smart)
        if [[ $# -ne 2 ]]; then
            error_json "Usage: adminui-hardware.sh smart <device>"
            exit 1
        fi

        DEVICE="$2"
        validate_device "$DEVICE"

        if ! command -v smartctl &>/dev/null; then
            error_json "smartctl not found (install smartmontools)"
            exit 1
        fi

        # -j: JSON出力, -a: 全情報
        smart_output=$(smartctl -j -a "$DEVICE" 2>/dev/null || true)

        if [[ -z "$smart_output" ]]; then
            # smartctl が JSON をサポートしない古いバージョン
            error_json "smartctl JSON output not supported or device error"
            exit 1
        fi

        # statusフィールドを追加してラップ
        printf '{"status":"success","device":"%s","smart":%s,"timestamp":"%s"}\n' \
            "$DEVICE" "$smart_output" "$(timestamp)"
        ;;

    # ------------------------------------------------------------------
    # sensors: 温度センサー (lm-sensors)
    # ------------------------------------------------------------------
    sensors)
        if ! command -v sensors &>/dev/null; then
            # sensors がない場合は /sys/class/thermal/ からフォールバック
            thermal_json=""
            for zone in /sys/class/thermal/thermal_zone*/; do
                if [[ -f "${zone}temp" && -f "${zone}type" ]]; then
                    temp_raw=$(cat "${zone}temp" 2>/dev/null || echo 0)
                    zone_type=$(cat "${zone}type" 2>/dev/null || echo "unknown")
                    temp_c=$(echo "scale=1; $temp_raw / 1000" | bc 2>/dev/null || echo "0.0")
                    zone_name=$(basename "$zone")
                    if [[ -n "$thermal_json" ]]; then
                        thermal_json="${thermal_json},"
                    fi
                    thermal_json="${thermal_json}{\"zone\":\"${zone_name}\",\"type\":\"${zone_type}\",\"temp_celsius\":${temp_c}}"
                fi
            done
            printf '{"status":"success","source":"thermal_zone","sensors":[%s],"timestamp":"%s"}\n' \
                "${thermal_json:-}" "$(timestamp)"
        else
            # lm-sensors JSON 出力
            sensors_output=$(sensors -j 2>/dev/null || echo "{}")
            printf '{"status":"success","source":"lm-sensors","sensors":%s,"timestamp":"%s"}\n' \
                "$sensors_output" "$(timestamp)"
        fi
        ;;

    # ------------------------------------------------------------------
    # memory: メモリ情報 (free + /proc/meminfo)
    # ------------------------------------------------------------------
    memory)
        if [[ -f /proc/meminfo ]]; then
            mem_total=$(grep "^MemTotal:" /proc/meminfo | awk '{print $2}')
            mem_free=$(grep "^MemFree:" /proc/meminfo | awk '{print $2}')
            mem_available=$(grep "^MemAvailable:" /proc/meminfo | awk '{print $2}')
            mem_buffers=$(grep "^Buffers:" /proc/meminfo | awk '{print $2}')
            mem_cached=$(grep "^Cached:" /proc/meminfo | awk '{print $2}')
            swap_total=$(grep "^SwapTotal:" /proc/meminfo | awk '{print $2}')
            swap_free=$(grep "^SwapFree:" /proc/meminfo | awk '{print $2}')

            printf '{"status":"success","memory":{"total_kb":%s,"free_kb":%s,"available_kb":%s,"buffers_kb":%s,"cached_kb":%s,"swap_total_kb":%s,"swap_free_kb":%s},"timestamp":"%s"}\n' \
                "${mem_total:-0}" "${mem_free:-0}" "${mem_available:-0}" \
                "${mem_buffers:-0}" "${mem_cached:-0}" \
                "${swap_total:-0}" "${swap_free:-0}" \
                "$(timestamp)"
        else
            error_json "/proc/meminfo not available"
            exit 1
        fi
        ;;

    *)
        error_json "Unexpected subcommand: $SUBCOMMAND"
        exit 1
        ;;

esac

exit 0
