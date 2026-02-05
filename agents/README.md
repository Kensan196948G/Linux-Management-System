# SubAgent 7体構成 運用ガイド

**Linux Management System - SubAgent アーキテクチャ**

---

## 📋 概要

本プロジェクトでは、開発プロセスを7体の SubAgent に分割し、各 Agent が明確な責務を持つことで、**品質・セキュリティ・トレーサビリティ**を担保します。

---

## 🧭 SubAgent 一覧

| # | SubAgent | 役割 | 成果物 |
|---|----------|------|--------|
| 1 | **spec-planner** | 要件・運用定義 | specs/* |
| 2 | **arch-reviewer** | 設計レビュー | design/* |
| 3 | **code-implementer** | 実装 | src/* |
| 4 | **code-reviewer** | 自動レビューゲート | reviews/*.json |
| 5 | **test-designer** | テスト設計 | tests/test_cases.md |
| 6 | **test-reviewer** | テストレビュー | reviews/*.json |
| 7 | **ci-specialist** | CI/リリース | ci/* |

---

## 🔄 ワークフロー全体図

```
ユーザー要求
  ↓
[1] spec-planner: 要件定義
  ↓ specs/* 生成
Hook: on-spec-complete
  ↓
[2] arch-reviewer: 設計レビュー
  ↓ design/* 生成（PASS時）
Hook: on-arch-approved
  ↓
[3] code-implementer: 実装
  ↓ src/* 生成
Hook: on-implementation-complete
  ↓
[4] code-reviewer: コードレビュー
  ↓ reviews/*.json 生成
Hook: on-code-review-result
  ├─ FAIL → code-implementer に差し戻し
  ├─ PASS_WITH_WARNINGS → 人に通知 + test-designer 起動可
  └─ PASS → test-designer 自動起動
        ↓
[5] test-designer: テスト設計
  ↓ tests/test_cases.md 生成
Hook: on-test-design-complete
  ↓
[6] test-reviewer: テストレビュー
  ↓ reviews/*.json 生成
Hook: on-test-review-result
  ├─ FAIL → test-designer に差し戻し
  └─ PASS → ci-specialist 起動
        ↓
[7] ci-specialist: CI/CD設計
  ↓ ci/* 生成
  ↓
リリース判定
```

---

## 🪝 Hooks 一覧

| Hook | トリガー | アクション |
|------|---------|-----------|
| **on-spec-complete** | spec-planner が specs/* を生成 | arch-reviewer 自動起動 |
| **on-arch-approved** | arch-reviewer が PASS 返却 | code-implementer 自動起動 |
| **on-implementation-complete** | code-implementer が完了宣言 | code-reviewer 自動起動 |
| **on-code-review-result** | code-reviewer が結果返却 | PASS → test-designer 起動<br>FAIL → 差し戻し |
| **on-test-design-complete** | test-designer が完了 | test-reviewer 自動起動 |
| **on-test-review-result** | test-reviewer が結果返却 | PASS → ci-specialist 起動<br>FAIL → 差し戻し |

---

## 🔀 並列実行ルール

### 常時並列実行

```
arch-reviewer + (security SubAgent) + (qa SubAgent)
```

設計段階から3者並列でレビュー

### 競合時ロック（逐次実行）

```
code-implementer ⇄ (同一ファイル)
```

同一ファイルへの同時書き込み防止

### 常駐

```
ci-specialist（GitHub Actions 監視）
```

---

## 📂 ディレクトリ構成

```
Linux-Management-Systm/
├── specs/                    # spec-planner 成果物
│   ├── overview.md
│   └── requirements.md
│
├── design/                   # arch-reviewer 成果物
│   ├── architecture.md
│   └── security.md
│
├── src/                      # code-implementer 成果物
│   ├── backend/
│   ├── frontend/
│   └── wrappers/
│
├── tests/                    # test-designer 成果物
│   ├── test_cases.md
│   ├── test_api.py
│   └── test_security.py
│
├── reviews/                  # code-reviewer / test-reviewer 成果物
│   ├── 20260205_feature_001.json
│   └── 20260205_test_review.json
│
└── ci/                       # ci-specialist 成果物
    ├── pipeline.md
    ├── build.ps1
    └── build.sh
```

---

## 🚀 使い方

### 1. 新機能開発の開始

```bash
# 1. spec-planner に要件を伝える
"ユーザー認証機能を追加したい"

# 2. spec-planner が specs/* を生成
# 3. Hooks により自動的に arch-reviewer が起動
# 4. 以降、自動的にワークフローが進行
```

### 2. レビュー失敗時の対応

```bash
# code-reviewer が FAIL を返した場合
# → reviews/*.json を確認
# → blocking_issues を修正
# → code-implementer が再実装
# → 自動的に再レビュー
```

### 3. 並列開発時

```bash
# Git WorkTree を使用
git worktree add ../feature-auth feature/auth
cd ../feature-auth

# code-implementer が feature/auth ブランチで実装
# 他の開発者は別 WorkTree で並列開発可能
```

---

## ✅ 品質ゲート

各 SubAgent には品質ゲートが設定されています：

| SubAgent | 品質ゲート |
|----------|-----------|
| spec-planner | 要件の明確性・測定可能性・セキュリティ要件包含 |
| arch-reviewer | セキュリティ設計・SPOF 排除・SoD 実現 |
| code-implementer | 設計書準拠・CLAUDE.md 遵守 |
| code-reviewer | セキュリティ違反ゼロ・ログ記録必須 |
| test-designer | テスト網羅性 80%以上 |
| test-reviewer | 重要機能の抜け漏れなし |
| ci-specialist | 全テスト PASS・セキュリティ HIGH issue ゼロ |

---

## 🚫 禁止事項（全 SubAgent 共通）

1. **工程スキップ禁止**
   - Hooks を通らない遷移は禁止

2. **仕様外実装禁止**
   - 設計書に書いていないことは実装しない

3. **レビュー FAIL の無視禁止**
   - blocking_issues は必ず修正

4. **セキュリティ原則違反禁止**
   - CLAUDE.md の原則は絶対遵守

---

## 📚 各 SubAgent の詳細

- [01_spec-planner.md](./01_spec-planner.md)
- [02_arch-reviewer.md](./02_arch-reviewer.md)
- [03_code-implementer.md](./03_code-implementer.md)
- [04_code-reviewer.md](./04_code-reviewer.md)
- [05_test-designer.md](./05_test-designer.md)
- [06_test-reviewer.md](./06_test-reviewer.md)
- [07_ci-specialist.md](./07_ci-specialist.md)

---

## 🎯 成功の定義

この SubAgent 7体構成が有効化された環境では：

* ✅ すべての作業は SubAgent 経由で行われる
* ✅ すべての成果物はレビューゲートを通過する
* ✅ すべての判断は証跡として残る
* ✅ セキュリティ違反は工程内で検出・排除される
* ✅ 品質は機械的に測定可能

👉 **「事故らない開発環境」**が完成する。

---

## 🔗 関連ドキュメント

- [CLAUDE.md](../CLAUDE.md) - セキュリティ原則
- [README.md](../README.md) - プロジェクト概要
- [.github/workflows/](../.github/workflows/) - CI/CD 設定

---

**最終更新**: 2026-02-05
