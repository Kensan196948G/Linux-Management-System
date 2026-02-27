# GitHub Copilot Agent Teams 設定
# Linux Management System - SubAgent 7体構成

## 📋 Teams 概要

このディレクトリには GitHub Copilot の Agent Teams 設定が含まれます。
SubAgent 7体が役割分担して高品質・高セキュリティな開発を実現します。

## 👥 チーム構成

```
Linux Management System Dev Team
├── spec-planner    (要件定義)
├── arch-reviewer   (設計レビュー)
├── code-implementer (実装)
├── code-reviewer   (コードレビュー)
├── test-designer   (テスト設計)
├── test-reviewer   (テストレビュー)
└── ci-specialist   (CI/CD管理)
```

## 📂 ファイル構成

```
teams/
├── README.md          # このファイル
└── dev-team.md        # 開発チーム設定
```

## 🔄 並列実行ルール

| パターン | 実行方式 |
|---------|---------|
| spec-planner + arch-reviewer + security | 並列OK |
| code-implementer | 排他（ファイルロック必須） |
| test-designer + test-reviewer | 並列OK |
| ci-specialist | 常駐（GitHub Actions監視） |

## 🪝 Hooks との連携

各 Agent の完了時に `hooks/workflow-engine.sh` を呼び出して
次の Agent を自動起動します。詳細は `hooks/README.md` を参照。
