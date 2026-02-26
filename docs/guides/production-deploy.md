# 本番環境デプロイガイド

## システム要件

- **OS**: Ubuntu 20.04 LTS 以上
- **Python**: 3.10 以上
- **Nginx**: 1.18 以上
- **RAM**: 512MB 以上 / **Disk**: 2GB 以上

## インストール手順

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
sudo cp systemd/adminui.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now adminui
```

### 5. sudoers の設定

```bash
sudo cp config/sudoers.d/adminui /etc/sudoers.d/adminui
sudo chmod 440 /etc/sudoers.d/adminui
sudo visudo -c  # 構文チェック
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
