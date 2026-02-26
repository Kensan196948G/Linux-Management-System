# Documentation

Linux管理WebUI プロジェクト ドキュメント集

最終更新: 2026-02-25

---

## ディレクトリ構成

```
docs/
├── README.md                          ← 本ファイル
├── 要件定義書_詳細設計仕様書.md           ← プロジェクト要件・設計（中核文書）
├── 開発環境仕様書.md                     ← ClaudeCode 開発環境詳細
│
├── webui-sample-docs/                 ← ★ WebUIサンプル仕様書集（全15種）
│   ├── README.md                      ← 仕様書一覧インデックス
│   ├── 01_requirements-overview.md   ← 要件定義書（概要）
│   ├── 02_functional-requirements.md ← 機能要件定義書
│   ├── 03_nonfunctional-requirements.md ← 非機能要件定義書
│   ├── 04_system-architecture.md     ← システムアーキテクチャ設計書
│   ├── 05_screen-design.md           ← 画面設計書（UI/UX仕様）
│   ├── 06_api-specification.md       ← API仕様書
│   ├── 07_database-design.md         ← データベース設計書
│   ├── 08_security-design.md         ← セキュリティ設計書
│   ├── 09_test-specification.md      ← テスト仕様書
│   ├── 10_deployment-procedure.md    ← デプロイ・リリース手順書
│   ├── 11_operations-manual.md       ← 運用・保守設計書
│   ├── 12_user-manual.md             ← ユーザー操作マニュアル
│   ├── 13_coding-standards.md        ← コーディング規約
│   ├── 14_dev-environment.md         ← 開発環境構築手順書
│   └── 15_change-management.md       ← 変更管理・バージョン管理仕様書
│
├── api/                               ← API仕様・OpenAPI
│   ├── api-reference.md
│   ├── approval-api-spec.md
│   ├── openapi.json
│   └── processes-api-spec.yaml
│
├── architecture/                      ← アーキテクチャ・設計文書
│   ├── approval-workflow-design.md
│   ├── cron-jobs-design.md
│   ├── login-flow-analysis.md
│   ├── menu-structure-redesign.md
│   ├── processes-implementation-guide.md
│   ├── processes-module-design.md
│   ├── processes-module-requirements.md
│   ├── processes-review-checklist.md
│   ├── service-management.md
│   └── users-groups-design.md
│
├── security/                          ← セキュリティ文書
│   ├── FINAL_SECURITY_REVIEW_PROCESSES.md
│   ├── PARALLEL_REVIEW_PROTOCOL.md
│   ├── SECURITY_CHECKLIST_PROCESSES.md
│   ├── SECURITY_REQUIREMENTS_PROCESSES.md
│   ├── SECURITY_TEST_TEMPLATE_PROCESSES.md
│   ├── THREAT_ANALYSIS_PROCESSES.md
│   ├── comprehensive-security-review-2026-02-06.md
│   ├── cron-allowlist-policy.md
│   ├── cron-jobs-threat-analysis.md
│   ├── improvement-proposals.md
│   ├── pr-review-summary.md
│   ├── processes-security-checklist.md
│   ├── sudoers-config.md
│   ├── users-groups-allowlist-policy.md
│   └── users-groups-threat-analysis.md
│
├── database/                          ← データベース設計
│   └── approval-schema.sql
│
├── guides/                            ← How-to ガイド
│   ├── menu-i18n-guide.md
│   ├── webui-shared-drive-usage.md
│   └── worktree-guide.md
│
├── scripts/                           ← ユーティリティスクリプト
│   ├── build-webui-singlefile.mjs
│   ├── check-shared-drive-compat.mjs
│   ├── check-webui-syntax.mjs
│   ├── compare-openapi-docs-vs-runtime.mjs
│   ├── generate_openapi.py
│   ├── openapi-sync-v03.mjs
│   ├── run-shared-drive-checks.cmd
│   ├── run-shared-drive-checks.mjs
│   ├── run-shared-drive-checks.sh
│   └── validate-openapi.mjs
│
└── archive/                           ← 過去ドキュメント（参照用）
    ├── SESSION_SUMMARY_2026-02-14.md
    ├── reports/
    │   ├── ci-failure-analysis.md
    │   ├── menu-redesign-verification.md
    │   ├── v03-integration-issues-found.md
    │   └── v03-integration-review-report.md
    └── test-reports/
        ├── 2026-02-06-agent-teams/
        ├── e2e-test-report.md
        ├── webui-comprehensive-test-final-report.md
        ├── webui-test-final-summary.md
        └── webui-v03-test-checklist.md
```

---

## クイックリファレンス

| 目的 | 参照先 |
|------|--------|
| WebUIの全仕様書を確認 | [webui-sample-docs/README.md](./webui-sample-docs/README.md) |
| プロジェクト要件・設計 | [要件定義書_詳細設計仕様書.md](./要件定義書_詳細設計仕様書.md) |
| 開発環境の構築 | [webui-sample-docs/14_dev-environment.md](./webui-sample-docs/14_dev-environment.md) |
| セキュリティ設計 | [webui-sample-docs/08_security-design.md](./webui-sample-docs/08_security-design.md) |
| API仕様 | [api/](./api/) / [webui-sample-docs/06_api-specification.md](./webui-sample-docs/06_api-specification.md) |
| デプロイ手順 | [webui-sample-docs/10_deployment-procedure.md](./webui-sample-docs/10_deployment-procedure.md) |

---

## プロジェクト全体ドキュメント

- [../README.md](../README.md) - プロジェクト概要
- [../CLAUDE.md](../CLAUDE.md) - ClaudeCode 開発仕様書
- [../SECURITY.md](../SECURITY.md) - セキュリティポリシー
