/**
 * cron.js - Cron Jobs Management UI
 *
 * Features:
 * - Cron job list per user (with user selector)
 * - Add form with schedule presets and command allowlist
 * - Enable/disable toggle
 * - Delete (comment-out) functionality
 * - XSS prevention (escapeHtml)
 * - Role-based UI (Admin: full control, others: read-only + approval)
 */

class CronManager {
    constructor() {
        this.jobs = [];
        this.currentUser = null;
        this.selectedUsername = '';
        this.autoRefreshInterval = null;
        this.autoRefreshEnabled = false;
        this.maxAllowed = 10;
        this.totalCount = 0;

        // Allowlist (mirrors backend ALLOWED_CRON_COMMANDS)
        this.allowedCommands = [
            '/usr/bin/rsync',
            '/usr/local/bin/healthcheck.sh',
            '/usr/bin/find',
            '/usr/bin/tar',
            '/usr/bin/gzip',
            '/usr/bin/curl',
            '/usr/bin/wget',
            '/usr/bin/python3',
            '/usr/bin/node',
        ];

        // Schedule presets
        this.schedulePresets = [
            { label: '5分毎', value: '*/5 * * * *' },
            { label: '15分毎', value: '*/15 * * * *' },
            { label: '30分毎', value: '*/30 * * * *' },
            { label: '毎時', value: '0 * * * *' },
            { label: '毎日 0:00', value: '0 0 * * *' },
            { label: '毎日 2:00', value: '0 2 * * *' },
            { label: '毎日 6:00', value: '0 6 * * *' },
            { label: '毎週月曜', value: '0 0 * * 1' },
            { label: '毎月1日', value: '0 0 1 * *' },
        ];

        // Forbidden argument chars
        this.forbiddenArgChars = /[;|&$(){}\[\]`]/;

        this.init();
    }

    /**
     * 初期化
     */
    init() {
        console.log('CronManager: Initializing...');
        this.setupEventListeners();
    }

    /**
     * イベントリスナーの設定
     */
    setupEventListeners() {
        // Refresh ボタン
        const refreshBtn = document.getElementById('refreshBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.loadCronJobs();
            });
        }

        // Auto-Refresh トグル
        const autoRefreshBtn = document.getElementById('autoRefreshBtn');
        if (autoRefreshBtn) {
            autoRefreshBtn.addEventListener('click', () => {
                this.toggleAutoRefresh();
            });
        }

        // ユーザーセレクタ変更
        const userSelect = document.getElementById('cronUserSelect');
        if (userSelect) {
            userSelect.addEventListener('change', (e) => {
                this.selectedUsername = e.target.value;
                if (this.selectedUsername) {
                    this.loadCronJobs();
                } else {
                    this.clearJobTable();
                }
            });
        }

        // ジョブ追加ボタン
        const addJobBtn = document.getElementById('addCronJobBtn');
        if (addJobBtn) {
            addJobBtn.addEventListener('click', () => {
                this.showAddJobModal();
            });
        }

        // スケジュールプリセット選択
        const presetSelect = document.getElementById('schedulePreset');
        if (presetSelect) {
            presetSelect.addEventListener('change', (e) => {
                const scheduleInput = document.getElementById('cronSchedule');
                if (scheduleInput && e.target.value) {
                    scheduleInput.value = e.target.value;
                    this.updateSchedulePreview();
                }
            });
        }

        // スケジュール入力変更時
        const scheduleInput = document.getElementById('cronSchedule');
        if (scheduleInput) {
            scheduleInput.addEventListener('input', () => {
                this.updateSchedulePreview();
            });
        }

        // ジョブ追加フォーム送信
        const addJobForm = document.getElementById('addCronJobForm');
        if (addJobForm) {
            addJobForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleAddJob();
            });
        }
    }

    /**
     * ユーザー一覧をロード（ユーザーセレクタ用）
     */
    async loadUserList() {
        try {
            const result = await api.request('GET', '/api/users?limit=500');
            const userSelect = document.getElementById('cronUserSelect');
            if (!userSelect) return;

            // 既存オプションをクリア（最初のプレースホルダを残す）
            while (userSelect.options.length > 1) {
                userSelect.remove(1);
            }

            const users = result.users || [];
            users.forEach(user => {
                const option = document.createElement('option');
                option.value = user.username;
                option.textContent = `${user.username} (UID: ${user.uid})`;
                userSelect.appendChild(option);
            });

            // 自分自身を選択状態にする
            if (this.currentUser && this.currentUser.role !== 'admin') {
                userSelect.value = this.currentUser.username;
                this.selectedUsername = this.currentUser.username;
                userSelect.disabled = true;
                this.loadCronJobs();
            }
        } catch (error) {
            console.error('Failed to load user list:', error);
            this.showAlert('danger', 'ユーザー一覧の取得に失敗しました');
        }
    }

    /**
     * Cron ジョブ一覧をロード
     */
    async loadCronJobs() {
        if (!this.selectedUsername) {
            this.showAlert('warning', 'ユーザーを選択してください');
            return;
        }

        const tableBody = document.getElementById('cronJobsTableBody');
        const loadingSpinner = document.getElementById('cronLoadingSpinner');
        const statusText = document.getElementById('cronStatusText');

        if (loadingSpinner) loadingSpinner.style.display = 'block';
        if (statusText) statusText.textContent = '読み込み中...';

        try {
            const result = await api.request('GET', `/api/cron/${encodeURIComponent(this.selectedUsername)}`);

            this.jobs = result.jobs || [];
            this.totalCount = result.total_count || 0;
            this.maxAllowed = result.max_allowed || 10;

            this.renderJobTable();

            if (statusText) {
                statusText.textContent =
                    `${this.totalCount}件のジョブ（最大${this.maxAllowed}件）`;
            }

            // 追加ボタンの状態更新
            this.updateAddButtonState();

        } catch (error) {
            console.error('Failed to load cron jobs:', error);
            if (statusText) statusText.textContent = 'エラー';
            this.showAlert('danger', `Cronジョブの取得に失敗しました: ${this.escapeHtml(error.message || 'Unknown error')}`);
            this.clearJobTable();
        } finally {
            if (loadingSpinner) loadingSpinner.style.display = 'none';
        }
    }

    /**
     * ジョブテーブルを描画
     */
    renderJobTable() {
        const tableBody = document.getElementById('cronJobsTableBody');
        if (!tableBody) return;

        if (this.jobs.length === 0) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="7" class="text-center text-muted py-4">
                        Cronジョブが登録されていません
                    </td>
                </tr>
            `;
            return;
        }

        const isAdmin = this.currentUser && this.currentUser.role === 'admin';

        tableBody.innerHTML = this.jobs.map(job => `
            <tr class="${job.enabled ? '' : 'table-secondary'}">
                <td>
                    <span class="badge ${job.enabled ? 'bg-success' : 'bg-secondary'}">
                        ${job.enabled ? '有効' : '無効'}
                    </span>
                </td>
                <td><code>${this.escapeHtml(job.schedule)}</code></td>
                <td title="${this.escapeHtml(job.command)}">
                    <code>${this.escapeHtml(this.getCommandShortName(job.command))}</code>
                </td>
                <td class="text-truncate" style="max-width: 200px;"
                    title="${this.escapeHtml(job.arguments || '')}">
                    ${this.escapeHtml(job.arguments || '-')}
                </td>
                <td>${this.escapeHtml(job.comment || '-')}</td>
                <td>${job.line_number}</td>
                <td>
                    ${isAdmin ? this.renderJobActions(job) : '<span class="text-muted">-</span>'}
                </td>
            </tr>
        `).join('');

        // イベントリスナーをアクションボタンに設定
        if (isAdmin) {
            this.attachJobActionListeners();
        }
    }

    /**
     * ジョブアクションボタンをレンダリング
     */
    renderJobActions(job) {
        const toggleLabel = job.enabled ? '無効化' : '有効化';
        const toggleClass = job.enabled ? 'btn-outline-warning' : 'btn-outline-success';
        const toggleIcon = job.enabled ? 'pause' : 'play';

        return `
            <div class="btn-group btn-group-sm">
                <button class="btn ${toggleClass} toggle-job-btn"
                    data-line="${job.line_number}" data-enabled="${job.enabled}"
                    title="${toggleLabel}">
                    <i class="bi bi-${toggleIcon}-fill"></i>
                </button>
                <button class="btn btn-outline-danger delete-job-btn"
                    data-line="${job.line_number}" title="削除">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        `;
    }

    /**
     * ジョブアクションのイベントリスナーを設定
     */
    attachJobActionListeners() {
        // トグルボタン
        document.querySelectorAll('.toggle-job-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const target = e.currentTarget;
                const lineNumber = parseInt(target.dataset.line, 10);
                const currentEnabled = target.dataset.enabled === 'true';
                this.handleToggleJob(lineNumber, !currentEnabled);
            });
        });

        // 削除ボタン
        document.querySelectorAll('.delete-job-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const target = e.currentTarget;
                const lineNumber = parseInt(target.dataset.line, 10);
                this.handleDeleteJob(lineNumber);
            });
        });
    }

    /**
     * ジョブの有効/無効を切り替え
     */
    async handleToggleJob(lineNumber, enabled) {
        const action = enabled ? '有効化' : '無効化';
        if (!confirm(`行番号 ${lineNumber} のジョブを${action}しますか？`)) {
            return;
        }

        try {
            await api.request('PUT', `/api/cron/${encodeURIComponent(this.selectedUsername)}/toggle`, {
                line_number: lineNumber,
                enabled: enabled
            });

            this.showAlert('success', `ジョブを${action}しました`);
            await this.loadCronJobs();

        } catch (error) {
            console.error('Failed to toggle cron job:', error);
            this.showAlert('danger', `ジョブの${action}に失敗しました: ${this.escapeHtml(error.message || 'Unknown error')}`);
        }
    }

    /**
     * ジョブを削除（コメントアウト）
     */
    async handleDeleteJob(lineNumber) {
        if (!confirm(`行番号 ${lineNumber} のジョブを削除しますか？\n（コメントアウトされます）`)) {
            return;
        }

        try {
            await api.request('DELETE', `/api/cron/${encodeURIComponent(this.selectedUsername)}`, {
                line_number: lineNumber
            });

            this.showAlert('success', 'ジョブを削除しました');
            await this.loadCronJobs();

        } catch (error) {
            console.error('Failed to delete cron job:', error);
            this.showAlert('danger', `ジョブの削除に失敗しました: ${this.escapeHtml(error.message || 'Unknown error')}`);
        }
    }

    /**
     * ジョブ追加モーダルを表示
     */
    showAddJobModal() {
        if (!this.selectedUsername) {
            this.showAlert('warning', 'ユーザーを選択してください');
            return;
        }

        // フォームリセット
        const form = document.getElementById('addCronJobForm');
        if (form) form.reset();

        // コマンドセレクタにallowlistを反映
        const commandSelect = document.getElementById('cronCommand');
        if (commandSelect) {
            commandSelect.innerHTML = '<option value="">コマンドを選択...</option>';
            this.allowedCommands.forEach(cmd => {
                const option = document.createElement('option');
                option.value = cmd;
                option.textContent = cmd;
                commandSelect.appendChild(option);
            });
        }

        // プリセットセレクタに値を反映
        const presetSelect = document.getElementById('schedulePreset');
        if (presetSelect) {
            presetSelect.innerHTML = '<option value="">プリセットを選択...</option>';
            this.schedulePresets.forEach(preset => {
                const option = document.createElement('option');
                option.value = preset.value;
                option.textContent = `${preset.label} (${preset.value})`;
                presetSelect.appendChild(option);
            });
        }

        // ターゲットユーザー表示
        const targetLabel = document.getElementById('addJobTargetUser');
        if (targetLabel) {
            targetLabel.textContent = this.selectedUsername;
        }

        // ジョブ数残り表示
        const remainingLabel = document.getElementById('addJobRemaining');
        if (remainingLabel) {
            const remaining = this.maxAllowed - this.totalCount;
            remainingLabel.textContent = `残り ${remaining} / ${this.maxAllowed} 件`;
            remainingLabel.className = remaining <= 2 ? 'text-danger fw-bold' : 'text-muted';
        }

        // スケジュールプレビューをクリア
        const preview = document.getElementById('schedulePreview');
        if (preview) preview.textContent = '';

        // モーダルを表示
        const modal = new bootstrap.Modal(document.getElementById('addCronJobModal'));
        modal.show();
    }

    /**
     * スケジュール文字列のプレビューを更新
     */
    updateSchedulePreview() {
        const scheduleInput = document.getElementById('cronSchedule');
        const preview = document.getElementById('schedulePreview');
        if (!scheduleInput || !preview) return;

        const value = scheduleInput.value.trim();
        if (!value) {
            preview.textContent = '';
            return;
        }

        const parts = value.split(/\s+/);
        if (parts.length !== 5) {
            preview.textContent = '(5フィールド必須: 分 時 日 月 曜日)';
            preview.className = 'form-text text-danger';
            return;
        }

        const description = this.describeCronSchedule(parts);
        preview.textContent = description;
        preview.className = 'form-text text-success';
    }

    /**
     * Cron 式を人間可読な説明に変換
     */
    describeCronSchedule(parts) {
        const [minute, hour, dom, month, dow] = parts;
        let desc = '';

        // 曜日
        const dowNames = ['日', '月', '火', '水', '木', '金', '土'];
        if (dow !== '*') {
            const dowNum = parseInt(dow, 10);
            if (dowNum >= 0 && dowNum <= 6) {
                desc += `毎週${dowNames[dowNum]}曜 `;
            } else {
                desc += `曜日=${dow} `;
            }
        }

        // 月
        if (month !== '*') {
            desc += `${month}月 `;
        }

        // 日
        if (dom !== '*') {
            desc += `${dom}日 `;
        }

        // 時
        if (hour === '*') {
            desc += '毎時 ';
        } else {
            desc += `${hour}時 `;
        }

        // 分
        if (minute.startsWith('*/')) {
            desc += `${minute.slice(2)}分毎`;
        } else if (minute === '*') {
            desc += '毎分';
        } else {
            desc += `${minute}分`;
        }

        return desc || 'カスタムスケジュール';
    }

    /**
     * ジョブ追加処理
     */
    async handleAddJob() {
        const schedule = document.getElementById('cronSchedule').value.trim();
        const command = document.getElementById('cronCommand').value;
        const arguments_ = document.getElementById('cronArguments').value.trim();
        const comment = document.getElementById('cronComment').value.trim();

        // クライアント側バリデーション
        if (!schedule) {
            this.showModalAlert('danger', 'スケジュールを入力してください');
            return;
        }

        if (!command) {
            this.showModalAlert('danger', 'コマンドを選択してください');
            return;
        }

        // スケジュール形式チェック
        const scheduleParts = schedule.split(/\s+/);
        if (scheduleParts.length !== 5) {
            this.showModalAlert('danger', 'スケジュールは5フィールド必須です（分 時 日 月 曜日）');
            return;
        }

        // 引数の禁止文字チェック
        if (arguments_ && this.forbiddenArgChars.test(arguments_)) {
            this.showModalAlert('danger', '引数に使用できない文字が含まれています: ; | & $ ( ) { } [ ] `');
            return;
        }

        // パストラバーサルチェック
        if (arguments_ && arguments_.includes('..')) {
            this.showModalAlert('danger', '引数にパストラバーサル (..) は使用できません');
            return;
        }

        // コメントの禁止文字チェック
        if (comment && this.forbiddenArgChars.test(comment)) {
            this.showModalAlert('danger', 'コメントに使用できない文字が含まれています');
            return;
        }

        const submitBtn = document.getElementById('submitAddCronJob');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = '追加中...';
        }

        try {
            const data = {
                schedule: schedule,
                command: command,
            };
            if (arguments_) data.arguments = arguments_;
            if (comment) data.comment = comment;

            await api.request('POST', `/api/cron/${encodeURIComponent(this.selectedUsername)}`, data);

            // モーダルを閉じる
            const modalEl = document.getElementById('addCronJobModal');
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();

            this.showAlert('success', 'Cronジョブを追加しました');
            await this.loadCronJobs();

        } catch (error) {
            console.error('Failed to add cron job:', error);
            this.showModalAlert('danger', `追加に失敗しました: ${this.escapeHtml(error.message || 'Unknown error')}`);
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = '追加';
            }
        }
    }

    /**
     * 追加ボタンの状態を更新
     */
    updateAddButtonState() {
        const addBtn = document.getElementById('addCronJobBtn');
        if (!addBtn) return;

        const isAdmin = this.currentUser && this.currentUser.role === 'admin';
        const hasCapacity = this.totalCount < this.maxAllowed;

        if (!isAdmin) {
            addBtn.style.display = 'none';
            return;
        }

        addBtn.style.display = '';
        addBtn.disabled = !hasCapacity || !this.selectedUsername;

        if (!hasCapacity) {
            addBtn.title = `最大ジョブ数 (${this.maxAllowed}) に達しています`;
        } else {
            addBtn.title = 'ジョブを追加';
        }
    }

    /**
     * Auto-Refresh の切替
     */
    toggleAutoRefresh() {
        this.autoRefreshEnabled = !this.autoRefreshEnabled;
        const btn = document.getElementById('autoRefreshBtn');

        if (this.autoRefreshEnabled) {
            this.autoRefreshInterval = setInterval(() => {
                if (this.selectedUsername) {
                    this.loadCronJobs();
                }
            }, 15000);
            if (btn) {
                btn.classList.remove('btn-outline-secondary');
                btn.classList.add('btn-secondary');
                btn.title = '自動更新: ON (15秒)';
            }
        } else {
            if (this.autoRefreshInterval) {
                clearInterval(this.autoRefreshInterval);
                this.autoRefreshInterval = null;
            }
            if (btn) {
                btn.classList.remove('btn-secondary');
                btn.classList.add('btn-outline-secondary');
                btn.title = '自動更新: OFF';
            }
        }
    }

    /**
     * ジョブテーブルをクリア
     */
    clearJobTable() {
        const tableBody = document.getElementById('cronJobsTableBody');
        if (tableBody) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="7" class="text-center text-muted py-4">
                        ユーザーを選択してください
                    </td>
                </tr>
            `;
        }
        const statusText = document.getElementById('cronStatusText');
        if (statusText) statusText.textContent = '';
    }

    /**
     * コマンドの短縮名を取得
     */
    getCommandShortName(command) {
        if (!command) return '-';
        const parts = command.split('/');
        return parts[parts.length - 1] || command;
    }

    /**
     * アラート表示（ページ上部）
     */
    showAlert(type, message) {
        const container = document.getElementById('cronAlertContainer');
        if (!container) return;

        const alertHtml = `
            <div class="alert alert-${type} alert-dismissible fade show" role="alert">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        container.innerHTML = alertHtml;

        setTimeout(() => {
            const alert = container.querySelector('.alert');
            if (alert) alert.remove();
        }, 5000);
    }

    /**
     * モーダル内アラート表示
     */
    showModalAlert(type, message) {
        const container = document.getElementById('addJobModalAlert');
        if (!container) return;

        container.innerHTML = `
            <div class="alert alert-${type} alert-dismissible fade show mb-2" role="alert">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
    }

    /**
     * XSS 防止: HTML エスケープ
     */
    escapeHtml(str) {
        if (str === null || str === undefined) return '';
        const div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    }

    /**
     * 日時フォーマット
     */
    formatDateTime(dateStr) {
        if (!dateStr || dateStr === 'null') return '-';
        try {
            const d = new Date(dateStr);
            return d.toLocaleString('ja-JP');
        } catch {
            return dateStr;
        }
    }

    /**
     * クリーンアップ
     */
    destroy() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
            this.autoRefreshInterval = null;
        }
    }
}

// ページロード時に初期化
document.addEventListener('DOMContentLoaded', async function() {
    console.log('Initializing CronManager...');

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

        // CronManager 初期化
        window.cronManager = new CronManager();
        window.cronManager.currentUser = currentUser;

        // ユーザー一覧をロード
        await window.cronManager.loadUserList();

    } catch (error) {
        console.error('Failed to initialize CronManager:', error);
    }

    // アコーディオンの状態を復元
    if (typeof restoreAccordionState === 'function') {
        restoreAccordionState();
    }
});
