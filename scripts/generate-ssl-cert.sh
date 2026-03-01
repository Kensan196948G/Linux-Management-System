#!/bin/bash
# /etc/ssl/adminui/ へ nginx 用自己署名証明書を生成するスクリプト
# 用途: scripts/setup-https.sh から呼び出される (または単独実行)

set -euo pipefail

CERT_DIR="/etc/ssl/adminui"
CERT_FILE="${CERT_DIR}/server.crt"
KEY_FILE="${CERT_DIR}/server.key"

COUNTRY="JP"
STATE="Tokyo"
CITY="Tokyo"
ORG="Linux Management System"
ORG_UNIT="IT Department"
COMMON_NAME="localhost"
VALID_DAYS=365

echo "=================================="
echo "HTTPS 自己署名証明書生成"
echo "=================================="
echo "証明書ディレクトリ: ${CERT_DIR}"
echo "有効期限: ${VALID_DAYS} 日"
echo ""

# ディレクトリ作成
if [[ ! -d "${CERT_DIR}" ]]; then
    echo "ディレクトリを作成中: ${CERT_DIR}"
    mkdir -p "${CERT_DIR}"
fi

# SAN (Subject Alternative Name) 用の一時設定ファイル
SAN_CONF="$(mktemp /tmp/openssl-san-XXXXXX.cnf)"
trap 'rm -f "${SAN_CONF}"' EXIT

cat > "${SAN_CONF}" << 'EOF'
[req]
default_bits       = 4096
distinguished_name = req_distinguished_name
req_extensions     = v3_req
prompt             = no

[req_distinguished_name]
C  = JP
ST = Tokyo
L  = Tokyo
O  = Linux Management System
OU = IT Department
CN = localhost

[v3_req]
subjectAltName = @alt_names
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = localhost
DNS.2 = *.localhost
IP.1  = 127.0.0.1
IP.2  = 0.0.0.0
EOF

# 変数を展開してから書き込む
sed -i "s/^C  = JP$/C  = ${COUNTRY}/" "${SAN_CONF}"
sed -i "s/^ST = Tokyo$/ST = ${STATE}/" "${SAN_CONF}"
sed -i "s/^L  = Tokyo$/L  = ${CITY}/" "${SAN_CONF}"
sed -i "s/^O  = Linux Management System$/O  = ${ORG}/" "${SAN_CONF}"
sed -i "s/^OU = IT Department$/OU = ${ORG_UNIT}/" "${SAN_CONF}"
sed -i "s/^CN = localhost$/CN = ${COMMON_NAME}/" "${SAN_CONF}"

echo "🔐 RSA 4096bit 自己署名証明書を生成中..."

openssl req -x509 \
    -newkey rsa:4096 \
    -keyout "${KEY_FILE}" \
    -out "${CERT_FILE}" \
    -days "${VALID_DAYS}" \
    -nodes \
    -sha256 \
    -config "${SAN_CONF}" \
    -extensions v3_req

# 権限設定: cert=644, key=600
chmod 644 "${CERT_FILE}"
chmod 600 "${KEY_FILE}"

echo ""
echo "✅ 証明書を生成しました"
echo "  証明書: ${CERT_FILE} (644)"
echo "  秘密鍵: ${KEY_FILE} (600)"
echo ""

# 証明書情報を表示
echo "証明書情報:"
openssl x509 -in "${CERT_FILE}" -text -noout \
    | grep -E "(Subject:|Issuer:|Not Before|Not After|DNS:|IP Address:)" \
    || true

echo ""
echo "=================================="
echo "✅ 完了"
echo "=================================="
