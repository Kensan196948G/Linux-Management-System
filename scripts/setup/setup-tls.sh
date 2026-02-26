#!/bin/bash
# ==============================================================================
# setup-tls.sh - Linux Management System TLS/HTTPS セットアップスクリプト
#
# 機能:
#   1. 自己署名証明書の生成（開発・テスト用）
#   2. Let's Encrypt 証明書の取得（本番用）
#   3. Nginx 設定ファイルのデプロイ
#   4. Nginx の設定検証と再起動
#
# 使用方法:
#   ./setup-tls.sh --self-signed --domain adminui.local
#   ./setup-tls.sh --letsencrypt --domain adminui.example.com --email admin@example.com
#   ./setup-tls.sh --dry-run --self-signed --domain adminui.local
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - 証明書は /etc/ssl/linux-management/ に保存（600 権限）
#   - Nginx 設定は visudo 同様 --test オプションで検証してから適用
# ==============================================================================

set -euo pipefail

# ==============================================================================
# 定数
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
NGINX_CONFIG_SRC="${PROJECT_ROOT}/config/nginx/linux-management.conf"
NGINX_SITES_AVAILABLE="/etc/nginx/sites-available"
NGINX_SITES_ENABLED="/etc/nginx/sites-enabled"
NGINX_CONF_NAME="linux-management"
CERT_DIR="/etc/ssl/linux-management"
BACKEND_PORT="${BACKEND_PORT:-8000}"

# ==============================================================================
# カラー出力
# ==============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
step()    { echo -e "\n${BLUE}==>${NC} $*"; }

# ==============================================================================
# オプション解析
# ==============================================================================

DRY_RUN=false
MODE=""        # self-signed | letsencrypt
DOMAIN=""
EMAIL=""
YES=false

usage() {
    cat <<EOF
使用方法:
  $0 --self-signed --domain <DOMAIN> [--dry-run] [--yes]
  $0 --letsencrypt --domain <DOMAIN> --email <EMAIL> [--dry-run] [--yes]
  $0 --status

オプション:
  --self-signed       自己署名証明書を生成（開発・テスト用）
  --letsencrypt       Let's Encrypt 証明書を取得（本番用）
  --domain DOMAIN     ドメイン名（必須）
  --email EMAIL       Let's Encrypt アカウントメール（--letsencrypt 必須）
  --dry-run           実際の変更を行わずに検証のみ
  --yes               確認プロンプトをスキップ
  --status            現在のTLS設定状態を表示

例:
  # 開発環境（自己署名）
  $0 --self-signed --domain adminui.local

  # 本番環境（Let's Encrypt）
  $0 --letsencrypt --domain adminui.example.com --email admin@example.com

  # ドライラン
  $0 --dry-run --self-signed --domain adminui.local
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --self-signed)  MODE="self-signed"; shift ;;
        --letsencrypt)  MODE="letsencrypt"; shift ;;
        --domain)       DOMAIN="$2"; shift 2 ;;
        --email)        EMAIL="$2"; shift 2 ;;
        --dry-run)      DRY_RUN=true; shift ;;
        --yes)          YES=true; shift ;;
        --status)       MODE="status"; shift ;;
        -h|--help)      usage; exit 0 ;;
        *)              error "Unknown option: $1"; usage; exit 1 ;;
    esac
done

# ==============================================================================
# ドライラン用ラッパー
# ==============================================================================

run_cmd() {
    if $DRY_RUN; then
        echo "  [DRY-RUN] $*"
    else
        "$@"
    fi
}

# ==============================================================================
# ステータス表示
# ==============================================================================

show_status() {
    step "TLS 設定状態"

    # Nginx 設定
    if [[ -f "${NGINX_SITES_ENABLED}/${NGINX_CONF_NAME}" ]]; then
        success "Nginx 設定: 有効 (${NGINX_SITES_ENABLED}/${NGINX_CONF_NAME})"
    else
        warn "Nginx 設定: 無効"
    fi

    # 証明書確認
    if [[ -f "${CERT_DIR}/cert.pem" ]]; then
        success "証明書: ${CERT_DIR}/cert.pem"
        openssl x509 -in "${CERT_DIR}/cert.pem" -noout -subject -dates 2>/dev/null | sed 's/^/    /'
    else
        warn "証明書: 見つかりません (${CERT_DIR}/cert.pem)"
    fi

    # Let's Encrypt
    if command -v certbot &>/dev/null; then
        if [[ -d "/etc/letsencrypt/live" ]] && ls /etc/letsencrypt/live/ 2>/dev/null | grep -q .; then
            success "Let's Encrypt 証明書が存在します"
            certbot certificates 2>/dev/null | grep -E "Domains:|Expiry Date:" | sed 's/^/    /' || true
        else
            info "Let's Encrypt 証明書: なし"
        fi
    else
        info "certbot: インストールされていません"
    fi

    # Nginx 起動状態
    if systemctl is-active --quiet nginx 2>/dev/null; then
        success "Nginx: 起動中"
    else
        warn "Nginx: 停止中"
    fi
}

# ==============================================================================
# 前提条件チェック
# ==============================================================================

check_prerequisites() {
    step "前提条件チェック"

    local errors=0

    # root 権限確認
    if [[ $EUID -ne 0 ]]; then
        error "このスクリプトは root 権限で実行してください"
        error "  sudo $0 $*"
        ((errors++))
    fi

    # Nginx インストール確認
    if ! command -v nginx &>/dev/null; then
        error "nginx がインストールされていません"
        error "  sudo apt-get install -y nginx"
        ((errors++))
    else
        success "nginx: $(nginx -v 2>&1 | head -1)"
    fi

    # openssl 確認
    if ! command -v openssl &>/dev/null; then
        error "openssl がインストールされていません"
        ((errors++))
    else
        success "openssl: $(openssl version)"
    fi

    # Let's Encrypt の場合は certbot 確認
    if [[ "$MODE" == "letsencrypt" ]]; then
        if ! command -v certbot &>/dev/null; then
            error "certbot がインストールされていません"
            error "  sudo apt-get install -y certbot python3-certbot-nginx"
            ((errors++))
        else
            success "certbot: $(certbot --version 2>&1 | head -1)"
        fi
    fi

    # Nginx 設定ソースファイル確認
    if [[ ! -f "$NGINX_CONFIG_SRC" ]]; then
        error "Nginx 設定ファイルが見つかりません: $NGINX_CONFIG_SRC"
        ((errors++))
    else
        success "Nginx 設定ソース: $NGINX_CONFIG_SRC"
    fi

    if [[ $errors -gt 0 ]]; then
        error "${errors} 件のエラーがあります。修正後に再実行してください。"
        exit 1
    fi
}

# ==============================================================================
# 自己署名証明書の生成
# ==============================================================================

generate_self_signed() {
    step "自己署名証明書の生成: ${DOMAIN}"

    local cert_path="${CERT_DIR}/cert.pem"
    local key_path="${CERT_DIR}/key.pem"

    # ディレクトリ作成
    run_cmd install -d -m 750 -o root -g root "${CERT_DIR}"

    if $DRY_RUN; then
        info "証明書生成（dry-run）: ${cert_path}"
        info "秘密鍵生成（dry-run）: ${key_path}"
        return 0
    fi

    # SAN（Subject Alternative Name）付き自己署名証明書を生成
    local san_conf
    san_conf=$(mktemp /tmp/san-openssl-XXXXXX.cnf)
    cat > "$san_conf" <<EOF
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no

[req_distinguished_name]
CN = ${DOMAIN}
O = Linux Management System
OU = System Administration
C = JP

[v3_req]
subjectAltName = @alt_names
keyUsage = keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = ${DOMAIN}
DNS.2 = localhost
IP.1 = 127.0.0.1
EOF

    # 4096-bit RSA、有効期限 365 日
    openssl req -x509 -nodes \
        -newkey rsa:4096 \
        -keyout "${key_path}" \
        -out "${cert_path}" \
        -days 365 \
        -config "$san_conf" 2>/dev/null

    rm -f "$san_conf"

    # 権限設定（秘密鍵は root のみ読み取り可能）
    chmod 644 "${cert_path}"
    chmod 600 "${key_path}"
    chown root:root "${cert_path}" "${key_path}"

    success "自己署名証明書を生成しました"
    info "  証明書: ${cert_path}"
    info "  秘密鍵: ${key_path}"
    warn "※ 自己署名証明書はブラウザに警告が表示されます（開発環境専用）"
}

# ==============================================================================
# Let's Encrypt 証明書の取得
# ==============================================================================

obtain_letsencrypt() {
    step "Let's Encrypt 証明書の取得: ${DOMAIN}"

    if [[ -z "$EMAIL" ]]; then
        error "--email オプションが必要です"
        exit 1
    fi

    if $DRY_RUN; then
        info "certbot certonly (dry-run): --domain ${DOMAIN} --email ${EMAIL}"
        return 0
    fi

    # Certbot で証明書取得（スタンドアロンモード）
    certbot certonly \
        --nginx \
        --non-interactive \
        --agree-tos \
        --email "${EMAIL}" \
        --domain "${DOMAIN}" \
        --keep-until-expiring

    local cert_path="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
    local key_path="/etc/letsencrypt/live/${DOMAIN}/privkey.pem"

    # シンボリックリンクを作成（設定ファイルからの参照を統一）
    install -d -m 750 -o root -g root "${CERT_DIR}"
    ln -sf "${cert_path}" "${CERT_DIR}/cert.pem"
    ln -sf "${key_path}" "${CERT_DIR}/key.pem"

    success "Let's Encrypt 証明書を取得しました"
    info "  証明書: ${CERT_DIR}/cert.pem -> ${cert_path}"

    # 自動更新タイマーの確認
    if systemctl is-enabled --quiet certbot.timer 2>/dev/null; then
        success "certbot.timer: 自動更新が有効です"
    else
        warn "certbot.timer が無効です"
        warn "  sudo systemctl enable --now certbot.timer"
    fi
}

# ==============================================================================
# Nginx 設定のデプロイ
# ==============================================================================

deploy_nginx_config() {
    step "Nginx 設定のデプロイ"

    local cert_path="${CERT_DIR}/cert.pem"
    local key_path="${CERT_DIR}/key.pem"

    # Let's Encrypt の場合はパスを変更
    if [[ "$MODE" == "letsencrypt" ]]; then
        cert_path="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
        key_path="/etc/letsencrypt/live/${DOMAIN}/privkey.pem"
    fi

    # テンプレートから設定ファイルを生成
    local dest="${NGINX_SITES_AVAILABLE}/${NGINX_CONF_NAME}"

    if $DRY_RUN; then
        info "設定ファイル生成（dry-run）: ${dest}"
        info "  SERVER_NAME=${DOMAIN}"
        info "  SSL_CERT_PATH=${cert_path}"
        info "  SSL_KEY_PATH=${key_path}"
        info "  BACKEND_PORT=${BACKEND_PORT}"
        return 0
    fi

    # テンプレート変数を置換して設定ファイルを生成
    sed \
        -e "s|SERVER_NAME|${DOMAIN}|g" \
        -e "s|SSL_CERT_PATH|${cert_path}|g" \
        -e "s|SSL_KEY_PATH|${key_path}|g" \
        -e "s|BACKEND_PORT|${BACKEND_PORT}|g" \
        "${NGINX_CONFIG_SRC}" > "${dest}"

    chmod 644 "${dest}"
    success "Nginx 設定ファイル: ${dest}"

    # sites-enabled にシンボリックリンク
    local link="${NGINX_SITES_ENABLED}/${NGINX_CONF_NAME}"
    if [[ ! -L "$link" ]]; then
        ln -s "${dest}" "${link}"
        success "シンボリックリンク: ${link}"
    fi

    # デフォルト設定を無効化（HTTPSへのリダイレクトに干渉するため）
    if [[ -L "${NGINX_SITES_ENABLED}/default" ]]; then
        warn "デフォルト設定を無効化します: ${NGINX_SITES_ENABLED}/default"
        rm -f "${NGINX_SITES_ENABLED}/default"
    fi

    # Nginx 設定テスト
    nginx -t
    success "Nginx 設定テスト: OK"

    # Nginx 再読み込み
    systemctl reload nginx
    success "Nginx を再読み込みしました"
}

# ==============================================================================
# 確認プロンプト
# ==============================================================================

confirm() {
    if $YES || $DRY_RUN; then
        return 0
    fi
    echo
    read -rp "$* [y/N] " reply
    case "$reply" in
        [yY][eE][sS]|[yY]) return 0 ;;
        *) echo "中止しました。"; exit 0 ;;
    esac
}

# ==============================================================================
# メイン処理
# ==============================================================================

main() {
    echo "======================================================================"
    echo " Linux Management System - TLS/HTTPS セットアップ"
    echo "======================================================================"

    if [[ "$MODE" == "status" ]]; then
        show_status
        exit 0
    fi

    if [[ -z "$MODE" ]]; then
        error "モードを指定してください: --self-signed または --letsencrypt"
        usage
        exit 1
    fi

    if [[ -z "$DOMAIN" ]]; then
        error "--domain オプションが必要です"
        usage
        exit 1
    fi

    if $DRY_RUN; then
        warn "=== ドライランモード（実際の変更は行いません） ==="
    fi

    info "モード: ${MODE}"
    info "ドメイン: ${DOMAIN}"
    info "バックエンドポート: ${BACKEND_PORT}"
    [[ -n "$EMAIL" ]] && info "メール: ${EMAIL}"

    confirm "TLS セットアップを開始しますか？"

    # 前提条件チェック
    check_prerequisites

    # 証明書取得
    case "$MODE" in
        self-signed)  generate_self_signed ;;
        letsencrypt)  obtain_letsencrypt ;;
    esac

    # Nginx 設定デプロイ
    deploy_nginx_config

    echo
    echo "======================================================================"
    success "TLS セットアップが完了しました"
    echo "======================================================================"
    echo
    info "アクセス URL: https://${DOMAIN}"
    echo
    if [[ "$MODE" == "self-signed" ]]; then
        warn "自己署名証明書を使用しているため、ブラウザに警告が表示されます。"
        warn "本番環境では --letsencrypt オプションを使用してください。"
    fi
}

main "$@"
