# nginx セットアップガイド

Linux Management System の nginx リバースプロキシ設定手順。

- **本番環境**: nginx:443 → gunicorn:8000 (2 workers)
- **開発環境**: uvicorn:5012 を直接利用（nginx 不要）、または nginx:5013 → uvicorn:5012

---

## 目次

1. [前提条件](#前提条件)
2. [nginx インストール](#nginx-インストール)
3. [SSL 証明書の準備](#ssl-証明書の準備)
4. [設定ファイルの配置](#設定ファイルの配置)
5. [サイトの有効化と反映](#サイトの有効化と反映)
6. [UFW ファイアウォール設定](#ufw-ファイアウォール設定)
7. [動作確認](#動作確認)
8. [自動起動設定](#自動起動設定)
9. [トラブルシューティング](#トラブルシューティング)

---

## 前提条件

- Ubuntu 20.04 / 22.04 / 24.04
- `svc-adminui` ユーザーで gunicorn が稼働中（ポート 8000）
- sudo 権限を持つ管理者アカウント

gunicorn の稼働確認:

```bash
sudo systemctl status linux-management
# または
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool
```

---

## nginx インストール

```bash
sudo apt update
sudo apt install -y nginx

# バージョン確認
nginx -v

# 起動確認
sudo systemctl status nginx
```

---

## SSL 証明書の準備

詳細は `config/ssl/README.md` を参照。

### 開発環境（自己署名）

```bash
sudo openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout /etc/ssl/private/linux-management.key \
    -out    /etc/ssl/certs/linux-management.crt \
    -days   365 \
    -subj   "/C=JP/ST=Tokyo/L=Tokyo/O=LinuxManagement/CN=localhost"

sudo chmod 600 /etc/ssl/private/linux-management.key
sudo chmod 644 /etc/ssl/certs/linux-management.crt
```

### 本番環境（Let's Encrypt）

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.example.com

# nginx が参照するパスにリンク
sudo ln -sf /etc/letsencrypt/live/your-domain.example.com/fullchain.pem \
            /etc/ssl/certs/linux-management.crt
sudo ln -sf /etc/letsencrypt/live/your-domain.example.com/privkey.pem \
            /etc/ssl/private/linux-management.key
```

---

## 設定ファイルの配置

### 1. メイン設定スニペットを適用

`config/nginx/nginx-main-snippets.conf` の内容を `/etc/nginx/nginx.conf` の `http {}` ブロックに追加するか、`conf.d/` にコピーします:

```bash
# 方法 A: conf.d にコピー（推奨）
sudo cp config/nginx/nginx-main-snippets.conf \
        /etc/nginx/conf.d/linux-management-main.conf

# /etc/nginx/nginx.conf に以下が含まれているか確認
grep "conf.d" /etc/nginx/nginx.conf
# → include /etc/nginx/conf.d/*.conf; が存在すること
```

> **重要**: `limit_req_zone` ディレクティブは `http {}` ブロックに定義する必要があります。  
> `nginx-main-snippets.conf` の `limit_req_zone` 行は、`server {}` ブロックではなく `http {}` 内に置いてください。

### 2. 本番サイト設定を配置

```bash
# リポジトリルートで実行
REPO_ROOT=/opt/linux-management  # またはリポジトリのパスに合わせて変更

sudo cp ${REPO_ROOT}/config/nginx/linux-management.conf \
        /etc/nginx/sites-available/linux-management
```

### 3. （オプション）開発用設定を配置

```bash
sudo cp ${REPO_ROOT}/config/nginx/linux-management-dev.conf \
        /etc/nginx/sites-available/linux-management-dev
```

---

## サイトの有効化と反映

```bash
# デフォルトサイトを無効化（競合防止）
sudo rm -f /etc/nginx/sites-enabled/default

# 本番サイトを有効化
sudo ln -s /etc/nginx/sites-available/linux-management \
           /etc/nginx/sites-enabled/linux-management

# （オプション）開発サイトを有効化
# sudo ln -s /etc/nginx/sites-available/linux-management-dev \
#            /etc/nginx/sites-enabled/linux-management-dev

# 設定テスト
sudo nginx -t

# nginx 反映
sudo systemctl reload nginx
```

期待される出力:
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

---

## UFW ファイアウォール設定

```bash
# UFW が有効か確認
sudo ufw status

# HTTP / HTTPS を許可
sudo ufw allow 80/tcp   comment 'HTTP (nginx redirect)'
sudo ufw allow 443/tcp  comment 'HTTPS (nginx production)'

# （オプション）開発 nginx ポートを許可（ローカルのみ推奨）
# sudo ufw allow from 127.0.0.1 to any port 5013

# バックエンド直接アクセスを拒否（外部からのポート 8000 へのアクセスをブロック）
sudo ufw deny 8000/tcp  comment 'Block direct backend access'

# UFW を有効化（まだの場合）
sudo ufw enable

# 状態確認
sudo ufw status verbose
```

期待される出力（抜粋）:
```
80/tcp     ALLOW IN   Anywhere
443/tcp    ALLOW IN   Anywhere
8000/tcp   DENY IN    Anywhere
```

---

## 動作確認

### 1. nginx が起動中か確認

```bash
sudo systemctl status nginx
```

### 2. HTTP → HTTPS リダイレクト確認

```bash
curl -I http://localhost/
# 期待値: HTTP/1.1 301 Moved Permanently
# Location: https://localhost/
```

### 3. HTTPS 接続確認

```bash
# 自己署名証明書の場合は -k（--insecure）を追加
curl -sk https://localhost/ -o /dev/null -w "%{http_code}\n"
# 期待値: 302（ログイン画面へリダイレクト）

curl -sk https://localhost/api/health | python3 -m json.tool
# 期待値: {"status": "ok", ...}
```

### 4. セキュリティヘッダー確認

```bash
curl -skI https://localhost/ | grep -E "Strict-Transport|X-Frame|X-Content|X-XSS|Content-Security"
```

期待される出力:
```
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Content-Security-Policy: default-src 'self'; ...
```

### 5. レート制限確認（ログイン API）

```bash
# 連続リクエストでレート制限が発動することを確認
for i in $(seq 1 10); do
    STATUS=$(curl -sk -o /dev/null -w "%{http_code}" \
        -X POST https://localhost/api/auth/login \
        -H "Content-Type: application/json" \
        -d '{"username":"test","password":"test"}')
    echo "Request $i: HTTP $STATUS"
done
# 6 回目以降は 429 (Too Many Requests) が返ること
```

### 6. WebSocket 接続確認

```bash
# wscat をインストール
npm install -g wscat

# WebSocket 接続テスト（自己署名証明書は --no-check を追加）
wscat --connect wss://localhost/ws/test --no-check
```

### 7. ログ確認

```bash
# アクセスログ
sudo tail -f /var/log/nginx/linux-management-access.log

# エラーログ
sudo tail -f /var/log/nginx/linux-management-error.log
```

---

## 自動起動設定

```bash
# nginx を OS 起動時に自動起動
sudo systemctl enable nginx

# linux-management サービスも自動起動（gunicorn）
sudo systemctl enable linux-management

# 起動順序を確認（nginx は linux-management の後に起動する必要はないが、
# バックエンドが先に起動していることが望ましい）
```

---

## 設定ファイル一覧

| ファイル | 配置先 | 説明 |
|----------|--------|------|
| `config/nginx/linux-management.conf` | `/etc/nginx/sites-available/linux-management` | 本番 HTTPS サイト設定 |
| `config/nginx/linux-management-dev.conf` | `/etc/nginx/sites-available/linux-management-dev` | 開発用サイト設定 |
| `config/nginx/nginx-main-snippets.conf` | `/etc/nginx/conf.d/linux-management-main.conf` | gzip・レート制限・共通設定 |

---

## トラブルシューティング

### nginx が起動しない

```bash
sudo nginx -t                       # 設定構文エラーを確認
sudo journalctl -u nginx -n 50      # systemd ログを確認
sudo cat /var/log/nginx/error.log   # nginx エラーログ
```

### 502 Bad Gateway

バックエンドが起動していない可能性:

```bash
# gunicorn の状態確認
sudo systemctl status linux-management

# ポート 8000 のリッスン確認
ss -tlnp | grep 8000

# 手動でバックエンドを起動
sudo systemctl start linux-management
```

### 403 Forbidden（静的ファイル）

```bash
# ファイルのパーミッションを確認
ls -la /opt/linux-management/frontend/

# nginx ユーザーに読み取り権限を付与
sudo chown -R www-data:www-data /opt/linux-management/frontend/
sudo chmod -R 755 /opt/linux-management/frontend/
```

### レート制限が効かない

`limit_req_zone` が `http {}` ブロックに設定されているか確認:

```bash
grep -n "limit_req_zone" /etc/nginx/nginx.conf /etc/nginx/conf.d/*.conf
sudo nginx -t
```

### SSL 証明書エラー

```bash
# 証明書の有効期限確認
openssl x509 -in /etc/ssl/certs/linux-management.crt -noout -enddate

# 証明書と秘密鍵のペア確認（同じ MD5 なら OK）
openssl x509 -noout -modulus -in /etc/ssl/certs/linux-management.crt | openssl md5
openssl rsa  -noout -modulus -in /etc/ssl/private/linux-management.key | openssl md5
```
