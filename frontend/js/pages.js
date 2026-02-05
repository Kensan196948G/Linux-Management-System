/**
 * 各ページのコンテンツ生成
 */

/**
 * ダッシュボードページ
 */
function showDashboardPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">システム概要</h3>
            <button class="btn btn-primary mb-1" onclick="loadDashboardData()">更新</button>
            <div id="dashboard-system-status"></div>
        </div>

        <div class="grid grid-2">
            <div class="card">
                <h3 class="card-title">クイックアクション</h3>
                <div style="display: flex; flex-direction: column; gap: var(--spacing-sm);">
                    <button class="btn btn-primary" onclick="showPage('services')">サービス管理</button>
                    <button class="btn btn-primary" onclick="showPage('logs')">ログ閲覧</button>
                    <button class="btn btn-primary" onclick="showPage('disk')">ディスク使用状況</button>
                </div>
            </div>

            <div class="card">
                <h3 class="card-title">最近の操作</h3>
                <p class="text-secondary">監査ログから最近の操作を表示（今後実装）</p>
            </div>
        </div>

        <div class="card">
            <h3 class="card-title">ディスク使用状況</h3>
            <div id="dashboard-disk"></div>
        </div>
    `;

    // データを読み込み
    loadDashboardData();
}

/**
 * ダッシュボードデータを読み込み
 */
async function loadDashboardData() {
    const statusEl = document.getElementById('dashboard-system-status');
    const diskEl = document.getElementById('dashboard-disk');

    if (statusEl) showLoading('dashboard-system-status');
    if (diskEl) showLoading('dashboard-disk');

    try {
        const status = await api.getSystemStatus();

        if (statusEl) {
            statusEl.innerHTML = createSystemStatusCard(status);
        }

        if (diskEl && status.disk) {
            diskEl.innerHTML = createDiskUsageTable(status.disk);
        }
    } catch (error) {
        console.error('Failed to load dashboard data:', error);
        if (statusEl) statusEl.innerHTML = '<p class="text-secondary">データの取得に失敗しました</p>';
        if (diskEl) diskEl.innerHTML = '<p class="text-secondary">データの取得に失敗しました</p>';
    }
}

/**
 * サービス管理ページ
 */
function showServicesPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">サービス操作</h3>
            <p style="color: var(--text-secondary); margin-bottom: 1rem;">
                許可されたサービスのみ操作可能です（allowlist方式）
            </p>
            <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
                <button class="btn btn-warning" onclick="restartService('nginx')">nginx を再起動</button>
                <button class="btn btn-warning" onclick="restartService('postgresql')">postgresql を再起動</button>
                <button class="btn btn-warning" onclick="restartService('redis')">redis を再起動</button>
            </div>
            <div id="service-result" style="margin-top: 1rem;"></div>
        </div>

        <div class="card">
            <h3 class="card-title">サービス状態</h3>
            <p class="text-secondary">サービス状態の一覧表示（今後実装）</p>
        </div>
    `;
}

/**
 * 操作ログページ
 */
function showAuditLogPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">操作ログ（監査証跡）</h3>
            <p class="text-secondary">全操作の監査ログを表示（今後実装）</p>
            <p>実装予定の機能:</p>
            <ul>
                <li>全操作の履歴表示</li>
                <li>ユーザー別フィルタ</li>
                <li>操作種別フィルタ</li>
                <li>日時範囲指定</li>
                <li>CSV/JSON エクスポート</li>
            </ul>
        </div>
    `;
}

/**
 * ディスク使用状況ページ
 */
function showDiskPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">ディスク使用状況</h3>
            <button class="btn btn-primary mb-1" onclick="loadDiskUsage()">更新</button>
            <div id="disk-usage-detail"></div>
        </div>
    `;

    loadDiskUsage();
}

/**
 * ディスク使用状況を読み込み
 */
async function loadDiskUsage() {
    const diskEl = document.getElementById('disk-usage-detail');

    if (diskEl) showLoading('disk-usage-detail');

    try {
        const status = await api.getSystemStatus();

        if (diskEl && status.disk) {
            diskEl.innerHTML = createDiskUsageTable(status.disk);
        }
    } catch (error) {
        console.error('Failed to load disk usage:', error);
        if (diskEl) diskEl.innerHTML = '<p class="text-secondary">データの取得に失敗しました</p>';
    }
}

/**
 * ログ閲覧ページ
 */
function showLogsPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">システムログ閲覧</h3>
            <div style="display: flex; gap: 1rem; margin-bottom: 1rem; flex-wrap: wrap;">
                <div class="form-group" style="flex: 1; min-width: 200px; margin-bottom: 0;">
                    <label class="form-label">サービス</label>
                    <select class="form-input" id="log-service-page">
                        <option value="nginx">nginx</option>
                        <option value="postgresql">postgresql</option>
                        <option value="redis">redis</option>
                        <option value="sshd">sshd</option>
                        <option value="systemd">systemd</option>
                    </select>
                </div>
                <div class="form-group" style="width: 120px; margin-bottom: 0;">
                    <label class="form-label">行数</label>
                    <input type="number" class="form-input" id="log-lines-page" value="100" min="1" max="1000">
                </div>
                <div style="display: flex; align-items: flex-end;">
                    <button class="btn btn-primary" onclick="loadLogsForPage()">ログ取得</button>
                </div>
            </div>
            <div id="logs-display-page"></div>
        </div>
    `;
}

/**
 * ログを読み込み（ページ用）
 */
async function loadLogsForPage() {
    const serviceName = document.getElementById('log-service-page').value;
    const lines = parseInt(document.getElementById('log-lines-page').value, 10);
    const logsEl = document.getElementById('logs-display-page');

    showLoading('logs-display-page');

    try {
        const result = await api.getLogs(serviceName, lines);

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
