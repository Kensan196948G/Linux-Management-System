# ログインフロー分析レポート

## 報告された問題
「ログインできているようだが、ダッシュボード画面が表示されずにログイン画面に戻ってしまう」

## ログインフローの追跡

### Step 1: ログインフォーム送信 (index.html)
```javascript
// frontend/dev/index.html:49-74
document.getElementById('login-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;

    // ✅ ログイン試行
    const result = await api.login(email, password);

    // ✅ 成功メッセージ表示
    alertsEl.innerHTML = '<div class="alert alert-success">✅ ログインしました...</div>';

    // ✅ 1秒後にリダイレクト
    setTimeout(() => {
        console.log('Redirecting to dashboard...');
        window.location.href = '/dev/dashboard.html';
    }, 1000);
});
```

**期待される動作**: トークンがlocalStorageに保存され、dashboard.htmlに遷移

### Step 2: トークン保存 (api.js)
```javascript
// frontend/js/api.js
async login(email, password) {
    const result = await this.request('POST', '/api/auth/login', { email, password });
    this.setToken(result.access_token);  // ✅ トークン保存
    return result;
}

setToken(token) {
    this.token = token;
    localStorage.setItem('access_token', token);  // ✅ localStorage保存
}
```

**検証結果**: バックエンドAPIは正常動作（curlテスト済み）

### Step 3: dashboard.html読み込み
```html
<!-- frontend/dev/dashboard.html -->
<script src="../js/api.js"></script>          <!-- APIClient読み込み -->
<script src="../js/components.js"></script>   <!-- UI関数読み込み -->
<script src="../js/sidebar.js"></script>      <!-- showPage関数読み込み -->
<script src="../js/pages.js"></script>        <!-- ページ表示関数読み込み -->
<script src="../js/app-dashboard.js"></script><!-- 初期化処理 -->
```

**検証結果**: 全てのスクリプトファイルは存在し、HTTP 200で配信されている

### Step 4: APIClient再初期化 (api.js:134)
```javascript
const api = new APIClient();
```

**constructor実行時**:
```javascript
constructor(baseURL) {
    this.baseURL = baseURL || '';
    this.token = localStorage.getItem('access_token');  // ✅ トークン取得
}
```

**期待される動作**: localStorageからトークンを読み込み、this.tokenに設定

### Step 5: 認証チェック (app-dashboard.js:12-16)
```javascript
// 認証チェック
if (!api.isAuthenticated()) {
    console.warn('No authentication token found, redirecting to login...');
    window.location.href = '/dev/index.html';
    return;
}
```

**isAuthenticated()の実装**:
```javascript
isAuthenticated() {
    return !!this.token;  // this.tokenが存在すればtrue
}
```

**🔴 問題の可能性**:
- もしthis.tokenがnullなら、ここでログイン画面にリダイレクト
- localStorageからトークンが取得できない場合に発生

### Step 6: ユーザー情報取得 (app-dashboard.js:22-24)
```javascript
try {
    currentUser = await api.getCurrentUser();
    console.log('User info loaded:', currentUser);
    // ...
} catch (error) {
    console.error('Dashboard initialization failed:', error);
    alert('認証エラーが発生しました。ログイン画面に戻ります。\n\nエラー: ' + error.message);
    api.clearToken();
    window.location.href = '/dev/index.html';  // ❌ エラー時にログイン画面へ
}
```

**🔴 問題の可能性**:
- getCurrentUser() APIが失敗した場合、catch節でログイン画面にリダイレクト
- APIが401エラーを返した場合も同様

## 考えられる原因

### 原因A: localStorageの読み込み失敗
**症状**: Step 4でthis.tokenがnull
**可能性**:
- ブラウザのプライベートモード
- localStorageが無効
- 異なるドメイン/ポート間でのlocalStorage不一致
- CORS問題

**検証方法**:
```javascript
// ブラウザコンソールで確認
localStorage.getItem('access_token')
```

### 原因B: getCurrentUser() APIの失敗
**症状**: Step 6でエラー
**可能性**:
1. トークンが期限切れ
2. バックエンドAPIが401を返す
3. ネットワークエラー
4. CORSエラー

**検証方法**:
```bash
# 有効なトークンでテスト
curl -X GET "http://192.168.0.185:5012/api/auth/me" \
  -H "Authorization: Bearer $TOKEN"
```
**結果**: ✅ APIは正常動作（テスト済み）

### 原因C: JavaScriptエラー
**症状**: 初期化中にエラーが発生
**可能性**:
- showPage関数が見つからない
- pages.jsの読み込み失敗
- 他のJavaScriptエラー

**検証方法**: ブラウザのコンソールでエラー確認

## デバッグ強化（実施済み）

### 追加したログ（commit d329a1f）
```javascript
console.log('Linux Management System - Dashboard loaded');
console.log('Token found, fetching user info...');
console.log('User info loaded:', currentUser);
console.log('Displaying page:', targetPage);

// エラー時
console.error('Dashboard initialization failed:', error);
alert('認証エラーが発生しました。ログイン画面に戻ります。\n\nエラー: ' + error.message);
```

## 推奨される次のステップ

### 1. ユーザーによるブラウザデバッグ
```
1. Ctrl+Shift+Delete でキャッシュクリア
2. F12 でコンソール開く3. ログインを試行
4. コンソールログを確認
5. アラートメッセージを確認
```

### 2. 追加のデバッグコード（必要に応じて）
```javascript
// app-dashboard.js の最初に追加
console.log('=== Dashboard Debug Info ===');
console.log('Current URL:', window.location.href);
console.log('LocalStorage token:', localStorage.getItem('access_token') ? 'EXISTS' : 'NOT FOUND');
console.log('api.token:', api.token ? 'EXISTS' : 'NOT FOUND');
console.log('api.isAuthenticated():', api.isAuthenticated());
```

### 3. トークンの手動確認
ブラウザコンソールで：
```javascript
localStorage.getItem('access_token')
// 期待値: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

## 結論

**最も可能性の高い原因**:
- **原因B**: トークンは正しく保存されているが、getCurrentUser()が何らかの理由で失敗している
- エラーがcatch節で捕捉され、ログイン画面にリダイレクトされる

**次に確認すべき情報**:
1. ブラウザのコンソールログ（特にエラーメッセージ）
2. アラートに表示されるエラー内容
3. NetworkタブでAPIリクエストの状態コード

**暫定的な回避策**:
- ブラウザのlocalStorageを手動でクリアして再ログイン
- シークレットモードで試す
- 別のブラウザで試す
