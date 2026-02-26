#!/bin/bash
set -euo pipefail

# Linux Management System - Nginx HTTPS Setup Script
# Usage: sudo bash scripts/setup-nginx.sh [--self-signed|--cert-path /path/to/cert /path/to/key]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CERT_DIR="/etc/ssl/adminui"
NGINX_CONF_DIR="/etc/nginx/sites-available"
NGINX_ENABLED_DIR="/etc/nginx/sites-enabled"

if [[ $EUID -ne 0 ]]; then
    echo "Error: This script must be run as root" >&2
    exit 1
fi

MODE="${1:---self-signed}"

# Create cert directory
mkdir -p "$CERT_DIR"
chmod 700 "$CERT_DIR"

case "$MODE" in
    --self-signed)
        echo "Generating self-signed certificate..."
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout "$CERT_DIR/server.key" \
            -out "$CERT_DIR/server.crt" \
            -subj "/CN=adminui/O=Linux Management System/C=JP"
        chmod 600 "$CERT_DIR/server.key"
        chmod 644 "$CERT_DIR/server.crt"
        echo "Self-signed certificate created at $CERT_DIR"
        ;;
    --cert-path)
        CERT_FILE="${2:-}"
        KEY_FILE="${3:-}"
        if [[ -z "$CERT_FILE" || -z "$KEY_FILE" ]]; then
            echo "Error: --cert-path requires cert and key paths" >&2
            exit 1
        fi
        cp "$CERT_FILE" "$CERT_DIR/server.crt"
        cp "$KEY_FILE" "$CERT_DIR/server.key"
        chmod 600 "$CERT_DIR/server.key"
        chmod 644 "$CERT_DIR/server.crt"
        echo "Certificate installed from $CERT_FILE"
        ;;
    *)
        echo "Usage: $0 [--self-signed|--cert-path cert.crt cert.key]" >&2
        exit 1
        ;;
esac

# Install Nginx config
cp "$PROJECT_ROOT/config/nginx/adminui.conf" "$NGINX_CONF_DIR/adminui"
if [[ -f "$NGINX_ENABLED_DIR/default" ]]; then
    rm -f "$NGINX_ENABLED_DIR/default"
fi
ln -sf "$NGINX_CONF_DIR/adminui" "$NGINX_ENABLED_DIR/adminui"

# Test and reload
nginx -t
systemctl reload nginx

echo "✅ Nginx HTTPS setup complete. Access: https://$(hostname -f)"
