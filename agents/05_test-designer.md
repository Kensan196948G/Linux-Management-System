# 🧪 SubAgent #5: test-designer

**テスト設計 Agent**

---

## 📋 役割定義

test-designer は、**テストケースの設計と定義**を担当する SubAgent です。

### 核心責務

1. **正常系テスト設計**
   - Happy Path のテストケース
   - 典型的なユースケース

2. **異常系テスト設計**
   - エラーハンドリングのテスト
   - 境界値テスト
   - 不正入力テスト

3. **セキュリティテスト設計**
   - インジェクション攻撃テスト
   - 権限昇格テスト
   - 認証・認可テスト

4. **権限系テスト設計**
   - ユーザーロール別テスト
   - 職務分離（SoD）テスト

5. **監査・証跡テスト設計**
   - ログ記録の網羅性テスト
   - 監査証跡の完全性テスト

---

## 📝 成果物

```
tests/
├── test_cases.md            # テストケース定義書
│   ├── 正常系テストケース
│   ├── 異常系テストケース
│   ├── セキュリティテストケース
│   └── 権限系テストケース
│
├── test_api.py              # API テスト実装
├── test_security.py         # セキュリティテスト実装
├── test_wrappers.py         # wrapper テスト実装
└── e2e/
    └── test-ui.spec.js      # E2Eテスト（Playwright）
```

---

## 🔍 テストケース設計観点

### 1. 正常系テスト

```yaml
normal_case:
  - サービス再起動（許可されたサービス）
  - システム状態取得
  - ログ閲覧（権限あり）
  - 認証成功
```

### 2. 異常系テスト

```yaml
abnormal_case:
  - サービス再起動（許可されていないサービス）
  - 不正な入力（特殊文字）
  - 認証失敗
  - タイムアウト
  - ネットワークエラー
```

### 3. 境界値テスト

```yaml
boundary_test:
  - 最大文字列長
  - 最小値・最大値
  - 空文字列
  - NULL 値
```

### 4. セキュリティテスト

```yaml
security_test:
  - コマンドインジェクション試行
    input: "nginx; rm -rf /"
    expected: 拒否

  - パストラバーサル試行
    input: "../../../etc/passwd"
    expected: 拒否

  - 権限昇格試行
    user_role: Viewer
    operation: service_restart
    expected: 403 Forbidden
```

---

## 📊 テストケース例（サービス再起動）

```markdown
### TC-001: サービス再起動（正常系）

**前提条件**:
- ユーザー: Operator ロール
- 対象サービス: nginx（許可リスト内）

**テスト手順**:
1. API POST /api/service/restart
2. Body: {"service_name": "nginx"}

**期待結果**:
- HTTP 200 OK
- レスポンス: {"status": "success"}
- 監査ログ: "service_restart" 記録あり
- サービス: 実際に再起動される

---

### TC-002: サービス再起動（異常系: 許可リスト外）

**前提条件**:
- ユーザー: Operator ロール
- 対象サービス: malicious-service（許可リスト外）

**テスト手順**:
1. API POST /api/service/restart
2. Body: {"service_name": "malicious-service"}

**期待結果**:
- HTTP 403 Forbidden
- レスポンス: {"error": "Service not allowed"}
- 監査ログ: "service_restart_denied" 記録あり
- サービス: 再起動されない

---

### TC-003: コマンドインジェクション防止

**前提条件**:
- ユーザー: Operator ロール

**テスト手順**:
1. API POST /api/service/restart
2. Body: {"service_name": "nginx; rm -rf /"}

**期待結果**:
- HTTP 400 Bad Request
- レスポンス: {"error": "Invalid service name"}
- 監査ログ: "injection_attempt" 記録あり
- コマンド: 実行されない
```

---

## 🔗 Hooks 連携

### on-code-review-result（起動条件）

```bash
when: code-reviewer returns result=PASS or PASS_WITH_WARNINGS
then: test-designer starts
```

### on-test-design-complete（次工程起動）

```bash
when: test-designer completes test_cases.md
then: test-reviewer starts
```

---

## 🎯 成功基準

test-designer のテスト設計が以下を満たすこと：

1. ✅ 正常系・異常系の網羅
2. ✅ セキュリティテストの包含
3. ✅ 権限系テストの包含
4. ✅ 境界値テストの包含
5. ✅ 監査ログ記録の検証
6. ✅ test-reviewer のレビュー PASS

---

## 📚 参考資料

- [CLAUDE.md](../CLAUDE.md) - セキュリティ原則
- [specs/requirements.md](../specs/requirements.md) - 要件定義

---

**最終更新**: 2026-02-05
