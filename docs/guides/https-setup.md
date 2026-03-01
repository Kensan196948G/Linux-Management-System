# HTTPS セットアップガイド

Linux Management System の HTTPS/TLS 設定手順を説明します。

---

## 目次

1. [自己署名証明書の生成](#1-自己署名証明書の生成)
2. [Let's Encrypt による本番証明書取得](#2-lets-encrypt-による本番証明書取得)
3. [nginx 設定の切り替え方法](#3-nginx-設定の切り替え方法)
4. [prod.json の ssl_enabled 設定](#4-prodjson-の-ssl_enabled-設定)
5. [トラブルシューティング](#5-トラブルシューティング)

---

## 1. 自己署名証明書の生成

開発・テスト環境向けに、`scripts/generate-ssl-cert.sh` で自己署名証明書を生成します。

### 必要な権限

証明書は `/etc/ssl/adminui/` に配置されるため、`root` または `sudo` 権限が必要です。

### 手順

```bash
# プロジェクトルートで実行
sudo bash scripts/generate-ssl-cert.sh
```

生成されるファイル:

| ファイル | パーミッション | 用途 |
|---|---|---|
| `/etc/ssl/adminui/server.crt` | 644 | SSL 証明書 (公開鍵) |
| `/etc/ssl/adminui/server.key` | 600 | SSL 秘密鍵 |

### 証明書の仕様

- **鍵長**: RSA 4096bit
- **署名アルゴリズム**: SHA256
- **有効期限**: 365日
- **SAN (Subject Alternative Name)**:
  - `DNS: localhost`
  - `DNS: *.localhost`
  - `IP: 127.0.0.1`
  - `IP: 0.0.0.0`

### HTTPS 環境の一括セットアップ

nginx 設定のコピーとリンク作成も含めて一括で行う場合:

```bash
sudo bash scripts/setup-https.sh
sudo systemctl reload nginx
```

---

## 2. Let's Encrypt による本番証明書取得

公開サーバーで HTTPS を使用する場合、Let's Encrypt の無料証明書を推奨します。

### 前提条件

- ドメイン名が取得済みで DNS が設定済みであること
- ポート 80/443 が外部からアクセス可能であること
- Ubuntu 20.04 以降

### certbot インストール

```bash
sudo apt update
sudo apt install -y certbot python3-certbot-nginx
```

### 証明書の取得

```bash
# YOUR_DOMAIN を実際のドメイン名に置き換えてください
sudo certbot --nginx -d YOUR_DOMAIN
```

nginx プラグインを使用しない場合 (スタンドアロンモード):

```bash
# nginx を一時停止する必要があります
sudo systemctl stop nginx
sudo certbot certonly --standalone -d YOUR_DOMAIN
sudo systemctl start nginx
```

### 証明書の自動更新確認

certbot をインストールすると自動更新タイマーが設定されます。

```bash
# 自動更新のテスト (ドライラン)
sudo certbot renew --dry-run

# タイマーの状態確認
sudo systemctl status certbot.timer
```

### nginx 設定を Let's Encrypt 証明書に変更

`config/nginx/adminui.conf` の証明書パスを変更します:

```nginx
# 自己署名証明書 (デフォルト)
ssl_certificate /etc/ssl/adminui/server.crt;
ssl_certificate_key /etc/ssl/adminui/server.key;

# Let's Encrypt に変更する場合 (YOUR_DOMAIN を置き換え)
ssl_certificate /etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem;
```

変更後に設定を反映:

```bash
sudo cp config/nginx/adminui.conf /etc/nginx/sites-available/adminui.conf
sudo nginx -t && sudo systemctl reload nginx
```

---

## 3. nginx 設定の切り替え方法

### HTTPS 設定 (本番・推奨)

`config/nginx/adminui.conf` を使用します (デフォルト)。

```bash
sudo cp config/nginx/adminui.conf /etc/nginx/sites-available/adminui.conf
sudo ln -sf /etc/nginx/sites-available/adminui.conf /etc/nginx/sites-enabled/adminui.conf
sudo nginx -t && sudo systemctl reload nginx
```

### HTTP のみ設定 (開発環境用)

`config/nginx/adminui-http-only.conf` を使用します。

```bash
sudo cp config/nginx/adminui-http-only.conf /etc/nginx/sites-available/adminui.conf
sudo ln -sf /etc/nginx/sites-available/adminui.conf /etc/nginx/sites-enabled/adminui.conf
sudo nginx -t && sudo systemctl reload nginx
```

> ⚠️ HTTP のみの設定は開発環境専用です。本番環境では必ず HTTPS を使用してください。

### default サイトの無効化

nginx のデフォルトサイトが有効な場合、ポート競合が発生することがあります。

```bash
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

---

## 4. prod.json の ssl_enabled 設定

`config/prod.json` の `server.ssl_enabled` は FastAPI アプリ側の SSL 設定です。

nginx がリバースプロキシとして TLS を終端する構成では、**FastAPI 側の SSL は無効** にします。

### 推奨設定 (nginx で TLS 終端)

```json
{
  "server": {
    "ssl_enabled": false,
    "host": "127.0.0.1",
    "http_port": 8000
  },
  "security": {
    "require_https": true
  }
}
```

`require_https: true` を設定すると、HTTP でのアクセスが拒否されます。

### FastAPI が直接 HTTPS を提供する場合

```json
{
  "server": {
    "ssl_enabled": true,
    "ssl_cert": "/etc/ssl/adminui/server.crt",
    "ssl_key": "/etc/ssl/adminui/server.key",
    "https_port": 8443
  }
}
```

---

## 5. トラブルシューティング

### 証明書エラー: ブラウザの警告

自己署名証明書を使用している場合、ブラウザに「安全でない接続」の警告が表示されます。
これは正常な動作です。開発環境では警告を無視して続行できます。

本番環境では Let's Encrypt 等の信頼された CA の証明書を使用してください。

### nginx が起動しない: 証明書ファイルが見つからない

```
nginx: [emerg] cannot load certificate "/etc/ssl/adminui/server.crt"
```

証明書を再生成してください:

```bash
sudo bash scripts/generate-ssl-cert.sh
sudo systemctl restart nginx
```

### ポート 443 が使用中

```bash
sudo ss -tlnp | grep ':443'
```

他のプロセスが 443 を使用している場合、そのプロセスを停止するか、nginx の設定でポートを変更してください。

### nginx 設定テストの失敗

```bash
sudo nginx -t
```

エラーメッセージを確認し、`config/nginx/adminui.conf` の構文を修正してください。

### curl で HTTPS 接続テスト

```bash
# 自己署名証明書の場合 -k で証明書検証をスキップ
curl -k https://localhost/api/health

# 証明書情報を表示
curl -kv https://localhost 2>&1 | grep -E "(SSL|TLS|subject|issuer)"
```

### ログの確認

```bash
# nginx エラーログ
sudo tail -f /var/log/nginx/error.log

# アプリケーションログ
tail -f logs/prod.log
```
