# adminui-cron-toggle.sh - ラッパースクリプト仕様書

**作成日**: 2026-02-14
**作成者**: cron-planner (v03-planning-team)
**ステータス**: 仕様段階（実装前）

---

## 概要

ユーザーのcrontab内の指定ジョブを有効化/無効化（コメントアウト/コメント解除）するラッパースクリプト。

## 基本情報

| 項目 | 値 |
|------|-----|
| スクリプト名 | adminui-cron-toggle.sh |
| 配置先 | /usr/local/sbin/adminui-cron-toggle.sh |
| 呼び出し | `sudo /usr/local/sbin/adminui-cron-toggle.sh <username> <line_number> <enable|disable>` |
| root権限 | 必要（crontab -u による他ユーザー操作） |
| 危険度 | MEDIUM（crontab変更） |
| タイムアウト | 15秒 |

## 引数

| # | 引数 | 必須 | 検証ルール | 例 |
|---|------|------|-----------|-----|
| 1 | username | Yes | `^[a-z_][a-z0-9_-]{0,31}$` | `svc-adminui` |
| 2 | line_number | Yes | `^[1-9][0-9]{0,3}$` (1-9999) | `3` |
| 3 | action | Yes | `^(enable|disable)$` | `disable` |

## セキュリティ要件

### 入力検証

1. **引数数チェック**: 正確に3個
2. **ユーザー名検証**: パターン照合 + 禁止ユーザー + 存在確認
3. **行番号検証**: 正の整数 + crontab内の有効行
4. **アクション検証**: `enable` または `disable` のみ

### 有効化時の追加検証

ジョブを有効化（コメント解除）する場合、以下の追加検証を実施:

1. コメントアウトされたジョブであること（adminuiによるコメント形式）
2. 有効化後のジョブ数が上限（10個）以下であること
3. コマンドが現在のallowlistに含まれていること（allowlistが縮小された場合の対策）
4. スケジュールが現在の検証ルールを満たすこと

### コメント形式

```
# 無効化時:
# [DISABLED by adminui 2026-02-14T10:30:00Z caller=admin] 0 2 * * * /usr/bin/rsync -avz /data /backup

# 有効化時（コメントプレフィクスを除去）:
0 2 * * * /usr/bin/rsync -avz /data /backup
```

## 正常系出力

### 無効化成功

```json
{
  "status": "success",
  "message": "Cron job disabled",
  "user": "svc-adminui",
  "job": {
    "line_number": 3,
    "schedule": "0 2 * * *",
    "command": "/usr/bin/rsync",
    "enabled": false
  },
  "active_jobs": 2
}
```

### 有効化成功

```json
{
  "status": "success",
  "message": "Cron job enabled",
  "user": "svc-adminui",
  "job": {
    "line_number": 3,
    "schedule": "0 2 * * *",
    "command": "/usr/bin/rsync",
    "enabled": true
  },
  "active_jobs": 4
}
```

## 異常系出力

### 既に同じ状態

```json
{"status": "error", "code": "ALREADY_ENABLED", "message": "Job is already enabled"}
```

```json
{"status": "error", "code": "ALREADY_DISABLED", "message": "Job is already disabled"}
```

### 有効化時のallowlistチェック失敗

```json
{"status": "error", "code": "COMMAND_NOT_ALLOWED", "message": "Cannot re-enable: command /usr/bin/old-tool is no longer in allowlist"}
```

### 有効化時のジョブ数上限超過

```json
{"status": "error", "code": "MAX_JOBS_EXCEEDED", "message": "Cannot enable: maximum 10 active jobs (current: 10)"}
```

### アクション不正

```json
{"status": "error", "code": "INVALID_ACTION", "message": "Invalid action: restart (expected: enable or disable)"}
```

### adminui以外のコメント行

```json
{"status": "error", "code": "NOT_ADMINUI_COMMENT", "message": "Line 3 was not disabled by adminui (cannot re-enable unknown comments)"}
```

## 実装要件

```bash
#!/bin/bash
set -euo pipefail

# 1. 引数チェック (正確に3個)
# 2. ユーザー名検証
# 3. 行番号検証
# 4. アクション検証 (enable|disable のみ)
# 5. crontab取得
# 6. 指定行の取得・検証
#
# [disable の場合]
# 7a. ジョブ行であることを確認（コメント行でないこと）
# 8a. コメントアウト（タイムスタンプ + 操作者 プレフィクス追加）
#
# [enable の場合]
# 7b. adminuiコメント形式であることを確認
# 8b. コメントプレフィクスを除去してジョブ内容を取得
# 9b. コマンドのallowlist再検証
# 10b. スケジュールの再検証
# 11b. 有効ジョブ数の上限チェック
# 12b. コメント解除
#
# 13. 一時ファイルに書き出し
# 14. crontab -u "$USER" に設定
# 15. 一時ファイル削除
# 16. 成功JSON出力
```

## ログ要件

```
[INFO]  Cron toggle requested: user=svc-adminui, line=3, action=disable, caller=admin
[INFO]  Cron toggle successful: user=svc-adminui, line=3, action=disable
[ERROR] Cannot enable: command /usr/bin/old-tool not in current allowlist
[ERROR] Cannot enable: max jobs exceeded (current: 10, max: 10)
[ERROR] Line 3 is not an adminui-disabled comment
```

## テストケース

| # | テスト | 入力 | 期待結果 |
|---|--------|------|---------|
| 1 | 正常: 無効化 | `user 3 disable` | success, enabled=false |
| 2 | 正常: 有効化 | `user 3 enable` | success, enabled=true |
| 3 | 異常: 既に無効 | `user 3 disable` (既に無効) | ALREADY_DISABLED |
| 4 | 異常: 既に有効 | `user 3 enable` (既に有効) | ALREADY_ENABLED |
| 5 | 異常: 不正アクション | `user 3 restart` | INVALID_ACTION |
| 6 | 異常: 有効化時allowlist外 | `user 3 enable` (コマンドがallowlist外) | COMMAND_NOT_ALLOWED |
| 7 | 異常: 有効化時上限超過 | `user 3 enable` (10個アクティブ) | MAX_JOBS_EXCEEDED |
| 8 | 異常: 非adminuiコメント | `user 1 enable` (手動コメント) | NOT_ADMINUI_COMMENT |
| 9 | 異常: root | `root 3 disable` | FORBIDDEN_USER |
| 10 | 異常: 特殊文字 | `user;ls 3 disable` | INVALID_USERNAME |

## sudoers設定

```
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-cron-toggle.sh
```

---

**最終更新**: 2026-02-14
