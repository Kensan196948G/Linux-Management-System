# Git WorkTree 使用ガイド

**並列モジュール開発のための WorkTree 活用**

---

## 📋 概要

Git WorkTree を使用することで、複数のモジュールを並列開発できます。

**原則**: **1機能 = 1 WorkTree/ブランチ**

---

## 🎯 WorkTree のメリット

### 従来の方法（ブランチ切り替え）

```bash
# 問題点: ブランチ切り替えのたびにファイルが変更される
git checkout feature/user-management
# 開発作業...
git checkout feature/cron-management
# ファイルが全て切り替わる → IDE の再読み込み、依存関係の再インストールが必要
```

### WorkTree 方式

```bash
# メリット: 複数の機能を並行して開発可能
Linux-Management-System/           # main ブランチ
../user-management-worktree/      # feature/user-management
../cron-management-worktree/      # feature/cron-management

# それぞれ独立した作業ディレクトリ
# ブランチ切り替え不要
# 同時に複数の IDE を開ける
```

---

## 🚀 基本的な使い方

### Linux / macOS

```bash
# WorkTree を作成
./scripts/worktree/worktree-manager.sh create user-management

# WorkTree 一覧を表示
./scripts/worktree/worktree-manager.sh list

# WorkTree に移動
cd ../user-management-worktree

# 開発作業
# ...

# 完了したら main にマージ
git add .
git commit -m "feat: Add user management module"
git push origin feature/user-management

# GitHub で Pull Request を作成
# マージ後、WorkTree を削除
cd /path/to/Linux-Management-System
./scripts/worktree/worktree-manager.sh remove user-management
```

### Windows (PowerShell)

```powershell
# WorkTree を作成
.\scripts\worktree\worktree-manager.ps1 create user-management

# WorkTree 一覧を表示
.\scripts\worktree\worktree-manager.ps1 list

# WorkTree を削除
.\scripts\worktree\worktree-manager.ps1 remove user-management
```

---

## 📚 コマンドリファレンス

### create - WorkTree を作成

```bash
./scripts/worktree/worktree-manager.sh create <feature-name>
```

**動作**:
1. `feature/<feature-name>` ブランチを作成
2. `../<feature-name>-worktree/` ディレクトリに WorkTree を作成
3. ブランチをチェックアウト

**例**:
```bash
./scripts/worktree/worktree-manager.sh create user-management
# → ../user-management-worktree/ が作成される
```

### list - WorkTree 一覧を表示

```bash
./scripts/worktree/worktree-manager.sh list
```

**出力例**:
```
/mnt/LinuxHDD/Linux-Management-System  3b3d802 [main]
/mnt/LinuxHDD/user-management-worktree 5a1b2c3 [feature/user-management]
/mnt/LinuxHDD/cron-management-worktree 7d4e5f6 [feature/cron-management]

合計: 3 個の WorkTree
```

### status - 全 WorkTree の状態を表示

```bash
./scripts/worktree/worktree-manager.sh status
```

**出力例**:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 /mnt/LinuxHDD/Linux-Management-System
🌿 Branch: main
✅ クリーン
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 /mnt/LinuxHDD/user-management-worktree
🌿 Branch: feature/user-management
⚠️  未コミットの変更あり
M  backend/api/routes/users.py
```

### remove - WorkTree を削除

```bash
./scripts/worktree/worktree-manager.sh remove <feature-name>
```

**動作**:
1. WorkTree ディレクトリを削除
2. （オプション）ブランチも削除

### cleanup - 削除済み WorkTree をクリーンアップ

```bash
./scripts/worktree/worktree-manager.sh cleanup
```

手動で WorkTree ディレクトリを削除した場合、Git の管理情報が残ります。このコマンドでクリーンアップできます。

---

## 🔄 並列開発ワークフロー

### シナリオ: 2つのモジュールを同時開発

```bash
# 1. Users Management モジュール用 WorkTree
./scripts/worktree/worktree-manager.sh create user-management
cd ../user-management-worktree

# backend/api/routes/users.py を実装
# tests/integration/test_users.py を実装
git add .
git commit -m "feat: Add user management module"
git push origin feature/user-management

# 2. Cron Jobs モジュール用 WorkTree（並行開発）
cd /path/to/Linux-Management-System
./scripts/worktree/worktree-manager.sh create cron-management
cd ../cron-management-worktree

# backend/api/routes/cron.py を実装
# tests/integration/test_cron.py を実装
git add .
git commit -m "feat: Add cron management module"
git push origin feature/cron-management

# 3. 両方の Pull Request を作成
# マージ後、WorkTree を削除
cd /path/to/Linux-Management-System
./scripts/worktree/worktree-manager.sh remove user-management
./scripts/worktree/worktree-manager.sh remove cron-management
```

---

## 🛡️ コンフリクト防止

### Hooks との連携

WorkTree 管理スクリプトは、`hooks/conflict-prevention.sh` と連携します。

```bash
# ファイルロックを使用
cd ../user-management-worktree
./hooks/conflict-prevention.sh register code-implementer \
    backend/api/routes/users.py \
    backend/core/user_management.py

# 開発作業
# ...

# ロック解放
./hooks/conflict-prevention.sh unregister code-implementer \
    backend/api/routes/users.py \
    backend/core/user_management.py
```

---

## 💡 ベストプラクティス

### 1. 機能ごとに WorkTree を作成

```bash
# ✅ 良い例: 機能ごと
./scripts/worktree/worktree-manager.sh create user-management
./scripts/worktree/worktree-manager.sh create cron-management

# ❌ 悪い例: 1つの WorkTree で複数機能
# （main ブランチで直接開発）
```

### 2. 定期的にクリーンアップ

```bash
# マージ済みの WorkTree を削除
./scripts/worktree/worktree-manager.sh remove user-management

# 孤立した WorkTree をクリーンアップ
./scripts/worktree/worktree-manager.sh cleanup
```

### 3. WorkTree 状態を定期確認

```bash
# 全 WorkTree の状態を確認
./scripts/worktree/worktree-manager.sh status

# 未コミットの変更がある WorkTree を確認
```

---

## 🔍 トラブルシューティング

### WorkTree が削除できない

```bash
# 強制削除
rm -rf ../user-management-worktree
git worktree prune
```

### ブランチが残っている

```bash
# ブランチを削除
git branch -D feature/user-management
```

### WorkTree の場所がわからない

```bash
# 一覧表示
./scripts/worktree/worktree-manager.sh list
```

---

## 📚 参考資料

- [Git WorkTree 公式ドキュメント](https://git-scm.com/docs/git-worktree)
- [hooks/README.md](./hooks/README.md) - コンフリクト防止機構
- [agents/README.md](./agents/README.md) - SubAgent 並列実行

---

## 🎯 モジュール開発での活用

### v0.2 モジュール開発例

```bash
# Phase 2 の5つのモジュールを並列開発

# 開発者1: Users and Groups
./scripts/worktree/worktree-manager.sh create users-and-groups
cd ../users-and-groups-worktree

# 開発者2: Cron Jobs
./scripts/worktree/worktree-manager.sh create cron-jobs
cd ../cron-jobs-worktree

# 開発者3: Network Configuration
./scripts/worktree/worktree-manager.sh create network-config
cd ../network-config-worktree

# それぞれ独立して開発・テスト・コミット可能
```

---

**最終更新**: 2026-02-05
