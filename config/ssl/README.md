# SSL 証明書 セットアップガイド

Linux Management System で使用する SSL/TLS 証明書の生成・配置手順。

---

## ディレクトリ構成

```
/etc/ssl/certs/   linux-management.crt   # 証明書（公開鍵）
/etc/ssl/private/ linux-management.key   # 秘密鍵（root のみ読み取り可）
```

---

## 方法 1: 自己署名証明書（開発・テスト環境）

> ⚠️ 自己署名証明書はブラウザに警告が表示されます。  
> 開発・内部テスト目的にのみ使用してください。

### 生成コマンド

```bash
# 作業ディレクトリを作成
sudo mkdir -p /etc/ssl/certs /etc/ssl/private

# 自己署名証明書を生成（有効期限 365 日）
sudo openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout /etc/ssl/private/linux-management.key \
    -out    /etc/ssl/certs/linux-management.crt \
    -days   365 \
    -subj   "/C=JP/ST=Tokyo/L=Tokyo/O=LinuxManagement/CN=localhost"

# パーミッション設定
sudo chmod 600 /etc/ssl/private/linux-management.key
sudo chmod 644 /etc/ssl/certs/linux-management.crt
```

### SAN (Subject Alternative Name) 付き自己署名証明書（推奨）

```bash
# OpenSSL 設定ファイルを一時作成
cat > /tmp/openssl-san.cnf << 'EOF'
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no

[req_distinguished_name]
C  = JP
ST = Tokyo
L  = Tokyo
O  = Linux Management System
CN = localhost

[v3_req]
subjectAltName = @alt_names
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = localhost
DNS.2 = *.localhost
IP.1  = 127.0.0.1
IP.2  = ::1
EOF

# 証明書生成
sudo openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout /etc/ssl/private/linux-management.key \
    -out    /etc/ssl/certs/linux-management.crt \
    -days   365 \
    -config /tmp/openssl-san.cnf

# パーミッション設定
sudo chmod 600 /etc/ssl/private/linux-management.key
sudo chmod 644 /etc/ssl/certs/linux-management.crt

# 一時ファイル削除
rm /tmp/openssl-san.cnf
```

### 証明書の確認

```bash
# 証明書情報を表示
openssl x509 -in /etc/ssl/certs/linux-management.crt -text -noout | head -30

# 有効期限を確認
openssl x509 -in /etc/ssl/certs/linux-management.crt -noout -enddate

# 秘密鍵と証明書の整合性を確認（同じ値なら OK）
openssl x509 -noout -modulus -in /etc/ssl/certs/linux-management.crt | openssl md5
openssl rsa  -noout -modulus -in /etc/ssl/private/linux-management.key | openssl md5
```

### ブラウザへの登録（オプション）

Chrome / Edge の場合:
1. `chrome://settings/certificates` を開く
2. 「認証機関」→「インポート」
3. `/etc/ssl/certs/linux-management.crt` を選択
4. 「このサーバーを識別するための証明書を信頼します」にチェック

Firefox の場合:
1. `about:preferences#privacy` を開く
2. 「証明書を表示」→「認証局証明書」→「インポート」
3. `/etc/ssl/certs/linux-management.crt` を選択

---

## 方法 2: Let's Encrypt（本番環境、公開ドメイン必須）

### 前提条件

- 公開ドメインを所有していること
- ポート 80/443 がインターネットに公開されていること
- `certbot` がインストールされていること

### Certbot インストール

```bash
sudo apt update
sudo apt install -y certbot python3-certbot-nginx
```

### 証明書取得（nginx プラグイン使用）

```bash
# ドメインを置換して実行（例: adminui.example.com）
sudo certbot --nginx -d your-domain.example.com

# 複数ドメインの場合
sudo certbot --nginx -d adminui.example.com -d www.adminui.example.com
```

### 取得後の nginx 設定パスへのシンボリックリンク

```bash
DOMAIN="your-domain.example.com"

# nginx 設定が参照するパスにシンボリックリンクを作成
sudo ln -sf /etc/letsencrypt/live/${DOMAIN}/fullchain.pem \
            /etc/ssl/certs/linux-management.crt
sudo ln -sf /etc/letsencrypt/live/${DOMAIN}/privkey.pem \
            /etc/ssl/private/linux-management.key

# nginx 再起動
sudo systemctl reload nginx
```

### 自動更新の設定

```bash
# certbot の自動更新タイマーを確認
sudo systemctl status certbot.timer

# 手動で更新テスト
sudo certbot renew --dry-run

# 更新後に nginx を自動リロードするフック（推奨）
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh << 'EOF'
#!/bin/bash
systemctl reload nginx
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

---

## 方法 3: 既存の商用証明書を配置

```bash
# 証明書ファイルを配置（ファイル名を合わせること）
sudo cp your-cert.crt     /etc/ssl/certs/linux-management.crt
sudo cp your-private.key  /etc/ssl/private/linux-management.key

# 中間証明書がある場合は結合
sudo cat your-cert.crt intermediate.crt > /tmp/fullchain.crt
sudo cp /tmp/fullchain.crt /etc/ssl/certs/linux-management.crt

# パーミッション設定
sudo chmod 644 /etc/ssl/certs/linux-management.crt
sudo chmod 600 /etc/ssl/private/linux-management.key
sudo chown root:root /etc/ssl/private/linux-management.key

# nginx 設定テストと反映
sudo nginx -t && sudo systemctl reload nginx
```

---

## トラブルシューティング

### nginx が起動しない（SSL 関連エラー）

```bash
# エラーログを確認
sudo journalctl -u nginx -n 50
sudo nginx -t

# よくあるエラーと対処
# "cannot load certificate": ファイルパスと権限を確認
ls -la /etc/ssl/certs/linux-management.crt
ls -la /etc/ssl/private/linux-management.key

# "permission denied": 秘密鍵の権限
sudo chmod 600 /etc/ssl/private/linux-management.key
sudo chown root:root /etc/ssl/private/linux-management.key
```

### ブラウザで証明書エラーが出る

| エラー | 原因 | 対処 |
|--------|------|------|
| `NET::ERR_CERT_AUTHORITY_INVALID` | 自己署名証明書 | ブラウザに CA として登録 |
| `NET::ERR_CERT_COMMON_NAME_INVALID` | CN/SAN がホスト名と不一致 | SAN 付き証明書を再生成 |
| `NET::ERR_CERT_DATE_INVALID` | 証明書期限切れ | `certbot renew` または再生成 |
