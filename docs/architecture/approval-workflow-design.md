# 承認ワークフロー基盤 詳細設計書

**バージョン**: v0.3
**作成日**: 2026-02-14
**ステータス**: 設計完了（実装前レビュー待ち）

---

## 1. 概要

### 1.1 目的

本設計書は、Linux Management System v0.3 における承認ワークフロー基盤（Approval Workflow）の詳細設計を定義する。危険な操作（ユーザー追加・削除、Cronジョブ追加等）の実行前に、権限を持つ承認者（Approver/Admin）による明示的な承認を必須とすることで、**職務分離（Separation of Duties: SoD）** を実現する。

### 1.2 スコープ

| 区分 | 内容 |
|------|------|
| v0.3 実装範囲 | 単一承認フロー、タイムアウト処理、承認履歴 |
| v0.4 拡張予定 | 多段階承認、通知システム（メール/Slack） |
| 対象外 | 任意コマンド実行、shell直接操作 |

### 1.3 設計原則

本設計は CLAUDE.md のセキュリティ原則を完全遵守する。

1. **Allowlist First**: 承認対象の操作は明示的に定義されたもののみ
2. **Deny by Default**: 承認ポリシーに定義されていない操作は全拒否
3. **Audit Trail**: 全ての承認アクション（作成・承認・拒否・期限切れ・実行）を改ざん防止ログに記録
4. **Self-Approval Prohibition**: 自己承認の完全禁止（requester_id != approved_by）
5. **Least Privilege**: 承認権限は Approver/Admin ロールに限定

---

## 2. データベース設計

### 2.1 概要

現行システムは SQLite（`data/dev/database.db`）を使用している。承認ワークフローのテーブルも同一 SQLite データベースに作成する。将来の PostgreSQL 移行を考慮し、標準 SQL に準拠した設計とする。

### 2.2 ER図（テキスト形式）

```
+---------------------+       +------------------------+
| approval_policies   |       | approval_requests      |
|---------------------|       |------------------------|
| id (PK)             |       | id (PK, UUID)          |
| operation_type (UQ) |<------| request_type (FK概念)   |
| approval_required   |       | requester_id            |
| approver_roles      |       | request_payload         |
| approval_count      |       | reason                  |
| timeout_hours       |       | status                  |
| auto_execute        |       | created_at              |
| description         |       | expires_at              |
| risk_level          |       | approved_by             |
+---------------------+       | approved_at             |
                               | rejection_reason        |
                               +------------------------+
                                        |
                                        | 1:N
                                        v
                               +------------------------+
                               | approval_history       |
                               |------------------------|
                               | id (PK, AUTOINCREMENT) |
                               | approval_request_id(FK)|
                               | action                 |
                               | actor_id               |
                               | timestamp              |
                               | details                |
                               | signature (HMAC)       |
                               +------------------------+
```

### 2.3 テーブル定義

#### 2.3.1 approval_policies（承認ポリシー）

承認が必要な操作種別とそのルールを定義する静的テーブル。

| カラム名 | 型 | 制約 | 説明 |
|----------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | ポリシーID |
| operation_type | VARCHAR(50) | NOT NULL, UNIQUE | 操作種別キー |
| description | VARCHAR(200) | NOT NULL | 操作の説明 |
| approval_required | BOOLEAN | NOT NULL, DEFAULT TRUE | 承認必須フラグ |
| approver_roles | TEXT (JSON) | NOT NULL | 承認可能ロール一覧 |
| approval_count | INTEGER | NOT NULL, DEFAULT 1 | 必要承認者数 |
| timeout_hours | INTEGER | NOT NULL, DEFAULT 24 | 承認期限（時間） |
| auto_execute | BOOLEAN | NOT NULL, DEFAULT FALSE | 承認後自動実行 |
| risk_level | VARCHAR(10) | NOT NULL, DEFAULT 'HIGH' | リスクレベル |
| created_at | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 作成日時 |
| updated_at | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 更新日時 |

**operation_type の allowlist（v0.3 初期値）**:

| operation_type | description | risk_level | timeout_hours |
|----------------|-------------|------------|---------------|
| user_add | ユーザーアカウント追加 | HIGH | 24 |
| user_delete | ユーザーアカウント削除 | CRITICAL | 24 |
| user_modify | ユーザーアカウント変更 | HIGH | 24 |
| group_add | グループ追加 | MEDIUM | 24 |
| group_delete | グループ削除 | HIGH | 24 |
| cron_add | Cronジョブ追加 | HIGH | 24 |
| cron_delete | Cronジョブ削除 | HIGH | 24 |
| cron_modify | Cronジョブ変更 | HIGH | 24 |
| service_stop | サービス停止 | CRITICAL | 12 |
| firewall_modify | ファイアウォール変更 | CRITICAL | 24 |

#### 2.3.2 approval_requests（承認リクエスト）

個別の承認申請を管理する動的テーブル。

| カラム名 | 型 | 制約 | 説明 |
|----------|------|------|------|
| id | VARCHAR(36) | PRIMARY KEY | UUID v4 |
| request_type | VARCHAR(50) | NOT NULL | 操作種別（policies参照） |
| requester_id | VARCHAR(50) | NOT NULL | 申請者ユーザーID |
| requester_name | VARCHAR(100) | NOT NULL | 申請者表示名 |
| request_payload | TEXT (JSON) | NOT NULL | 操作パラメータ |
| reason | TEXT | NOT NULL | 申請理由 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'pending' | ステータス |
| created_at | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 申請日時 |
| expires_at | TIMESTAMP | NOT NULL | 承認期限 |
| approved_by | VARCHAR(50) | NULL | 承認者ユーザーID |
| approved_by_name | VARCHAR(100) | NULL | 承認者表示名 |
| approved_at | TIMESTAMP | NULL | 承認日時 |
| rejection_reason | TEXT | NULL | 拒否理由 |
| execution_result | TEXT (JSON) | NULL | 実行結果 |
| executed_at | TIMESTAMP | NULL | 実行日時 |

**status の許可値**:

| status | 説明 | 遷移元 |
|--------|------|--------|
| pending | 承認待ち | （初期状態） |
| approved | 承認済み | pending |
| rejected | 拒否 | pending |
| expired | 期限切れ | pending |
| executed | 実行完了 | approved |
| execution_failed | 実行失敗 | approved |
| cancelled | 申請者によるキャンセル | pending |

#### 2.3.3 approval_history（承認履歴 - 追記専用）

改ざん防止のため、全アクションを追記専用で記録する監査テーブル。DELETE/UPDATE は禁止。

| カラム名 | 型 | 制約 | 説明 |
|----------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 連番ID |
| approval_request_id | VARCHAR(36) | NOT NULL, REFERENCES approval_requests(id) | リクエストID |
| action | VARCHAR(30) | NOT NULL | アクション種別 |
| actor_id | VARCHAR(50) | NOT NULL | 実行者ユーザーID |
| actor_name | VARCHAR(100) | NOT NULL | 実行者表示名 |
| actor_role | VARCHAR(20) | NOT NULL | 実行者ロール |
| timestamp | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 記録日時 |
| details | TEXT (JSON) | NULL | 追加情報 |
| previous_status | VARCHAR(20) | NULL | 変更前ステータス |
| new_status | VARCHAR(20) | NULL | 変更後ステータス |
| signature | VARCHAR(64) | NOT NULL | HMAC-SHA256 署名 |

**action の許可値**:

| action | 説明 |
|--------|------|
| created | リクエスト作成 |
| approved | 承認 |
| rejected | 拒否 |
| expired | タイムアウトによる期限切れ |
| executed | 操作実行完了 |
| execution_failed | 操作実行失敗 |
| cancelled | 申請者によるキャンセル |

### 2.4 インデックス設計

```sql
-- approval_requests の検索最適化
CREATE INDEX idx_approval_requests_status ON approval_requests(status);
CREATE INDEX idx_approval_requests_requester ON approval_requests(requester_id);
CREATE INDEX idx_approval_requests_type_status ON approval_requests(request_type, status);
CREATE INDEX idx_approval_requests_expires ON approval_requests(expires_at);
CREATE INDEX idx_approval_requests_created ON approval_requests(created_at DESC);

-- approval_history の検索最適化
CREATE INDEX idx_approval_history_request ON approval_history(approval_request_id);
CREATE INDEX idx_approval_history_actor ON approval_history(actor_id);
CREATE INDEX idx_approval_history_timestamp ON approval_history(timestamp DESC);
```

---

## 3. 承認フロー設計

### 3.1 状態遷移図

```
                          +--[申請者キャンセル]--+
                          |                     |
                          v                     |
+----------+  申請   +---------+  承認   +----------+  実行   +----------+
| (なし)   | ------> | pending | ------> | approved | ------> | executed |
+----------+         +---------+         +----------+         +----------+
                       |    |                  |
                       |    |                  +--[実行失敗]-->  +------------------+
                       |    |                                   | execution_failed |
                       |    +--[拒否]--> +-----------+          +------------------+
                       |                 | rejected  |
                       |                 +-----------+
                       |
                       +--[期限切れ]--> +-----------+
                       |                | expired   |
                       |                +-----------+
                       |
                       +--[キャンセル]--> +-----------+
                                         | cancelled |
                                         +-----------+
```

### 3.2 フローA: 単一承認フロー（v0.3 実装対象）

```
[1] Operator が危険操作をリクエスト
    ├── 入力: request_type, payload, reason
    ├── バリデーション: operation_type が policies に存在すること
    ├── 権限チェック: Operator 以上であること
    └── 出力: approval_request 作成（status: pending）
         ↓
[2] System が approval_history に "created" を記録
    ├── HMAC-SHA256 署名を付与
    └── 出力: 履歴レコード追記
         ↓
[3] System が Approver/Admin に通知（v0.3: WebUI 内通知のみ）
    ├── 承認待ち一覧に新規リクエスト表示
    └── 出力: 通知レコード（将来: メール/Slack）
         ↓
[4] Approver/Admin が承認または拒否
    ├── 自己承認禁止チェック（requester_id != actor_id）
    ├── ロールチェック（Approver/Admin であること）
    ├── 承認の場合:
    │   ├── status: pending -> approved
    │   ├── approval_history に "approved" を記録
    │   └── auto_execute が TRUE の場合 → [5] へ
    └── 拒否の場合:
        ├── status: pending -> rejected
        ├── rejection_reason を記録
        └── approval_history に "rejected" を記録
         ↓
[5] 承認後の操作実行（auto_execute = TRUE の場合）
    ├── sudo ラッパー経由で操作を実行
    ├── 実行結果を execution_result に記録
    ├── 成功: status -> executed, approval_history に "executed" を記録
    └── 失敗: status -> execution_failed, approval_history に "execution_failed" を記録
```

### 3.3 フローB: タイムアウト処理

```
[1] System が定期的に期限切れリクエストをチェック（5分間隔）
    ├── SELECT * FROM approval_requests
    │   WHERE status = 'pending'
    │   AND expires_at < CURRENT_TIMESTAMP
    └── 出力: 期限切れリクエスト一覧
         ↓
[2] 各リクエストに対して:
    ├── status: pending -> expired
    ├── approval_history に "expired" を記録
    └── 申請者に通知（v0.3: WebUI 内通知のみ）
```

### 3.4 フローC: 申請者によるキャンセル

```
[1] 申請者が pending 状態のリクエストをキャンセル
    ├── 権限チェック: リクエストの requester_id と一致すること
    ├── 状態チェック: status が "pending" であること
    ├── status: pending -> cancelled
    └── approval_history に "cancelled" を記録
```

### 3.5 フローD: 多段階承認（v0.4 予定 - 設計のみ）

```
[1] Operator が危険操作をリクエスト（approval_count >= 2 の操作）
         ↓
[2] 1次承認者（Approver）が承認
    ├── 現在の承認数 < 必要承認数 の場合 → status は pending のまま
    └── approval_history に "approved" を記録（1次）
         ↓
[3] 2次承認者（Admin）が承認
    ├── 現在の承認数 >= 必要承認数 → status: pending -> approved
    └── approval_history に "approved" を記録（2次）
         ↓
[4] 操作実行
```

---

## 4. API設計

### 4.1 エンドポイント一覧

| メソッド | パス | 説明 | 認可 |
|----------|------|------|------|
| POST | /api/approval/request | 承認リクエスト作成 | Operator, Approver, Admin |
| GET | /api/approval/pending | 承認待ちリクエスト一覧 | Approver, Admin |
| GET | /api/approval/my-requests | 自分の申請一覧 | Operator, Approver, Admin |
| GET | /api/approval/{request_id} | リクエスト詳細取得 | 関係者（申請者 or Approver/Admin） |
| POST | /api/approval/{request_id}/approve | 承認実行 | Approver, Admin |
| POST | /api/approval/{request_id}/reject | 拒否実行 | Approver, Admin |
| POST | /api/approval/{request_id}/cancel | キャンセル | 申請者本人 |
| POST | /api/approval/{request_id}/execute | 手動実行（承認済みのみ） | Admin |
| GET | /api/approval/history | 承認履歴一覧 | Admin |
| GET | /api/approval/history/export | 承認履歴エクスポート | Admin |
| GET | /api/approval/policies | 承認ポリシー一覧 | Operator, Approver, Admin |
| GET | /api/approval/stats | 承認統計情報 | Admin |

詳細なAPI仕様は `docs/api/approval-api-spec.md` を参照。

### 4.2 認可マトリクス

| 操作 | Viewer | Operator | Approver | Admin |
|------|--------|----------|----------|-------|
| 承認リクエスト作成 | - | O | O | O |
| 承認待ち一覧閲覧 | - | - | O | O |
| 自分の申請一覧 | - | O | O | O |
| リクエスト詳細（自分の） | - | O | O | O |
| リクエスト詳細（他人の） | - | - | O | O |
| 承認実行 | - | - | O | O |
| 拒否実行 | - | - | O | O |
| キャンセル（自分の） | - | O | O | O |
| 手動実行 | - | - | - | O |
| 承認履歴閲覧 | - | - | - | O |
| 承認履歴エクスポート | - | - | - | O |
| 承認ポリシー閲覧 | - | O | O | O |
| 承認統計 | - | - | - | O |

### 4.3 新規権限の追加

既存の `auth.py` の ROLES 定義に以下の権限を追加する:

```python
# 追加する権限
"request:approval"        # 承認リクエスト作成
"view:approval_pending"   # 承認待ち一覧閲覧
"execute:approval"        # 承認/拒否実行
"execute:approved_action" # 承認済み操作の手動実行
"view:approval_history"   # 承認履歴閲覧
"export:approval_history" # 承認履歴エクスポート
"view:approval_policies"  # 承認ポリシー閲覧
"view:approval_stats"     # 承認統計閲覧
```

ロール別の権限割り当て:

```python
ROLES = {
    "Viewer": UserRole(
        name="Viewer",
        permissions=[
            "read:status", "read:logs", "read:processes",
            # 承認関連: なし
        ],
    ),
    "Operator": UserRole(
        name="Operator",
        permissions=[
            "read:status", "read:logs", "read:processes",
            "execute:service_restart",
            # 承認関連:
            "request:approval",
            "view:approval_policies",
        ],
    ),
    "Approver": UserRole(
        name="Approver",
        permissions=[
            "read:status", "read:logs", "read:processes",
            "execute:service_restart",
            "approve:dangerous_operation",
            # 承認関連:
            "request:approval",
            "view:approval_pending",
            "execute:approval",
            "view:approval_policies",
        ],
    ),
    "Admin": UserRole(
        name="Admin",
        permissions=[
            "read:status", "read:logs", "read:processes",
            "execute:service_restart",
            "approve:dangerous_operation",
            "manage:users", "manage:settings",
            # 承認関連:
            "request:approval",
            "view:approval_pending",
            "execute:approval",
            "execute:approved_action",
            "view:approval_history",
            "export:approval_history",
            "view:approval_policies",
            "view:approval_stats",
        ],
    ),
}
```

---

## 5. UI設計

### 5.1 画面遷移図

```
[サイドメニュー]
  ├── [承認リクエスト] ────────> [承認リクエスト作成画面]
  │                              ├── 操作種別選択
  │                              ├── パラメータ入力
  │                              ├── 理由入力
  │                              └── プレビュー → 送信
  │
  ├── [承認待ち] ─────────────> [承認待ち一覧画面] (Approver/Admin)
  │   (バッジ: 件数表示)           ├── フィルタ（種別/申請者/期限）
  │                              └── 各行クリック → [承認詳細画面]
  │                                                  ├── リクエスト内容表示
  │                                                  ├── [承認] ボタン
  │                                                  ├── [拒否] ボタン + 理由入力
  │                                                  └── 操作プレビュー
  │
  ├── [自分の申請] ───────────> [申請一覧画面]
  │                              ├── ステータスフィルタ
  │                              ├── 各行クリック → [申請詳細画面]
  │                              └── pending の場合 → [キャンセル] ボタン
  │
  └── [承認履歴] ─────────────> [承認履歴画面] (Admin)
                                 ├── 期間フィルタ
                                 ├── 操作種別フィルタ
                                 ├── 承認者フィルタ
                                 └── [CSV/JSONエクスポート] ボタン
```

### 5.2 ワイヤーフレーム（テキスト形式）

#### 5.2.1 承認リクエスト作成画面

```
+---------------------------------------------------------------+
| [Linux Management System]              [admin@example.com] [v] |
+---------------------------------------------------------------+
| > Approval > New Request                                       |
+---------------------------------------------------------------+
|                                                                 |
|  +--- 承認リクエスト作成 ----------------------------------+   |
|  |                                                          |   |
|  |  操作種別:  [ユーザーアカウント追加       v]              |   |
|  |                                                          |   |
|  |  +--- 操作パラメータ ---------------------------+        |   |
|  |  |  ユーザー名:  [__________________]           |        |   |
|  |  |  グループ:    [__________________]           |        |   |
|  |  |  ホームDir:   [/home/___________]            |        |   |
|  |  |  シェル:      [/bin/bash         v]          |        |   |
|  |  +----------------------------------------------+        |   |
|  |                                                          |   |
|  |  申請理由（必須）:                                       |   |
|  |  +----------------------------------------------+        |   |
|  |  | 新規プロジェクトメンバーのアカウント作成       |        |   |
|  |  | プロジェクト: XYZ                              |        |   |
|  |  +----------------------------------------------+        |   |
|  |                                                          |   |
|  |  +--- プレビュー ---------------------------------+      |   |
|  |  | 実行コマンド: adminui-user-add                 |      |   |
|  |  | 対象: username=newuser, group=developers       |      |   |
|  |  | リスクレベル: HIGH                              |      |   |
|  |  | 承認期限: 24時間後                              |      |   |
|  |  +------------------------------------------------+      |   |
|  |                                                          |   |
|  |  [キャンセル]                    [承認リクエスト送信]     |   |
|  +----------------------------------------------------------+   |
+---------------------------------------------------------------+
```

#### 5.2.2 承認待ち一覧画面

```
+---------------------------------------------------------------+
| [Linux Management System]              [admin@example.com] [v] |
+---------------------------------------------------------------+
| > Approval > Pending (5)                                       |
+---------------------------------------------------------------+
|                                                                 |
|  フィルタ: [全種別 v] [全申請者 v] [期限切れ間近 v] [検索...]   |
|                                                                 |
|  +--- 承認待ちリクエスト一覧 ----------------------------+     |
|  | # | 種別         | 申請者    | 理由       | 期限      |     |
|  |---|--------------|----------|------------|-----------|     |
|  | 1 | user_add     | operator | 新規メンバ | 23h残     |     |
|  | 2 | cron_add     | operator | バッチ追加 | 20h残     |     |
|  | 3 | user_delete  | admin    | 退職者     | 12h残     |     |
|  | 4 | service_stop | operator | メンテ     |  6h残     |     |
|  | 5 | group_add    | operator | 新部署     |  2h残 (!)|     |
|  +----------------------------------------------------------+   |
|                                                                 |
|  表示: 1-5 / 5件  [<前へ] [次へ>]                               |
+---------------------------------------------------------------+
```

#### 5.2.3 承認詳細画面

```
+---------------------------------------------------------------+
| [Linux Management System]              [admin@example.com] [v] |
+---------------------------------------------------------------+
| > Approval > Pending > Request #abc-123                        |
+---------------------------------------------------------------+
|                                                                 |
|  +--- リクエスト詳細 -----------------------------------+     |
|  |                                                       |     |
|  |  リクエストID: abc-123-def-456                        |     |
|  |  操作種別:     ユーザーアカウント追加 (user_add)       |     |
|  |  リスクレベル: HIGH                                    |     |
|  |  申請者:       operator (operator@example.com)         |     |
|  |  申請日時:     2026-02-14 15:00:00                     |     |
|  |  承認期限:     2026-02-15 15:00:00 (残り23時間)        |     |
|  |                                                       |     |
|  |  +--- 操作内容 ---------------------------------+     |     |
|  |  | {                                            |     |     |
|  |  |   "username": "newuser",                     |     |     |
|  |  |   "group": "developers",                     |     |     |
|  |  |   "home": "/home/newuser",                   |     |     |
|  |  |   "shell": "/bin/bash"                       |     |     |
|  |  | }                                            |     |     |
|  |  +----------------------------------------------+     |     |
|  |                                                       |     |
|  |  申請理由:                                             |     |
|  |  新規プロジェクトメンバーのアカウント作成               |     |
|  |  プロジェクト: XYZ                                     |     |
|  |                                                       |     |
|  |  +--- 承認/拒否 --------------------------------+     |     |
|  |  |                                              |     |     |
|  |  |  コメント（任意）:                           |     |     |
|  |  |  [________________________________]          |     |     |
|  |  |                                              |     |     |
|  |  |  [拒否]                         [承認]        |     |     |
|  |  +----------------------------------------------+     |     |
|  +-------------------------------------------------------+     |
+---------------------------------------------------------------+
```

#### 5.2.4 承認履歴画面

```
+---------------------------------------------------------------+
| [Linux Management System]              [admin@example.com] [v] |
+---------------------------------------------------------------+
| > Approval > History                                           |
+---------------------------------------------------------------+
|                                                                 |
|  フィルタ:                                                      |
|  期間: [2026-02-01] ～ [2026-02-14]                             |
|  種別: [全種別 v]  承認者: [全承認者 v]  結果: [全結果 v]       |
|                                                                 |
|  [CSV Export] [JSON Export]                                     |
|                                                                 |
|  +--- 承認履歴 ---------------------------------------------+  |
|  | 日時       | 種別      | 申請者   | 承認者 | 結果     |     |
|  |------------|-----------|---------|--------|----------|     |
|  | 02-14 15:30| user_add  | operator| admin  | approved |     |
|  | 02-14 14:00| cron_add  | operator| admin  | rejected |     |
|  | 02-13 10:00| user_del  | operator| -      | expired  |     |
|  | 02-12 09:00| group_add | operator| admin  | executed |     |
|  +-------------------------------------------------------------+|
|                                                                 |
|  表示: 1-4 / 4件  [<前へ] [次へ>]                               |
+---------------------------------------------------------------+
```

---

## 6. セキュリティ設計

### 6.1 脅威分析

| # | 脅威 | 影響度 | 緩和策 |
|---|------|--------|--------|
| T1 | 自己承認 | CRITICAL | requester_id != approved_by の強制チェック |
| T2 | 承認レコード改ざん | CRITICAL | HMAC-SHA256 署名、追記専用テーブル |
| T3 | 権限昇格 | HIGH | JWT ロールに基づく厳格な RBAC |
| T4 | 期限切れリクエストの悪用 | HIGH | status チェック + expires_at チェックの二重検証 |
| T5 | リクエストペイロード改ざん | HIGH | 作成時のペイロードを変更不可に |
| T6 | replay攻撃（同一リクエスト再利用） | MEDIUM | UUID一意性 + 実行済みチェック |
| T7 | タイミング攻撃（承認直後の改ざん） | MEDIUM | DB トランザクションによる原子性保証 |
| T8 | 大量リクエストによるDoS | MEDIUM | レート制限 + 同時pending上限 |

### 6.2 HMAC 署名による改ざん防止

approval_history の各レコードに HMAC-SHA256 署名を付与する。

```python
import hmac
import hashlib
import json

def compute_history_signature(
    approval_request_id: str,
    action: str,
    actor_id: str,
    timestamp: str,
    details: dict | None,
    secret_key: str,
) -> str:
    """
    承認履歴レコードの HMAC-SHA256 署名を計算

    Args:
        approval_request_id: リクエストID
        action: アクション種別
        actor_id: 実行者ID
        timestamp: タイムスタンプ (ISO 8601)
        details: 追加情報
        secret_key: HMAC 秘密鍵

    Returns:
        HMAC-SHA256 署名（16進数文字列、64文字）
    """
    # 署名対象データを正規化
    sign_data = {
        "approval_request_id": approval_request_id,
        "action": action,
        "actor_id": actor_id,
        "timestamp": timestamp,
        "details": details or {},
    }

    # JSON の正規化（キーソート、ASCII エスケープなし）
    canonical = json.dumps(sign_data, sort_keys=True, ensure_ascii=False)

    # HMAC-SHA256 署名の計算
    signature = hmac.new(
        secret_key.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return signature
```

**署名検証**:

```python
def verify_history_signature(record: dict, secret_key: str) -> bool:
    """
    承認履歴レコードの署名を検証

    Returns:
        署名が正しい場合 True
    """
    stored_signature = record.get("signature", "")

    computed = compute_history_signature(
        approval_request_id=record["approval_request_id"],
        action=record["action"],
        actor_id=record["actor_id"],
        timestamp=record["timestamp"],
        details=record.get("details"),
        secret_key=secret_key,
    )

    return hmac.compare_digest(stored_signature, computed)
```

### 6.3 自己承認防止

```python
def validate_not_self_approval(
    request: ApprovalRequest,
    current_user: TokenData,
) -> None:
    """
    自己承認を防止

    Raises:
        HTTPException: 自己承認の場合
    """
    if request.requester_id == current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-approval is prohibited. "
                   "A different Approver/Admin must approve this request.",
        )
```

### 6.4 入力バリデーション

承認リクエストの `request_payload` に対しても CLAUDE.md の特殊文字拒否を適用する。

```python
FORBIDDEN_CHARS = [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?", "{", "}", "[", "]"]

def validate_payload_values(payload: dict) -> None:
    """
    ペイロード内の全文字列値に対して特殊文字チェックを実行

    Raises:
        SecurityError: 禁止文字が含まれる場合
    """
    for key, value in payload.items():
        if isinstance(value, str):
            for char in FORBIDDEN_CHARS:
                if char in value:
                    raise SecurityError(
                        f"Forbidden character '{char}' detected "
                        f"in payload field '{key}'"
                    )
```

### 6.5 レート制限

| 操作 | 制限 |
|------|------|
| 承認リクエスト作成 | ユーザーあたり 10件/時間 |
| 同時 pending リクエスト | ユーザーあたり 20件 |
| 承認/拒否 | 承認者あたり 50件/時間 |
| 履歴エクスポート | 管理者あたり 5回/時間 |

### 6.6 監査ログ連携

承認ワークフローの全操作は、既存の `AuditLog` クラス（`backend/core/audit_log.py`）にも記録する。

```python
# 承認関連の操作種別
APPROVAL_OPERATIONS = {
    "approval_request_created",
    "approval_approved",
    "approval_rejected",
    "approval_expired",
    "approval_executed",
    "approval_execution_failed",
    "approval_cancelled",
}
```

---

## 7. 実装ガイドライン

### 7.1 ファイル構成

```
backend/
  api/
    routes/
      approval.py          # 承認ワークフローAPIルーター
  core/
    approval/
      __init__.py
      models.py            # Pydantic モデル定義
      service.py           # ビジネスロジック
      repository.py        # データベースアクセス
      scheduler.py         # タイムアウト処理スケジューラ
      security.py          # HMAC署名、バリデーション
frontend/
  js/
    approval.js            # 承認ワークフローUI
  dev/
    approval.html          # 承認ワークフロー画面
    approval-detail.html   # 承認詳細画面
    approval-history.html  # 承認履歴画面
```

### 7.2 実装順序

1. **データベーススキーマ作成** (`docs/database/approval-schema.sql`)
2. **Pydantic モデル定義** (`backend/core/approval/models.py`)
3. **リポジトリ層** (`backend/core/approval/repository.py`)
4. **ビジネスロジック層** (`backend/core/approval/service.py`)
5. **セキュリティ層** (`backend/core/approval/security.py`)
6. **API ルーター** (`backend/api/routes/approval.py`)
7. **タイムアウトスケジューラ** (`backend/core/approval/scheduler.py`)
8. **フロントエンド UI**
9. **テスト作成・実行**

### 7.3 既存コードとの統合ポイント

| 統合先 | 変更内容 |
|--------|----------|
| `backend/core/auth.py` | ROLES に承認関連権限を追加 |
| `backend/api/main.py` | 承認ルーターの登録、スケジューラの起動 |
| `backend/core/config.py` | HMAC 秘密鍵の設定追加 |
| `backend/core/audit_log.py` | 承認関連の操作種別追加 |
| `frontend/js/api.js` | 承認API呼び出し関数追加 |
| `frontend/dev/dashboard.html` | 承認待ちバッジ表示 |

### 7.4 テスト要件

| テストカテゴリ | テスト項目数（目標） |
|---------------|---------------------|
| 単体テスト（models） | 15+ |
| 単体テスト（service） | 25+ |
| 単体テスト（security） | 20+ |
| API テスト（routes） | 30+ |
| セキュリティテスト | 15+ |
| 統合テスト | 10+ |
| **合計** | **115+** |

必須テストケース:

- 自己承認の拒否
- 期限切れリクエストの承認拒否
- 権限不足での操作拒否
- HMAC 署名の検証
- 特殊文字を含むペイロードの拒否
- 同時実行時のデータ整合性
- ステータス遷移の正当性（不正な遷移の拒否）

### 7.5 パフォーマンス考慮

| 指標 | 目標値 |
|------|--------|
| 承認リクエスト作成 | < 200ms |
| 承認待ち一覧取得 | < 300ms（100件以下） |
| 承認実行 | < 500ms（操作実行除く） |
| 履歴検索 | < 1000ms（1000件以下） |

### 7.6 他モジュールとの連携

承認ワークフローは以下のモジュールと連携する:

| モジュール | 連携方法 |
|-----------|----------|
| Users and Groups | user_add/user_delete/user_modify 操作の承認フロー経由 |
| Cron Jobs | cron_add/cron_delete/cron_modify 操作の承認フロー経由 |
| Service Management | service_stop 操作の承認フロー経由 |
| Firewall | firewall_modify 操作の承認フロー経由 |

各モジュールは承認ワークフローAPIを呼び出して承認リクエストを作成し、承認後に実際の操作を実行する。

---

## 8. 将来拡張（v0.4 以降）

### 8.1 多段階承認

- approval_count > 1 のポリシーに対応
- approval_approvals テーブル（中間テーブル）の追加
- 承認進捗のリアルタイム表示

### 8.2 通知システム

- メール通知（SMTP）
- Slack 通知（Webhook）
- WebUI 内リアルタイム通知（WebSocket）

### 8.3 承認テンプレート

- よく使う承認リクエストのテンプレート化
- テンプレートからのワンクリック申請

### 8.4 承認ダッシュボード

- 承認待ち件数のリアルタイム表示
- 平均承認時間の統計
- 承認率・拒否率のグラフ

---

## 付録A: 用語集

| 用語 | 定義 |
|------|------|
| Requester | 承認リクエストを作成する申請者 |
| Approver | 承認リクエストを承認/拒否する承認者 |
| SoD | Separation of Duties（職務分離） |
| HMAC | Hash-based Message Authentication Code |
| RBAC | Role-Based Access Control（ロールベースアクセス制御） |

## 付録B: 関連ドキュメント

- [API仕様書](../api/approval-api-spec.md)
- [SQLスキーマ](../database/approval-schema.sql)
- [セキュリティポリシー](../../SECURITY.md)
- [要件定義書](../要件定義書_詳細設計仕様書.md)
