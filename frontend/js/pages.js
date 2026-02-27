/**
 * 各ページのコンテンツ生成
 * 実APIデータ使用・エラー時はグレースフルなメッセージを表示
 */

/** エラー表示ヘルパー */
function showDataUnavailable(elementId, message = 'データを取得できませんでした') {
    const el = document.getElementById(elementId);
    if (el) el.innerHTML = `<p class="text-secondary" style="padding:1rem;text-align:center;">⚠️ ${message}</p>`;
}

function showDataLoading(elementId) {
    const el = document.getElementById(elementId);
    if (el) el.innerHTML = '<p class="text-secondary" style="padding:1rem;text-align:center;">⏳ 読み込み中...</p>';
}

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
                <h3 class="card-title">最近の操作ログ</h3>
                <div id="dashboard-recent-audit"></div>
            </div>
        </div>

        <div class="card">
            <h3 class="card-title">ディスク使用状況</h3>
            <div id="dashboard-disk"></div>
        </div>
    `;

    loadDashboardData();
}

async function loadDashboardData() {
    const statusEl = document.getElementById('dashboard-system-status');
    const diskEl = document.getElementById('dashboard-disk');
    const auditEl = document.getElementById('dashboard-recent-audit');

    if (statusEl) statusEl.innerHTML = '<p class="text-secondary" style="padding:1rem;text-align:center;">⏳ 読み込み中...</p>';
    if (diskEl) diskEl.innerHTML = '<p class="text-secondary" style="padding:1rem;text-align:center;">⏳ 読み込み中...</p>';
    if (auditEl) auditEl.innerHTML = '<p class="text-secondary" style="padding:1rem;text-align:center;">⏳ 読み込み中...</p>';

    // システム状態
    try {
        const status = await api.getSystemStatus();
        if (statusEl) statusEl.innerHTML = createSystemStatusCard(status);
        if (diskEl && status.disk) diskEl.innerHTML = createDiskUsageTable(status.disk);
        else if (diskEl) showDataUnavailable('dashboard-disk', 'ディスク情報がありません');
    } catch (error) {
        console.error('Failed to load system status:', error);
        if (statusEl) showDataUnavailable('dashboard-system-status', 'システム状態を取得できませんでした');
        if (diskEl) showDataUnavailable('dashboard-disk', 'ディスク情報を取得できませんでした');
    }

    // 監査ログ（直近5件）
    try {
        const auditData = await api.getAuditLogs(1, 5);
        if (auditEl && auditData.entries && auditData.entries.length > 0) {
            const rows = auditData.entries.map(e => {
                const time = new Date(e.timestamp).toLocaleString('ja-JP', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
                const statusBadge = e.status === 'success' || e.status === 'attempt'
                    ? '<span class="status-badge status-active">成功</span>'
                    : '<span class="status-badge status-error">失敗</span>';
                return `<li style="padding:0.4rem 0;border-bottom:1px solid #e2e8f0;font-size:0.8rem;">
                    <strong>${time}</strong> - ${e.user_id} / ${e.operation} → ${statusBadge}
                </li>`;
            }).join('');
            auditEl.innerHTML = `<ul style="list-style:none;padding:0;">${rows}</ul>`;
        } else if (auditEl) {
            auditEl.innerHTML = '<p class="text-secondary" style="padding:0.5rem;">操作ログがありません</p>';
        }
    } catch (error) {
        console.error('Failed to load audit logs:', error);
        if (auditEl) auditEl.innerHTML = '<p class="text-secondary" style="padding:0.5rem;">操作ログを取得できませんでした</p>';
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
            <h3 class="card-title">サーバー状態</h3>
            <button class="btn btn-primary mb-1" onclick="loadServicesData()">更新</button>
            <div id="services-status-list"></div>
        </div>
    `;

    loadServicesData();
}

async function loadServicesData() {
    const el = document.getElementById('services-status-list');
    if (!el) return;
    el.innerHTML = '<p class="text-secondary" style="padding:1rem;text-align:center;">⏳ 読み込み中...</p>';

    try {
        const data = await api.getAllServerStatus();
        if (data && data.servers && Object.keys(data.servers).length > 0) {
            const rows = Object.entries(data.servers).map(([name, info]) => {
                const isActive = info.status === 'active';
                const badge = isActive
                    ? '<span class="status-badge status-active">実行中</span>'
                    : `<span class="status-badge status-inactive">${info.status || '停止'}</span>`;
                return `<tr>
                    <td><strong>${name}</strong></td>
                    <td>${badge}</td>
                    <td>${info.version || '-'}</td>
                    <td>${info.memory_mb ? info.memory_mb + ' MB' : '-'}</td>
                </tr>`;
            }).join('');
            el.innerHTML = `<table class="table"><thead>
                <tr><th>サービス名</th><th>状態</th><th>バージョン</th><th>メモリ</th></tr>
            </thead><tbody>${rows}</tbody></table>`;
        } else {
            el.innerHTML = '<p class="text-secondary" style="padding:1rem;">サーバー情報がありません</p>';
        }
    } catch (error) {
        console.error('Failed to load services:', error);
        el.innerHTML = '<p class="text-secondary" style="padding:1rem;">⚠️ サーバー状態を取得できませんでした</p>';
    }
}

/**
 * 操作ログページ（監査証跡）
 */
function showAuditLogPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">操作ログ（監査証跡）</h3>
            <div style="display: flex; gap: 1rem; margin-bottom: 1rem; flex-wrap: wrap; align-items: flex-end;">
                <button class="btn btn-primary" onclick="loadAuditLogs(1)">更新</button>
                <button class="btn btn-success" style="margin-left: auto;" onclick="exportAuditLogs()">CSV エクスポート</button>
            </div>
            <div id="audit-log-content"></div>
            <div id="audit-log-pagination" style="margin-top:1rem;text-align:center;"></div>
        </div>
    `;
    loadAuditLogs(1);
}

let auditCurrentPage = 1;
async function loadAuditLogs(page = 1) {
    auditCurrentPage = page;
    const el = document.getElementById('audit-log-content');
    if (!el) return;
    el.innerHTML = '<p class="text-secondary" style="padding:1rem;text-align:center;">⏳ 読み込み中...</p>';

    try {
        const data = await api.getAuditLogs(page, 20);
        if (data.entries && data.entries.length > 0) {
            const rows = data.entries.map(e => {
                const time = new Date(e.timestamp).toLocaleString('ja-JP');
                const statusBadge = e.status === 'success'
                    ? '<span class="status-badge status-active">成功</span>'
                    : e.status === 'attempt'
                    ? '<span class="status-badge" style="background:#fef3c7;color:#92400e;">試行</span>'
                    : '<span class="status-badge status-error">失敗</span>';
                return `<tr>
                    <td>${time}</td>
                    <td><strong>${e.user_id || '-'}</strong></td>
                    <td>${e.operation || '-'}</td>
                    <td>${e.target || '-'}</td>
                    <td>${statusBadge}</td>
                    <td style="font-size:0.75rem;max-width:200px;overflow:hidden;text-overflow:ellipsis;">${JSON.stringify(e.details || {})}</td>
                </tr>`;
            }).join('');
            el.innerHTML = `<table class="table">
                <thead><tr><th>日時</th><th>ユーザー</th><th>操作</th><th>対象</th><th>結果</th><th>詳細</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>`;

            // ページネーション
            const paginationEl = document.getElementById('audit-log-pagination');
            if (paginationEl && data.has_next !== undefined) {
                let paging = '';
                if (page > 1) paging += `<button class="btn btn-primary" style="margin-right:0.5rem;" onclick="loadAuditLogs(${page-1})">← 前のページ</button>`;
                paging += `<span style="margin:0 1rem;">ページ ${page} / 合計${data.total}件</span>`;
                if (data.has_next) paging += `<button class="btn btn-primary" onclick="loadAuditLogs(${page+1})">次のページ →</button>`;
                paginationEl.innerHTML = paging;
            }
        } else {
            el.innerHTML = '<p class="text-secondary" style="padding:1rem;">操作ログがありません</p>';
        }
    } catch (error) {
        console.error('Failed to load audit logs:', error);
        el.innerHTML = '<p class="text-secondary" style="padding:1rem;">⚠️ 監査ログを取得できませんでした</p>';
    }
}

async function exportAuditLogs() {
    try {
        const data = await api.exportAuditLogs();
        const blob = new Blob([typeof data === 'string' ? data : JSON.stringify(data, null, 2)], {type: 'text/plain'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = 'audit-logs.json'; a.click();
        URL.revokeObjectURL(url);
    } catch (error) {
        showAlert('エクスポートに失敗しました: ' + error.message, 'error');
    }
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

async function loadDiskUsage() {
    const diskEl = document.getElementById('disk-usage-detail');
    if (!diskEl) return;
    diskEl.innerHTML = '<p class="text-secondary" style="padding:1rem;text-align:center;">⏳ 読み込み中...</p>';

    try {
        const status = await api.getSystemStatus();
        if (status.disk && status.disk.length > 0) {
            diskEl.innerHTML = createDiskUsageTable(status.disk);
        } else {
            diskEl.innerHTML = '<p class="text-secondary" style="padding:1rem;">ディスク情報がありません</p>';
        }
    } catch (error) {
        console.error('Failed to load disk usage:', error);
        diskEl.innerHTML = '<p class="text-secondary" style="padding:1rem;">⚠️ ディスク情報を取得できませんでした</p>';
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
            <div id="logs-display-page"><p class="text-secondary" style="padding:1rem;">サービスを選択してログを取得してください</p></div>
        </div>
    `;
}

async function loadLogsForPage() {
    const serviceName = document.getElementById('log-service-page').value;
    const lines = parseInt(document.getElementById('log-lines-page').value, 10);
    const logsEl = document.getElementById('logs-display-page');

    if (!logsEl) return;
    logsEl.innerHTML = '<p class="text-secondary" style="padding:1rem;text-align:center;">⏳ ログ取得中...</p>';

    try {
        const result = await api.getLogs(serviceName, lines);
        if (result.status === 'success' && result.lines && result.lines.length > 0) {
            logsEl.innerHTML = createLogViewer(result.lines);
        } else if (result.status === 'success' && result.logs && result.logs.length > 0) {
            logsEl.innerHTML = createLogViewer(result.logs);
        } else {
            logsEl.innerHTML = '<p class="text-secondary" style="padding:1rem;">ログデータがありません</p>';
        }
    } catch (error) {
        console.error('Failed to load logs:', error);
        logsEl.innerHTML = '<p class="text-secondary" style="padding:1rem;">⚠️ ログを取得できませんでした。サービスが実行されていない可能性があります。</p>';
    }
}

// ===================================================================
// Networking カテゴリのページ
// ===================================================================

function showFirewallPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">ファイアウォール（UFW/iptables）</h3>
            <button class="btn btn-primary mb-1" onclick="loadFirewallData()">更新</button>
            <div id="firewall-content"></div>
        </div>
    `;
    loadFirewallData();
}

async function loadFirewallData() {
    const el = document.getElementById('firewall-content');
    if (!el) return;
    el.innerHTML = '<p class="text-secondary" style="padding:1rem;text-align:center;">⏳ 読み込み中...</p>';

    try {
        const data = await api.getFirewallStatus();
        if (data) {
            const status = data.status || data.ufw_status || 'unknown';
            const rules = data.rules || data.policies || [];
            let html = `<div style="margin-bottom:1rem;">
                <strong>UFWステータス:</strong> 
                <span class="status-badge ${status === 'active' ? 'status-active' : 'status-inactive'}">${status}</span>
            </div>`;
            if (rules.length > 0) {
                const rows = rules.map(r => `<tr>
                    <td>${r.to || r.port || '-'}</td>
                    <td>${r.action || r.policy || '-'}</td>
                    <td>${r.from || r.source || '-'}</td>
                    <td>${r.comment || '-'}</td>
                </tr>`).join('');
                html += `<table class="table"><thead><tr><th>宛先/ポート</th><th>アクション</th><th>送信元</th><th>コメント</th></tr></thead>
                <tbody>${rows}</tbody></table>`;
            } else {
                html += '<p class="text-secondary">ルールがありません</p>';
            }
            el.innerHTML = html;
        }
    } catch (error) {
        console.error('Failed to load firewall:', error);
        el.innerHTML = '<p class="text-secondary" style="padding:1rem;">⚠️ ファイアウォール情報を取得できませんでした</p>';
    }
}

function showNetworkConfigPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">ネットワークインターフェース</h3>
            <button class="btn btn-primary mb-1" onclick="loadNetworkConfigData()">更新</button>
            <div id="network-config-content"></div>
        </div>
    `;
    loadNetworkConfigData();
}

async function loadNetworkConfigData() {
    const el = document.getElementById('network-config-content');
    if (!el) return;
    el.innerHTML = '<p class="text-secondary" style="padding:1rem;text-align:center;">⏳ 読み込み中...</p>';

    try {
        const data = await api.getNetworkInterfaces();
        if (data && data.interfaces && data.interfaces.length > 0) {
            const rows = data.interfaces.map(iface => `<tr>
                <td><strong>${iface.name || iface.interface || '-'}</strong></td>
                <td>${iface.ip4 || iface.ip_address || iface.addr || '-'}</td>
                <td>${iface.ip6 || '-'}</td>
                <td><span class="status-badge ${iface.is_up || iface.status === 'up' ? 'status-active' : 'status-inactive'}">${iface.is_up || iface.status === 'up' ? 'UP' : 'DOWN'}</span></td>
                <td>${iface.speed || iface.speed_mbps ? (iface.speed || iface.speed_mbps) + ' Mbps' : '-'}</td>
                <td>${iface.mac || iface.mac_address || '-'}</td>
            </tr>`).join('');
            el.innerHTML = `<table class="table"><thead>
                <tr><th>IF名</th><th>IPv4</th><th>IPv6</th><th>状態</th><th>速度</th><th>MAC</th></tr>
            </thead><tbody>${rows}</tbody></table>`;
        } else {
            el.innerHTML = '<p class="text-secondary" style="padding:1rem;">ネットワーク情報がありません</p>';
        }
    } catch (error) {
        console.error('Failed to load network config:', error);
        el.innerHTML = '<p class="text-secondary" style="padding:1rem;">⚠️ ネットワーク情報を取得できませんでした</p>';
    }
}

function showRoutingPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">ルーティングテーブル</h3>
            <button class="btn btn-primary mb-1" onclick="loadRoutingData()">更新</button>
            <div id="routing-content"></div>
        </div>
    `;
    loadRoutingData();
}

async function loadRoutingData() {
    const el = document.getElementById('routing-content');
    if (!el) return;
    el.innerHTML = '<p class="text-secondary" style="padding:1rem;text-align:center;">⏳ 読み込み中...</p>';

    try {
        const data = await api.getNetworkRoutes();
        if (data && data.routes && data.routes.length > 0) {
            const rows = data.routes.map(r => `<tr>
                <td>${r.destination || r.dest || '-'}</td>
                <td>${r.gateway || r.gw || '-'}</td>
                <td>${r.netmask || r.prefix || '-'}</td>
                <td>${r.interface || r.iface || '-'}</td>
                <td>${r.metric || '-'}</td>
            </tr>`).join('');
            el.innerHTML = `<table class="table"><thead>
                <tr><th>宛先</th><th>ゲートウェイ</th><th>サブネット</th><th>IF</th><th>メトリック</th></tr>
            </thead><tbody>${rows}</tbody></table>`;
        } else {
            el.innerHTML = '<p class="text-secondary" style="padding:1rem;">ルーティング情報がありません</p>';
        }
    } catch (error) {
        console.error('Failed to load routing:', error);
        el.innerHTML = '<p class="text-secondary" style="padding:1rem;">⚠️ ルーティング情報を取得できませんでした</p>';
    }
}

function showNetstatPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">ネットワーク接続状態</h3>
            <button class="btn btn-primary mb-1" onclick="loadNetstatData()">更新</button>
            <div id="netstat-content"></div>
        </div>
    `;
    loadNetstatData();
}

async function loadNetstatData() {
    const el = document.getElementById('netstat-content');
    if (!el) return;
    el.innerHTML = '<p class="text-secondary" style="padding:1rem;text-align:center;">⏳ 読み込み中...</p>';

    try {
        const data = await api.getNetworkConnections();
        if (data && data.connections && data.connections.length > 0) {
            const rows = data.connections.slice(0, 50).map(c => `<tr>
                <td>${c.proto || c.type || '-'}</td>
                <td>${c.local_address || c.local || '-'}</td>
                <td>${c.remote_address || c.remote || '-'}</td>
                <td>${c.state || '-'}</td>
                <td>${c.pid || '-'}</td>
                <td>${c.program || c.process || '-'}</td>
            </tr>`).join('');
            el.innerHTML = `<p class="text-secondary" style="font-size:0.85rem;margin-bottom:0.5rem;">表示: 上位50件 / 合計${data.connections.length}件</p>
            <table class="table"><thead>
                <tr><th>Proto</th><th>Local</th><th>Remote</th><th>State</th><th>PID</th><th>プロセス</th></tr>
            </thead><tbody>${rows}</tbody></table>`;
        } else {
            el.innerHTML = '<p class="text-secondary" style="padding:1rem;">接続情報がありません</p>';
        }
    } catch (error) {
        console.error('Failed to load netstat:', error);
        el.innerHTML = '<p class="text-secondary" style="padding:1rem;">⚠️ 接続状態を取得できませんでした</p>';
    }
}

function showBandwidthPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">帯域幅モニタリング</h3>
            <button class="btn btn-primary mb-1" onclick="loadBandwidthData()">更新</button>
            <div id="bandwidth-content"></div>
        </div>
    `;
    loadBandwidthData();
}

async function loadBandwidthData() {
    const el = document.getElementById('bandwidth-content');
    if (!el) return;
    el.innerHTML = '<p class="text-secondary" style="padding:1rem;text-align:center;">⏳ 読み込み中...</p>';

    try {
        const [summary, live] = await Promise.allSettled([
            api.getBandwidthSummary(),
            api.getBandwidthLive()
        ]);

        if (summary.status === 'fulfilled' && summary.value.status !== 'unavailable') {
            const d = summary.value;
            const rxBytes = d.rx_bytes ? (d.rx_bytes / 1024 / 1024).toFixed(2) + ' MB' : '-';
            const txBytes = d.tx_bytes ? (d.tx_bytes / 1024 / 1024).toFixed(2) + ' MB' : '-';
            el.innerHTML = `<div class="grid grid-2">
                <div class="card"><h4>受信 (RX)</h4><p style="font-size:2rem;font-weight:600;color:#2563eb;">${rxBytes}</p></div>
                <div class="card"><h4>送信 (TX)</h4><p style="font-size:2rem;font-weight:600;color:#10b981;">${txBytes}</p></div>
            </div>
            <p class="text-secondary" style="font-size:0.85rem;margin-top:0.5rem;">インターフェース: ${d.interface || '-'} | ソース: ${d.source || '-'}</p>`;
        } else if (summary.value && summary.value.message) {
            el.innerHTML = `<p class="text-secondary" style="padding:1rem;">ℹ️ ${summary.value.message}</p>
            <div id="bandwidth-live-data"></div>`;
            // ライブデータを試みる
            if (live.status === 'fulfilled') {
                const liveEl = document.getElementById('bandwidth-live-data');
                if (liveEl && live.value && live.value.interfaces) {
                    const rows = Object.entries(live.value.interfaces).map(([iface, stats]) => `<tr>
                        <td>${iface}</td>
                        <td>${stats.rx_bytes_formatted || stats.rx_rate || '-'}</td>
                        <td>${stats.tx_bytes_formatted || stats.tx_rate || '-'}</td>
                    </tr>`).join('');
                    liveEl.innerHTML = `<table class="table"><thead><tr><th>IF</th><th>受信</th><th>送信</th></tr></thead><tbody>${rows}</tbody></table>`;
                }
            }
        } else {
            el.innerHTML = '<p class="text-secondary" style="padding:1rem;">帯域幅データがありません</p>';
        }
    } catch (error) {
        console.error('Failed to load bandwidth:', error);
        el.innerHTML = '<p class="text-secondary" style="padding:1rem;">⚠️ 帯域幅情報を取得できませんでした</p>';
    }
}

// Hardware カテゴリ
async function showPartitionsPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">ローカルディスク・パーティション</h3>
            <button class="btn btn-primary mb-1" onclick="loadPartitionsData()">更新</button>
            <div id="partitions-detail"></div>
        </div>
    `;
    loadPartitionsData();
}

async function loadPartitionsData() {
    const diskEl = document.getElementById('partitions-detail');
    if (!diskEl) return;
    diskEl.innerHTML = '<p class="text-secondary" style="padding:1rem;text-align:center;">⏳ 読み込み中...</p>';

    try {
        const status = await api.getSystemStatus();
        if (status.disk && status.disk.length > 0) {
            diskEl.innerHTML = createDiskUsageTable(status.disk);
        } else {
            diskEl.innerHTML = '<p class="text-secondary" style="padding:1rem;">ディスク情報がありません</p>';
        }
    } catch (error) {
        console.error('Failed to load partition data:', error);
        diskEl.innerHTML = '<p class="text-secondary" style="padding:1rem;">⚠️ ディスク情報を取得できませんでした</p>';
    }
}

function showSystemTimePage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">システム時刻</h3>
            <button class="btn btn-primary mb-1" onclick="loadTimeData()">更新</button>
            <div id="time-content"></div>
        </div>
    `;
    loadTimeData();
    // ローカル時刻は常に表示
    setInterval(() => {
        const el = document.getElementById('local-time-live');
        if (el) el.textContent = new Date().toLocaleString('ja-JP');
    }, 1000);
}

async function loadTimeData() {
    const el = document.getElementById('time-content');
    if (!el) return;
    el.innerHTML = '<p class="text-secondary" style="padding:1rem;text-align:center;">⏳ 読み込み中...</p>';

    try {
        const data = await api.getTimeStatus();
        if (data && data.data) {
            const d = data.data;
            el.innerHTML = `
                <div class="grid grid-2">
                    <div class="card">
                        <h4>システム時刻</h4>
                        <p style="font-size:1.5rem;font-weight:600;color:#2563eb;" id="local-time-live">${new Date().toLocaleString('ja-JP')}</p>
                    </div>
                    <div class="card">
                        <h4>UTC時刻</h4>
                        <p style="font-size:1.5rem;font-weight:600;">${d.utc_time || '-'}</p>
                    </div>
                </div>
                <table class="table" style="margin-top:1rem;">
                    <tbody>
                        <tr><td>タイムゾーン</td><td><strong>${d.timezone || '-'}</strong></td></tr>
                        <tr><td>NTP同期</td><td><span class="status-badge ${d.ntp_synchronized === 'yes' ? 'status-active' : 'status-warning'}">${d.ntp_synchronized || '-'}</span></td></tr>
                        <tr><td>NTPサービス</td><td>${d.ntp_service || '-'}</td></tr>
                        <tr><td>RTC時刻</td><td>${d.rtc_time || '-'}</td></tr>
                    </tbody>
                </table>`;
        }
    } catch (error) {
        console.error('Failed to load time:', error);
        el.innerHTML = `<div class="card">
            <h4>ローカル時刻（ブラウザ）</h4>
            <p style="font-size:1.5rem;font-weight:600;color:#2563eb;" id="local-time-live">${new Date().toLocaleString('ja-JP')}</p>
        </div>
        <p class="text-secondary" style="margin-top:0.5rem;">⚠️ サーバー時刻を取得できませんでした</p>`;
    }
}

function showSmartStatusPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">S.M.A.R.T. ドライブ状態</h3>
            <button class="btn btn-primary mb-1" onclick="loadSmartData()">更新</button>
            <div id="smart-content"></div>
        </div>
    `;
    loadSmartData();
}

async function loadSmartData() {
    const el = document.getElementById('smart-content');
    if (!el) return;
    el.innerHTML = '<p class="text-secondary" style="padding:1rem;text-align:center;">⏳ 読み込み中...</p>';

    try {
        const disks = await api.getHardwareDisks();
        if (disks && disks.disks && disks.disks.length > 0) {
            const rows = disks.disks.map(d => `<tr>
                <td><strong>${d.device || d.name || '-'}</strong></td>
                <td>${d.model || '-'}</td>
                <td>${d.size || '-'}</td>
                <td><span class="status-badge ${d.health === 'PASSED' || d.health === '正常' ? 'status-active' : 'status-warning'}">${d.health || '情報なし'}</span></td>
                <td>${d.temperature ? d.temperature + '°C' : '-'}</td>
            </tr>`).join('');
            el.innerHTML = `<table class="table"><thead>
                <tr><th>デバイス</th><th>モデル</th><th>容量</th><th>状態</th><th>温度</th></tr>
            </thead><tbody>${rows}</tbody></table>`;
        } else {
            el.innerHTML = '<p class="text-secondary" style="padding:1rem;">ディスク情報がありません</p>';
        }
    } catch (error) {
        console.error('Failed to load SMART data:', error);
        el.innerHTML = '<p class="text-secondary" style="padding:1rem;">⚠️ ディスク情報を取得できませんでした</p>';
    }
}

function showSensorsPage(container) {
    container.innerHTML = `
        <div class="card">
            <h3 class="card-title">センサー情報 (lm-sensors)</h3>
            <button class="btn btn-primary mb-1" onclick="loadSensorsData()">更新</button>
            <div id="sensors-content"></div>
        </div>
    `;
    loadSensorsData();
}

async function loadSensorsData() {
    const el = document.getElementById('sensors-content');
    if (!el) return;
    el.innerHTML = '<p class="text-secondary" style="padding:1rem;text-align:center;">⏳ 読み込み中...</p>';

    try {
        const data = await api.getHardwareSensors();
        if (data && data.sensors && data.sensors.length > 0) {
            const items = data.sensors.map(s => `
                <div class="card" style="text-align:center;">
                    <h4 style="font-size:0.85rem;color:#6b7280;">${s.name || s.sensor || '-'}</h4>
                    <p style="font-size:1.8rem;font-weight:600;color:${(s.temp || s.value || 0) > 70 ? '#ef4444' : '#10b981'};">${s.temp || s.value || '-'}${s.unit || '°C'}</p>
                    <p style="font-size:0.75rem;color:#9ca3af;">${s.chip || s.type || ''}</p>
                </div>`).join('');
            el.innerHTML = `<div class="grid grid-3">${items}</div>`;
        } else if (data && data.message) {
            el.innerHTML = `<p class="text-secondary" style="padding:1rem;">ℹ️ ${data.message}</p>`;
        } else {
            el.innerHTML = '<p class="text-secondary" style="padding:1rem;">センサー情報がありません（lm-sensorsがインストールされていない可能性があります）</p>';
        }
    } catch (error) {
        console.error('Failed to load sensors:', error);
        el.innerHTML = '<p class="text-secondary" style="padding:1rem;">⚠️ センサー情報を取得できませんでした</p>';
    }
}
