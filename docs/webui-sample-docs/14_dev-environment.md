# 開発環境構築手順書

**文書番号**: WEBUI-DEV-002
**バージョン**: 1.0
**作成日**: 2026-02-25
**対象システム**: Linux管理 WebUI サンプルシステム

---

## 1. 前提条件

### 1.1 必要なソフトウェア

| ソフトウェア | バージョン | 用途 |
|-----------|----------|------|
| Ubuntu / Debian | 22.04 LTS / 12.x | 開発OS（推奨） |
| Python | 3.10 以上 | バックエンド |
| Node.js | 20.x LTS | フロントエンド |
| npm | 10.x | パッケージ管理 |
| Git | 2.x | バージョン管理 |
| Docker | 24.x | コンテナ（任意） |
| SQLite3 | 3.x | 開発用DB |
| make | - | タスクランナー |

### 1.2 ハードウェア要件（開発環境）

| 項目 | 最小 | 推奨 |
|------|------|------|
| CPU | 2コア | 4コア以上 |
| メモリ | 4GB | 8GB以上 |
| ディスク | 10GB | 20GB以上 |
| OS | Linux（Ubuntu推奨）| - |

---

## 2. リポジトリのクローン

```bash
# SSH（推奨）
git clone git@gitrepo.example.local:adminui/linux-mgmt-webui.git
cd linux-mgmt-webui

# または HTTPS
git clone https://gitrepo.example.local/adminui/linux-mgmt-webui.git
cd linux-mgmt-webui
```

---

## 3. バックエンド環境構築

### 3.1 Python 仮想環境の作成

```bash
# Python バージョン確認
python3 --version  # 3.10以上であること

# 仮想環境の作成と有効化
python3 -m venv .venv
source .venv/bin/activate

# pip のアップグレード
pip install --upgrade pip
```

### 3.2 依存ライブラリのインストール

```bash
cd backend

# 本番依存
pip install -r requirements.txt

# 開発依存（テスト・リント等）
pip install -r requirements-dev.txt
```

`requirements.txt` 主要ライブラリ:
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
sqlalchemy==2.0.23
pydantic==2.5.0
structlog==23.2.0
pyotp==2.9.0
```

`requirements-dev.txt` 主要ライブラリ:
```
pytest==7.4.3
pytest-asyncio==0.21.1
httpx==0.25.2
black==23.11.0
flake8==6.1.0
mypy==1.7.0
isort==5.12.0
pytest-cov==4.1.0
```

### 3.3 環境変数の設定

```bash
# 開発用設定ファイルをコピー
cp backend/.env.example backend/.env

# .env の編集（最低限以下を設定）
nano backend/.env
```

`.env` の設定例:
```env
# アプリケーション設定
APP_ENV=development
DEBUG=true
SECRET_KEY=dev-secret-key-change-in-production-min-32chars!!

# データベース
DATABASE_URL=sqlite:///./data/adminui_dev.db

# JWT設定
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_HOURS=8

# セキュリティ
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ORIGINS=http://localhost:5173

# ログ
LOG_LEVEL=DEBUG
LOG_FORMAT=console  # 開発時は読みやすいコンソール形式
```

### 3.4 データベースの初期化

```bash
cd backend

# DBディレクトリ作成
mkdir -p data

# マイグレーション実行
python manage.py migrate

# 初期データ投入（開発用）
python manage.py seed --env development
# → Admin: admin / Password123! (MFA無効)
# → Operator: operator01 / Password123! (MFA無効)
# → Viewer: viewer01 / Password123! (MFA無効)
```

### 3.5 バックエンドの起動

```bash
cd backend

# 開発サーバー起動（ホットリロード有効）
uvicorn main:app --reload --host 127.0.0.1 --port 8000

# ブラウザで確認
# API ドキュメント: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc
```

---

## 4. フロントエンド環境構築

### 4.1 Node.js の確認

```bash
node --version  # v20.x 以上
npm --version   # 10.x 以上
```

### 4.2 依存ライブラリのインストール

```bash
cd frontend

npm install
```

### 4.3 環境変数の設定

```bash
cp frontend/.env.example frontend/.env.local
```

`.env.local` の設定:
```env
VITE_API_BASE_URL=http://localhost:8000
VITE_APP_TITLE=Linux管理WebUI（開発）
```

### 4.4 フロントエンドの起動

```bash
cd frontend

# 開発サーバー起動（ホットリロード有効）
npm run dev

# ブラウザで確認: http://localhost:5173
```

---

## 5. 開発用サンプル sudo 設定

> **重要**: 開発環境では実際の sudo 設定は不要です（モックを使用）。
> ステージング環境以降で実際の設定を行います。

```bash
# 開発用モックの有効化（.env で設定）
WRAPPER_MOCK_MODE=true
# → sudo を呼ばず、モックレスポンスを返す
```

---

## 6. テストの実行

### 6.1 ユニット・統合テスト（Python）

```bash
cd backend

# 全テスト実行
pytest

# カバレッジ付き
pytest --cov=. --cov-report=html

# 特定テストのみ
pytest tests/test_validators.py -v

# セキュリティ重要テストのみ
pytest tests/test_security.py tests/test_injection.py -v
```

### 6.2 フロントエンドテスト

```bash
cd frontend

# ユニットテスト
npm run test

# E2E テスト（Playwright）
npx playwright test

# E2E テスト（ブラウザ表示あり）
npx playwright test --headed
```

---

## 7. コード品質チェック

```bash
# バックエンド全チェック（CI と同等）
cd backend
make lint  # black + isort + flake8 + mypy

# または個別実行
black --check .
isort --check .
flake8 .
mypy .

# フロントエンド全チェック
cd frontend
npm run lint
npm run type-check
```

### Makefile（プロジェクトルート）

```makefile
.PHONY: setup dev test lint

setup:
    cd backend && pip install -r requirements-dev.txt
    cd frontend && npm install

dev:
    # バックエンド・フロントエンドを並列起動
    cd backend && uvicorn main:app --reload &
    cd frontend && npm run dev &

test:
    cd backend && pytest --cov
    cd frontend && npm run test

lint:
    cd backend && make lint
    cd frontend && npm run lint
```

---

## 8. IDE 設定推奨

### 8.1 Visual Studio Code（推奨）

インストール推奨拡張機能:
- `ms-python.python` - Python
- `ms-python.black-formatter` - Black フォーマッタ
- `ms-python.mypy-type-checker` - 型チェック
- `Vue.volar` - Vue.js サポート
- `dbaeumer.vscode-eslint` - ESLint
- `esbenp.prettier-vscode` - Prettier

`.vscode/settings.json`:
```json
{
  "editor.formatOnSave": true,
  "python.defaultInterpreterPath": ".venv/bin/python",
  "[python]": {
    "editor.defaultFormatter": "ms-python.black-formatter"
  },
  "[typescript]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "[vue]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  }
}
```

---

## 9. トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| `uvicorn` コマンドが見つからない | 仮想環境が有効でない | `source .venv/bin/activate` |
| DBエラー（テーブルなし） | マイグレーション未実行 | `python manage.py migrate` |
| CORS エラー | フロントURL が設定と不一致 | `.env` の `CORS_ORIGINS` を確認 |
| npm install 失敗 | Node.js バージョン不一致 | `node --version` で確認・更新 |
| pytest が失敗 | 開発依存未インストール | `pip install -r requirements-dev.txt` |

---

*本文書はLinux管理WebUIサンプルシステムの開発環境構築手順を定めるものである。*
