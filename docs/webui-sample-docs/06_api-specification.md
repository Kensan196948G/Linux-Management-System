# API仕様書

**文書番号**: WEBUI-API-001
**バージョン**: 1.0
**作成日**: 2026-02-25
**対象システム**: Linux管理 WebUI サンプルシステム

---

## 1. 基本仕様

| 項目 | 内容 |
|------|------|
| ベースURL | `https://{host}/api/v1` |
| プロトコル | HTTPS のみ |
| データ形式 | JSON (`Content-Type: application/json`) |
| 文字コード | UTF-8 |
| 認証方式 | JWT Bearer Token |
| APIバージョニング | URLパス（`/api/v1/`） |

---

## 2. 認証

### 2.1 ログイン

**`POST /api/v1/auth/login`**

リクエスト:
```json
{
  "username": "operator01",
  "password": "Password123!",
  "mfa_code": "123456"
}
```

レスポンス（200 OK）:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": 1,
    "username": "operator01",
    "role": "operator",
    "display_name": "運用担当 一郎"
  }
}
```

エラーレスポンス（401）:
```json
{
  "detail": "ユーザー名またはパスワードが正しくありません"
}
```

### 2.2 トークンリフレッシュ

**`POST /api/v1/auth/refresh`**

リクエスト:
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### 2.3 ログアウト

**`POST /api/v1/auth/logout`**

ヘッダー: `Authorization: Bearer {access_token}`

---

## 3. システム状態 API

### 3.1 システム概要取得

**`GET /api/v1/status`**

レスポンス（200 OK）:
```json
{
  "hostname": "linux-server-01",
  "os": "Ubuntu 22.04.3 LTS",
  "kernel": "5.15.0-89-generic",
  "uptime_seconds": 1296000,
  "uptime_human": "15日 0時間 0分",
  "timestamp": "2026-02-25T14:30:00+09:00"
}
```

### 3.2 リソース使用状況取得

**`GET /api/v1/status/resources`**

レスポンス（200 OK）:
```json
{
  "cpu": {
    "usage_percent": 42.5,
    "core_count": 4,
    "per_core": [38.2, 45.1, 40.8, 45.9],
    "load_average": {
      "1min": 1.23,
      "5min": 1.15,
      "15min": 1.08
    }
  },
  "memory": {
    "total_bytes": 8589934592,
    "used_bytes": 5872025600,
    "available_bytes": 2717908992,
    "usage_percent": 68.4,
    "swap_total_bytes": 2147483648,
    "swap_used_bytes": 104857600
  },
  "disk": [
    {
      "mount": "/",
      "device": "/dev/sda1",
      "total_bytes": 107374182400,
      "used_bytes": 59055800320,
      "free_bytes": 48318382080,
      "usage_percent": 55.0
    }
  ],
  "network": [
    {
      "interface": "eth0",
      "bytes_sent": 1234567890,
      "bytes_recv": 9876543210,
      "packets_sent": 1234567,
      "packets_recv": 9876543
    }
  ],
  "timestamp": "2026-02-25T14:30:00+09:00"
}
```

---

## 4. サービス管理 API

### 4.1 サービス一覧取得

**`GET /api/v1/services`**

クエリパラメータ:

| パラメータ | 型 | 必須 | 説明 |
|----------|-----|------|------|
| `status` | string | 任意 | フィルタ: `active`/`inactive`/`failed` |
| `search` | string | 任意 | サービス名の部分一致検索 |
| `limit` | integer | 任意 | 最大件数（デフォルト: 50） |
| `offset` | integer | 任意 | オフセット（デフォルト: 0） |

レスポンス（200 OK）:
```json
{
  "services": [
    {
      "name": "nginx",
      "description": "A high performance web server",
      "status": "active",
      "sub_status": "running",
      "enabled": true,
      "pid": 1234,
      "since": "2026-02-20T08:00:00+09:00"
    }
  ],
  "total": 42,
  "limit": 50,
  "offset": 0
}
```

### 4.2 サービス詳細取得

**`GET /api/v1/services/{service_name}`**

パスパラメータ: `service_name` - サービス名（英数字・ハイフン・アンダースコアのみ）

レスポンス（200 OK）:
```json
{
  "name": "nginx",
  "status": "active",
  "sub_status": "running",
  "enabled": true,
  "pid": 1234,
  "memory_bytes": 10485760,
  "cpu_percent": 0.1,
  "since": "2026-02-20T08:00:00+09:00",
  "recent_logs": [
    "Feb 25 14:30:00 nginx[1234]: ...",
    "Feb 25 14:25:00 nginx[1234]: ..."
  ]
}
```

### 4.3 サービス操作

**`POST /api/v1/services/{service_name}/action`**

リクエスト:
```json
{
  "action": "restart",
  "approval_token": null
}
```

`action` に指定可能な値: `restart`, `start`, `stop`

- `stop` 操作時は `approval_token` 必須

レスポンス（202 Accepted）:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "サービス再起動を実行中..."
}
```

### 4.4 操作結果取得

**`GET /api/v1/jobs/{job_id}`**

レスポンス（200 OK）:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "exit_code": 0,
  "stdout": "",
  "stderr": "",
  "started_at": "2026-02-25T14:35:00+09:00",
  "completed_at": "2026-02-25T14:35:03+09:00"
}
```

---

## 5. ログ管理 API

### 5.1 ジャーナルログ取得

**`GET /api/v1/logs/journal`**

クエリパラメータ:

| パラメータ | 型 | 必須 | 説明 |
|----------|-----|------|------|
| `unit` | string | 任意 | サービス単位フィルタ |
| `since` | datetime | 任意 | 開始日時（ISO 8601） |
| `until` | datetime | 任意 | 終了日時（ISO 8601） |
| `level` | string | 任意 | `debug`/`info`/`warning`/`error`/`critical` |
| `keyword` | string | 任意 | キーワード検索（最大256文字） |
| `limit` | integer | 任意 | 最大件数（デフォルト: 100、最大: 1000） |

レスポンス（200 OK）:
```json
{
  "logs": [
    {
      "timestamp": "2026-02-25T14:30:00+09:00",
      "unit": "nginx",
      "priority": "info",
      "message": "started A high performance web server"
    }
  ],
  "total_lines": 1523,
  "truncated": false
}
```

---

## 6. 監査ログ API

### 6.1 監査ログ一覧取得

**`GET /api/v1/audit`**

クエリパラメータ:

| パラメータ | 型 | 必須 | 説明 |
|----------|-----|------|------|
| `user` | string | 任意 | 実行ユーザーフィルタ |
| `action` | string | 任意 | 操作種別フィルタ |
| `since` | datetime | 任意 | 開始日時 |
| `until` | datetime | 任意 | 終了日時 |
| `limit` | integer | 任意 | デフォルト50 |

レスポンス（200 OK）:
```json
{
  "records": [
    {
      "id": 12345,
      "timestamp": "2026-02-25T14:35:00+09:00",
      "user": "operator01",
      "role": "operator",
      "ip_address": "192.168.1.100",
      "action": "service.restart",
      "target": "nginx",
      "parameters": {"service_name": "nginx"},
      "result": "success",
      "exit_code": 0,
      "duration_ms": 2534
    }
  ],
  "total": 8543
}
```

---

## 7. エラーレスポンス仕様

### 7.1 共通エラー形式

```json
{
  "detail": "エラーの説明",
  "error_code": "SERVICE_NOT_FOUND",
  "timestamp": "2026-02-25T14:30:00+09:00"
}
```

### 7.2 HTTPステータスコード一覧

| ステータス | 説明 |
|----------|------|
| 200 OK | 成功 |
| 201 Created | リソース作成成功 |
| 202 Accepted | 非同期処理受付 |
| 400 Bad Request | リクエスト不正（バリデーションエラー） |
| 401 Unauthorized | 認証失敗・トークン無効 |
| 403 Forbidden | 権限不足 |
| 404 Not Found | リソースが存在しない |
| 409 Conflict | 競合（同一操作の重複実行等） |
| 422 Unprocessable Entity | 入力値エラー |
| 429 Too Many Requests | レート制限超過 |
| 500 Internal Server Error | サーバーエラー |
| 503 Service Unavailable | ラッパー実行不可 |

---

## 8. レート制限

| エンドポイント種別 | 制限 |
|-----------------|------|
| 認証（ログイン） | 5 req/min |
| 参照系API | 60 req/min |
| 操作系API | 10 req/min |
| ログダウンロード | 5 req/min |

制限超過時は `Retry-After` ヘッダーに再試行可能時刻を返却。

---

*本文書はLinux管理WebUIサンプルシステムのAPI仕様を定めるものである。*
