# 🖥️ Linux管理運用システム v0.47.0

**Secure Linux Management WebUI with sudo allowlist control, audit logging, and approval workflow**

> このシステムは「Linuxを操作するツール」ではなく、「Linux運用を統制する仕組み」である。

---

## 📋 概要

Linux管理運用システムは、Linuxサーバの運用管理をWebブラウザから安全に行うためのシステムです。
Webminの便利さを踏襲しつつ、企業・組織での運用に必要な**セキュリティ統制**と**監査証跡**を最優先に設計されています。

### 🎯 プロジェクトの目的

- **root作業をWebUI経由で安全に制御**
- **sudo権限を最小化・可視化**
- **操作ログを完全に証跡化**
- **将来的なITSM・承認フロー連携を前提**

### ❌ Webminとの違い

| 項目 | Webmin | 本システム |
|------|--------|-----------|
| 権限制御 | 粗い | 細密なallowlist |
| 監査ログ | 弱い | 全操作証跡化 |
| 承認フロー | なし | 実装予定 |
| セキュリティ思想 | 機能優先 | **統制優先** |

---

## 🔒 セキュリティ原則（設計の核心）

### Allowlist First
定義されていない操作は**全拒否**。デフォルトは「禁止」。

### Deny by Default
明示的に許可されたもののみ実行可能。

### Shell禁止
`shell=True` の使用を全面禁止。コマンドは配列で渡し、シェル展開を防止。

### sudo最小化
直接的なsudoコマンド実行を禁止。**必ずラッパースクリプト経由**で実行。

### 監査証跡
全操作について「誰が・いつ・何を」を記録し、改ざん防止。

---

## 🚫 禁止操作（即時拒否）

以下の操作は設計上**完全に禁止**されています：

- ❌ 任意コマンドの実行
- ❌ bash / sh の起動
- ❌ /etc 配下の直接編集
- ❌ ユーザー・sudo権限の追加
- ❌ 特殊文字の使用: `; | & $( ) \` > < * ? { } [ ]`

---

## 🏗️ システムアーキテクチャ

```
[ Browser ]
   ↓ HTTPS
[ WebUI (HTML/JS) ]
   ↓ REST API
[ Backend (FastAPI) ]
   ↓ sudo (allowlist only)
[ Root Wrapper Scripts ]
   ↓ 入力検証・実行制御
[ Linux OS / systemctl / journalctl ]
```

### コンポーネント

| コンポーネント | 技術スタック | 役割 |
|--------------|------------|------|
| **Frontend** | HTML/CSS/JavaScript | ユーザーインターフェース |
| **Backend** | FastAPI (Python) | API提供・認証・権限管理 |
| **Wrappers** | Bash (配列引数のみ) | sudo実行の安全な仲介 |
| **Audit Log** | JSON形式 | 改ざん防止型ログ記録 |

---

## 📦 機能一覧（Webmin互換を目指した包括的管理）

**対象OS**: Ubuntu Linux（標準）

本システムは100個以上のモジュールを段階的に実装予定。Webminの便利さとセキュリティ統制を両立。

### 🏗️ Linux Management System カテゴリ

| モジュール | 内容 | 実装状況 |
|----------|------|---------|
| **System Configuration** | システム全体設定 | 📋 計画中 |
| **System Users** | ユーザー管理 | 📋 計画中 |
| **System Servers** | サービス管理 | ✅ v0.1実装済み |
| **System Actions Log** | 操作ログ・監査 | ✅ v0.1実装済み |
| **System Themes** | UI テーマ | 📋 計画中 |
| **System Modules** | モジュール管理 | 📋 計画中 |

### 💻 System カテゴリ（基幹機能）

| モジュール | 内容 | 実装状況 |
|----------|------|---------|
| **Bootup and Shutdown** | 起動・シャットダウン管理 | ✅ v0.7実装済み |
| **Disk and Network Filesystems** | ファイルシステム管理 | ✅ v0.6実装済み |
| **Disk Quotas** | ディスククォータ | ✅ v0.8実装済み |
| **Local Disk** | ディスク使用状況 | ✅ v0.1実装済み |
| **Users and Groups** | ユーザー・グループ管理 | ✅ v0.3実装済み |
| **Software Package Updates** | APT/パッケージ更新 | ✅ v0.5実装済み |
| **Cron Jobs** | Cron ジョブ管理 | ✅ v0.3実装済み |
| **System Logs** | ログ閲覧 | ✅ v0.1実装済み |
| **Running Processes** | プロセス監視 | ✅ v0.2実装済み |

### 🖥️ Servers カテゴリ（サービス管理）

| サービス | 内容 | 実装状況 |
|---------|------|---------|
| **Apache Webserver** | Apache 設定管理 | ✅ v0.9実装済み |
| **BIND DNS Server** | DNS サーバー管理 | ✅ v0.9実装済み |
| **Postfix / Sendmail** | メールサーバー管理 | ✅ v0.9実装済み |
| **MySQL / MariaDB** | MySQL データベース監視 | ✅ v0.8実装済み |
| **PostgreSQL** | PostgreSQL データベース監視 | ✅ v0.8実装済み |
| **SSH Server** | SSH サーバー設定 | ✅ v0.5実装済み |
| **ProFTPD / WU-FTP** | FTP サーバー管理 | ✅ v0.9実装済み |
| **Squid Proxy** | プロキシサーバー管理 | ✅ v0.9実装済み |
| **DHCP Server** | DHCP サーバー管理 | ✅ v0.9実装済み |

### 🌐 Networking カテゴリ（ネットワーク）

| モジュール | 内容 | 実装状況 |
|----------|------|---------|
| **Linux Firewall** | iptables/UFW管理 | ✅ v0.5実装済み |
| **Network Configuration** | ネットワーク設定 | ✅ v0.4実装済み |
| **Routing and Gateways** | ルーティング設定 | ✅ v0.4実装済み（ルート表示） |
| **Netstat** | ネットワーク統計 | ✅ v0.4実装済み（接続一覧） |
| **Bandwidth Monitoring** | 帯域幅監視 | ✅ v0.8実装済み |

### 🔧 Hardware カテゴリ（ハードウェア）

| モジュール | 内容 | 実装状況 |
|----------|------|---------|
| **Partitions on Local Disks** | パーティション管理 | ✅ v0.9実装済み |
| **System Time** | システム時刻設定 | ✅ v0.7実装済み |
| **SMART Drive Status** | ディスク健全性監視 | ✅ v0.4実装済み |
| **Sensors (lm-sensors)** | ハードウェアセンサー | ✅ v0.4実装済み |

### 🔗 Cluster / Tools カテゴリ（クラスタ・ツール）

| モジュール | 内容 | 実装状況 |
|----------|------|---------|
| **Cluster SSH** | クラスタ SSH 管理 | 📋 v0.5計画 |
| **Cluster Cron Jobs** | クラスタ Cron 管理 | 📋 v0.5計画 |
| **Cluster Users and Groups** | クラスタユーザー管理 | 📋 v0.5計画 |
| **Command Shell** | コマンドシェル | ❌ セキュリティ上禁止 |
| **File Manager** | ファイルマネージャー | ✅ v0.23実装済み |
| **Scheduled Commands** | スケジュールコマンド | 📋 v0.5計画 |
| **Custom Commands** | カスタムコマンド | ⚠️ 制限付き実装予定 |

### 現在実装済み（v0.47.0時点）

| 機能 | 実装状況 |
|------|---------|
| ✅ システム状態（CPU/メモリ/ディスク） | v0.1実装済み |
| ✅ サービス管理（allowlist） | v0.1実装済み |
| ✅ ログ閲覧（journalctl） | v0.1実装済み |
| ✅ 認証・認可（JWT/RBAC） | v0.1実装済み |
| ✅ 監査ログ（API + UI） | v0.5実装済み |
| ✅ Running Processes 管理 | v0.2実装済み |
| ✅ Users and Groups 管理 | v0.3実装済み |
| ✅ Cron Jobs 管理 | v0.3実装済み |
| ✅ 承認ワークフロー | v0.3実装済み |
| ✅ Network Configuration | v0.4実装済み |
| ✅ Hardware（SMART/Sensors） | v0.4実装済み |
| ✅ Linux Firewall（UFW） | v0.5実装済み |
| ✅ Software Package Updates | v0.5実装済み |
| ✅ SSH Server 設定 | v0.5実装済み |
| ✅ Disk and Network Filesystems | v0.6実装済み |
| ✅ Bootup and Shutdown | v0.7実装済み |
| ✅ System Time | v0.7実装済み |
| ✅ Disk Quotas | v0.8実装済み |
| ✅ MySQL/PostgreSQL 監視 | v0.8実装済み |
| ✅ Bandwidth Monitoring | v0.8実装済み |
| ✅ Apache Webserver 管理 | v0.9実装済み |
| ✅ Postfix/Sendmail 管理 | v0.9実装済み |
| ✅ Users/Groups UI強化 | v0.20.0実装済み |
| ✅ Cron UI強化（バリデーター） | v0.20.0実装済み |
| ✅ Apache設定強化（vhosts/SSL） | v0.21.0実装済み |
| ✅ ログ集約+検索 | v0.21.0実装済み |
| ✅ セキュリティ監査レポート | v0.22.0実装済み |
| ✅ Network Configuration UI強化（interfaces-detail/dns-config/active-connections） | v0.23.0実装済み |
| ✅ Package Manager UI（upgradeable/search/info/installed/security-updates） | v0.23.0実装済み |
| ✅ System Time/NTP UI強化（ntp-servers/sync-status/timezones） | v0.24.0実装済み |
| ✅ Bandwidth監視強化（history/monthly/alert-config） | v0.24.0実装済み |
| ✅ System Journal（全ログ/ユニット/ブート/カーネル/優先度別） | v0.25.0実装済み |
| ✅ Backup & Restore UI（一覧/状態/ディスク使用量/ログ） | v0.25.0実装済み |
| ✅ System Resource Alerts（閾値ルール/アクティブアラート/サマリ） | v0.26.0実装済み |
| ✅ User Session Management（アクティブ/履歴/失敗ログイン/統計） | v0.26.0実装済み |
| ✅ Log Search UI（全文検索/ファイル一覧/直近エラー集約） | v0.27.0実装済み |
| ✅ WebSocket自動再接続（ws-reconnect.js） | v0.45.0実装済み |
| ✅ Bootstrap Icons / Chart.js / SortableJS のCDN→vendor化 | v0.46.0実装済み |
| ✅ 全55ページサイドバー完全修正（dev/prod両対応） | v0.47.0実装済み |

---

## 🔧 最近の修正 (v0.45.0–v0.47.0)

| 修正内容 | バージョン |
|---------|----------|
| 全55ページサイドバー完全修正（46 prodページ含む） | v0.47.0 |
| API 500エラー修正（logsearch / security / routing） | v0.47.0 |
| テスト高速化（fixture session化、約7倍速・62秒で1275件実行） | v0.47.0 |
| WebSocket自動再接続ライブラリ（ws-reconnect.js）実装 | v0.45.0 |
| Bootstrap Icons / Chart.js / SortableJS をCDN→vendor化 | v0.46.0 |

### テスト状況

| 種別 | 件数 | 状態 |
|------|------|------|
| unit tests | 1275+ | ✅ 全合格（約62秒） |
| integration tests | 実装中 | 🔄 |
| security tests | 実装中 | 🔄 |
| e2e tests | 実装中 | 🔄 |

---

## 🚀 クイックスタート

### 前提条件

- Linux OS（Ubuntu 22.04 LTS 以降推奨）
- Python 3.11+
- sudo権限を持つユーザー

### インストール

```bash
# リポジトリのクローン
git clone https://github.com/Kensan196948G/Linux-Management-System.git
cd Linux-Management-System

# バックエンド依存関係のインストール
cd backend
pip install -r requirements.txt

# 開発サーバーの起動
uvicorn api.main:app --reload
```

### 初期セットアップ

詳細は [ENVIRONMENT.md](./ENVIRONMENT.md) を参照してください。

---

## 👥 ユーザーロール

| ロール | 権限 |
|--------|------|
| **Viewer** | 参照のみ |
| **Operator** | 限定的な操作（再起動など） |
| **Approver** | 危険操作の承認権限 |
| **Admin** | システム設定管理 |

---

## 📊 開発フェーズ（段階的モジュール実装）

| フェーズ | 実装モジュール | 状態 | 進捗 |
|---------|-------------|------|------|
| **v0.1** | **基本監視・操作**（現在） | ✅ **完了** | **80%** |
| | - システム状態（CPU/メモリ/ディスク） | ✅ 実装済み | |
| | - サービス再起動（allowlist） | ✅ 実装済み | |
| | - ログ閲覧（journalctl） | ✅ 実装済み | |
| | - 認証・認可（JWT/RBAC） | ✅ 実装済み | |
| | - 監査ログ | ✅ 実装済み | |
| **v0.2** | **System管理拡張** | ✅ **完了** | **100%** |
| | - Users and Groups 管理 | ✅ | v0.3実装済み |
| | - Cron Jobs 管理 | ✅ | v0.3実装済み |
| | - Running Processes 詳細 | ✅ | v0.2実装済み（179 test cases） |
| | - Network Configuration | ✅ | v0.4実装済み |
| | - SSH Server 設定 | ✅ | v0.5実装済み |
| **v0.3** | **Servers・Security** | ✅ **完了** | **100%** |
| | - MySQL/PostgreSQL 監視 | ✅ | v0.8実装済み |
| | - Linux Firewall（UFW） | ✅ | v0.5実装済み |
| | - Package Updates（APT） | ✅ | v0.5実装済み |
| | - 承認フロー実装 | ✅ | v0.3実装済み |
| | - SMART Drive Status | ✅ | v0.4実装済み |
| **v0.4** | **高度な管理** | 🔄 **一部完了** | **50%** |
| | - Apache Webserver 管理 | ✅ | v0.9実装済み |
| | - Postfix/Sendmail 管理 | ✅ | v0.9実装済み |
| | - File Manager（制限付き） | 📋 | |
| | - DNS/DHCP Server 管理 | 📋 | |
| **v0.5** | **クラスタ管理** | 📋 計画中 | 0% |
| | - Cluster SSH | 📋 | |
| | - Cluster Cron Jobs | 📋 | |
| | - Cluster Users | 📋 | |
| **v1.0** | **本番運用** | 📋 計画中 | 0% |
| | - 全モジュール統合 | 📋 | |
| | - パフォーマンス最適化 | 📋 | |
| | - セキュリティ監査 | 📋 | |

**注意**: Command Shell / 任意コマンド実行は、セキュリティ原則により**実装しない**

---

## 🛠️ 開発体制

### ClaudeCode 主導開発

本プロジェクトは **ClaudeCode** による自動開発を採用しています。

- **SubAgent 7体構成**（Planner / Architect / Backend / Frontend / Security / QA / CIManager）
- **並列セキュリティ検証**（全変更に対してSecurity SubAgentが並列で検証）
- **GitHub Actions 自動修復**（テスト失敗時の自動原因分析・修復）

詳細は [CLAUDE.md](./CLAUDE.md) を参照してください。

### 人間レビュー必須ポイント

以下の変更は**必ず人間による承認**が必要です：

- ✋ sudoers ファイルの変更
- ✋ 新規操作の追加
- ✋ 承認フローの変更
- ✋ root権限に関わる変更

---

## 🔐 セキュリティポリシー

セキュリティ脆弱性を発見した場合は、[SECURITY.md](./SECURITY.md) を参照して報告してください。

**Public Issue は使用しないでください。**

---

## 📚 ドキュメント

### プロジェクト概要・開発
- [README.md](./README.md) - プロジェクト概要（本ファイル）
- [CLAUDE.md](./CLAUDE.md) - ClaudeCode開発仕様・セキュリティ原則
- [ENVIRONMENT.md](./ENVIRONMENT.md) - 開発環境セットアップガイド
- [CONTRIBUTING.md](./CONTRIBUTING.md) - コントリビューションガイドライン
- [CHANGELOG.md](./CHANGELOG.md) - 変更履歴

### セキュリティ・設計
- [SECURITY.md](./SECURITY.md) - セキュリティポリシー
- [docs/要件定義書_詳細設計仕様書.md](./docs/要件定義書_詳細設計仕様書.md) - 詳細要件・設計仕様
- [docs/開発環境仕様書.md](./docs/開発環境仕様書.md) - 開発環境詳細

### API・技術仕様
- [docs/api-reference.md](./docs/api-reference.md) - REST API リファレンス
- [docs/openapi.json](./docs/openapi.json) - OpenAPI 仕様 (v3.1.0)
- `/api/docs` - Swagger UI（開発環境のみ）
- `/api/redoc` - ReDoc UI（開発環境のみ）

---

## 📄 ライセンス

本プロジェクトは [MIT License](./LICENSE) の下で公開されています。

---

## 🤝 コントリビューション

コントリビューションを歓迎します！ただし、以下の原則を遵守してください：

1. **セキュリティファースト** - 便利さより安全性を優先
2. **Allowlist思想** - デフォルト拒否を徹底
3. **監査証跡** - 全ての操作を記録
4. **テストカバレッジ** - 新機能には必ずテストを追加

詳細は [CONTRIBUTING.md](./CONTRIBUTING.md) を参照してください。

---

## 📞 お問い合わせ

- **Issues**: [GitHub Issues](https://github.com/Kensan196948G/Linux-Management-System/issues)
- **Security**: [SECURITY.md](./SECURITY.md) を参照

---

## 🙏 謝辞

本プロジェクトは Webmin の思想に触発されつつ、企業運用に必要なセキュリティ統制を実現することを目指しています。

---

**⚠️ 重要な注意事項**

本システムは Linux サーバの root 権限操作を扱います。
**本番環境への導入前に、必ず十分なテストと監査を実施してください。**

開発者・管理者は、本システムの設計思想である
**「統制優先・安全第一」** を常に念頭に置いてください。
