#!/bin/bash
# adminui-cron-list.sh - Cron ジョブ一覧取得ラッパー
#
# 用途: ユーザーのcrontabエントリを一覧取得し、JSON形式で出力
# 権限: root権限必要（crontab -u による他ユーザー参照）
# 呼び出し: sudo /usr/local/sbin/adminui-cron-list.sh <username>
#
# セキュリティ原則:
# - 入力検証必須（ユーザー名パターン、禁止ユーザー、禁止文字）
# - 出力のJSONエスケープ処理
# - 読み取り専用操作

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

# ===================================================================
# ログ関数
# ===================================================================

log_info() {
    logger -t adminui-cron-list -p user.info "$*"
}

log_error() {
    logger -t adminui-cron-list -p user.err "ERROR: $*"
}

log_security() {
    logger -t adminui-cron-list -p user.warning "SECURITY: $*"
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

# JSONエスケープ: ダブルクォートとバックスラッシュをエスケープ
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

# 1. 引数チェック（正確に1個）
if [[ $# -ne 1 ]]; then
    log_error "Invalid number of arguments: expected 1, got $#"
    json_error "INVALID_ARGS" "Usage: adminui-cron-list.sh <username>"
fi

USERNAME="$1"

log_info "Cron list requested: user=${USERNAME}, caller=${SUDO_USER:-$USER}"

# 2. 空文字チェック
if [[ -z "$USERNAME" ]]; then
    log_error "Empty username"
    json_error "INVALID_USERNAME" "Invalid username format"
fi

# 3. 禁止文字チェック
check_forbidden_chars "$USERNAME" "username"

# 4. ユーザー名パターン検証
if [[ ! "$USERNAME" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then
    log_error "Invalid username format: ${USERNAME}"
    json_error "INVALID_USERNAME" "Invalid username format"
fi

# 5. 禁止ユーザーチェック
for forbidden in "${FORBIDDEN_USERNAMES[@]}"; do
    if [[ "$USERNAME" == "$forbidden" ]]; then
        log_error "Forbidden system user: ${USERNAME}"
        json_error "FORBIDDEN_USER" "System user not allowed: ${USERNAME}"
    fi
done

# 6. ユーザー存在確認
if ! id -u "$USERNAME" >/dev/null 2>&1; then
    log_error "User does not exist: ${USERNAME}"
    json_error "USER_NOT_FOUND" "User does not exist: ${USERNAME}"
fi

# 7. crontab取得
CRONTAB_OUTPUT=""
if ! CRONTAB_OUTPUT=$(crontab -u "$USERNAME" -l 2>/dev/null); then
    # crontabが未設定の場合
    log_info "Cron list successful: user=${USERNAME}, count=0"
    echo "{\"status\":\"success\",\"user\":\"${USERNAME}\",\"jobs\":[],\"total_count\":0,\"max_allowed\":${MAX_JOBS}}"
    exit 0
fi

# 8. crontab内容をパースしてJSON化
JOBS_JSON=""
JOB_COUNT=0
LINE_NUMBER=0
COMMENT_FOR_NEXT=""

while IFS= read -r line; do
    LINE_NUMBER=$((LINE_NUMBER + 1))

    # 空行をスキップ
    if [[ -z "$line" ]]; then
        COMMENT_FOR_NEXT=""
        continue
    fi

    # 環境変数行をスキップ（MAILTO, SHELL, PATH等）
    if [[ "$line" =~ ^[A-Z_]+=.* ]]; then
        COMMENT_FOR_NEXT=""
        continue
    fi

    # adminuiによるDISABLEDコメント行（無効化されたジョブ）
    if [[ "$line" =~ ^#\ \[DISABLED\ by\ adminui\ .+\]\ (.+)$ ]]; then
        local_disabled_line="${BASH_REMATCH[1]}"
        # 無効化されたジョブ行をパース
        if [[ "$local_disabled_line" =~ ^([0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+)[[:space:]]+(/[^[:space:]]+)(.*)?$ ]]; then
            schedule=$(json_escape "${BASH_REMATCH[1]}")
            command=$(json_escape "${BASH_REMATCH[2]}")
            rest="${BASH_REMATCH[3]}"

            # 引数とインラインコメントを分離
            arguments=""
            comment=""
            if [[ -n "$rest" ]]; then
                # インラインコメント（# で始まる部分）を分離
                if [[ "$rest" =~ ^(.*)[[:space:]]#[[:space:]](.+)$ ]]; then
                    arguments=$(json_escape "$(echo "${BASH_REMATCH[1]}" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')")
                    comment=$(json_escape "${BASH_REMATCH[2]}")
                else
                    arguments=$(json_escape "$(echo "$rest" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')")
                fi
            fi

            # 前の行のコメントを使用（インラインコメントがない場合）
            if [[ -z "$comment" && -n "$COMMENT_FOR_NEXT" ]]; then
                comment=$(json_escape "$COMMENT_FOR_NEXT")
            fi

            JOB_COUNT=$((JOB_COUNT + 1))
            job_id=$(printf "cron_%03d" "$JOB_COUNT")

            if [[ -n "$JOBS_JSON" ]]; then
                JOBS_JSON="${JOBS_JSON},"
            fi

            JOBS_JSON="${JOBS_JSON}{\"id\":\"${job_id}\",\"line_number\":${LINE_NUMBER},\"schedule\":\"${schedule}\",\"command\":\"${command}\",\"arguments\":\"${arguments}\",\"comment\":\"${comment}\",\"enabled\":false}"
        fi
        COMMENT_FOR_NEXT=""
        continue
    fi

    # 通常のコメント行（次のジョブのコメントとして保持）
    if [[ "$line" =~ ^#[[:space:]]?(.*)$ ]]; then
        COMMENT_FOR_NEXT="${BASH_REMATCH[1]}"
        continue
    fi

    # ジョブ行のパース: schedule(5フィールド) command [arguments] [# comment]
    if [[ "$line" =~ ^([0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+[[:space:]]+[0-9\*\/\,\-]+)[[:space:]]+(/[^[:space:]]+)(.*)?$ ]]; then
        schedule=$(json_escape "${BASH_REMATCH[1]}")
        command=$(json_escape "${BASH_REMATCH[2]}")
        rest="${BASH_REMATCH[3]}"

        # 引数とインラインコメントを分離
        arguments=""
        comment=""
        if [[ -n "$rest" ]]; then
            # インラインコメント（# で始まる部分）を分離
            if [[ "$rest" =~ ^(.*)[[:space:]]#[[:space:]](.+)$ ]]; then
                arguments=$(json_escape "$(echo "${BASH_REMATCH[1]}" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')")
                comment=$(json_escape "${BASH_REMATCH[2]}")
            else
                arguments=$(json_escape "$(echo "$rest" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')")
            fi
        fi

        # 前の行のコメントを使用（インラインコメントがない場合）
        if [[ -z "$comment" && -n "$COMMENT_FOR_NEXT" ]]; then
            comment=$(json_escape "$COMMENT_FOR_NEXT")
        fi

        JOB_COUNT=$((JOB_COUNT + 1))
        job_id=$(printf "cron_%03d" "$JOB_COUNT")

        if [[ -n "$JOBS_JSON" ]]; then
            JOBS_JSON="${JOBS_JSON},"
        fi

        JOBS_JSON="${JOBS_JSON}{\"id\":\"${job_id}\",\"line_number\":${LINE_NUMBER},\"schedule\":\"${schedule}\",\"command\":\"${command}\",\"arguments\":\"${arguments}\",\"comment\":\"${comment}\",\"enabled\":true}"
        COMMENT_FOR_NEXT=""
    else
        COMMENT_FOR_NEXT=""
    fi
done <<< "$CRONTAB_OUTPUT"

# 9. JSON出力
log_info "Cron list successful: user=${USERNAME}, count=${JOB_COUNT}"
echo "{\"status\":\"success\",\"user\":\"${USERNAME}\",\"jobs\":[${JOBS_JSON}],\"total_count\":${JOB_COUNT},\"max_allowed\":${MAX_JOBS}}"
exit 0
