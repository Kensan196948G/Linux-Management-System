#!/bin/bash
# adminui-cron-remove.sh - Cron ジョブ削除（コメントアウト）ラッパー
#
# 用途: ユーザーのcrontabから指定行のジョブをコメントアウト（物理削除ではない）
# 権限: root権限必要（crontab -u による他ユーザー操作）
# 呼び出し: sudo /usr/local/sbin/adminui-cron-remove.sh <username> <line_number>
#
# セキュリティ原則:
# - 物理削除ではなくコメントアウト方式（復元可能、監査証跡）
# - 安全な一時ファイル処理（mktemp + trap）
# - 行番号で指定（内容ベースではインジェクションリスクあり）

set -euo pipefail

# ===================================================================
# 定数定義
# ===================================================================

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

# ===================================================================
# ログ関数
# ===================================================================

log_info() {
    logger -t adminui-cron-remove -p user.info "$*"
}

log_error() {
    logger -t adminui-cron-remove -p user.err "ERROR: $*"
}

log_security() {
    logger -t adminui-cron-remove -p user.warning "SECURITY: $*"
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
# メイン処理
# ===================================================================

# 1. 引数チェック（正確に2個）
if [[ $# -ne 2 ]]; then
    log_error "Invalid number of arguments: expected 2, got $#"
    json_error "INVALID_ARGS" "Usage: adminui-cron-remove.sh <username> <line_number>"
fi

USERNAME="$1"
LINE_NUMBER="$2"

log_info "Cron remove requested: user=${USERNAME}, line=${LINE_NUMBER}, caller=${SUDO_USER:-$USER}"

# 2. ユーザー名検証
# 2a. 空文字チェック
if [[ -z "$USERNAME" ]]; then
    log_error "Empty username"
    json_error "INVALID_USERNAME" "Invalid username format"
fi

# 2b. 禁止文字チェック
check_forbidden_chars "$USERNAME" "username"

# 2c. パターン照合
if [[ ! "$USERNAME" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then
    log_error "Invalid username format: ${USERNAME}"
    json_error "INVALID_USERNAME" "Invalid username format"
fi

# 2d. 禁止ユーザーチェック
for forbidden in "${FORBIDDEN_USERNAMES[@]}"; do
    if [[ "$USERNAME" == "$forbidden" ]]; then
        log_error "Forbidden system user: ${USERNAME}"
        json_error "FORBIDDEN_USER" "System user not allowed: ${USERNAME}"
    fi
done

# 2e. ユーザー存在確認
if ! id -u "$USERNAME" >/dev/null 2>&1; then
    log_error "User does not exist: ${USERNAME}"
    json_error "USER_NOT_FOUND" "User does not exist: ${USERNAME}"
fi

# 3. 行番号検証
# 3a. 正の整数チェック
if [[ ! "$LINE_NUMBER" =~ ^[1-9][0-9]{0,3}$ ]]; then
    log_error "Invalid line number: ${LINE_NUMBER}"
    json_error "INVALID_LINE_NUMBER" "Invalid line number: ${LINE_NUMBER}"
fi

# 4. crontab取得
CRONTAB_CONTENT=""
if ! CRONTAB_CONTENT=$(crontab -u "$USERNAME" -l 2>/dev/null); then
    log_error "No crontab for user=${USERNAME}"
    json_error "LINE_NOT_FOUND" "Line ${LINE_NUMBER} does not exist (no crontab set)"
fi

# 5. 総行数確認
TOTAL_LINES=$(echo "$CRONTAB_CONTENT" | wc -l)
if [[ $LINE_NUMBER -gt $TOTAL_LINES ]]; then
    log_error "Line ${LINE_NUMBER} out of range for user=${USERNAME} (total: ${TOTAL_LINES})"
    json_error "LINE_NOT_FOUND" "Line ${LINE_NUMBER} does not exist (total lines: ${TOTAL_LINES})"
fi

# 6. 指定行の取得・検証
TARGET_LINE=$(echo "$CRONTAB_CONTENT" | sed -n "${LINE_NUMBER}p")

# 6a. 空行チェック
if [[ -z "$TARGET_LINE" ]]; then
    log_error "Line ${LINE_NUMBER} is empty"
    json_error "NOT_A_JOB" "Line ${LINE_NUMBER} is empty, not a cron job"
fi

# 6b. 既にadminuiによりDISABLED済みかチェック
if [[ "$TARGET_LINE" =~ ^#\ \[DISABLED\ by\ adminui ]]; then
    log_error "Line ${LINE_NUMBER} is already disabled"
    json_error "ALREADY_DISABLED" "Line ${LINE_NUMBER} is already disabled"
fi

# 6c. 通常のコメント行/環境変数行チェック
if [[ "$TARGET_LINE" =~ ^# ]] || [[ "$TARGET_LINE" =~ ^[A-Z_]+=.* ]]; then
    log_error "Line ${LINE_NUMBER} is a comment or system directive"
    json_error "NOT_A_JOB" "Line ${LINE_NUMBER} is a comment or system directive, not a cron job"
fi

# 6d. ジョブ行であることの確認
if [[ ! "$TARGET_LINE" =~ ^[0-9\*\/\,\-]+[[:space:]] ]]; then
    log_error "Line ${LINE_NUMBER} is not a valid cron job"
    json_error "NOT_A_JOB" "Line ${LINE_NUMBER} is not a valid cron job"
fi

# 7. ジョブ行のパース（出力用）
SCHEDULE=""
COMMAND=""
ARGUMENTS=""
if [[ "$TARGET_LINE" =~ ^([0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+)[[:space:]]+(/[^[:space:]]+)(.*)?$ ]]; then
    SCHEDULE="${BASH_REMATCH[1]}"
    COMMAND="${BASH_REMATCH[2]}"
    REST="${BASH_REMATCH[3]}"
    if [[ -n "$REST" ]]; then
        # インラインコメントを除去
        ARGUMENTS=$(echo "$REST" | sed 's/[[:space:]]#[[:space:]].*$//' | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
    fi
fi

# 8. コメントアウト処理
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
CALLER="${SUDO_USER:-$USER}"
DISABLED_PREFIX="# [DISABLED by adminui ${TIMESTAMP} caller=${CALLER}] "

# 安全な一時ファイル作成
TMPFILE=$(mktemp /tmp/adminui-cron-XXXXXX)
trap 'rm -f "$TMPFILE"' EXIT
chmod 600 "$TMPFILE"

# crontabを一時ファイルに書き出し（指定行をコメントアウト）
CURRENT_LINE=0
while IFS= read -r line; do
    CURRENT_LINE=$((CURRENT_LINE + 1))
    if [[ $CURRENT_LINE -eq $LINE_NUMBER ]]; then
        echo "${DISABLED_PREFIX}${line}" >> "$TMPFILE"
    else
        echo "$line" >> "$TMPFILE"
    fi
done <<< "$CRONTAB_CONTENT"

# 9. crontabに設定
if ! crontab -u "$USERNAME" "$TMPFILE" 2>/dev/null; then
    log_error "Failed to install crontab for user=${USERNAME}"
    json_error "CRONTAB_INSTALL_FAILED" "Failed to install crontab"
fi

# 10. 残りのアクティブジョブ数を計算
REMAINING_JOBS=$(crontab -u "$USERNAME" -l 2>/dev/null | grep -cE '^[0-9\*]' || true)

# 11. 成功JSON出力
ESCAPED_SCHEDULE=$(json_escape "$SCHEDULE")
ESCAPED_COMMAND=$(json_escape "$COMMAND")
ESCAPED_ARGUMENTS=$(json_escape "$ARGUMENTS")

log_info "Cron remove successful: user=${USERNAME}, line=${LINE_NUMBER}, command=${COMMAND}"

echo "{\"status\":\"success\",\"message\":\"Cron job disabled (commented out)\",\"user\":\"${USERNAME}\",\"removed_job\":{\"line_number\":${LINE_NUMBER},\"schedule\":\"${ESCAPED_SCHEDULE}\",\"command\":\"${ESCAPED_COMMAND}\",\"arguments\":\"${ESCAPED_ARGUMENTS}\"},\"remaining_jobs\":${REMAINING_JOBS}}"
exit 0
