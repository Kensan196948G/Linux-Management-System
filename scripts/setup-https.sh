#!/bin/bash
# HTTPS 環境セットアップスクリプト
# 自己署名証明書の生成 → nginx 設定コピー → シンボリックリンク作成 → nginx 設定テスト

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

CERT_FILE="/etc/ssl/adminui/server.crt"
KEY_FILE="/etc/ssl/adminui/server.key"
NGINX_CONF_SRC="${PROJECT_ROOT}/config/nginx/adminui.conf"
NGINX_AVAILABLE="/etc/nginx/sites-available/adminui.conf"
NGINX_ENABLED="/etc/nginx/sites-enabled/adminui.conf"

echo "=========================================="
echo "HTTPS 環境セットアップ"
echo "=========================================="

# ----------------------------------------
# 1. 証明書生成 (存在しない場合のみ)
# ----------------------------------------
if [[ -f "${CERT_FILE}" && -f "${KEY_FILE}" ]]; then
    echo "✅ 証明書は既に存在します: ${CERT_FILE}"
    echo "   スキップします (再生成する場合は scripts/generate-ssl-cert.sh を直接実行してください)"
else
    echo "🔐 自己署名証明書を生成します..."
    bash "${SCRIPT_DIR}/generate-ssl-cert.sh"
fi

echo ""

# ----------------------------------------
# 2. nginx 設定を sites-available にコピー
# ----------------------------------------
if [[ ! -f "${NGINX_CONF_SRC}" ]]; then
    echo "❌ nginx 設定ファイルが見つかりません: ${NGINX_CONF_SRC}" >&2
    exit 1
fi

echo "📋 nginx 設定をコピー: ${NGINX_CONF_SRC} → ${NGINX_AVAILABLE}"
cp "${NGINX_CONF_SRC}" "${NGINX_AVAILABLE}"
echo "✅ コピー完了"

echo ""

# ----------------------------------------
# 3. sites-enabled にシンボリックリンク作成
# ----------------------------------------
if [[ -L "${NGINX_ENABLED}" ]]; then
    echo "🔗 シンボリックリンクが既に存在します: ${NGINX_ENABLED}"
    echo "   既存のリンクを更新します..."
    ln -sf "${NGINX_AVAILABLE}" "${NGINX_ENABLED}"
elif [[ -f "${NGINX_ENABLED}" ]]; then
    echo "⚠️  ${NGINX_ENABLED} は通常ファイルです。バックアップ後に置換します..."
    mv "${NGINX_ENABLED}" "${NGINX_ENABLED}.bak"
    ln -s "${NGINX_AVAILABLE}" "${NGINX_ENABLED}"
else
    ln -s "${NGINX_AVAILABLE}" "${NGINX_ENABLED}"
fi
echo "✅ シンボリックリンク作成完了: ${NGINX_ENABLED} → ${NGINX_AVAILABLE}"

echo ""

# ----------------------------------------
# 4. nginx 設定テスト
# ----------------------------------------
echo "🧪 nginx 設定をテスト中..."
if nginx -t 2>&1; then
    echo "✅ nginx 設定テスト成功"
else
    echo "❌ nginx 設定テストに失敗しました" >&2
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ セットアップ完了"
echo ""
echo "nginx をリロードするには以下を実行してください:"
echo "  sudo systemctl reload nginx"
echo "  または"
echo "  sudo nginx -s reload"
echo "=========================================="
