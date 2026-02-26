# systemd サービス管理ガイド

**Linux Management System の自動起動設定**

---

## 📋 概要

systemd サービスとして登録することで、機器再起動後も自動的にサービスが起動します。

---

## 🚀 クイックスタート

### 開発環境のインストール

```bash
# インストール
sudo ./scripts/install-service.sh dev

# 起動
sudo systemctl start linux-management-dev

# 状態確認
sudo systemctl status linux-management-dev

# ログ確認
sudo journalctl -u linux-management-dev -f
```

### 本番環境のインストール

```bash
# 事前準備（重要！）
sudo useradd -r -s /bin/bash -d /opt/linux-management svc-adminui
sudo mkdir -p /opt/linux-management
sudo cp -r /mnt/LinuxHDD/Linux-Management-Systm/* /opt/linux-management/
sudo chown -R svc-adminui:svc-adminui /opt/linux-management

# インストール
sudo ./scripts/install-service.sh prod

# 起動
sudo systemctl start linux-management-prod

# 自動起動確認
sudo systemctl is-enabled linux-management-prod
```

---

## 📂 サービスファイル

### 開発環境（linux-management-dev.service）

| 項目 | 設定値 |
|------|--------|
| **ユーザー** | kensan（現在のユーザー） |
| **ワーキングディレクトリ** | /mnt/LinuxHDD/Linux-Management-Systm |
| **ポート** | 5012 (HTTP), 5443 (HTTPS) |
| **サーバー** | uvicorn（シングルプロセス） |
| **再起動** | on-failure（失敗時のみ） |

### 本番環境（linux-management-prod.service）

| 項目 | 設定値 |
|------|--------|
| **ユーザー** | svc-adminui（専用ユーザー） |
| **ワーキングディレクトリ** | /opt/linux-management |
| **ポート** | 8000 (HTTP), 8443 (HTTPS) |
| **サーバー** | gunicorn + uvicorn（4 workers） |
| **再起動** | always（常に再起動） |
| **セキュリティ** | 強化設定有効 |

---

## ⚙️ サービス管理コマンド

### 基本操作

```bash
# 起動
sudo systemctl start linux-management-dev

# 停止
sudo systemctl stop linux-management-dev

# 再起動
sudo systemctl restart linux-management-dev

# 状態確認
sudo systemctl status linux-management-dev

# ログ確認（リアルタイム）
sudo journalctl -u linux-management-dev -f

# ログ確認（最新100行）
sudo journalctl -u linux-management-dev -n 100
```

### 自動起動設定

```bash
# 自動起動を有効化
sudo systemctl enable linux-management-dev

# 自動起動を無効化
sudo systemctl disable linux-management-dev

# 自動起動の状態確認
sudo systemctl is-enabled linux-management-dev
```

### トラブルシューティング

```bash
# サービスが起動しない場合

# 1. ログを確認
sudo journalctl -u linux-management-dev -n 50 --no-pager

# 2. 設定ファイルを確認
sudo systemctl cat linux-management-dev

# 3. 設定をリロード
sudo systemctl daemon-reload

# 4. 手動で起動してエラー確認
cd /mnt/LinuxHDD/Linux-Management-Systm
source venv/bin/activate
export ENV=dev
uvicorn backend.api.main:app --host 0.0.0.0 --port 5012
```

---

## 🔐 本番環境の事前準備

### 1. サービスユーザーの作成

```bash
# svc-adminui ユーザーを作成
sudo useradd -r -s /bin/bash -d /opt/linux-management svc-adminui

# ホームディレクトリの作成
sudo mkdir -p /opt/linux-management
sudo chown svc-adminui:svc-adminui /opt/linux-management
```

### 2. プロジェクトの配置

```bash
# プロジェクトを /opt/linux-management にコピー
sudo cp -r /mnt/LinuxHDD/Linux-Management-Systm/* /opt/linux-management/
sudo chown -R svc-adminui:svc-adminui /opt/linux-management
```

### 3. Python 仮想環境の作成

```bash
# svc-adminui ユーザーとして実行
sudo -u svc-adminui bash -c "cd /opt/linux-management && python3 -m venv venv-prod"
sudo -u svc-adminui bash -c "cd /opt/linux-management && source venv-prod/bin/activate && pip install -r backend/requirements.txt gunicorn"
```

### 4. sudo ラッパーの配置

```bash
# ラッパースクリプトをコピー
sudo cp /opt/linux-management/wrappers/adminui-*.sh /usr/local/sbin/

# 所有者を root に設定
sudo chown root:root /usr/local/sbin/adminui-*.sh

# パーミッション設定
sudo chmod 755 /usr/local/sbin/adminui-*.sh
```

### 5. sudoers 設定

```bash
# visudo で編集
sudo visudo

# 以下を追加:
# svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-status.sh
# svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-service-restart.sh
# svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-logs.sh
```

### 6. .env ファイルの配置

```bash
# .env をコピー（SESSION_SECRET を変更！）
sudo cp /opt/linux-management/.env.example /opt/linux-management/.env
sudo nano /opt/linux-management/.env
# SESSION_SECRET を変更
sudo chown svc-adminui:svc-adminui /opt/linux-management/.env
sudo chmod 600 /opt/linux-management/.env
```

---

## 🔍 動作確認

### 開発環境

```bash
# サービス起動
sudo systemctl start linux-management-dev

# ブラウザでアクセス
http://localhost:5012/dev/index.html

# API ドキュメント
http://localhost:5012/api/docs

# ログ確認
sudo journalctl -u linux-management-dev -f
```

### 本番環境

```bash
# サービス起動
sudo systemctl start linux-management-prod

# ブラウザでアクセス
https://localhost:8443/prod/index.html

# ログ確認
sudo journalctl -u linux-management-prod -f
```

---

## 🔄 自動起動の確認

### テスト方法

```bash
# 1. サービスを有効化
sudo systemctl enable linux-management-dev

# 2. 機器を再起動
sudo reboot

# 3. 再起動後、サービスが起動しているか確認
sudo systemctl status linux-management-dev
```

### 期待される結果

```
● linux-management-dev.service - Linux Management System - Development Environment
     Loaded: loaded (/etc/systemd/system/linux-management-dev.service; enabled)
     Active: active (running) since ...
```

---

## 📊 監視

### ログローテーション

systemd journal は自動的にログローテーションを行いますが、
必要に応じて手動設定も可能です。

```bash
# journald 設定
sudo nano /etc/systemd/journald.conf

# 設定例:
# SystemMaxUse=1G
# SystemMaxFileSize=100M
```

### リソース使用状況

```bash
# CPU・メモリ使用状況
sudo systemctl status linux-management-dev

# 詳細なリソース情報
sudo systemd-cgtop
```

---

## 🚫 アンインストール

```bash
# 1. サービス停止
sudo systemctl stop linux-management-dev

# 2. 自動起動を無効化
sudo systemctl disable linux-management-dev

# 3. サービスファイルを削除
sudo rm /etc/systemd/system/linux-management-dev.service

# 4. systemd リロード
sudo systemctl daemon-reload
```

---

## 📚 参考資料

- [systemd/linux-management-dev.service](../systemd/linux-management-dev.service)
- [systemd/linux-management-prod.service](../systemd/linux-management-prod.service)
- [scripts/install-service.sh](../scripts/install-service.sh)

---

## ⚠️ 重要な注意事項

### 本番環境

1. **必ず svc-adminui ユーザーで実行**
   - root での実行は禁止

2. **SESSION_SECRET を変更**
   - .env.example の値は使用しない

3. **SSL 証明書を適切に設定**
   - 自己署名証明書は開発用のみ
   - 本番環境では適切な証明書を使用

4. **ファイアウォール設定**
   - ポート 8000, 8443 を開放

5. **定期的なセキュリティ監査**
   - ログの定期確認
   - sudo ラッパーの改ざんチェック

---

**最終更新**: 2026-02-05
