# Cron Jobs モジュール - Allowlist ポリシー

**作成日**: 2026-02-14
**作成者**: cron-planner (v03-planning-team)
**対象モジュール**: Cron Jobs Management (Phase 3 v0.3)
**ステータス**: 設計段階（実装前、人間承認必須）

---

## 1. 概要

本ドキュメントは、Cron Jobs管理モジュールにおける**コマンドallowlist**と**スケジュール検証ルール**の完全定義である。

CLAUDE.mdのセキュリティ原則「Allowlist First（許可リスト優先）」に準拠し、**明示的に許可されたコマンドのみ**をCronジョブとして登録可能とする。

---

## 2. コマンド Allowlist

### 2.1 許可コマンド一覧

| # | コマンド (絶対パス) | 用途 | リスク | 引数制約 |
|---|-------------------|------|--------|---------|
| 1 | `/usr/bin/rsync` | ファイル同期・バックアップ | LOW | `--delete` 禁止 |
| 2 | `/usr/local/bin/healthcheck.sh` | ヘルスチェック | LOW | 引数なし |
| 3 | `/usr/bin/find` | ファイル検索・クリーンアップ | MEDIUM | `-exec` 禁止、`-delete` 禁止 |
| 4 | `/usr/bin/tar` | アーカイブ作成 | LOW | 展開先は `/backup/` のみ |
| 5 | `/usr/bin/gzip` | 圧縮 | LOW | 対象は `/backup/`, `/var/log/` のみ |
| 6 | `/usr/bin/curl` | HTTP リクエスト（監視用） | MEDIUM | `-o` は `/tmp/healthcheck/` のみ |
| 7 | `/usr/bin/wget` | ファイルダウンロード（更新用） | MEDIUM | `-O` は `/tmp/downloads/` のみ |
| 8 | `/usr/bin/python3` | Python スクリプト実行 | HIGH | `/opt/adminui/scripts/` 内のみ |
| 9 | `/usr/bin/node` | Node.js スクリプト実行 | HIGH | `/opt/adminui/scripts/` 内のみ |

### 2.2 許可コマンドの追加手順

allowlistへの新規コマンド追加は、CLAUDE.mdの「人間承認必須ポイント」に該当する。

```
追加手順:
1. セキュリティ評価書を作成（脅威分析、影響範囲）
2. 引数制約を定義
3. テストケースを作成
4. Security SubAgent によるレビュー
5. 人間による明示的承認
6. コード変更（cron_config.py + ラッパースクリプト）
7. テスト実行
8. デプロイ
```

### 2.3 Allowlist 定義コード

```python
# backend/core/cron_config.py

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AllowedCommand:
    """許可コマンドの定義"""
    path: str                           # 絶対パス
    description: str                    # 説明
    risk_level: str                     # LOW / MEDIUM / HIGH
    max_arguments: int = 10             # 最大引数数
    forbidden_argument_patterns: tuple[str, ...] = ()  # 禁止引数パターン
    allowed_argument_paths: tuple[str, ...] = ()       # 引数に許可されるパス


ALLOWED_CRON_COMMANDS_DETAIL: dict[str, AllowedCommand] = {
    "/usr/bin/rsync": AllowedCommand(
        path="/usr/bin/rsync",
        description="File synchronization and backup",
        risk_level="LOW",
        max_arguments=20,
        forbidden_argument_patterns=(
            "--delete",
            "--remove-source-files",
            "-e",           # リモートシェル指定を禁止
            "--rsync-path",  # リモート側のrsyncパスを禁止
        ),
    ),
    "/usr/local/bin/healthcheck.sh": AllowedCommand(
        path="/usr/local/bin/healthcheck.sh",
        description="System health check script",
        risk_level="LOW",
        max_arguments=0,
    ),
    "/usr/bin/find": AllowedCommand(
        path="/usr/bin/find",
        description="File search and cleanup",
        risk_level="MEDIUM",
        max_arguments=15,
        forbidden_argument_patterns=(
            "-exec",
            "-execdir",
            "-ok",
            "-okdir",
            "-delete",
            "-fls",
            "-fprint",
            "-fprint0",
        ),
    ),
    "/usr/bin/tar": AllowedCommand(
        path="/usr/bin/tar",
        description="Archive creation",
        risk_level="LOW",
        max_arguments=10,
        allowed_argument_paths=("/backup/",),
    ),
    "/usr/bin/gzip": AllowedCommand(
        path="/usr/bin/gzip",
        description="File compression",
        risk_level="LOW",
        max_arguments=5,
        allowed_argument_paths=("/backup/", "/var/log/"),
    ),
    "/usr/bin/curl": AllowedCommand(
        path="/usr/bin/curl",
        description="HTTP requests (monitoring)",
        risk_level="MEDIUM",
        max_arguments=10,
        forbidden_argument_patterns=(
            "--upload-file",
            "-T",
            "--data",
            "-d",
            "--form",
            "-F",
        ),
        allowed_argument_paths=("/tmp/healthcheck/",),
    ),
    "/usr/bin/wget": AllowedCommand(
        path="/usr/bin/wget",
        description="File download (updates)",
        risk_level="MEDIUM",
        max_arguments=10,
        forbidden_argument_patterns=(
            "--post-data",
            "--post-file",
            "--execute",
            "-e",
        ),
        allowed_argument_paths=("/tmp/downloads/",),
    ),
    "/usr/bin/python3": AllowedCommand(
        path="/usr/bin/python3",
        description="Python script execution (approved scripts only)",
        risk_level="HIGH",
        max_arguments=5,
        forbidden_argument_patterns=(
            "-c",       # インラインコード実行禁止
            "-m",       # モジュール実行禁止
            "--command",
        ),
        allowed_argument_paths=("/opt/adminui/scripts/",),
    ),
    "/usr/bin/node": AllowedCommand(
        path="/usr/bin/node",
        description="Node.js script execution (approved scripts only)",
        risk_level="HIGH",
        max_arguments=5,
        forbidden_argument_patterns=(
            "-e",       # インラインコード実行禁止
            "--eval",
            "-p",       # 式の評価禁止
            "--print",
        ),
        allowed_argument_paths=("/opt/adminui/scripts/",),
    ),
}

# 簡易参照用リスト
ALLOWED_CRON_COMMANDS: list[str] = list(ALLOWED_CRON_COMMANDS_DETAIL.keys())
```

---

## 3. 禁止コマンドリスト (Denylist)

Allowlist方式が基本であるため、allowlistに含まれないコマンドは全て拒否される。
以下のdenylistは、セキュリティログおよび監査で「明示的に危険なコマンドが試行された」ことを識別するための補助リストである。

### 3.1 カテゴリ別禁止コマンド

#### シェルインタプリタ（絶対禁止）

```
/bin/bash
/bin/sh
/bin/zsh
/bin/dash
/bin/csh
/bin/tcsh
/bin/fish
/usr/bin/bash
/usr/bin/sh
/usr/bin/zsh
```

**理由**: シェルインタプリタの実行は任意コマンド実行と同義であり、allowlistの意味を完全に無効化する。

#### ファイル破壊コマンド

```
/bin/rm
/usr/bin/rm
/usr/bin/shred
/bin/dd
/usr/bin/dd
```

**理由**: データの不可逆的な破壊が可能。

#### システム操作コマンド

```
/sbin/reboot
/sbin/shutdown
/sbin/init
/sbin/poweroff
/sbin/halt
/usr/sbin/reboot
```

**理由**: システムの可用性に直接影響する。

#### ディスク・パーティション操作

```
/sbin/mkfs
/sbin/mkfs.*
/sbin/fdisk
/sbin/gdisk
/sbin/parted
/sbin/mkswap
```

**理由**: データ損失やシステム破壊のリスク。

#### 権限・ユーザー操作

```
/usr/bin/chmod
/bin/chmod
/usr/bin/chown
/bin/chown
/usr/bin/chgrp
/usr/sbin/useradd
/usr/sbin/userdel
/usr/sbin/usermod
/usr/sbin/groupadd
/usr/sbin/groupdel
/usr/sbin/visudo
/usr/bin/sudo
/usr/bin/su
/usr/bin/passwd
```

**理由**: 権限昇格や認証バイパスのリスク。

#### ネットワーク攻撃ツール

```
/usr/bin/nc
/usr/bin/ncat
/usr/bin/netcat
/usr/bin/nmap
/usr/bin/socat
/usr/bin/telnet
/usr/bin/ssh (cron経由での直接使用)
/usr/bin/scp (cron経由での直接使用)
```

**理由**: リバースシェルやネットワーク偵察に使用される可能性。

#### パッケージ管理

```
/usr/bin/apt
/usr/bin/apt-get
/usr/bin/dpkg
/usr/bin/pip
/usr/bin/pip3
/usr/bin/npm
```

**理由**: 不正なパッケージのインストールリスク。

### 3.2 禁止コマンド定義コード

```python
# backend/core/cron_config.py (続き)

FORBIDDEN_CRON_COMMANDS: list[str] = [
    # シェルインタプリタ
    "/bin/bash", "/bin/sh", "/bin/zsh", "/bin/dash",
    "/bin/csh", "/bin/tcsh", "/bin/fish",
    "/usr/bin/bash", "/usr/bin/sh", "/usr/bin/zsh",

    # ファイル破壊
    "/bin/rm", "/usr/bin/rm", "/usr/bin/shred",
    "/bin/dd", "/usr/bin/dd",

    # システム操作
    "/sbin/reboot", "/sbin/shutdown", "/sbin/init",
    "/sbin/poweroff", "/sbin/halt",
    "/usr/sbin/reboot",

    # ディスク操作
    "/sbin/mkfs", "/sbin/fdisk", "/sbin/gdisk",
    "/sbin/parted", "/sbin/mkswap",

    # 権限操作
    "/usr/bin/chmod", "/bin/chmod",
    "/usr/bin/chown", "/bin/chown", "/usr/bin/chgrp",
    "/usr/sbin/useradd", "/usr/sbin/userdel", "/usr/sbin/usermod",
    "/usr/sbin/groupadd", "/usr/sbin/groupdel",
    "/usr/sbin/visudo", "/usr/bin/sudo", "/usr/bin/su",
    "/usr/bin/passwd",

    # ネットワークツール
    "/usr/bin/nc", "/usr/bin/ncat", "/usr/bin/netcat",
    "/usr/bin/nmap", "/usr/bin/socat", "/usr/bin/telnet",

    # パッケージ管理
    "/usr/bin/apt", "/usr/bin/apt-get", "/usr/bin/dpkg",
    "/usr/bin/pip", "/usr/bin/pip3", "/usr/bin/npm",
]

# 禁止コマンドが試行された場合のセキュリティアラートレベル
FORBIDDEN_COMMAND_ALERT_LEVELS: dict[str, str] = {
    # CRITICAL: 即座にセキュリティチームへ通知
    "/bin/bash": "CRITICAL",
    "/bin/sh": "CRITICAL",
    "/usr/bin/sudo": "CRITICAL",
    "/usr/sbin/visudo": "CRITICAL",
    "/usr/bin/nc": "CRITICAL",

    # HIGH: 監査ログに記録 + 管理者通知
    "/bin/rm": "HIGH",
    "/sbin/reboot": "HIGH",
    "/usr/sbin/useradd": "HIGH",
    "/usr/bin/passwd": "HIGH",

    # MEDIUM: 監査ログに記録
    # デフォルト: その他の禁止コマンド
}
```

---

## 4. スケジュール検証ルール

### 4.1 Cron式の形式

```
┌───────────── 分 (0-59)
│ ┌───────────── 時 (0-23)
│ │ ┌───────────── 日 (1-31)
│ │ │ ┌───────────── 月 (1-12)
│ │ │ │ ┌───────────── 曜日 (0-7, 0と7=日曜)
│ │ │ │ │
* * * * *
```

### 4.2 許可パターン

| パターン | 説明 | 例 |
|---------|------|-----|
| `N` | 固定値 | `30` (30分) |
| `*` | 全値 | `*` (毎分) |
| `*/N` | N間隔 | `*/5` (5分ごと) |
| `N-M` | 範囲 | `9-17` (9時〜17時) |
| `N,M` | 列挙 | `1,15` (1日と15日) |

### 4.3 禁止パターン

| 制約 | ルール | 理由 |
|------|--------|------|
| 最小実行間隔 | 5分以上 | リソース保護 |
| `* * * * *` | 禁止 | 毎分実行はリソース枯渇リスク |
| `*/1 * * * *` | 禁止 | 同上 |
| `*/2 * * * *` | 禁止 | 2分間隔もリソースリスク |
| `*/3 * * * *` | 禁止 | 3分間隔もリソースリスク |
| `*/4 * * * *` | 禁止 | 4分間隔もリソースリスク |

### 4.4 検証コード

```python
import re
from typing import Optional


class CronScheduleValidator:
    """Cronスケジュール検証クラス"""

    # 各フィールドの有効範囲
    FIELD_RANGES = {
        "minute": (0, 59),
        "hour": (0, 23),
        "day": (1, 31),
        "month": (1, 12),
        "weekday": (0, 7),
    }

    # 許可されるフィールドパターン
    FIELD_PATTERN = re.compile(
        r"^(\*|[0-9]+|[0-9]+-[0-9]+|[0-9]+(,[0-9]+)*|\*/[0-9]+)$"
    )

    # 最小実行間隔（分）
    MIN_INTERVAL_MINUTES = 5

    @classmethod
    def validate(cls, schedule: str) -> tuple[bool, Optional[str]]:
        """
        Cronスケジュールを検証する

        Args:
            schedule: Cron式 (例: "0 2 * * *")

        Returns:
            (valid, error_message)
        """
        parts = schedule.strip().split()

        # フィールド数チェック
        if len(parts) != 5:
            return False, f"Invalid field count: expected 5, got {len(parts)}"

        field_names = ["minute", "hour", "day", "month", "weekday"]

        for i, (part, name) in enumerate(zip(parts, field_names)):
            # パターンチェック
            if not cls.FIELD_PATTERN.match(part):
                return False, f"Invalid {name} field: {part}"

            # 範囲チェック
            min_val, max_val = cls.FIELD_RANGES[name]
            error = cls._validate_range(part, min_val, max_val, name)
            if error:
                return False, error

        # 最小実行間隔チェック
        error = cls._validate_min_interval(parts[0], parts[1])
        if error:
            return False, error

        return True, None

    @classmethod
    def _validate_range(
        cls, field: str, min_val: int, max_val: int, name: str
    ) -> Optional[str]:
        """フィールドの範囲を検証"""
        if field == "*":
            return None

        if field.startswith("*/"):
            step = int(field[2:])
            if step < 1 or step > max_val:
                return f"Invalid step in {name}: {step}"
            return None

        if "-" in field:
            parts = field.split("-")
            low, high = int(parts[0]), int(parts[1])
            if low < min_val or high > max_val or low > high:
                return f"Invalid range in {name}: {field}"
            return None

        if "," in field:
            values = [int(v) for v in field.split(",")]
            for v in values:
                if v < min_val or v > max_val:
                    return f"Value out of range in {name}: {v}"
            return None

        # 固定値
        val = int(field)
        if val < min_val or val > max_val:
            return f"Value out of range in {name}: {val}"
        return None

    @classmethod
    def _validate_min_interval(
        cls, minute_field: str, hour_field: str
    ) -> Optional[str]:
        """最小実行間隔を検証"""
        # 毎分実行の検出
        if minute_field == "*":
            return "Every-minute execution is not allowed (minimum interval: 5 minutes)"

        # */N の場合、N >= 5 であること
        if minute_field.startswith("*/"):
            step = int(minute_field[2:])
            if step < cls.MIN_INTERVAL_MINUTES:
                return (
                    f"Execution interval too short: */{step} "
                    f"(minimum: */{cls.MIN_INTERVAL_MINUTES})"
                )

        return None

    @classmethod
    def to_human_readable(cls, schedule: str) -> str:
        """Cron式を人間が読める形式に変換"""
        parts = schedule.strip().split()
        if len(parts) != 5:
            return schedule

        minute, hour, day, month, weekday = parts
        descriptions = []

        if minute == "*" and hour == "*":
            descriptions.append("Every minute")
        elif minute.startswith("*/"):
            descriptions.append(f"Every {minute[2:]} minutes")
        elif hour == "*":
            descriptions.append(f"At minute {minute} of every hour")
        else:
            descriptions.append(f"At {hour}:{minute.zfill(2)}")

        if day != "*" and month != "*":
            descriptions.append(f"on day {day} of month {month}")
        elif day != "*":
            descriptions.append(f"on day {day}")
        elif month != "*":
            descriptions.append(f"in month {month}")

        weekday_names = {
            "0": "Sunday", "7": "Sunday",
            "1": "Monday", "2": "Tuesday",
            "3": "Wednesday", "4": "Thursday",
            "5": "Friday", "6": "Saturday",
        }
        if weekday != "*":
            if weekday in weekday_names:
                descriptions.append(f"on {weekday_names[weekday]}")
            else:
                descriptions.append(f"on weekday {weekday}")

        return " ".join(descriptions)
```

---

## 5. 引数検証ルール

### 5.1 共通禁止文字

全コマンドの引数に対して、以下の文字を**無条件で拒否**する:

```python
FORBIDDEN_ARGUMENT_CHARS: list[str] = [
    ";",    # コマンド連結
    "|",    # パイプ
    "&",    # バックグラウンド実行 / AND
    "$",    # 変数展開
    "(",    # サブシェル
    ")",    # サブシェル
    "`",    # コマンド置換
    ">",    # リダイレクト
    "<",    # リダイレクト
    "{",    # ブレース展開
    "}",    # ブレース展開
    "[",    # グロブ
    "]",    # グロブ
    "!",    # 履歴展開
    "~",    # ホームディレクトリ展開
    "#",    # コメント
    "\\",   # エスケープ文字
]
```

### 5.2 コマンド別引数制約

#### /usr/bin/rsync

```python
RSYNC_FORBIDDEN_ARGS = [
    "--delete",             # ファイル削除
    "--remove-source-files", # ソース削除
    "-e",                   # リモートシェル指定
    "--rsh",                # リモートシェル指定
    "--rsync-path",         # リモートrsyncパス
    "--exclude-from",       # 外部ファイル参照
    "--files-from",         # 外部ファイル参照
    "--filter",             # フィルタルール
]
```

#### /usr/bin/find

```python
FIND_FORBIDDEN_ARGS = [
    "-exec",      # コマンド実行
    "-execdir",   # コマンド実行
    "-ok",        # コマンド実行（対話的）
    "-okdir",     # コマンド実行（対話的）
    "-delete",    # ファイル削除
    "-fls",       # ファイル出力
    "-fprint",    # ファイル出力
    "-fprint0",   # ファイル出力
    "-fprintf",   # ファイル出力
]
```

#### /usr/bin/python3, /usr/bin/node

```python
SCRIPT_FORBIDDEN_ARGS = [
    "-c",         # インラインコード実行
    "--command",
    "-m",         # モジュール実行（python3）
    "-e",         # インラインコード実行（node）
    "--eval",     # インラインコード実行（node）
    "-p",         # 式の評価（node）
    "--print",    # 式の評価（node）
]

# 許可されるスクリプトパス
ALLOWED_SCRIPT_DIR = "/opt/adminui/scripts/"
```

### 5.3 引数検証コード

```python
def validate_cron_arguments(
    command: str,
    arguments: str
) -> tuple[bool, Optional[str]]:
    """
    Cronジョブの引数を検証する

    Args:
        command: コマンド絶対パス
        arguments: 引数文字列

    Returns:
        (valid, error_message)
    """
    if not arguments:
        return True, None

    # 1. 禁止文字チェック
    for char in FORBIDDEN_ARGUMENT_CHARS:
        if char in arguments:
            return False, f"Forbidden character in arguments: '{char}'"

    # 2. コマンド固有の制約チェック
    cmd_config = ALLOWED_CRON_COMMANDS_DETAIL.get(command)
    if not cmd_config:
        return False, f"Command not in allowlist: {command}"

    # 3. 引数数チェック
    arg_parts = arguments.split()
    if len(arg_parts) > cmd_config.max_arguments:
        return False, (
            f"Too many arguments: {len(arg_parts)} "
            f"(max: {cmd_config.max_arguments})"
        )

    # 4. 禁止引数パターンチェック
    for forbidden in cmd_config.forbidden_argument_patterns:
        for arg in arg_parts:
            if arg == forbidden or arg.startswith(forbidden + "="):
                return False, f"Forbidden argument pattern: {forbidden}"

    # 5. 許可パスチェック（パスを含む引数のみ）
    if cmd_config.allowed_argument_paths:
        for arg in arg_parts:
            if arg.startswith("/"):
                path_allowed = any(
                    arg.startswith(allowed_path)
                    for allowed_path in cmd_config.allowed_argument_paths
                )
                if not path_allowed:
                    return False, (
                        f"Path not allowed: {arg} "
                        f"(allowed: {cmd_config.allowed_argument_paths})"
                    )

    # 6. パストラバーサルチェック
    if ".." in arguments:
        return False, "Path traversal detected: '..' in arguments"

    return True, None
```

---

## 6. ユーザー名検証ルール

### 6.1 許可パターン

```python
import re

# Linux標準のユーザー名パターン
USERNAME_PATTERN = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")

# 操作禁止ユーザー
FORBIDDEN_CRON_USERS: list[str] = [
    "root",
    "daemon",
    "bin",
    "sys",
    "sync",
    "games",
    "man",
    "lp",
    "mail",
    "news",
    "uucp",
    "proxy",
    "www-data",
    "backup",
    "nobody",
    "systemd-network",
    "systemd-resolve",
]
```

### 6.2 検証コード

```python
def validate_cron_user(username: str) -> tuple[bool, Optional[str]]:
    """
    Cronジョブ操作対象ユーザーを検証する

    Args:
        username: ユーザー名

    Returns:
        (valid, error_message)
    """
    # パターンチェック
    if not USERNAME_PATTERN.match(username):
        return False, f"Invalid username format: {username}"

    # 禁止ユーザーチェック
    if username in FORBIDDEN_CRON_USERS:
        return False, f"User not allowed for cron operations: {username}"

    return True, None
```

---

## 7. 機密情報検出ルール

### 7.1 検出パターン

引数に含まれる可能性のある機密情報パターン:

```python
import re

SENSITIVE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("password", re.compile(r"(?i)(password|passwd|pass)[\s=:]+\S+")),
    ("api_key", re.compile(r"(?i)(api[_-]?key|apikey)[\s=:]+\S+")),
    ("token", re.compile(r"(?i)(token|secret|auth)[\s=:]+\S+")),
    ("connection_string", re.compile(r"(?i)(mysql|postgres|redis)://\S+:\S+@")),
    ("private_key", re.compile(r"(?i)(ssh|rsa|dsa|ecdsa)[_-]?(key|private)")),
    ("aws_credentials", re.compile(r"(?i)(AKIA|aws[_-]?access|aws[_-]?secret)\S+")),
]
```

### 7.2 処理方針

```
検出時の処理:
1. リクエストは拒否しない（誤検知の可能性）
2. 警告を承認画面に表示
3. 監査ログに記録
4. 承認者に注意を促すメッセージを付与
```

---

## 8. ポリシー変更履歴

| 日付 | バージョン | 変更内容 | 承認者 |
|------|----------|---------|--------|
| 2026-02-14 | 1.0 | 初版作成 | (設計段階、承認待ち) |

---

## 9. 関連ドキュメント

- [docs/architecture/cron-jobs-design.md](../architecture/cron-jobs-design.md) - アーキテクチャ設計
- [docs/security/cron-jobs-threat-analysis.md](cron-jobs-threat-analysis.md) - 脅威分析
- [CLAUDE.md](../../CLAUDE.md) - セキュリティ原則
- [SECURITY.md](../../SECURITY.md) - セキュリティポリシー

---

**最終更新**: 2026-02-14
**次回レビュー**: 実装開始前に人間承認必須
**変更管理**: 本ポリシーの変更は人間の明示的承認が必須
