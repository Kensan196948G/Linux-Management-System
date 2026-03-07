#!/bin/bash
set -euo pipefail

ACTION="${1:-}"
ALLOWED_ACTIONS=("list" "status" "disk-usage" "recent-logs" "list-backups" "list-schedules" "restore-file")

if [[ ! " ${ALLOWED_ACTIONS[*]} " =~ " ${ACTION} " ]]; then
    echo "Error: Invalid action: ${ACTION}" >&2
    exit 1
fi

# バックアップ対象ディレクトリの allowlist（restore-file 用）
ALLOWED_RESTORE_DIRS=("/var/backups" "/tmp/backups")

_validate_path() {
    local path="$1"
    # 特殊文字チェック
    if [[ "${path}" =~ [';''|''&''$''('')''\`''>''<''*''?''{''}''\[''\\'] ]]; then
        echo "Error: Forbidden characters in path: ${path}" >&2
        exit 1
    fi
    # パストラバーサル防止
    if [[ "${path}" =~ \.\. ]]; then
        echo "Error: Path traversal detected: ${path}" >&2
        exit 1
    fi
}

case "${ACTION}" in
    list)
        # /var/backups 以下のバックアップファイル一覧
        if [ -d /var/backups ]; then
            ls -la /var/backups/ 2>/dev/null || echo "No backups found"
        else
            echo "Backup directory /var/backups not found"
        fi
        ;;
    status)
        # rsync/tar の最新ステータス（systemd timer or cron経由のステータス）
        if command -v systemctl >/dev/null 2>&1; then
            systemctl list-timers --no-pager 2>/dev/null | grep -i backup || echo "No backup timers found"
        else
            echo "systemctl not available"
        fi
        ;;
    disk-usage)
        # バックアップディレクトリのディスク使用量
        if [ -d /var/backups ]; then
            du -sh /var/backups 2>/dev/null || echo "Cannot read /var/backups"
        else
            echo "0\t/var/backups (not found)"
        fi
        ;;
    recent-logs)
        # バックアップ関連のジャーナルログ
        journalctl -u rsync -n 20 --no-pager 2>/dev/null || \
        journalctl -g "backup" -n 20 --no-pager 2>/dev/null || \
        echo "No backup logs found"
        ;;
    list-backups)
        # バックアップファイル詳細一覧（JSON形式）
        if [ -d /var/backups ]; then
            find /var/backups -maxdepth 2 -type f \( -name "*.tar.gz" -o -name "*.tar.bz2" -o -name "*.zip" -o -name "*.tar" \) \
                -printf '{"name":"%f","path":"%p","size":%s,"mtime":"%TY-%Tm-%TdT%TH:%TM:%TS"}\n' 2>/dev/null \
                | sort -t'"' -k8 -r \
                || echo "No backup files found"
        else
            echo "Backup directory /var/backups not found"
        fi
        ;;
    list-schedules)
        # crontab から adminui バックアップスケジュールを取得
        crontab -l 2>/dev/null | grep -i "adminui-backup\|# adminui-schedule" || echo "No scheduled backups found"
        ;;
    restore-file)
        # ファイルリストア（承認フロー経由でのみ呼ばれる）
        # 引数: restore-file <backup_file_path> <restore_target_dir>
        BACKUP_FILE="${2:-}"
        RESTORE_DIR="${3:-/tmp/restore}"

        if [ -z "${BACKUP_FILE}" ]; then
            echo "Error: backup file path required" >&2
            exit 1
        fi

        _validate_path "${BACKUP_FILE}"
        _validate_path "${RESTORE_DIR}"

        # allowlist チェック: バックアップファイルは /var/backups 配下のみ
        ALLOWED=0
        for ALLOWED_DIR in "${ALLOWED_RESTORE_DIRS[@]}"; do
            if [[ "${BACKUP_FILE}" == "${ALLOWED_DIR}"* ]]; then
                ALLOWED=1
                break
            fi
        done
        if [ "${ALLOWED}" -eq 0 ]; then
            echo "Error: Backup file must be within allowed directories: ${ALLOWED_RESTORE_DIRS[*]}" >&2
            exit 1
        fi

        if [ ! -f "${BACKUP_FILE}" ]; then
            echo "Error: Backup file not found: ${BACKUP_FILE}" >&2
            exit 1
        fi

        mkdir -p "${RESTORE_DIR}"
        tar -xzf "${BACKUP_FILE}" -C "${RESTORE_DIR}" 2>&1
        echo "Restore completed to ${RESTORE_DIR}"
        ;;
esac
