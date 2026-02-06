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

    console.log('✅ Token found, fetching user info...');

    try {
        // ユーザー情報を取得
        console.log('Calling api.getCurrentUser()...');
        currentUser = await api.getCurrentUser();
        console.log('✅ User info loaded successfully:', currentUser);

        // ユーザー情報の詳細確認
        if (!currentUser || !currentUser.username) {
            throw new Error('Invalid user data received: ' + JSON.stringify(currentUser));
        }
        console.log('✅ User data validated');

        // サイドバーのユーザー情報を更新
        console.log('Updating sidebar user info...');
        try {
            updateSidebarUserInfo(currentUser);
            console.log('✅ Sidebar user info updated');
        } catch (error) {
            console.error('❌ Failed to update sidebar:', error);
            throw error;
        }

        // アコーディオンの状態を復元
        console.log('Restoring accordion state...');
        if (typeof restoreAccordionState === 'function') {
            restoreAccordionState();
            console.log('✅ Accordion state restored');
        } else {
            console.warn('⚠️ restoreAccordionState function not found');
        }

        // URLパラメータからページを取得（なければdashboard）
        const urlParams = new URLSearchParams(window.location.search);
        const targetPage = urlParams.get('page') || 'dashboard';

        console.log('📄 Displaying page:', targetPage);

        // 指定されたページを表示
        try {
            if (typeof showPage !== 'function') {
                throw new Error('showPage function not found!');
            }
            showPage(targetPage);
            console.log('✅ Page displayed successfully');
        } catch (error) {
            console.error('❌ Failed to display page:', error);
            throw error;
        }

    } catch (error) {
        console.error('❌❌❌ Dashboard initialization FAILED ❌❌❌');
        console.error('Error message:', error.message);
        console.error('Error stack:', error.stack);
        console.error('Error object:', error);

        // エラーの詳細をアラートで表示
        const errorDetails = `
ダッシュボードの初期化に失敗しました。

エラー: ${error.message}

詳細はブラウザのコンソール（F12）を確認してください。
ログイン画面に戻ります...
        `.trim();

        alert(errorDetails);

        // 認証エラー: ログインページにリダイレクト
        console.error('Clearing token and redirecting to login...');
        api.clearToken();

        // 3秒待ってからリダイレクト（ユーザーがエラーを確認できるように）
        setTimeout(() => {
            window.location.href = '/dev/index.html';
        }, 3000);
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
