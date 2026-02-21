#!/bin/bash
# adminui-cron-add.sh - Cron ジョブ追加ラッパー
#
# 用途: ユーザーのcrontabに新しいジョブを追加
# 権限: root権限必要（crontab -u による他ユーザー操作）
# 呼び出し: sudo /usr/local/sbin/adminui-cron-add.sh <username> <schedule> <command> [arguments] [comment]
#
# セキュリティ原則:
# - allowlist方式（許可コマンドのみ）
# - 多重防御（禁止文字、禁止コマンド、パストラバーサル）
# - 安全な一時ファイル処理（mktemp + trap）
# - ジョブ数制限（ユーザーあたり最大10個）

set -euo pipefail

# ===================================================================
# 定数定義
# ===================================================================

MAX_JOBS=10
MAX_ARGS_LENGTH=512
MAX_COMMENT_LENGTH=256

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

FORBIDDEN_COMMANDS=(
    "/bin/bash" "/bin/sh" "/bin/zsh" "/bin/dash"
    "/usr/bin/bash" "/usr/bin/sh"
    "/bin/rm" "/usr/bin/rm"
    "/sbin/reboot" "/sbin/shutdown" "/sbin/init"
    "/sbin/mkfs" "/sbin/fdisk"
    "/usr/bin/dd" "/bin/dd"
    "/usr/bin/sudo" "/usr/sbin/visudo"
    "/usr/bin/chmod" "/usr/bin/chown"
    "/bin/chmod" "/bin/chown"
)

# ===================================================================
# ログ関数
# ===================================================================

log_info() {
    logger -t adminui-cron-add -p user.info "$*"
}

log_error() {
    logger -t adminui-cron-add -p user.err "ERROR: $*"
}

log_security() {
    logger -t adminui-cron-add -p user.warning "SECURITY: $*"
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
            json_error "FORBIDDEN_CHARS" "Forbidden character detected in ${field_name}: ${char}"
        fi
    done
}

# ===================================================================
# スケジュール検証
# ===================================================================

validate_schedule() {
    local schedule="$1"

    # 5フィールドに分割
    local fields
    IFS=' ' read -ra fields <<< "$schedule"
    if [[ ${#fields[@]} -ne 5 ]]; then
        log_error "Invalid schedule: not 5 fields: ${schedule}"
        json_error "INVALID_SCHEDULE" "Schedule must have exactly 5 fields"
    fi

    local minute="${fields[0]}"
    local hour="${fields[1]}"
    local dom="${fields[2]}"
    local month="${fields[3]}"
    local dow="${fields[4]}"

    # 各フィールドの基本パターン検証（数字、*、/、,、- のみ許可）
    local field_pattern='^[0-9\*\/\,\-]+$'
    for field in "$minute" "$hour" "$dom" "$month" "$dow"; do
        if [[ ! "$field" =~ $field_pattern ]]; then
            log_error "Invalid schedule field: ${field}"
            json_error "INVALID_SCHEDULE" "Invalid characters in schedule field: ${field}"
        fi
    done

    # 最小間隔チェック（毎分や*/1~*/4は拒否）
    if [[ "$minute" == "*" ]]; then
        log_error "Execution interval too short: minute=*"
        json_error "INVALID_SCHEDULE" "Execution interval too short (minimum: */5)"
    fi
    if [[ "$minute" =~ ^\*/[1-4]$ ]]; then
        log_error "Execution interval too short: minute=${minute}"
        json_error "INVALID_SCHEDULE" "Execution interval too short: ${minute} (minimum: */5)"
    fi
}

# ===================================================================
# メイン処理
# ===================================================================

# 1. 引数チェック（3-5個）
if [[ $# -lt 3 || $# -gt 5 ]]; then
    log_error "Invalid number of arguments: expected 3-5, got $#"
    json_error "INVALID_ARGS" "Usage: adminui-cron-add.sh <username> <schedule> <command> [arguments] [comment]"
fi

USERNAME="$1"
SCHEDULE="$2"
COMMAND="$3"
ARGUMENTS="${4:-}"
COMMENT="${5:-}"

log_info "Cron add requested: user=${USERNAME}, schedule=\"${SCHEDULE}\", command=${COMMAND}, caller=${SUDO_USER:-$USER}"

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

# 3. スケジュール検証
# 3a. 禁止文字チェック（スケジュール用: *, / は許可するためスケジュールフィールドは個別チェック）
for char in ';' '|' '&' '$' '(' ')' '`' '>' '<' '?' '{' '}' '[' ']'; do
    if [[ "$SCHEDULE" == *"$char"* ]]; then
        log_security "Forbidden character '${char}' in schedule, caller=${SUDO_USER:-$USER}"
        json_error "FORBIDDEN_CHARS" "Forbidden character detected in schedule: ${char}"
    fi
done

# 3b. スケジュール形式検証
validate_schedule "$SCHEDULE"

# 4. コマンド検証
# 4a. 空文字チェック
if [[ -z "$COMMAND" ]]; then
    log_error "Empty command"
    json_error "INVALID_COMMAND" "Command is required"
fi

# 4b. 禁止文字チェック
check_forbidden_chars "$COMMAND" "command"

# 4c. 絶対パスチェック
if [[ "$COMMAND" != /* ]]; then
    log_error "Command is not absolute path: ${COMMAND}"
    json_error "INVALID_COMMAND" "Command must be absolute path"
fi

# 4d. 禁止コマンドチェック（allowlistより先にチェック）
for forbidden_cmd in "${FORBIDDEN_COMMANDS[@]}"; do
    if [[ "$COMMAND" == "$forbidden_cmd" ]]; then
        log_security "Forbidden command attempted: ${COMMAND}, caller=${SUDO_USER:-$USER}"
        json_error "FORBIDDEN_COMMAND" "Forbidden command: ${COMMAND}"
    fi
done

# 4e. allowlistチェック
COMMAND_ALLOWED=false
for allowed_cmd in "${ALLOWED_COMMANDS[@]}"; do
    if [[ "$COMMAND" == "$allowed_cmd" ]]; then
        COMMAND_ALLOWED=true
        break
    fi
done

if [[ "$COMMAND_ALLOWED" == "false" ]]; then
    log_error "Command not in allowlist: ${COMMAND}, caller=${SUDO_USER:-$USER}"
    json_error "COMMAND_NOT_ALLOWED" "Command not in allowlist: ${COMMAND}"
fi

# 4f. realpath正規化 + 再チェック（symlink対策）
if [[ -e "$COMMAND" ]]; then
    REAL_COMMAND=$(realpath "$COMMAND" 2>/dev/null || echo "$COMMAND")
    if [[ "$REAL_COMMAND" != "$COMMAND" ]]; then
        # symlink先がallowlistに含まれるかチェック
        REAL_ALLOWED=false
        for allowed_cmd in "${ALLOWED_COMMANDS[@]}"; do
            if [[ "$REAL_COMMAND" == "$allowed_cmd" ]]; then
                REAL_ALLOWED=true
                break
            fi
        done
        if [[ "$REAL_ALLOWED" == "false" ]]; then
            log_security "Symlink detected: ${COMMAND} -> ${REAL_COMMAND}, caller=${SUDO_USER:-$USER}"
            json_error "COMMAND_NOT_ALLOWED" "Command not in allowlist (symlink resolved): ${REAL_COMMAND}"
        fi
    fi
fi

# 5. 引数検証（存在する場合）
if [[ -n "$ARGUMENTS" ]]; then
    # 5a. 長さチェック
    if [[ ${#ARGUMENTS} -gt $MAX_ARGS_LENGTH ]]; then
        log_error "Arguments too long: ${#ARGUMENTS} chars (max ${MAX_ARGS_LENGTH})"
        json_error "INVALID_ARGUMENTS" "Arguments exceed maximum length of ${MAX_ARGS_LENGTH} characters"
    fi

    # 5b. 禁止文字チェック（引数用: 一部文字は許可するため個別チェック）
    for char in ';' '|' '&' '$' '(' ')' '`' '{' '}' '[' ']'; do
        if [[ "$ARGUMENTS" == *"$char"* ]]; then
            log_security "Forbidden character '${char}' in arguments, caller=${SUDO_USER:-$USER}"
            json_error "FORBIDDEN_CHARS" "Forbidden character detected in arguments: ${char}"
        fi
    done

    # 5c. パストラバーサルチェック
    if [[ "$ARGUMENTS" == *".."* ]]; then
        log_security "Path traversal detected in arguments, caller=${SUDO_USER:-$USER}"
        json_error "PATH_TRAVERSAL" "Path traversal detected in arguments"
    fi
fi

# 6. コメント検証（存在する場合）
if [[ -n "$COMMENT" ]]; then
    if [[ ${#COMMENT} -gt $MAX_COMMENT_LENGTH ]]; then
        log_error "Comment too long: ${#COMMENT} chars (max ${MAX_COMMENT_LENGTH})"
        json_error "INVALID_COMMENT" "Comment exceeds maximum length of ${MAX_COMMENT_LENGTH} characters"
    fi

    # コメント内の禁止文字チェック
    for char in ';' '|' '&' '$' '(' ')' '`' '{' '}' '[' ']'; do
        if [[ "$COMMENT" == *"$char"* ]]; then
            log_security "Forbidden character '${char}' in comment, caller=${SUDO_USER:-$USER}"
            json_error "FORBIDDEN_CHARS" "Forbidden character detected in comment: ${char}"
        fi
    done
fi

# 7. ジョブ数チェック
CURRENT_JOBS=0
if CRONTAB_CONTENT=$(crontab -u "$USERNAME" -l 2>/dev/null); then
    # 有効なジョブ行のみカウント（コメント行、空行、環境変数行を除外）
    CURRENT_JOBS=$(echo "$CRONTAB_CONTENT" | grep -cE '^[0-9\*]' || true)
fi

if [[ $CURRENT_JOBS -ge $MAX_JOBS ]]; then
    log_error "Max jobs exceeded: user=${USERNAME}, current=${CURRENT_JOBS}, max=${MAX_JOBS}"
    json_error "MAX_JOBS_EXCEEDED" "Maximum ${MAX_JOBS} cron jobs per user (current: ${CURRENT_JOBS})"
fi

# 8. 重複チェック
if [[ -n "$CRONTAB_CONTENT" ]]; then
    NEW_ENTRY="${SCHEDULE} ${COMMAND}"
    if [[ -n "$ARGUMENTS" ]]; then
        NEW_ENTRY="${NEW_ENTRY} ${ARGUMENTS}"
    fi
    # 既存のcrontabに同一エントリがあるかチェック
    while IFS= read -r line; do
        # コメント行・空行をスキップ
        if [[ -z "$line" || "$line" =~ ^# || "$line" =~ ^[A-Z_]+=.* ]]; then
            continue
        fi
        # コメント部分を除去して比較 (shellcheck disable: character class pattern requires sed)
        # shellcheck disable=SC2001
        clean_line=$(echo "$line" | sed 's/[[:space:]]#[[:space:]].*$//')
        if [[ "$clean_line" == "$NEW_ENTRY" ]]; then
            log_error "Duplicate job: ${NEW_ENTRY}"
            json_error "DUPLICATE_JOB" "Identical cron job already exists"
        fi
    done <<< "$CRONTAB_CONTENT"
fi

# 9. 安全な一時ファイル作成
TMPFILE=$(mktemp /tmp/adminui-cron-XXXXXX)
trap 'rm -f "$TMPFILE"' EXIT
chmod 600 "$TMPFILE"

# 10. 既存のcrontabを取得
if [[ -n "${CRONTAB_CONTENT:-}" ]]; then
    echo "$CRONTAB_CONTENT" > "$TMPFILE"
else
    : > "$TMPFILE"
fi

# 11. 新エントリ追記
if [[ -n "$COMMENT" ]]; then
    echo "# ${COMMENT}" >> "$TMPFILE"
fi
if [[ -n "$ARGUMENTS" ]]; then
    echo "${SCHEDULE} ${COMMAND} ${ARGUMENTS}" >> "$TMPFILE"
else
    echo "${SCHEDULE} ${COMMAND}" >> "$TMPFILE"
fi

# 12. crontabに設定
if ! crontab -u "$USERNAME" "$TMPFILE" 2>/dev/null; then
    log_error "Failed to install crontab for user=${USERNAME}"
    json_error "CRONTAB_INSTALL_FAILED" "Failed to install crontab"
fi

# 13. 成功JSON出力
TOTAL_JOBS=$((CURRENT_JOBS + 1))
ESCAPED_SCHEDULE=$(json_escape "$SCHEDULE")
ESCAPED_COMMAND=$(json_escape "$COMMAND")
ESCAPED_ARGUMENTS=$(json_escape "$ARGUMENTS")
ESCAPED_COMMENT=$(json_escape "$COMMENT")

log_info "Cron add successful: user=${USERNAME}, total_jobs=${TOTAL_JOBS}"

echo "{\"status\":\"success\",\"message\":\"Cron job added successfully\",\"user\":\"${USERNAME}\",\"job\":{\"schedule\":\"${ESCAPED_SCHEDULE}\",\"command\":\"${ESCAPED_COMMAND}\",\"arguments\":\"${ESCAPED_ARGUMENTS}\",\"comment\":\"${ESCAPED_COMMENT}\"},\"total_jobs\":${TOTAL_JOBS}}"
exit 0
