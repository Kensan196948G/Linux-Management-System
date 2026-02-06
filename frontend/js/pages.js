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
                    <button class="btn btn-primary" onclick="showPage('services')">システムサーバー</button>
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
 * システムサーバー管理ページ
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

// ===================================================================
// Networking カテゴリのページ
// ===================================================================

function showFirewallPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">Linux Firewall - サンプルデータ</h3>
            <div class="grid grid-2">
                <div class="card" style="background-color: #f0fdf4;">
                    <h4 style="color: #166534;">✅ 許可ルール</h4>
                    <ul style="font-size: 0.875rem; list-style: none; padding: 0;">
                        <li style="padding: 0.25rem 0;">SSH (22) from 192.168.0.0/24</li>
                        <li style="padding: 0.25rem 0;">HTTP (80) from any</li>
                        <li style="padding: 0.25rem 0;">HTTPS (443) from any</li>
                    </ul>
                </div>
                <div class="card" style="background-color: #fef2f2;">
                    <h4 style="color: #991b1b;">🚫 拒否ルール</h4>
                    <ul style="font-size: 0.875rem; list-style: none; padding: 0;">
                        <li style="padding: 0.25rem 0;">Telnet (23) - 全拒否</li>
                        <li style="padding: 0.25rem 0;">FTP (21) - 全拒否</li>
                    </ul>
                </div>
            </div>
            <p class="text-secondary" style="margin-top: 1rem; font-size: 0.875rem;">
                ℹ️ サンプルデータ（v0.3実装予定）
            </p>
        </div>
    `;
}

function showNetworkConfigPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">Network Configuration - サンプルデータ</h3>
            <table class="table">
                <thead>
                    <tr><th>IF</th><th>IP</th><th>状態</th><th>速度</th></tr>
                </thead>
                <tbody>
                    <tr><td>eth0</td><td>192.168.0.185</td><td><span class="status-badge status-active">UP</span></td><td>1000Mbps</td></tr>
                    <tr><td>lo</td><td>127.0.0.1</td><td><span class="status-badge status-active">UP</span></td><td>-</td></tr>
                </tbody>
            </table>
            <p class="text-secondary" style="font-size: 0.875rem;">ℹ️ サンプルデータ（v0.2実装予定）</p>
        </div>
    `;
}

function showRoutingPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">Routing - サンプルデータ</h3>
            <table class="table">
                <thead>
                    <tr><th>宛先</th><th>ゲートウェイ</th><th>IF</th></tr>
                </thead>
                <tbody>
                    <tr><td>default</td><td>192.168.0.1</td><td>eth0</td></tr>
                    <tr><td>192.168.0.0/24</td><td>0.0.0.0</td><td>eth0</td></tr>
                </tbody>
            </table>
            <p class="text-secondary" style="font-size: 0.875rem;">ℹ️ サンプルデータ（v0.3実装予定）</p>
        </div>
    `;
}

function showNetstatPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">Netstat - サンプルデータ</h3>
            <table class="table">
                <thead>
                    <tr><th>Proto</th><th>Local</th><th>Remote</th><th>State</th></tr>
                </thead>
                <tbody>
                    <tr><td>tcp</td><td>0.0.0.0:22</td><td>*</td><td><span class="status-badge status-active">LISTEN</span></td></tr>
                    <tr><td>tcp</td><td>0.0.0.0:80</td><td>*</td><td><span class="status-badge status-active">LISTEN</span></td></tr>
                </tbody>
            </table>
            <p class="text-secondary" style="font-size: 0.875rem;">ℹ️ サンプルデータ（v0.2実装予定）</p>
        </div>
    `;
}

function showBandwidthPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">Bandwidth Monitoring - サンプルデータ</h3>
            <div class="grid grid-2">
                <div class="card">
                    <h4>受信</h4>
                    <p style="font-size: 2rem; font-weight: 600; color: #2563eb;">125.5 MB/s</p>
                    <div class="progress-bar mt-1"><div class="progress-fill" style="width: 45%;"></div></div>
                </div>
                <div class="card">
                    <h4>送信</h4>
                    <p style="font-size: 2rem; font-weight: 600; color: #10b981;">82.3 MB/s</p>
                    <div class="progress-bar mt-1"><div class="progress-fill" style="width: 30%; background-color: #10b981;"></div></div>
                </div>
            </div>
            <p class="text-secondary" style="font-size: 0.875rem;">ℹ️ サンプルデータ（v0.3実装予定）</p>
        </div>
    `;
}

// Hardware カテゴリ
async function showPartitionsPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">Partitions on Local Disks - ディスク使用状況</h3>
            <button class="btn btn-primary mb-1" onclick="loadPartitionsData()">更新</button>
            <div id="partitions-detail"></div>
        </div>
    `;

    loadPartitionsData();
}

async function loadPartitionsData() {
    const diskEl = document.getElementById('partitions-detail');
    if (diskEl) showLoading('partitions-detail');

    try {
        const status = await api.getSystemStatus();
        if (diskEl && status.disk) {
            diskEl.innerHTML = createDiskUsageTable(status.disk);
        }
    } catch (error) {
        console.error('Failed to load partition data:', error);
        if (diskEl) diskEl.innerHTML = '<p class="text-secondary">データの取得に失敗しました</p>';
    }
}

function showSystemTimePage(container) {
    const now = new Date().toLocaleString('ja-JP');
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">System Time - サンプルデータ</h3>
            <p style="font-size: 2rem; font-weight: 600; color: #2563eb;" id="live-time">${now}</p>
            <p class="text-secondary">タイムゾーン: Asia/Tokyo</p>
            <p class="text-secondary" style="font-size: 0.875rem;">ℹ️ サンプルデータ（v0.2実装予定）</p>
        </div>
    `;
    setInterval(() => {
        const el = document.getElementById('live-time');
        if (el) el.textContent = new Date().toLocaleString('ja-JP');
    }, 1000);
}

function showSmartStatusPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">SMART Status - サンプルデータ</h3>
            <table class="table">
                <thead>
                    <tr><th>Drive</th><th>Model</th><th>Health</th><th>Temp</th></tr>
                </thead>
                <tbody>
                    <tr><td>/dev/sda</td><td>Samsung SSD 970</td><td><span class="status-badge status-active">正常</span></td><td>42°C</td></tr>
                    <tr><td>/dev/sdb</td><td>WD Red 1TB</td><td><span class="status-badge status-active">正常</span></td><td>38°C</td></tr>
                </tbody>
            </table>
            <p class="text-secondary" style="font-size: 0.875rem;">ℹ️ サンプルデータ（v0.3実装予定）</p>
        </div>
    `;
}

function showSensorsPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">Sensors - サンプルデータ</h3>
            <div class="grid grid-3">
                <div class="card"><h4>CPU温度</h4><p style="font-size: 2rem; color: #10b981;">52°C</p></div>
                <div class="card"><h4>MB温度</h4><p style="font-size: 2rem; color: #10b981;">45°C</p></div>
                <div class="card"><h4>ファン</h4><p style="font-size: 2rem; color: #2563eb;">1850RPM</p></div>
            </div>
            <p class="text-secondary" style="font-size: 0.875rem;">ℹ️ サンプルデータ（v0.3実装予定）</p>
        </div>
    `;
}
