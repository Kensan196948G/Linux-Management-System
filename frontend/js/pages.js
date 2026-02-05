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
                <h3 class="card-title">最近の操作（サンプル）</h3>
                <ul style="font-size: 0.875rem; list-style: none; padding: 0;">
                    <li style="padding: 0.5rem 0; border-bottom: 1px solid #e2e8f0;">
                        <strong>13:20</strong> - operator が nginx を再起動
                    </li>
                    <li style="padding: 0.5rem 0; border-bottom: 1px solid #e2e8f0;">
                        <strong>13:18</strong> - operator がログを閲覧
                    </li>
                    <li style="padding: 0.5rem 0;">
                        <strong>13:15</strong> - viewer がログイン
                    </li>
                </ul>
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
            <h3 class="card-title">サービス状態（サンプルデータ）</h3>
            <table class="table">
                <thead>
                    <tr>
                        <th>サービス名</th>
                        <th>状態</th>
                        <th>稼働時間</th>
                        <th>メモリ使用</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>nginx</strong></td>
                        <td><span class="status-badge status-active">実行中</span></td>
                        <td>2日 3時間</td>
                        <td>45.2 MB</td>
                        <td><button class="btn btn-warning" style="padding: 4px 12px; font-size: 0.875rem;" onclick="restartService('nginx')">再起動</button></td>
                    </tr>
                    <tr>
                        <td><strong>postgresql</strong></td>
                        <td><span class="status-badge status-active">実行中</span></td>
                        <td>5日 12時間</td>
                        <td>128.5 MB</td>
                        <td><button class="btn btn-warning" style="padding: 4px 12px; font-size: 0.875rem;" onclick="restartService('postgresql')">再起動</button></td>
                    </tr>
                    <tr>
                        <td><strong>redis</strong></td>
                        <td><span class="status-badge status-active">実行中</span></td>
                        <td>1日 8時間</td>
                        <td>32.1 MB</td>
                        <td><button class="btn btn-warning" style="padding: 4px 12px; font-size: 0.875rem;" onclick="restartService('redis')">再起動</button></td>
                    </tr>
                    <tr>
                        <td><strong>apache2</strong></td>
                        <td><span class="status-badge status-inactive">停止中</span></td>
                        <td>-</td>
                        <td>-</td>
                        <td><button class="btn btn-primary" style="padding: 4px 12px; font-size: 0.875rem;" disabled>起動（未実装）</button></td>
                    </tr>
                </tbody>
            </table>
            <p class="text-secondary" style="margin-top: 1rem; font-size: 0.875rem;">
                ℹ️ これはサンプルデータです。実際のサービス状態は systemctl から取得予定（v0.2実装）
            </p>
        </div>
    `;
}

/**
 * 操作ログページ
 */
function showAuditLogPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">操作ログ（監査証跡）- サンプルデータ</h3>
            <div style="display: flex; gap: 1rem; margin-bottom: 1rem; flex-wrap: wrap;">
                <select class="form-input" style="width: 150px;">
                    <option value="">全ユーザー</option>
                    <option value="operator">operator</option>
                    <option value="admin">admin</option>
                    <option value="viewer">viewer</option>
                </select>
                <select class="form-input" style="width: 150px;">
                    <option value="">全操作</option>
                    <option value="login">ログイン</option>
                    <option value="service_restart">サービス再起動</option>
                    <option value="log_view">ログ閲覧</option>
                </select>
                <button class="btn btn-primary">検索</button>
                <button class="btn btn-success" style="margin-left: auto;">CSV エクスポート</button>
            </div>

            <table class="table">
                <thead>
                    <tr>
                        <th>日時</th>
                        <th>ユーザー</th>
                        <th>操作</th>
                        <th>対象</th>
                        <th>結果</th>
                        <th>詳細</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>2026-02-05 13:20:15</td>
                        <td><strong>operator</strong></td>
                        <td>ログイン</td>
                        <td>system</td>
                        <td><span class="status-badge status-active">成功</span></td>
                        <td>-</td>
                    </tr>
                    <tr>
                        <td>2026-02-05 13:19:42</td>
                        <td><strong>operator</strong></td>
                        <td>サービス再起動</td>
                        <td>nginx</td>
                        <td><span class="status-badge status-active">成功</span></td>
                        <td>before: active, after: active</td>
                    </tr>
                    <tr>
                        <td>2026-02-05 13:18:30</td>
                        <td><strong>operator</strong></td>
                        <td>ログ閲覧</td>
                        <td>nginx</td>
                        <td><span class="status-badge status-active">成功</span></td>
                        <td>100行取得</td>
                    </tr>
                    <tr>
                        <td>2026-02-05 13:15:10</td>
                        <td><strong>viewer</strong></td>
                        <td>サービス再起動</td>
                        <td>nginx</td>
                        <td><span class="status-badge status-error">拒否</span></td>
                        <td>権限不足（Viewer ロール）</td>
                    </tr>
                    <tr>
                        <td>2026-02-05 13:10:05</td>
                        <td><strong>admin</strong></td>
                        <td>ログイン</td>
                        <td>system</td>
                        <td><span class="status-badge status-active">成功</span></td>
                        <td>-</td>
                    </tr>
                    <tr>
                        <td>2026-02-05 13:05:22</td>
                        <td><strong>operator</strong></td>
                        <td>システム状態閲覧</td>
                        <td>system</td>
                        <td><span class="status-badge status-active">成功</span></td>
                        <td>CPU: 25%, Memory: 36%</td>
                    </tr>
                </tbody>
            </table>
            <p class="text-secondary" style="margin-top: 1rem; font-size: 0.875rem;">
                ℹ️ これはサンプルデータです。実際の監査ログは logs/dev/audit/ から取得予定（v0.2実装）
            </p>
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
