# Changelog

All notable changes to the Linux Management System will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned for v0.2.0
- Users and Groups Management module
- Cron Jobs Management module
- Running Processes detailed view
- Network Configuration module
- SSH Server configuration module

---

## [0.1.0] - 2026-02-06

**Initial Release** - 基本監視・操作機能の実装完了

### Added

#### Core Features
- **System Status Monitoring**: CPU使用率、メモリ使用量、ディスク使用状況のリアルタイム監視
- **Service Management**: allowlistベースのサービス再起動機能（nginx, postgresql, redis対応）
- **Log Viewing**: journalctl経由のシステムログ閲覧機能（フィルタリング、検索機能付き）

#### Authentication & Authorization
- **JWT-based Authentication**: JSON Web Tokenによる認証機構
- **Role-Based Access Control (RBAC)**: ユーザーロールベースの権限管理
  - Viewer: 参照のみ
  - Operator: 限定的な操作（サービス再起動）
  - Approver: 危険操作の承認権限（将来拡張用）
  - Admin: システム設定管理
- **Session Management**: セッション管理とトークンリフレッシュ機能

#### Security Features
- **Allowlist-First Design**: 定義されていない操作は全拒否
- **sudo Wrapper Scripts**: sudo権限の厳格な制御（ラッパースクリプト経由のみ実行可能）
- **Input Validation**: 特殊文字の検出と拒否（Shell Injection対策）
- **Audit Logging**: 全操作の証跡記録（誰が・いつ・何を・結果）
- **Security Headers**: CORS設定、XSS対策、CSRF対策

#### Backend (FastAPI)
- **RESTful API**: FastAPIベースのREST API実装
- **Async Database**: aiosqliteによる非同期SQLiteデータベース操作
- **Configuration Management**: python-dotenvによる環境変数管理
- **Error Handling**: 統一されたエラーハンドリングとHTTPステータスコード
- **API Documentation**: OpenAPI/Swagger UIによる自動生成APIドキュメント

#### Frontend (HTML/CSS/JavaScript)
- **Responsive UI**: Webmin風のレスポンシブWebインターフェース
- **Real-time Updates**: システム状態のリアルタイム更新（自動リフレッシュ）
- **Interactive Dashboard**: ダッシュボード形式のシステム概要表示
- **Client-side Validation**: ユーザー入力のクライアント側検証

#### Development Infrastructure
- **ClaudeCode Integration**: ClaudeCode主導開発体制の確立
- **SubAgent Architecture**: 7体のSubAgent構成（Planner, Architect, Backend, Frontend, Security, QA, CIManager）
- **Automated Testing**: pytestベースのテストフレームワーク
- **CI/CD Pipeline**: GitHub Actionsによる自動テスト・セキュリティスキャン

#### Documentation
- **CLAUDE.md**: ClaudeCode開発仕様・セキュリティ原則
- **SECURITY.md**: セキュリティポリシーと脆弱性報告手順
- **README.md**: プロジェクト概要とクイックスタート
- **ENVIRONMENT.md**: 開発環境セットアップガイド
- **CONTRIBUTING.md**: コントリビューションガイドライン
- **CHANGELOG.md**: 変更履歴（本ファイル）
- **docs/要件定義書_詳細設計仕様書.md**: 詳細要件・設計仕様
- **docs/開発環境仕様書.md**: 開発環境詳細
- **docs/api-reference.md**: API リファレンス

### Security

#### Implemented Protections
- **Shell Injection Prevention**: `shell=True` の全面禁止、配列引数による安全なコマンド実行
- **Command Injection Prevention**: 特殊文字の検出と拒否（`;`, `|`, `&`, `$`, `` ` ``, etc.）
- **Path Traversal Prevention**: ファイルパスの検証とサニタイゼーション
- **SQL Injection Prevention**: パラメータ化クエリの徹底使用
- **XSS Prevention**: 入力のエスケープ処理とContent Security Policy
- **CSRF Prevention**: CORS設定とトークンベース認証

#### Security Audit Tools
- **Bandit**: Pythonコードのセキュリティ脆弱性スキャン
- **Safety**: 依存関係の既知の脆弱性チェック
- **Flake8**: コード品質とセキュリティパターンのチェック
- **ShellCheck**: Bashスクリプトのセキュリティチェック（将来導入）

#### Audit Logging
- **Operation Logs**: 全操作のJSON形式ログ記録
- **Authentication Logs**: ログイン・ログアウトの記録
- **Error Logs**: エラーと例外の詳細記録
- **Log Rotation**: ログローテーション機構（将来実装）

### Testing

#### Test Coverage
- **Backend Core**: 90%以上のカバレッジ目標
- **Backend API**: 85%以上のカバレッジ目標
- **Wrapper Scripts**: 100%のカバレッジ目標（全パターンテスト）

#### Test Types
- **Unit Tests**: 個別関数・クラスの単体テスト
- **Integration Tests**: API統合テスト
- **Security Tests**: セキュリティ脆弱性のテスト
- **E2E Tests**: エンドツーエンドテスト（将来実装）

### Configuration

#### Environment Variables
- `GITHUB_TOKEN`: GitHub API アクセストークン（CI/CD用）
- `DEV_IP`, `DEV_PORT`: 開発環境のIP/ポート設定
- `PROD_IP`, `PROD_PORT`: 本番環境のIP/ポート設定
- `DB_PATH`: データベースファイルパス
- `SESSION_SECRET`: セッション暗号化鍵
- `LOG_LEVEL`: ログレベル（DEBUG, INFO, WARNING, ERROR）

#### Database Schema
- **users**: ユーザー情報テーブル
- **roles**: ロール定義テーブル
- **audit_logs**: 監査ログテーブル
- **sessions**: セッション管理テーブル

### Known Limitations

#### v0.1.0 Constraints
- **参照系のみ**: 現時点では読み取り専用機能が中心（サービス再起動を除く）
- **限定サービス対応**: allowlistに登録されたサービスのみ再起動可能
- **シングルサーバー**: クラスタ管理機能は未実装
- **承認フロー未実装**: 危険操作の承認フローは v0.3 で実装予定

#### Security Trade-offs
- **sudoers手動設定**: 初回セットアップ時に sudoers ファイルを手動編集する必要がある
- **HTTPS未対応**: 開発環境ではHTTPのみ（本番環境ではリバースプロキシ推奨）

### Dependencies

#### Production Dependencies
- fastapi==0.115.6
- uvicorn==0.34.0
- python-jose==3.3.0
- passlib==1.7.4
- aiosqlite==0.20.0
- python-dotenv==1.0.1
- pydantic==2.10.6
- cryptography==44.0.0

#### Development Dependencies
- pytest==8.3.4
- pytest-cov==6.0.0
- bandit==1.8.0
- black==24.10.0
- flake8==7.1.1
- mypy==1.14.1

Full dependency list: [backend/requirements.txt](./backend/requirements.txt), [backend/requirements-dev.txt](./backend/requirements-dev.txt)

---

## [0.0.1] - 2026-01-15

### Added
- Initial project structure
- Basic FastAPI backend setup
- Proof-of-concept sudo wrapper

### Changed
- None

### Deprecated
- None

### Removed
- None

### Fixed
- None

### Security
- Initial security baseline established

---

## Version Naming Convention

本プロジェクトは Semantic Versioning を採用しています:

- **MAJOR.MINOR.PATCH** (例: 1.2.3)
  - **MAJOR**: 後方互換性のない変更
  - **MINOR**: 後方互換性のある機能追加
  - **PATCH**: 後方互換性のあるバグ修正

### Release Phases

- **v0.x.x**: 開発フェーズ（現在）
- **v1.0.0**: 本番運用開始リリース
- **v2.0.0+**: 大規模な機能拡張・アーキテクチャ変更

---

## Changelog Maintenance

### 変更記録のルール

1. **ユーザー視点**: 技術的な詳細よりもユーザーへの影響を記述
2. **カテゴリ分類**: Added/Changed/Deprecated/Removed/Fixed/Security
3. **時系列順**: 新しい変更を上部に追加
4. **リンク**: 関連するIssue/PRへのリンクを含める（該当する場合）

### 例

```markdown
### Added
- New module for user management (#123)

### Fixed
- Fix authentication bypass vulnerability (CVE-2026-XXXX) (#456)

### Security
- Update cryptography library to address CVE-2026-YYYY
```

---

## Links

- [Project Homepage](https://github.com/Kensan196948G/Linux-Management-System)
- [Issue Tracker](https://github.com/Kensan196948G/Linux-Management-System/issues)
- [Security Policy](./SECURITY.md)
- [Contributing Guide](./CONTRIBUTING.md)

---

**Note**: このファイルは全てのリリース時に更新され、Git管理されます。変更履歴は永続的に保持されます。
