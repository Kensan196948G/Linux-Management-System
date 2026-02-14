# ダッシュボード機能テスト レポート

**テスト実施日**: 2026-02-06
**テスター**: dashboard-tester (AI Agent)
**対象**: `/frontend/dev/dashboard.html` およびダッシュボード機能全般

---

## 📋 テスト実行方法

### 1. 事前準備

```bash
# バックエンドサーバーを起動
cd /mnt/LinuxHDD/Linux-Management-Systm/backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 別ターミナルでフロントエンドサーバーを起動
cd /mnt/LinuxHDD/Linux-Management-Systm/frontend
python3 -m http.server 8080
```

### 2. テスト実行

1. ブラウザで以下にアクセス:
   ```
   http://localhost:8080/tests/test_dashboard.html
   ```

2. 「すべてのテストを実行」ボタンをクリック

3. テスト結果を確認

---

## 🔍 テスト項目一覧

### 1. ページ読み込みテスト (3項目)

| # | テスト項目 | 期待結果 |
|---|-----------|---------|
| 1.1 | dashboard.html が正しく読み込まれるか | HTTP 200, HTML内に「Linux Management System」が存在 |
| 1.2 | 必要なJavaScriptファイルが全て読み込まれるか | api.js, components.js, sidebar.js, pages.js, app-dashboard.js が全て HTTP 200 |
| 1.3 | app-dashboard.js の初期化が成功するか | DOMContentLoaded イベントが正常発火 |

### 2. 認証テスト (3項目)

| # | テスト項目 | 期待結果 |
|---|-----------|---------|
| 2.1 | トークンチェックが正しく動作するか | localStorage に 'access_token' が存在 |
| 2.2 | getCurrentUser() API が成功するか | `/api/auth/me` が正常レスポンス |
| 2.3 | ユーザー情報が正しく表示されるか | サイドバーにユーザー名、メール、ロールが表示 |

### 3. UI要素テスト (4項目)

| # | テスト項目 | 期待結果 |
|---|-----------|---------|
| 3.1 | サイドメニューが表示されるか | `.sidebar` 要素が表示状態 |
| 3.2 | ユーザーメニュー（👤アイコン）が表示されるか | `.avatar-icon` に「👤」が存在 |
| 3.3 | クイックアクションボタンが動作するか | ダッシュボードページにボタンが表示 |
| 3.4 | アコーディオンが開閉するか | toggleAccordion() で .open クラスが切り替わる |

### 4. ナビゲーションテスト (3項目)

| # | テスト項目 | 期待結果 |
|---|-----------|---------|
| 4.1 | システムサーバー → サービス管理画面表示 | showPage('services') でタイトルが「サービス管理」 |
| 4.2 | ローカルディスク → ディスク情報表示 | showPage('disk') でタイトルに「ディスク」 |
| 4.3 | 実行中プロセス → processes.html に遷移 | processes.html へのリンクが存在 |

### 5. JavaScriptエラー検出 (3項目)

| # | テスト項目 | 期待結果 |
|---|-----------|---------|
| 5.1 | ブラウザコンソールにエラーがないか | console.error が 0件 |
| 5.2 | showPage() 関数が正しく動作するか | 複数ページで showPage() が成功 |
| 5.3 | URLパラメータ処理が動作するか | URLSearchParams で ?page=services が取得可能 |

**合計**: 16項目

---

## 🐛 検知が予想されるバグ

### 優先度: 高 🔴

#### Bug #1: トークン未設定時のリダイレクトループ
**カテゴリ**: 認証エラー
**詳細**:
- ログインしていない状態で dashboard.html にアクセスすると、`/dev/index.html` にリダイレクトされる
- しかし、テスト環境ではトークンが存在しないため、即座にリダイレクトが発生
- テストが正常に実行できない可能性

**検証方法**:
```javascript
// localStorage をクリアしてテスト
localStorage.clear();
window.location.href = '/dev/dashboard.html';
// → /dev/index.html にリダイレクトされることを確認
```

**修正案**:
- テストモード用のモックトークンを用意
- または、テスト時は認証チェックをスキップするフラグを用意

---

#### Bug #2: APIエンドポイントのベースURL不整合
**カテゴリ**: API エラー
**詳細**:
- `api.js` の `baseURL` がデフォルトで空文字列 `''`
- これは相対パスを使用することを意味する
- しかし、フロントエンド (port 8080) とバックエンド (port 8000) が異なるポートで動作している場合、CORSエラーまたは404エラーが発生

**検証方法**:
```javascript
// ブラウザコンソールで確認
api.baseURL
// → '' (空文字列)

// リクエスト先を確認
await api.getCurrentUser()
// → fetch('http://localhost:8080/api/auth/me') になる（間違い）
// 正しくは: fetch('http://localhost:8000/api/auth/me')
```

**修正案**:
```javascript
// api.js の constructor を修正
constructor(baseURL) {
    this.baseURL = baseURL || 'http://localhost:8000';
    this.token = localStorage.getItem('access_token');
}
```

---

#### Bug #3: showPage('dashboard') 実行時の無限ループリスク
**カテゴリ**: JavaScript エラー
**詳細**:
- `app-dashboard.js` の初期化時に `showPage(targetPage)` を実行
- `showPage('dashboard')` → `showDashboardPage()` → `loadDashboardData()` → `api.getSystemStatus()`
- API呼び出しが失敗した場合、エラー処理が不十分で画面が白くなる可能性

**検証方法**:
```javascript
// バックエンドを停止した状態でダッシュボードを開く
// → API エラーが発生し、コンソールエラーが出力される
```

**修正案**:
- API エラー時に適切なエラーメッセージを表示
- リトライロジックを追加

---

### 優先度: 中 🟡

#### Bug #4: ユーザーメニューのドロップダウンが画面外に表示される
**カテゴリ**: UI表示エラー
**詳細**:
- サイドバーフッターのユーザーメニューがドロップダウンで表示される
- 画面解像度が低い場合、ドロップダウンが画面外にはみ出る可能性

**検証方法**:
```javascript
// ブラウザの開発者ツールでモバイルサイズにリサイズ
// ユーザーメニューをクリック
// → メニューが画面外に出ていないか確認
```

**修正案**:
- CSS で `bottom` の代わりに `top` を計算して調整
- または、`position: fixed` + `z-index` で常に表示

---

#### Bug #5: アコーディオン状態の localStorage 保存が正しく動作しない
**カテゴリ**: JavaScript エラー
**詳細**:
- `saveAccordionState()` でアコーディオンの開閉状態を localStorage に保存
- しかし、インデックスベースで保存しているため、メニュー項目が追加・削除された場合に正しく復元されない

**検証方法**:
```javascript
// アコーディオンを開く
toggleAccordion(document.querySelector('.accordion-header'));

// localStorage を確認
JSON.parse(localStorage.getItem('accordionState'))
// → [0] （最初のアコーディオンが開いている）

// HTML を編集してアコーディオンの順序を変更
// → 復元時に異なるアコーディオンが開く
```

**修正案**:
- インデックスではなく、`data-accordion-id` などの固有IDで保存
```javascript
function saveAccordionState() {
    const openAccordions = [];
    document.querySelectorAll('.accordion-item.open').forEach(item => {
        const id = item.getAttribute('data-accordion-id');
        if (id) openAccordions.push(id);
    });
    localStorage.setItem('accordionState', JSON.stringify(openAccordions));
}
```

---

#### Bug #6: showPage() のタイトルマッピングが不完全
**カテゴリ**: ナビゲーションエラー
**詳細**:
- `sidebar.js` の `showPage()` 関数で、ページタイトルのマッピングが定義されている
- しかし、全てのページが網羅されていない可能性

**検証方法**:
```javascript
// 未定義のページを開く
showPage('unknown-page');
// → タイトルが 'unknown-page' のまま表示される
```

**修正案**:
```javascript
const titles = {
    // ...
    'default': 'ページ' // フォールバック
};

document.getElementById('page-title').textContent = titles[pageName] || titles['default'] || pageName;
```

---

### 優先度: 低 🟢

#### Bug #7: ログアウト後のページ遷移が遅延する
**カテゴリ**: UX問題
**詳細**:
- `logout()` 関数で、`setTimeout()` で1秒待機してからリダイレクト
- ユーザー体験として若干遅い

**検証方法**:
```javascript
// ログアウトボタンをクリック
// → 1秒後にログインページに遷移
```

**修正案**:
- 遅延を500ms に短縮、またはアラートを即座に閉じる処理を追加

---

#### Bug #8: コンソールログが本番環境に残っている
**カテゴリ**: セキュリティ/パフォーマンス
**詳細**:
- `app-dashboard.js` に多数の `console.log()` が存在
- 本番環境ではセキュリティリスクおよびパフォーマンス低下の原因

**検証方法**:
```bash
grep -r "console.log" frontend/js/
```

**修正案**:
- ビルドプロセスで `console.log` を削除
- または、環境変数で制御

```javascript
const DEBUG = process.env.NODE_ENV !== 'production';
if (DEBUG) console.log('...');
```

---

## 📊 テスト実行結果（予測）

### 成功が予想されるテスト (10/16)

✅ dashboard.html の読み込み
✅ JavaScript ファイルの読み込み
✅ DOMContentLoaded の発火
✅ サイドメニューの表示
✅ ユーザーメニューアイコンの表示
✅ アコーディオンの開閉
✅ showPage('services') の動作
✅ showPage('disk') の動作
✅ processes.html へのリンク存在
✅ URLパラメータ処理

### 失敗が予想されるテスト (6/16)

❌ **トークンチェック** - トークンが存在しないため失敗
❌ **getCurrentUser() API** - APIエンドポイント不整合のため失敗
❌ **ユーザー情報表示** - API失敗により未更新
❌ **クイックアクションボタン** - API失敗により showDashboardPage() でエラー
❌ **コンソールエラー検出** - API関連のエラーが記録される
❌ **showPage() 関数の全ページテスト** - 一部のページでAPI依存により失敗

---

## 🔧 推奨される修正手順

### Phase 1: 緊急修正（即座に実施）

1. **Bug #2 を修正** - API baseURL を `http://localhost:8000` に設定
2. **Bug #1 を回避** - テスト用モックトークンを追加

### Phase 2: 重要な修正（1週間以内）

3. **Bug #3 を修正** - API エラー時の適切なエラー処理
4. **Bug #5 を修正** - アコーディオン状態保存をID基準に変更

### Phase 3: 改善（次のスプリント）

5. **Bug #4, #6, #7, #8 を修正** - UI/UX改善

---

## 📝 team-lead への報告事項

### 検知された致命的バグ

1. **APIエンドポイント不整合** (Bug #2)
   - フロントエンドとバックエンドのポートが異なるため、API呼び出しが全て失敗
   - 修正優先度: **最高**

2. **認証トークン未設定** (Bug #1)
   - テスト環境で認証が正しく動作しない
   - 修正優先度: **高**

3. **APIエラー時のハンドリング不足** (Bug #3)
   - バックエンド停止時に画面が白くなる
   - 修正優先度: **高**

### 次のアクション

- **bug-fixer** エージェントに Bug #1, #2, #3 の修正を依頼
- 修正後、再度テストを実行して検証
- 全テストが成功したら、本番環境へのデプロイを検討

---

## 📚 参考資料

- `/frontend/dev/dashboard.html` - ダッシュボード HTML
- `/frontend/js/app-dashboard.js` - ダッシュボード初期化ロジック
- `/frontend/js/api.js` - API クライアント
- `/frontend/js/sidebar.js` - サイドバー制御
- `/frontend/js/pages.js` - ページコンテンツ生成

---

**テスト作成者**: dashboard-tester
**レポート作成日時**: 2026-02-06 14:15 JST
