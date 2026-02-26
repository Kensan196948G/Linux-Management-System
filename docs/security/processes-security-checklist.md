# Running Processes モジュール セキュリティチェックリスト

**バージョン**: 1.0
**作成日**: 2026-02-06
**モジュール区分**: System - 参照系
**セキュリティリスク**: **LOW**（参照専用、操作機能なし）

---

## 1. セキュリティ評価サマリ

| 項目 | 評価 | 理由 |
|------|------|------|
| **総合リスク** | **LOW** | 参照専用機能、root権限不要 |
| コマンド実行 | **LOW** | `ps`, `/proc` 読み取りのみ |
| 入力検証 | **MEDIUM** | PID, ユーザー名の検証必須 |
| 権限制御 | **LOW** | 全ロール参照可能 |
| 監査ログ | **必須** | 全操作記録 |

### セキュリティ原則遵守状況

| 原則 | 遵守状況 | 備考 |
|------|---------|------|
| ✅ Allowlist First | **遵守** | `sort_by`, `order` はallowlistのみ |
| ✅ Deny by Default | **遵守** | 許可リスト外は拒否 |
| ✅ Shell禁止 | **遵守** | `shell=True` 不使用 |
| ✅ sudo最小化 | **遵守** | ラッパー経由のみ |
| ✅ 監査証跡 | **遵守** | 全操作ログ記録 |

---

## 2. 脅威分析（Threat Modeling）

### 2.1 攻撃シナリオ

#### シナリオ1: PIDパラメータでのShell Injection

**攻撃手法**:
```http
GET /api/processes/1234;rm -rf /
```

**リスク**: **HIGH**（実装不備の場合）

**対策**:
- ✅ PIDの型検証（整数のみ）
- ✅ 範囲検証（1-999999）
- ✅ 特殊文字拒否
- ✅ 配列渡し（文字列結合なし）

**実装例**:
```python
# ❌ 危険な実装（絶対禁止）
subprocess.run(f"ps -p {pid}", shell=True)  # Shell injection可能

# ✅ 安全な実装
if not isinstance(pid, int) or not (1 <= pid <= 999999):
    raise ValidationError("Invalid PID")
subprocess.run(["ps", "-p", str(pid)], check=True)
```

---

#### シナリオ2: userパラメータでのCommand Injection

**攻撃手法**:
```http
GET /api/processes?user=www-data|cat /etc/passwd
```

**リスク**: **HIGH**（実装不備の場合）

**対策**:
- ✅ 正規表現検証（`^[a-zA-Z0-9_-]+$`）
- ✅ 特殊文字即座に拒否
- ✅ 配列渡し

**実装例**:
```python
import re

# ✅ 安全な実装
FORBIDDEN_CHARS = [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?", "{", "}", "[", "]"]

def validate_user(user: str) -> bool:
    # 特殊文字チェック
    for char in FORBIDDEN_CHARS:
        if char in user:
            raise SecurityError(f"Forbidden character detected: {char}")

    # 正規表現チェック
    if not re.match(r'^[a-zA-Z0-9_-]+$', user):
        raise ValidationError("Invalid user format")

    return True
```

---

#### シナリオ3: sort_by / order パラメータでの不正値注入

**攻撃手法**:
```http
GET /api/processes?sort_by=cpu;DROP TABLE processes
```

**リスク**: **MEDIUM**（実装不備の場合）

**対策**:
- ✅ Allowlistによる検証
- ✅ enum型使用（FastAPI）

**実装例**:
```python
from enum import Enum

class SortBy(str, Enum):
    CPU = "cpu"
    MEMORY = "memory"
    PID = "pid"
    NAME = "name"

class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"

# FastAPI エンドポイント
@router.get("/processes")
async def list_processes(
    sort_by: SortBy = SortBy.CPU,
    order: SortOrder = SortOrder.DESC,
):
    # allowlist外の値は自動的に拒否される
    pass
```

---

#### シナリオ4: 大量リクエストによるDoS攻撃

**攻撃手法**:
```bash
# 毎秒100リクエストを送信
for i in {1..100}; do
  curl https://adminui.example.com/api/processes &
done
```

**リスク**: **MEDIUM**

**対策**:
- ✅ レートリミット（1ユーザーあたり 10req/秒）
- ✅ タイムアウト設定（30秒）
- ✅ キャッシング（5秒間隔）

**実装例**:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.get("/processes")
@limiter.limit("10/second")
async def list_processes():
    pass
```

---

#### シナリオ5: 認証トークン漏洩

**攻撃手法**:
```bash
# 漏洩したトークンで不正アクセス
curl -H "Authorization: Bearer leaked-token" \
  https://adminui.example.com/api/processes
```

**リスク**: **HIGH**

**対策**:
- ✅ トークン有効期限（15分）
- ✅ リフレッシュトークン（7日）
- ✅ HTTPS必須
- ✅ トークン無効化API

---

### 2.2 脅威マトリクス

| 脅威 | 影響 | 発生確率 | リスク | 対策 |
|------|------|---------|--------|------|
| Shell Injection | **HIGH** | **LOW** | **MEDIUM** | 入力検証、配列渡し |
| Command Injection | **HIGH** | **LOW** | **MEDIUM** | 正規表現検証、allowlist |
| DoS攻撃 | **MEDIUM** | **MEDIUM** | **MEDIUM** | レートリミット、キャッシング |
| 認証トークン漏洩 | **HIGH** | **LOW** | **MEDIUM** | トークン有効期限、HTTPS |
| 権限昇格 | **CRITICAL** | **VERY LOW** | **MEDIUM** | 権限チェック、監査ログ |
| 情報漏洩 | **MEDIUM** | **LOW** | **LOW** | 権限チェック |

---

## 3. 入力検証チェックリスト

### 3.1 PIDパラメータ（CRITICAL）

- [ ] **型検証**: `isinstance(pid, int)`
- [ ] **範囲検証**: `1 <= pid <= 999999`
- [ ] **特殊文字拒否**: `;`, `|`, `&`, `$`, `` ` ``, `(`, `)` 等
- [ ] **配列渡し**: `["ps", "-p", str(pid)]`（文字列結合なし）
- [ ] **エラー時即座に拒否**: 例外スロー

**テストケース**:
```python
# 正常系
assert validate_pid(1234) == True

# 異常系
with pytest.raises(ValidationError):
    validate_pid(-1)           # 負の値
    validate_pid(0)            # 0
    validate_pid(1000000)      # 範囲外
    validate_pid("1234")       # 文字列
    validate_pid("1234; rm -rf /")  # Shell injection試行
```

---

### 3.2 userパラメータ（CRITICAL）

- [ ] **正規表現検証**: `^[a-zA-Z0-9_-]+$`
- [ ] **長さ制限**: 最大64文字
- [ ] **特殊文字即座に拒否**: FORBIDDEN_CHARS チェック
- [ ] **配列渡し**: コマンドラインオプション値として渡す

**テストケース**:
```python
# 正常系
assert validate_user("www-data") == True
assert validate_user("nginx") == True
assert validate_user("user_123") == True

# 異常系
with pytest.raises(SecurityError):
    validate_user("www-data; rm -rf /")
    validate_user("nginx | cat /etc/passwd")
    validate_user("user$(whoami)")
    validate_user("root&&ls")
```

---

### 3.3 sort_by / order パラメータ（MEDIUM）

- [ ] **Allowlist検証**: `sort_by in ["cpu", "memory", "pid", "name"]`
- [ ] **Enum型使用**: FastAPIのEnum型で自動検証
- [ ] **デフォルト値**: `sort_by="cpu"`, `order="desc"`

**テストケース**:
```python
# 正常系
assert validate_sort_by("cpu") == True
assert validate_sort_by("memory") == True

# 異常系
with pytest.raises(ValidationError):
    validate_sort_by("cpu; DROP TABLE")
    validate_sort_by("unknown")
    validate_sort_by("")
```

---

### 3.4 limit / offset パラメータ（LOW）

- [ ] **型検証**: `isinstance(limit, int)`
- [ ] **範囲検証**: `1 <= limit <= 1000`
- [ ] **範囲検証**: `0 <= offset`

**テストケース**:
```python
# 正常系
assert validate_limit(100) == True
assert validate_limit(1) == True
assert validate_limit(1000) == True

# 異常系
with pytest.raises(ValidationError):
    validate_limit(0)
    validate_limit(-1)
    validate_limit(1001)
```

---

## 4. sudo ラッパー実装チェックリスト

### 4.1 adminui-processes.sh（新規作成）

#### 基本設計

- [ ] **Shebang**: `#!/bin/bash`
- [ ] **安全オプション**: `set -euo pipefail`
- [ ] **ログ記録**: 実行前/実行後
- [ ] **JSON出力**: 構造化データ返却

#### 入力検証

- [ ] **引数数チェック**: `if [ $# -ne 5 ]; then exit 1; fi`
- [ ] **PID範囲チェック**: `if [ "$PID" -lt 1 ] || [ "$PID" -gt 999999 ]; then exit 1; fi`
- [ ] **特殊文字チェック**: `[[ "$USER" =~ [;\|\&\$\(\)\`] ]]`
- [ ] **allowlist検証**: `ALLOWED_SORT_BY=("cpu" "memory" "pid" "name")`

#### コマンド実行

- [ ] **配列使用**: `CMD=("ps" "-p" "$PID")`
- [ ] **引用符徹底**: `"${CMD[@]}"`
- [ ] **shell展開なし**: 絶対に `eval` / `$()` / `` ` ` `` を使わない

#### エラーハンドリング

- [ ] **エラーログ**: stderr に記録
- [ ] **JSON エラーレスポンス**: `{"status": "error", "message": "..."}`
- [ ] **終了コード**: 成功時 `0`, 失敗時 `1-255`

---

### 4.2 実装例（抜粋）

```bash
#!/bin/bash
# adminui-processes.sh - プロセス一覧取得ラッパー

set -euo pipefail

# 引数検証
if [ $# -ne 5 ]; then
    echo '{"status": "error", "message": "Invalid arguments"}' >&2
    exit 1
fi

USER_FILTER="$1"
SORT_BY="$2"
ORDER="$3"
LIMIT="$4"
OFFSET="$5"

# 特殊文字チェック
if [[ "$USER_FILTER" =~ [;\|\&\$\(\)\`\>\<\*\?\{\}\[\]] ]]; then
    echo '{"status": "error", "message": "Forbidden character detected"}' >&2
    exit 1
fi

# allowlist検証
ALLOWED_SORT_BY=("cpu" "memory" "pid" "name")
if [[ ! " ${ALLOWED_SORT_BY[@]} " =~ " ${SORT_BY} " ]]; then
    echo '{"status": "error", "message": "Invalid sort_by"}' >&2
    exit 1
fi

# 実行ログ
logger -t adminui-processes -p user.info "Process list requested by UID=$UID"

# プロセス一覧取得（配列渡し）
ps aux --sort="-${SORT_BY}" | jq -R . | jq -s .

exit 0
```

---

## 5. API実装チェックリスト

### 5.1 backend/api/routes/processes.py

#### エンドポイント定義

- [ ] **FastAPI router**: `router = APIRouter(prefix="/processes", tags=["processes"])`
- [ ] **認証必須**: `Depends(get_current_user)`
- [ ] **権限チェック**: `Depends(require_permission("read:processes"))`
- [ ] **Pydanticモデル**: リクエスト/レスポンスの型定義

#### 入力バリデーション

- [ ] **Pydantic Field**: `Field(..., ge=1, le=999999)`
- [ ] **正規表現**: `pattern="^[a-zA-Z0-9_-]+$"`
- [ ] **Enum型**: `class SortBy(str, Enum)`

#### sudo ラッパー呼び出し

- [ ] **SudoWrapper使用**: `sudo_wrapper.get_processes(...)`
- [ ] **配列渡し**: `self._execute("adminui-processes.sh", [user, sort_by, order, str(limit), str(offset)])`
- [ ] **タイムアウト**: `timeout=30`

#### エラーハンドリング

- [ ] **HTTPException**: `raise HTTPException(status_code=404, detail="...")`
- [ ] **監査ログ記録**: 成功/失敗両方
- [ ] **詳細エラー情報**: `details={"field": "pid", "value": -1}`

---

### 5.2 実装例（抜粋）

```python
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from enum import Enum

router = APIRouter(prefix="/processes", tags=["processes"])

class SortBy(str, Enum):
    CPU = "cpu"
    MEMORY = "memory"
    PID = "pid"
    NAME = "name"

class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"

@router.get("/processes")
async def list_processes(
    user: str | None = None,
    sort_by: SortBy = SortBy.CPU,
    order: SortOrder = SortOrder.DESC,
    limit: int = Field(100, ge=1, le=1000),
    offset: int = Field(0, ge=0),
    current_user: TokenData = Depends(require_permission("read:processes")),
):
    """プロセス一覧取得"""

    # ユーザー名検証
    if user:
        validate_user(user)

    # 監査ログ記録（試行）
    audit_log.record(
        operation="process_list_view",
        user_id=current_user.user_id,
        target="all_processes",
        status="attempt",
    )

    try:
        # sudo ラッパー呼び出し
        result = sudo_wrapper.get_processes(
            user=user,
            sort_by=sort_by.value,
            order=order.value,
            limit=limit,
            offset=offset,
        )

        # 監査ログ記録（成功）
        audit_log.record(
            operation="process_list_view",
            user_id=current_user.user_id,
            target="all_processes",
            status="success",
            details={"result_count": len(result["data"]["processes"])},
        )

        return result

    except SudoWrapperError as e:
        # 監査ログ記録（失敗）
        audit_log.record(
            operation="process_list_view",
            user_id=current_user.user_id,
            target="all_processes",
            status="failure",
            details={"error": str(e)},
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
```

---

## 6. テストチェックリスト

### 6.1 セキュリティテスト（CRITICAL）

#### Shell Injection テスト

```python
def test_reject_shell_injection_in_pid():
    """PIDパラメータでのshell injection試行を拒否"""
    malicious_pids = [
        "1234; rm -rf /",
        "1234 | cat /etc/passwd",
        "1234 && whoami",
        "1234`ls`",
        "1234$(whoami)",
    ]
    for pid in malicious_pids:
        with pytest.raises(ValidationError):
            get_process_detail(pid)
```

#### Command Injection テスト

```python
def test_reject_command_injection_in_user():
    """userパラメータでのcommand injection試行を拒否"""
    malicious_users = [
        "www-data; rm -rf /",
        "nginx | cat /etc/passwd",
        "user$(whoami)",
        "root&&ls",
        "user`id`",
    ]
    for user in malicious_users:
        with pytest.raises(SecurityError):
            list_processes(user=user)
```

---

### 6.2 正常系テスト

```python
def test_list_processes_success():
    """プロセス一覧取得（正常系）"""
    result = list_processes(sort_by="cpu", order="desc", limit=100)
    assert result["status"] == "success"
    assert "processes" in result["data"]
    assert len(result["data"]["processes"]) <= 100

def test_get_process_detail_success():
    """プロセス詳細取得（正常系）"""
    result = get_process_detail(pid=1)  # init/systemd
    assert result["status"] == "success"
    assert result["data"]["pid"] == 1
```

---

### 6.3 異常系テスト

```python
def test_process_not_found():
    """存在しないPIDを指定した場合"""
    with pytest.raises(HTTPException) as exc_info:
        get_process_detail(pid=999999)
    assert exc_info.value.status_code == 404

def test_invalid_sort_by():
    """不正なソート基準を指定した場合"""
    with pytest.raises(ValidationError):
        list_processes(sort_by="invalid")
```

---

### 6.4 カバレッジ目標

| コンポーネント | カバレッジ目標 | 重点テスト項目 |
|--------------|-------------|-------------|
| `backend/api/routes/processes.py` | **85%以上** | 入力検証、エラーハンドリング |
| `backend/core/sudo_wrapper.py` | **90%以上** | ラッパー呼び出し、タイムアウト |
| `wrappers/adminui-processes.sh` | **100%** | 全パターン（正常/異常） |

---

## 7. デプロイ前チェックリスト

### 7.1 コードレビュー

- [ ] **shell=True 不使用**: `grep -r "shell=True" backend/` → 検出なし
- [ ] **os.system 不使用**: `grep -r "os.system" backend/` → 検出なし
- [ ] **eval/exec 不使用**: `grep -r "eval\|exec" backend/` → 検出なし
- [ ] **配列渡し**: 全ての `subprocess.run` で配列使用

### 7.2 静的解析

```bash
# Bandit（セキュリティ検査）
bandit -r backend/api/routes/processes.py -ll

# Flake8（コード品質）
flake8 backend/api/routes/processes.py

# ShellCheck（シェルスクリプト検査）
shellcheck wrappers/adminui-processes.sh
```

### 7.3 テスト実行

```bash
# 全テスト実行
pytest tests/test_processes.py -v

# カバレッジ確認
pytest tests/test_processes.py --cov=backend/api/routes/processes --cov-report=html

# セキュリティテストのみ実行
pytest tests/test_processes.py -k "security" -v
```

---

## 8. 運用監視チェックリスト

### 8.1 監査ログ監視

- [ ] **異常なアクセスパターン**: 1ユーザーが1分間に100回以上アクセス
- [ ] **特殊文字検出ログ**: `FORBIDDEN_CHAR` エラーの頻発
- [ ] **存在しないPIDへの連続アクセス**: プロセススキャン試行の可能性

### 8.2 アラート設定

```yaml
# アラート条件例
alerts:
  - name: "Process API - Shell Injection Attempt"
    condition: 'audit_log.error_code == "FORBIDDEN_CHAR"'
    threshold: 5 occurrences / 5 minutes
    severity: HIGH

  - name: "Process API - DoS Attempt"
    condition: 'rate(process_api_requests_total) > 100/user/minute'
    threshold: continuous for 5 minutes
    severity: MEDIUM
```

---

## 9. インシデント対応手順

### 9.1 Shell Injection検出時

1. **即座にAPI無効化**（緊急停止）
2. **監査ログ確認**（攻撃元IP特定）
3. **ファイアウォールでIP遮断**
4. **脆弱性修正**
5. **再デプロイ・検証**

### 9.2 DoS攻撃検出時

1. **レートリミット強化**（一時的に 5req/秒に制限）
2. **攻撃元IP特定・遮断**
3. **キャッシング強化**（30秒間隔に延長）

---

## 10. 最終承認

| 役割 | 承認者 | 承認日 | 署名 |
|------|-------|--------|------|
| セキュリティレビュー | @Security (AI) | - | - |
| コードレビュー | @Backend (AI) | - | - |
| 人間承認 | Team Lead | - | - |

---

**📌 本チェックリストは実装前・実装後の両方で確認すること。**
**📌 全項目のチェックが完了するまでデプロイ不可。**
