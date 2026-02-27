#!/bin/bash
# adminui-bootup.sh - 起動・シャットダウン管理ラッパー
#
# 用途: システムの起動サービス管理・シャットダウン・再起動（allowlist制御）
# 権限: root 権限必要
# 呼び出し: sudo /usr/local/sbin/adminui-bootup.sh <subcommand> [args]
#
# セキュリティ原則:
# - allowlist 方式（許可サブコマンドのみ）
# - シャットダウン/再起動は必ず承認フロー経由で呼び出すこと
# - 入力検証必須（特殊文字拒否）

set -euo pipefail

# ─── ログ ────────────────────────────────────────────────────────
log() {
    logger -t adminui-bootup -p user.info "$*"
    echo "[$(date -Iseconds)] $*" >&2
}

error() {
    logger -t adminui-bootup -p user.err "ERROR: $*"
    echo "[$(date -Iseconds)] ERROR: $*" >&2
}

# ─── 定数 ────────────────────────────────────────────────────────
readonly ALLOWED_SUBCMDS=("status" "services" "enable" "disable" "shutdown" "reboot" "poweroff")

# systemctl enable/disable の allowlist
readonly ALLOWED_SERVICES=(
    "nginx"
    "apache2"
    "postgresql"
    "mysql"
    "redis"
    "ssh"
    "ufw"
    "cron"
    "rsyslog"
    "chrony"
    "ntp"
    "docker"
    "fail2ban"
)

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

validate_service() {
    local svc="$1"
    for allowed in "${ALLOWED_SERVICES[@]}"; do
        [[ "$svc" == "$allowed" ]] && return 0
    done
    error "Service '$svc' is not in allowlist"
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

# JSON 出力ヘルパー
json_ok() {
    printf '{"status":"ok","data":%s}\n' "$1"
}

json_error() {
    printf '{"status":"error","message":"%s"}\n' "$1"
}

# ─── メイン ──────────────────────────────────────────────────────
[[ $# -lt 1 ]] && usage

SUBCMD="$1"
validate_safe_string "$SUBCMD"
validate_subcmd "$SUBCMD"

log "Bootup command: subcmd=$SUBCMD, caller=${SUDO_USER:-$USER}"

case "$SUBCMD" in
    # ── 現在の起動状態（runlevel / systemd target）────────────
    status)
        TARGET=$(systemctl get-default 2>/dev/null || echo "unknown")
        UPTIME=$(uptime -p 2>/dev/null || echo "unknown")
        LAST_BOOT=$(who -b 2>/dev/null | awk '{print $3, $4}' || echo "unknown")
        FAILED_UNITS=$(systemctl --failed --no-legend --no-pager 2>/dev/null | wc -l || echo "0")

        printf '{"status":"ok","data":{"default_target":"%s","uptime":"%s","last_boot":"%s","failed_units":%s}}\n' \
            "$TARGET" "$UPTIME" "$LAST_BOOT" "$FAILED_UNITS"
        ;;

    # ── 起動時に有効化されているサービス一覧 ─────────────────
    services)
        # systemctl list-unit-files で enabled サービス一覧取得
        # JSON形式で出力
        echo '{"status":"ok","data":{"services":['
        FIRST=1
        while IFS= read -r line; do
            UNIT=$(echo "$line" | awk '{print $1}')
            STATE=$(echo "$line" | awk '{print $2}')
            VENDOR=$(echo "$line" | awk '{print $3}')
            # サービス名のみ（.service拡張子除去）
            NAME="${UNIT%.service}"
            if [[ $FIRST -eq 0 ]]; then
                echo ","
            fi
            printf '{"unit":"%s","state":"%s","vendor_preset":"%s"}' \
                "$NAME" "$STATE" "${VENDOR:-}"
            FIRST=0
        done < <(systemctl list-unit-files --type=service --no-legend --no-pager 2>/dev/null | \
                 grep -E "enabled|disabled|static|masked" | head -100)
        echo ']}}'
        ;;

    # ── サービス起動時有効化 ──────────────────────────────────
    enable)
        [[ $# -lt 2 ]] && { error "enable requires service name"; exit 1; }
        SVC="$2"
        validate_safe_string "$SVC"
        validate_service "$SVC"
        if systemctl enable "$SVC" 2>&1; then
            log "Service enabled at boot: $SVC"
            json_ok "\"Service '$SVC' enabled at boot\""
        else
            error "Failed to enable $SVC"
            json_error "Failed to enable $SVC"
            exit 1
        fi
        ;;

    # ── サービス起動時無効化 ──────────────────────────────────
    disable)
        [[ $# -lt 2 ]] && { error "disable requires service name"; exit 1; }
        SVC="$2"
        validate_safe_string "$SVC"
        validate_service "$SVC"
        if systemctl disable "$SVC" 2>&1; then
            log "Service disabled at boot: $SVC"
            json_ok "\"Service '$SVC' disabled at boot\""
        else
            error "Failed to disable $SVC"
            json_error "Failed to disable $SVC"
            exit 1
        fi
        ;;

    # ── シャットダウン（承認フロー必須・Admin のみ） ──────────
    shutdown)
        DELAY="${2:-+1}"  # デフォルト1分後
        # 遅延値の検証（数字またはHH:MM形式）
        if [[ ! "$DELAY" =~ ^(\+[0-9]+|[0-9]{2}:[0-9]{2}|now)$ ]]; then
            error "Invalid shutdown delay: $DELAY (use +N, HH:MM, or now)"
            exit 1
        fi
        log "AUDIT: System shutdown scheduled - delay=$DELAY, caller=${SUDO_USER:-$USER}"
        if shutdown -h "$DELAY" 2>&1; then
            json_ok "\"System shutdown scheduled at $DELAY\""
        else
            json_error "Failed to schedule shutdown"
            exit 1
        fi
        ;;

    # ── 再起動（承認フロー必須・Admin のみ） ────────────────
    reboot)
        DELAY="${2:-+1}"
        if [[ ! "$DELAY" =~ ^(\+[0-9]+|[0-9]{2}:[0-9]{2}|now)$ ]]; then
            error "Invalid reboot delay: $DELAY"
            exit 1
        fi
        log "AUDIT: System reboot scheduled - delay=$DELAY, caller=${SUDO_USER:-$USER}"
        if shutdown -r "$DELAY" 2>&1; then
            json_ok "\"System reboot scheduled at $DELAY\""
        else
            json_error "Failed to schedule reboot"
            exit 1
        fi
        ;;

    # ── 電源OFF（承認フロー必須・Admin のみ） ────────────────
    poweroff)
        log "AUDIT: System poweroff requested - caller=${SUDO_USER:-$USER}"
        if shutdown -P now 2>&1; then
            json_ok "\"System poweroff initiated\""
        else
            json_error "Failed to initiate poweroff"
            exit 1
        fi
        ;;

    *)
        error "Unknown subcommand: $SUBCMD"
        usage
        ;;
esac
