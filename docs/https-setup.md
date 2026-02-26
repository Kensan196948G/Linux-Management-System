# HTTPS / TLS 設定ガイド

Linux Management System を HTTPS で運用するための手順書です。

## 概要

本システムは以下の構成で HTTPS を実現します：

```
[ブラウザ] ←HTTPS→ [Nginx (443)] ←HTTP→ [FastAPI (8000, localhost のみ)]
```

- **Nginx**: TLS 終端・リバースプロキシ
- **FastAPI**: バックエンド API（localhost のみでリッスン）
- **証明書**: 自己署名（開発）または Let's Encrypt（本番）

---

## クイックスタート

### 開発環境（自己署名証明書）

```bash
sudo ./scripts/setup/setup-tls.sh \
  --self-signed \
  --domain adminui.local \
  --yes
```

### 本番環境（Let's Encrypt）

```bash
sudo ./scripts/setup/setup-tls.sh \
  --letsencrypt \
  --domain adminui.example.com \
  --email admin@example.com \
  --yes
```

---

## 前提条件

### 必須パッケージ

```bash
sudo apt-get install -y nginx openssl

# Let's Encrypt を使用する場合
sudo apt-get install -y certbot python3-certbot-nginx
```

### FastAPI バックエンドの起動確認

```bash
systemctl status linux-management-prod
```

---

## 詳細設定

### Nginx 設定ファイル

```
config/nginx/linux-management.conf
```

テンプレート変数：

| 変数 | 説明 | 例 |
|------|------|-----|
| `SERVER_NAME` | ドメイン名 | `adminui.example.com` |
| `SSL_CERT_PATH` | 証明書パス | `/etc/ssl/linux-management/cert.pem` |
| `SSL_KEY_PATH` | 秘密鍵パス | `/etc/ssl/linux-management/key.pem` |
| `BACKEND_PORT` | FastAPI ポート | `8000` |

### TLS バージョン

本設定では以下のみを許可（TLS 1.0/1.1 は無効）：
- TLS 1.2
- TLS 1.3

### セキュリティヘッダー

| ヘッダー | 設定値 |
|---------|--------|
| `Strict-Transport-Security` | `max-age=31536000` (1年) |
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `Content-Security-Policy` | `default-src 'self'; ...` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |

---

## 証明書の管理

### 自己署名証明書

- **場所**: `/etc/ssl/linux-management/`
- **有効期限**: 365 日
- **更新**: `setup-tls.sh --self-signed` を再実行

### Let's Encrypt 証明書

- **自動更新**: `certbot.timer` による自動更新（90日ごと）
- **確認**: `sudo certbot certificates`
- **手動更新**: `sudo certbot renew`
- **自動更新の有効化**: `sudo systemctl enable --now certbot.timer`

---

## FastAPI バックエンド設定

Nginx リバースプロキシ経由の場合、`TrustedHostMiddleware` が有効になります。

### 環境変数（`.env`）

```bash
# 本番環境では localhost のみでリッスン
DEV_IP=127.0.0.1
PROD_PORT=8000
```

### X-Forwarded-For ヘッダー

`X-Forwarded-For` は Nginx から自動設定されます。FastAPI 側では
`TrustedHostMiddleware` を通じて適切に処理されます。

---

## ファイアウォール設定

```bash
# HTTP/HTTPS を開放
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# FastAPI ポートは外部から遮断（localhost のみ）
sudo ufw deny 8000/tcp
```

---

## トラブルシューティング

### Nginx 設定テスト

```bash
sudo nginx -t
```

### Nginx ログ確認

```bash
# アクセスログ
sudo tail -f /var/log/nginx/linux-management-access.log

# エラーログ
sudo tail -f /var/log/nginx/linux-management-error.log
```

### 証明書確認

```bash
sudo openssl x509 -in /etc/ssl/linux-management/cert.pem \
  -noout -subject -dates
```

### TLS 接続テスト

```bash
# 自己署名証明書の場合は -k を追加
curl -k https://adminui.local/api/health
```

### よくあるエラー

| エラー | 原因 | 対処 |
|-------|------|------|
| `502 Bad Gateway` | FastAPI が起動していない | `systemctl start linux-management-prod` |
| 証明書エラー | 自己署名証明書 | ブラウザで例外追加 or `--letsencrypt` を使用 |
| `403 Forbidden` | ファイル権限エラー | `/opt/linux-management/frontend/` の権限確認 |

---

## セキュリティチェックリスト

- [ ] TLS 1.0/1.1 が無効であることを確認
- [ ] 自己署名証明書を本番で使用していないことを確認  
- [ ] `X-Frame-Options: DENY` ヘッダーが送信されていることを確認
- [ ] FastAPI (8000) が外部からアクセスできないことを確認（UFW）
- [ ] Let's Encrypt の自動更新タイマーが有効であることを確認
- [ ] HSTS ヘッダーが送信されていることを確認
