# WebUI サンプル仕様書集

Linux管理WebUI サンプルシステムの全仕様書一覧です。

**対象システム**: Webminライク Linux運用管理WebUI（サンプル）
**作成日**: 2026-02-25

---

## 仕様書一覧

### 要件・設計フェーズ

| ファイル | 内容 | 文書番号 |
|---------|------|---------|
| [01_requirements-overview.md](./01_requirements-overview.md) | **要件定義書（概要）** - 背景・目的・主要要件サマリー | WEBUI-REQ-001 |
| [02_functional-requirements.md](./02_functional-requirements.md) | **機能要件定義書** - 参照系・操作系・管理系の全機能要件 | WEBUI-REQ-002 |
| [03_nonfunctional-requirements.md](./03_nonfunctional-requirements.md) | **非機能要件定義書** - 性能・可用性・セキュリティ・運用要件 | WEBUI-REQ-003 |
| [04_system-architecture.md](./04_system-architecture.md) | **システムアーキテクチャ設計書** - 全体構成・コンポーネント・技術スタック | WEBUI-ARC-001 |

### UI・API フェーズ

| ファイル | 内容 | 文書番号 |
|---------|------|---------|
| [05_screen-design.md](./05_screen-design.md) | **画面設計書（UI/UX仕様）** - 画面一覧・レイアウト・各画面設計 | WEBUI-UI-001 |
| [06_api-specification.md](./06_api-specification.md) | **API仕様書** - 全エンドポイント・リクエスト/レスポンス仕様 | WEBUI-API-001 |

### データ・セキュリティフェーズ

| ファイル | 内容 | 文書番号 |
|---------|------|---------|
| [07_database-design.md](./07_database-design.md) | **データベース設計書** - テーブル定義・ER図・データ保管ポリシー | WEBUI-DB-001 |
| [08_security-design.md](./08_security-design.md) | **セキュリティ設計書** - 認証・認可・インジェクション対策・監査 | WEBUI-SEC-001 |

### テスト・リリースフェーズ

| ファイル | 内容 | 文書番号 |
|---------|------|---------|
| [09_test-specification.md](./09_test-specification.md) | **テスト仕様書** - ユニット・統合・E2E・セキュリティテスト仕様 | WEBUI-TST-001 |
| [10_deployment-procedure.md](./10_deployment-procedure.md) | **デプロイ・リリース手順書** - 本番デプロイ・ロールバック手順 | WEBUI-DEP-001 |

### 運用・開発フェーズ

| ファイル | 内容 | 文書番号 |
|---------|------|---------|
| [11_operations-manual.md](./11_operations-manual.md) | **運用・保守設計書** - 日常運用・バックアップ・監視・障害対応 | WEBUI-OPS-001 |
| [12_user-manual.md](./12_user-manual.md) | **ユーザー操作マニュアル** - エンドユーザー向け操作ガイド | WEBUI-USR-001 |
| [13_coding-standards.md](./13_coding-standards.md) | **コーディング規約** - Python・JS・Shell・SQLの標準規約 | WEBUI-DEV-001 |
| [14_dev-environment.md](./14_dev-environment.md) | **開発環境構築手順書** - ローカル開発環境のセットアップ手順 | WEBUI-DEV-002 |
| [15_change-management.md](./15_change-management.md) | **変更管理・バージョン管理仕様書** - 変更フロー・RFC・リリースノート規約 | WEBUI-CHG-001 |

---

## 仕様書の種類と役割

```
要件定義書（概要）
  └── 機能要件定義書      ← 何を作るか
  └── 非機能要件定義書    ← どれくらいの品質で作るか
        ↓
システムアーキテクチャ設計書  ← どう作るか（全体像）
  ├── 画面設計書          ← 画面をどう作るか
  ├── API仕様書           ← APIをどう作るか
  ├── データベース設計書   ← DBをどう作るか
  └── セキュリティ設計書  ← 安全をどう確保するか
        ↓
テスト仕様書             ← どう確認するか
デプロイ・リリース手順書  ← どう本番に届けるか
        ↓
運用・保守設計書          ← どう維持するか
ユーザー操作マニュアル    ← どう使うか
コーディング規約          ← どう書くか
開発環境構築手順書        ← どう開発環境を作るか
変更管理・バージョン管理  ← どう変更を管理するか
```

---

## 参照順序（推奨）

1. **01_requirements-overview.md** - システム全体像の把握
2. **08_security-design.md** - セキュリティ設計の理解（最重要）
3. **04_system-architecture.md** - アーキテクチャの理解
4. 目的に応じた各設計書を参照

---

*本ディレクトリはLinux管理WebUIサンプルシステムの仕様書集である。*
