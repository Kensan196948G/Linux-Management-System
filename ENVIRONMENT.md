# 🔧 開発環境セットアップ

**Linux Management System - Development Environment Setup Guide**

このドキュメントでは、Linux管理運用システムの開発環境を構築する手順を説明します。

---

## 📋 前提条件

開発を始める前に、以下の環境が必要です。

### オペレーティングシステム

- **推奨**: Ubuntu 22.04 LTS 以降
- **サポート**: その他の Linux ディストリビューション（Debian系推奨）
- **非サポート**: Windows（WSL2は未テスト）、macOS（一部機能が動作しない可能性）

### 必須ソフトウェア

| ソフトウェア | 最小バージョン | 推奨バージョン | 確認コマンド |
|------------|-------------|-------------|------------|
| **Python** | 3.11 | 3.12+ | `python3 --version` |
| **pip** | 23.0+ | 最新 | `pip3 --version` |
| **Git** | 2.30+ | 最新 | `git --version` |
| **sudo** | - | - | `sudo -V` |
| **systemctl** | - | - | `systemctl --version` |

### 権限要件

- **sudo権限を持つユーザーアカウント**（一部機能のテストに必要）
- sudoersに以下の設定を追加することを推奨（開発環境のみ）:

```bash
# 開発環境専用の設定（本番環境では使用しない）
# /etc/sudoers.d/linux-management-dev
your_username ALL=(ALL) NOPASSWD: /usr/local/sbin/adminui-*
```

**⚠️ 警告**: 本番環境では sudoers の設定を慎重に行ってください。

---

## 🚀 セットアップ手順

### ステップ1: リポジトリのクローン

```bash
# GitHubからクローン
git clone https://github.com/Kensan196948G/Linux-Management-System.git
cd Linux-Management-System
```

### ステップ2: Python仮想環境の作成

開発環境を隔離するため、Python仮想環境を使用します。

```bash
# 仮想環境の作成
python3 -m venv venv

# 仮想環境のアクティベート
source venv/bin/activate

# (仮想環境内で) pipのアップグレード
pip install --upgrade pip
```

**ヒント**: 仮想環境を終了するには `deactivate` コマンドを実行します。

### ステップ3: 依存関係のインストール

#### バックエンド依存関係（本番 + 開発）

```bash
# backend/ ディレクトリに移動
cd backend

# 本番依存関係のインストール
pip install -r requirements.txt

# 開発・テスト依存関係のインストール
pip install -r requirements-dev.txt
```

**依存関係の内訳**:

- **本番依存関係** (`requirements.txt`):
  - FastAPI: RESTful API フレームワーク
  - uvicorn: ASGI サーバー
  - aiosqlite: 非同期SQLiteドライバ
  - python-jose, passlib: 認証・認可
  - python-dotenv: 環境変数管理

- **開発依存関係** (`requirements-dev.txt`):
  - pytest: テストフレームワーク
  - bandit, safety: セキュリティスキャナ
  - black, flake8, mypy: コード品質ツール
  - pytest-cov: カバレッジ測定

#### フロントエンド（依存関係なし）

フロントエンドはバニラ HTML/CSS/JavaScript で実装されているため、追加の依存関係はありません。

---

## 🗄️ データベース設定

### SQLite データベース

本システムは **SQLite** をデータベースとして使用します。

#### データベースファイルのパス

| 環境 | パス | 用途 |
|-----|------|-----|
| **開発環境** | `./data/dev/database.db` | ローカル開発用（リポジトリに含まれない） |
| **本番環境** | `/var/lib/linux-management/database.db` | 本番デプロイ用 |
| **テスト環境** | `:memory:` または `./data/test/database.db` | pytest実行時の一時DB |

#### データベース初期化

データベースは初回起動時に自動的に作成されます。

```bash
# 開発用データディレクトリの作成
mkdir -p data/dev
mkdir -p data/test

# データベースは自動作成されます（手動作成不要）
```

#### スキーママイグレーション

現在はスキーママイグレーションツールを使用していません。スキーマ変更時は以下の手順を実行します。

```bash
# 既存データベースの削除（開発環境のみ）
rm -f data/dev/database.db

# アプリケーション起動時に新スキーマで自動作成
```

**将来の拡張**: Alembic 等のマイグレーションツールを導入予定。

---

## 🔐 環境変数設定

### .env ファイルの作成

環境変数は `.env` ファイルで管理します。

```bash
# リポジトリルートに戻る
cd ..

# .env.example をコピーして .env を作成
cp .env.example .env
```

### 環境変数の説明

`.env.example` の内容を参考に、以下の環境変数を設定します。

```bash
# GitHub Token（CI/CD、自動化に必要）
# https://github.com/settings/tokens から取得
# 必要なスコープ: repo, workflow
GITHUB_TOKEN=ghp_your_token_here

# 開発環境設定
DEV_IP=0.0.0.0          # 全インターフェースでリッスン
DEV_PORT=5012            # 開発サーバーのポート
DEV_HTTPS_PORT=5443      # HTTPS用ポート（将来使用）

# 本番環境設定
PROD_IP=0.0.0.0
PROD_PORT=8000
PROD_HTTPS_PORT=8443

# データベースパス
DB_PATH=/var/lib/linux-management/data.db  # 本番環境用

# セッション秘密鍵（本番環境では必ず変更）
SESSION_SECRET=change-this-in-production

# ログレベル（DEBUG, INFO, WARNING, ERROR）
LOG_LEVEL=INFO
```

**⚠️ セキュリティ注意**:
- `.env` ファイルは Git で管理しないでください（`.gitignore` に含まれています）
- `SESSION_SECRET` は本番環境で必ず変更してください
- `GITHUB_TOKEN` は他人に見せないでください

---

## 🏃 開発サーバーの起動

### バックエンドサーバーの起動

```bash
# backend/ ディレクトリから起動（仮想環境内）
cd backend
uvicorn api.main:app --reload --host 0.0.0.0 --port 5012
```

**起動オプション**:
- `--reload`: ファイル変更時に自動リロード
- `--host 0.0.0.0`: 全インターフェースでリッスン
- `--port 5012`: ポート番号

**起動確認**:
```bash
# 別のターミナルで確認
curl http://localhost:5012/api/health
# 期待される応答: {"status":"ok"}
```

### フロントエンドの起動

フロントエンドは静的ファイルなので、ブラウザで直接開くか、バックエンドが `/` で配信します。

```bash
# ブラウザでアクセス
xdg-open http://localhost:5012
```

---

## ✅ Pre-flight チェックリスト

開発サーバーを起動する前に、以下を確認してください。

### 環境確認

```bash
# Python バージョン確認
python3 --version  # 3.11+ であること

# 仮想環境がアクティブか確認
which python3  # /path/to/venv/bin/python3 を指していること

# 依存関係が正しくインストールされているか確認
pip list | grep fastapi
pip list | grep uvicorn
```

### ディレクトリ構造確認

```bash
# 必要なディレクトリが存在するか確認
ls -la backend/api/
ls -la backend/core/
ls -la frontend/
ls -la wrappers/
ls -la data/dev/  # 自動作成される
```

### 権限確認

```bash
# sudo ラッパースクリプトが実行可能か確認
ls -l /usr/local/sbin/adminui-* 2>/dev/null || echo "Wrappers not installed (development mode OK)"

# sudoers 設定確認（開発環境）
sudo -l | grep adminui || echo "No sudoers configuration (some features may not work)"
```

### セキュリティチェック

開発開始前に以下のコマンドを実行し、セキュリティ違反がないことを確認します。

```bash
# shell=True の使用を検出（検出された場合は即修正）
grep -r "shell=True" backend/ && echo "❌ shell=True detected!" || echo "✅ No shell=True"

# eval/exec の使用を検出
grep -r "eval(" backend/ && echo "❌ eval() detected!" || echo "✅ No eval()"
grep -r "exec(" backend/ && echo "❌ exec() detected!" || echo "✅ No exec()"
```

---

## 🧪 テストの実行

### 全テストの実行

```bash
# backend/ ディレクトリから実行
cd backend
pytest tests/ -v
```

### カバレッジレポート付きテスト

```bash
# カバレッジ測定
pytest tests/ -v --cov=backend --cov-report=html

# HTMLレポートの確認
xdg-open htmlcov/index.html
```

### セキュリティスキャン

```bash
# Bandit（セキュリティ脆弱性スキャン）
bandit -r backend/ -f json -o bandit-report.json
bandit -r backend/  # コンソール出力

# Safety（依存関係の脆弱性スキャン）
safety check
```

### コード品質チェック

```bash
# Black（フォーマットチェック）
black --check backend/

# Flake8（リントチェック）
flake8 backend/

# MyPy（型チェック）
mypy backend/
```

---

## 🐛 トラブルシューティング

### よくある問題と解決方法

#### 1. `ModuleNotFoundError: No module named 'fastapi'`

**原因**: 仮想環境がアクティブでない、または依存関係がインストールされていない。

**解決方法**:
```bash
source venv/bin/activate
pip install -r backend/requirements.txt
```

#### 2. `Permission denied` エラー

**原因**: sudo ラッパースクリプトが実行可能でない、または sudoers 設定がない。

**解決方法**:
```bash
# ラッパースクリプトに実行権限を付与
sudo chmod +x /usr/local/sbin/adminui-*

# sudoers 設定を追加（開発環境のみ）
sudo visudo -f /etc/sudoers.d/linux-management-dev
```

#### 3. データベースロックエラー

**原因**: 複数のプロセスが同じデータベースファイルにアクセスしている。

**解決方法**:
```bash
# 開発サーバーを停止
pkill -f uvicorn

# データベースファイルを削除して再作成
rm -f data/dev/database.db

# サーバーを再起動
uvicorn api.main:app --reload
```

#### 4. ポート番号が既に使用されている

**原因**: 別のプロセスがポート 5012 を使用している。

**解決方法**:
```bash
# ポートを使用しているプロセスを確認
sudo lsof -i :5012

# プロセスを終了（PIDを確認してから）
kill <PID>

# または、別のポート番号で起動
uvicorn api.main:app --reload --port 5013
```

---

## 📚 関連ドキュメント

開発を進める際は、以下のドキュメントも参照してください。

- [README.md](./README.md) - プロジェクト概要
- [CLAUDE.md](./CLAUDE.md) - ClaudeCode開発仕様・セキュリティ原則
- [CONTRIBUTING.md](./CONTRIBUTING.md) - コントリビューションガイド
- [SECURITY.md](./SECURITY.md) - セキュリティポリシー
- [docs/要件定義書_詳細設計仕様書.md](./docs/要件定義書_詳細設計仕様書.md) - 詳細要件・設計
- [docs/api-reference.md](./docs/api-reference.md) - API リファレンス

---

## 🔄 開発ワークフロー

### 推奨される開発フロー

```bash
# 1. 仮想環境のアクティベート
source venv/bin/activate

# 2. 最新コードの取得
git pull origin main

# 3. 依存関係の更新（必要に応じて）
pip install -r backend/requirements-dev.txt

# 4. 開発サーバーの起動
cd backend
uvicorn api.main:app --reload

# 5. コード編集

# 6. テストの実行
pytest tests/ -v

# 7. セキュリティチェック
bandit -r backend/
flake8 backend/

# 8. コミット前の最終確認
black backend/
pytest tests/ -v --cov=backend

# 9. Git コミット（CLAUDE.md の Git ポリシーに従う）
```

---

## 🔐 本番環境への移行

開発環境から本番環境への移行については、以下のドキュメントを参照してください。

- [docs/要件定義書_詳細設計仕様書.md](./docs/要件定義書_詳細設計仕様書.md) - デプロイメント戦略
- [SECURITY.md](./SECURITY.md) - 本番環境のセキュリティ設定

**重要な注意事項**:
- 本番環境では必ず HTTPS を使用してください
- `SESSION_SECRET` を強力なランダム文字列に変更してください
- sudoers 設定を最小権限の原則に基づいて構成してください
- データベースファイルの権限を適切に設定してください（`chmod 600`）

---

**⚠️ 開発環境のセキュリティ**

開発環境であっても、以下のセキュリティ原則を遵守してください:

1. **Allowlist First**: 定義されていない操作は全拒否
2. **Deny by Default**: 明示的に許可されたもののみ実行
3. **Shell禁止**: `shell=True` の使用を全面禁止
4. **sudo最小化**: ラッパースクリプト経由必須
5. **監査証跡**: 全操作のログ記録

詳細は [CLAUDE.md](./CLAUDE.md) を参照してください。
