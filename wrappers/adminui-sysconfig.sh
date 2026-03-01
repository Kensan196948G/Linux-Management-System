#!/usr/bin/env bash
# ==============================================================================
# adminui-sysconfig.sh - システム設定情報取得ラッパー（読み取り専用）
#
# 使用方法:
#   adminui-sysconfig.sh hostname  - ホスト名情報
#   adminui-sysconfig.sh timezone  - タイムゾーン情報
#   adminui-sysconfig.sh locale    - ロケール情報
#   adminui-sysconfig.sh kernel    - カーネル情報
#   adminui-sysconfig.sh uptime    - システム稼働時間
#   adminui-sysconfig.sh modules   - カーネルモジュール一覧
#   adminui-sysconfig.sh limits    - システムリソース制限
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - allowlist によるサブコマンド制限
#   - JSON 形式出力
# ==============================================================================

set -euo pipefail

# ==============================================================================
# 定数
# ==============================================================================

ALLOWED_SUBCOMMANDS=("hostname" "timezone" "locale" "kernel" "uptime" "modules" "limits")

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

json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\t'/\\t}"
    printf '%s' "$s"
}

# ==============================================================================
# サブコマンド実装
# ==============================================================================

cmd_hostname() {
    local hostname fqdn short_hostname
    hostname=$(hostname 2>/dev/null || echo "unknown")
    fqdn=$(hostname -f 2>/dev/null || echo "$hostname")
    short_hostname=$(hostname -s 2>/dev/null || echo "$hostname")

    printf '{"status":"success","hostname":"%s","fqdn":"%s","short":"%s","timestamp":"%s"}\n' \
        "$(json_escape "$hostname")" \
        "$(json_escape "$fqdn")" \
        "$(json_escape "$short_hostname")" \
        "$(timestamp)"
}

cmd_timezone() {
    local tz timedatectl_out timezone_file
    timezone_file=""
    if [[ -f /etc/timezone ]]; then
        timezone_file=$(cat /etc/timezone 2>/dev/null || echo "")
    fi

    if command -v timedatectl &>/dev/null; then
        timedatectl_out=$(timedatectl show 2>/dev/null || echo "")
        tz=$(echo "$timedatectl_out" | grep '^Timezone=' | cut -d= -f2 || echo "")
        local ntp local_rtc rtc_in_local_tz
        ntp=$(echo "$timedatectl_out" | grep '^NTP=' | cut -d= -f2 || echo "unknown")
        local_rtc=$(echo "$timedatectl_out" | grep '^LocalRTC=' | cut -d= -f2 || echo "unknown")
        rtc_in_local_tz=$(echo "$timedatectl_out" | grep '^RTCInLocalTZ=' | cut -d= -f2 || echo "unknown")
        printf '{"status":"success","timezone":"%s","timezone_file":"%s","ntp_enabled":"%s","local_rtc":"%s","rtc_in_local_tz":"%s","timestamp":"%s"}\n' \
            "$(json_escape "${tz:-unknown}")" \
            "$(json_escape "$timezone_file")" \
            "$(json_escape "$ntp")" \
            "$(json_escape "$local_rtc")" \
            "$(json_escape "$rtc_in_local_tz")" \
            "$(timestamp)"
    else
        tz="${timezone_file:-unknown}"
        printf '{"status":"success","timezone":"%s","timezone_file":"%s","ntp_enabled":"unknown","local_rtc":"unknown","rtc_in_local_tz":"unknown","timestamp":"%s"}\n' \
            "$(json_escape "$tz")" \
            "$(json_escape "$timezone_file")" \
            "$(timestamp)"
    fi
}

cmd_locale() {
    local locale_out lang language lc_all lc_ctype lc_messages charmap
    lang="" language="" lc_all="" lc_ctype="" lc_messages="" charmap=""

    if command -v localectl &>/dev/null; then
        locale_out=$(localectl status 2>/dev/null || echo "")
        lang=$(echo "$locale_out" | grep 'LANG=' | sed 's/.*LANG=//' | awk '{print $1}' || echo "")
        lc_ctype=$(echo "$locale_out" | grep 'LC_CTYPE=' | sed 's/.*LC_CTYPE=//' | awk '{print $1}' || echo "")
        lc_messages=$(echo "$locale_out" | grep 'LC_MESSAGES=' | sed 's/.*LC_MESSAGES=//' | awk '{print $1}' || echo "")
    fi

    # /etc/locale.gen または /etc/default/locale からのフォールバック
    if [[ -z "$lang" && -f /etc/default/locale ]]; then
        lang=$(grep '^LANG=' /etc/default/locale 2>/dev/null | cut -d= -f2 | tr -d '"' || echo "")
    fi

    charmap=$(locale charmap 2>/dev/null || echo "")

    printf '{"status":"success","lang":"%s","lc_ctype":"%s","lc_messages":"%s","charmap":"%s","timestamp":"%s"}\n' \
        "$(json_escape "${lang:-unknown}")" \
        "$(json_escape "${lc_ctype:-}")" \
        "$(json_escape "${lc_messages:-}")" \
        "$(json_escape "${charmap:-}")" \
        "$(timestamp)"
}

cmd_kernel() {
    local uname_a version_file
    uname_a=$(uname -a 2>/dev/null || echo "unknown")
    version_file=""
    if [[ -f /proc/version ]]; then
        version_file=$(cat /proc/version 2>/dev/null || echo "")
    fi

    local kernel_name kernel_release kernel_version machine
    kernel_name=$(uname -s 2>/dev/null || echo "")
    kernel_release=$(uname -r 2>/dev/null || echo "")
    kernel_version=$(uname -v 2>/dev/null || echo "")
    machine=$(uname -m 2>/dev/null || echo "")

    printf '{"status":"success","uname":"%s","kernel_name":"%s","kernel_release":"%s","kernel_version":"%s","machine":"%s","proc_version":"%s","timestamp":"%s"}\n' \
        "$(json_escape "$uname_a")" \
        "$(json_escape "$kernel_name")" \
        "$(json_escape "$kernel_release")" \
        "$(json_escape "$kernel_version")" \
        "$(json_escape "$machine")" \
        "$(json_escape "$version_file")" \
        "$(timestamp)"
}

cmd_uptime() {
    local uptime_out proc_uptime uptime_seconds
    uptime_out=$(uptime 2>/dev/null || echo "unknown")
    proc_uptime=""
    uptime_seconds=""
    if [[ -f /proc/uptime ]]; then
        proc_uptime=$(cat /proc/uptime 2>/dev/null || echo "")
        uptime_seconds=$(echo "$proc_uptime" | awk '{print $1}' || echo "")
    fi

    # load average
    local load_1 load_5 load_15
    load_1="" load_5="" load_15=""
    if [[ -f /proc/loadavg ]]; then
        read -r load_1 load_5 load_15 _ _ < /proc/loadavg 2>/dev/null || true
    fi

    printf '{"status":"success","uptime_string":"%s","uptime_seconds":"%s","load_1min":"%s","load_5min":"%s","load_15min":"%s","timestamp":"%s"}\n' \
        "$(json_escape "$uptime_out")" \
        "$(json_escape "${uptime_seconds:-}")" \
        "$(json_escape "${load_1:-}")" \
        "$(json_escape "${load_5:-}")" \
        "$(json_escape "${load_15:-}")" \
        "$(timestamp)"
}

cmd_modules() {
    local lsmod_out
    lsmod_out=$(lsmod 2>/dev/null || echo "")

    # lsmod の出力を JSON 配列に変換
    local modules_json="["
    local first=true
    while IFS= read -r line; do
        # ヘッダー行をスキップ
        [[ "$line" =~ ^Module ]] && continue
        [[ -z "$line" ]] && continue

        local mod_name mod_size mod_used
        mod_name=$(echo "$line" | awk '{print $1}')
        mod_size=$(echo "$line" | awk '{print $2}')
        mod_used=$(echo "$line" | awk '{print $3}')

        [[ -z "$mod_name" ]] && continue

        if [[ "$first" == "true" ]]; then
            first=false
        else
            modules_json="${modules_json},"
        fi
        modules_json="${modules_json}{\"name\":\"$(json_escape "$mod_name")\",\"size\":\"$(json_escape "$mod_size")\",\"used\":\"$(json_escape "$mod_used")\"}"
    done <<< "$lsmod_out"
    modules_json="${modules_json}]"

    printf '{"status":"success","modules":%s,"timestamp":"%s"}\n' \
        "$modules_json" \
        "$(timestamp)"
}

cmd_limits() {
    local limits_out
    limits_out=$(ulimit -a 2>/dev/null || echo "")

    printf '{"status":"success","limits":"%s","timestamp":"%s"}\n' \
        "$(json_escape "$limits_out")" \
        "$(timestamp)"
}

# ==============================================================================
# メイン処理
# ==============================================================================

SUBCOMMAND="${1:-}"

# allowlist チェック
allowed=false
for cmd in "${ALLOWED_SUBCOMMANDS[@]}"; do
    if [[ "$SUBCOMMAND" == "$cmd" ]]; then
        allowed=true
        break
    fi
done

if [[ "$allowed" != "true" ]]; then
    error_json "Unknown subcommand: ${SUBCOMMAND}. Allowed: ${ALLOWED_SUBCOMMANDS[*]}"
    exit 1
fi

case "$SUBCOMMAND" in
    hostname) cmd_hostname ;;
    timezone) cmd_timezone ;;
    locale)   cmd_locale ;;
    kernel)   cmd_kernel ;;
    uptime)   cmd_uptime ;;
    modules)  cmd_modules ;;
    limits)   cmd_limits ;;
esac
