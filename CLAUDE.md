# CLAUDE.md - ClaudeCode 開発仕様書

**Webmin風 Linux管理WebUI - セキュリティファースト開発ガイド**

---

## 🎯 プロジェクト使命（必読）

> このシステムは「Linuxを操作するツール」ではなく、
> 「Linux運用を統制する仕組み」である。

**開発の最優先事項**: 便利さより**安全性**、機能追加より**統制強化**

---

## 🔒 セキュリティ原則（絶対遵守）

### 1. Allowlist First（許可リスト優先）

```
✅ 明示的に許可されたもののみ実行
❌ 定義されていない操作は全拒否
```

**実装例**:
```python
# ✅ 良い例
ALLOWED_SERVICES = ["nginx", "postgresql", "redis"]
if service_name in ALLOWED_SERVICES:
    execute_restart(service_name)

# ❌ 悪い例
execute_restart(user_input)  # 任意のサービス名を受け入れ
```

### 2. Deny by Default（デフォルト拒否）

```python
# ✅ 良い例
def can_execute(operation):
    return operation in EXPLICIT_ALLOWED_OPS

# ❌ 悪い例
def can_execute(operation):
    return operation not in BLACKLIST  # ブラックリスト方式は禁止
```

### 3. Shell禁止（shell=True 全面禁止）

```python
# ✅ 良い例
subprocess.run(["/usr/local/sbin/adminui-status"], check=True)

# ❌ 悪い例
subprocess.run("systemctl status nginx", shell=True)  # 絶対禁止
```

### 4. sudo最小化（ラッパー経由必須）

```python
# ✅ 良い例
subprocess.run(["sudo", "/usr/local/sbin/adminui-service-restart", "nginx"])

# ❌ 悪い例
subprocess.run(["sudo", "systemctl", "restart", "nginx"])  # 直接実行禁止
```

### 5. 監査証跡（全操作ログ）

```python
# 必須ログ項目
audit_log = {
    "timestamp": "2026-02-05T12:34:56Z",
    "user_id": "admin@example.com",
    "operation": "service_restart",
    "target": "nginx",
    "result": "success",
    "stdout": "...",
    "stderr": ""
}
```

---

## 🚫 禁止操作（即時拒否・即時警告）

### コード上の禁止事項

```python
# ❌ 即座に拒否
subprocess.run(..., shell=True)           # shell=True
os.system("...")                          # os.system
eval(user_input)                          # eval
exec(user_input)                          # exec
__import__(user_input)                    # 動的import
```

### 特殊文字（入力バリデーション）

```python
# ❌ 以下の文字が含まれる入力は即座に拒否
FORBIDDEN_CHARS = [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?", "{", "}", "[", "]"]

def validate_input(user_input: str) -> bool:
    for char in FORBIDDEN_CHARS:
        if char in user_input:
            raise SecurityError(f"Forbidden character detected: {char}")
    return True
```

### 操作の禁止

- ❌ 任意コマンドの実行
- ❌ bash / sh / zsh の起動
- ❌ /etc 配下の直接編集
- ❌ ユーザーアカウントの追加・削除
- ❌ sudo権限の追加・変更
- ❌ sudoers ファイルの編集（人間承認必須）

---

## 👥 SubAgent 7体構成（役割分担）

### 1. @Planner（プランナー）
**役割**: 要件分解・タスク設計
- ユーザー要求を具体的なタスクに分解
- 実装順序の決定
- リスク分析

**責任範囲**: 計画フェーズ全般

### 2. @Architect（アーキテクト）
**役割**: 全体設計・セキュリティアーキテクチャ
- システム全体の構造設計
- API設計
- データベーススキーマ設計
- セキュリティ境界の定義

**責任範囲**: 設計フェーズ、設計レビュー

### 3. @Backend（バックエンド）
**役割**: API実装・sudo制御・wrapper開発
- FastAPI エンドポイント実装
- 認証・認可ロジック
- sudoラッパースクリプト作成
- データベース操作

**責任範囲**: backend/ ディレクトリ、wrappers/ ディレクトリ

### 4. @Frontend（フロントエンド）
**役割**: WebUI実装
- HTML/CSS/JavaScript 実装
- ユーザー入力のクライアント側検証
- API連携
- UI/UX改善

**責任範囲**: frontend/ ディレクトリ

### 5. @Security（セキュリティ）
**役割**: 脅威分析・拒否基準検証・セキュリティレビュー
- 全コード変更のセキュリティ検証
- 脆弱性パターン検出
- セキュリティテストケース作成
- 監査ログ設計

**責任範囲**: **全てのコード変更に対する並列検証**

**重要**: Security SubAgentは他のSubAgentと**必ず並列実行**

### 6. @QA（品質保証）
**役割**: テスト設計・自動テスト実装
- pytest テストケース作成
- カバレッジ向上
- リグレッションテスト
- E2Eテスト

**責任範囲**: tests/ ディレクトリ

### 7. @CIManager（CI管理者）
**役割**: GitHub Actions制御・自動修復
- CI/CDパイプライン管理
- 失敗ログ解析
- 自動修復スクリプト作成
- ワークフロー最適化

**責任範囲**: .github/workflows/ ディレクトリ

---

## 🔄 開発フロー（標準手順）

### フェーズ1: 要件受領・分析
```
User Request
  ↓
@Planner: タスク分解
  ↓ 並列
@Architect: 設計案作成
@Security: 脅威分析（並列実行）
```

### フェーズ2: 実装
```
@Backend: コード実装
  ↓ 並列
@Security: コードレビュー（並列実行）
@QA: テスト作成（並列実行）
```

### フェーズ3: 検証
```
@QA: テスト実行
  ↓
@Security: セキュリティ再検証
  ↓
結果報告
```

### フェーズ4: コミット前チェック
```
1. セキュリティチェック（@Security）
2. テスト全実行（@QA）
3. Lint・フォーマット
4. 人間承認（必要な場合）
  ↓
git commit
```

---

## 📋 Git / GitHub 操作ポリシー

### ローカルで自動実行可能な操作

```bash
# ✅ 承認不要（情報取得のみ）
git status
git diff
git log
git branch -l

# ✅ 承認不要（開発作業）
pytest tests/
bandit -r backend/
black backend/
flake8 backend/
```

### 必ず確認を求める操作

```bash
# ⚠️ 人間承認必須
git add .
git commit -m "..."
git push
git push --force
git merge
git rebase
```

### GitHub上の操作（全て承認必須）

- Pull Request の作成
- Pull Request へのコメント
- Issue の作成・更新
- GitHub Actions の手動トリガー
- ブランチ保護ルールの変更

---

## 🧪 テスト要件

### テストカバレッジ目標

| コンポーネント | カバレッジ目標 |
|--------------|-------------|
| backend/core/ | **90%以上** |
| backend/api/ | **85%以上** |
| wrappers/ | **100%** （シェルスクリプトは全パターン） |

### 必須テストケース

#### セキュリティテスト
```python
def test_reject_shell_injection():
    """特殊文字を含む入力を拒否すること"""
    malicious_input = "nginx; rm -rf /"
    with pytest.raises(SecurityError):
        validate_service_name(malicious_input)

def test_allowlist_only():
    """許可リスト外のサービスを拒否すること"""
    with pytest.raises(PermissionError):
        restart_service("malicious-service")
```

#### wrapper テスト
```bash
# wrappers/test/test-adminui-service-restart.sh
#!/bin/bash
set -euo pipefail

# 正常系
./adminui-service-restart nginx
echo "✅ Normal case passed"

# 異常系: 許可リスト外
if ./adminui-service-restart unknown-service 2>/dev/null; then
    echo "❌ Should reject unknown service"
    exit 1
fi
echo "✅ Reject unknown service"

# 異常系: 特殊文字
if ./adminui-service-restart "nginx; ls" 2>/dev/null; then
    echo "❌ Should reject special characters"
    exit 1
fi
echo "✅ Reject special characters"
```

---

## 🚨 GitHub Actions 想定

### CI Workflow（全Push時）

```yaml
# .github/workflows/ci.yml で実行されるコマンド
1. pytest tests/ -v --cov=backend --cov-report=html
2. bandit -r backend/ -f json -o bandit-report.json
3. black --check backend/
4. flake8 backend/
5. shellcheck wrappers/*.sh
```

### Security Audit Workflow（全PR時）

```yaml
# .github/workflows/security-audit.yml で実行される検証
1. grep -r "shell=True" backend/ （検出 → 即失敗）
2. grep -r '\$(' backend/api/ （検出 → 即失敗）
3. grep -r "bash -c" wrappers/ （検出 → 即失敗）
4. bandit -ll -r backend/
```

### ローカル開発時の事前チェック

コミット前に以下を**必ず実行**:
```bash
# セキュリティチェック
grep -r "shell=True" backend/ && echo "❌ shell=True detected" || echo "✅ No shell=True"

# テスト
pytest tests/ -v

# 静的解析
bandit -r backend/
flake8 backend/
```

---

## 🎓 人間承認必須ポイント（CRITICAL）

以下の変更は**必ず人間による明示的な承認**を得てから実装すること:

### 1. sudoers 関連
- ❗ sudoersファイルの変更
- ❗ sudo許可コマンドの追加
- ❗ NOPASSWD設定の変更

### 2. 新規操作の追加
- ❗ 新しいroot操作の追加
- ❗ 新しいsudoラッパーの作成
- ❗ 許可リストへのサービス追加

### 3. 承認フロー
- ❗ 承認ロジックの変更
- ❗ ユーザーロールの変更
- ❗ 権限マトリクスの変更

### 4. セキュリティ境界
- ❗ 入力バリデーションルールの緩和
- ❗ 特殊文字許可の追加
- ❗ allowlistからdenylistへの変更（原則禁止）

---

## 📝 コーディング規約

### Python（backend）

```python
# ✅ 良い例: 型ヒント必須
def restart_service(service_name: str) -> dict:
    """サービスを再起動する

    Args:
        service_name: 再起動対象サービス名（allowlist検証済み）

    Returns:
        実行結果の辞書

    Raises:
        SecurityError: 不正な入力
        PermissionError: 権限不足
    """
    validate_service_name(service_name)
    # ...

# ❌ 悪い例: 型ヒントなし、docstringなし
def restart_service(service_name):
    # ...
```

### Bash（wrappers）

```bash
# ✅ 良い例: 配列使用、引用符徹底
#!/bin/bash
set -euo pipefail

SERVICE_NAME="$1"
ALLOWED_SERVICES=("nginx" "postgresql" "redis")

# 配列で許可リスト検証
if [[ ! " ${ALLOWED_SERVICES[@]} " =~ " ${SERVICE_NAME} " ]]; then
    echo "Error: Service not allowed" >&2
    exit 1
fi

# 配列渡し（shell展開なし）
sudo systemctl restart "${SERVICE_NAME}"

# ❌ 悪い例: 文字列結合、引用符なし
#!/bin/bash
sudo systemctl restart $1  # 危険: 引数展開攻撃可能
```

---

## 🧠 Memory（永続記憶）戦略

### 記憶すべき内容

- ✅ 要件定義の合意事項
- ✅ セキュリティ拒否基準
- ✅ sudo制御ルール
- ✅ 過去の修復履歴
- ✅ レビューでの指摘事項

### 記憶してはいけない内容

- ❌ 一時的な回避策（正解として保存しない）
- ❌ root権限拡張の提案
- ❌ セキュリティ基準の緩和案

---

## 🔍 SubAgent 並列実行ルール

### 常時並列実行

```
@Architect + @Security + @QA
```
設計段階から常に3者並列でレビュー

### 競合時ロック（逐次実行）

```
@Backend ⇄ @Frontend
```
同一ファイルを触る可能性がある場合はロック

### 常駐

```
@CIManager
```
GitHub Actionsの監視・修復対応のため常駐

---

## 📚 参照ドキュメント

開発時は以下を常に参照すること:

1. [README.md](./README.md) - プロジェクト概要
2. [docs/要件定義書_詳細設計仕様書.md](./docs/要件定義書_詳細設計仕様書.md) - 要件・設計詳細
3. [SECURITY.md](./SECURITY.md) - セキュリティポリシー
4. [.github/workflows/](..github/workflows/) - CI設定

---

## ⚙️ 開発環境構築

```bash
# Python仮想環境
python3 -m venv venv
source venv/bin/activate

# 依存関係インストール
pip install -r backend/requirements.txt
pip install -r backend/requirements-dev.txt

# Pre-commit hooks（推奨）
pre-commit install
```

---

## 🎯 開発フェーズとゴール

### v0.1（参照系のみ）
- ✅ システム状態取得
- ✅ サービス状態表示
- ✅ ログ閲覧
- ❌ 操作機能なし

**セキュリティ目標**: 読み取り専用で脆弱性ゼロ

### v0.2（限定操作）
- ✅ 許可サービスの再起動のみ
- ✅ sudoラッパー経由のみ
- ✅ 全操作のログ記録

**セキュリティ目標**: 操作はallowlistのみ、監査証跡100%

### v0.3（承認フロー）
- ✅ 危険操作の承認フロー
- ✅ 多段階承認
- ✅ 承認履歴の記録

**セキュリティ目標**: 職務分離（SoD）の実現

---

## 🚀 ClaudeCode 起動時プロンプト（推奨）

```
あなたはLinux管理WebUIを開発するClaudeCodeです。

本プロジェクトはroot操作を最小化し、
sudo allowlist と監査証跡を最優先します。

SubAgent 7体構成を有効化し、
@Security / @Architect / @QA を常時並列実行してください。

仕様逸脱、危険操作、sudo拡張は
必ず停止・警告・人間承認を要求してください。

CLAUDE.md のセキュリティ原則を厳守してください。
```

---

## 🔐 最後に（開発者への警告）

> この開発環境は「速く作るため」ではなく、
> **「壊れず、暴走せず、説明できるため」** に設計されている。

**全ての開発者・AI Agentへ**:
- 便利さを求めてセキュリティを犠牲にしない
- 「動けばいい」ではなく「安全に動く」を目指す
- 疑わしい場合は実装せず、人間に確認する

**このシステムは本番環境でroot権限を扱います。**
**一つの脆弱性が組織全体のセキュリティ侵害につながります。**

---

## 📦 モジュール実装ガイドライン（100+モジュール対応）

### 対象範囲

本システムは Webmin 互換の包括的な Linux 管理を目指し、**100個以上のモジュール**を段階的に実装します。

**対象OS**: Ubuntu Linux

### モジュールカテゴリ

1. **Linux Management System** - システム全体設定
2. **System** - 基幹機能（Users, Cron, Logs, Processes, etc.）
3. **Servers** - サービス管理（Apache, MySQL, PostgreSQL, etc.）
4. **Networking** - ネットワーク（Firewall, Routing, etc.）
5. **Hardware** - ハードウェア（Disk, SMART, Sensors, etc.）
6. **Cluster / Tools** - クラスタ・ツール

### 新モジュール実装時の必須ルール

#### 1. セキュリティ評価（最優先）

```
新モジュール実装前に必ず確認:
- ❓ root 権限が必要か？
- ❓ 既存の sudo ラッパーで対応可能か？
- ❓ 新しいラッパーが必要か？
- ❓ allowlist に追加すべきコマンドは？
- ❓ 特殊文字を含む入力があるか？
- ❓ ファイル操作は安全か（パストラバーサル対策）？
```

#### 2. 禁止モジュール（実装不可）

```
❌ Command Shell - 任意コマンド実行
❌ Direct /etc editing - 直接編集
❌ User/sudo 追加 - セキュリティリスク
❌ Package removal - システム破壊リスク
```

#### 3. 制限付きモジュール（人間承認必須）

```
⚠️ Custom Commands - 事前定義のみ
⚠️ File Manager - 特定ディレクトリのみ
⚠️ Scheduled Commands - allowlist のみ
⚠️ Firewall Settings - 誤設定防止
```

#### 4. 実装テンプレート

新モジュール実装時は以下の順序で進める：

```
1. @spec-planner: モジュール要件定義
   - 目的・スコープ
   - セキュリティ評価
   - allowlist 定義

2. @arch-reviewer: 設計レビュー
   - sudo ラッパー設計
   - 入力検証設計
   - エラーハンドリング

3. @code-implementer: 実装
   - ラッパースクリプト作成
   - API エンドポイント追加
   - フロントエンド UI 追加

4. @code-reviewer: レビュー
   - セキュリティ原則遵守確認
   - テストカバレッジ確認

5. @test-designer: テスト作成
   - 正常系・異常系
   - セキュリティテスト
   - allowlist 検証

6. @ci-specialist: CI 統合
```

### モジュール優先度

```
Phase 1 (v0.1) - 完了済み:
  ✅ System Status
  ✅ Service Restart
  ✅ Log Viewing

Phase 2 (v0.2) - 次の実装:
  🔴 Users and Groups
  🔴 Cron Jobs
  🔴 Network Configuration
  🟡 Running Processes

Phase 3 (v0.3):
  🟡 MySQL/PostgreSQL
  🟡 Firewall
  🟡 Package Updates
  🟡 Approval Workflow

Phase 4-5 (v0.4-v0.5):
  🟢 Advanced Server Management
  🟢 Cluster Management
```

### 例：新モジュール実装チェックリスト

```yaml
module_name: Users and Groups Management
category: System
security_risk: HIGH（ユーザー追加・削除）

implementation_checklist:
  - [ ] sudo ラッパー作成（adminui-user-*.sh）
  - [ ] allowlist 定義（追加可能ユーザー、グループ）
  - [ ] 入力検証（ユーザー名、パスワード強度）
  - [ ] API エンドポイント実装
  - [ ] フロントエンド UI 実装
  - [ ] セキュリティテスト（15+ テスト）
  - [ ] 監査ログ記録
  - [ ] 承認フロー（Admin のみ実行可能）
  - [ ] 人間レビュー・承認
```

---

**📌 本ドキュメントは ClaudeCode の全セッションで参照されます。**
**変更時は必ず Git管理し、変更履歴を残してください。**
