/**
 * Running Processes モジュール
 * プロセス一覧の取得・表示・フィルタリング・リアルタイム更新
 */

class ProcessManager {
    constructor() {
        this.processes = [];
        this.autoRefreshInterval = null;
        this.autoRefreshEnabled = false;
        this.currentFilters = {
            sortBy: 'cpu',
            user: '',
            minCpu: 0.0,
            minMem: 0.0,
            limit: 100
        };

        this.init();
    }

    /**
     * 初期化
     */
    init() {
        console.log('ProcessManager: Initializing...');

        // イベントリスナーの設定
        this.setupEventListeners();

        // 初回ロード
        this.loadProcesses();
    }

    /**
     * イベントリスナーの設定
     */
    setupEventListeners() {
        // Refresh ボタン
        document.getElementById('refreshBtn').addEventListener('click', () => {
            this.loadProcesses();
        });

        // Auto-Refresh トグル
        document.getElementById('autoRefreshBtn').addEventListener('click', () => {
            this.toggleAutoRefresh();
        });

        // フィルタ変更時
        document.getElementById('sortBy').addEventListener('change', (e) => {
            this.currentFilters.sortBy = e.target.value;
            this.loadProcesses();
        });

        document.getElementById('filterUser').addEventListener('input', (e) => {
            // 特殊文字検証（XSS対策）
            const value = e.target.value;
            if (!/^[a-zA-Z0-9_-]*$/.test(value)) {
                e.target.setCustomValidity('英数字、ハイフン、アンダースコアのみ使用可能です');
                return;
            }
            e.target.setCustomValidity('');
            this.currentFilters.user = value;
        });

        // フィルタ適用（Enterキー）
        document.getElementById('filterUser').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.loadProcesses();
            }
        });

        document.getElementById('minCpu').addEventListener('change', (e) => {
            this.currentFilters.minCpu = parseFloat(e.target.value) || 0.0;
            this.loadProcesses();
        });

        document.getElementById('minMem').addEventListener('change', (e) => {
            this.currentFilters.minMem = parseFloat(e.target.value) || 0.0;
            this.loadProcesses();
        });

        document.getElementById('limitCount').addEventListener('change', (e) => {
            this.currentFilters.limit = parseInt(e.target.value, 10);
            this.loadProcesses();
        });
    }

    /**
     * プロセス一覧を取得
     */
    async loadProcesses() {
        console.log('ProcessManager: Loading processes...', this.currentFilters);

        // ローディング表示
        this.showLoading();

        try {
            // API呼び出し
            const params = new URLSearchParams();
            params.append('sort_by', this.currentFilters.sortBy);
            params.append('limit', this.currentFilters.limit);

            if (this.currentFilters.user) {
                params.append('filter_user', this.currentFilters.user);
            }
            if (this.currentFilters.minCpu > 0) {
                params.append('min_cpu', this.currentFilters.minCpu);
            }
            if (this.currentFilters.minMem > 0) {
                params.append('min_mem', this.currentFilters.minMem);
            }

            const response = await api.request('GET', `/api/processes?${params.toString()}`);

            console.log('ProcessManager: Processes loaded', response);

            this.processes = response.processes;

            // テーブル描画
            this.renderProcessTable();

            // 統計情報表示（将来拡張用）
            this.renderStats(response);

            // 成功メッセージ
            this.showStatus('success', `✅ ${response.returned_processes} プロセスを取得しました`);

            // ページネーション情報
            this.updatePaginationInfo(response.returned_processes, response.total_processes);

        } catch (error) {
            console.error('ProcessManager: Failed to load processes', error);
            this.showStatus('error', `❌ プロセス取得失敗: ${error.message}`);
            this.showNoData('エラーが発生しました');
        }
    }

    /**
     * プロセステーブルを描画
     */
    renderProcessTable() {
        const tbody = document.getElementById('processTableBody');
        tbody.innerHTML = '';

        if (this.processes.length === 0) {
            this.showNoData('プロセスが見つかりませんでした');
            return;
        }

        this.processes.forEach(proc => {
            const row = document.createElement('tr');

            // 高CPU/高メモリのハイライト
            if (proc.cpu_percent > 50) {
                row.classList.add('high-cpu');
            }
            if (proc.mem_percent > 50) {
                row.classList.add('high-memory');
            }

            // PID
            const pidCell = document.createElement('td');
            pidCell.textContent = proc.pid;
            row.appendChild(pidCell);

            // Name
            const nameCell = document.createElement('td');
            nameCell.textContent = proc.name || '-';
            row.appendChild(nameCell);

            // User
            const userCell = document.createElement('td');
            userCell.textContent = proc.user;
            row.appendChild(userCell);

            // CPU %
            const cpuCell = document.createElement('td');
            cpuCell.className = 'cpu-usage';
            const cpuPercent = proc.cpu_percent;  // Already a percentage
            cpuCell.textContent = cpuPercent.toFixed(1);
            if (cpuPercent < 10) {
                cpuCell.classList.add('cpu-low');
            } else if (cpuPercent < 50) {
                cpuCell.classList.add('cpu-medium');
            } else {
                cpuCell.classList.add('cpu-high');
            }
            row.appendChild(cpuCell);

            // Memory %
            const memCell = document.createElement('td');
            memCell.className = 'mem-usage';
            const memPercent = proc.mem_percent;  // Already a percentage
            memCell.textContent = memPercent.toFixed(1);
            if (memPercent < 10) {
                memCell.classList.add('cpu-low');
            } else if (memPercent < 50) {
                memCell.classList.add('cpu-medium');
            } else {
                memCell.classList.add('cpu-high');
            }
            row.appendChild(memCell);

            // RSS (MB)
            const rssCell = document.createElement('td');
            rssCell.textContent = proc.rss ? proc.rss.toFixed(1) : '-';  // rss not memory_rss_mb
            rssCell.style.textAlign = 'right';
            row.appendChild(rssCell);

            // State
            const stateCell = document.createElement('td');
            const stateBadge = document.createElement('span');
            stateBadge.className = `state-badge state-${proc.stat}`;  // stat not state
            stateBadge.textContent = proc.stat;  // stat not state
            stateCell.appendChild(stateBadge);
            row.appendChild(stateCell);

            // Started
            const startedCell = document.createElement('td');
            startedCell.textContent = this.formatDateTime(proc.start);  // start not started_at
            startedCell.style.fontSize = '11px';
            row.appendChild(startedCell);

            // Time
            const timeCell = document.createElement('td');
            timeCell.textContent = proc.time || '-';
            timeCell.style.fontSize = '11px';
            row.appendChild(timeCell);

            // Command
            const commandCell = document.createElement('td');
            commandCell.className = 'command';
            commandCell.textContent = proc.command;
            commandCell.title = proc.command; // ツールチップで全文表示
            row.appendChild(commandCell);

            // クリックイベント（詳細モーダル表示）
            row.addEventListener('click', () => {
                this.showProcessDetail(proc.pid);
            });

            tbody.appendChild(row);
        });
    }

    /**
     * 統計情報を描画（将来拡張用）
     */
    renderStats(data) {
        // 現在は統計APIが未実装のため、基本情報のみ表示
        document.getElementById('stat-total').textContent = data.total_count || '-';
        document.getElementById('stat-running').textContent = '-';
        document.getElementById('stat-sleeping').textContent = '-';
        document.getElementById('stat-cpu').textContent = '-';
        document.getElementById('stat-memory').textContent = '-';

        // 統計カードを表示
        // document.getElementById('statsCard').style.display = 'block';
    }

    /**
     * プロセス詳細モーダルを表示
     */
    async showProcessDetail(pid) {
        console.log('ProcessManager: Showing detail for PID', pid);

        const modalBody = document.getElementById('processDetailBody');
        modalBody.innerHTML = '<p class="loading">Loading details...</p>';

        // モーダルを表示
        const modal = new bootstrap.Modal(document.getElementById('processDetailModal'));
        modal.show();

        try {
            // API呼び出し（プロセス詳細取得 - 将来実装）
            // const response = await api.request('GET', `/api/processes/${pid}`);

            // 現在は一覧データから表示
            const proc = this.processes.find(p => p.pid === pid);
            if (!proc) {
                modalBody.innerHTML = '<p class="error">プロセスが見つかりませんでした</p>';
                return;
            }

            // 詳細情報を表示
            modalBody.innerHTML = `
                <div class="row">
                    <div class="col-md-6">
                        <p><strong>PID:</strong> ${this.escapeHtml(proc.pid.toString())}</p>
                        <p><strong>Name:</strong> ${this.escapeHtml(proc.name || '-')}</p>
                        <p><strong>User:</strong> ${this.escapeHtml(proc.user)}</p>
                        <p><strong>State:</strong> <span class="state-badge state-${proc.stat}">${proc.stat}</span></p>
                    </div>
                    <div class="col-md-6">
                        <p><strong>CPU %:</strong> ${proc.cpu_percent.toFixed(2)}</p>
                        <p><strong>Memory %:</strong> ${proc.mem_percent.toFixed(2)}</p>
                        <p><strong>RSS (KB):</strong> ${proc.rss ? proc.rss.toFixed(0) : '-'}</p>
                        <p><strong>Started:</strong> ${this.escapeHtml(this.formatDateTime(proc.start))}</p>
                    </div>
                </div>
                <hr>
                <p><strong>Command:</strong></p>
                <pre style="background-color: #f8f9fa; padding: 10px; border-radius: 5px; font-size: 12px; overflow-x: auto;">${this.escapeHtml(proc.command)}</pre>
            `;

        } catch (error) {
            console.error('ProcessManager: Failed to load process detail', error);
            modalBody.innerHTML = `<p class="error">詳細情報の取得に失敗しました: ${this.escapeHtml(error.message)}</p>`;
        }
    }

    /**
     * Auto-Refresh トグル
     */
    toggleAutoRefresh() {
        this.autoRefreshEnabled = !this.autoRefreshEnabled;

        const btn = document.getElementById('autoRefreshBtn');

        if (this.autoRefreshEnabled) {
            btn.textContent = '⏱️ Auto-Refresh: ON';
            btn.classList.add('active');

            // 5秒間隔で自動更新
            this.autoRefreshInterval = setInterval(() => {
                this.loadProcesses();
            }, 5000);

            this.showStatus('info', '🔄 自動更新が有効になりました（5秒間隔）');
        } else {
            btn.textContent = '⏱️ Auto-Refresh: OFF';
            btn.classList.remove('active');

            if (this.autoRefreshInterval) {
                clearInterval(this.autoRefreshInterval);
                this.autoRefreshInterval = null;
            }

            this.showStatus('info', '⏸️ 自動更新が無効になりました');
        }
    }

    /**
     * ステータスメッセージを表示
     */
    showStatus(type, message) {
        const statusDiv = document.getElementById('statusDisplay');
        statusDiv.className = `status ${type}`;
        statusDiv.textContent = message;

        // 3秒後に非表示
        setTimeout(() => {
            statusDiv.textContent = '';
            statusDiv.className = '';
        }, 3000);
    }

    /**
     * ローディング表示
     */
    showLoading() {
        const tbody = document.getElementById('processTableBody');
        tbody.innerHTML = '<tr><td colspan="10" class="loading">Loading processes...</td></tr>';
    }

    /**
     * データなし表示
     */
    showNoData(message) {
        const tbody = document.getElementById('processTableBody');
        tbody.innerHTML = `<tr><td colspan="10" class="no-data">${this.escapeHtml(message)}</td></tr>`;
    }

    /**
     * ページネーション情報を更新
     */
    updatePaginationInfo(returned, total) {
        const infoDiv = document.getElementById('paginationInfo');
        infoDiv.textContent = `表示: ${returned} / ${total} プロセス`;
    }

    /**
     * 日時フォーマット
     */
    formatDateTime(isoString) {
        if (!isoString) return '-';

        try {
            const date = new Date(isoString);
            const now = new Date();
            const diff = now - date;

            // 24時間以内なら相対時間表示
            if (diff < 86400000) {
                const hours = Math.floor(diff / 3600000);
                const minutes = Math.floor((diff % 3600000) / 60000);
                if (hours > 0) {
                    return `${hours}時間前`;
                } else if (minutes > 0) {
                    return `${minutes}分前`;
                } else {
                    return '数秒前';
                }
            }

            // それ以外は日時表示
            return date.toLocaleString('ja-JP', {
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch (e) {
            return isoString;
        }
    }

    /**
     * HTML エスケープ（XSS対策）
     */
    escapeHtml(text) {
        if (typeof text !== 'string') {
            text = String(text);
        }

        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// ページロード時に初期化
document.addEventListener('DOMContentLoaded', async function() {
    console.log('Initializing ProcessManager...');

    // 認証チェック
    if (!api.isAuthenticated()) {
        console.warn('Not authenticated, redirecting to login');
        window.location.href = '/dev/index.html';
        return;
    }

    try {
        // ユーザー情報を取得してサイドバーに表示
        const currentUser = await api.getCurrentUser();
        if (typeof updateSidebarUserInfo === 'function') {
            updateSidebarUserInfo(currentUser);
        }
    } catch (error) {
        console.error('Failed to load user info:', error);
    }

    // アコーディオンの状態を復元
    if (typeof restoreAccordionState === 'function') {
        restoreAccordionState();
    }

    // ProcessManager 初期化
    window.processManager = new ProcessManager();
});
