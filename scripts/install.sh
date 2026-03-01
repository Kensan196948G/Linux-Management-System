#!/bin/bash
# ==============================================================================
# install.sh - Linux Management System ワンクリックインストールスクリプト
#
# 対応OS: Ubuntu 22.04 LTS / 24.04 LTS
# 使用方法: sudo bash install.sh [--dev|--prod]
#
# 注意: このスクリプトは root (sudo) で実行してください。
# ==============================================================================

set -euo pipefail

# ------------------------------------------------------------------------------
# 定数
# ------------------------------------------------------------------------------
INSTALL_DIR="/opt/linux-management-system"
SERVICE_USER="svc-adminui"
VENV_DIR="${INSTALL_DIR}/venv"
SBIN_DIR="/usr/local/sbin"
SUDOERS_FILE="/etc/sudoers.d/adminui"
NGINX_AVAILABLE="/etc/nginx/sites-available"
NGINX_ENABLED="/etc/nginx/sites-enabled"
SYSTEMD_DIR="/etc/systemd/system"
MODE="${1:---prod}"

# このスクリプトのあるディレクトリ (install.sh は scripts/ に置かれる)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ------------------------------------------------------------------------------
# ヘルパー関数
# ------------------------------------------------------------------------------
banner() { echo ""; echo "============================================================"; echo "  $*"; echo "============================================================"; echo ""; }
ok()     { echo "  ✅ $*"; }
info()   { echo "  ℹ️  $*"; }
warn()   { echo "  ⚠️  $*"; }
err()    { echo "  ❌ $*" >&2; }

usage() {
    echo "使用方法: sudo bash $0 [--dev|--prod]"
    echo ""
    echo "オプション:"
    echo "  --prod  本番環境インストール (デフォルト)"
    echo "  --dev   開発環境インストール"
    exit 1
}

# ------------------------------------------------------------------------------
# 事前チェック
# ------------------------------------------------------------------------------
preflight_check() {
    banner "事前チェック"

    if [[ "${EUID}" -ne 0 ]]; then
        err "このスクリプトは root 権限が必要です。"
        err "実行方法: sudo bash $0"
        exit 1
    fi

    if ! command -v lsb_release &>/dev/null; then
        err "lsb_release が見つかりません。Ubuntu 22.04/24.04 LTS をご使用ください。"
        exit 1
    fi

    local distro
    distro="$(lsb_release -si)"
    local release
    release="$(lsb_release -sr)"

    if [[ "${distro}" != "Ubuntu" ]]; then
        warn "Ubuntu 以外の OS を検出しました: ${distro} ${release}"
        warn "動作は保証されません。"
    else
        ok "OS: ${distro} ${release}"
    fi

    if [[ "${MODE}" != "--prod" && "${MODE}" != "--dev" ]]; then
        err "不明なオプション: ${MODE}"
        usage
    fi

    ok "モード: ${MODE}"
}

# ------------------------------------------------------------------------------
# Phase 1: システムパッケージインストール
# ------------------------------------------------------------------------------
install_system_packages() {
    banner "Phase 1: システムパッケージインストール"

    apt-get update -q
    apt-get install -y \
        python3 \
        python3-venv \
        python3-pip \
        nginx \
        git \
        curl \
        ca-certificates

    ok "システムパッケージのインストール完了"
}

# ------------------------------------------------------------------------------
# Phase 2: サービスユーザー作成
# ------------------------------------------------------------------------------
create_service_user() {
    banner "Phase 2: サービスユーザー作成"

    if id "${SERVICE_USER}" &>/dev/null; then
        ok "ユーザー ${SERVICE_USER} は既に存在します"
    else
        useradd \
            --system \
            --no-create-home \
            --shell /usr/sbin/nologin \
            --comment "Linux Management System service account" \
            "${SERVICE_USER}"
        ok "ユーザー ${SERVICE_USER} を作成しました"
    fi
}

# ------------------------------------------------------------------------------
# Phase 3: アプリケーションディレクトリ作成・ファイル配置
# ------------------------------------------------------------------------------
install_application() {
    banner "Phase 3: アプリケーションディレクトリ作成"

    mkdir -p "${INSTALL_DIR}"

    # ソースを配置 (既にインストール先にいる場合はスキップ)
    if [[ "${SOURCE_ROOT}" != "${INSTALL_DIR}" ]]; then
        info "ソースファイルを ${INSTALL_DIR} にコピー中..."
        cp -r "${SOURCE_ROOT}/." "${INSTALL_DIR}/"
        ok "ソースファイルのコピー完了"
    else
        ok "インストールディレクトリはソースと同一です (スキップ)"
    fi

    # ディレクトリ作成
    mkdir -p "${INSTALL_DIR}/logs"
    mkdir -p "${INSTALL_DIR}/data"

    # 所有権設定 (logs/data は svc-adminui が書き込む)
    chown -R root:root "${INSTALL_DIR}"
    chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/logs"
    chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/data"

    ok "ディレクトリ作成・権限設定完了"
}

# ------------------------------------------------------------------------------
# Phase 4: Python 仮想環境作成と依存関係インストール
# ------------------------------------------------------------------------------
install_python_dependencies() {
    banner "Phase 4: Python 仮想環境・依存関係インストール"

    if [[ ! -d "${VENV_DIR}" ]]; then
        python3 -m venv "${VENV_DIR}"
        ok "仮想環境を作成しました: ${VENV_DIR}"
    else
        ok "仮想環境は既に存在します: ${VENV_DIR}"
    fi

    "${VENV_DIR}/bin/pip" install --upgrade pip --quiet
    "${VENV_DIR}/bin/pip" install -r "${INSTALL_DIR}/backend/requirements.txt" --quiet
    ok "Python 依存関係のインストール完了"
}

# ------------------------------------------------------------------------------
# Phase 5: sudo ラッパースクリプトのインストール
# ------------------------------------------------------------------------------
install_sudo_wrappers() {
    banner "Phase 5: sudo ラッパースクリプトインストール"

    local wrapper_count=0

    # wrappers/ 配下の .sh ファイルを /usr/local/sbin/ にコピー
    if [[ -d "${INSTALL_DIR}/wrappers" ]]; then
        for wrapper in "${INSTALL_DIR}/wrappers"/adminui-*.sh; do
            [[ -f "${wrapper}" ]] || continue
            local dest
            dest="${SBIN_DIR}/$(basename "${wrapper}")"
            cp "${wrapper}" "${dest}"
            chmod 755 "${dest}"
            chown root:root "${dest}"
            wrapper_count=$((wrapper_count + 1))
        done
        ok "${wrapper_count} 個のラッパースクリプトをインストールしました"
    else
        warn "wrappers/ ディレクトリが見つかりません (スキップ)"
    fi
}

# ------------------------------------------------------------------------------
# Phase 6: sudoers 設定追加
# ------------------------------------------------------------------------------
configure_sudoers() {
    banner "Phase 6: sudoers 設定"

    # sudoers ファイル作成
    cat > "${SUDOERS_FILE}" <<'EOF'
# Linux Management System - sudo allowlist
# 生成: install.sh
# 注意: このファイルは visudo を使わずに直接編集しないでください
#
# svc-adminui は /usr/local/sbin/adminui-*.sh のみ root として実行可能
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-*.sh
EOF

    chmod 440 "${SUDOERS_FILE}"

    # 構文チェック
    if visudo -c -f "${SUDOERS_FILE}" &>/dev/null; then
        ok "sudoers 設定を追加しました: ${SUDOERS_FILE}"
    else
        err "sudoers 構文エラー。${SUDOERS_FILE} を確認してください。"
        rm -f "${SUDOERS_FILE}"
        exit 1
    fi
}

# ------------------------------------------------------------------------------
# Phase 7: systemd サービス登録
# ------------------------------------------------------------------------------
install_systemd_service() {
    banner "Phase 7: systemd サービス登録"

    local svc_name
    if [[ "${MODE}" == "--prod" ]]; then
        svc_name="linux-management-prod"
    else
        svc_name="linux-management-dev"
    fi

    local svc_src="${INSTALL_DIR}/systemd/${svc_name}.service"
    local svc_dst="${SYSTEMD_DIR}/${svc_name}.service"

    if [[ -f "${svc_src}" ]]; then
        cp "${svc_src}" "${svc_dst}"
        chmod 644 "${svc_dst}"
        systemctl daemon-reload
        systemctl enable "${svc_name}"
        ok "systemd サービスを登録・自動起動有効化しました: ${svc_name}"
    else
        warn "サービスファイルが見つかりません: ${svc_src} (スキップ)"
    fi
}

# ------------------------------------------------------------------------------
# Phase 8: nginx 設定インストール
# ------------------------------------------------------------------------------
install_nginx_config() {
    banner "Phase 8: nginx 設定インストール"

    local nginx_src="${INSTALL_DIR}/config/nginx/adminui.conf"
    local nginx_dst="${NGINX_AVAILABLE}/adminui.conf"
    local nginx_link="${NGINX_ENABLED}/adminui.conf"

    if [[ -f "${nginx_src}" ]]; then
        cp "${nginx_src}" "${nginx_dst}"
        ln -sf "${nginx_dst}" "${nginx_link}"
        # デフォルト設定を無効化
        rm -f "${NGINX_ENABLED}/default"
        if nginx -t 2>/dev/null; then
            systemctl reload nginx 2>/dev/null || true
            ok "nginx 設定をインストールしました"
        else
            warn "nginx 設定に問題があります。手動で確認してください: nginx -t"
        fi
    else
        warn "nginx 設定ファイルが見つかりません: ${nginx_src} (スキップ)"
        info "手動で nginx を設定してください: docs/guides/production-deploy.md を参照"
    fi
}

# ------------------------------------------------------------------------------
# Phase 9: 完了メッセージ
# ------------------------------------------------------------------------------
print_completion_message() {
    banner "✅ インストール完了"

    local svc_name
    if [[ "${MODE}" == "--prod" ]]; then
        svc_name="linux-management-prod"
    else
        svc_name="linux-management-dev"
    fi

    echo "  インストールディレクトリ: ${INSTALL_DIR}"
    echo "  サービスユーザー:         ${SERVICE_USER}"
    echo "  sudoers:                  ${SUDOERS_FILE}"
    echo ""
    echo "  次のステップ:"
    echo "  1. 環境変数を設定:"
    echo "     sudo cp ${INSTALL_DIR}/.env.example ${INSTALL_DIR}/.env"
    echo "     sudo \$EDITOR ${INSTALL_DIR}/.env"
    echo ""
    echo "  2. SSL 証明書を設定 (本番の場合):"
    echo "     sudo bash ${INSTALL_DIR}/scripts/setup-https.sh"
    echo ""
    echo "  3. サービスを起動:"
    echo "     sudo systemctl start ${svc_name}"
    echo ""
    echo "  4. ステータス確認:"
    echo "     sudo systemctl status ${svc_name}"
    echo "     sudo journalctl -u ${svc_name} -f"
    echo ""
    echo "  詳細: ${INSTALL_DIR}/docs/guides/production-deploy.md"
}

# ------------------------------------------------------------------------------
# メイン処理
# ------------------------------------------------------------------------------
main() {
    banner "Linux Management System インストール (${MODE})"

    preflight_check
    install_system_packages
    create_service_user
    install_application
    install_python_dependencies
    install_sudo_wrappers
    configure_sudoers
    install_systemd_service
    install_nginx_config
    print_completion_message
}

main
