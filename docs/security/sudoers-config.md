# sudoers 設定ガイド

**sudo ラッパースクリプト用の安全な sudoers 設定**

---

## ⚠️ 重要な注意事項

sudoers ファイルの編集は**システムセキュリティに直接影響**します。
誤った設定は、システムへのアクセス不能やセキュリティホールにつながります。

**必ず `visudo` コマンドを使用してください。**

---

## 📋 前提条件

### 実行ユーザーの作成

```bash
# Linux 管理 WebUI 用のサービスユーザーを作成
sudo useradd -r -s /bin/bash -d /opt/linux-management svc-adminui

# ホームディレクトリの作成
sudo mkdir -p /opt/linux-management
sudo chown svc-adminui:svc-adminui /opt/linux-management
```

### ラッパースクリプトの配置

```bash
# ラッパースクリプトを /usr/local/sbin/ にコピー
sudo cp wrappers/adminui-*.sh /usr/local/sbin/

# 所有者を root に設定
sudo chown root:root /usr/local/sbin/adminui-*.sh

# パーミッションを 755 に設定（root のみ編集可能）
sudo chmod 755 /usr/local/sbin/adminui-*.sh
```

---

## ⚙️ sudoers 設定

### 設定方法

```bash
# visudo で sudoers ファイルを編集
sudo visudo
```

### 推奨設定（最小権限）

```sudoers
# Linux Management System - sudo wrapper configuration
# User: svc-adminui
# Purpose: Secure Linux management operations via allowlist-based wrappers

# ラッパースクリプトのみを許可（NOPASSWD）
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-status.sh
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-service-restart.sh
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-logs.sh

# 直接的な systemctl / journalctl の実行は禁止
# （ラッパー経由のみ許可）
```

### 設定の説明

| 項目 | 説明 |
|------|------|
| `svc-adminui` | 実行を許可するユーザー |
| `ALL=` | 全ホストで有効 |
| `(root)` | root として実行 |
| `NOPASSWD:` | パスワード入力不要 |
| `/usr/local/sbin/adminui-*.sh` | 許可するコマンド（絶対パス） |

---

## ✅ 設定の検証

### 1. 構文チェック

```bash
# visudo は保存時に自動的に構文チェックを実行
# エラーがあれば保存されない
```

### 2. 権限テスト

```bash
# svc-adminui ユーザーに切り替え
sudo -u svc-adminui bash

# ラッパースクリプトを実行（パスワード不要で実行できるはず）
sudo /usr/local/sbin/adminui-status.sh

# 直接 systemctl を実行（拒否されるはず）
sudo systemctl status nginx
# → "Sorry, user svc-adminui is not allowed to execute..."
```

### 3. セキュリティテスト

```bash
# コマンドインジェクション試行（拒否されるはず）
sudo /usr/local/sbin/adminui-service-restart.sh "nginx; rm -rf /"
# → "Forbidden character detected"

# 許可リスト外のサービス（拒否されるはず）
sudo /usr/local/sbin/adminui-service-restart.sh malicious-service
# → "Service not in allowlist"
```

---

## 🔒 セキュリティのベストプラクティス

### 1. 最小権限の原則

```sudoers
# ❌ 悪い例: 全コマンドを許可
svc-adminui ALL=(ALL) NOPASSWD: ALL

# ✅ 良い例: 特定のラッパーのみ許可
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-status.sh
```

### 2. 絶対パスの使用

```sudoers
# ❌ 悪い例: 相対パスや * を使用
svc-adminui ALL=(root) NOPASSWD: adminui-*.sh
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/*

# ✅ 良い例: 各スクリプトを明示的に指定
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-status.sh
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-service-restart.sh
```

### 3. NOPASSWD の慎重な使用

```sudoers
# NOPASSWD は必要最小限に
# WebUI からの自動実行のため、今回は必要

# ただし、以下のような危険なコマンドには絶対に NOPASSWD を使わない:
# - /bin/bash, /bin/sh（シェル起動）
# - /usr/bin/sudo（sudo の再帰実行）
# - /usr/bin/su（ユーザー切り替え）
```

### 4. ラッパースクリプトの保護

```bash
# root のみが編集可能
sudo chown root:root /usr/local/sbin/adminui-*.sh
sudo chmod 755 /usr/local/sbin/adminui-*.sh

# ラッパースクリプトが改ざんされていないか定期的にチェック
# （ファイルハッシュの記録・比較）
```

---

## 🧪 テスト手順

### 完全なテストシナリオ

```bash
# 1. ラッパースクリプトのテストを実行
./wrappers/test/test-all-wrappers.sh

# 2. svc-adminui ユーザーでの権限テスト
sudo -u svc-adminui sudo /usr/local/sbin/adminui-status.sh

# 3. セキュリティテスト
sudo -u svc-adminui sudo /usr/local/sbin/adminui-service-restart.sh "nginx; ls"
# → 拒否されることを確認

# 4. 正常系テスト（実際にサービスを操作）
# 注意: nginx がインストールされている必要がある
sudo -u svc-adminui sudo /usr/local/sbin/adminui-service-restart.sh nginx
```

---

## 📊 トラブルシューティング

### エラー: "Sorry, user svc-adminui is not allowed to execute..."

**原因**: sudoers の設定が正しくない

**解決方法**:
1. `sudo visudo` で設定を再確認
2. 絶対パスが正しいか確認
3. ユーザー名が正しいか確認

### エラー: "command not found"

**原因**: ラッパースクリプトが正しく配置されていない

**解決方法**:
```bash
# スクリプトが存在するか確認
ls -la /usr/local/sbin/adminui-*.sh

# パスが正しいか確認
which adminui-status.sh
```

### エラー: "Forbidden character detected"

**原因**: 入力に特殊文字が含まれている（正常な動作）

**解決方法**: 正常なセキュリティチェックです。引数を確認してください。

---

## 🔄 本番環境への適用

### 1. テスト環境で検証

```bash
# テスト環境で十分にテスト
./wrappers/test/test-all-wrappers.sh
```

### 2. 段階的なロールアウト

```bash
# 1. 1つのラッパーのみ有効化
# 2. 動作確認
# 3. 問題なければ次のラッパーを有効化
```

### 3. ログ監視

```bash
# sudo のログを監視
sudo tail -f /var/log/auth.log | grep adminui

# syslog を監視
sudo tail -f /var/log/syslog | grep adminui
```

---

## 📚 関連ドキュメント

- [wrappers/README.md](../wrappers/README.md) - ラッパースクリプトの使用方法
- [CLAUDE.md](../CLAUDE.md) - セキュリティ原則
- [SECURITY.md](../SECURITY.md) - セキュリティポリシー

---

## ⚠️ 重要な警告

1. **sudoers ファイルは慎重に編集してください**
   - 誤った設定はシステムへのアクセス不能につながります
   - 必ず `visudo` を使用してください

2. **定期的なセキュリティ監査**
   - sudoers 設定の定期レビュー
   - ラッパースクリプトの改ざんチェック
   - ログの定期確認

3. **本番環境での変更前に必ずバックアップ**
   ```bash
   sudo cp /etc/sudoers /etc/sudoers.backup
   ```

---

**最終更新**: 2026-02-05
