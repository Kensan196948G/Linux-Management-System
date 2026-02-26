# コーディング規約

**文書番号**: WEBUI-DEV-001
**バージョン**: 1.0
**作成日**: 2026-02-25
**対象システム**: Linux管理 WebUI サンプルシステム

---

## 1. 基本方針

本プロジェクトのコードは以下を最優先とする。

1. **安全性**: セキュリティ欠陥を作り込まない
2. **可読性**: チームメンバーが理解できるシンプルなコード
3. **保守性**: 変更・テストが容易な構造
4. **一貫性**: プロジェクト全体で統一されたスタイル

---

## 2. Python（バックエンド）

### 2.1 フォーマット・スタイル

| ルール | 設定 |
|-------|------|
| フォーマッタ | `black`（line-length: 88） |
| リンター | `flake8` + `pylint` |
| 型チェック | `mypy`（strict モード） |
| インポート整理 | `isort` |
| Pythonバージョン | 3.10+ |

```bash
# 実行方法
black backend/
isort backend/
flake8 backend/
mypy backend/
```

### 2.2 命名規則

| 種別 | 規則 | 例 |
|------|------|----|
| 変数・関数 | snake_case | `get_service_status()` |
| クラス | PascalCase | `ServiceManager` |
| 定数 | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT = 3` |
| プライベート | アンダースコア接頭辞 | `_validate_input()` |
| モジュール | snake_case | `service_manager.py` |

### 2.3 セキュリティ必須ルール

```python
# ❌ 絶対禁止: shell=True
subprocess.run(f"systemctl restart {name}", shell=True)
os.system(f"restart {name}")

# ✅ 必須: リスト形式 + shell=False
subprocess.run(
    ["sudo", "/usr/local/sbin/adminui-service-restart", name],
    shell=False,
    capture_output=True,
    timeout=30,
    check=False  # 例外は自分でハンドル
)

# ❌ 絶対禁止: eval / exec
eval(user_input)
exec(code_string)

# ❌ 絶対禁止: pickle（外部データ）
data = pickle.loads(untrusted_bytes)

# ✅ 必須: 型アノテーション
def restart_service(service_name: str) -> ServiceResult:
    ...

# ✅ 必須: 入力バリデーション（Pydantic）
class ServiceActionRequest(BaseModel):
    action: Literal["restart", "start", "stop"]
    service_name: str = Field(..., pattern=r'^[a-zA-Z0-9\-_\.]{1,128}$')
```

### 2.4 エラーハンドリング

```python
# ✅ 具体的な例外を捕捉
try:
    result = execute_wrapper(service_name, action)
except subprocess.TimeoutExpired:
    logger.error("Wrapper execution timed out", extra={"service": service_name})
    raise ServiceTimeoutError(f"Operation timed out for {service_name}")
except PermissionError:
    logger.error("Permission denied", extra={"service": service_name})
    raise InsufficientPermissionError("Not in allowlist")

# ❌ 禁止: 全例外の握りつぶし
try:
    ...
except Exception:
    pass

# ✅ 必須: ログには機密情報を含めない
logger.error("Login failed", extra={"username": username})  # OK
logger.error("Login failed", extra={"password": password})  # NG（パスワードログ禁止）
```

### 2.5 ログ記録

```python
import structlog

logger = structlog.get_logger(__name__)

# ✅ 構造化ログ（JSON形式）
logger.info(
    "service_action",
    action="restart",
    service_name=service_name,
    user_id=current_user.id,
    result="success",
    duration_ms=elapsed_ms
)

# ❌ 文字列フォーマットは避ける
logger.info(f"User {username} restarted {service_name}")  # 非推奨
```

---

## 3. TypeScript/JavaScript（フロントエンド）

### 3.1 フォーマット・スタイル

| ルール | 設定 |
|-------|------|
| フォーマッタ | `prettier` |
| リンター | `eslint` + `vue-eslint-parser` |
| 型チェック | TypeScript strict モード |
| パッケージ管理 | `npm` |

```bash
# 実行
npm run lint
npm run type-check
npm run format
```

### 3.2 命名規則

| 種別 | 規則 | 例 |
|------|------|----|
| 変数・関数 | camelCase | `getServiceList()` |
| コンポーネント | PascalCase | `ServiceCard.vue` |
| 定数 | UPPER_SNAKE_CASE | `API_BASE_URL` |
| CSS クラス | kebab-case | `.service-card` |
| ファイル（Vue） | PascalCase | `ServiceList.vue` |

### 3.3 セキュリティ必須ルール

```typescript
// ❌ 禁止: innerHTML への直接代入（XSS）
element.innerHTML = userContent;

// ✅ 必須: textContent を使用
element.textContent = userContent;

// ❌ 禁止: eval
eval(someString);

// ✅ 必須: API レスポンスは必ず型バリデーション
const response = await apiClient.get<ServiceListResponse>('/services');

// ✅ 必須: トークンは localStorage ではなく httpOnly Cookie
// （localStorage は XSS 攻撃で盗取可能）
// NG: localStorage.setItem('token', accessToken)
// OK: Cookie に httpOnly / Secure / SameSite=Strict で設定済み（サーバー側）

// ✅ 必須: APIエラーのユーザー表示（詳細を隠す）
catch (error) {
    // 詳細なエラーメッセージはログのみ、ユーザーには汎用メッセージ
    console.error('API Error:', error);
    showNotification('操作に失敗しました。管理者にお問い合わせください。', 'error');
}
```

---

## 4. Shell（Wrapper スクリプト）

### 4.1 必須ヘッダー

```bash
#!/bin/bash
# スクリプト名: adminui-service-restart
# 説明: WebUI からのサービス再起動（allowlist チェック付き）
# 権限: root（sudo経由）
# 呼び出し: adminui-service-restart <service_name>
# 更新日: 2026-02-25

set -euo pipefail  # 必須: エラー即停止・未定義変数エラー・パイプエラー
```

### 4.2 入力検証（必須）

```bash
# 引数チェック
if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <service_name>" >&2
    exit 1
fi

SERVICE_NAME="$1"

# パターンチェック（必須）
if ! [[ "${SERVICE_NAME}" =~ ^[a-zA-Z0-9_\-\.]{1,128}$ ]]; then
    echo "ERROR: Invalid service name: ${SERVICE_NAME}" >&2
    exit 1
fi

# allowlist チェック（必須）
ALLOWLIST=("nginx" "apache2" "mysql" "postgresql" "redis-server")
ALLOWED=false
for svc in "${ALLOWLIST[@]}"; do
    if [[ "${SERVICE_NAME}" == "${svc}" ]]; then
        ALLOWED=true
        break
    fi
done

if [[ "${ALLOWED}" != "true" ]]; then
    echo "ERROR: Service not in allowlist: ${SERVICE_NAME}" >&2
    exit 1
fi
```

### 4.3 実行・ログ記録

```bash
# 実行前ログ（必須）
logger -t adminui-wrapper \
    "ACTION=restart SERVICE=${SERVICE_NAME} USER=${SUDO_USER:-unknown}"

# コマンド実行（変数は引数として、クォート必須）
timeout 30 systemctl restart "${SERVICE_NAME}"
EXIT_CODE=$?

# 実行後ログ（必須）
logger -t adminui-wrapper \
    "RESULT=${EXIT_CODE} ACTION=restart SERVICE=${SERVICE_NAME}"

exit ${EXIT_CODE}
```

---

## 5. SQL（データベース）

### 5.1 命名規則

| 種別 | 規則 | 例 |
|------|------|----|
| テーブル名 | snake_case（複数形） | `audit_logs` |
| カラム名 | snake_case | `created_at` |
| インデックス | `idx_テーブル名_カラム名` | `idx_users_username` |
| 外部キー | `fk_テーブル名_参照テーブル名` | `fk_users_roles` |

### 5.2 セキュリティルール

```python
# ❌ 禁止: 文字列結合によるSQL（SQLインジェクション）
query = f"SELECT * FROM users WHERE username = '{username}'"

# ✅ 必須: パラメータバインディング（SQLAlchemy ORM）
user = db.query(User).filter(User.username == username).first()

# ✅ 必須: Raw SQLを使う場合はバインド変数
result = db.execute(
    text("SELECT * FROM users WHERE username = :username"),
    {"username": username}
)
```

---

## 6. Git コミット規約

### 6.1 コミットメッセージ形式

```
<type>(<scope>): <subject>

<body>（任意）

<footer>（任意）
```

**type 一覧**:

| type | 用途 |
|------|------|
| `feat` | 新機能追加 |
| `fix` | バグ修正 |
| `sec` | セキュリティ修正（最優先） |
| `refactor` | リファクタリング |
| `test` | テスト追加・修正 |
| `docs` | ドキュメント更新 |
| `chore` | ビルド・設定変更 |

**例**:
```
feat(services): サービス再起動APIのallowlistチェック追加

- allowlist.yaml から許可サービスを読み込む
- 未定義サービスへのリクエストは403を返す

Closes #123
```

### 6.2 ブランチ戦略

```
main          ← 本番リリース（直接プッシュ禁止）
  └── develop ← 開発統合ブランチ
        └── feature/issue-123-service-restart  ← 機能開発
        └── fix/issue-456-login-bug            ← バグ修正
        └── sec/issue-789-xss-fix              ← セキュリティ修正
```

---

## 7. コードレビュー基準

### 7.1 必須確認項目

- [ ] セキュリティルールに違反していないか（特に shell=True, eval 等）
- [ ] 全入力値のバリデーションが実装されているか
- [ ] テストが追加・更新されているか
- [ ] エラーハンドリングが適切か
- [ ] ログに機密情報が含まれていないか
- [ ] 型アノテーションが記述されているか

### 7.2 セキュリティレビュー（必須シナリオ）

- sudo / ラッパー関連の変更
- 認証・認可ロジックの変更
- allowlist の変更
- 新規APIエンドポイントの追加

---

*本文書はLinux管理WebUIサンプルシステムのコーディング規約を定めるものである。*
