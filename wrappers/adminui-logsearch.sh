#!/bin/bash
# adminui-logsearch.sh - ログ検索ラッパー
#
# 用途: /var/log/ 配下のログファイル検索・一覧・エラー集約
# 権限: sudo 経由で実行
# セキュリティ: allowlist サブコマンド、禁止文字チェック必須

set -euo pipefail

log()   { logger -t adminui-logsearch -p user.info  "$*"; echo "[$(date -Iseconds)] $*" >&2; }
error() { logger -t adminui-logsearch -p user.err   "ERROR: $*"; echo "[$(date -Iseconds)] ERROR: $*" >&2; }

# ===================================================================
# 許可サブコマンド（allowlist）
# ===================================================================
ALLOWED=("search" "list-files" "recent-errors" "tail-multi")

# ===================================================================
# 禁止文字パターン
# ===================================================================
# shellcheck disable=SC2016
FORBIDDEN_CHARS='[;|&$()` ><*?{}[\]]'

validate_arg() {
    local val="$1"
    if [[ "$val" =~ $FORBIDDEN_CHARS ]]; then
        error "Forbidden character detected in argument: $val"
        echo "{\"status\": \"error\", \"message\": \"Forbidden character in argument\"}"
        exit 1
    fi
}

# ===================================================================
# 引数チェック
# ===================================================================
SUBCOMMAND="${1:-}"

if [ -z "$SUBCOMMAND" ]; then
    error "No subcommand given"
    echo "{\"status\": \"error\", \"message\": \"No subcommand given\"}"
    exit 1
fi

# allowlist チェック
CMD_ALLOWED=false
for allowed in "${ALLOWED[@]}"; do
    if [ "$SUBCOMMAND" = "$allowed" ]; then
        CMD_ALLOWED=true
        break
    fi
done

if [ "$CMD_ALLOWED" = false ]; then
    error "Subcommand not allowed: $SUBCOMMAND"
    echo "{\"status\": \"error\", \"message\": \"Subcommand not allowed: $SUBCOMMAND\"}"
    exit 1
fi

log "logsearch requested: subcommand=$SUBCOMMAND, caller=${SUDO_USER:-$USER}"

# ===================================================================
# JSON ヘルパー
# ===================================================================
json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\t'/\\t}"
    echo "$s"
}

output_lines_json() {
    # stdin から行を読んで JSON 配列として出力
    local first=true
    echo "["
    while IFS= read -r line; do
        if [ "$first" = false ]; then printf ',\n'; fi
        first=false
        printf '    "%s"' "$(json_escape "$line")"
    done
    echo ""
    echo "  ]"
}

# ===================================================================
# サブコマンド実装
# ===================================================================

case "$SUBCOMMAND" in

# ------------------------------------------------------------------
# search: grep でパターン検索
# 引数: pattern logfile lines
# ------------------------------------------------------------------
search)
    PATTERN="${2:-}"
    LOGFILE="${3:-syslog}"
    LINES="${4:-50}"

    if [ -z "$PATTERN" ]; then
        error "search: pattern is required"
        echo "{\"status\": \"error\", \"message\": \"pattern is required\"}"
        exit 1
    fi

    validate_arg "$PATTERN"
    validate_arg "$LOGFILE"

    # ログファイル名の安全チェック（英数字・ハイフン・ドット・アンダースコアのみ）
    if [[ ! "$LOGFILE" =~ ^[a-zA-Z0-9._-]+$ ]]; then
        error "Invalid log file name: $LOGFILE"
        echo "{\"status\": \"error\", \"message\": \"Invalid log file name\"}"
        exit 1
    fi

    # 行数の検証
    if [[ ! "$LINES" =~ ^[0-9]+$ ]] || [ "$LINES" -lt 1 ] || [ "$LINES" -gt 200 ]; then
        LINES=50
    fi

    LOGPATH="/var/log/${LOGFILE}"

    # ファイルが存在しない場合は空結果
    if [ ! -f "$LOGPATH" ]; then
        echo "{\"status\": \"success\", \"pattern\": \"$(json_escape "$PATTERN")\", \"logfile\": \"$LOGFILE\", \"lines_returned\": 0, \"results\": [], \"timestamp\": \"$(date -Iseconds)\"}"
        exit 0
    fi

    # grep 実行（配列渡し）
    RAW_OUTPUT=$(grep -i -m "$LINES" -- "$PATTERN" "$LOGPATH" 2>/dev/null || true)
    LINE_COUNT=$(echo "$RAW_OUTPUT" | grep -c . || true)

    echo "{"
    echo "  \"status\": \"success\","
    echo "  \"pattern\": \"$(json_escape "$PATTERN")\","
    echo "  \"logfile\": \"$LOGFILE\","
    echo "  \"lines_returned\": $LINE_COUNT,"
    printf '  "results": '
    if [ -z "$RAW_OUTPUT" ]; then
        echo "[],"
    else
        echo "$RAW_OUTPUT" | output_lines_json
        echo ","
    fi
    echo "  \"timestamp\": \"$(date -Iseconds)\""
    echo "}"
    ;;

# ------------------------------------------------------------------
# list-files: /var/log/ 配下の .log ファイル一覧
# ------------------------------------------------------------------
list-files)
    FILES=$(find /var/log/ -name "*.log" -maxdepth 3 -type f 2>/dev/null | sort | head -50 || true)
    # syslog/auth.log 等（拡張子なし）も追加
    EXTRA=$(find /var/log/ -maxdepth 1 -type f \( -name "syslog" -o -name "auth.log" -o -name "kern.log" -o -name "messages" -o -name "dmesg" \) 2>/dev/null | sort || true)

    ALL_FILES=$(printf '%s\n%s' "$FILES" "$EXTRA" | sort -u | grep -v '^$' | head -50 || true)
    FILE_COUNT=$(echo "$ALL_FILES" | grep -c . || true)

    echo "{"
    echo "  \"status\": \"success\","
    echo "  \"file_count\": $FILE_COUNT,"
    printf '  "files": '
    if [ -z "$ALL_FILES" ]; then
        echo "[],"
    else
        echo "$ALL_FILES" | output_lines_json
        echo ","
    fi
    echo "  \"timestamp\": \"$(date -Iseconds)\""
    echo "}"
    ;;

# ------------------------------------------------------------------
# recent-errors: syslog から直近エラー集約
# ------------------------------------------------------------------
recent-errors)
    ERRORS=$(grep -i -E "error|critical|fatal" /var/log/syslog 2>/dev/null | tail -50 || true)
    # auth.log も含める
    AUTH_ERRORS=$(grep -i -E "error|critical|fatal|failed" /var/log/auth.log 2>/dev/null | tail -20 || true)

    ALL_ERRORS=$(printf '%s\n%s' "$ERRORS" "$AUTH_ERRORS" | grep -v '^$' | tail -50 || true)
    ERROR_COUNT=$(echo "$ALL_ERRORS" | grep -c . || true)

    echo "{"
    echo "  \"status\": \"success\","
    echo "  \"error_count\": $ERROR_COUNT,"
    printf '  "errors": '
    if [ -z "$ALL_ERRORS" ]; then
        echo "[],"
    else
        echo "$ALL_ERRORS" | output_lines_json
        echo ","
    fi
    echo "  \"timestamp\": \"$(date -Iseconds)\""
    echo "}"
    ;;

# ------------------------------------------------------------------
# tail-multi: 複数ログファイルの末尾連結表示
# ------------------------------------------------------------------
tail-multi)
    LINES="${2:-30}"
    if [[ ! "$LINES" =~ ^[0-9]+$ ]] || [ "$LINES" -lt 1 ] || [ "$LINES" -gt 200 ]; then
        LINES=30
    fi

    declare -a LOG_FILES=()
    for f in /var/log/syslog /var/log/auth.log /var/log/kern.log; do
        [ -f "$f" ] && LOG_FILES+=("$f")
    done

    if [ ${#LOG_FILES[@]} -eq 0 ]; then
        echo "{\"status\": \"success\", \"lines_returned\": 0, \"lines\": [], \"timestamp\": \"$(date -Iseconds)\"}"
        exit 0
    fi

    OUTPUT=$(tail -n "$LINES" "${LOG_FILES[@]}" 2>/dev/null || true)
    LINE_COUNT=$(echo "$OUTPUT" | grep -c . || true)

    echo "{"
    echo "  \"status\": \"success\","
    echo "  \"lines_returned\": $LINE_COUNT,"
    printf '  "lines": '
    if [ -z "$OUTPUT" ]; then
        echo "[],"
    else
        echo "$OUTPUT" | output_lines_json
        echo ","
    fi
    echo "  \"timestamp\": \"$(date -Iseconds)\""
    echo "}"
    ;;

esac

exit 0
