#!/bin/bash
# adminui-cron-toggle.sh - Cron ジョブ有効/無効切替ラッパー
#
# 用途: ユーザーのcrontab内の指定ジョブを有効化/無効化
# 権限: root権限必要（crontab -u による他ユーザー操作）
# 呼び出し: sudo /usr/local/sbin/adminui-cron-toggle.sh <username> <line_number> <enable|disable>
#
# セキュリティ原則:
# - enable時: allowlist再検証、ジョブ数上限チェック、スケジュール再検証
# - disable時: adminuiコメント形式でコメントアウト
# - 安全な一時ファイル処理（mktemp + trap）

set -euo pipefail

# ===================================================================
# 定数定義
# ===================================================================

MAX_JOBS=10

FORBIDDEN_CHARS=(';' '|' '&' '$' '(' ')' '`' '>' '<' '*' '?' '{' '}' '[' ']')

FORBIDDEN_USERNAMES=(
    'root' 'bin' 'daemon' 'sys' 'sync' 'games' 'man' 'lp'
    'mail' 'news' 'uucp' 'proxy' 'backup' 'list' 'irc'
    'gnats' 'nobody' '_apt' 'messagebus'
    'www-data' 'sshd' 'systemd-network' 'systemd-resolve'
    'systemd-timesync' 'syslog' 'uuidd' 'tcpdump'
    'admin' 'administrator' 'sudo' 'wheel' 'operator'
    'adm' 'staff' 'adminui' 'svc-adminui'
    'postgres' 'mysql' 'redis' 'nginx' 'apache'
    'docker' 'containerd'
)

ALLOWED_COMMANDS=(
    "/usr/bin/rsync"
    "/usr/local/bin/healthcheck.sh"
    "/usr/bin/find"
    "/usr/bin/tar"
    "/usr/bin/gzip"
    "/usr/bin/curl"
    "/usr/bin/wget"
    "/usr/bin/python3"
    "/usr/bin/node"
)

# ===================================================================
# ログ関数
# ===================================================================

log_info() {
    logger -t adminui-cron-toggle -p user.info "$*"
}

log_error() {
    logger -t adminui-cron-toggle -p user.err "ERROR: $*"
}

log_security() {
    logger -t adminui-cron-toggle -p user.warning "SECURITY: $*"
}

# ===================================================================
# JSON出力ヘルパー
# ===================================================================

json_error() {
    local code="$1"
    local message="$2"
    echo "{\"status\":\"error\",\"code\":\"${code}\",\"message\":\"${message}\"}"
    exit 1
}

json_escape() {
    local str="$1"
    str="${str//\\/\\\\}"
    str="${str//\"/\\\"}"
    str="${str//$'\n'/\\n}"
    str="${str//$'\r'/\\r}"
    str="${str//$'\t'/\\t}"
    echo -n "$str"
}

# ===================================================================
# 入力検証: 禁止文字チェック
# ===================================================================

check_forbidden_chars() {
    local input="$1"
    local field_name="$2"
    for char in "${FORBIDDEN_CHARS[@]}"; do
        if [[ "$input" == *"$char"* ]]; then
            log_security "Forbidden character '${char}' in ${field_name}, caller=${SUDO_USER:-$USER}"
            json_error "FORBIDDEN_CHARS" "Forbidden character in ${field_name}: ${char}"
        fi
    done
}

# ===================================================================
# スケジュール再検証（enable時）
# ===================================================================

validate_schedule() {
    local schedule="$1"

    local fields
    IFS=' ' read -ra fields <<< "$schedule"
    if [[ ${#fields[@]} -ne 5 ]]; then
        return 1
    fi

    local minute="${fields[0]}"

    # 最小間隔チェック
    if [[ "$minute" == "*" ]] || [[ "$minute" =~ ^\*/[1-4]$ ]]; then
        return 1
    fi

    return 0
}

# ===================================================================
# メイン処理
# ===================================================================

# 1. 引数チェック（正確に3個）
if [[ $# -ne 3 ]]; then
    log_error "Invalid number of arguments: expected 3, got $#"
    json_error "INVALID_ARGS" "Usage: adminui-cron-toggle.sh <username> <line_number> <enable|disable>"
fi

USERNAME="$1"
LINE_NUMBER="$2"
ACTION="$3"

log_info "Cron toggle requested: user=${USERNAME}, line=${LINE_NUMBER}, action=${ACTION}, caller=${SUDO_USER:-$USER}"

# 2. ユーザー名検証
if [[ -z "$USERNAME" ]]; then
    log_error "Empty username"
    json_error "INVALID_USERNAME" "Invalid username format"
fi

check_forbidden_chars "$USERNAME" "username"

if [[ ! "$USERNAME" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then
    log_error "Invalid username format: ${USERNAME}"
    json_error "INVALID_USERNAME" "Invalid username format"
fi

for forbidden in "${FORBIDDEN_USERNAMES[@]}"; do
    if [[ "$USERNAME" == "$forbidden" ]]; then
        log_error "Forbidden system user: ${USERNAME}"
        json_error "FORBIDDEN_USER" "System user not allowed: ${USERNAME}"
    fi
done

if ! id -u "$USERNAME" >/dev/null 2>&1; then
    log_error "User does not exist: ${USERNAME}"
    json_error "USER_NOT_FOUND" "User does not exist: ${USERNAME}"
fi

# 3. 行番号検証
if [[ ! "$LINE_NUMBER" =~ ^[1-9][0-9]{0,3}$ ]]; then
    log_error "Invalid line number: ${LINE_NUMBER}"
    json_error "INVALID_LINE_NUMBER" "Invalid line number: ${LINE_NUMBER}"
fi

# 4. アクション検証
if [[ "$ACTION" != "enable" && "$ACTION" != "disable" ]]; then
    log_error "Invalid action: ${ACTION}"
    json_error "INVALID_ACTION" "Invalid action: ${ACTION} (expected: enable or disable)"
fi

# 5. crontab取得
CRONTAB_CONTENT=""
if ! CRONTAB_CONTENT=$(crontab -u "$USERNAME" -l 2>/dev/null); then
    log_error "No crontab for user=${USERNAME}"
    json_error "LINE_NOT_FOUND" "Line ${LINE_NUMBER} does not exist (no crontab set)"
fi

# 6. 総行数確認
TOTAL_LINES=$(echo "$CRONTAB_CONTENT" | wc -l)
if [[ $LINE_NUMBER -gt $TOTAL_LINES ]]; then
    log_error "Line ${LINE_NUMBER} out of range for user=${USERNAME} (total: ${TOTAL_LINES})"
    json_error "LINE_NOT_FOUND" "Line ${LINE_NUMBER} does not exist (total lines: ${TOTAL_LINES})"
fi

# 7. 指定行の取得
TARGET_LINE=$(echo "$CRONTAB_CONTENT" | sed -n "${LINE_NUMBER}p")

if [[ -z "$TARGET_LINE" ]]; then
    log_error "Line ${LINE_NUMBER} is empty"
    json_error "NOT_A_JOB" "Line ${LINE_NUMBER} is empty, not a cron job"
fi

# ===================================================================
# DISABLE処理
# ===================================================================

if [[ "$ACTION" == "disable" ]]; then
    # 既にDISABLED済みかチェック
    if [[ "$TARGET_LINE" =~ ^#\ \[DISABLED\ by\ adminui ]]; then
        log_error "Line ${LINE_NUMBER} is already disabled"
        json_error "ALREADY_DISABLED" "Job is already disabled"
    fi

    # コメント行・環境変数行のチェック
    if [[ "$TARGET_LINE" =~ ^# ]] || [[ "$TARGET_LINE" =~ ^[A-Z_]+=.* ]]; then
        log_error "Line ${LINE_NUMBER} is not a cron job"
        json_error "NOT_A_JOB" "Line ${LINE_NUMBER} is a comment or system directive, not a cron job"
    fi

    # ジョブ行であることの確認
    if [[ ! "$TARGET_LINE" =~ ^[0-9\*\/\,\-]+[[:space:]] ]]; then
        log_error "Line ${LINE_NUMBER} is not a valid cron job"
        json_error "NOT_A_JOB" "Line ${LINE_NUMBER} is not a valid cron job"
    fi

    # ジョブ行のパース
    SCHEDULE=""
    COMMAND=""
    if [[ "$TARGET_LINE" =~ ^([0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+)[[:space:]]+(/[^[:space:]]+) ]]; then
        SCHEDULE="${BASH_REMATCH[1]}"
        COMMAND="${BASH_REMATCH[2]}"
    fi

    # コメントアウト
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    CALLER="${SUDO_USER:-$USER}"
    NEW_LINE="# [DISABLED by adminui ${TIMESTAMP} caller=${CALLER}] ${TARGET_LINE}"

    # 安全な一時ファイル作成
    TMPFILE=$(mktemp /tmp/adminui-cron-XXXXXX)
    trap 'rm -f "$TMPFILE"' EXIT
    chmod 600 "$TMPFILE"

    CURRENT_LINE=0
    while IFS= read -r line; do
        CURRENT_LINE=$((CURRENT_LINE + 1))
        if [[ $CURRENT_LINE -eq $LINE_NUMBER ]]; then
            echo "$NEW_LINE" >> "$TMPFILE"
        else
            echo "$line" >> "$TMPFILE"
        fi
    done <<< "$CRONTAB_CONTENT"

    if ! crontab -u "$USERNAME" "$TMPFILE" 2>/dev/null; then
        log_error "Failed to install crontab for user=${USERNAME}"
        json_error "CRONTAB_INSTALL_FAILED" "Failed to install crontab"
    fi

    ACTIVE_JOBS=$(crontab -u "$USERNAME" -l 2>/dev/null | grep -cE '^[0-9\*]' || true)

    ESCAPED_SCHEDULE=$(json_escape "$SCHEDULE")
    ESCAPED_COMMAND=$(json_escape "$COMMAND")

    log_info "Cron toggle successful: user=${USERNAME}, line=${LINE_NUMBER}, action=disable"

    echo "{\"status\":\"success\",\"message\":\"Cron job disabled\",\"user\":\"${USERNAME}\",\"job\":{\"line_number\":${LINE_NUMBER},\"schedule\":\"${ESCAPED_SCHEDULE}\",\"command\":\"${ESCAPED_COMMAND}\",\"enabled\":false},\"active_jobs\":${ACTIVE_JOBS}}"
    exit 0
fi

# ===================================================================
# ENABLE処理
# ===================================================================

# adminuiコメント形式であることの確認
if [[ ! "$TARGET_LINE" =~ ^#\ \[DISABLED\ by\ adminui\ .+\]\ (.+)$ ]]; then
    # 通常のコメント行なら拒否
    if [[ "$TARGET_LINE" =~ ^# ]]; then
        log_error "Line ${LINE_NUMBER} is not an adminui-disabled comment"
        json_error "NOT_ADMINUI_COMMENT" "Line ${LINE_NUMBER} was not disabled by adminui (cannot re-enable unknown comments)"
    fi
    # 既に有効なジョブ行なら拒否
    if [[ "$TARGET_LINE" =~ ^[0-9\*\/\,\-]+[[:space:]] ]]; then
        log_error "Line ${LINE_NUMBER} is already enabled"
        json_error "ALREADY_ENABLED" "Job is already enabled"
    fi
    # その他
    log_error "Line ${LINE_NUMBER} is not a valid target for enable"
    json_error "NOT_A_JOB" "Line ${LINE_NUMBER} is not a valid cron job"
fi

# コメントプレフィクスを除去してジョブ内容を取得
JOB_LINE="${BASH_REMATCH[1]}"

# ジョブ行のパース
SCHEDULE=""
COMMAND=""
if [[ "$JOB_LINE" =~ ^([0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+)[[:space:]]+(/[^[:space:]]+) ]]; then
    SCHEDULE="${BASH_REMATCH[1]}"
    COMMAND="${BASH_REMATCH[2]}"
else
    log_error "Cannot parse disabled job line: ${JOB_LINE}"
    json_error "PARSE_ERROR" "Cannot parse the disabled job content"
fi

# コマンドのallowlist再検証
COMMAND_ALLOWED=false
for allowed_cmd in "${ALLOWED_COMMANDS[@]}"; do
    if [[ "$COMMAND" == "$allowed_cmd" ]]; then
        COMMAND_ALLOWED=true
        break
    fi
done

if [[ "$COMMAND_ALLOWED" == "false" ]]; then
    log_error "Cannot enable: command ${COMMAND} not in current allowlist"
    json_error "COMMAND_NOT_ALLOWED" "Cannot re-enable: command ${COMMAND} is no longer in allowlist"
fi

# スケジュールの再検証
if ! validate_schedule "$SCHEDULE"; then
    log_error "Cannot enable: invalid schedule ${SCHEDULE}"
    json_error "INVALID_SCHEDULE" "Cannot re-enable: schedule no longer meets validation rules"
fi

# 有効ジョブ数の上限チェック
ACTIVE_JOBS=$(echo "$CRONTAB_CONTENT" | grep -cE '^[0-9\*]' || true)
if [[ $ACTIVE_JOBS -ge $MAX_JOBS ]]; then
    log_error "Cannot enable: max jobs exceeded (current: ${ACTIVE_JOBS}, max: ${MAX_JOBS})"
    json_error "MAX_JOBS_EXCEEDED" "Cannot enable: maximum ${MAX_JOBS} active jobs (current: ${ACTIVE_JOBS})"
fi

# コメント解除
TMPFILE=$(mktemp /tmp/adminui-cron-XXXXXX)
trap 'rm -f "$TMPFILE"' EXIT
chmod 600 "$TMPFILE"

CURRENT_LINE=0
while IFS= read -r line; do
    CURRENT_LINE=$((CURRENT_LINE + 1))
    if [[ $CURRENT_LINE -eq $LINE_NUMBER ]]; then
        echo "$JOB_LINE" >> "$TMPFILE"
    else
        echo "$line" >> "$TMPFILE"
    fi
done <<< "$CRONTAB_CONTENT"

if ! crontab -u "$USERNAME" "$TMPFILE" 2>/dev/null; then
    log_error "Failed to install crontab for user=${USERNAME}"
    json_error "CRONTAB_INSTALL_FAILED" "Failed to install crontab"
fi

NEW_ACTIVE_JOBS=$((ACTIVE_JOBS + 1))

ESCAPED_SCHEDULE=$(json_escape "$SCHEDULE")
ESCAPED_COMMAND=$(json_escape "$COMMAND")

log_info "Cron toggle successful: user=${USERNAME}, line=${LINE_NUMBER}, action=enable"

echo "{\"status\":\"success\",\"message\":\"Cron job enabled\",\"user\":\"${USERNAME}\",\"job\":{\"line_number\":${LINE_NUMBER},\"schedule\":\"${ESCAPED_SCHEDULE}\",\"command\":\"${ESCAPED_COMMAND}\",\"enabled\":true},\"active_jobs\":${NEW_ACTIVE_JOBS}}"
exit 0
