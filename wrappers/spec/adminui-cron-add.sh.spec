# adminui-cron-add.sh - ラッパースクリプト仕様書

**作成日**: 2026-02-14
**作成者**: cron-planner (v03-planning-team)
**ステータス**: 仕様段階（実装前）

---

## 概要

ユーザーのcrontabに新しいジョブを追加するラッパースクリプト。
allowlist検証、ジョブ数制限、スケジュール検証を実施する。

## 基本情報

| 項目 | 値 |
|------|-----|
| スクリプト名 | adminui-cron-add.sh |
| 配置先 | /usr/local/sbin/adminui-cron-add.sh |
| 呼び出し | `sudo /usr/local/sbin/adminui-cron-add.sh <username> <schedule> <command> [arguments] [comment]` |
| root権限 | 必要（crontab -u による他ユーザー操作） |
| 危険度 | MEDIUM（crontab書き込み） |
| タイムアウト | 15秒 |

## 引数

| # | 引数 | 必須 | 検証ルール | 例 |
|---|------|------|-----------|-----|
| 1 | username | Yes | `^[a-z_][a-z0-9_-]{0,31}$` | `svc-adminui` |
| 2 | schedule | Yes | Cron式 (5フィールド) | `"0 2 * * *"` |
| 3 | command | Yes | 絶対パス、allowlist内 | `/usr/bin/rsync` |
| 4 | arguments | No | 禁止文字なし、最大512文字 | `-avz /data /backup` |
| 5 | comment | No | 最大256文字 | `Daily backup` |

## セキュリティ要件

### 入力検証（多重防御）

1. **引数数チェック**: 3〜5個
2. **ユーザー名検証**: パターン照合 + 禁止ユーザー + 存在確認
3. **スケジュール検証**:
   - 5フィールド形式
   - 各フィールドの範囲チェック
   - 最小実行間隔（5分以上）
   - 禁止文字なし
4. **コマンド検証**:
   - 絶対パス必須（`/` で開始）
   - allowlist照合（完全一致）
   - `realpath` で正規化して再照合（symlink対策）
   - 禁止コマンドリスト照合
5. **引数検証**:
   - 禁止文字（`;|&$()` 等）の拒否
   - コマンド固有の禁止引数パターン照合
   - パストラバーサル（`..`）の拒否
   - 長さ制限（512文字）
6. **ジョブ数制限**: ユーザーあたり最大10個

### Allowlist（ラッパー内で再定義）

```bash
ALLOWED_COMMANDS=(
    "/usr/bin/rsync"
    "/usr/local/bin/healthcheck.sh"
    "/usr/bin/find"
    "/usr/bin/tar"
    "/usr/bin/gzip"
    "/usr/bin/curl"
    "/usr/bin/wget"
    "/usr/bin/python3"
    "/usr/bin/node"
)
```

### 禁止コマンド

```bash
FORBIDDEN_COMMANDS=(
    "/bin/bash" "/bin/sh" "/bin/zsh" "/bin/dash"
    "/usr/bin/bash" "/usr/bin/sh"
    "/bin/rm" "/usr/bin/rm"
    "/sbin/reboot" "/sbin/shutdown"
    "/usr/bin/sudo" "/usr/sbin/visudo"
    "/usr/bin/chmod" "/usr/bin/chown"
)
```

## 正常系出力

### 追加成功

```json
{
  "status": "success",
  "message": "Cron job added successfully",
  "user": "svc-adminui",
  "job": {
    "schedule": "0 2 * * *",
    "command": "/usr/bin/rsync",
    "arguments": "-avz /data /backup/data",
    "comment": "Daily data backup"
  },
  "total_jobs": 4
}
```

## 異常系出力

### allowlist外コマンド

```json
{"status": "error", "code": "COMMAND_NOT_ALLOWED", "message": "Command not in allowlist: /tmp/evil.sh"}
```

### 禁止コマンド

```json
{"status": "error", "code": "FORBIDDEN_COMMAND", "message": "Forbidden command: /bin/bash"}
```

### ジョブ数上限超過

```json
{"status": "error", "code": "MAX_JOBS_EXCEEDED", "message": "Maximum 10 cron jobs per user (current: 10)"}
```

### スケジュール不正

```json
{"status": "error", "code": "INVALID_SCHEDULE", "message": "Execution interval too short: */2 (minimum: */5)"}
```

### 禁止文字検出

```json
{"status": "error", "code": "FORBIDDEN_CHARS", "message": "Forbidden character detected in arguments: ;"}
```

### パストラバーサル検出

```json
{"status": "error", "code": "PATH_TRAVERSAL", "message": "Path traversal detected in arguments"}
```

### 重複ジョブ

```json
{"status": "error", "code": "DUPLICATE_JOB", "message": "Identical cron job already exists"}
```

## 実装要件

```bash
#!/bin/bash
set -euo pipefail

# 1. 引数数チェック (3-5個)
# 2. ユーザー名検証
#    a. パターン照合
#    b. 禁止ユーザーチェック
#    c. 存在確認 (id -u)
# 3. スケジュール検証
#    a. 5フィールドチェック
#    b. 各フィールド範囲チェック
#    c. 最小間隔チェック (5分)
# 4. コマンド検証
#    a. 絶対パスチェック
#    b. 禁止コマンドチェック
#    c. allowlistチェック
#    d. realpath正規化 + 再チェック
#    e. ファイル存在・実行可能確認
# 5. 引数検証（存在する場合）
#    a. 禁止文字チェック
#    b. パストラバーサルチェック
#    c. 長さチェック
# 6. ジョブ数チェック
#    a. 現在のジョブ数取得
#    b. MAX_JOBS (10) との比較
# 7. 重複チェック
# 8. 一時ファイルにcrontab書き出し（安全なmktemp使用）
# 9. 新しいエントリ追記
# 10. crontab -u "$USER" に設定
# 11. 一時ファイルの安全な削除 (trap)
# 12. 成功JSON出力
```

### 一時ファイルの安全な取り扱い

```bash
# 安全な一時ファイル作成
TMPFILE=$(mktemp /tmp/adminui-cron-XXXXXX)
trap 'rm -f "$TMPFILE"' EXIT

# パーミッション制限
chmod 600 "$TMPFILE"
```

## ログ要件

```
[INFO]  Cron add requested: user=svc-adminui, schedule="0 2 * * *", command=/usr/bin/rsync, caller=admin
[INFO]  Cron add successful: user=svc-adminui, total_jobs=4
[ERROR] Command not in allowlist: /tmp/evil.sh (caller=operator1)
[SECURITY] Forbidden command attempted: /bin/bash (caller=operator1)
[SECURITY] Forbidden character in arguments: ; (caller=operator1)
[SECURITY] Path traversal detected in arguments (caller=operator1)
```

## テストケース

| # | テスト | 入力 | 期待結果 |
|---|--------|------|---------|
| 1 | 正常: 基本追加 | `user "0 2 * * *" /usr/bin/rsync` | success |
| 2 | 正常: 引数付き | `user "0 2 * * *" /usr/bin/rsync "-avz /data /backup"` | success |
| 3 | 正常: コメント付き | `user "0 2 * * *" /usr/bin/rsync "-avz" "backup"` | success |
| 4 | 異常: allowlist外 | `user "0 2 * * *" /tmp/evil.sh` | COMMAND_NOT_ALLOWED |
| 5 | 異常: 禁止コマンド | `user "0 2 * * *" /bin/bash` | FORBIDDEN_COMMAND |
| 6 | 異常: 高頻度 | `user "* * * * *" /usr/bin/rsync` | INVALID_SCHEDULE |
| 7 | 異常: root | `root "0 2 * * *" /usr/bin/rsync` | FORBIDDEN_USER |
| 8 | 異常: インジェクション | `user "0 2 * * *" /usr/bin/rsync "a; rm -rf /"` | FORBIDDEN_CHARS |
| 9 | 異常: パストラバーサル | `user "0 2 * * *" /usr/bin/rsync "-avz ../../etc"` | PATH_TRAVERSAL |
| 10 | 異常: 上限超過 | (11個目) | MAX_JOBS_EXCEEDED |
| 11 | 異常: 重複 | (同一ジョブ) | DUPLICATE_JOB |
| 12 | 異常: symlink攻撃 | `user "0 2 * * *" /usr/bin/rsync_symlink` | COMMAND_NOT_ALLOWED |
| 13 | 異常: 引数なしコマンド | `user "0 2 * * *" /usr/local/bin/healthcheck.sh "arg"` | ARGS_NOT_ALLOWED |

## sudoers設定

```
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-cron-add.sh
```

---

**最終更新**: 2026-02-14
