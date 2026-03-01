# Changelog

All notable changes to the Linux Management System will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [v0.22.0] - 2026-03-01

### Added (Step 26)
- セキュリティ監査レポート機能
  - `GET /api/security/audit-report` — 監査ログ統計レポート
  - `GET /api/security/failed-logins` — ログイン失敗一覧
  - `GET /api/security/sudo-logs` — sudoログ
  - `GET /api/security/open-ports` — オープンポート一覧
  - `GET /api/security/bandit-status` — Banditセキュリティスキャン結果
- `wrappers/adminui-security.sh` — セキュリティ情報ラッパー
- `frontend/dev/security.html` — セキュリティ監査UI（失敗ログイン10件以上で赤色警告）

---

## [v0.21.0] - 2026-03-01

### Added (Step 24-25)
- Apache設定管理強化
  - `GET /api/apache/vhosts-detail` — バーチャルホスト詳細
  - `GET /api/apache/ssl-certs` — SSL証明書一覧
- ログ集約+検索UI
  - `GET /api/logs/search` — ログ全文検索
  - `GET /api/logs/files` — ログファイル一覧
  - `GET /api/logs/recent-errors` — 最近のエラー
- `wrappers/adminui-logsearch.sh` — ログ検索ラッパー
- `frontend/dev/logs.html` 強化（検索バー・フィルタ・ハイライト）

---

## [v0.20.0] - 2026-03-01

### Added (Step 22-23)
- Cron UI強化
  - `GET /api/cron/validate` — cron式バリデーション（禁止文字チェック付き）
  - `frontend/dev/cron.html` — collapsibleバリデーターパネル
- Users/Groups UI強化
  - `GET /api/users/groups` — グループ一覧エイリアス
  - `GET /api/users/list` — ユーザー一覧エイリアス
  - `frontend/dev/users.html` — タブUI・承認申請フォーム強化

---

## [0.14.0] - 2026-03-01

**v0.14.0 リリース** - HTTPS/TLS本番対応 + システム設定モジュール + UIテーマ管理

### Added

#### HTTPS/TLS 本番対応 (Step 10)
- **scripts/generate-ssl-cert.sh**: RSA 4096bit / SHA256 / SAN付き自己署名証明書生成スクリプト
  - `/etc/ssl/adminui/` に証明書を生成 (cert=644, key=600)
  - ShellCheck 通過
- **scripts/setup-https.sh**: nginx HTTPS 環境一括セットアップスクリプト
  - 証明書生成 → nginx設定コピー → シンボリックリンク → `nginx -t` 検証
- **config/nginx/adminui-http-only.conf**: 開発環境用 HTTP のみ nginx 設定
- **docs/guides/https-setup.md**: Let's Encrypt / 自己署名証明書のセットアップガイド (日本語)
- **tests/unit/test_ssl_config.py**: SSL 設定テスト 18 件

#### System Configuration モジュール (Step 11)
- **wrappers/adminui-sysconfig.sh**: `hostname`/`timezone`/`locale`/`kernel`/`uptime`/`modules` allowlist制御
- **GET /api/sysconfig/hostname**: ホスト名情報
- **GET /api/sysconfig/timezone**: タイムゾーン情報
- **GET /api/sysconfig/locale**: ロケール情報
- **GET /api/sysconfig/kernel**: カーネル情報
- **GET /api/sysconfig/uptime**: システム稼働時間
- **GET /api/sysconfig/modules**: カーネルモジュール一覧
- **frontend/dev/sysconfig.html** / **frontend/prod/sysconfig.html**: システム設定UI + ライト/ダークテーマ切り替え

### Tests
- **1952 PASS / 0 FAIL / 41 SKIP**
- カバレッジ: 95.46%

---

## [0.13.0] - 2026-02-29

**v0.13.0 リリース** - FTP/Squid/DHCP/Sensors/Routing モジュール群

### Added

#### v0.13 モジュール (Step 7-9)
- **FTP/ProFTPD 管理** (`GET /api/ftp/*`): status/users/config/logs
- **Squid Proxy 管理** (`GET /api/squid/*`): status/cache/config/logs
- **DHCP Server 管理** (`GET /api/dhcp/*`): status/leases/config/pools/logs
- **lm-sensors 監視** (`GET /api/sensors/*`): all/temperature/fans/voltage
- **Routing & Gateways** (`GET /api/routing/*`): routes/gateways/arp/interfaces
- 各モジュールに wrappers/adminui-*.sh (allowlist制御), テスト20-25件

### Tests
- **1907 PASS / 0 FAIL / 41 SKIP**
- カバレッジ: 95.43%

---

## [0.12.0] - 2026-02-28

**v0.12.0 リリース** - SMART/Partitions/Netstat/BIND DNS モジュール群

### Added
- **SMART Drive Status** (`GET /api/smart/*`): disks/info/health/tests
- **Disk Partitions** (`GET /api/partitions/*`): list/usage/detail
- **Netstat** (`GET /api/netstat/*`): connections/listening/stats/routes
- **BIND DNS Server** (`GET /api/bind/*`): status/zones/config/logs

### Tests
- **1798 PASS / 0 FAIL / 41 SKIP** / カバレッジ: 95.94%

---

## [0.11.0] - 2026-02-28

**v0.11.0 リリース** - MySQL/MariaDB + PostgreSQL 管理モジュール

### Added
- **MySQL/MariaDB 管理** (`GET /api/mysql/*`): status/databases/users/processes/variables/logs
- **PostgreSQL 管理** (`GET /api/postgresql/*`): status/databases/users/activity/config/logs

### Tests
- **1745 PASS / 0 FAIL / 41 SKIP** / カバレッジ: 96%

---

## [0.10.1] - 2026-02-27

**v0.10.1 リリース** - 本番環境準備完了・Systemd本番サービス稼働

### Added

#### 本番環境 Systemd サービス
- **systemd/linux-management-prod.service**: 本番環境自動起動サービス
  - `User=kensan`・`WorkingDirectory=/mnt/LinuxHDD/Linux-Management-Systm`
  - gunicornパス: `/home/kensan/.local/bin/gunicorn`（user install）
  - `ExecStartPre=detect-ip.sh` でIP自動検出
  - `workers=2 / worker-class=uvicorn.workers.UvicornWorker`
  - `Restart=always / RestartSec=10s`（本番用自動再起動）
  - `LimitNPROC` 削除（多プロセス環境でのEAGAIN防止）

#### 本番環境バッジ（フロントエンド）
- **frontend/js/env-config.js**: 本番（赤・PROD）/開発（黄・DEV）バッジを切り替え表示
- `getApiBaseUrl()`: `/api/info` の `api_base` フィールドを優先

### Changed
- `config/prod.json`:
  - `cors_origins`: HTTPSのみ（セキュリティポリシー準拠）
  - `require_https: true`（セキュリティポリシー遵守）
  - `ssl_enabled: false`（現在は証明書未設定・HTTP8000で運用）
  - `allowed_services`: nginx/apache2/postgresql/mysql/redis/postfix/ssh/cronに拡充
  - `database.path`: プロジェクトディレクトリ配下に変更
- `backend/api/main.py`:
  - `GET /api/info`: version=0.10.0、`ssl_enabled`・`api_base`フィールド追加
  - `validate_production_config`: `require_https` チェックをRuntimeErrorに維持（セキュリティテスト対応）

### Tests
- **1029 PASS / 0 FAIL / 42 SKIP**（テスト50件増）
- カバレッジ: 89.22%

### Infrastructure
- 開発環境 Systemd: **active (running)** ✅  `http://192.168.0.185:5012`
- 本番環境 Systemd: **active (running)** ✅  `http://192.168.0.185:8000`
- 両環境が同時稼働・自動起動設定済み

---

## [0.10.0] - 2026-02-27

**v0.10.0 リリース** - 動的IP検出・URL設定・Systemd自動起動登録

### Added

#### 動的IP検出システム
- **scripts/detect-ip.sh**: デフォルトルートNIC経由でIPを自動検出
  - 3段階フォールバック: UDP trick → hostname -I → 127.0.0.1
  - `.env.runtime` に DEV/PROD の URL・ポート情報を書き出す
  - Systemd `ExecStartPre` とスタンドアロン両方で利用可能
  - ShellCheck エラーゼロ確認済み
- **backend/core/config.py**: `_detect_primary_ip()` / `_build_cors_origins()` 追加
  - 起動時に実際のIPを取得しCORS・api_base_urlを動的設定
  - `.env.runtime` → 環境変数 → UDP socket の優先順位でIP取得
- **GET /api/info エンドポイント**: 環境/IP/ポート/URL情報をJSON返却
  - `{"detected_ip":"192.168.0.185","urls":{"http":"...","api_http":"..."},...}`
- **frontend/js/env-config.js**: `/api/info` から動的URLを取得してフロントエンドに設定
  - DEV環境ではページ右上にDEVバッジ表示
  - `window.API_BASE_URL` を自動設定

#### Systemd サービス登録
- **systemd/linux-management-dev.service**: 開発環境自動起動サービス
  - `ExecStartPre=detect-ip.sh` でIP自動検出
  - `After=network-online.target` でネットワーク待機
  - `PATH=/home/kensan/.local/bin:...` でuvicorn/gunicornを認識
  - `EnvironmentFile=-.env.runtime` で動的IP変数を読み込む
- **systemd/linux-management-prod.service**: 本番環境サービス（同様の改善）
- **scripts/install-service.sh**: 全面書き直し（自動化・6コマンド対応）
  - `dev/prod/status/start/stop/restart/log/uninstall` コマンド
  - detect-ip.sh を自動呼び出し

### Changed
- `config/dev.json`: 固定IP削除・CORS動的化（CORS自動生成）
- `scripts/start-dev-server.sh`: `--systemd` オプション追加・動的URL表示
- `backend/api/main.py`: 起動ログに Detected IP・URL 追加
- `.gitignore`: `.env.runtime` を除外（動的生成ファイル）

### Tests
- 979 PASS / 0 FAIL / 41 SKIP（既存テスト全通過）
- カバレッジ: 88.92%

### Infrastructure
- Systemd dev サービス: **active (running)** ✅
- 検出IP: 192.168.0.185
- Dev URL: http://192.168.0.185:5012
- API Info: http://192.168.0.185:5012/api/info

---

## [0.9.2] - 2026-03-01

**v0.9.2 リリース** - Postfix メール管理モジュール・テスト安定化

### Added

#### Postfix メール管理モジュール
- **wrappers/adminui-postfix.sh**: Postfix 管理ラッパースクリプト
  - status/queue/logs/mailq サブコマンド（allowlist 制御）
  - postfix 未インストール環境では `{"status":"unavailable"}` フォールバック
  - ログ行数を 1〜200 に制限（上限なし入力を拒否）
  - ShellCheck エラーゼロ確認済み
- **GET /api/postfix/status**: Postfix サービス状態・バージョン・キュー件数
- **GET /api/postfix/queue**: メールキュー内容
- **GET /api/postfix/logs**: Postfix ログ取得（lines=1〜200 パラメータ）
- **frontend/dev/postfix.html**: Postfix 管理 WebUI（タブ切替・リアルタイム更新）
- **tests/integration/test_postfix_api.py**: 20件テスト (TC_PTF_001〜020) 全 PASS

### Fixed
- `tests/integration/test_api.py::TestSystemStatusError`: `raise_server_exceptions=False` を使用して 500 レスポンスを正しくテスト
- `tests/integration/test_time_api.py::TestTimeErrorPaths`: `get_available_timezones` → `get_timezones` メソッド名修正

### Changed
- `backend/core/sudo_wrapper.py`: Postfix 3メソッド追加（get_postfix_status/queue/logs）
- `backend/api/main.py`: postfix router 登録
- `frontend/js/sidebar.js`: postfix ページルート・タイトル追加

### Tests
- 979 PASS / 0 FAIL / 41 SKIP
- カバレッジ: 89.23%（目標 80% 達成）

---

## [0.9.1] - 2026-03-01

**v0.9.1 リリース** - テストカバレッジ向上・エラーパス補完

### Added
- **tests/integration/test_bootup_api.py**: TestBootupDisableAPI (9件) + TestBootupStatusWrapperError 追加
- **tests/integration/test_firewall_api.py**: TestFirewallWriteOperations (11件) - POST/DELETE 承認フロー
- **tests/integration/test_time_api.py**: TestTimeErrorPaths (5件) - SudoWrapperError エラーパス
- **tests/integration/test_dbmonitor_api.py**: TestDBMonitorErrorPaths (5件) - 各エンドポイント 503 エラー

### Tests
- 959 PASS / 0 FAIL / 41 SKIP
- カバレッジ: 89.20%

---

## [0.9.0] - 2026-03-01

**v0.9.0 リリース** - Apache Webserver 管理モジュール

### Added

#### Apache Webserver モジュール
- **wrappers/adminui-apache.sh**: Apache 管理ラッパースクリプト
  - status/vhosts/modules/config-check サブコマンド
  - apache2ctl/apachectl/apache2/httpd を自動検出
  - 未インストール環境では `{"status":"unavailable"}` フォールバック
  - ShellCheck エラーゼロ確認済み
- **GET /api/apache/status**: Apache サービス状態・バージョン
- **GET /api/apache/vhosts**: バーチャルホスト一覧
- **GET /api/apache/modules**: 有効化モジュール一覧
- **GET /api/apache/config-check**: 設定構文検証
- **frontend/dev/apache.html**: Apache 管理 WebUI（タブ切替・リアルタイム更新）
- **tests/integration/test_apache_api.py**: 20件テスト (TC_APH_001〜020) 全 PASS

### Changed
- `backend/core/sudo_wrapper.py`: Apache 4メソッド追加（get_apache_status/vhosts/modules/config_check）
- `backend/api/main.py`: apache router 登録
- `frontend/js/sidebar.js`: apache ページルート追加

### Tests
- 927 PASS / 0 FAIL / 41 SKIP
- カバレッジ: 86.75%

---

## [0.8.2] - 2026-03-01

**v0.8.2 リリース** - Bandwidth Monitoring モジュール

### Added

#### Bandwidth Monitoring 帯域幅監視モジュール
- **wrappers/adminui-bandwidth.sh**: 帯域幅監視ラッパースクリプト
  - list/summary/daily/hourly/live/top サブコマンド
  - vnstat 使用（未インストール時は ip -s link でフォールバック）
  - インターフェース名 allowlist 検証（正規表現 `^[a-zA-Z0-9._-]{1,32}$`）
  - /sys/class/net/ 経由の 1秒サンプリングリアルタイム計測
- **GET /api/bandwidth/interfaces**: ネットワークインターフェース一覧
- **GET /api/bandwidth/summary**: 帯域幅サマリ（vnstat/ip）
- **GET /api/bandwidth/daily**: 日別トラフィック統計（vnstat）
- **GET /api/bandwidth/hourly**: 時間別トラフィック統計（vnstat）
- **GET /api/bandwidth/live**: 1秒サンプリングリアルタイム帯域幅
- **GET /api/bandwidth/top**: 全インターフェース累積トラフィック
- **frontend/dev/bandwidth.html**: 帯域幅監視 WebUI（自動更新 3秒・インターフェース切替）
- **tests/integration/test_bandwidth_api.py**: 20件テスト (TC_BW_001〜020)

### Changed
- `backend/core/sudo_wrapper.py`: Bandwidth 監視メソッド 6件追加 + `re` モジュールインポート
- `backend/api/main.py`: bandwidth router 登録
- `frontend/js/sidebar.js`: bandwidth ページルート追加

### Tests
- 907 PASS / 0 FAIL / 0 ERROR
- カバレッジ: 86.40%

---

## [0.8.1] - 2026-03-01

**v0.8.1 リリース** - DB監視モジュール（MySQL/PostgreSQL）

### Added

#### DB Monitor データベース監視モジュール
- **wrappers/adminui-dbmonitor.sh**: MySQL/PostgreSQL 監視ラッパースクリプト
  - mysql status/processlist/variables/databases サブコマンド
  - postgresql status/connections/databases/activity サブコマンド
  - DBクライアント未インストール時 `{"status":"unavailable"}` フォールバック
- **GET /api/dbmonitor/{db_type}/status**: DBサービス状態・バージョン
- **GET /api/dbmonitor/{db_type}/processes**: プロセス/アクティビティ一覧
- **GET /api/dbmonitor/{db_type}/databases**: データベース一覧
- **GET /api/dbmonitor/{db_type}/connections**: 接続一覧
- **GET /api/dbmonitor/{db_type}/variables**: 変数・設定情報
- **frontend/dev/dbmonitor.html**: DB監視 WebUI（MySQL/PostgreSQL タブ切替）
- **tests/integration/test_dbmonitor_api.py**: 20件テスト (TC_DBM_001〜020)

### Changed
- `backend/core/sudo_wrapper.py`: DBモニターメソッド 5件追加
- `backend/api/main.py`: dbmonitor router 登録
- `frontend/js/sidebar.js`: dbmonitor ページルート追加

---

## [0.8.0] - 2026-02-27

**v0.8 リリース** - テスト安定化（110 ERROR → 0）・Disk Quotas モジュール

### Added

#### Disk Quotas 管理モジュール
- **wrappers/adminui-quotas.sh**: ディスククォータ管理ラッパースクリプト
  - status/user/group/users/set/report サブコマンド
  - quota ツール未インストール時のフォールバック（`{"status":"unavailable"}`）
  - allowlist 制御（user/group/filesystem パターン正規表現検証）
  - setquota による user/group クォータ設定（soft/hard/inode）
- **GET /api/quotas/status**: ファイルシステム別クォータ状態取得
- **GET /api/quotas/users**: 全ユーザークォータ一覧
- **GET /api/quotas/user/{username}**: 特定ユーザーのクォータ情報
- **GET /api/quotas/group/{groupname}**: 特定グループのクォータ情報
- **GET /api/quotas/report**: 詳細クォータレポート
- **POST /api/quotas/set**: ユーザー/グループクォータ設定（Admin/Approver のみ）
  - Pydantic バリデーション（名前・ファイルシステムパターン・値範囲）
- **tests/integration/test_quotas_api.py**: 25件テスト（全 PASS）
- **frontend/dev/quotas.html**: ディスククォータ管理 WebUI
  - ユーザークォータ一覧（使用率バー・状態バッジ）
  - クォータレポート表示
  - クォータ設定フォーム（write:quotas 権限保持者のみ表示）
- **backend/core/auth.py**: 全ロールに `read:quotas` 権限追加、Admin/Approver に `write:quotas` 追加
- **frontend/dev/dashboard.html**: ダッシュボードメニューに「ディスククォータ」追加

### Fixed

#### テスト安定化（0 ERROR・0 FAIL 達成）
- **110 ERROR → 0 ERROR**: `asyncio.new_event_loop().run_until_complete()` → `sqlite3` 同期 DB 初期化に変換
  - `tests/conftest.py`: `_init_approval_db_sync()` 追加、asyncio 依存を完全排除
  - `tests/integration/test_approval_api.py`: module-scope fixture + sqlite3 クリーンアップ
  - `tests/integration/test_approval_extended.py`: 同上
  - `tests/unit/test_approval_service.py`: `run_async()` を ThreadPoolExecutor 対応に変更
- **6 FAIL → 0 FAIL** (`TestJWTSecretValidation`): `@pytest.mark.asyncio` + `@patch` の running loop 競合を解消
  - `tests/security/test_security_hardening.py`: async テストを同期化、`_run_async()` (ThreadPoolExecutor) を使用
- **pytest.ini**: `asyncio_mode = auto`・`asyncio_default_fixture_loop_scope = function` 追加

### Statistics
- テスト数: 764 → 902 PASS (+138件)
- ERROR: 110 → 0
- FAIL: 6 → 0

---

## [0.7.0] - 2026-02-27

**v0.7 リリース** - Bootup/Shutdown管理・System Time管理・GitHub Copilot統合設定

### Added

#### Bootup/Shutdown 管理モジュール
- **wrappers/adminui-bootup.sh**: 起動・シャットダウン管理ラッパースクリプト
  - status/services/enable/disable/shutdown/reboot/poweroff サブコマンド
  - allowlist 制御、特殊文字チェック、JSON出力
- **GET /api/bootup/status**: ブートロード情報・起動時間取得
- **GET /api/bootup/services**: 自動起動設定済みサービス一覧
- **POST /api/bootup/enable**: 自動起動 enable（Admin のみ）
- **POST /api/bootup/disable**: 自動起動 disable（Admin のみ）
- **POST /api/bootup/action**: shutdown/reboot/poweroff 実行（Admin のみ、遅延 allowlist 制御）
- **tests/integration/test_bootup_api.py**: 38件テスト（全 PASS）

#### System Time 管理モジュール
- **wrappers/adminui-time.sh**: システム時刻・タイムゾーン管理ラッパースクリプト
  - パストラバーサル防止、zoneinfo ファイル存在検証
- **GET /api/time/status**: 現在時刻・タイムゾーン・NTP 状態取得
- **GET /api/time/timezones**: 利用可能タイムゾーン一覧
- **POST /api/time/timezone**: タイムゾーン変更（Admin のみ、Pydantic バリデーション）
- **backend/api/routes/system_time.py**: `time` 組み込みモジュールとの競合回避のため `system_time.py` として命名
- **tests/integration/test_time_api.py**: 38件テスト（全 PASS）

#### GitHub Copilot 統合設定
- **.github/copilot-instructions.md**: GitHub Copilot 向けプロジェクト指示書
  - セキュリティルール、ディレクトリ構造、API追加手順、ロール権限、コーディング規約
- **.github/copilot/skills/new-module.md**: 新モジュール追加テンプレート
- **.github/copilot/skills/security-audit.md**: セキュリティ監査スキル定義
- **.github/copilot/teams/dev-team.md**: SubAgent 7体構成（@Planner/@Architect/@Backend/@Frontend/@Security/@QA/@CIManager）

#### フロントエンド UI
- **frontend/dev/bootup.html**: 起動管理UI（起動状態・サービス管理・システム操作 3タブ構成、確認モーダル付き）
- **frontend/dev/time.html**: システム時刻管理UI（リアルタイムクロック・タイムゾーン変更 2タブ構成）
- **dashboard.html**: 起動・シャットダウン・システム時刻をメニューに追加（実装済みリンク）
- **frontend/js/sidebar.js**: bootup/system-time ページへのナビゲーション追加

### Fixed
- **tests/conftest.py**: `asyncio.get_event_loop().run_until_complete()` → `asyncio.run()` に修正（Python 3.12 対応）
- **backend/core/approval_service.py**: `user_add` 自動実行時の `password_hash` KeyError 修正（デフォルト `"!"` 使用）

### Security
- Bootup 操作（enable/disable/shutdown/reboot）は Admin ロール限定
- タイムゾーン変更は Admin ロール限定
- 遅延値は allowlist `["now", "+1", "+2", "+5", "+10", "+30", "+60"]` で検証
- タイムゾーン名は正規表現 + zoneinfo ファイル存在の二重チェック
- `time.py` → `system_time.py` リネーム（Python 組み込み `time` モジュール競合防止）

---

## [0.6.0] - 2026-02-26

**v0.6 リリース** - Approval完全実装・セキュリティ強化・ファイルシステム管理・HTTPS対応

### Added

#### Approval Workflow 完全実装
- **wrappers/adminui-user-modify.sh**: ユーザー属性変更ラッパー（set-shell/set-gecos/add-group/remove-group）
  - シェル allowlist（7種のみ）、UID < 1000 システムユーザー保護、特権グループ追加禁止
- **approval_service.py**: user_modify / firewall_modify dispatch 完全実装
- **sudo_wrapper.py**: modify_user_shell/gecos/add_group/remove_group メソッド追加
- **tests/integration/test_approval_extended.py**: 17件テスト（全PASS）

#### セキュリティ強化
- **セキュリティヘッダー middleware**: X-Content-Type-Options / X-Frame-Options / X-XSS-Protection / Referrer-Policy / CSP / HSTS
- **APIレート制限**: 1分あたり60リクエスト上限（インメモリ）
- **ログインブルートフォース対策**: 5回失敗→15分ロック
- **Bandit Medium 0件**: 全 Medium/High 警告解消

#### HTTPS/TLS 対応
- **config/nginx/adminui.conf**: HTTP→HTTPS 308 リダイレクト + TLS 1.2/1.3 設定
- **scripts/setup-nginx.sh**: 自己署名証明書または外部証明書インストールスクリプト
- **docs/guides/production-deploy.md**: 本番デプロイ手順書（日本語）

#### Firewall 書き込みモジュール
- **wrappers/adminui-firewall-write.sh**: allow-port/deny-port/delete-rule（ポート allowlist）
- **POST /api/firewall/rules**: UFW ルール追加（承認フロー経由、Admin のみ）
- **DELETE /api/firewall/rules/{rule_num}**: ルール削除（承認フロー経由）
- **auth.py**: write:firewall 権限追加（Admin ロール）

#### ファイルシステム管理モジュール
- **wrappers/adminui-filesystem.sh**: df/du/mounts サブコマンド（パス allowlist）
- **GET /api/filesystem/usage**: ファイルシステム使用量（85% 警告付き）
- **GET /api/filesystem/mounts**: マウントポイント一覧
- **tests/integration/test_filesystem_api.py**: 20件テスト（全PASS）

#### 設定統合UI
- **frontend/dev/settings.html**: SSH設定/ユーザー管理/Cronジョブ/サービス管理 統合タブページ

### Changed
- **main.py**: セキュリティヘッダー・レート制限・ログインブルートフォース対策 middleware 追加
- **tests/conftest.py**: reset_rate_limits autouse fixture 追加（テスト間干渉防止）

### Tests
- テスト合計: 624 → 709 PASS（+85件）、102 → 39 SKIP（-63件）

---

## [0.5.0] - 2026-02-14

**v0.5 リリース** - フロントエンド刷新・Firewall/SSH/Packages/監査ログモジュール・E2Eテスト

### Added

#### フロントエンド刷新
- **frontend/dev/network.html**: ネットワーク情報ページ（タブ: インターフェース/接続/ルート/統計）
- **frontend/dev/servers.html**: サーバー状態一覧ページ（nginx/apache2/mysql/postgresql/redis）
- **frontend/dev/hardware.html**: ハードウェア情報ページ（タブ: メモリ/ディスク/センサー）
- **frontend/dev/audit.html**: 監査ログ一覧ページ（フィルタ/ページネーション/エクスポート）

#### Firewall モジュール（read-only）
- **wrappers/adminui-firewall.sh**: rules/policy/status サブコマンド
- **GET /api/firewall/rules, /policy, /status**
- **tests/integration/test_firewall_api.py**: 22件テスト

#### Package Manager モジュール（apt）
- **wrappers/adminui-packages.sh**: list/updates/security サブコマンド
- **GET /api/packages/installed, /updates, /security**
- **tests/integration/test_packages_api.py**: 20件テスト

#### SSH Server モジュール（read-only）
- **wrappers/adminui-ssh.sh**: status/config サブコマンド（危険設定自動検出）
- **GET /api/ssh/status, /config**
- **tests/integration/test_ssh_api.py**: 20件テスト

#### 監査ログ API + UI
- **GET /api/audit/logs**: ページネーション付き一覧（Operator: 自分のみ / Admin: 全員）
- **GET /api/audit/logs/export**: CSV/JSON エクスポート（Admin のみ）
- **tests/integration/test_audit_api.py**: 20件テスト

#### 承認ワークフロー拡張
- **wrappers/adminui-service-stop.sh**: サービス停止ラッパー
- **approval_service.py**: service_stop dispatch 追加

#### CI/CD 強化
- **.github/workflows/e2e.yml**: Playwright E2E テスト専用 workflow

### Changed
- **auth.py**: read:firewall / read:packages / read:ssh / read:audit / export:audit 権限追加

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
