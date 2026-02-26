# WebUI Shared Drive Usage Guide

更新日: 2026-02-24

## 前提

- `Z:` は Linux 共有を Windows から参照するためのドライブレター
- `webui-sample` は以下の2系統で利用する
  - `file://` デモ閲覧（単一ファイル版）
  - `http://localhost` 開発/検証（モジュール版）

## 1. `file://` デモ運用（共有ドライブ向け）

### 正式デモ入口

- `webui-sample/index.singlefile.html`

### 使い方

1. `webui-sample/index.singlefile.html` をエクスプローラーまたはブラウザで開く
2. モック動作で UI を確認する（ログイン可能）
3. 必要に応じて URL 末尾に `?apiMode=mock` を付与

例:

```text
file:///Z:/Mirai-IT-System-Sample/Linux-Management-Systm-Sample/webui-sample/index.singlefile.html?apiMode=mock
```

### 再生成 → 配布（共有ドライブ）

Windows:

```powershell
cd Z:\Mirai-IT-System-Sample\Linux-Management-Systm-Sample\webui-sample
.\build-singlefile.cmd
```

Linux:

```bash
cd /path/to/Linux-Management-Systm-Sample/webui-sample
sh ./build-singlefile.sh
```

配布時の確認:

- `index.singlefile.html` の更新日時が新しいこと
- `node ../docs/scripts/check-webui-syntax.mjs` が成功すること

## 2. `http://localhost` 開発/検証（モジュール版）

`webui-sample/index.html` は ES Modules を使用しているため、`file://` 直開きではなく HTTP サーバー経由で開く。

Windows PowerShell:

```powershell
cd Z:\Mirai-IT-System-Sample\Linux-Management-Systm-Sample\webui-sample
py -m http.server 8080
```

Linux:

```bash
cd /path/to/Linux-Management-Systm-Sample/webui-sample
python3 -m http.server 8080
```

アクセス例:

- `http://localhost:8080/index.html?apiMode=mock`
- `http://localhost:8080/index.html?apiMode=auto`
- `http://localhost:8080/index.html?apiMode=live&apiBaseUrl=http://localhost:5012/api`

## 3. Shared Drive 向け注意点

- スクリプトは相対パスで実装し、`Z:` / `/mnt/...` の固定パスを埋め込まない
- UTF-8（BOMなし）を使用する
- 改行コードは `.cmd` を除き LF を推奨
- `index.singlefile.html` はデモ用途（本番運用対象外）

## 4. ローカルチェック（shared drive 対応）

```bash
node docs/scripts/run-shared-drive-checks.mjs
```

Runtime OpenAPI と比較する場合:

```bash
node docs/scripts/run-shared-drive-checks.mjs --runtime artifacts/openapi.runtime.json --strict-openapi-runtime
```
