/**
 * ダッシュボード用メインアプリケーションロジック
 */

// 現在のユーザー情報
let currentUser = null;

/** dev/prod 両対応: ログインページのURLを動的に取得 */
function getLoginUrl() {
    return window.location.pathname.replace(/[^/]*$/, '') + 'index.html';
}

// ページ読み込み時の初期化
document.addEventListener('DOMContentLoaded', async () => {
    // 認証チェック
    if (!api.isAuthenticated()) {
        console.warn('❌ No authentication token found, redirecting to login...');
        window.location.href = getLoginUrl();
        return;
    }

    try {
        // ユーザー情報を取得
        currentUser = await api.getCurrentUser();

        if (!currentUser || !currentUser.username) {
            throw new Error('Invalid user data received');
        }

        // サイドバーのユーザー情報を更新
        if (typeof updateSidebarUserInfo === 'function') {
            updateSidebarUserInfo(currentUser);
        }

        // URLパラメータからページを取得（なければdashboard）
        const urlParams = new URLSearchParams(window.location.search);
        const targetPage = urlParams.get('page') || 'dashboard';

        // 指定されたページを表示
        if (typeof showPage === 'function') {
            showPage(targetPage);
        }

    } catch (error) {
        console.error('Dashboard initialization error:', error.message);

        // 401 (auth error) の場合のみトークンをクリアしてリダイレクト
        const isAuthError = error.message === 'Token expired or invalid' ||
                            error.message.includes('401') ||
                            error.message.includes('Unauthorized');

        if (isAuthError) {
            api.clearToken();
            window.location.href = getLoginUrl();
        } else {
            // ネットワークエラー等: トークンは保持し、UI にエラー表示
            const mainBody = document.getElementById('main-body');
            if (mainBody) {
                mainBody.innerHTML = `<div class="card" style="border-left:4px solid #ef4444;">
                    <h3 style="color:#ef4444;">⚠️ 初期化エラー</h3>
                    <p>${typeof escapeHtml === 'function' ? escapeHtml(error.message) : ''}</p>
                    <button class="btn btn-primary" onclick="location.reload()">再読み込み</button>
                </div>`;
            }
        }
    }
});

/**
 * ログアウト処理
 */
async function logout() {
    try {
        await api.logout();
    } catch (error) {
        console.error('Logout failed:', error);
    }
    api.clearToken();
    window.location.href = getLoginUrl();
}

/**
 * サービス再起動
 */
async function restartService(serviceName) {
    const resultEl = document.getElementById('service-result');

    if (!resultEl) {
        console.error('service-result element not found');
        return;
    }

    if (!confirm(`${serviceName} を再起動しますか？`)) {
        return;
    }

    resultEl.innerHTML = '<div class="loading"><div class="spinner"></div><p>再起動中...</p></div>';

    try {
        const result = await api.restartService(serviceName);

        if (result.status === 'success') {
            showAlert(`${serviceName} を再起動しました`, 'success');
            resultEl.innerHTML = `
                <div class="alert alert-success">
                    ✅ ${serviceName} を再起動しました<br>
                    再起動前: ${result.before}<br>
                    再起動後: ${result.after}
                </div>
            `;
        } else {
            showAlert(`再起動に失敗しました: ${result.message}`, 'error');
            resultEl.innerHTML = `<div class="alert alert-error">❌ ${typeof escapeHtml === 'function' ? escapeHtml(result.message) : ''}</div>`;
        }
    } catch (error) {
        console.error('Service restart failed:', error);
        showAlert(`再起動に失敗しました: ${error.message}`, 'error');
        resultEl.innerHTML = `<div class="alert alert-error">❌ ${typeof escapeHtml === 'function' ? escapeHtml(error.message) : ''}</div>`;
    }
}
