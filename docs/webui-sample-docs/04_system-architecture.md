# システムアーキテクチャ設計書

**文書番号**: WEBUI-ARC-001
**バージョン**: 1.0
**作成日**: 2026-02-25
**対象システム**: Linux管理 WebUI サンプルシステム

---

## 1. システム構成概要

### 1.1 全体アーキテクチャ

```
┌─────────────────────────────────────────────────────────┐
│                    管理者端末（ブラウザ）                    │
│              Chrome / Firefox / Edge                     │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTPS (TLS 1.3)
                       │ ポート 443
┌──────────────────────▼──────────────────────────────────┐
│                  リバースプロキシ層                          │
│              Nginx / Caddy                               │
│  - TLS終端  - 静的ファイル配信  - APIプロキシ               │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP (127.0.0.1:8000)
┌──────────────────────▼──────────────────────────────────┐
│                  バックエンド API 層                        │
│              FastAPI (Python 3.10+)                      │
│  - 認証・認可  - ビジネスロジック  - API エンドポイント         │
│  - 操作ログ記録  - セッション管理                           │
└──────┬───────────────┬───────────────┬──────────────────┘
       │               │               │
┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
│ 認証 DB      │ │ 操作ログ DB  │ │ 設定 DB     │
│ SQLite/PG    │ │ SQLite/PG    │ │ SQLite/PG   │
└─────────────┘ └─────────────┘ └─────────────┘
       │
       │ sudo（allowlist ラッパーのみ）
┌──────▼──────────────────────────────────────────────────┐
│               Root Wrapper スクリプト層                    │
│      /usr/local/sbin/adminui-*                           │
│  - 入力検証  - allowlist チェック  - コマンド実行           │
│  - 実行ログ記録  - タイムアウト制御                          │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                   Linux OS 層                            │
│      systemctl / journalctl / ps / cron / useradd       │
└─────────────────────────────────────────────────────────┘
```

### 1.2 デプロイ構成

```
/opt/linux-mgmt-webui/
├── frontend/           # 静的ファイル（HTML/JS/CSS）
│   ├── index.html
│   ├── assets/
│   └── dist/
├── backend/            # FastAPI アプリケーション
│   ├── main.py
│   ├── api/
│   ├── models/
│   ├── services/
│   └── utils/
├── wrappers/           # Root ラッパースクリプト
│   └── （sudoers経由でのみアクセス）
├── config/             # 設定ファイル
│   ├── settings.yaml
│   └── allowlist.yaml
├── logs/               # ログディレクトリ（追記専用）
│   ├── audit.log
│   └── app.log
└── data/               # データベース
    └── adminui.db
```

---

## 2. コンポーネント詳細設計

### 2.1 フロントエンド（SPA）

| 項目 | 内容 |
|------|------|
| フレームワーク | Vanilla JS または Vue.js 3 |
| ビルドツール | Vite |
| UIライブラリ | TailwindCSS |
| グラフ | Chart.js |
| HTTP クライアント | Fetch API |
| 状態管理 | Pinia（Vue使用時） |

**主要コンポーネント**:

```
frontend/src/
├── views/
│   ├── Dashboard.vue       # ダッシュボード
│   ├── Services.vue        # サービス管理
│   ├── Processes.vue       # プロセス一覧
│   ├── Logs.vue            # ログ閲覧
│   ├── Users.vue           # ユーザー管理
│   └── Audit.vue           # 監査ログ
├── components/
│   ├── ResourceGraph.vue   # リソースグラフ
│   ├── ServiceCard.vue     # サービスカード
│   ├── LogViewer.vue       # ログビューア
│   └── ApprovalModal.vue   # 承認ダイアログ
├── stores/
│   ├── auth.js             # 認証状態
│   └── notifications.js   # 通知状態
└── api/
    └── client.js           # API クライアント
```

### 2.2 バックエンド API（FastAPI）

| 項目 | 内容 |
|------|------|
| フレームワーク | FastAPI 0.100+ |
| Pythonバージョン | 3.10+ |
| 非同期処理 | asyncio / uvicorn |
| 認証 | JWT (python-jose) |
| ORM | SQLAlchemy 2.0 |
| データバリデーション | Pydantic v2 |
| テスト | pytest / httpx |

**モジュール構成**:

```
backend/
├── main.py                 # アプリケーションエントリ
├── api/
│   ├── v1/
│   │   ├── auth.py         # 認証エンドポイント
│   │   ├── status.py       # システム状態
│   │   ├── services.py     # サービス管理
│   │   ├── processes.py    # プロセス管理
│   │   ├── logs.py         # ログ管理
│   │   ├── users.py        # ユーザー管理
│   │   └── audit.py        # 監査ログ
│   └── deps.py             # 依存性注入
├── core/
│   ├── config.py           # 設定管理
│   ├── security.py         # セキュリティユーティリティ
│   └── logging.py          # ログ設定
├── models/
│   ├── user.py             # ユーザーモデル
│   ├── audit.py            # 監査ログモデル
│   └── approval.py         # 承認モデル
├── services/
│   ├── system_service.py   # システム情報取得
│   ├── service_mgr.py      # サービス管理
│   ├── user_service.py     # ユーザー管理
│   └── audit_service.py    # 監査ログ
└── wrappers/
    └── executor.py         # ラッパー実行管理
```

### 2.3 Root ラッパースクリプト

| 項目 | 内容 |
|------|------|
| 設置場所 | `/usr/local/sbin/adminui-*` |
| 言語 | Bash（シンプルな構成） |
| 実行権限 | root（sudo 経由） |
| 呼び出し方 | Python から subprocess（shell=False） |

**ラッパー一覧**:

```
/usr/local/sbin/
├── adminui-service-restart    # サービス再起動
├── adminui-service-start      # サービス開始
├── adminui-service-stop       # サービス停止
├── adminui-service-status     # サービス状態確認
├── adminui-log-read           # ログ読み取り
├── adminui-user-list          # ユーザー一覧
└── adminui-system-info        # システム情報取得
```

---

## 3. データフロー設計

### 3.1 通常操作フロー（参照系）

```
ブラウザ
  → [1] GET /api/v1/status  (JWT付き)
バックエンド
  → [2] JWTトークン検証
  → [3] ロール・権限確認
  → [4] subprocess（shell=False）でラッパー呼び出し
  → [5] ラッパーが入力検証 → コマンド実行
  → [6] 結果をJSON返却
  → [7] 操作ログ記録（成功/失敗問わず）
  → [8] レスポンスをブラウザへ
```

### 3.2 危険操作フロー（承認フロー経由）

```
Operator
  → [1] POST /api/v1/approvals  (操作申請)
  → [2] 承認者へ通知
Approver
  → [3] PUT /api/v1/approvals/{id}/approve
  → [4] 有効期限付きトークン生成
Operator
  → [5] POST /api/v1/services/{name}/stop  (承認トークン付き)
バックエンド
  → [6] 承認トークン検証（有効期限チェック）
  → [7] ラッパー呼び出し → 実行
  → [8] 承認・実行ログ記録
```

---

## 4. セキュリティアーキテクチャ

### 4.1 多層防御の設計

```
Layer 1: ネットワーク層
  - 社内ネットワークのみアクセス許可
  - HTTPS強制（HTTP→HTTPS リダイレクト）

Layer 2: 認証・認可層
  - JWT トークン検証
  - ロールベースアクセス制御（RBAC）
  - セッション管理・タイムアウト

Layer 3: アプリケーション層
  - 入力バリデーション（Pydantic）
  - SQLインジェクション対策（ORM使用）
  - XSS対策（出力エスケープ・CSP）

Layer 4: OS実行層
  - 専用サービスアカウント（非root）
  - sudo allowlist（ラッパーのみ）
  - コマンドインジェクション対策（shell=False）

Layer 5: 監査層
  - 全操作の記録
  - 改ざん防止ログ
  - 異常検知アラート
```

---

## 5. 技術スタック一覧

| カテゴリ | 技術 | バージョン |
|---------|------|----------|
| OS | Ubuntu / RHEL | 20.04 LTS / 8.x |
| Webサーバー | Nginx | 1.24+ |
| バックエンド | FastAPI | 0.104+ |
| 言語 | Python | 3.10+ |
| フロントエンド | Vue.js / Vite | 3.x / 5.x |
| CSSフレームワーク | TailwindCSS | 3.x |
| データベース | SQLite / PostgreSQL | 3.x / 15.x |
| ORM | SQLAlchemy | 2.0+ |
| 認証 | JWT (python-jose) | 3.3+ |
| プロセス管理 | systemd | - |
| コンテナ（開発用） | Docker | 24.x+ |

---

*本文書はLinux管理WebUIサンプルシステムのシステムアーキテクチャを定めるものである。*
