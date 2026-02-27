#!/bin/bash
# start-dev-server.sh - 開発サーバー起動スクリプト（Systemdまたは直接起動）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 引数解析
USE_SYSTEMD=false
FOREGROUND=false
for arg in "$@"; do
    case "${arg}" in
        --systemd) USE_SYSTEMD=true ;;
        --fg|--foreground) FOREGROUND=true ;;
    esac
done

echo "========================================="
echo "Linux Management System - 開発サーバー"
echo "========================================="
echo ""

# IP検出
echo "🔍 IPアドレスを検出中..."
bash "${SCRIPT_DIR}/detect-ip.sh"
echo ""

# .env / .env.runtime 読み込み
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    # shellcheck disable=SC1091
    set -a; source "${PROJECT_ROOT}/.env"; set +a
fi
if [[ -f "${PROJECT_ROOT}/.env.runtime" ]]; then
    # shellcheck disable=SC1091
    set -a; source "${PROJECT_ROOT}/.env.runtime"; set +a
fi

DEV_PORT="${DEV_PORT:-5012}"
DEV_HTTPS_PORT="${DEV_HTTPS_PORT:-5443}"
DETECTED_IP="${DETECTED_IP:-127.0.0.1}"

if [[ "${USE_SYSTEMD}" == "true" ]]; then
    # Systemd経由で起動
    echo "🚀 Systemdサービスとして起動中..."
    sudo systemctl start linux-management-dev.service
    sleep 2
    sudo systemctl status linux-management-dev.service --no-pager | head -20
    echo ""
    echo "✅ Systemdサービス起動完了"
    echo "   管理コマンド:"
    echo "     停止:   sudo systemctl stop linux-management-dev"
    echo "     再起動: sudo systemctl restart linux-management-dev"
    echo "     ログ:   sudo journalctl -u linux-management-dev -f"
else
    # Python 仮想環境の確認
    if [[ ! -d "${PROJECT_ROOT}/venv" ]]; then
        echo "❌ Python仮想環境が見つかりません: ${PROJECT_ROOT}/venv"
        exit 1
    fi
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/venv/bin/activate"
    cd "${PROJECT_ROOT}"
    export ENV=dev
    export PYTHONUNBUFFERED=1

    echo "🚀 開発サーバー起動中..."
    echo "   環境:    開発 (dev)"
    echo "   バインド: 0.0.0.0:${DEV_PORT}"
fi

echo ""
echo "📌 アクセスURL:"
echo "   HTTP  (ローカル):  http://localhost:${DEV_PORT}"
echo "   HTTPS (ローカル):  https://localhost:${DEV_HTTPS_PORT}"
echo "   HTTP  (LAN):       http://${DETECTED_IP}:${DEV_PORT}"
echo "   HTTPS (LAN):       https://${DETECTED_IP}:${DEV_HTTPS_PORT}"
echo "   API ドキュメント:  http://${DETECTED_IP}:${DEV_PORT}/api/docs"
echo "   サーバー情報:      http://${DETECTED_IP}:${DEV_PORT}/api/info"
echo ""

if [[ "${USE_SYSTEMD}" == "false" ]]; then
    echo "停止するには Ctrl+C を押してください"
    echo ""
    # uvicorn で起動（フォアグラウンド・ホットリロード有効）
    exec uvicorn backend.api.main:app \
        --host 0.0.0.0 \
        --port "${DEV_PORT}" \
        --reload \
        --log-level debug
fi
