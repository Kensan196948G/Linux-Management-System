# GitHub Copilot Instructions
# Linux Management System - セキュリティファースト開発ガイド

## 🎯 プロジェクト概要

**Linux管理WebUI** - Webmin互換のLinuxサーバ運用管理システム。
root操作を `sudo allowlist + 承認ワークフロー` で統制するセキュリティファースト設計。

- **対象OS**: Ubuntu Linux
- **バックエンド**: FastAPI (Python 3.11+)
- **フロントエンド**: HTML/CSS/Vanilla JS
- **認証**: JWT (HS256)
- **DB**: SQLite (承認ワークフロー用)
- **実行ユーザー**: `svc-adminui`

---

## 🔒 絶対遵守ルール（セキュリティ）

### 1. shell=True 全面禁止
```python
# ✅ 正しい
subprocess.run(["/usr/local/sbin/adminui-status"], check=True)
# ❌ 禁止
subprocess.run("systemctl status nginx", shell=True)
```

### 2. Allowlist First（許可リスト優先）
```python
# ✅ 正しい
ALLOWED_SERVICES = ["nginx", "postgresql", "redis"]
if service_name in ALLOWED_SERVICES:
    execute_restart(service_name)
# ❌ 禁止 - ブラックリスト方式
if service_name not in BLACKLIST:
    execute_restart(service_name)
```

### 3. sudo は wrapper スクリプト経由のみ
```python
# ✅ 正しい
subprocess.run(["sudo", "/usr/local/sbin/adminui-service-restart", "nginx"])
# ❌ 禁止 - 直接実行
subprocess.run(["sudo", "systemctl", "restart", "nginx"])
```

### 4. 入力バリデーション必須
```python
FORBIDDEN_CHARS = [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?"]
# 全てのユーザー入力に validate_input() を適用すること
```

### 5. 監査ログ必須
```python
# 全ての操作（read含む重要操作）は audit_log.record() で記録すること
```

---

## 📁 ディレクトリ構造

```
backend/
  api/
    routes/       # FastAPI ルーター（各モジュール）
    main.py       # アプリケーションエントリーポイント
  core/
    auth.py       # JWT認証・RBAC
    approval_service.py  # 承認ワークフロー
    sudo_wrapper.py      # sudo呼び出し抽象化
    audit_log.py         # 監査ログ
    validation.py        # 入力バリデーション
    constants.py         # 許可リスト定数
wrappers/
  adminui-*.sh    # sudo ラッパースクリプト（allowlist実装）
frontend/
  dev/            # HTML ページ
  js/             # JavaScript モジュール
  css/            # スタイルシート
tests/
  unit/           # ユニットテスト
  integration/    # 統合テスト
  security/       # セキュリティテスト
  e2e/            # E2Eテスト
```

---

## 🧩 APIルーター追加時の手順

新しいモジュール `xyz` を追加する場合：

1. **ラッパースクリプト** `wrappers/adminui-xyz.sh` を作成（allowlist実装）
2. **バックエンド** `backend/api/routes/xyz.py` を作成
3. **テスト** `tests/integration/test_xyz_api.py` を作成（15件以上）
4. **フロントエンド** `frontend/dev/xyz.html` を作成
5. **ルーター登録** `backend/api/main.py` に `app.include_router()` 追加
6. **権限追加** `backend/core/auth.py` の `PERMISSIONS` に `read:xyz` 追加

---

## 👥 ロールと権限

| ロール | 説明 | 主な権限 |
|--------|------|----------|
| `viewer` | 閲覧のみ | read:system, read:logs 等 |
| `operator` | 操作申請 | viewer + 承認リクエスト作成 |
| `approver` | 承認権限 | operator + 承認/却下 |
| `admin` | 全権限 | 全操作 + ユーザー管理 |

---

## ✅ テスト要件

- **カバレッジ目標**: backend/core/ は **90%以上**、backend/api/ は **85%以上**
- **セキュリティテスト必須**: 不正入力拒否・allowlist外拒否・権限不足拒否
- **各テストは独立**: 共有状態を持たない（tmp_path を使用）
- **asyncio**: `asyncio.run()` を使用（`asyncio.get_event_loop()` は使用禁止）

---

## 🔄 承認ワークフロー

危険な操作（ユーザー追加・削除・シャットダウン等）は必ず承認フロー経由：

1. `POST /api/approval/request` でリクエスト作成
2. Approver/Admin が `POST /api/approval/{id}/approve` で承認
3. 承認後に自動実行（`approval_service.py` の `execute_approved_action()`）

---

## 📋 コーディング規約

- **型ヒント必須**: 全関数に型ヒントを付ける
- **docstring必須**: 全関数・クラスにdocstringを付ける
- **フォーマット**: Black (line-length=127)
- **import順**: isort
- **セキュリティ**: bandit で Medium/High 0件を維持

---

## 🚫 絶対禁止コード

```python
# 以下のパターンが含まれるコードは提案しないこと
subprocess.run(..., shell=True)    # shell=True
os.system("...")                   # os.system
eval(user_input)                   # eval
exec(user_input)                   # exec
```

---

## 📚 参照ドキュメント

- [CLAUDE.md](../CLAUDE.md) - 詳細な開発仕様
- [SECURITY.md](../SECURITY.md) - セキュリティポリシー
- [docs/guides/production-deploy.md](../docs/guides/production-deploy.md) - デプロイ手順
