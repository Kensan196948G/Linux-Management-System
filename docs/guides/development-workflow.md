# 開発ワークフローガイド

Linux Management System の開発手順・テスト実行・CI/CD パイプラインの説明。

---

## 1. ローカル開発環境セットアップ

### 前提条件

- Python 3.11 以上
- Ubuntu Linux (推奨)
- Git

### セットアップ手順

```bash
# リポジトリクローン
git clone <repo-url>
cd Linux-Management-Systm

# Python 仮想環境の作成と有効化
python3 -m venv venv
source venv/bin/activate

# 依存関係のインストール（開発用）
pip install -r backend/requirements.txt
pip install -r backend/requirements-dev.txt

# Pre-commit hooks のインストール（推奨）
pre-commit install
```

### 開発サーバーの起動

```bash
# 環境変数の読み込み
source load-env.sh

# 開発サーバー起動
cd backend
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 2. テスト実行方法

### ユニット/統合テスト

```bash
# 全テスト実行（E2E 除く）
make test
# または
pytest tests/ --ignore=tests/e2e -v --tb=short

# 特定のテストファイルのみ実行
pytest tests/unit/test_validation.py -v

# 特定のテストクラスのみ実行
pytest tests/integration/test_services_api.py::TestServicesAPI -v
```

### E2Eテスト

E2Eテストは FastAPI TestClient を使用するため、実際のサーバー起動は不要。

```bash
# E2Eテスト全実行
make test-e2e
# または
pytest -c pytest-e2e.ini

# 特定の E2E テストのみ
pytest tests/e2e/test_security_headers.py -v
pytest tests/e2e/test_api_smoke.py -v
```

### カバレッジ付きテスト

```bash
# カバレッジレポート生成（80%以上で合格）
make coverage

# カバレッジチェックスクリプト（CI で使用）
bash scripts/check-coverage.sh 80

# XML 形式レポート生成（CI の Codecov アップロード用）
pytest tests/ --ignore=tests/e2e --cov=backend --cov-report=xml
```

### テストカバレッジ目標

| コンポーネント | 目標 |
|--------------|------|
| `backend/core/` | 90% 以上 |
| `backend/api/` | 85% 以上 |

---

## 3. コードフォーマット・Lint

```bash
# フォーマットチェック（変更なし）
make lint

# フォーマット自動修正
black backend/
isort backend/

# 型チェック
mypy backend/ --ignore-missing-imports
```

---

## 4. セキュリティチェック

```bash
# セキュリティチェック（bandit + shell=True 検出）
make security-check

# bandit のみ（詳細レポート）
bandit -r backend/ -f screen

# shell=True の手動確認
grep -rn "shell=True" backend/ --include="*.py"
```

---

## 5. Makefile コマンド一覧

| コマンド | 説明 |
|---------|------|
| `make test` | ユニット/統合テスト実行 |
| `make test-e2e` | E2E テスト実行 |
| `make lint` | Black + flake8 チェック |
| `make security-check` | bandit + shell=True 検出 |
| `make coverage` | カバレッジレポート生成 |
| `make clean` | キャッシュファイル削除 |
| `make help` | コマンド一覧表示 |

---

## 6. CI/CD パイプライン

### ワークフロー構成

`.github/workflows/` に以下のワークフローが存在する:

| ファイル | トリガー | 説明 |
|---------|---------|------|
| `ci.yml` | push/PR | メインCI（テスト・Lint・セキュリティ） |
| `security-audit.yml` | push(main)/PR/週次 | 包括的セキュリティ監査 |
| `e2e.yml` | push/PR | E2E テスト専用 |
| `auto-repair.yml` | 手動 | CI 失敗時の自動修復 |

### ci.yml の主要ステップ

```
1. Python 3.11 / 3.12 マトリクスビルド
2. 依存関係インストール
   pip install -r backend/requirements.txt -r backend/requirements-dev.txt
3. Black フォーマットチェック
4. isort インポート順チェック
5. flake8 Lint
6. mypy 型チェック
7. bandit セキュリティスキャン
8. pytest テスト + カバレッジ (--cov=backend --cov-report=xml)
9. ShellCheck (wrappers/*.sh)
10. 禁止パターン検出 (shell=True / os.system / eval/exec)
```

### security-audit.yml の主要ステップ

```
1. bandit -ll (Medium/High 以上のみ報告)
2. shell=True 検出 (CRITICAL - 即失敗)
3. os.system 検出 (CRITICAL - 即失敗)
4. eval/exec 検出 (CRITICAL - 即失敗)
5. bash -c in wrappers 検出 (CRITICAL - 即失敗)
6. truffleHog シークレットスキャン
7. sudo ラッパースクリプト検証
```

---

## 7. Git ワークフロー

### ブランチ戦略

```
main          ← 本番ブランチ（直接コミット禁止）
develop       ← 開発統合ブランチ
feature/*     ← 機能開発ブランチ
fix/*         ← バグ修正ブランチ
```

### 推奨フロー

```bash
# 1. feature ブランチを作成
git checkout -b feature/add-new-module

# 2. 開発・テスト
make test
make lint
make security-check

# 3. コミット（Co-authored-by トレーラー必須）
git add -A
git commit -m "feat: 新機能の説明

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"

# 4. プッシュ
git push origin feature/add-new-module

# 5. Pull Request 作成 → レビュー → マージ
```

### コミットメッセージ規約

| プレフィックス | 説明 |
|-------------|------|
| `feat:` | 新機能追加 |
| `fix:` | バグ修正 |
| `docs:` | ドキュメント更新 |
| `test:` | テスト追加・修正 |
| `refactor:` | リファクタリング |
| `ci:` | CI/CD 設定変更 |
| `security:` | セキュリティ修正 |

### コミット前チェックリスト

```bash
# セキュリティチェック
grep -r "shell=True" backend/ && echo "❌ shell=True detected" || echo "✅ OK"

# テスト
pytest tests/ --ignore=tests/e2e -q

# 静的解析
bandit -r backend/ -ll
flake8 backend/
```

---

## 8. 新モジュール追加手順

新しいAPIモジュール `xyz` を追加する場合:

```bash
# 1. sudo ラッパースクリプト作成
cp wrappers/adminui-template.sh wrappers/adminui-xyz.sh
# allowlist を編集

# 2. API ルーター実装
touch backend/api/routes/xyz.py

# 3. テスト作成（15件以上）
touch tests/integration/test_xyz_api.py

# 4. フロントエンド UI
touch frontend/dev/xyz.html

# 5. ルーター登録（main.py に追加）
# app.include_router(xyz.router, prefix="/api")

# 6. 権限追加（auth.py の PERMISSIONS に追加）
# "read:xyz": [Role.viewer, Role.operator, Role.approver, Role.admin]
```

---

## 参照ドキュメント

- [README.md](../../README.md) - プロジェクト概要
- [CLAUDE.md](../../CLAUDE.md) - 開発仕様・セキュリティ原則
- [SECURITY.md](../../SECURITY.md) - セキュリティポリシー
- [production-deploy.md](production-deploy.md) - 本番デプロイ手順
