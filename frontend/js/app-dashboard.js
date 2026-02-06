/**
 * ダッシュボード用メインアプリケーションロジック
 */

// 現在のユーザー情報
let currentUser = null;

// ページ読み込み時の初期化
document.addEventListener('DOMContentLoaded', async () => {
    console.log('===== Dashboard Initialization Debug =====');
    console.log('1. Current URL:', window.location.href);
    console.log('2. LocalStorage token exists:', !!localStorage.getItem('access_token'));
    console.log('3. LocalStorage token (first 50 chars):',
                (localStorage.getItem('access_token') || 'NOT FOUND').substring(0, 50));
    console.log('4. api.token exists:', !!api.token);
    console.log('5. api.isAuthenticated():', api.isAuthenticated());
    console.log('==========================================');

    // 認証チェック
    if (!api.isAuthenticated()) {
        console.warn('❌ No authentication token found, redirecting to login...');
        // ログインページにリダイレクト
        window.location.href = '/dev/index.html';
        return;
    }

    console.log('Token found, fetching user info...');

    try {
        // ユーザー情報を取得
        currentUser = await api.getCurrentUser();
        console.log('User info loaded:', currentUser);

        // サイドバーのユーザー情報を更新
        updateSidebarUserInfo(currentUser);

        // アコーディオンの状態を復元
        if (typeof restoreAccordionState === 'function') {
            restoreAccordionState();
        }

        // URLパラメータからページを取得（なければdashboard）
        const urlParams = new URLSearchParams(window.location.search);
        const targetPage = urlParams.get('page') || 'dashboard';

        console.log('Displaying page:', targetPage);

        // 指定されたページを表示
        showPage(targetPage);

    } catch (error) {
        console.error('Dashboard initialization failed:', error);
        console.error('Error details:', {
            message: error.message,
            stack: error.stack
        });
        // 認証エラー: ログインページにリダイレクト
        alert('認証エラーが発生しました。ログイン画面に戻ります。\n\nエラー: ' + error.message);
        api.clearToken();
        window.location.href = '/dev/index.html';
    }
});

/**
 * ログアウト処理
 */
async function logout() {
    try {
        await api.logout();
        showAlert('ログアウトしました', 'success');

        // ログインページにリダイレクト
        setTimeout(() => {
            window.location.href = '/dev/index.html';
        }, 1000);

    } catch (error) {
        console.error('Logout failed:', error);
        api.clearToken();
        window.location.href = '/dev/index.html';
    }
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
            resultEl.innerHTML = `<div class="alert alert-error">❌ ${result.message}</div>`;
        }
    } catch (error) {
        console.error('Service restart failed:', error);
        showAlert(`再起動に失敗しました: ${error.message}`, 'error');
        resultEl.innerHTML = `<div class="alert alert-error">❌ ${error.message}</div>`;
    }
}
