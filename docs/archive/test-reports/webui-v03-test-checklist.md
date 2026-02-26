# WebUI v0.3 Test / Ops Checklist

更新日: 2026-02-24

## 1. 事前準備

- 利用形態を先に決める
  - `file://` デモ閲覧: `webui-sample/index.singlefile.html`
  - `http://localhost` 開発/検証: `webui-sample/index.html`
- 詳細は `docs/webui-shared-drive-usage.md` を参照（`Z:` は Linux共有の Windows側ドライブレター前提）
- `webui-sample/index.html` をブラウザで開く
- APIモードを選択
  - `mock`: `...?apiMode=mock`
  - `auto`: `...?apiMode=auto`（Live失敗時にMockフォールバック）
  - `live`: `...?apiMode=live&apiBaseUrl=http://localhost:5012/api`
- もしくは `meta[name="lms-api-base-url"]` / `window.__WEBUI_CONFIG__` で設定

## 2. 契約/構文の自動チェック（ローカル）

```bash
node docs/scripts/openapi-sync-v03.mjs
node docs/scripts/validate-openapi.mjs
node docs/scripts/check-webui-syntax.mjs
```

期待結果:
- `openapi.json` が `v0.3.0-doc-sync`
- 必須 v0.3 パス / ApprovalStatus enum / `x-required-permissions*` が検証OK
- `webui-sample` の ESM 構文と主要DOM要素チェックがOK

## 3. E2E シナリオ（Live API 接続時）

### 3.1 ログイン/セッション

- [ ] 正常ログイン（JWT取得、UI遷移）
- [ ] 不正ログイン（401表示）
- [ ] ログアウト（セッション破棄）
- [ ] `auto` モードで API停止時に Mockへフォールバック

### 3.2 Processes

- [ ] 一覧取得（`/api/v1/processes`）
- [ ] フィルタ（user / min_cpu / min_mem）
- [ ] ソート（cpu / mem / pid / time）
- [ ] 自動更新 ON/OFF
- [ ] エラー時トースト表示

### 3.3 Cron（承認リクエスト）

- [ ] 一覧取得（`GET /api/cron`）
- [ ] 追加申請（`POST /api/cron` -> `approval_pending`）
- [ ] 有効/無効切替申請（`PATCH /api/cron/{job_id}`）
- [ ] 削除申請（`DELETE /api/cron/{job_id}`）
- [ ] allowlist違反/禁止文字/バリデーションエラー表示

### 3.4 Users / Groups（承認リクエスト）

- [ ] Users一覧取得（`GET /api/users`）
- [ ] Groups一覧取得（`GET /api/groups`）
- [ ] User追加申請（`POST /api/users` -> `approval_pending`）
- [ ] パスワード強度バリデーション（フロント）
- [ ] Pydanticエラーのフィールド表示マッピング

### 3.5 Approval Workflow

- [ ] pending / my-requests / history 一覧取得
- [ ] 詳細表示（`GET /api/approval/{request_id}`）
- [ ] approve（成功）
- [ ] reject（理由必須）
- [ ] cancel（申請者本人のみ）
- [ ] self-approval 禁止メッセージ表示
- [ ] 期限切れ / 状態不整合（409）の表示統一

## 4. 監査ログ連携確認

- [ ] 承認ID付き監査ログがバックエンドで記録される
- [ ] 承認操作（approve/reject/cancel/execute）が履歴に反映される
- [ ] UIの承認一覧/詳細と監査履歴の request_id が一致する
- [ ] エラー系（403/409/422）でも監査ログ記録方針どおりになる

## 5. UI 回帰 / アクセシビリティ

- [ ] タブ切替 / モーダル / サイドバー / パンくずの回帰
- [ ] モバイル幅（<= 768px）で崩れない
- [ ] `toast` 読み上げ (`aria-live`) が動作
- [ ] キーボード操作で主要フローが実行可能
- [ ] フォーカス可視化の確認

## 6. 本番向けチェック

- [ ] `apiBaseUrl` を環境注入（テンプレート/`window.__WEBUI_CONFIG__`）
- [ ] 認証トークン保管方針見直し（Cookie優先）
- [ ] CSP / CSRF ポリシー適用
- [ ] 監視 / エラーログ / 相関ID（request_id）導入
- [ ] `live` モード時のフォールバック方針を明示（本番で `auto` を使うかどうか）

## 7. 未実施（このリポジトリでは不可）

- 実バックエンドへの統合テスト実行
- 自動E2E（Playwright/Cypress）導入
- 監査ログDB実データでの検証
