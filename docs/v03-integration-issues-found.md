# v0.3設計 統合レビュー - 発見された不整合と修正計画

**発見日**: 2026-02-14
**発見者**: cron-planner (v03-planning-team)
**重要度**: CRITICAL 1件、HIGH 2件、MEDIUM 2件

---

## 1. operation_type の不整合（HIGH）

### 問題点

| operation_type | approval-architect | users-planner | 状態 |
|---|---|---|---|
| user_passwd | ❌ 未定義 | ✅ 使用 | **不整合** |
| group_modify | ❌ 未定義 | ✅ 使用 | **不整合** |
| user_modify | ✅ 定義済 | ❌ 未使用 | **未使用** |

### 影響
- users-plannerが`user_passwd`でリクエスト作成 → approval_policiesに定義なし → エラー

### 修正案（推奨）
**approval-schema.sql の初期データに追加**:
```sql
INSERT INTO approval_policies (operation_type, description, approval_required, approver_roles, approval_count, timeout_hours, auto_execute, risk_level)
VALUES
  ('user_passwd', 'ユーザーパスワード変更', 1, '["Approver", "Admin"]', 1, 4, 0, 'HIGH'),
  ('group_modify', 'グループメンバーシップ変更', 1, '["Approver", "Admin"]', 1, 24, 0, 'HIGH');
```

**修正ファイル**: `docs/database/approval-schema.sql`

---

## 2. sudoersサービスユーザー名の不整合（CRITICAL）

### 問題点
- **cron-planner**: `svc-adminui` を明示
- **users-planner**: サービスユーザー名未明示

### 影響
- 実装時にどのユーザー名を使うか不明
- sudoers設定が不完全

### 修正案（推奨）
**サービスユーザー名を `svc-adminui` に統一**:

1. users-groups-design.md にsudoersセクションを追加:
```bash
# /etc/sudoers.d/adminui-users
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-user-list.sh
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-user-add.sh
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-user-delete.sh
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-user-passwd.sh
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-group-*.sh
```

2. CLAUDE.md または README.md に明記:
```
システム実行ユーザー: svc-adminui
```

**修正ファイル**:
- `docs/architecture/users-groups-design.md`
- `CLAUDE.md`（サービスユーザー名の明記）

---

## 3. FORBIDDEN_CHARS の範囲差（HIGH）

### 問題点

| モジュール | FORBIDDEN_CHARS | 文字数 |
|---|---|---|
| CLAUDE.md（基準） | `;|&$()` ><*?{}[]` | 15文字 |
| cron-planner | `;|&$()` ><{}[]` | 13文字（`*?`欠落） |
| users-planner | `;|&$()` ><*?{}\[\]\\\'\"\\n\\r\\t\\0` | 21文字（拡張版） |

### 影響
- cron-plannerで`*`や`?`を含むコマンド引数が誤って許可される可能性

### 修正案（推奨）
**users-plannerの拡張版（21文字）を全モジュール共通に採用**:

```python
# backend/core/validation.py (新規作成)
FORBIDDEN_CHARS = r'[;|&$()` ><*?{}\[\]\\\'\"\\n\\r\\t\\0]'
FORBIDDEN_CHARS_LIST = [';', '|', '&', '$', '(', ')', '`', ' ', '>', '<', '*', '?', '{', '}', '[', ']', '\\', "'", '"', '\n', '\r', '\t', '\0']

def validate_no_forbidden_chars(value: str, field_name: str = "input") -> None:
    """禁止文字チェック"""
    for char in FORBIDDEN_CHARS_LIST:
        if char in value:
            raise ValueError(f"{field_name} contains forbidden character: {repr(char)}")
```

**修正ファイル**:
- `backend/core/validation.py`（新規作成）
- `docs/architecture/cron-jobs-design.md`（FORBIDDEN_CHARSを21文字に更新）

---

## 4. タイムアウト値の不一致（MEDIUM）

### 問題点

| operation_type | approval_policies | users-planner設計 |
|---|---|---|
| user_delete | 24h | 12h |
| user_passwd | (未定義) | 4h |
| group_delete | 24h | 12h |

### 影響
- users-plannerの短縮タイムアウト（合理的）がapproval_policiesに反映されていない

### 修正案（推奨）
**approval-schema.sql の初期データを更新**:
```sql
-- user_delete のtimeoutを12hに短縮
UPDATE approval_policies SET timeout_hours = 12 WHERE operation_type = 'user_delete';

-- group_delete のtimeoutを12hに短縮
UPDATE approval_policies SET timeout_hours = 12 WHERE operation_type = 'group_delete';

-- user_passwd を追加（timeout 4h）
INSERT INTO approval_policies (..., timeout_hours, ...) VALUES (..., 4, ...);
```

**修正ファイル**: `docs/database/approval-schema.sql`

---

## 5. 禁止ユーザーリストの粒度差（MEDIUM）

### 問題点
- **users-planner**: 100+件の詳細な禁止リスト
- **cron-planner**: 7件の基本リスト

### 影響
- cronモジュールでサービスアカウント（postgres, mysql等）へのcron追加が許可される可能性

### 修正案（推奨）
**共通の禁止ユーザーリストを定義**:

```python
# backend/core/constants.py (新規作成)
FORBIDDEN_USERNAMES = [
    # System critical
    'root', 'bin', 'daemon', 'sys', 'sync', 'games', 'man', 'lp',
    # ... （users-plannerの100+件リストを使用）
]
```

**修正ファイル**:
- `backend/core/constants.py`（新規作成）
- `docs/architecture/cron-jobs-design.md`（共通定数を参照）

---

## 修正優先度と実施計画

| # | 問題 | 重要度 | 修正ファイル | 推定時間 |
|---|------|--------|------------|---------|
| 1 | sudoersサービスユーザー名 | 🔴 CRITICAL | users-groups-design.md, CLAUDE.md | 5分 |
| 2 | operation_type 追加 | 🟠 HIGH | approval-schema.sql | 5分 |
| 3 | FORBIDDEN_CHARS 統一 | 🟠 HIGH | cron-jobs-design.md, validation.py新規 | 10分 |
| 4 | タイムアウト値反映 | 🟡 MEDIUM | approval-schema.sql | 5分 |
| 5 | 禁止ユーザーリスト共通化 | 🟡 MEDIUM | constants.py新規, cron-jobs-design.md | 10分 |

**推定修正時間**: 35分

---

## 推奨アクション

### Option A: 今すぐ修正（推奨）
設計フェーズで完全な整合性を確保してから実装フェーズに移行。修正は35分で完了可能。

### Option B: 実装フェーズで修正
実装開始後、最初のPhaseで修正。ただし、設計の手戻りが発生する可能性。

**推奨**: Option A（今すぐ修正）

---

**作成者**: cron-planner (発見者) → team-lead (整理)
**作成日**: 2026-02-14 16:00
