# 📡 API Reference

**Linux Management System - RESTful API Documentation**

このドキュメントは、Linux Management System のバックエンド REST API の完全なリファレンスです。

---

## 📋 目次

1. [概要](#概要)
2. [認証](#認証)
3. [エラーハンドリング](#エラーハンドリング)
4. [API エンドポイント](#api-エンドポイント)
   - [Authentication](#authentication)
   - [System](#system)
   - [Services](#services)
   - [Logs](#logs)
   - [v0.3 Docs-Sync 追補](#v03-docs-sync-追補-2026-02-24)
5. [権限一覧](#権限一覧)
6. [監査ログ](#監査ログ)
7. [OpenAPI仕様](#openapi仕様)

---

## 概要

### ベースURL

| 環境 | ベースURL |
|-----|----------|
| **開発環境** | `http://localhost:5012/api` |
| **本番環境** | `https://your-domain.com/api` |

### API バージョン

- **現在のバージョン**: `v0.3.0-doc-sync`（2026-02-24 時点の docs 同期版）
- **OpenAPI バージョン**: `3.1.0`

### Content-Type

- **Request**: `application/json`
- **Response**: `application/json`

### 認証方式

- **JWT (JSON Web Token)** ベースの認証
- Bearer トークン形式

---

## 認証

### JWT トークンの取得

全てのAPI（`/auth/login` を除く）は、JWT トークンによる認証が必要です。

#### 認証ヘッダー形式

```http
Authorization: Bearer <access_token>
```

#### トークンの有効期限

- **デフォルト**: 30分
- **更新方法**: 再ログインが必要（v0.2でトークンリフレッシュ機能追加予定）

### 権限ベースのアクセス制御

各エンドポイントには、必要な権限が定義されています。

| ロール | 権限 |
|--------|------|
| **Viewer** | `read:status`, `read:logs` |
| **Operator** | Viewer + `execute:service_restart` |
| **Approver** | Operator + `approve:dangerous_operations` |
| **Admin** | 全ての権限 |

---

## エラーハンドリング

### HTTP ステータスコード

| コード | 意味 | 使用例 |
|-------|------|--------|
| **200** | OK | 成功 |
| **201** | Created | リソース作成成功 |
| **400** | Bad Request | 不正なリクエスト |
| **401** | Unauthorized | 認証失敗 |
| **403** | Forbidden | 権限不足 |
| **404** | Not Found | リソースが見つからない |
| **500** | Internal Server Error | サーバーエラー |

### エラーレスポンス形式

```json
{
  "detail": "エラーメッセージ",
  "status_code": 403
}
```

#### 例: 権限不足

```json
{
  "detail": "Insufficient permissions: execute:service_restart required",
  "status_code": 403
}
```

---

## v0.3 Docs-Sync 追補 (2026-02-24)

このセクションは、`docs/openapi.json`（`v0.3.0-doc-sync`）と以下設計書の差分を解消するための追補です。

- `docs/api/approval-api-spec.md`
- `docs/architecture/approval-workflow-design.md`
- `docs/architecture/cron-jobs-design.md`
- `docs/architecture/processes-module-design.md`
- `docs/architecture/users-groups-design.md`

### 追補の位置づけ

- 本ドキュメント内の後続セクション（Authentication/System/Services/Logs）は `v0.1` 相当の詳細例として有効です
- `Cron / Users&Groups / Approval / Processes(v1)` の契約は **この追補 + `docs/openapi.json`** を優先してください
- `docs/openapi.json` には権限情報を `x-required-permissions` / `x-required-permissions-anyOf` として付与しています

### 追加・更新された主要エンドポイント（v0.3）

| モジュール | メソッド | パス | 主な権限 |
|---|---|---|---|
| Processes | GET | `/api/v1/processes` | `read:processes` |
| Cron | GET/POST | `/api/cron` | `read:cron` / `write:cron` |
| Cron | DELETE/PATCH | `/api/cron/{job_id}` | `write:cron` |
| Users | GET/POST | `/api/users` | `read:users` / `write:users` |
| Users | GET/DELETE | `/api/users/{uid}` | `read:users` / `write:users` |
| Users | PUT | `/api/users/{uid}/password` | `write:users` |
| Groups | GET/POST | `/api/groups` | `read:users` / `write:users` |
| Groups | DELETE | `/api/groups/{gid}` | `write:users` |
| Groups | PUT | `/api/groups/{gid}/members` | `write:users` |
| Approval | POST | `/api/approval/request` | `request:approval` |
| Approval | GET | `/api/approval/pending` | `view:approval_pending` |
| Approval | GET | `/api/approval/my-requests` | `request:approval` |
| Approval | GET | `/api/approval/{request_id}` | `request:approval` or `view:approval_pending` |
| Approval | POST | `/api/approval/{request_id}/approve` | `execute:approval` |
| Approval | POST | `/api/approval/{request_id}/reject` | `execute:approval` |
| Approval | POST | `/api/approval/{request_id}/cancel` | `request:approval`（申請者本人） |
| Approval | POST | `/api/approval/{request_id}/execute` | `execute:approved_action` |
| Approval | GET | `/api/approval/history` | `view:approval_history` |
| Approval | GET | `/api/approval/history/export` | `export:approval_history` |
| Approval | GET | `/api/approval/policies` | `view:approval_policies` |
| Approval | GET | `/api/approval/stats` | `view:approval_stats` |

### フィールド名同期（UI 実装で使用している主キー）

#### Processes (`GET /api/v1/processes`)

- クエリ: `sort_by`, `filter_user`, `min_cpu`, `min_mem`, `limit`
- 主要レスポンス: `status`, `total_processes`, `returned_processes`, `sort_by`, `filters`, `processes`, `timestamp`
- `processes[]` 主要項目: `pid`, `user`, `cpu_percent`, `mem_percent`, `vsz`, `rss`, `tty`, `stat`, `start`, `time`, `command`

#### Cron (`/api/cron*`)

- 追加リクエスト: `schedule`, `command`, `arguments`, `comment`, `reason`
- 一覧レスポンス: `status`, `user`, `jobs`, `total_count`, `max_allowed`
- `jobs[]` 主要項目: `id`, `schedule`, `schedule_human`, `command`, `arguments`, `enabled`, `created_at`, `created_by`
- 書き込みレスポンス（申請系）: `status`, `request_id`, `message`（`approval_pending`）

#### Users / Groups (`/api/users*`, `/api/groups*`)

- User作成: `username`, `password`, `groups`, `home_dir`, `shell`, `reason`
- User一覧: `status`, `users`, `total_count`, `timestamp`
- Group一覧: `status`, `groups`, `total_count`, `timestamp`
- 削除/更新系は承認申請レスポンスを返す（`status`, `request_id`, `message`）

#### Approval (`/api/approval*`)

- 申請作成: `request_type`, `payload`, `reason`
- 一覧系: `status`, `requests`, `total`, `page`, `per_page`
- 詳細系: `status`, `request`
- アクション系: `status`, `message`, `request_id`, `status_value`（実装により追加項目あり）

### 承認ステータスの正規化（v0.3）

`docs/openapi.json` の `ApprovalStatus` enum は以下に統一:

- `pending`
- `approved`
- `rejected`
- `expired`
- `executed`
- `execution_failed`
- `cancelled`

### 承認ワークフロー実装上の注意（UI/BE共通）

- **自己承認禁止**: `approve` は申請者本人では実行不可（409/403の実装差異は許容、メッセージで明示）
- **状態遷移制約**: `approve/reject/cancel` は原則 `pending` のみ、`execute` は原則 `approved` のみ
- **権限不足**: `403 Forbidden`
- **存在しないID**: `404 Not Found`
- **入力不正**: `422 Validation Error`（Pydantic 系）

---

## API エンドポイント

### Authentication

#### POST `/api/auth/login`

ユーザーログイン（JWT トークン取得）

**権限**: なし（公開エンドポイント）

**Request Body**:
```json
{
  "email": "admin@example.com",
  "password": "your_password"
}
```

**Response** (200 OK):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user_id": "user_12345",
  "username": "admin",
  "role": "admin"
}
```

**Error Response** (401 Unauthorized):
```json
{
  "detail": "Incorrect email or password"
}
```

**監査ログ**:
- Operation: `login`
- Status: `success` / `failure`

**例 (curl)**:
```bash
curl -X POST http://localhost:5012/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123"}'
```

---

#### GET `/api/auth/me`

現在のユーザー情報を取得

**権限**: 認証済みユーザー（全ロール）

**Headers**:
```http
Authorization: Bearer <access_token>
```

**Response** (200 OK):
```json
{
  "user_id": "user_12345",
  "username": "admin",
  "email": "admin@example.com",
  "role": "admin",
  "permissions": [
    "read:status",
    "read:logs",
    "execute:service_restart",
    "approve:dangerous_operations",
    "manage:users"
  ]
}
```

**Error Response** (401 Unauthorized):
```json
{
  "detail": "Could not validate credentials"
}
```

**例 (curl)**:
```bash
TOKEN="your_access_token_here"

curl -X GET http://localhost:5012/api/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

---

#### POST `/api/auth/logout`

ログアウト

**権限**: 認証済みユーザー（全ロール）

**Headers**:
```http
Authorization: Bearer <access_token>
```

**Response** (200 OK):
```json
{
  "status": "success",
  "message": "Logged out successfully"
}
```

**Note**: JWTはステートレスなため、クライアント側でトークンを削除する必要があります。

**監査ログ**:
- Operation: `logout`
- Status: `success`

**例 (curl)**:
```bash
TOKEN="your_access_token_here"

curl -X POST http://localhost:5012/api/auth/logout \
  -H "Authorization: Bearer $TOKEN"
```

---

### System

#### GET `/api/system/status`

システム状態を取得（CPU、メモリ、ディスク、稼働時間）

**権限**: `read:status`（Viewer以上）

**Headers**:
```http
Authorization: Bearer <access_token>
```

**Response** (200 OK):
```json
{
  "status": "success",
  "uptime": "5 days, 3:24:15",
  "cpu": {
    "usage_percent": 23.5,
    "cores": 4
  },
  "memory": {
    "total_mb": 16384,
    "used_mb": 8192,
    "free_mb": 8192,
    "usage_percent": 50.0
  },
  "disk": {
    "total_gb": 500,
    "used_gb": 250,
    "free_gb": 250,
    "usage_percent": 50.0
  },
  "timestamp": "2026-02-06T12:34:56Z"
}
```

**Error Response** (403 Forbidden):
```json
{
  "detail": "Insufficient permissions: read:status required"
}
```

**監査ログ**:
- Operation: `system_status_view`
- Status: `success` / `failure`

**例 (curl)**:
```bash
TOKEN="your_access_token_here"

curl -X GET http://localhost:5012/api/system/status \
  -H "Authorization: Bearer $TOKEN"
```

---

### Services

#### POST `/api/services/restart`

サービスを再起動（allowlist ベース）

**権限**: `execute:service_restart`（Operator以上）

**Headers**:
```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request Body**:
```json
{
  "service_name": "nginx"
}
```

**Validation**:
- `service_name`: 必須、1-64文字、パターン: `^[a-zA-Z0-9_-]+$`
- Allowlist: `nginx`, `postgresql`, `redis` のみ許可（v0.1.0）

**Response** (200 OK):
```json
{
  "status": "success",
  "service": "nginx",
  "before": "active (running)",
  "after": "active (running)"
}
```

**Error Response** (403 Forbidden - Allowlist外):
```json
{
  "detail": "Service not in allowlist: unknown-service"
}
```

**Error Response** (400 Bad Request - 不正な入力):
```json
{
  "detail": [
    {
      "loc": ["body", "service_name"],
      "msg": "string does not match regex \"^[a-zA-Z0-9_-]+$\"",
      "type": "value_error.str.regex"
    }
  ]
}
```

**監査ログ**:
- Operation: `service_restart`
- Status: `attempt` → `success` / `denied` / `failure`

**例 (curl)**:
```bash
TOKEN="your_access_token_here"

curl -X POST http://localhost:5012/api/services/restart \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"service_name":"nginx"}'
```

---

### Logs

#### GET `/api/logs/{service_name}`

サービスのログを取得（journalctl経由）

**権限**: `read:logs`（Viewer以上）

**Headers**:
```http
Authorization: Bearer <access_token>
```

**Path Parameters**:
- `service_name` (string, required): サービス名（1-64文字、パターン: `^[a-zA-Z0-9_-]+$`）

**Query Parameters**:
- `lines` (integer, optional): 取得行数（1-1000、デフォルト: 100）

**Response** (200 OK):
```json
{
  "status": "success",
  "service": "nginx",
  "lines_requested": 100,
  "lines_returned": 50,
  "logs": [
    "Feb 06 12:00:00 server nginx[1234]: Server started",
    "Feb 06 12:00:01 server nginx[1234]: Listening on port 80",
    "..."
  ],
  "timestamp": "2026-02-06T12:34:56Z"
}
```

**Error Response** (403 Forbidden):
```json
{
  "detail": "Log view denied"
}
```

**監査ログ**:
- Operation: `log_view`
- Status: `attempt` → `success` / `denied` / `failure`

**例 (curl)**:
```bash
TOKEN="your_access_token_here"

# 最新100行を取得
curl -X GET "http://localhost:5012/api/logs/nginx?lines=100" \
  -H "Authorization: Bearer $TOKEN"

# 最新500行を取得
curl -X GET "http://localhost:5012/api/logs/nginx?lines=500" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 権限一覧

### 権限マトリクス

| 権限 | Viewer | Operator | Approver | Admin |
|------|--------|----------|----------|-------|
| `read:status` | ✅ | ✅ | ✅ | ✅ |
| `read:logs` | ✅ | ✅ | ✅ | ✅ |
| `execute:service_restart` | ❌ | ✅ | ✅ | ✅ |
| `approve:dangerous_operations` | ❌ | ❌ | ✅ | ✅ |
| `manage:users` | ❌ | ❌ | ❌ | ✅ |

`v0.3 Docs-Sync` で追加された主な権限（詳細は `## v0.3 Docs-Sync 追補` と `docs/openapi.json` の `x-required-permissions*` を参照）:

- `read:processes`
- `read:cron` / `write:cron` / `approve:cron`（設計書上）
- `read:users` / `write:users` / `approve:users`（設計書上）
- `request:approval`
- `view:approval_pending`
- `execute:approval`
- `execute:approved_action`
- `view:approval_history`
- `export:approval_history`
- `view:approval_policies`
- `view:approval_stats`

### 権限の説明

| 権限 | 説明 |
|------|------|
| `read:status` | システム状態の閲覧 |
| `read:logs` | ログの閲覧 |
| `execute:service_restart` | サービスの再起動 |
| `approve:dangerous_operations` | 危険操作の承認（v0.3実装予定） |
| `manage:users` | ユーザー管理（v0.2実装予定） |

---

## 監査ログ

全てのAPI操作は、監査ログに記録されます。

### ログ形式

```json
{
  "timestamp": "2026-02-06T12:34:56.789123Z",
  "operation": "service_restart",
  "user_id": "user_12345",
  "username": "admin",
  "target": "nginx",
  "status": "success",
  "details": {
    "before": "active (running)",
    "after": "active (running)"
  }
}
```

### 記録される操作

| Operation | 説明 |
|-----------|------|
| `login` | ログイン試行 |
| `logout` | ログアウト |
| `system_status_view` | システム状態閲覧 |
| `service_restart` | サービス再起動 |
| `log_view` | ログ閲覧 |

### ステータス

| Status | 説明 |
|--------|------|
| `attempt` | 操作開始 |
| `success` | 成功 |
| `denied` | 拒否（権限不足、allowlist外） |
| `failure` | 失敗（エラー発生） |

---

## OpenAPI仕様

`docs/openapi.json` は 2026-02-24 に `v0.3.0-doc-sync` として更新され、`Processes(v1) / Cron / Users&Groups / Approval` の設計書ベース契約を含みます。

追加された OpenAPI 拡張:

- `x-required-permissions`
- `x-required-permissions-anyOf`

docs 同期運用ルール（v0.3 以降）:

1. 実装側 OpenAPI を出力（runtime）
2. `docs/scripts/compare-openapi-docs-vs-runtime.mjs --runtime <runtime-openapi.json>` を実行
3. 差分がある場合は `docs/openapi.json` と `docs/api-reference.md` を同時更新

### OpenAPI JSON のダウンロード

開発サーバーが起動している場合、以下のエンドポイントから OpenAPI 仕様をダウンロードできます。

```bash
# OpenAPI JSON の取得
curl http://localhost:5012/openapi.json -o docs/openapi.json

# ブラウザで Swagger UI を開く
xdg-open http://localhost:5012/api/docs

# ReDoc UI を開く
xdg-open http://localhost:5012/api/redoc
```

### Interactive API Documentation

開発環境では、以下のインタラクティブなAPIドキュメントが利用可能です。

| URL | 説明 |
|-----|------|
| `/api/docs` | Swagger UI（OpenAPIベース） |
| `/api/redoc` | ReDoc UI（OpenAPIベース） |
| `/openapi.json` | OpenAPI 仕様（JSON形式） |

**Note**: 本番環境では、セキュリティ上の理由から `/api/docs` と `/api/redoc` は無効化されます。`docs/openapi.json` は docs 同期版（設計書ベース）を含むため、実装との差分確認時は `backend` 実装の自動生成OpenAPIと比較してください。

---

## 使用例

### Python (httpx)

```python
import httpx

BASE_URL = "http://localhost:5012/api"

# ログイン
response = httpx.post(
    f"{BASE_URL}/auth/login",
    json={"email": "admin@example.com", "password": "admin123"}
)
token = response.json()["access_token"]

# ヘッダーに認証トークンを設定
headers = {"Authorization": f"Bearer {token}"}

# システム状態を取得
response = httpx.get(f"{BASE_URL}/system/status", headers=headers)
print(response.json())

# サービスを再起動
response = httpx.post(
    f"{BASE_URL}/services/restart",
    json={"service_name": "nginx"},
    headers=headers
)
print(response.json())

# ログを取得
response = httpx.get(f"{BASE_URL}/logs/nginx?lines=50", headers=headers)
print(response.json())
```

### JavaScript (fetch)

```javascript
const BASE_URL = "http://localhost:5012/api";

// ログイン
async function login(email, password) {
  const response = await fetch(`${BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  const data = await response.json();
  return data.access_token;
}

// システム状態を取得
async function getSystemStatus(token) {
  const response = await fetch(`${BASE_URL}/system/status`, {
    headers: { "Authorization": `Bearer ${token}` }
  });
  return await response.json();
}

// 使用例
(async () => {
  const token = await login("admin@example.com", "admin123");
  const status = await getSystemStatus(token);
  console.log(status);
})();
```

### Bash (curl)

```bash
#!/bin/bash

BASE_URL="http://localhost:5012/api"

# ログイン
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123"}')

# トークンを抽出
TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token')

# システム状態を取得
curl -s -X GET "$BASE_URL/system/status" \
  -H "Authorization: Bearer $TOKEN" | jq .

# サービスを再起動
curl -s -X POST "$BASE_URL/services/restart" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"service_name":"nginx"}' | jq .

# ログを取得
curl -s -X GET "$BASE_URL/logs/nginx?lines=100" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

---

## セキュリティ考慮事項

### HTTPS の使用

本番環境では、**必ず HTTPS を使用**してください。

```nginx
# Nginx リバースプロキシ例
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location /api {
        proxy_pass http://localhost:5012;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### トークンの保管

- ❌ localStorage への保存（XSSリスク）
- ✅ httpOnly Cookie への保存（推奨、v0.2で実装予定）
- ✅ sessionStorage への保存（セッション終了時に削除）

### レート制限

v0.3 で実装予定:
- `/api/auth/login`: 5回/分
- その他のエンドポイント: 100回/分

---

## バージョン履歴

| バージョン | リリース日 | 変更内容 |
|----------|----------|---------|
| **0.1.0** | 2026-02-06 | 初回リリース（認証、システム状態、サービス再起動、ログ閲覧） |
| **0.2.0** | 未定 | ユーザー管理、Cronジョブ管理 |
| **0.3.0** | 未定 | 承認フロー、Cron/Users&Groups 強化、Processes v1 |
| **0.3.0-doc-sync** | 2026-02-24 | `docs/openapi.json` / `api-reference.md` を設計書ベースで同期（OpenAPI拡張権限注記を追加） |

---

## 関連ドキュメント

- [README.md](../README.md) - プロジェクト概要
- [ENVIRONMENT.md](../ENVIRONMENT.md) - 開発環境セットアップ
- [CLAUDE.md](../CLAUDE.md) - セキュリティ原則
- [SECURITY.md](../SECURITY.md) - セキュリティポリシー

---

**Note**: このAPIドキュメントには v0.1 の詳細例と v0.3 docs-sync 追補が混在します。実装確認時は `docs/openapi.json`（docs同期版）と実コード生成OpenAPIの両方を参照してください。
