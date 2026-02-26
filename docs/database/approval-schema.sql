-- ============================================================
-- 承認ワークフロー基盤 データベーススキーマ
-- Linux Management System v0.3
--
-- 対象DB: SQLite (将来 PostgreSQL 移行を考慮)
-- 作成日: 2026-02-14
-- ============================================================

-- ============================================================
-- 1. approval_policies: 承認ポリシー定義（静的データ）
-- ============================================================
-- 承認が必要な操作種別とそのルールを定義する。
-- このテーブルの変更は管理者による手動操作のみ許可。

CREATE TABLE IF NOT EXISTS approval_policies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_type  VARCHAR(50)  NOT NULL UNIQUE,
    description     VARCHAR(200) NOT NULL,
    approval_required BOOLEAN    NOT NULL DEFAULT 1,
    approver_roles  TEXT         NOT NULL,  -- JSON配列: ["Approver", "Admin"]
    approval_count  INTEGER      NOT NULL DEFAULT 1,
    timeout_hours   INTEGER      NOT NULL DEFAULT 24,
    auto_execute    BOOLEAN      NOT NULL DEFAULT 0,
    risk_level      VARCHAR(10)  NOT NULL DEFAULT 'HIGH',
    created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 制約
    CONSTRAINT chk_risk_level CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    CONSTRAINT chk_approval_count CHECK (approval_count >= 1 AND approval_count <= 10),
    CONSTRAINT chk_timeout_hours CHECK (timeout_hours >= 1 AND timeout_hours <= 168)
);


-- ============================================================
-- 2. approval_requests: 承認リクエスト（動的データ）
-- ============================================================
-- 個別の承認申請を管理する。

CREATE TABLE IF NOT EXISTS approval_requests (
    id                VARCHAR(36)  PRIMARY KEY,  -- UUID v4
    request_type      VARCHAR(50)  NOT NULL,
    requester_id      VARCHAR(50)  NOT NULL,
    requester_name    VARCHAR(100) NOT NULL,
    request_payload   TEXT         NOT NULL,      -- JSON
    reason            TEXT         NOT NULL,
    status            VARCHAR(20)  NOT NULL DEFAULT 'pending',
    created_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at        TIMESTAMP    NOT NULL,
    approved_by       VARCHAR(50)  NULL,
    approved_by_name  VARCHAR(100) NULL,
    approved_at       TIMESTAMP    NULL,
    rejection_reason  TEXT         NULL,
    execution_result  TEXT         NULL,          -- JSON
    executed_at       TIMESTAMP    NULL,
    executed_by       VARCHAR(50)  NULL,

    -- 制約
    CONSTRAINT chk_status CHECK (
        status IN (
            'pending',
            'approved',
            'rejected',
            'expired',
            'executed',
            'execution_failed',
            'cancelled'
        )
    ),
    -- 自己承認防止（DB レベル）
    CONSTRAINT chk_not_self_approval CHECK (
        approved_by IS NULL OR approved_by != requester_id
    )
);


-- ============================================================
-- 3. approval_history: 承認履歴（追記専用、改ざん防止）
-- ============================================================
-- 全アクションを追記専用で記録する監査テーブル。
-- このテーブルに対する DELETE / UPDATE は禁止。
-- アプリケーション層で強制する。

CREATE TABLE IF NOT EXISTS approval_history (
    id                    INTEGER     PRIMARY KEY AUTOINCREMENT,
    approval_request_id   VARCHAR(36) NOT NULL,
    action                VARCHAR(30) NOT NULL,
    actor_id              VARCHAR(50) NOT NULL,
    actor_name            VARCHAR(100) NOT NULL,
    actor_role            VARCHAR(20) NOT NULL,
    timestamp             TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    details               TEXT        NULL,      -- JSON
    previous_status       VARCHAR(20) NULL,
    new_status            VARCHAR(20) NULL,
    signature             VARCHAR(64) NOT NULL,  -- HMAC-SHA256 (64 hex chars)

    -- 制約
    CONSTRAINT chk_action CHECK (
        action IN (
            'created',
            'approved',
            'rejected',
            'expired',
            'executed',
            'execution_failed',
            'cancelled'
        )
    ),
    CONSTRAINT chk_actor_role CHECK (
        actor_role IN ('Viewer', 'Operator', 'Approver', 'Admin', 'System')
    ),
    -- 外部キー
    CONSTRAINT fk_approval_request
        FOREIGN KEY (approval_request_id)
        REFERENCES approval_requests(id)
        ON DELETE RESTRICT  -- 削除禁止
);


-- ============================================================
-- 4. インデックス
-- ============================================================

-- approval_requests 検索最適化
CREATE INDEX IF NOT EXISTS idx_approval_requests_status
    ON approval_requests(status);

CREATE INDEX IF NOT EXISTS idx_approval_requests_requester
    ON approval_requests(requester_id);

CREATE INDEX IF NOT EXISTS idx_approval_requests_type_status
    ON approval_requests(request_type, status);

CREATE INDEX IF NOT EXISTS idx_approval_requests_expires
    ON approval_requests(expires_at);

CREATE INDEX IF NOT EXISTS idx_approval_requests_created
    ON approval_requests(created_at DESC);

-- approval_history 検索最適化
CREATE INDEX IF NOT EXISTS idx_approval_history_request
    ON approval_history(approval_request_id);

CREATE INDEX IF NOT EXISTS idx_approval_history_actor
    ON approval_history(actor_id);

CREATE INDEX IF NOT EXISTS idx_approval_history_timestamp
    ON approval_history(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_approval_history_action
    ON approval_history(action);


-- ============================================================
-- 5. 初期データ: 承認ポリシー（v0.3 allowlist）
-- ============================================================

INSERT OR IGNORE INTO approval_policies
    (operation_type, description, approval_required, approver_roles, approval_count, timeout_hours, auto_execute, risk_level)
VALUES
    -- ユーザー管理
    ('user_add',
     'ユーザーアカウント追加',
     1,
     '["Approver", "Admin"]',
     1,
     24,
     0,
     'HIGH'),

    ('user_delete',
     'ユーザーアカウント削除',
     1,
     '["Admin"]',
     1,
     12,  -- 短縮: 24h → 12h（users-planner推奨）
     0,
     'CRITICAL'),

    ('user_modify',
     'ユーザーアカウント変更（グループ、シェル等）',
     1,
     '["Approver", "Admin"]',
     1,
     24,
     0,
     'HIGH'),

    ('user_passwd',
     'ユーザーパスワード変更',
     1,
     '["Approver", "Admin"]',
     1,
     4,  -- 短縮タイムアウト（迅速な反映のため）
     0,
     'HIGH'),

    -- グループ管理
    ('group_add',
     'グループ追加',
     1,
     '["Approver", "Admin"]',
     1,
     24,
     0,
     'MEDIUM'),

    ('group_delete',
     'グループ削除',
     1,
     '["Admin"]',
     1,
     12,  -- 短縮: 24h → 12h（users-planner推奨）
     0,
     'HIGH'),

    ('group_modify',
     'グループメンバーシップ変更',
     1,
     '["Approver", "Admin"]',
     1,
     24,
     0,
     'HIGH'),

    -- Cronジョブ管理
    ('cron_add',
     'Cronジョブ追加',
     1,
     '["Approver", "Admin"]',
     1,
     24,
     0,
     'HIGH'),

    ('cron_delete',
     'Cronジョブ削除',
     1,
     '["Approver", "Admin"]',
     1,
     24,
     0,
     'HIGH'),

    ('cron_modify',
     'Cronジョブ変更（スケジュール、コマンド等）',
     1,
     '["Approver", "Admin"]',
     1,
     24,
     0,
     'HIGH'),

    -- サービス管理
    ('service_stop',
     'サービス停止（再起動ではなく完全停止）',
     1,
     '["Admin"]',
     1,
     12,
     0,
     'CRITICAL'),

    -- ファイアウォール管理
    ('firewall_modify',
     'ファイアウォールルール変更',
     1,
     '["Admin"]',
     1,
     24,
     0,
     'CRITICAL');


-- ============================================================
-- 6. サンプルデータ（開発環境テスト用）
-- ============================================================
-- 注意: 本番環境ではこのセクションを実行しないこと

-- サンプル承認リクエスト #1: pending
INSERT OR IGNORE INTO approval_requests
    (id, request_type, requester_id, requester_name, request_payload, reason, status, created_at, expires_at)
VALUES
    ('sample-0001-aaaa-bbbb-ccccddddeeee',
     'user_add',
     'user_002',
     'operator',
     '{"username": "testuser1", "group": "developers", "home": "/home/testuser1", "shell": "/bin/bash"}',
     'テスト用ユーザーアカウント作成（開発プロジェクト参加のため）',
     'pending',
     datetime('now'),
     datetime('now', '+24 hours'));

-- サンプル承認リクエスト #2: approved
INSERT OR IGNORE INTO approval_requests
    (id, request_type, requester_id, requester_name, request_payload, reason, status, created_at, expires_at, approved_by, approved_by_name, approved_at)
VALUES
    ('sample-0002-aaaa-bbbb-ccccddddeeee',
     'cron_add',
     'user_002',
     'operator',
     '{"schedule": "0 2 * * *", "command": "adminui-backup", "description": "Daily backup"}',
     'バックアップ用Cronジョブの追加',
     'approved',
     datetime('now', '-2 hours'),
     datetime('now', '+22 hours'),
     'user_003',
     'admin',
     datetime('now', '-1 hour'));

-- サンプル承認リクエスト #3: rejected
INSERT OR IGNORE INTO approval_requests
    (id, request_type, requester_id, requester_name, request_payload, reason, status, created_at, expires_at, approved_by, approved_by_name, approved_at, rejection_reason)
VALUES
    ('sample-0003-aaaa-bbbb-ccccddddeeee',
     'user_delete',
     'user_002',
     'operator',
     '{"username": "olduser"}',
     '退職者アカウントの削除',
     'rejected',
     datetime('now', '-3 hours'),
     datetime('now', '+21 hours'),
     'user_003',
     'admin',
     datetime('now', '-2 hours'),
     '退職処理がまだ完了していません。人事部門の確認が必要です。');

-- サンプル承認リクエスト #4: expired
INSERT OR IGNORE INTO approval_requests
    (id, request_type, requester_id, requester_name, request_payload, reason, status, created_at, expires_at)
VALUES
    ('sample-0004-aaaa-bbbb-ccccddddeeee',
     'group_add',
     'user_002',
     'operator',
     '{"groupname": "project-alpha"}',
     'プロジェクトAlphaのグループ作成',
     'expired',
     datetime('now', '-48 hours'),
     datetime('now', '-24 hours'));

-- サンプル承認履歴
INSERT OR IGNORE INTO approval_history
    (approval_request_id, action, actor_id, actor_name, actor_role, timestamp, details, previous_status, new_status, signature)
VALUES
    -- リクエスト #1 の作成
    ('sample-0001-aaaa-bbbb-ccccddddeeee',
     'created',
     'user_002',
     'operator',
     'Operator',
     datetime('now'),
     NULL,
     NULL,
     'pending',
     'sample_signature_placeholder_0001'),

    -- リクエスト #2 の作成
    ('sample-0002-aaaa-bbbb-ccccddddeeee',
     'created',
     'user_002',
     'operator',
     'Operator',
     datetime('now', '-2 hours'),
     NULL,
     NULL,
     'pending',
     'sample_signature_placeholder_0002a'),

    -- リクエスト #2 の承認
    ('sample-0002-aaaa-bbbb-ccccddddeeee',
     'approved',
     'user_003',
     'admin',
     'Admin',
     datetime('now', '-1 hour'),
     '{"comment": "確認しました。承認します。"}',
     'pending',
     'approved',
     'sample_signature_placeholder_0002b'),

    -- リクエスト #3 の作成
    ('sample-0003-aaaa-bbbb-ccccddddeeee',
     'created',
     'user_002',
     'operator',
     'Operator',
     datetime('now', '-3 hours'),
     NULL,
     NULL,
     'pending',
     'sample_signature_placeholder_0003a'),

    -- リクエスト #3 の拒否
    ('sample-0003-aaaa-bbbb-ccccddddeeee',
     'rejected',
     'user_003',
     'admin',
     'Admin',
     datetime('now', '-2 hours'),
     '{"reason": "退職処理がまだ完了していません。"}',
     'pending',
     'rejected',
     'sample_signature_placeholder_0003b'),

    -- リクエスト #4 の作成
    ('sample-0004-aaaa-bbbb-ccccddddeeee',
     'created',
     'user_002',
     'operator',
     'Operator',
     datetime('now', '-48 hours'),
     NULL,
     NULL,
     'pending',
     'sample_signature_placeholder_0004a'),

    -- リクエスト #4 の期限切れ
    ('sample-0004-aaaa-bbbb-ccccddddeeee',
     'expired',
     'system',
     'system',
     'System',
     datetime('now', '-24 hours'),
     '{"reason": "Approval request timed out after 24 hours"}',
     'pending',
     'expired',
     'sample_signature_placeholder_0004b');


-- ============================================================
-- 7. ビュー（便利なクエリ）
-- ============================================================

-- 承認待ち一覧ビュー
CREATE VIEW IF NOT EXISTS v_pending_approvals AS
SELECT
    r.id,
    r.request_type,
    p.description AS request_type_description,
    p.risk_level,
    r.requester_id,
    r.requester_name,
    r.reason,
    r.created_at,
    r.expires_at,
    ROUND(
        (JULIANDAY(r.expires_at) - JULIANDAY('now')) * 24,
        1
    ) AS remaining_hours
FROM approval_requests r
JOIN approval_policies p ON r.request_type = p.operation_type
WHERE r.status = 'pending'
  AND r.expires_at > datetime('now')
ORDER BY r.expires_at ASC;

-- 承認統計ビュー
CREATE VIEW IF NOT EXISTS v_approval_stats AS
SELECT
    COUNT(*)                                                AS total_requests,
    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END)    AS pending_count,
    SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END)   AS approved_count,
    SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END)   AS rejected_count,
    SUM(CASE WHEN status = 'expired' THEN 1 ELSE 0 END)    AS expired_count,
    SUM(CASE WHEN status = 'executed' THEN 1 ELSE 0 END)   AS executed_count,
    SUM(CASE WHEN status = 'execution_failed' THEN 1 ELSE 0 END) AS execution_failed_count,
    SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END)  AS cancelled_count,
    ROUND(
        CAST(SUM(CASE WHEN status IN ('approved', 'executed') THEN 1 ELSE 0 END) AS REAL)
        / NULLIF(SUM(CASE WHEN status != 'pending' THEN 1 ELSE 0 END), 0)
        * 100,
        1
    ) AS approval_rate_pct
FROM approval_requests;

-- リクエスト種別別統計ビュー
CREATE VIEW IF NOT EXISTS v_approval_stats_by_type AS
SELECT
    request_type,
    COUNT(*) AS total,
    SUM(CASE WHEN status IN ('approved', 'executed') THEN 1 ELSE 0 END) AS approved,
    SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected,
    SUM(CASE WHEN status = 'expired' THEN 1 ELSE 0 END) AS expired
FROM approval_requests
GROUP BY request_type
ORDER BY total DESC;


-- ============================================================
-- 注記
-- ============================================================
--
-- 1. SQLite ではトリガーを使用して approval_history の
--    UPDATE/DELETE を防止することを推奨:
--
-- CREATE TRIGGER prevent_history_update
-- BEFORE UPDATE ON approval_history
-- BEGIN
--     SELECT RAISE(ABORT, 'approval_history is append-only: UPDATE is prohibited');
-- END;
--
-- CREATE TRIGGER prevent_history_delete
-- BEFORE DELETE ON approval_history
-- BEGIN
--     SELECT RAISE(ABORT, 'approval_history is append-only: DELETE is prohibited');
-- END;
--
-- 2. PostgreSQL 移行時は以下を変更:
--    - INTEGER PRIMARY KEY AUTOINCREMENT -> SERIAL/BIGSERIAL
--    - VARCHAR(36) for UUID -> UUID 型
--    - datetime() 関数 -> NOW() / INTERVAL
--    - JULIANDAY() -> EXTRACT(EPOCH FROM ...)
--    - TEXT for JSON -> JSONB 型
--
-- 3. 本番環境では必ず以下を実施:
--    - サンプルデータ（セクション6）は投入しない
--    - HMAC 秘密鍵を安全に管理（環境変数経由）
--    - 定期的なバックアップ設定
--    - WAL モード有効化: PRAGMA journal_mode=WAL;
