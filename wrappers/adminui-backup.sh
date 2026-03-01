#!/bin/bash
set -euo pipefail

ACTION="${1:-}"
ALLOWED_ACTIONS=("list" "status" "disk-usage" "recent-logs")

if [[ ! " ${ALLOWED_ACTIONS[*]} " =~ " ${ACTION} " ]]; then
    echo "Error: Invalid action: ${ACTION}" >&2
    exit 1
fi

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
esac
