#!/usr/bin/env bash
# ==============================================================================
# adminui-sensors.sh - lm-sensors センサー情報取得ラッパー（読み取り専用）
#
# 使用方法:
#   adminui-sensors.sh all         - 全センサー情報
#   adminui-sensors.sh temperature - 温度センサー
#   adminui-sensors.sh fans        - ファン速度 (RPM)
#   adminui-sensors.sh voltage     - 電圧センサー
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - sensors 未インストール時: /sys/class/thermal/ フォールバック
#   - JSON 形式出力
# ==============================================================================

set -euo pipefail

# ==============================================================================
# 定数
# ==============================================================================

ALLOWED_SUBCOMMANDS=("all" "temperature" "fans" "voltage")

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

# thermal_zone フォールバック: JSON配列を返す
read_thermal_zones() {
    local result="["
    local first=true
    for zone in /sys/class/thermal/thermal_zone*/; do
        if [[ -f "${zone}temp" && -f "${zone}type" ]]; then
            local temp_raw zone_type zone_name temp_c
            temp_raw=$(cat "${zone}temp" 2>/dev/null || echo "0")
            zone_type=$(cat "${zone}type" 2>/dev/null || echo "unknown")
            zone_name=$(basename "$zone")
            temp_c=$(awk "BEGIN {printf \"%.1f\", $temp_raw / 1000}")
            if [[ "$first" == "true" ]]; then
                first=false
            else
                result="${result},"
            fi
            result="${result}{\"zone\":\"${zone_name}\",\"type\":\"${zone_type}\",\"temp_celsius\":${temp_c}}"
        fi
    done
    result="${result}]"
    printf '%s' "$result"
}

# ==============================================================================
# 引数チェック
# ==============================================================================

if [[ $# -lt 1 ]]; then
    error_json "Usage: adminui-sensors.sh <subcommand>"
    exit 1
fi

SUBCOMMAND="$1"

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
    # all: 全センサー情報
    # ------------------------------------------------------------------
    all)
        if ! command -v sensors &>/dev/null; then
            thermal_json=$(read_thermal_zones)
            printf '{"status":"unavailable","message":"lm-sensors not installed","source":"thermal_zone","sensors":{"temperature":%s,"fans":[],"voltage":[]},"timestamp":"%s"}\n' \
                "$thermal_json" "$(timestamp)"
            exit 0
        fi

        sensors_json=$(sensors -j 2>/dev/null || echo "{}")
        printf '{"status":"success","source":"lm-sensors","sensors":%s,"timestamp":"%s"}\n' \
            "$sensors_json" "$(timestamp)"
        ;;

    # ------------------------------------------------------------------
    # temperature: 温度センサー
    # ------------------------------------------------------------------
    temperature)
        if ! command -v sensors &>/dev/null; then
            thermal_json=$(read_thermal_zones)
            printf '{"status":"unavailable","message":"lm-sensors not installed","source":"thermal_zone","temperature":%s,"timestamp":"%s"}\n' \
                "$thermal_json" "$(timestamp)"
            exit 0
        fi

        sensors_json=$(sensors -j 2>/dev/null || echo "{}")
        # Python でフィルタリング（温度フィールドのみ）
        temp_json=$(python3 -c "
import json, sys
data = json.loads('''$sensors_json''')
result = {}
for chip, chip_data in data.items():
    temps = {}
    for feature, fdata in chip_data.items():
        if isinstance(fdata, dict):
            for subf, val in fdata.items():
                if 'temp' in subf.lower() and 'input' in subf.lower():
                    temps[feature] = fdata
                    break
    if temps:
        result[chip] = temps
print(json.dumps(result))
" 2>/dev/null || echo "{}")
        printf '{"status":"success","source":"lm-sensors","temperature":%s,"timestamp":"%s"}\n' \
            "$temp_json" "$(timestamp)"
        ;;

    # ------------------------------------------------------------------
    # fans: ファン速度 (RPM)
    # ------------------------------------------------------------------
    fans)
        if ! command -v sensors &>/dev/null; then
            printf '{"status":"unavailable","message":"lm-sensors not installed","fans":[],"timestamp":"%s"}\n' \
                "$(timestamp)"
            exit 0
        fi

        sensors_json=$(sensors -j 2>/dev/null || echo "{}")
        fans_json=$(python3 -c "
import json, sys
data = json.loads('''$sensors_json''')
result = {}
for chip, chip_data in data.items():
    fans = {}
    for feature, fdata in chip_data.items():
        if isinstance(fdata, dict):
            for subf, val in fdata.items():
                if 'fan' in subf.lower() and 'input' in subf.lower():
                    fans[feature] = fdata
                    break
    if fans:
        result[chip] = fans
print(json.dumps(result))
" 2>/dev/null || echo "{}")
        printf '{"status":"success","source":"lm-sensors","fans":%s,"timestamp":"%s"}\n' \
            "$fans_json" "$(timestamp)"
        ;;

    # ------------------------------------------------------------------
    # voltage: 電圧センサー
    # ------------------------------------------------------------------
    voltage)
        if ! command -v sensors &>/dev/null; then
            printf '{"status":"unavailable","message":"lm-sensors not installed","voltage":[],"timestamp":"%s"}\n' \
                "$(timestamp)"
            exit 0
        fi

        sensors_json=$(sensors -j 2>/dev/null || echo "{}")
        volt_json=$(python3 -c "
import json, sys
data = json.loads('''$sensors_json''')
result = {}
for chip, chip_data in data.items():
    volts = {}
    for feature, fdata in chip_data.items():
        if isinstance(fdata, dict):
            for subf, val in fdata.items():
                if 'in' in subf.lower() and 'input' in subf.lower():
                    volts[feature] = fdata
                    break
    if volts:
        result[chip] = volts
print(json.dumps(result))
" 2>/dev/null || echo "{}")
        printf '{"status":"success","source":"lm-sensors","voltage":%s,"timestamp":"%s"}\n' \
            "$volt_json" "$(timestamp)"
        ;;

    *)
        error_json "Unexpected subcommand: $SUBCOMMAND"
        exit 1
        ;;

esac

exit 0
