#!/bin/bash
# ==============================================================================
# adminui-proftpd.sh - ProFTPD/FTP Server 管理ラッパー（読み取り専用）
#
# 機能:
#   ProFTPD / vsftpd サービスの状態・ユーザー・セッション・ログを取得する。
#   全操作は読み取り専用。設定変更は行わない。
#
# 使用方法:
#   adminui-proftpd.sh <subcommand> [lines]
#
# サブコマンド:
#   status   - FTP サービス状態 (systemctl status)
#   users    - FTP 許可ユーザー一覧 (/etc/ftpusers, /etc/proftpd/proftpd.conf)
#   sessions - アクティブセッション (ftptop / ss -tnp ポート21)
#   logs     - FTP ログ (journalctl / /var/log/proftpd/)
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - 許可サブコマンドのみ実行（allowlist方式）
#   - 読み取り専用（設定変更・再起動等は行わない）
# ==============================================================================

set -euo pipefail

ALLOWED_SUBCOMMANDS=("status" "users" "sessions" "logs")

error_json() {
    echo "{\"status\": \"error\", \"message\": \"$1\"}" >&2
    exit 1
}

if [ "$#" -lt 1 ]; then
    error_json "Usage: adminui-proftpd.sh <subcommand> [lines]"
fi

SUBCOMMAND="$1"
LINES="${2:-50}"

# lines パラメータの検証（数値のみ許可）
if ! [[ "$LINES" =~ ^[0-9]+$ ]]; then
    error_json "lines must be a positive integer"
fi
if [ "$LINES" -lt 1 ]; then LINES=1; fi
if [ "$LINES" -gt 200 ]; then LINES=200; fi

# allowlist 検証
ALLOWED=false
for cmd in "${ALLOWED_SUBCOMMANDS[@]}"; do
    if [ "$cmd" = "$SUBCOMMAND" ]; then
        ALLOWED=true
        break
    fi
done

if ! $ALLOWED; then
    error_json "Unknown subcommand: $SUBCOMMAND. Allowed: ${ALLOWED_SUBCOMMANDS[*]}"
fi

TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

# FTP サービス名の自動検出
detect_ftp_service() {
    if systemctl list-units --type=service 2>/dev/null | grep -q "proftpd"; then
        echo "proftpd"
    elif systemctl list-units --type=service 2>/dev/null | grep -q "vsftpd"; then
        echo "vsftpd"
    elif systemctl list-units --type=service 2>/dev/null | grep -q "pure-ftpd"; then
        echo "pure-ftpd"
    else
        echo ""
    fi
}

json_escape() {
    python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo "\"(escape failed)\""
}

case "$SUBCOMMAND" in
    status)
        SERVICE_NAME=$(detect_ftp_service)

        if [ -z "$SERVICE_NAME" ]; then
            echo "{\"status\": \"unavailable\", \"message\": \"FTP service not found (proftpd/vsftpd/pure-ftpd)\", \"timestamp\": \"${TIMESTAMP}\"}"
            exit 0
        fi

        ACTIVE_STATE=$(systemctl is-active "${SERVICE_NAME}" 2>/dev/null || echo "unknown")
        ENABLED_STATE=$(systemctl is-enabled "${SERVICE_NAME}" 2>/dev/null || echo "unknown")

        # バージョン取得
        VERSION="unknown"
        if [ "$SERVICE_NAME" = "proftpd" ] && command -v proftpd >/dev/null 2>&1; then
            VERSION=$(proftpd --version 2>/dev/null | head -1 || echo "unknown")
        elif [ "$SERVICE_NAME" = "vsftpd" ] && command -v vsftpd >/dev/null 2>&1; then
            VERSION=$(vsftpd -v 2>&1 | head -1 || echo "unknown")
        fi

        VERSION_ESCAPED=$(echo "$VERSION" | json_escape)
        echo "{\"status\": \"success\", \"service\": \"${SERVICE_NAME}\", \"active\": \"${ACTIVE_STATE}\", \"enabled\": \"${ENABLED_STATE}\", \"version\": ${VERSION_ESCAPED}, \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    users)
        # FTP 許可ユーザー一覧を取得
        USERS_OUTPUT=""

        # /etc/ftpusers (拒否リスト) の確認
        if [ -f /etc/ftpusers ]; then
            USERS_OUTPUT=$(cat /etc/ftpusers 2>/dev/null || echo "")
        fi

        # /etc/vsftpd.userlist の確認
        if [ -f /etc/vsftpd.userlist ]; then
            USERLIST=$(cat /etc/vsftpd.userlist 2>/dev/null || echo "")
            USERS_OUTPUT="${USERS_OUTPUT}
--- vsftpd.userlist ---
${USERLIST}"
        fi

        # /etc/proftpd/ftpusers の確認
        if [ -f /etc/proftpd/ftpusers ]; then
            PROFTPD_USERS=$(cat /etc/proftpd/ftpusers 2>/dev/null || echo "")
            USERS_OUTPUT="${USERS_OUTPUT}
--- proftpd/ftpusers ---
${PROFTPD_USERS}"
        fi

        if [ -z "$USERS_OUTPUT" ]; then
            USERS_OUTPUT="No FTP user list files found (/etc/ftpusers, /etc/vsftpd.userlist)"
        fi

        USERS_ESCAPED=$(echo "$USERS_OUTPUT" | json_escape)
        echo "{\"status\": \"success\", \"users_raw\": ${USERS_ESCAPED}, \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    sessions)
        # アクティブセッション (ポート21の接続状況)
        SESSIONS_OUTPUT=""

        if command -v ss >/dev/null 2>&1; then
            SESSIONS_OUTPUT=$(ss -tnp 'sport = :21 or dport = :21' 2>/dev/null || echo "")
        fi

        if [ -z "$SESSIONS_OUTPUT" ]; then
            SESSIONS_OUTPUT="No active FTP sessions detected"
        fi

        SESSIONS_ESCAPED=$(echo "$SESSIONS_OUTPUT" | json_escape)
        echo "{\"status\": \"success\", \"sessions_raw\": ${SESSIONS_ESCAPED}, \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    logs)
        # FTP ログ取得
        LOG_OUTPUT=""

        # journalctl でサービスログを取得
        SERVICE_NAME=$(detect_ftp_service)
        if [ -n "$SERVICE_NAME" ]; then
            LOG_OUTPUT=$(journalctl -u "${SERVICE_NAME}" --no-pager -n "${LINES}" 2>/dev/null || echo "")
        fi

        # /var/log/proftpd/ ログファイルの確認
        if [ -z "$LOG_OUTPUT" ] && [ -f /var/log/proftpd/proftpd.log ]; then
            LOG_OUTPUT=$(tail -n "${LINES}" /var/log/proftpd/proftpd.log 2>/dev/null || echo "")
        fi

        # /var/log/vsftpd.log の確認
        if [ -z "$LOG_OUTPUT" ] && [ -f /var/log/vsftpd.log ]; then
            LOG_OUTPUT=$(tail -n "${LINES}" /var/log/vsftpd.log 2>/dev/null || echo "")
        fi

        if [ -z "$LOG_OUTPUT" ]; then
            LOG_OUTPUT="No FTP log entries found"
        fi

        LOG_ESCAPED=$(echo "$LOG_OUTPUT" | json_escape)
        echo "{\"status\": \"success\", \"logs_raw\": ${LOG_ESCAPED}, \"lines\": ${LINES}, \"timestamp\": \"${TIMESTAMP}\"}"
        ;;

    *)
        error_json "Unexpected subcommand: $SUBCOMMAND"
        ;;
esac
