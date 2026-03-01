#!/bin/bash
# adminui-time.sh - システム時刻・タイムゾーン管理ラッパー
#
# 用途: システム時刻・タイムゾーンの参照・設定（allowlist制御）
# 権限: set-timezone のみ root 権限必要（timedatectl set-timezone）
# 呼び出し: sudo /usr/local/sbin/adminui-time.sh <subcommand> [args]
#
# セキュリティ原則:
# - allowlist 方式（許可サブコマンドのみ）
# - タイムゾーン名は zoneinfo ファイルの存在確認で検証
# - 特殊文字チェック必須

set -euo pipefail

# ─── ログ ────────────────────────────────────────────────────────
log() {
    logger -t adminui-time -p user.info "$*"
    echo "[$(date -Iseconds)] $*" >&2
}

error() {
    logger -t adminui-time -p user.err "ERROR: $*"
    echo "[$(date -Iseconds)] ERROR: $*" >&2
}

# ─── 定数 ────────────────────────────────────────────────────────
readonly ALLOWED_SUBCMDS=("status" "list-timezones" "set-timezone" "ntp-servers" "sync-status" "current-time" "timezones")
readonly ZONEINFO_DIR="/usr/share/zoneinfo"

# ─── ヘルパー ────────────────────────────────────────────────────
usage() {
    echo "Usage: $0 <subcommand> [args]" >&2
    echo "Subcommands: ${ALLOWED_SUBCMDS[*]}" >&2
    exit 1
}

validate_subcmd() {
    local cmd="$1"
    for allowed in "${ALLOWED_SUBCMDS[@]}"; do
        [[ "$cmd" == "$allowed" ]] && return 0
    done
    error "Subcommand '$cmd' is not allowed"
    exit 1
}

validate_safe_string() {
    local input="$1"
    if [[ "$input" =~ [[:space:]\;\|\&\$\(\)\`\>\<\*\?\{\}\[\]] ]]; then
        error "Unsafe characters in input: $input"
        log "SECURITY: Injection attempt detected - input=$input, caller=${SUDO_USER:-$USER}"
        exit 1
    fi
}

# タイムゾーン名の検証
# - 英数字・スラッシュ・アンダースコア・ハイフン・ドットのみ許可
# - zoneinfo ファイルの存在確認（パストラバーサル対策）
validate_timezone() {
    local tz="$1"

    # 書式チェック（例: Asia/Tokyo, UTC, US/Eastern）
    if [[ ! "$tz" =~ ^[A-Za-z0-9/_+-]+$ ]]; then
        error "Invalid timezone format: $tz"
        exit 1
    fi

    # パストラバーサル防止（".." を含まないこと）
    if [[ "$tz" == *".."* ]]; then
        error "Path traversal attempt in timezone: $tz"
        log "SECURITY: Path traversal attempt - tz=$tz, caller=${SUDO_USER:-$USER}"
        exit 1
    fi

    # zoneinfo ファイルの存在確認
    local tz_path="${ZONEINFO_DIR}/${tz}"
    if [[ ! -f "$tz_path" ]]; then
        error "Timezone not found: $tz (path: $tz_path)"
        exit 1
    fi
}

# ─── メイン ──────────────────────────────────────────────────────
[[ $# -lt 1 ]] && usage

SUBCMD="$1"
validate_safe_string "$SUBCMD"
validate_subcmd "$SUBCMD"

log "Time command: subcmd=$SUBCMD, caller=${SUDO_USER:-$USER}"

case "$SUBCMD" in
    # ── 現在の時刻・NTP 状態 ────────────────────────────────
    status)
        # timedatectl show で JSON 互換の情報取得
        if command -v timedatectl &>/dev/null; then
            LOCAL_TIME=$(timedatectl show --property=TimeUSec --value 2>/dev/null || echo "")
            TIMEZONE=$(timedatectl show --property=Timezone --value 2>/dev/null || echo "")
            NTP_SYNC=$(timedatectl show --property=NTPSynchronized --value 2>/dev/null || echo "no")
            NTP_SERVICE=$(timedatectl show --property=NTPService --value 2>/dev/null || echo "")
            RTC_TIME=$(timedatectl show --property=RTCTimeUSec --value 2>/dev/null || echo "")
            SYSTEM_TIME=$(date -Iseconds 2>/dev/null || echo "")
            UTC_TIME=$(date -u -Iseconds 2>/dev/null || echo "")
        else
            TIMEZONE=$(cat /etc/timezone 2>/dev/null || echo "UTC")
            SYSTEM_TIME=$(date -Iseconds 2>/dev/null || echo "")
            UTC_TIME=$(date -u -Iseconds 2>/dev/null || echo "")
            NTP_SYNC="unknown"
            NTP_SERVICE=""
            LOCAL_TIME=""
            RTC_TIME=""
        fi

        printf '{"status":"ok","data":{"system_time":"%s","utc_time":"%s","timezone":"%s","ntp_synchronized":"%s","ntp_service":"%s","rtc_time":"%s"}}\n' \
            "$SYSTEM_TIME" "$UTC_TIME" "$TIMEZONE" "$NTP_SYNC" "$NTP_SERVICE" "$RTC_TIME"
        ;;

    # ── 利用可能なタイムゾーン一覧 ──────────────────────────
    list-timezones)
        if command -v timedatectl &>/dev/null; then
            echo '{"status":"ok","data":{"timezones":['
            FIRST=1
            while IFS= read -r tz; do
                [[ -z "$tz" ]] && continue
                if [[ $FIRST -eq 0 ]]; then printf ','; fi
                printf '"%s"' "$tz"
                FIRST=0
            done < <(timedatectl list-timezones 2>/dev/null)
            echo ']}}'
        else
            # timedatectl がない場合は zoneinfo から取得
            echo '{"status":"ok","data":{"timezones":['
            FIRST=1
            while IFS= read -r f; do
                tz="${f#${ZONEINFO_DIR}/}"
                if [[ $FIRST -eq 0 ]]; then printf ','; fi
                printf '"%s"' "$tz"
                FIRST=0
            done < <(find "$ZONEINFO_DIR" -type f -not -path "*/right/*" -not -path "*/posix/*" | sort | head -600)
            echo ']}}'
        fi
        ;;

    # ── タイムゾーン設定（承認フロー必須・Admin のみ） ───────
    set-timezone)
        [[ $# -lt 2 ]] && { error "set-timezone requires timezone argument"; exit 1; }
        TZ="$2"
        validate_safe_string "$TZ"
        validate_timezone "$TZ"

        log "AUDIT: Timezone change requested - tz=$TZ, caller=${SUDO_USER:-$USER}"

        if timedatectl set-timezone "$TZ" 2>&1; then
            CURRENT_TZ=$(timedatectl show --property=Timezone --value 2>/dev/null || echo "$TZ")
            log "Timezone changed successfully: $TZ"
            printf '{"status":"ok","data":{"message":"Timezone set to %s","timezone":"%s"}}\n' "$TZ" "$CURRENT_TZ"
        else
            error "Failed to set timezone: $TZ"
            printf '{"status":"error","message":"Failed to set timezone to %s"}\n' "$TZ"
            exit 1
        fi
        ;;

    # ── NTP サーバー一覧 (chrony / ntpd) ────────────────────────
    ntp-servers)
        if command -v chronyc &>/dev/null; then
            OUTPUT=$(chronyc sources 2>/dev/null || echo "chrony not running")
        elif command -v ntpq &>/dev/null; then
            OUTPUT=$(ntpq -p 2>/dev/null || echo "ntpd not running")
        else
            OUTPUT="No NTP client found"
        fi
        printf '{"status":"ok","data":{"output":"%s"}}\n' "$(echo "$OUTPUT" | sed 's/"/\\"/g' | tr '\n' '|')"
        ;;

    # ── 時刻同期状態（詳細） ─────────────────────────────────
    sync-status)
        if command -v timedatectl &>/dev/null; then
            SYNC_OUT=$(timedatectl show 2>/dev/null || timedatectl status 2>/dev/null || date)
        else
            SYNC_OUT=$(date)
        fi
        printf '{"status":"ok","data":{"output":"%s"}}\n' "$(echo "$SYNC_OUT" | sed 's/"/\\"/g' | tr '\n' '|')"
        ;;

    # ── 現在時刻（簡易） ─────────────────────────────────────
    current-time)
        SYSTEM_TIME=$(date -Iseconds 2>/dev/null || date)
        UTC_TIME=$(date -u -Iseconds 2>/dev/null || date -u)
        printf '{"status":"ok","data":{"system_time":"%s","utc_time":"%s"}}\n' "$SYSTEM_TIME" "$UTC_TIME"
        ;;

    # ── タイムゾーン一覧（timezones エイリアス） ─────────────
    timezones)
        if command -v timedatectl &>/dev/null; then
            echo '{"status":"ok","data":{"timezones":['
            FIRST=1
            while IFS= read -r tz; do
                [[ -z "$tz" ]] && continue
                if [[ $FIRST -eq 0 ]]; then printf ','; fi
                printf '"%s"' "$tz"
                FIRST=0
            done < <(timedatectl list-timezones 2>/dev/null)
            echo ']}}'
        else
            echo '{"status":"ok","data":{"timezones":['
            FIRST=1
            while IFS= read -r f; do
                tz="${f#${ZONEINFO_DIR}/}"
                if [[ $FIRST -eq 0 ]]; then printf ','; fi
                printf '"%s"' "$tz"
                FIRST=0
            done < <(find "$ZONEINFO_DIR" -type f -not -path "*/right/*" -not -path "*/posix/*" | sort | head -600)
            echo ']}}'
        fi
        ;;

    *)
        error "Unknown subcommand: $SUBCMD"
        usage
        ;;
esac
