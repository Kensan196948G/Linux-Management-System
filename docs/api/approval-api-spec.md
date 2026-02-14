# 承認ワークフロー API 仕様書

**バージョン**: v0.3
**作成日**: 2026-02-14
**形式**: OpenAPI 3.0 準拠

---

## 概要

承認ワークフロー基盤の REST API 仕様。全エンドポイントは JWT Bearer Token 認証が必須。

### ベースURL

```
{scheme}://{host}:{port}/api/approval
```

### 共通ヘッダー

```
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json
```

### 共通エラーレスポンス

```json
{
  "status": "error",
  "message": "エラーメッセージ",
  "detail": "詳細情報（開発環境のみ）"
}
```

| HTTP Status | 説明 |
|-------------|------|
| 400 | リクエスト不正（バリデーションエラー） |
| 401 | 認証失敗（トークン無効/期限切れ） |
| 403 | 権限不足 |
| 404 | リソース未検出 |
| 409 | 状態競合（既に承認済み等） |
| 422 | バリデーションエラー（Pydantic） |
| 429 | レート制限超過 |
| 500 | 内部サーバーエラー |

---

## 1. POST /api/approval/request

### 概要

承認リクエストを新規作成する。

### 認可

- **必要ロール**: Operator, Approver, Admin
- **必要権限**: `request:approval`

### リクエスト

```json
{
  "request_type": "user_add",
  "payload": {
    "username": "newuser",
    "group": "developers",
    "home": "/home/newuser",
    "shell": "/bin/bash"
  },
  "reason": "新規プロジェクトメンバーのアカウント作成。プロジェクト: XYZ"
}
```

#### パラメータ詳細

| フィールド | 型 | 必須 | 制約 | 説明 |
|-----------|------|------|------|------|
| request_type | string | YES | approval_policies に定義済みの値 | 操作種別 |
| payload | object | YES | 各値に特殊文字禁止 | 操作パラメータ |
| reason | string | YES | 1-1000文字 | 申請理由 |

#### request_type の許可値（v0.3）

| 値 | 説明 |
|----|------|
| user_add | ユーザーアカウント追加 |
| user_delete | ユーザーアカウント削除 |
| user_modify | ユーザーアカウント変更 |
| group_add | グループ追加 |
| group_delete | グループ削除 |
| cron_add | Cronジョブ追加 |
| cron_delete | Cronジョブ削除 |
| cron_modify | Cronジョブ変更 |
| service_stop | サービス停止 |
| firewall_modify | ファイアウォール変更 |

### レスポンス

#### 201 Created - 成功

```json
{
  "status": "success",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "request_type": "user_add",
  "status_value": "pending",
  "created_at": "2026-02-14T15:00:00Z",
  "expires_at": "2026-02-15T15:00:00Z",
  "timeout_hours": 24,
  "risk_level": "HIGH",
  "message": "承認リクエストを作成しました。Approver/Admin の承認をお待ちください。"
}
```

#### 400 Bad Request - バリデーションエラー

```json
{
  "status": "error",
  "message": "Invalid request_type: unknown_operation",
  "detail": "request_type must be one of: user_add, user_delete, ..."
}
```

#### 400 Bad Request - 特殊文字検出

```json
{
  "status": "error",
  "message": "Security violation: Forbidden character ';' detected in payload field 'username'",
  "detail": "Input must not contain special characters"
}
```

#### 429 Too Many Requests - レート制限

```json
{
  "status": "error",
  "message": "Rate limit exceeded: maximum 10 requests per hour",
  "retry_after": 3600
}
```

---

## 2. GET /api/approval/pending

### 概要

承認待ちリクエストの一覧を取得する（Approver/Admin 向け）。

### 認可

- **必要ロール**: Approver, Admin
- **必要権限**: `view:approval_pending`

### クエリパラメータ

| パラメータ | 型 | 必須 | デフォルト | 説明 |
|-----------|------|------|-----------|------|
| request_type | string | NO | - | 操作種別でフィルタ |
| requester_id | string | NO | - | 申請者IDでフィルタ |
| sort_by | string | NO | created_at | ソートキー（created_at, expires_at, request_type） |
| sort_order | string | NO | asc | ソート順（asc, desc） |
| page | int | NO | 1 | ページ番号 |
| per_page | int | NO | 20 | 1ページあたり件数（最大100） |

### レスポンス

#### 200 OK

```json
{
  "status": "success",
  "total": 5,
  "page": 1,
  "per_page": 20,
  "requests": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "request_type": "user_add",
      "request_type_description": "ユーザーアカウント追加",
      "risk_level": "HIGH",
      "requester_id": "user_002",
      "requester_name": "operator",
      "reason": "新規プロジェクトメンバーのアカウント作成",
      "created_at": "2026-02-14T15:00:00Z",
      "expires_at": "2026-02-15T15:00:00Z",
      "remaining_hours": 23.5,
      "payload_summary": "username=newuser, group=developers"
    },
    {
      "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "request_type": "cron_add",
      "request_type_description": "Cronジョブ追加",
      "risk_level": "HIGH",
      "requester_id": "user_002",
      "requester_name": "operator",
      "reason": "バッチ処理の追加",
      "created_at": "2026-02-14T14:00:00Z",
      "expires_at": "2026-02-15T14:00:00Z",
      "remaining_hours": 22.5,
      "payload_summary": "schedule=0 2 * * *, command=adminui-backup"
    }
  ]
}
```

---

## 3. GET /api/approval/my-requests

### 概要

現在のユーザーが作成した承認リクエストの一覧を取得する。

### 認可

- **必要ロール**: Operator, Approver, Admin
- **必要権限**: `request:approval`

### クエリパラメータ

| パラメータ | 型 | 必須 | デフォルト | 説明 |
|-----------|------|------|-----------|------|
| status | string | NO | - | ステータスでフィルタ（pending, approved, rejected, expired, executed, cancelled） |
| request_type | string | NO | - | 操作種別でフィルタ |
| page | int | NO | 1 | ページ番号 |
| per_page | int | NO | 20 | 1ページあたり件数（最大100） |

### レスポンス

#### 200 OK

```json
{
  "status": "success",
  "total": 10,
  "page": 1,
  "per_page": 20,
  "requests": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "request_type": "user_add",
      "request_type_description": "ユーザーアカウント追加",
      "risk_level": "HIGH",
      "status": "pending",
      "reason": "新規プロジェクトメンバーのアカウント作成",
      "created_at": "2026-02-14T15:00:00Z",
      "expires_at": "2026-02-15T15:00:00Z",
      "approved_by_name": null,
      "approved_at": null,
      "rejection_reason": null
    }
  ]
}
```

---

## 4. GET /api/approval/{request_id}

### 概要

承認リクエストの詳細を取得する。

### 認可

- **申請者本人**: Operator, Approver, Admin
- **他者の申請**: Approver, Admin のみ

### パスパラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| request_id | string (UUID) | リクエストID |

### レスポンス

#### 200 OK

```json
{
  "status": "success",
  "request": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "request_type": "user_add",
    "request_type_description": "ユーザーアカウント追加",
    "risk_level": "HIGH",
    "requester_id": "user_002",
    "requester_name": "operator",
    "request_payload": {
      "username": "newuser",
      "group": "developers",
      "home": "/home/newuser",
      "shell": "/bin/bash"
    },
    "reason": "新規プロジェクトメンバーのアカウント作成。プロジェクト: XYZ",
    "status": "pending",
    "created_at": "2026-02-14T15:00:00Z",
    "expires_at": "2026-02-15T15:00:00Z",
    "approved_by": null,
    "approved_by_name": null,
    "approved_at": null,
    "rejection_reason": null,
    "execution_result": null,
    "executed_at": null,
    "history": [
      {
        "action": "created",
        "actor_id": "user_002",
        "actor_name": "operator",
        "actor_role": "Operator",
        "timestamp": "2026-02-14T15:00:00Z",
        "details": null
      }
    ]
  }
}
```

#### 404 Not Found

```json
{
  "status": "error",
  "message": "Approval request not found: a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

---

## 5. POST /api/approval/{request_id}/approve

### 概要

承認リクエストを承認する。自己承認は禁止。

### 認可

- **必要ロール**: Approver, Admin
- **必要権限**: `execute:approval`
- **制約**: `requester_id != current_user.user_id`（自己承認禁止）

### パスパラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| request_id | string (UUID) | リクエストID |

### リクエスト

```json
{
  "comment": "確認しました。承認します。"
}
```

| フィールド | 型 | 必須 | 制約 | 説明 |
|-----------|------|------|------|------|
| comment | string | NO | 0-500文字 | 承認コメント |

### レスポンス

#### 200 OK - 承認成功（auto_execute = false）

```json
{
  "status": "success",
  "message": "承認しました。",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "approved_by": "user_003",
  "approved_by_name": "admin",
  "approved_at": "2026-02-14T16:00:00Z",
  "auto_executed": false
}
```

#### 200 OK - 承認成功（auto_execute = true）

```json
{
  "status": "success",
  "message": "承認し、操作を実行しました。",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "approved_by": "user_003",
  "approved_by_name": "admin",
  "approved_at": "2026-02-14T16:00:00Z",
  "auto_executed": true,
  "execution_result": {
    "status": "success",
    "output": "User 'newuser' created successfully",
    "executed_at": "2026-02-14T16:00:01Z"
  }
}
```

#### 403 Forbidden - 自己承認

```json
{
  "status": "error",
  "message": "Self-approval is prohibited. A different Approver/Admin must approve this request."
}
```

#### 409 Conflict - 既に承認済み/拒否済み/期限切れ

```json
{
  "status": "error",
  "message": "Cannot approve: request status is 'expired'. Only 'pending' requests can be approved."
}
```

---

## 6. POST /api/approval/{request_id}/reject

### 概要

承認リクエストを拒否する。

### 認可

- **必要ロール**: Approver, Admin
- **必要権限**: `execute:approval`

### パスパラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| request_id | string (UUID) | リクエストID |

### リクエスト

```json
{
  "reason": "セキュリティポリシーに適合しないため拒否します。ユーザー名の命名規則を確認してください。"
}
```

| フィールド | 型 | 必須 | 制約 | 説明 |
|-----------|------|------|------|------|
| reason | string | YES | 1-1000文字 | 拒否理由（必須） |

### レスポンス

#### 200 OK

```json
{
  "status": "success",
  "message": "リクエストを拒否しました。",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "rejected_by": "user_003",
  "rejected_by_name": "admin",
  "rejected_at": "2026-02-14T16:00:00Z",
  "rejection_reason": "セキュリティポリシーに適合しないため拒否します。"
}
```

#### 409 Conflict - pending 以外のステータス

```json
{
  "status": "error",
  "message": "Cannot reject: request status is 'approved'. Only 'pending' requests can be rejected."
}
```

---

## 7. POST /api/approval/{request_id}/cancel

### 概要

申請者が自分の承認リクエストをキャンセルする。

### 認可

- **必要条件**: `current_user.user_id == request.requester_id`
- **必要権限**: `request:approval`

### パスパラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| request_id | string (UUID) | リクエストID |

### リクエスト

```json
{
  "reason": "申請内容に誤りがあったためキャンセルします。"
}
```

| フィールド | 型 | 必須 | 制約 | 説明 |
|-----------|------|------|------|------|
| reason | string | NO | 0-500文字 | キャンセル理由 |

### レスポンス

#### 200 OK

```json
{
  "status": "success",
  "message": "リクエストをキャンセルしました。",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "cancelled_at": "2026-02-14T15:30:00Z"
}
```

#### 403 Forbidden - 他者のリクエスト

```json
{
  "status": "error",
  "message": "Only the requester can cancel this request."
}
```

#### 409 Conflict - pending 以外

```json
{
  "status": "error",
  "message": "Cannot cancel: request status is 'approved'. Only 'pending' requests can be cancelled."
}
```

---

## 8. POST /api/approval/{request_id}/execute

### 概要

承認済みリクエストの操作を手動実行する（auto_execute = false の場合に使用）。

### 認可

- **必要ロール**: Admin
- **必要権限**: `execute:approved_action`

### パスパラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| request_id | string (UUID) | リクエストID |

### レスポンス

#### 200 OK - 実行成功

```json
{
  "status": "success",
  "message": "操作を実行しました。",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "execution_result": {
    "status": "success",
    "output": "User 'newuser' created successfully",
    "executed_at": "2026-02-14T17:00:00Z",
    "executed_by": "user_003"
  }
}
```

#### 200 OK - 実行失敗

```json
{
  "status": "success",
  "message": "操作の実行に失敗しました。",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "execution_result": {
    "status": "failure",
    "error": "useradd: user 'newuser' already exists",
    "executed_at": "2026-02-14T17:00:00Z",
    "executed_by": "user_003"
  }
}
```

#### 409 Conflict - 承認済み以外のステータス

```json
{
  "status": "error",
  "message": "Cannot execute: request status is 'pending'. Only 'approved' requests can be executed."
}
```

---

## 9. GET /api/approval/history

### 概要

承認履歴を取得する（監査証跡）。

### 認可

- **必要ロール**: Admin
- **必要権限**: `view:approval_history`

### クエリパラメータ

| パラメータ | 型 | 必須 | デフォルト | 説明 |
|-----------|------|------|-----------|------|
| start_date | string (ISO 8601) | NO | 30日前 | 開始日時 |
| end_date | string (ISO 8601) | NO | 現在 | 終了日時 |
| request_type | string | NO | - | 操作種別フィルタ |
| action | string | NO | - | アクション種別フィルタ |
| actor_id | string | NO | - | 実行者IDフィルタ |
| page | int | NO | 1 | ページ番号 |
| per_page | int | NO | 50 | 1ページあたり件数（最大200） |

### レスポンス

#### 200 OK

```json
{
  "status": "success",
  "total": 150,
  "page": 1,
  "per_page": 50,
  "history": [
    {
      "id": 1,
      "approval_request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "request_type": "user_add",
      "action": "created",
      "actor_id": "user_002",
      "actor_name": "operator",
      "actor_role": "Operator",
      "timestamp": "2026-02-14T15:00:00Z",
      "previous_status": null,
      "new_status": "pending",
      "details": null,
      "signature_valid": true
    },
    {
      "id": 2,
      "approval_request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "request_type": "user_add",
      "action": "approved",
      "actor_id": "user_003",
      "actor_name": "admin",
      "actor_role": "Admin",
      "timestamp": "2026-02-14T16:00:00Z",
      "previous_status": "pending",
      "new_status": "approved",
      "details": {
        "comment": "確認しました。承認します。"
      },
      "signature_valid": true
    }
  ]
}
```

---

## 10. GET /api/approval/history/export

### 概要

承認履歴を CSV または JSON 形式でエクスポートする。

### 認可

- **必要ロール**: Admin
- **必要権限**: `export:approval_history`

### クエリパラメータ

| パラメータ | 型 | 必須 | デフォルト | 説明 |
|-----------|------|------|-----------|------|
| format | string | NO | json | エクスポート形式（json, csv） |
| start_date | string (ISO 8601) | NO | 30日前 | 開始日時 |
| end_date | string (ISO 8601) | NO | 現在 | 終了日時 |
| request_type | string | NO | - | 操作種別フィルタ |

### レスポンス

#### 200 OK (format=json)

```
Content-Type: application/json
Content-Disposition: attachment; filename="approval_history_20260214.json"
```

```json
{
  "export_metadata": {
    "exported_at": "2026-02-14T17:00:00Z",
    "exported_by": "user_003",
    "total_records": 150,
    "filter": {
      "start_date": "2026-01-15T00:00:00Z",
      "end_date": "2026-02-14T23:59:59Z"
    }
  },
  "records": [...]
}
```

#### 200 OK (format=csv)

```
Content-Type: text/csv
Content-Disposition: attachment; filename="approval_history_20260214.csv"
```

```csv
id,approval_request_id,request_type,action,actor_id,actor_name,actor_role,timestamp,previous_status,new_status,signature_valid
1,a1b2c3d4-...,user_add,created,user_002,operator,Operator,2026-02-14T15:00:00Z,,pending,true
2,a1b2c3d4-...,user_add,approved,user_003,admin,Admin,2026-02-14T16:00:00Z,pending,approved,true
```

---

## 11. GET /api/approval/policies

### 概要

承認ポリシーの一覧を取得する。

### 認可

- **必要ロール**: Operator, Approver, Admin
- **必要権限**: `view:approval_policies`

### レスポンス

#### 200 OK

```json
{
  "status": "success",
  "policies": [
    {
      "id": 1,
      "operation_type": "user_add",
      "description": "ユーザーアカウント追加",
      "approval_required": true,
      "approver_roles": ["Approver", "Admin"],
      "approval_count": 1,
      "timeout_hours": 24,
      "auto_execute": false,
      "risk_level": "HIGH"
    },
    {
      "id": 2,
      "operation_type": "user_delete",
      "description": "ユーザーアカウント削除",
      "approval_required": true,
      "approver_roles": ["Admin"],
      "approval_count": 1,
      "timeout_hours": 24,
      "auto_execute": false,
      "risk_level": "CRITICAL"
    }
  ]
}
```

---

## 12. GET /api/approval/stats

### 概要

承認ワークフローの統計情報を取得する。

### 認可

- **必要ロール**: Admin
- **必要権限**: `view:approval_stats`

### クエリパラメータ

| パラメータ | 型 | 必須 | デフォルト | 説明 |
|-----------|------|------|-----------|------|
| period | string | NO | 30d | 集計期間（7d, 30d, 90d, 365d） |

### レスポンス

#### 200 OK

```json
{
  "status": "success",
  "period": "30d",
  "stats": {
    "total_requests": 45,
    "pending": 5,
    "approved": 25,
    "rejected": 8,
    "expired": 4,
    "executed": 22,
    "execution_failed": 3,
    "cancelled": 3,
    "approval_rate": 75.8,
    "average_approval_time_hours": 4.2,
    "by_type": {
      "user_add": 15,
      "user_delete": 5,
      "cron_add": 10,
      "cron_modify": 8,
      "service_stop": 7
    },
    "by_risk_level": {
      "CRITICAL": 5,
      "HIGH": 30,
      "MEDIUM": 10
    }
  }
}
```

---

## Pydantic モデル定義

以下は実装時に `backend/core/approval/models.py` に定義するモデルの仕様。

### リクエストモデル

```python
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime

class CreateApprovalRequest(BaseModel):
    """承認リクエスト作成"""
    request_type: str = Field(
        ...,
        description="操作種別",
        examples=["user_add", "cron_add"],
    )
    payload: dict = Field(
        ...,
        description="操作パラメータ",
    )
    reason: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="申請理由",
    )

class ApproveAction(BaseModel):
    """承認アクション"""
    comment: Optional[str] = Field(
        None,
        max_length=500,
        description="承認コメント",
    )

class RejectAction(BaseModel):
    """拒否アクション"""
    reason: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="拒否理由",
    )

class CancelAction(BaseModel):
    """キャンセルアクション"""
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="キャンセル理由",
    )
```

### レスポンスモデル

```python
class ApprovalRequestSummary(BaseModel):
    """承認リクエスト一覧用サマリー"""
    id: str
    request_type: str
    request_type_description: str
    risk_level: str
    requester_id: str
    requester_name: str
    status: str
    reason: str
    created_at: datetime
    expires_at: datetime
    remaining_hours: Optional[float] = None
    payload_summary: Optional[str] = None

class ApprovalRequestDetail(BaseModel):
    """承認リクエスト詳細"""
    id: str
    request_type: str
    request_type_description: str
    risk_level: str
    requester_id: str
    requester_name: str
    request_payload: dict
    reason: str
    status: str
    created_at: datetime
    expires_at: datetime
    approved_by: Optional[str] = None
    approved_by_name: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    execution_result: Optional[dict] = None
    executed_at: Optional[datetime] = None
    history: list[dict] = []

class ApprovalHistoryEntry(BaseModel):
    """承認履歴エントリ"""
    id: int
    approval_request_id: str
    request_type: str
    action: str
    actor_id: str
    actor_name: str
    actor_role: str
    timestamp: datetime
    previous_status: Optional[str] = None
    new_status: Optional[str] = None
    details: Optional[dict] = None
    signature_valid: bool

class ApprovalPolicy(BaseModel):
    """承認ポリシー"""
    id: int
    operation_type: str
    description: str
    approval_required: bool
    approver_roles: list[str]
    approval_count: int
    timeout_hours: int
    auto_execute: bool
    risk_level: str

class ApprovalStats(BaseModel):
    """承認統計"""
    total_requests: int
    pending: int
    approved: int
    rejected: int
    expired: int
    executed: int
    execution_failed: int
    cancelled: int
    approval_rate: float
    average_approval_time_hours: float
    by_type: dict[str, int]
    by_risk_level: dict[str, int]
```

---

## 関連ドキュメント

- [承認ワークフロー詳細設計書](../architecture/approval-workflow-design.md)
- [SQLスキーマ](../database/approval-schema.sql)
