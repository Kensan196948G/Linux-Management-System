# データベース設計書

**文書番号**: WEBUI-DB-001
**バージョン**: 1.0
**作成日**: 2026-02-25
**対象システム**: Linux管理 WebUI サンプルシステム

---

## 1. データベース概要

| 項目 | 内容 |
|------|------|
| DBMS | SQLite 3.x（開発・小規模）/ PostgreSQL 15.x（本番推奨） |
| 文字セット | UTF-8 |
| タイムゾーン | UTC（表示時に JST 変換） |
| スキーマ名 | `adminui` |
| バックアップ方式 | 日次フルバックアップ（pg_dump / SQLite ファイルコピー） |

---

## 2. テーブル一覧

| テーブル名 | 説明 | 主要用途 |
|-----------|------|---------|
| `users` | WebUIユーザー情報 | 認証・認可 |
| `roles` | ロール定義 | 権限管理 |
| `sessions` | セッション管理 | JWT管理 |
| `audit_logs` | 操作監査ログ | 証跡管理 |
| `approvals` | 承認申請 | 承認フロー |
| `allowlist_services` | 操作許可サービス一覧 | 操作制限 |
| `system_settings` | システム設定 | 設定管理 |
| `notifications` | 通知履歴 | 通知管理 |

---

## 3. テーブル定義

### 3.1 users テーブル

```sql
CREATE TABLE users (
    id            INTEGER      PRIMARY KEY AUTOINCREMENT,
    username      VARCHAR(64)  NOT NULL UNIQUE,
    display_name  VARCHAR(128) NOT NULL,
    email         VARCHAR(256) NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,        -- bcrypt ハッシュ
    role_id       INTEGER      NOT NULL REFERENCES roles(id),
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    mfa_secret    VARCHAR(64),                  -- TOTP シークレット（暗号化保存）
    mfa_enabled   BOOLEAN      NOT NULL DEFAULT FALSE,
    failed_login  INTEGER      NOT NULL DEFAULT 0,
    locked_until  TIMESTAMP,
    last_login_at TIMESTAMP,
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by    INTEGER      REFERENCES users(id)
);

-- インデックス
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email    ON users(email);
CREATE INDEX idx_users_role_id  ON users(role_id);
```

| カラム | 型 | 制約 | 説明 |
|--------|-----|------|------|
| id | INTEGER | PK, AUTO | ユーザーID |
| username | VARCHAR(64) | UNIQUE, NOT NULL | ログインID |
| display_name | VARCHAR(128) | NOT NULL | 表示名 |
| email | VARCHAR(256) | UNIQUE, NOT NULL | メールアドレス |
| password_hash | VARCHAR(256) | NOT NULL | bcryptハッシュ |
| role_id | INTEGER | FK, NOT NULL | ロールID |
| is_active | BOOLEAN | NOT NULL | 有効フラグ |
| mfa_secret | VARCHAR(64) | - | TOTP秘密鍵（暗号化） |
| failed_login | INTEGER | NOT NULL | 連続失敗回数 |
| locked_until | TIMESTAMP | - | ロック解除日時 |

---

### 3.2 roles テーブル

```sql
CREATE TABLE roles (
    id          INTEGER     PRIMARY KEY AUTOINCREMENT,
    name        VARCHAR(32) NOT NULL UNIQUE,
    display_name VARCHAR(64) NOT NULL,
    level       INTEGER     NOT NULL,   -- 権限レベル（高いほど強力）
    description TEXT,
    created_at  TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 初期データ
INSERT INTO roles (name, display_name, level, description) VALUES
    ('viewer',   '閲覧者',     1, '参照のみ可能'),
    ('operator', 'オペレーター', 2, '限定操作可能'),
    ('approver', '承認者',     3, '危険操作の承認権限'),
    ('admin',    '管理者',     4, 'システム全権');
```

---

### 3.3 sessions テーブル

```sql
CREATE TABLE sessions (
    id            INTEGER      PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER      NOT NULL REFERENCES users(id),
    jti           VARCHAR(36)  NOT NULL UNIQUE,  -- JWT ID (UUID)
    ip_address    VARCHAR(45)  NOT NULL,
    user_agent    VARCHAR(512),
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at    TIMESTAMP    NOT NULL,
    revoked_at    TIMESTAMP,
    is_revoked    BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_sessions_user_id  ON sessions(user_id);
CREATE INDEX idx_sessions_jti      ON sessions(jti);
CREATE INDEX idx_sessions_expires  ON sessions(expires_at);
```

---

### 3.4 audit_logs テーブル（最重要）

```sql
CREATE TABLE audit_logs (
    id            INTEGER      PRIMARY KEY AUTOINCREMENT,
    timestamp     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id       INTEGER      REFERENCES users(id),
    username      VARCHAR(64)  NOT NULL,          -- 削除後も証跡保持
    role          VARCHAR(32)  NOT NULL,
    ip_address    VARCHAR(45)  NOT NULL,
    user_agent    VARCHAR(512),
    action        VARCHAR(128) NOT NULL,           -- 例: service.restart
    category      VARCHAR(32)  NOT NULL,           -- read / write / auth
    target_type   VARCHAR(64),                     -- service / user / log
    target_name   VARCHAR(256),                    -- nginx / user01 等
    parameters    TEXT,                            -- JSON 形式
    result        VARCHAR(16)  NOT NULL,           -- success / failure / denied
    exit_code     INTEGER,
    stdout        TEXT,
    stderr        TEXT,
    duration_ms   INTEGER,
    error_message TEXT
);

-- 注意: UPDATE / DELETE は禁止（追記専用）
-- インデックス
CREATE INDEX idx_audit_timestamp   ON audit_logs(timestamp);
CREATE INDEX idx_audit_user_id     ON audit_logs(user_id);
CREATE INDEX idx_audit_action      ON audit_logs(action);
CREATE INDEX idx_audit_result      ON audit_logs(result);
```

> **重要**: `audit_logs` テーブルへの UPDATE/DELETE は一切禁止。
> アプリケーション側でも INSERT 権限のみ付与する。

---

### 3.5 approvals テーブル

```sql
CREATE TABLE approvals (
    id              INTEGER      PRIMARY KEY AUTOINCREMENT,
    requester_id    INTEGER      NOT NULL REFERENCES users(id),
    approver_id     INTEGER      REFERENCES users(id),
    action          VARCHAR(128) NOT NULL,
    target_type     VARCHAR(64)  NOT NULL,
    target_name     VARCHAR(256) NOT NULL,
    parameters      TEXT,                     -- JSON
    reason          TEXT         NOT NULL,
    status          VARCHAR(16)  NOT NULL DEFAULT 'pending',
    -- pending / approved / rejected / expired / executed
    approval_token  VARCHAR(64)  UNIQUE,      -- 実行時使用
    comment         TEXT,                     -- 承認/却下コメント
    expires_at      TIMESTAMP,               -- 承認有効期限
    requested_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    responded_at    TIMESTAMP,
    executed_at     TIMESTAMP
);

CREATE INDEX idx_approvals_requester ON approvals(requester_id);
CREATE INDEX idx_approvals_status    ON approvals(status);
CREATE INDEX idx_approvals_token     ON approvals(approval_token);
```

---

### 3.6 allowlist_services テーブル

```sql
CREATE TABLE allowlist_services (
    id           INTEGER     PRIMARY KEY AUTOINCREMENT,
    service_name VARCHAR(128) NOT NULL UNIQUE,
    allow_restart BOOLEAN     NOT NULL DEFAULT TRUE,
    allow_start   BOOLEAN     NOT NULL DEFAULT FALSE,
    allow_stop    BOOLEAN     NOT NULL DEFAULT FALSE,
    requires_approval_for_stop BOOLEAN NOT NULL DEFAULT TRUE,
    description  TEXT,
    is_active    BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by   INTEGER     REFERENCES users(id)
);

-- 初期データ例
INSERT INTO allowlist_services (service_name, allow_restart, allow_start, allow_stop) VALUES
    ('nginx',        TRUE,  TRUE,  TRUE),
    ('apache2',      TRUE,  TRUE,  TRUE),
    ('mysql',        TRUE,  TRUE,  FALSE),
    ('postgresql',   TRUE,  TRUE,  FALSE),
    ('redis-server', TRUE,  TRUE,  TRUE),
    ('cron',         FALSE, FALSE, FALSE);
```

---

### 3.7 system_settings テーブル

```sql
CREATE TABLE system_settings (
    key         VARCHAR(128) PRIMARY KEY,
    value       TEXT         NOT NULL,
    description TEXT,
    updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by  INTEGER      REFERENCES users(id)
);

-- 初期設定例
INSERT INTO system_settings (key, value, description) VALUES
    ('session_timeout_minutes',  '30',   'セッションタイムアウト（分）'),
    ('max_login_failures',       '5',    'ログイン失敗許容回数'),
    ('lockout_duration_minutes', '15',   'アカウントロック時間（分）'),
    ('cpu_alert_threshold',      '85',   'CPU警告閾値（%）'),
    ('memory_alert_threshold',   '90',   'メモリ警告閾値（%）'),
    ('disk_alert_threshold',     '85',   'ディスク警告閾値（%）');
```

---

## 4. ER図（概要）

```
users ──── roles
  │
  ├── sessions
  ├── audit_logs
  ├── approvals (requester / approver)
  └── system_settings (updated_by)

allowlist_services  （users テーブルとは独立）
```

---

## 5. データ保管ポリシー

| データ種別 | 保管期間 | 削除方針 |
|-----------|---------|---------|
| 監査ログ（audit_logs） | 永久（最低1年） | 削除禁止 |
| セッション情報 | 有効期限+30日 | 期限切れ後バッチ削除 |
| 承認申請 | 1年 | 期限後アーカイブ |
| 通知履歴 | 90日 | バッチ削除 |

---

*本文書はLinux管理WebUIサンプルシステムのデータベース設計を定めるものである。*
