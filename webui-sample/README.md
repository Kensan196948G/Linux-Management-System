# webui-sample

HTML + JavaScript + CSS の静的 WebUI サンプルです。`docs` の設計/仕様に基づく UI モックに、v0.3 向け API 接続（Live/Mock フォールバック）を追加しています。

## API接続モード

- `auto`（既定）: API失敗時にMockへフォールバック
- `live`: API必須（失敗時はエラー表示）
- `mock`: 常にモックデータ

## 開き方（重要）

### 正式デモ入口（`file://`）

- `webui-sample/index.singlefile.html`

`file://` デモ運用では、まずこちらを使用してください。

### モジュール版（開発/検証）

`file:///.../index.html` の直開きは、ブラウザの ES Module 制約（`origin: null` / CORS）で `app.js` の import が失敗し、ログインできない場合があります。

単一ファイル版（モジュールなし、CSS/JS内包）:

- `webui-sample/index.singlefile.html`

PowerShell 例:

```powershell
cd webui-sample
python -m http.server 8080
```

その後、`http://localhost:8080/` を開いてください。

## 単一ファイル版の再生成

```bash
node docs/scripts/build-webui-singlefile.mjs
```

Windows / Linux ラッパー:

```powershell
cd webui-sample
.\build-singlefile.cmd
```

```bash
cd webui-sample
sh ./build-singlefile.sh
```

## 共有ドライブ運用（再生成 → 配布）

1. `webui-sample/build-singlefile.cmd`（Windows）または `webui-sample/build-singlefile.sh`（Linux）で再生成
2. `node ../docs/scripts/check-webui-syntax.mjs` で構文/単一ファイル検証
3. 共有ドライブ上の `webui-sample/index.singlefile.html` をデモ配布物として利用
4. 利用者には `index.singlefile.html` を開くよう案内（`index.html` ではない）

詳細手順は `docs/webui-shared-drive-usage.md` を参照。

## 設定方法（優先順）

1. クエリパラメータ
   - `?apiMode=live&apiBaseUrl=http://localhost:5012/api`
2. `window.__WEBUI_CONFIG__`
3. `meta[name="lms-api-base-url"]` / `meta[name="lms-api-mode"]`
4. `localStorage`
5. 既定値（`/api`, `auto`）

## 例（本番配備時の設定注入）

```html
<script>
  window.__WEBUI_CONFIG__ = {
    apiBaseUrl: "https://example.com/api",
    apiMode: "live"
  };
</script>
```

## 確認コマンド

```bash
node ../docs/scripts/check-webui-syntax.mjs
node ../docs/scripts/check-shared-drive-compat.mjs
```

## 注意

- 認証トークンは現在 `localStorage` ベース（サンプル実装）
- 本番は `httpOnly Cookie` を優先検討
