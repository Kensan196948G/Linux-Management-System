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

- **現在のバージョン**: `v0.1.0`
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

**Note**: 本番環境では、セキュリティ上の理由から `/api/docs` と `/api/redoc` は無効化されます。

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
| **0.3.0** | 未定 | 承認フロー、ファイアウォール管理 |

---

## 関連ドキュメント

- [README.md](../README.md) - プロジェクト概要
- [ENVIRONMENT.md](../ENVIRONMENT.md) - 開発環境セットアップ
- [CLAUDE.md](../CLAUDE.md) - セキュリティ原則
- [SECURITY.md](../SECURITY.md) - セキュリティポリシー

---

**Note**: このAPIドキュメントは、コード変更に伴い自動的に更新されます。最新情報は `/api/docs` を参照してください。
