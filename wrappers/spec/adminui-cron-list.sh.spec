# adminui-cron-list.sh - ラッパースクリプト仕様書

**作成日**: 2026-02-14
**作成者**: cron-planner (v03-planning-team)
**ステータス**: 仕様段階（実装前）

---

## 概要

ユーザーのcrontabエントリを一覧取得し、JSON形式で出力するラッパースクリプト。

## 基本情報

| 項目 | 値 |
|------|-----|
| スクリプト名 | adminui-cron-list.sh |
| 配置先 | /usr/local/sbin/adminui-cron-list.sh |
| 呼び出し | `sudo /usr/local/sbin/adminui-cron-list.sh <username>` |
| root権限 | 必要（crontab -u による他ユーザー参照） |
| 危険度 | LOW（読み取り専用） |
| タイムアウト | 10秒 |

## 引数

| # | 引数 | 必須 | 検証ルール | 例 |
|---|------|------|-----------|-----|
| 1 | username | Yes | `^[a-z_][a-z0-9_-]{0,31}$` | `svc-adminui` |

## セキュリティ要件

### 入力検証

1. 引数数チェック: 正確に1個
2. ユーザー名パターン: `^[a-z_][a-z0-9_-]{0,31}$`
3. 禁止文字チェック: `;|&$()` 等
4. 禁止ユーザー: root, daemon, bin 等のシステムユーザー
5. ユーザー存在確認: `id -u "$USER"` で確認

### 出力サニタイゼーション

- コマンド引数内の機密情報パターンをマスク
- JSON出力のエスケープ処理

## 正常系出力

### crontabが存在する場合

```json
{
  "status": "success",
  "user": "svc-adminui",
  "jobs": [
    {
      "id": "cron_001",
      "line_number": 3,
      "schedule": "0 2 * * *",
      "command": "/usr/bin/rsync",
      "arguments": "-avz /data /backup/data",
      "comment": "Daily data backup",
      "enabled": true,
      "raw_line": "0 2 * * * /usr/bin/rsync -avz /data /backup/data # Daily data backup"
    }
  ],
  "total_count": 1,
  "max_allowed": 10
}
```

### crontabが存在しない場合

```json
{
  "status": "success",
  "user": "svc-adminui",
  "jobs": [],
  "total_count": 0,
  "max_allowed": 10
}
```

## 異常系出力

### 引数不正

```json
{"status": "error", "code": "INVALID_ARGS", "message": "Usage: adminui-cron-list.sh <username>"}
```

### ユーザー名不正

```json
{"status": "error", "code": "INVALID_USERNAME", "message": "Invalid username format"}
```

### 禁止ユーザー

```json
{"status": "error", "code": "FORBIDDEN_USER", "message": "System user not allowed: root"}
```

### ユーザー不存在

```json
{"status": "error", "code": "USER_NOT_FOUND", "message": "User does not exist: unknown_user"}
```

## 実装要件

```bash
#!/bin/bash
set -euo pipefail

# 1. 引数チェック (正確に1個)
# 2. ユーザー名パターン検証
# 3. 禁止文字チェック
# 4. 禁止ユーザーチェック
# 5. ユーザー存在確認 (id -u)
# 6. crontab -u "$USER" -l 実行
# 7. 出力のJSON変換
# 8. 機密情報のマスキング
# 9. JSON出力
```

## ログ要件

```
[INFO]  Cron list requested: user=svc-adminui, caller=admin
[INFO]  Cron list successful: user=svc-adminui, count=3
[ERROR] Invalid username: root (forbidden system user)
[SECURITY] Forbidden character detected: user=test;rm
```

## テストケース

| # | テスト | 入力 | 期待結果 |
|---|--------|------|---------|
| 1 | 正常: crontab存在 | `svc-adminui` | status=success, jobs=[...] |
| 2 | 正常: crontab未設定 | `newuser` | status=success, jobs=[] |
| 3 | 異常: 引数なし | (なし) | exit 1, INVALID_ARGS |
| 4 | 異常: 引数2個 | `user1 user2` | exit 1, INVALID_ARGS |
| 5 | 異常: root指定 | `root` | exit 1, FORBIDDEN_USER |
| 6 | 異常: 特殊文字 | `user;ls` | exit 1, INVALID_USERNAME |
| 7 | 異常: 存在しないユーザー | `nonexistent` | exit 1, USER_NOT_FOUND |
| 8 | 異常: 空文字 | `""` | exit 1, INVALID_USERNAME |
| 9 | 異常: 長すぎる名前 | `a` x 100 | exit 1, INVALID_USERNAME |

## sudoers設定

```
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-cron-list.sh
```

---

**最終更新**: 2026-02-14
