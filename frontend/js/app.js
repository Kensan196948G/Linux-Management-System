/**
 * メインアプリケーションロジック
 */

// ページ読み込み時の初期化
document.addEventListener('DOMContentLoaded', () => {
    console.log('Linux Management System - Frontend loaded');

    // 認証状態をチェック
    checkAuthentication();

    // ログインフォームのイベントリスナー
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', handleLogin);
    }
});

/**
 * 認証状態をチェック
 */
async function checkAuthentication() {
    if (api.isAuthenticated()) {
        try {
            // ユーザー情報を取得
            const user = await api.getCurrentUser();

            // ダッシュボードを表示
            showDashboard(user);

        } catch (error) {
            console.error('Authentication check failed:', error);
            showLogin();
        }
    } else {
        showLogin();
    }
}

/**
 * ログイン画面を表示
 */
function showLogin() {
    document.getElementById('login-section').classList.remove('hidden');
    document.getElementById('dashboard-section').classList.add('hidden');
}

/**
 * ダッシュボードを表示
 */
function showDashboard(user) {
    document.getElementById('login-section').classList.add('hidden');
    document.getElementById('dashboard-section').classList.remove('hidden');

    // ユーザー情報を表示
    document.getElementById('user-name').textContent = user.username;
    document.getElementById('user-role').textContent = user.role;

    // 権限に応じてサービス操作を表示/非表示
    const serviceOps = document.getElementById('service-operations');
    if (serviceOps) {
        if (!user.permissions.includes('execute:service_restart')) {
            serviceOps.style.display = 'none';
        } else {
            serviceOps.style.display = 'block';
        }
    }

    // 初回データ読み込み
    loadSystemStatus();
}

/**
 * ログイン処理
 */
async function handleLogin(event) {
    event.preventDefault();

    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;

    try {
        const result = await api.login(email, password);

        console.log('Login successful:', result);
        showAlert('ログインしました', 'success');

        // ダッシュボードに移動
        const user = await api.getCurrentUser();
        showDashboard(user);

    } catch (error) {
        console.error('Login failed:', error);
        showAlert('ログインに失敗しました: ' + error.message, 'error');
    }
}

/**
 * ログアウト処理
 */
async function logout() {
    try {
        await api.logout();
        showAlert('ログアウトしました', 'success');
        showLogin();
    } catch (error) {
        console.error('Logout failed:', error);
        api.clearToken();
        showLogin();
    }
}

/**
 * システム状態を読み込み
 */
async function loadSystemStatus() {
    const statusEl = document.getElementById('system-status');
    const diskEl = document.getElementById('disk-usage');

    showLoading('system-status');
    if (diskEl) showLoading('disk-usage');

    try {
        const status = await api.getSystemStatus();

        console.log('System status:', status);

        // システム状態カードを表示
        statusEl.innerHTML = createSystemStatusCard(status);

        // ディスク使用状況を表示
        if (diskEl && status.disk) {
            diskEl.innerHTML = createDiskUsageTable(status.disk);
        }

    } catch (error) {
        console.error('Failed to load system status:', error);
        showAlert('システム状態の取得に失敗しました: ' + error.message, 'error');
        statusEl.innerHTML = '<p class="text-secondary">データの取得に失敗しました</p>';
        if (diskEl) diskEl.innerHTML = '<p class="text-secondary">データの取得に失敗しました</p>';
    }
}

/**
 * サービス再起動
 */
async function restartService(serviceName) {
    const resultEl = document.getElementById('service-result');

    if (!confirm(`${serviceName} を再起動しますか？`)) {
        return;
    }

    resultEl.innerHTML = '<div class="loading"><div class="spinner"></div><p>再起動中...</p></div>';

    try {
        const result = await api.restartService(serviceName);

        console.log('Service restart result:', result);

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

/**
 * ログを読み込み
 */
async function loadLogs() {
    const serviceName = document.getElementById('log-service').value;
    const lines = parseInt(document.getElementById('log-lines').value, 10);
    const logsEl = document.getElementById('logs-display');

    showLoading('logs-display');

    try {
        const result = await api.getLogs(serviceName, lines);

        console.log('Logs retrieved:', result);

        if (result.status === 'success' && result.logs) {
            logsEl.innerHTML = createLogViewer(result.logs);
        } else {
            showAlert(`ログの取得に失敗しました: ${result.message}`, 'error');
            logsEl.innerHTML = '<p class="text-secondary">ログデータがありません</p>';
        }

    } catch (error) {
        console.error('Failed to load logs:', error);
        showAlert(`ログの取得に失敗しました: ${error.message}`, 'error');
        logsEl.innerHTML = '<p class="text-secondary">ログの取得に失敗しました</p>';
    }
}
