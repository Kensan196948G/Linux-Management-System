# Cron Jobs 管理モジュール - アーキテクチャ設計書

**作成日**: 2026-02-14
**作成者**: cron-planner (v03-planning-team)
**対象モジュール**: Cron Jobs Management (Phase 3 v0.3)
**セキュリティレベル**: MEDIUM RISK
**ステータス**: 設計段階（実装前）

---

## 1. モジュール概要

### 1.1 目的

Cron Jobs管理モジュールは、Linuxシステム上の定期実行タスク（crontab）を**安全に閲覧・追加・削除**するための管理インターフェースを提供する。

### 1.2 スコープ

| 操作 | 対応 | 承認要否 | 備考 |
|------|------|---------|------|
| Cronジョブ一覧表示 | READ | 不要 | 自分のジョブのみ（Admin: 全ユーザー） |
| Cronジョブ詳細表示 | READ | 不要 | 同上 |
| Cronジョブ追加 | WRITE | **承認必須** | allowlistコマンドのみ |
| Cronジョブ削除 | WRITE | **承認必須** | 自分のジョブのみ |
| Cronジョブ有効/無効化 | WRITE | **承認必須** | コメントアウト方式 |
| 任意コマンド実行 | **禁止** | - | 実装しない |
| crontab直接編集 | **禁止** | - | 実装しない |

### 1.3 設計原則

1. **Allowlist First**: 許可されたコマンドのみ登録可能
2. **承認フロー統合**: 全WRITE操作は承認ワークフロー経由
3. **sudo ラッパー経由**: crontab操作は専用ラッパースクリプトを使用
4. **監査証跡**: 全操作を監査ログに記録
5. **最小権限**: ユーザーは自分のジョブのみ操作可能

---

## 2. 全体アーキテクチャ

### 2.1 レイヤー構成

```
+--------------------------------------------------+
|  Frontend (cron.html + cron.js)                   |
|  - Cronジョブ一覧表示                              |
|  - 追加/削除 承認リクエストフォーム                   |
|  - allowlistコマンドのドロップダウン選択              |
+--------------------------------------------------+
            |  HTTP REST API
            v
+--------------------------------------------------+
|  API Layer (backend/api/routes/cron.py)           |
|  - GET  /api/cron           (一覧取得)             |
|  - GET  /api/cron/{id}      (詳細取得)             |
|  - POST /api/cron           (追加リクエスト)         |
|  - DELETE /api/cron/{id}    (削除リクエスト)         |
|  - PATCH /api/cron/{id}     (有効/無効切替)         |
|  - Pydantic バリデーション                          |
|  - 権限チェック (require_permission)                |
+--------------------------------------------------+
            |
            v
+--------------------------------------------------+
|  Service Layer (backend/core/cron_service.py)     |
|  - ビジネスロジック                                 |
|  - allowlist検証                                   |
|  - スケジュール検証                                 |
|  - 承認フロー連携                                   |
+--------------------------------------------------+
            |                          |
            v                          v
+------------------------+  +------------------------+
|  Approval Service      |  |  Sudo Wrapper          |
|  (承認ワークフロー)      |  |  (sudo_wrapper.py)     |
|  - create_request()    |  |  - list_cron_jobs()    |
|  - approve()           |  |  - add_cron_job()      |
|  - reject()            |  |  - remove_cron_job()   |
|  - on_approved() hook  |  |  - toggle_cron_job()   |
+------------------------+  +------------------------+
                                       |
                                       | subprocess (shell=False)
                                       v
+--------------------------------------------------+
|  Sudo Wrappers (bash scripts)                     |
|  - adminui-cron-list.sh     (crontab -l)          |
|  - adminui-cron-add.sh      (crontab追加)          |
|  - adminui-cron-remove.sh   (crontab行削除)        |
|  - adminui-cron-toggle.sh   (有効/無効切替)         |
+--------------------------------------------------+
            |  sudo (NOPASSWD)
            v
+--------------------------------------------------+
|  System (crontab)                                 |
|  - /var/spool/cron/crontabs/{user}                |
+--------------------------------------------------+
```

### 2.2 データフロー

#### READ フロー（承認不要）

```
Browser → GET /api/cron
  → require_permission("read:cron")
  → cron_service.list_jobs(user)
  → sudo_wrapper.list_cron_jobs(user)
  → subprocess: sudo adminui-cron-list.sh {user}
  → crontab -u {user} -l
  → JSON parse → Response
```

#### WRITE フロー（承認必須）

```
Browser → POST /api/cron (schedule, command, reason)
  → require_permission("write:cron")
  → cron_service.validate_request(schedule, command)
    → validate_cron_schedule(schedule)
    → validate_cron_command(command)  # allowlist check
  → approval_service.create_request(
      type="cron_add",
      payload={schedule, command, user},
      reason=reason
    )
  → Response: {status: "approval_pending", request_id: "..."}

--- 承認者が承認 ---

approval_service.on_approved("cron_add", request_id)
  → cron_service.execute_add(request)
  → sudo_wrapper.add_cron_job(user, schedule, command)
  → subprocess: sudo adminui-cron-add.sh {user} {schedule} {command}
  → audit_log.record(operation="cron_add", ...)
```

---

## 3. セキュリティ境界

### 3.1 境界定義

```
+-----------------------------------------------------------+
|                    Trust Boundary 1                         |
|  Browser (Untrusted)                                       |
|  - ユーザー入力は全て信頼しない                                |
|  - クライアント側バリデーションは利便性のみ                      |
+-----------------------------------------------------------+
            | HTTPS + JWT Token
            v
+-----------------------------------------------------------+
|                    Trust Boundary 2                         |
|  API Layer (Semi-Trusted)                                  |
|  - JWT認証 + 権限チェック                                    |
|  - Pydantic入力バリデーション                                |
|  - レート制限                                               |
+-----------------------------------------------------------+
            | Internal call
            v
+-----------------------------------------------------------+
|                    Trust Boundary 3                         |
|  Service Layer (Trusted)                                   |
|  - allowlist検証（サーバーサイド最終防壁）                      |
|  - スケジュール正規表現検証                                    |
|  - 承認フロー強制                                            |
+-----------------------------------------------------------+
            | subprocess (shell=False, 配列渡し)
            v
+-----------------------------------------------------------+
|                    Trust Boundary 4                         |
|  Sudo Wrapper (Highly Trusted)                             |
|  - set -euo pipefail                                       |
|  - 再度の入力検証（多重防御）                                  |
|  - allowlist再チェック                                       |
|  - crontabへの書き込み                                       |
+-----------------------------------------------------------+
            | sudo (NOPASSWD, 限定コマンド)
            v
+-----------------------------------------------------------+
|  System crontab (Root Trusted)                             |
+-----------------------------------------------------------+
```

### 3.2 多重防御（Defense in Depth）

各層での検証項目:

| 層 | コマンド検証 | スケジュール検証 | ユーザー名検証 | 特殊文字拒否 |
|----|------------|---------------|-------------|------------|
| Frontend (JS) | ドロップダウン選択 | フォーマットチェック | - | 基本チェック |
| API (Pydantic) | パターン照合 | 正規表現 | パターン照合 | 完全拒否 |
| Service (Python) | **allowlist照合** | **完全検証** | **権限チェック** | 完全拒否 |
| Wrapper (Bash) | **allowlist再照合** | **再検証** | **ユーザー存在確認** | 完全拒否 |

---

## 4. APIエンドポイント設計

### 4.1 GET /api/cron - Cronジョブ一覧取得

```python
@router.get("/cron")
async def list_cron_jobs(
    user: Optional[str] = Query(
        None,
        pattern="^[a-z_][a-z0-9_-]{0,31}$",
        description="対象ユーザー（Admin専用、省略時は自分）"
    ),
    current_user: TokenData = Depends(require_permission("read:cron"))
) -> CronJobListResponse:
    """Cronジョブ一覧を取得"""
```

**レスポンス例:**
```json
{
  "status": "success",
  "user": "svc-adminui",
  "jobs": [
    {
      "id": "cron_001",
      "schedule": "0 2 * * *",
      "schedule_human": "Every day at 02:00",
      "command": "/usr/bin/rsync",
      "arguments": "-avz /data /backup/data",
      "enabled": true,
      "created_at": "2026-02-14T10:00:00Z",
      "created_by": "admin"
    }
  ],
  "total_count": 1,
  "max_allowed": 10
}
```

### 4.2 POST /api/cron - Cronジョブ追加リクエスト

```python
@router.post("/cron")
async def create_cron_job(
    request: CronJobCreateRequest,
    current_user: TokenData = Depends(require_permission("write:cron"))
) -> ApprovalPendingResponse:
    """Cronジョブ追加の承認リクエストを作成"""
```

**リクエスト:**
```json
{
  "schedule": "0 2 * * *",
  "command": "/usr/bin/rsync",
  "arguments": "-avz /data /backup/data",
  "comment": "Daily data backup",
  "reason": "Nightly backup of application data to backup server"
}
```

**レスポンス:**
```json
{
  "status": "approval_pending",
  "request_id": "apr_20260214_001",
  "message": "Cron job creation request submitted for approval."
}
```

### 4.3 DELETE /api/cron/{job_id} - Cronジョブ削除リクエスト

```python
@router.delete("/cron/{job_id}")
async def delete_cron_job(
    job_id: str = Path(..., pattern="^cron_[0-9]{3,6}$"),
    reason: str = Query(..., min_length=10, max_length=500),
    current_user: TokenData = Depends(require_permission("write:cron"))
) -> ApprovalPendingResponse:
    """Cronジョブ削除の承認リクエストを作成"""
```

### 4.4 PATCH /api/cron/{job_id} - Cronジョブ有効/無効切替

```python
@router.patch("/cron/{job_id}")
async def toggle_cron_job(
    job_id: str = Path(..., pattern="^cron_[0-9]{3,6}$"),
    request: CronJobToggleRequest,
    current_user: TokenData = Depends(require_permission("write:cron"))
) -> ApprovalPendingResponse:
    """Cronジョブの有効/無効を切り替える承認リクエストを作成"""
```

---

## 5. データモデル

### 5.1 Pydanticモデル

```python
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime


class CronJobCreateRequest(BaseModel):
    """Cronジョブ追加リクエスト"""
    schedule: str = Field(
        ...,
        description="Cron式スケジュール (例: '0 2 * * *')",
        pattern=r"^[\d\*\/\-\,\s]+$",
        max_length=50
    )
    command: str = Field(
        ...,
        description="実行コマンド（絶対パス必須、allowlistのみ）",
        pattern=r"^/[a-zA-Z0-9/_\-\.]+$",
        max_length=256
    )
    arguments: Optional[str] = Field(
        None,
        description="コマンド引数",
        max_length=512
    )
    comment: Optional[str] = Field(
        None,
        description="ジョブの説明",
        max_length=256
    )
    reason: str = Field(
        ...,
        description="追加理由（承認者向け）",
        min_length=10,
        max_length=500
    )

    @field_validator("command")
    @classmethod
    def validate_command_in_allowlist(cls, v: str) -> str:
        """コマンドがallowlistに含まれることを検証"""
        from ..core.cron_config import ALLOWED_CRON_COMMANDS
        if v not in ALLOWED_CRON_COMMANDS:
            raise ValueError(f"Command not in allowlist: {v}")
        return v

    @field_validator("arguments")
    @classmethod
    def validate_arguments_no_injection(cls, v: Optional[str]) -> Optional[str]:
        """引数にインジェクション文字列がないことを検証"""
        if v is None:
            return v
        # v0.3統合: backend/core/validation.py のFORBIDDEN_CHARS_LISTを使用
        # 21文字セット（CLAUDE.md 15文字 + users-planner拡張 6文字）
        from backend.core.validation import validate_no_forbidden_chars
        try:
            validate_no_forbidden_chars(v, "arguments")
        except ValidationError as e:
            raise ValueError(str(e))
        return v


class CronJobResponse(BaseModel):
    """Cronジョブレスポンス"""
    id: str
    schedule: str
    schedule_human: str
    command: str
    arguments: Optional[str] = None
    comment: Optional[str] = None
    enabled: bool
    user: str
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None


class CronJobListResponse(BaseModel):
    """Cronジョブ一覧レスポンス"""
    status: str
    user: str
    jobs: List[CronJobResponse]
    total_count: int
    max_allowed: int = 10


class CronJobToggleRequest(BaseModel):
    """Cronジョブ有効/無効切替リクエスト"""
    enabled: bool
    reason: str = Field(..., min_length=10, max_length=500)
```

### 5.2 設定モデル（cron_config.py）

```python
"""Cron Jobs モジュール設定"""

# 許可コマンドリスト（絶対パスのみ）
ALLOWED_CRON_COMMANDS: list[str] = [
    "/usr/bin/rsync",
    "/usr/local/bin/healthcheck.sh",
    "/usr/bin/find",
    "/usr/bin/tar",
    "/usr/bin/gzip",
    "/usr/bin/curl",
    "/usr/bin/wget",
    "/usr/bin/python3",
    "/usr/bin/node",
]

# 明示的禁止コマンド（allowlistに含まれなくても拒否されるが、明示的に定義）
FORBIDDEN_CRON_COMMANDS: list[str] = [
    "/bin/bash",
    "/bin/sh",
    "/bin/zsh",
    "/bin/dash",
    "/usr/bin/bash",
    "/usr/bin/sh",
    "/usr/bin/rm",
    "/bin/rm",
    "/sbin/reboot",
    "/sbin/shutdown",
    "/sbin/init",
    "/sbin/mkfs",
    "/sbin/fdisk",
    "/usr/bin/dd",
    "/bin/dd",
    "/usr/bin/chmod",
    "/bin/chmod",
    "/usr/bin/chown",
    "/bin/chown",
    "/usr/sbin/visudo",
    "/usr/bin/sudo",
]

# ユーザーあたりの最大Cronジョブ数
MAX_CRON_JOBS_PER_USER: int = 10

# スケジュール検証: 最小実行間隔（分）
MIN_EXECUTION_INTERVAL_MINUTES: int = 5

# 引数に含めてはいけない文字
FORBIDDEN_ARGUMENT_CHARS: list[str] = [
    ";", "|", "&", "$", "(", ")", "`",
    ">", "<", "{", "}", "[", "]",
]
```

---

## 6. 承認フロー統合

### 6.1 承認リクエストタイプ

| リクエストタイプ | 操作 | 承認者 | 自動実行 | 備考 |
|---------------|------|--------|---------|------|
| `cron_add` | Cronジョブ追加 | Admin | 承認後にラッパー実行 | approval-architect定義済み |
| `cron_delete` | Cronジョブ削除 | Admin | 承認後にラッパー実行 | approval-architect定義済み |
| `cron_modify` | 有効/無効切替 | Admin | 承認後にラッパー実行 | approval-architect定義済み (toggle操作はcron_modifyに統合) |

### 6.2 承認後の自動実行フック

```python
async def on_cron_add_approved(request: ApprovalRequest) -> dict:
    """cron_add 承認後に自動実行されるフック"""
    payload = request.payload
    result = sudo_wrapper.add_cron_job(
        user=payload["user"],
        schedule=payload["schedule"],
        command=payload["command"],
        arguments=payload.get("arguments", ""),
        comment=payload.get("comment", "")
    )

    audit_log.record(
        operation="cron_add",
        user_id=request.requester_id,
        approved_by=request.approved_by,
        target=f"{payload['command']} ({payload['schedule']})",
        status="success" if result["status"] == "success" else "failure",
        details=result
    )

    return result
```

### 6.3 approval-architect モジュールとの整合性

本モジュールは approval-architect が設計する承認ワークフロー基盤と以下のインターフェースで統合する:

```python
# 承認リクエスト作成
approval_service.create_request(
    request_type: str,        # "cron_add" | "cron_remove" | "cron_toggle"
    requester_id: str,        # リクエスト者のユーザーID
    payload: dict,            # 操作の詳細データ
    reason: str,              # 理由（承認者向け）
    auto_execute: bool = True # 承認後の自動実行有無
)

# 承認後コールバック登録
approval_service.register_handler(
    request_type="cron_add",
    handler=on_cron_add_approved
)
approval_service.register_handler(
    request_type="cron_delete",
    handler=on_cron_remove_approved
)
approval_service.register_handler(
    request_type="cron_modify",
    handler=on_cron_toggle_approved
)
```

---

## 7. UI設計

### 7.1 画面構成

#### Cronジョブ管理画面 (cron.html)

```
+----------------------------------------------------------+
| Linux Management System          [admin] [Logout]         |
+----------------------------------------------------------+
| [Sidebar Menu]  |  Cron Jobs Management                   |
|                 |                                          |
| System          |  [+ Add Cron Job]  Jobs: 3/10           |
|   Dashboard     |                                          |
|   Processes     |  +------+----------+---------+--------+ |
|   Cron Jobs  <- |  | Sched| Command  | Status  | Action | |
|   Users         |  +------+----------+---------+--------+ |
|   ...           |  |0 2 **| rsync    | Active  |[D][T]  | |
|                 |  |*/5 **| health.. | Active  |[D][T]  | |
|                 |  |0 0 1*| tar ..   | Disabled|[D][T]  | |
|                 |  +------+----------+---------+--------+ |
|                 |                                          |
|                 |  [D] = Delete  [T] = Toggle              |
+----------------------------------------------------------+
```

#### 追加モーダル

```
+----------------------------------------------+
|  Add Cron Job                          [X]   |
+----------------------------------------------+
|                                              |
|  Schedule:                                   |
|  [分] [時] [日] [月] [曜日]                    |
|  Preset: [Every hour v]                      |
|  Preview: "Every day at 02:00 AM"            |
|                                              |
|  Command:                                    |
|  [/usr/bin/rsync            v]               |
|  (allowlist から選択)                          |
|                                              |
|  Arguments:                                  |
|  [-avz /data /backup/data          ]         |
|                                              |
|  Comment:                                    |
|  [Daily data backup                 ]        |
|                                              |
|  Reason for request: *                       |
|  [Nightly backup of app data ...    ]        |
|                                              |
|  [Cancel]  [Submit Approval Request]         |
+----------------------------------------------+
```

### 7.2 スケジュールプリセット

| プリセット名 | Cron式 | 説明 |
|------------|--------|------|
| Every 5 minutes | `*/5 * * * *` | 5分ごと |
| Every hour | `0 * * * *` | 毎時0分 |
| Every day at 2:00 | `0 2 * * *` | 毎日2:00 |
| Every Monday at 3:00 | `0 3 * * 1` | 毎週月曜3:00 |
| First day of month | `0 0 1 * *` | 毎月1日0:00 |

---

## 8. 権限マトリクス

### 8.1 ロール別権限

| 操作 | Viewer | Operator | Admin |
|------|--------|----------|-------|
| 自分のCronジョブ一覧 | READ | READ | READ |
| 他ユーザーのCronジョブ一覧 | - | - | READ |
| Cronジョブ追加リクエスト | - | REQUEST | REQUEST |
| Cronジョブ削除リクエスト | - | REQUEST | REQUEST |
| Cronジョブ有効/無効切替 | - | REQUEST | REQUEST |
| 承認リクエスト承認 | - | - | APPROVE |
| 承認リクエスト却下 | - | - | REJECT |

### 8.2 パーミッション定義

```python
CRON_PERMISSIONS = {
    "read:cron": ["Viewer", "Operator", "Admin"],
    "write:cron": ["Operator", "Admin"],
    "approve:cron": ["Admin"],
}
```

---

## 9. エラーハンドリング

### 9.1 エラーコード

| HTTPステータス | エラーコード | 説明 |
|-------------|-----------|------|
| 400 | `INVALID_SCHEDULE` | 不正なスケジュール形式 |
| 400 | `INVALID_COMMAND` | 不正なコマンドパス |
| 400 | `FORBIDDEN_CHARACTERS` | 禁止文字が含まれる |
| 403 | `COMMAND_NOT_ALLOWED` | allowlist外のコマンド |
| 403 | `ACCESS_DENIED` | 権限不足 |
| 403 | `OTHER_USER_JOB` | 他ユーザーのジョブは操作不可 |
| 409 | `MAX_JOBS_EXCEEDED` | ジョブ数上限超過 |
| 409 | `DUPLICATE_JOB` | 同一ジョブが既に存在 |
| 404 | `JOB_NOT_FOUND` | 指定ジョブが存在しない |
| 500 | `WRAPPER_ERROR` | ラッパースクリプト実行失敗 |

### 9.2 エラーレスポンス形式

```json
{
  "status": "error",
  "code": "COMMAND_NOT_ALLOWED",
  "message": "Command '/bin/bash' is not in the allowlist",
  "detail": {
    "command": "/bin/bash",
    "allowed_commands": ["/usr/bin/rsync", "/usr/bin/find", "..."]
  }
}
```

---

## 10. sudoers 設定

### 10.1 必要な設定

```sudoers
# Cron Jobs 管理ラッパー
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-cron-list.sh
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-cron-add.sh
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-cron-remove.sh
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-cron-toggle.sh
```

### 10.2 変更手順

sudoersファイルの変更は**人間の承認が必須**であり、以下の手順で実施する:

1. 設計書の人間承認
2. `visudo` による安全な編集
3. 構文チェック（`visudo -c`）
4. テスト実行
5. 監査ログ記録

---

## 11. テスト要件

### 11.1 テストカバレッジ目標

| コンポーネント | 目標 |
|-------------|------|
| cron_service.py | 90%以上 |
| routes/cron.py | 85%以上 |
| cron_config.py | 100% |
| adminui-cron-*.sh | 100%（全パターン） |

### 11.2 必須テストケース

- allowlist内コマンドの正常追加
- allowlist外コマンドの拒否
- 禁止コマンドの即座拒否
- 特殊文字を含む入力の拒否
- スケジュール形式の検証（正常/異常）
- ジョブ数上限超過の拒否
- 権限不足ユーザーのアクセス拒否
- 他ユーザーのジョブ操作の拒否
- 承認フロー連携テスト
- ラッパースクリプトの全パターンテスト

---

## 12. 実装優先度

### Phase 3a（基本機能）

1. Cronジョブ一覧表示（READ）
2. sudo ラッパースクリプト作成（list, add, remove）
3. API エンドポイント実装
4. フロントエンド UI

### Phase 3b（承認フロー統合）

1. 承認ワークフロー連携
2. 承認後の自動実行フック
3. 承認履歴の表示

### Phase 3c（拡張機能）

1. 有効/無効切替
2. スケジュールプリセット
3. 実行履歴表示

---

## 13. 関連ドキュメント

- [docs/security/cron-jobs-threat-analysis.md](../security/cron-jobs-threat-analysis.md) - 脅威分析
- [docs/security/cron-allowlist-policy.md](../security/cron-allowlist-policy.md) - allowlistポリシー
- [wrappers/spec/adminui-cron-list.sh.spec](../../wrappers/spec/adminui-cron-list.sh.spec) - ラッパー仕様
- [wrappers/spec/adminui-cron-add.sh.spec](../../wrappers/spec/adminui-cron-add.sh.spec) - ラッパー仕様
- [wrappers/spec/adminui-cron-remove.sh.spec](../../wrappers/spec/adminui-cron-remove.sh.spec) - ラッパー仕様
- [wrappers/spec/adminui-cron-toggle.sh.spec](../../wrappers/spec/adminui-cron-toggle.sh.spec) - ラッパー仕様
- [CLAUDE.md](../../CLAUDE.md) - セキュリティ原則
- [wrappers/README.md](../../wrappers/README.md) - ラッパー設計指針

---

**最終更新**: 2026-02-14
**次回レビュー**: 実装開始前に人間承認必須
