#!/bin/bash
# ==============================================================================
# uninstall.sh - Linux Management System アンインストールスクリプト
#
# 機能:
#   インストールされたサービス・設定ファイルの削除
#
# 使用方法:
#   sudo ./scripts/uninstall.sh [--yes] [--keep-data] [--keep-logs]
#
# オプション:
#   --yes         確認プロンプトをスキップ
#   --keep-data   データベース・設定ファイルを保持
#   --keep-logs   ログファイルを保持
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

YES=false
KEEP_DATA=false
KEEP_LOGS=false

usage() {
    echo "Usage: sudo $0 [--yes] [--keep-data] [--keep-logs]"
    echo ""
    echo "Options:"
    echo "  --yes         Skip confirmation prompts"
    echo "  --keep-data   Keep database and config files"
    echo "  --keep-logs   Keep log files"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes) YES=true; shift ;;
        --keep-data) KEEP_DATA=true; shift ;;
        --keep-logs) KEEP_LOGS=true; shift ;;
        --help) usage ;;
        *) echo "Unknown option: $1" >&2; usage ;;
    esac
done

# root 権限チェック
if [[ $EUID -ne 0 ]]; then
    echo "Error: This script must be run as root (sudo)" >&2
    exit 1
fi

echo "=============================================="
echo "Linux Management System - Uninstall"
echo "=============================================="
echo ""
echo "This will remove:"
echo "  - systemd services (adminui / linux-management-*)"
echo "  - Nginx configuration (/etc/nginx/sites-*/adminui)"
echo "  - SSL certificates (/etc/ssl/adminui/)"
echo "  - sudoers rules (/etc/sudoers.d/adminui)"
if [[ "$KEEP_DATA" == "false" ]]; then
    echo "  - Database files (${PROJECT_ROOT}/data/)"
fi
if [[ "$KEEP_LOGS" == "false" ]]; then
    echo "  - Log files (${PROJECT_ROOT}/logs/)"
fi
echo ""

if [[ "$YES" == "false" ]]; then
    read -r -p "Continue? [y/N] " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "Aborted."
        exit 0
    fi
fi

echo ""
echo "=== Phase 1: systemd サービス停止・削除 ==="

for service in adminui linux-management-prod linux-management-dev; do
    if systemctl is-active --quiet "$service" 2>/dev/null; then
        echo "Stopping $service..."
        systemctl stop "$service"
    fi
    if systemctl is-enabled --quiet "$service" 2>/dev/null; then
        echo "Disabling $service..."
        systemctl disable "$service"
    fi
    SERVICE_FILE="/etc/systemd/system/${service}.service"
    if [[ -f "$SERVICE_FILE" ]]; then
        echo "Removing $SERVICE_FILE..."
        rm -f "$SERVICE_FILE"
    fi
done

systemctl daemon-reload
echo "✅ systemd サービス削除完了"

echo ""
echo "=== Phase 2: Nginx 設定削除 ==="

for conf in /etc/nginx/sites-enabled/adminui /etc/nginx/sites-available/adminui; do
    if [[ -f "$conf" || -L "$conf" ]]; then
        echo "Removing $conf..."
        rm -f "$conf"
    fi
done

if [[ -d /etc/ssl/adminui ]]; then
    echo "Removing /etc/ssl/adminui/..."
    rm -rf /etc/ssl/adminui
fi

if command -v nginx &>/dev/null && nginx -t 2>/dev/null; then
    systemctl reload nginx 2>/dev/null || true
fi
echo "✅ Nginx 設定削除完了"

echo ""
echo "=== Phase 3: sudoers 設定削除 ==="

SUDOERS_FILE="/etc/sudoers.d/adminui"
if [[ -f "$SUDOERS_FILE" ]]; then
    echo "Removing $SUDOERS_FILE..."
    rm -f "$SUDOERS_FILE"
    echo "✅ sudoers 設定削除完了"
else
    echo "（sudoers ファイルなし - スキップ）"
fi

echo ""
echo "=== Phase 4: データ削除 ==="

if [[ "$KEEP_DATA" == "false" ]]; then
    if [[ -d "${PROJECT_ROOT}/data" ]]; then
        echo "Removing ${PROJECT_ROOT}/data/..."
        rm -rf "${PROJECT_ROOT}/data"
    fi
    echo "✅ データ削除完了"
else
    echo "（--keep-data 指定 - スキップ）"
fi

if [[ "$KEEP_LOGS" == "false" ]]; then
    if [[ -d "${PROJECT_ROOT}/logs" ]]; then
        echo "Removing ${PROJECT_ROOT}/logs/..."
        rm -rf "${PROJECT_ROOT}/logs"
    fi
    echo "✅ ログ削除完了"
else
    echo "（--keep-logs 指定 - スキップ）"
fi

echo ""
echo "=============================================="
echo "✅ アンインストール完了"
echo ""
echo "注意: アプリケーションファイル自体は削除されていません。"
echo "完全に削除する場合は: rm -rf ${PROJECT_ROOT}"
echo "=============================================="
