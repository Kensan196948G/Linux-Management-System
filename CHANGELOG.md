# Changelog

All notable changes to the Linux Management System will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added (v0.5.0相当)
- **フロントエンド刷新**: Network/Servers/Hardware/監査ログ ページ追加
  - frontend/dev/network.html: ネットワーク情報ページ（タブ: インターフェース/接続/ルート/統計）
  - frontend/dev/servers.html: サーバー状態一覧ページ（nginx/apache2/mysql/postgresql/redis）
  - frontend/dev/hardware.html: ハードウェア情報ページ（タブ: メモリ/ディスク/センサー）
  - frontend/dev/audit.html: 監査ログ一覧ページ（フィルタ/ページネーション/エクスポート）
  - frontend/js/api.js: Network/Servers/Hardware APIメソッド追加
  - frontend/dev/dashboard.html: サイドバーに全新規ページへのリンク追加

- **Firewall モジュール（read-only）**: iptables/nftables/UFW ルール読み取り
  - wrappers/adminui-firewall.sh: rules/policy/status サブコマンド
  - GET /api/firewall/rules, /policy, /status
  - tests/integration/test_firewall_api.py: 22件テスト

- **Package Manager モジュール（apt）**: インストール済み/更新可能/セキュリティパッケージ一覧
  - wrappers/adminui-packages.sh: list/updates/security サブコマンド
  - GET /api/packages/installed, /updates, /security
  - tests/integration/test_packages_api.py: 20件テスト

- **承認ワークフロー拡張**: service_stop 操作を承認フローに追加
  - wrappers/adminui-service-stop.sh: サービス停止ラッパー（allowlist方式）
  - approval_service.py に service_stop dispatch 追加

- **SSH Server モジュール（read-only）**: sshd_config 状態確認・危険設定チェック
  - wrappers/adminui-ssh.sh: status/config サブコマンド
  - GET /api/ssh/status, /config
  - 危険設定自動検出（PermitRootLogin yes / PasswordAuthentication yes 等）
  - tests/integration/test_ssh_api.py: 20件テスト

- **監査ログ API + UI**: 全操作ログの可視化・エクスポート機能
  - GET /api/audit/logs: ページネーション付き一覧（Operator: 自分のみ / Admin: 全員）
  - GET /api/audit/logs/export: CSV/JSON エクスポート（Admin のみ）
  - frontend/dev/audit.html: フィルタ・ページネーション・エクスポートボタン付き UI
  - tests/integration/test_audit_api.py: 20件テスト

- **CI/CD強化**: E2Eテスト専用 workflow 追加
  - .github/workflows/e2e.yml: Playwright Chromium ヘッドレステスト実行
  - テストレポートをアーティファクトに保存（playwright-report/）

### Changed
- **auth.py**: 全ロールに `read:firewall`, `read:packages`, `read:ssh` 権限追加
- **auth.py**: Operator/Approver に `read:audit`, Admin に `read:audit`/`export:audit` 追加
- **sudo_wrapper.py**: get_firewall_*, get_packages_*, get_ssh_*, stop_service メソッド追加

---

### Added (v0.4.1相当)
- **E2Eテスト実装**: Playwright + pytest-playwright による API/UI E2Eシナリオテスト (40件)
  - tests/e2e/conftest.py: UvicornTestServer フィクスチャ (ポート18765)
  - tests/e2e/test_api_e2e.py: 認証/ネットワーク/サーバー/ハードウェア/RBAC シナリオ
  - tests/e2e/test_frontend_e2e.py: フロントエンドUI + 複数モジュールアクセスフロー

### Fixed (v0.4.1相当)
- **adminui-servers.sh**: `is-enabled` 出力の改行混入バグを修正 (`head -1` 使用)
- **adminui-network.sh**: `ss` connections 出力の `process` フィールド内の引用符エスケープ修正
- **backend/api/routes/servers.py**: Wrapper JSON パース修正（`AllServerStatusResponse` 500エラー解消）
- **backend/api/routes/network.py**: Wrapper JSON パース修正
- **backend/api/routes/hardware.py**: Wrapper JSON パース修正
- **backend/api/routes/_utils.py**: 共通 `parse_wrapper_result` ユーティリティ追加

### Planned for v0.5.0
- HTTPS対応（Nginx リバースプロキシ + TLS）
- Linux Firewall モジュール（iptables/nftables）
- SSH Server 設定モジュール
- Approval Workflow: user_modify/service_stop/firewall_modify 対応

---

## [0.4.0] - 2026-02-26

**v0.4 リリース** - Networking / Servers / Hardware モジュール実装・デプロイ基盤整備

### Added

#### Networking Module（ネットワーク管理）
- **GET /api/network/interfaces**: ネットワークインターフェース一覧 (ip -j addr show)
- **GET /api/network/stats**: インターフェース統計 (ip -j -s link show)
- **GET /api/network/connections**: アクティブな接続 (ss -j -tlnp)
- **GET /api/network/routes**: ルーティングテーブル (ip -j route show)
- **wrappers/adminui-network.sh**: 4サブコマンド allowlist、iproute2 JSON非対応環境フォールバック
- **read:network 権限**: 全ロール（Viewer/Operator/Approver/Admin）に追加

#### Servers Module（サーバー管理）
- **GET /api/servers/status**: 全5サーバー状態一括取得 (nginx/apache2/mysql/postgresql/redis)
- **GET /api/servers/{server}/status**: 個別サーバー状態 (systemctl show)
- **GET /api/servers/{server}/version**: バージョン情報
- **GET /api/servers/{server}/config**: 設定ファイルパス情報（内容は返さない）
- **wrappers/adminui-servers.sh**: allowlist 5サーバー、設定ファイルパス allowlist
- **read:servers 権限**: 全ロールに追加

#### Hardware Module（ハードウェア管理）
- **GET /api/hardware/disks**: ブロックデバイス一覧 (lsblk -J)
- **GET /api/hardware/disk_usage**: ディスク使用量 (df -P)
- **GET /api/hardware/smart?device=**: SMART情報 (smartctl -j -a)
- **GET /api/hardware/sensors**: 温度センサー (sensors -j / /sys/class/thermal/ フォールバック)
- **GET /api/hardware/memory**: メモリ情報 (/proc/meminfo)
- **wrappers/adminui-hardware.sh**: デバイスパス正規表現 allowlist（パストラバーサル対策）
- **read:hardware 権限**: 全ロールに追加

#### デプロイ基盤
- **scripts/setup/setup-sudoers.sh**: sudoers自動設定スクリプト（--dry-run/--yes/--uninstall）
- **scripts/deploy.sh**: 本番デプロイスクリプト（6フェーズ、--dry-run/--skip-sudoers）

#### 承認ワークフロー改善
- **execute_request()**: 承認後の自動実行ロジック実装（9操作タイプ対応）
- **execute_approved_action()**: 501スタブから実装に変更
- **executed_by カラム**: approval_requests テーブルに追加（後方互換マイグレーション）

### Tests
- test_network_api.py: 23件
- test_servers_api.py: 25件
- test_hardware_api.py: 34件
- 合計: **598 PASS / 104 SKIP**

---

## [0.3.0] - 2026-02-14

**v0.3 リリース** - 承認ワークフロー・ユーザー管理・Cronジョブ管理

### Added

#### Approval Workflow（承認ワークフロー）
- **ApprovalService**: 承認リクエストの作成・承認・拒否・有効期限管理（860行）
- **Approval API**: 12エンドポイント（作成/承認/拒否/一覧/詳細/キャンセル/期限切れ処理/ポリシー管理）
- **Approval UI**: 承認待ちリスト、承認操作画面（frontend/dev/approval.html）
- **HMAC署名**: 承認履歴の改ざん防止機構
- **承認ポリシー管理**: 操作種別ごとのリスクレベル・必要承認者数・タイムアウト設定

#### Users & Groups Management（ユーザー・グループ管理）
- **Users API**: ユーザー一覧/詳細/作成/削除/パスワード変更（10エンドポイント）
- **Groups API**: グループ一覧/作成/削除/メンバー変更（8エンドポイント）
- **Users UI**: ユーザー管理画面（frontend/dev/users.html）
- **sudoラッパー**: adminui-user-*.sh, adminui-group-*.sh（9ラッパー）
- **危険操作の承認フロー連携**: user_add/user_delete/group_add/group_delete は承認必須

#### Cron Jobs Management（Cronジョブ管理）
- **Cron API**: Cronジョブ一覧/追加/削除/有効無効切替（6エンドポイント）
- **Cron UI**: Cronジョブ管理画面（frontend/dev/cron.html）
- **sudoラッパー**: adminui-cron-*.sh（4ラッパー）
- **コマンドallowlist**: 9コマンドのみ許可（rsync/healthcheck/find/tar/gzip/curl/wget/python3/node）

#### 共通モジュール
- **validation.py**: 入力検証共通ロジック（特殊文字検出、ユーザー名検証、UID/GID範囲検証）
- **constants.py**: 禁止ユーザー名100+件、禁止グループ名、許可シェル定義

### Security
- **4層防御アーキテクチャ**: Frontend→API→Service→Wrapper の多段検証
- **STRIDE脅威分析**: Users(11件)/Cron(7件)/Approval(8件) の脅威分析完了
- **Allowlistポリシー文書化**: 全モジュールのallowlist/denylistを文書化

### Testing
- **テストカバレッジ**: 92.69%（462件PASS）
- **セキュリティテスト**: approval/users/cron/processes の各種セキュリティテスト追加
- **統合テスト**: approval/users/cron/processes APIの統合テスト追加

---

## [0.2.0] - 2026-02-07

**v0.2 リリース** - Running Processes詳細表示・CI/CD整備

### Added

#### Running Processes（プロセス管理）
- **Processes API**: プロセス一覧取得・詳細表示・フィルタリング・ソート機能
- **Processes UI**: プロセス管理画面（frontend/dev/processes.html、JavaScript連携）
- **sudoラッパー**: adminui-processes.sh（詳細プロセス情報取得）
- **CPU/Memoryリアルタイム表示**: 使用率の正確な小数点表示

#### Frontend改善
- **サイドバー日本語化**: メニュー項目の完全日本語対応（menu-i18n.js、menu-ja.json）
- **メニュー構造再設計**: Webmin互換のカテゴリ構造に再編成
- **ユーザー情報UI改善**: ログインユーザー情報のアイコン表示

### Fixed
- processes.jsのレスポンス構造処理バグ修正
- CPU/メモリ使用率の整数→浮動小数点変換バグ修正
- Edge/Safari対応のlocalStorage互換性修正
- ダッシュボードリダイレクト問題の修正

### CI/CD
- **CI/CD復旧**: GitHub Actions CI成功率 0% → 100%
- **ShellCheck**: Bashスクリプトの静的解析追加
- **セキュリティパターン検出**: shell=True/os.system/eval/exec の自動検出
- **カバレッジレポート**: htmlcov/アーティファクト生成

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
