# GitHub Copilot Skills 定義
# Linux Management System - 各モジュール開発スキル

## 📋 Skills 概要

このディレクトリには GitHub Copilot のカスタムスキル定義が含まれます。
各スキルはプロジェクト固有の開発パターンを Copilot に教えるためのものです。

---

## 🧰 利用可能なスキル一覧

| スキル名 | 説明 | 使用場面 |
|---------|------|---------|
| `new-module` | 新モジュール追加テンプレート | 新機能実装時 |
| `wrapper-script` | sudo ラッパースクリプト生成 | 新しいシステム操作追加時 |
| `api-route` | FastAPI ルーター生成 | バックエンドAPI追加時 |
| `test-suite` | テストスイート生成 | テスト作成時 |
| `frontend-page` | フロントエンドページ生成 | UI追加時 |
| `security-audit` | セキュリティ監査 | コードレビュー時 |

---

## 📁 ファイル構成

```
skills/
├── README.md                 # このファイル
├── new-module.md             # 新モジュール追加スキル
├── wrapper-script.md         # ラッパースクリプトスキル
├── api-route.md              # APIルートスキル
├── test-suite.md             # テストスイートスキル
└── security-audit.md         # セキュリティ監査スキル
```
