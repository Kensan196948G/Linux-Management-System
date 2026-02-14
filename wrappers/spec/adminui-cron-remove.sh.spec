# adminui-cron-remove.sh - ラッパースクリプト仕様書

**作成日**: 2026-02-14
**作成者**: cron-planner (v03-planning-team)
**ステータス**: 仕様段階（実装前）

---

## 概要

ユーザーのcrontabから指定されたジョブを削除（コメントアウト）するラッパースクリプト。
物理削除ではなくコメントアウト方式を採用し、復元可能性を確保する。

## 基本情報

| 項目 | 値 |
|------|-----|
| スクリプト名 | adminui-cron-remove.sh |
| 配置先 | /usr/local/sbin/adminui-cron-remove.sh |
| 呼び出し | `sudo /usr/local/sbin/adminui-cron-remove.sh <username> <line_number>` |
| root権限 | 必要（crontab -u による他ユーザー操作） |
| 危険度 | MEDIUM（crontab変更） |
| タイムアウト | 15秒 |

## 引数

| # | 引数 | 必須 | 検証ルール | 例 |
|---|------|------|-----------|-----|
| 1 | username | Yes | `^[a-z_][a-z0-9_-]{0,31}$` | `svc-adminui` |
| 2 | line_number | Yes | `^[1-9][0-9]{0,3}$` (1-9999) | `3` |

## セキュリティ要件

### 入力検証

1. **引数数チェック**: 正確に2個
2. **ユーザー名検証**: パターン照合 + 禁止ユーザー + 存在確認
3. **行番号検証**:
   - 正の整数（1以上）
   - crontab内の有効行番号であること
   - コメント行やシステム行（MAILTO等）でないこと

### 削除方式

**物理削除ではなくコメントアウト方式**を採用:

```
# 変更前:
0 2 * * * /usr/bin/rsync -avz /data /backup

# 変更後:
# [DISABLED by adminui 2026-02-14T10:30:00Z caller=admin] 0 2 * * * /usr/bin/rsync -avz /data /backup
```

**理由**:
- 誤操作時の復元が容易
- 監査証跡としてcrontab内に記録が残る
- 承認フローの一部として変更履歴を保持

## 正常系出力

### 削除（コメントアウト）成功

```json
{
  "status": "success",
  "message": "Cron job disabled (commented out)",
  "user": "svc-adminui",
  "removed_job": {
    "line_number": 3,
    "schedule": "0 2 * * *",
    "command": "/usr/bin/rsync",
    "arguments": "-avz /data /backup/data"
  },
  "remaining_jobs": 2
}
```

## 異常系出力

### 行番号不正

```json
{"status": "error", "code": "INVALID_LINE_NUMBER", "message": "Invalid line number: 0"}
```

### 行番号範囲外

```json
{"status": "error", "code": "LINE_NOT_FOUND", "message": "Line 99 does not exist (total lines: 5)"}
```

### 既にコメントアウト済み

```json
{"status": "error", "code": "ALREADY_DISABLED", "message": "Line 3 is already disabled"}
```

### コメント行の削除試行

```json
{"status": "error", "code": "NOT_A_JOB", "message": "Line 1 is a comment or system directive, not a cron job"}
```

## 実装要件

```bash
#!/bin/bash
set -euo pipefail

# 1. 引数チェック (正確に2個)
# 2. ユーザー名検証
#    a. パターン照合
#    b. 禁止ユーザーチェック
#    c. 存在確認
# 3. 行番号検証
#    a. 正の整数チェック
#    b. 範囲チェック
# 4. crontab取得
# 5. 指定行の検証
#    a. 行の存在確認
#    b. コメント行でないこと
#    c. システム行（MAILTO, SHELL等）でないこと
# 6. コメントアウト処理
#    a. タイムスタンプと操作者を含むコメントプレフィクス追加
# 7. 一時ファイルに書き出し（安全なmktemp使用）
# 8. crontab -u "$USER" に設定
# 9. 一時ファイルの安全な削除
# 10. 成功JSON出力
```

## ログ要件

```
[INFO]  Cron remove requested: user=svc-adminui, line=3, caller=admin
[INFO]  Cron remove successful: user=svc-adminui, line=3, command=/usr/bin/rsync
[ERROR] Line 99 not found in crontab for user=svc-adminui
[ERROR] Line 1 is not a cron job (comment/system directive)
```

## テストケース

| # | テスト | 入力 | 期待結果 |
|---|--------|------|---------|
| 1 | 正常: ジョブ削除 | `user 3` | success, コメントアウト |
| 2 | 異常: 行番号0 | `user 0` | INVALID_LINE_NUMBER |
| 3 | 異常: 行番号負数 | `user -1` | INVALID_LINE_NUMBER |
| 4 | 異常: 行番号超過 | `user 99` | LINE_NOT_FOUND |
| 5 | 異常: コメント行 | `user 1` (コメント行) | NOT_A_JOB |
| 6 | 異常: 既にコメントアウト | `user 3` (既に無効) | ALREADY_DISABLED |
| 7 | 異常: root | `root 3` | FORBIDDEN_USER |
| 8 | 異常: 特殊文字 | `user;ls 3` | INVALID_USERNAME |
| 9 | 異常: crontab未設定 | `newuser 1` | LINE_NOT_FOUND |
| 10 | 異常: 引数不足 | `user` | INVALID_ARGS |

## sudoers設定

```
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-cron-remove.sh
```

---

**最終更新**: 2026-02-14
