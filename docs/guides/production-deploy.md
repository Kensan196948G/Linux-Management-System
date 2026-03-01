# 本番環境デプロイガイド

## システム要件

- **OS**: Ubuntu 22.04 LTS / 24.04 LTS (推奨)
- **Python**: 3.11 以上
- **Nginx**: 1.18 以上
- **RAM**: 512MB 以上 / **Disk**: 2GB 以上

---

## クイックインストール (推奨)

Ubuntu 22.04/24.04 LTS では `install.sh` でワンコマンドセットアップが可能です。

```bash
# リポジトリをクローン
git clone https://github.com/Kensan196948G/Linux-Management-System.git
cd Linux-Management-System

# 本番環境インストール (root 必須)
sudo bash scripts/install.sh --prod

# 開発環境インストール
sudo bash scripts/install.sh --dev
```

インストール先: `/opt/linux-management-system`
サービスユーザー: `svc-adminui`

インストール後の初期設定:

```bash
# 1. 環境変数を設定
sudo cp /opt/linux-management-system/.env.example /opt/linux-management-system/.env
sudo $EDITOR /opt/linux-management-system/.env  # JWT_SECRET を必ず変更

# 2. SSL 証明書を設定
sudo bash /opt/linux-management-system/scripts/setup-https.sh

# 3. サービスを起動
sudo systemctl start linux-management-prod
sudo systemctl status linux-management-prod
```

---

## .deb パッケージのビルドとインストール

```bash
# ビルド依存関係インストール
sudo apt install -y debhelper devscripts

# パッケージビルド (プロジェクトルートで実行)
dpkg-buildpackage -us -uc -b

# または簡易ビルド
dpkg-deb --build . /tmp/linux-management-system_0.19.0_all.deb

# インストール
sudo dpkg -i /tmp/linux-management-system_0.19.0_all.deb
sudo apt-get install -f  # 依存関係の解決
```

---

## 手動インストール手順

### 1. Python 仮想環境のセットアップ

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
```

### 2. 環境変数の設定

```bash
cp .env.example .env
# .env を編集して JWT_SECRET 等を設定
$EDITOR .env
```

### 3. Nginx のセットアップ

```bash
sudo apt install -y nginx
sudo bash scripts/setup-nginx.sh --self-signed
# 本番証明書を使用する場合:
# sudo bash scripts/setup-nginx.sh --cert-path /path/to/cert.crt /path/to/key
```

### 4. systemd サービスの登録

```bash
sudo cp systemd/linux-management-prod.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now linux-management-prod
```

### 5. sudoers の設定

```bash
sudo cp config/sudoers.d/adminui /etc/sudoers.d/adminui
sudo chmod 440 /etc/sudoers.d/adminui
sudo visudo -c  # 構文チェック
```

---

## ポストインストール設定

### HTTPS 証明書 (Let's Encrypt)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.example.com
sudo systemctl reload nginx
```

### HTTPS 証明書 (自己署名)

```bash
sudo bash scripts/setup-https.sh
```

### ファイアウォール (ufw)

```bash
sudo ufw allow 443/tcp
sudo ufw deny 8000/tcp  # バックエンドポートは外部非公開
sudo ufw enable
```

---

## アップグレード手順

```bash
cd /opt/linux-management-system

# 1. バックアップ
sudo cp -r data data.bak.$(date +%Y%m%d)

# 2. 最新コードを取得
sudo git pull origin main

# 3. 依存関係を更新
sudo venv/bin/pip install -r backend/requirements.txt

# 4. sudo ラッパーを更新
sudo cp wrappers/adminui-*.sh /usr/local/sbin/
sudo chmod 755 /usr/local/sbin/adminui-*.sh

# 5. サービスを再起動
sudo systemctl restart linux-management-prod
```

---

## アンインストール手順

```bash
# 確認プロンプトあり (データ保持)
sudo bash /opt/linux-management-system/scripts/uninstall.sh --keep-data

# 完全削除 (確認なし)
sudo bash /opt/linux-management-system/scripts/uninstall.sh --yes

# アプリケーションファイルも削除
sudo rm -rf /opt/linux-management-system
```

## セキュリティチェックリスト

- [ ] **JWT_SECRET**: 32文字以上のランダム文字列を設定
- [ ] **HTTPS必須**: HTTP アクセスは 308 リダイレクト済み（設定確認）
- [ ] **sudoers**: `config/sudoers.d/adminui` のみ適用、余分な権限なし
- [ ] **ファイアウォール**: 443/tcp のみ外部公開、8000/tcp はローカルのみ
- [ ] **サービス実行ユーザー**: `svc-adminui`（root 不可）
- [ ] **証明書の期限**: `openssl x509 -enddate -noout -in /etc/ssl/adminui/server.crt`

```bash
# ファイアウォール設定例 (ufw)
sudo ufw allow 443/tcp
sudo ufw deny 8000/tcp
sudo ufw enable
```

## ログ・監視

| ログ種別 | パス |
|---------|------|
| アプリログ | `logs/app.log` |
| 監査ログ | `logs/audit.log` |
| Nginx アクセス | `/var/log/nginx/access.log` |
| Nginx エラー | `/var/log/nginx/error.log` |
| systemd ログ | `journalctl -u adminui -f` |

```bash
# サービス状態確認
systemctl status adminui nginx
```
