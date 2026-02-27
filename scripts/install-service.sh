#!/bin/bash
# install-service.sh - Systemdサービス インストール・管理スクリプト
# 使用法:
#   ./install-service.sh dev    -- 開発環境サービスをインストール・有効化
#   ./install-service.sh prod   -- 本番環境サービスをインストール・有効化
#   ./install-service.sh status -- 両サービスの状態表示
#   ./install-service.sh start dev|prod  -- サービス起動
#   ./install-service.sh stop  dev|prod  -- サービス停止
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SYSTEMD_DIR="/etc/systemd/system"

# ─────────────────────────────────────────
# ヘルパー関数
# ─────────────────────────────────────────
banner() { echo ""; echo "========== $* =========="; echo ""; }
ok()  { echo "  ✅ $*"; }
err() { echo "  ❌ $*" >&2; }
warn(){ echo "  ⚠️  $*"; }
info(){ echo "  ℹ️  $*"; }

usage() {
    echo "使用法: $0 <コマンド> [オプション]"
    echo ""
    echo "コマンド:"
    echo "  dev        開発環境サービスをインストール・有効化"
    echo "  prod       本番環境サービスをインストール"
    echo "  status     両サービスの状態を表示"
    echo "  start ENV  サービスを起動 (ENV: dev|prod)"
    echo "  stop  ENV  サービスを停止 (ENV: dev|prod)"
    echo "  restart ENV サービスを再起動"
    echo "  log   ENV  リアルタイムログ表示"
    echo "  uninstall ENV サービスをアンインストール"
    exit 1
}

install_dev() {
    banner "開発環境サービス インストール"

    # IP検出
    info "IPアドレスを検出中..."
    bash "${SCRIPT_DIR}/detect-ip.sh"

    # .env.runtime から IP取得
    DETECTED_IP="127.0.0.1"
    if [[ -f "${PROJECT_ROOT}/.env.runtime" ]]; then
        _ip=$(grep "^DETECTED_IP=" "${PROJECT_ROOT}/.env.runtime" | cut -d'=' -f2 || echo "")
        [[ -n "${_ip}" ]] && DETECTED_IP="${_ip}"
    fi
    DEV_PORT=$(grep "^DEV_PORT=" "${PROJECT_ROOT}/.env" 2>/dev/null | cut -d'=' -f2 || echo "5012")

    # サービスファイルをシステムにコピー
    local svc_src="${PROJECT_ROOT}/systemd/linux-management-dev.service"
    local svc_dst="${SYSTEMD_DIR}/linux-management-dev.service"

    info "サービスファイルをコピー: ${svc_dst}"
    sudo cp "${svc_src}" "${svc_dst}"
    sudo chmod 644 "${svc_dst}"
    ok "サービスファイルをコピーしました"

    # systemd リロード・有効化
    sudo systemctl daemon-reload
    ok "systemd をリロードしました"

    sudo systemctl enable linux-management-dev.service
    ok "自動起動を有効化しました"

    echo ""
    ok "インストール完了"
    echo ""
    echo "  📌 アクセス URL:"
    echo "     http://localhost:${DEV_PORT}"
    echo "     http://${DETECTED_IP}:${DEV_PORT}"
    echo "     http://${DETECTED_IP}:${DEV_PORT}/api/info  ← URL情報"
    echo ""
    echo "  サービス起動:  sudo systemctl start linux-management-dev"
    echo "  ログ確認:      sudo journalctl -u linux-management-dev -f"
}

install_prod() {
    banner "本番環境サービス インストール"

    # svc-adminui ユーザー確認
    if ! id svc-adminui >/dev/null 2>&1; then
        warn "svc-adminui ユーザーが存在しません"
        info "サービスファイルはインストールしますが、起動前にユーザーを作成してください:"
        echo "    sudo useradd -r -s /bin/false -d /opt/linux-management svc-adminui"
    else
        ok "svc-adminui ユーザー確認済み"
    fi

    # /opt/linux-management 存在確認
    if [[ ! -d "/opt/linux-management" ]]; then
        warn "/opt/linux-management ディレクトリが存在しません"
        info "本番デプロイ時に以下で作成してください:"
        echo "    sudo mkdir -p /opt/linux-management"
        echo "    sudo cp -r ${PROJECT_ROOT}/* /opt/linux-management/"
    fi

    local svc_src="${PROJECT_ROOT}/systemd/linux-management-prod.service"
    local svc_dst="${SYSTEMD_DIR}/linux-management-prod.service"

    info "サービスファイルをコピー: ${svc_dst}"
    sudo cp "${svc_src}" "${svc_dst}"
    sudo chmod 644 "${svc_dst}"
    ok "サービスファイルをコピーしました"

    sudo systemctl daemon-reload
    ok "systemd をリロードしました（本番サービスはenableしていません）"

    echo ""
    warn "本番サービスは手動で enable/start してください:"
    echo "    sudo systemctl enable linux-management-prod"
    echo "    sudo systemctl start linux-management-prod"
}

show_status() {
    banner "サービス状態"
    for env in dev prod; do
        local svc="linux-management-${env}"
        echo "--- ${svc} ---"
        if systemctl list-unit-files "${svc}.service" --no-pager 2>/dev/null | grep -q "${svc}"; then
            sudo systemctl status "${svc}.service" --no-pager 2>&1 || true
        else
            echo "  (未インストール)"
        fi
        echo ""
    done
}

service_action() {
    local action="$1"
    local env="${2:-}"
    [[ -z "${env}" ]] && { err "ENV (dev|prod) を指定してください"; usage; }
    local svc="linux-management-${env}"
    sudo systemctl "${action}" "${svc}.service"
    echo ""
    sudo systemctl status "${svc}.service" --no-pager || true
}

show_log() {
    local env="${1:-dev}"
    local svc="linux-management-${env}"
    info "ログを表示中（Ctrl+C で終了）..."
    sudo journalctl -u "${svc}" -f
}

uninstall_service() {
    local env="${1:-}"
    [[ -z "${env}" ]] && { err "ENV (dev|prod) を指定してください"; usage; }
    local svc="linux-management-${env}"
    sudo systemctl stop "${svc}.service" 2>/dev/null || true
    sudo systemctl disable "${svc}.service" 2>/dev/null || true
    sudo rm -f "${SYSTEMD_DIR}/${svc}.service"
    sudo systemctl daemon-reload
    ok "${svc} をアンインストールしました"
}

# ─────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────
CMD="${1:-}"
[[ -z "${CMD}" ]] && usage

case "${CMD}" in
    dev)        install_dev ;;
    prod)       install_prod ;;
    status)     show_status ;;
    start)      service_action start "${2:-}" ;;
    stop)       service_action stop "${2:-}" ;;
    restart)    service_action restart "${2:-}" ;;
    log|logs)   show_log "${2:-dev}" ;;
    uninstall)  uninstall_service "${2:-}" ;;
    *)          err "不明なコマンド: ${CMD}"; usage ;;
esac
