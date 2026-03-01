/**
 * approval.js - 承認ワークフローUI管理
 *
 * 機能:
 * - 承認待ちリクエスト一覧表示
 * - 自分の申請一覧表示
 * - 承認履歴表示
 * - 承認/拒否アクション
 * - 自己承認防止（UI無効化）
 * - XSS防止（escapeHtml）
 * - 30秒自動リフレッシュ
 * - 期限切れ警告
 */

class ApprovalManager {
    constructor() {
        this.currentUser = null;
        this.pendingRequests = [];
        this.myRequests = [];
        this.historyEntries = [];
        this.policies = [];
        this.stats = null;
        this.autoRefreshInterval = null;
        this.currentRequestId = null; // 詳細表示中のリクエストID
        this.emergencyRejectRequestId = null; // 緊急拒否対象のリクエストID

        // 履歴ページネーション
        this.historyPage = 1;
        this.historyPerPage = 20;
        this.historyTotal = 0;
        this.historyTotalPages = 1;

        // 統計タブデータ
        this.statsTabData = null;

        // モーダルインスタンス
        this.detailModal = null;
        this.approveModal = null;
        this.rejectModal = null;
        this.emergencyRejectModal = null;
        this.cancelModal = null;
        this.notificationToast = null;
    }

    /**
     * 初期化
     */
    async init() {
        console.log('ApprovalManager: Initializing...');

        // 認証チェック
        if (!api.isAuthenticated()) {
            console.error('Not authenticated, redirecting to login');
            window.location.href = window.location.pathname.replace(/[^/]*$/, '') + 'index.html';
            return;
        }

        // 現在のユーザー情報取得
        await this.loadCurrentUser();

        // モーダル初期化
        this.initModals();

        // 承認ポリシー読み込み
        await this.loadPolicies();

        // 統計読み込み（Admin のみ）
        if (this.currentUser && this.currentUser.role === 'Admin') {
            await this.loadStats();
        }

        // 初回データ読み込み
        await this.refreshPendingRequests();
        await this.refreshMyRequests();

        // イベントリスナー設定
        this.setupEventListeners();

        // 自動更新開始（30秒間隔）
        this.startAutoRefresh();

        console.log('ApprovalManager: Initialized successfully');
    }

    /**
     * 現在のユーザー情報取得
     */
    async loadCurrentUser() {
        try {
            const response = await api.request('GET', '/api/auth/me');
            if (response.status === 'success') {
                this.currentUser = response.user;
                console.log('Current user:', this.currentUser);

                // サイドバーに表示
                const usernameEl = document.getElementById('user-menu-username');
                const roleEl = document.getElementById('user-menu-role');
                const emailEl = document.getElementById('user-menu-email');

                if (usernameEl) usernameEl.textContent = this.currentUser.username;
                if (roleEl) roleEl.textContent = this.currentUser.role;
                if (emailEl) emailEl.textContent = this.currentUser.email;
            }
        } catch (error) {
            console.error('Failed to load current user:', error);
            // ネットワークエラーはトークン保持（401のみリダイレクト）
            if (error.status === 401) {
                window.location.href = window.location.pathname.replace(/[^/]*$/, '') + 'index.html';
            }
        }
    }

    /**
     * 承認ポリシー読み込み
     */
    async loadPolicies() {
        try {
            const response = await api.request('GET', '/api/approval/policies');
            if (response.status === 'success') {
                this.policies = response.policies;
                console.log('Policies loaded:', this.policies.length);

                // フィルタのドロップダウンを構築
                this.populateTypeFilters();
            }
        } catch (error) {
            console.error('Failed to load policies:', error);
        }
    }

    /**
     * 統計読み込み（Admin のみ）
     */
    async loadStats() {
        try {
            const response = await api.request('GET', '/api/approval/stats?period=30d');
            if (response.status === 'success') {
                this.stats = response.stats;
                console.log('Stats loaded:', this.stats);
                this.renderStats();
            }
        } catch (error) {
            console.error('Failed to load stats:', error);
        }
    }

    /**
     * 統計表示
     */
    renderStats() {
        if (!this.stats) return;

        const statsCard = document.getElementById('statsCard');
        if (statsCard) {
            statsCard.style.display = 'block';
            document.getElementById('stat-pending').textContent = this.stats.pending || 0;
            document.getElementById('stat-approved').textContent = this.stats.approved || 0;
            document.getElementById('stat-rejected').textContent = this.stats.rejected || 0;
            document.getElementById('stat-approval-rate').textContent =
                (this.stats.approval_rate || 0).toFixed(1) + '%';
        }
    }

    /**
     * 操作種別フィルタのドロップダウンを構築
     */
    populateTypeFilters() {
        const pendingFilter = document.getElementById('pending-filter-type');
        const myFilter = document.getElementById('my-filter-type');
        const historyFilter = document.getElementById('history-filter-type');

        this.policies.forEach(policy => {
            const option = `<option value="${this.escapeHtml(policy.operation_type)}">${this.escapeHtml(policy.description)}</option>`;
            if (pendingFilter) pendingFilter.insertAdjacentHTML('beforeend', option);
            if (myFilter) myFilter.insertAdjacentHTML('beforeend', option);
            if (historyFilter) historyFilter.insertAdjacentHTML('beforeend', option);
        });
    }

    /**
     * モーダル初期化
     */
    initModals() {
        const detailModalEl = document.getElementById('detailModal');
        const approveModalEl = document.getElementById('approveModal');
        const rejectModalEl = document.getElementById('rejectModal');
        const emergencyRejectModalEl = document.getElementById('emergencyRejectModal');
        const cancelModalEl = document.getElementById('cancelModal');
        const toastEl = document.getElementById('notificationToast');

        if (detailModalEl) this.detailModal = new bootstrap.Modal(detailModalEl);
        if (approveModalEl) this.approveModal = new bootstrap.Modal(approveModalEl);
        if (rejectModalEl) this.rejectModal = new bootstrap.Modal(rejectModalEl);
        if (emergencyRejectModalEl) this.emergencyRejectModal = new bootstrap.Modal(emergencyRejectModalEl);
        if (cancelModalEl) this.cancelModal = new bootstrap.Modal(cancelModalEl);
        if (toastEl) this.notificationToast = new bootstrap.Toast(toastEl, { delay: 3000 });
    }

    /**
     * イベントリスナー設定
     */
    setupEventListeners() {
        // 承認ボタン
        const confirmApproveBtn = document.getElementById('confirm-approve-btn');
        if (confirmApproveBtn) {
            confirmApproveBtn.addEventListener('click', () => this.handleApprove());
        }

        // 拒否ボタン
        const confirmRejectBtn = document.getElementById('confirm-reject-btn');
        if (confirmRejectBtn) {
            confirmRejectBtn.addEventListener('click', () => this.handleReject());
        }

        // 緊急拒否ボタン
        const confirmEmergencyRejectBtn = document.getElementById('confirm-emergency-reject-btn');
        if (confirmEmergencyRejectBtn) {
            confirmEmergencyRejectBtn.addEventListener('click', () => this.handleEmergencyReject());
        }

        // キャンセル確認ボタン
        const confirmCancelBtn = document.getElementById('confirm-cancel-btn');
        if (confirmCancelBtn) {
            confirmCancelBtn.addEventListener('click', () => this.handleCancelConfirmed());
        }

        // 承認理由テキストエリア - 入力時にボタン有効/無効切り替え + 文字数カウント
        const approveReason = document.getElementById('approve-reason');
        if (approveReason) {
            approveReason.addEventListener('input', () => {
                const btn = document.getElementById('confirm-approve-btn');
                const count = document.getElementById('approve-reason-count');
                if (btn) btn.disabled = !approveReason.value.trim();
                if (count) count.textContent = approveReason.value.length;
            });
        }

        // 拒否理由テキストエリア - 入力時にボタン有効/無効切り替え + 文字数カウント
        const rejectReason = document.getElementById('reject-reason');
        if (rejectReason) {
            rejectReason.addEventListener('input', () => {
                const btn = document.getElementById('confirm-reject-btn');
                const count = document.getElementById('reject-reason-count');
                if (btn) btn.disabled = !rejectReason.value.trim();
                if (count) count.textContent = rejectReason.value.length;
            });
        }

        // 緊急拒否理由テキストエリア - 入力時にボタン有効/無効切り替え + 文字数カウント
        const emergencyRejectReason = document.getElementById('emergency-reject-reason');
        if (emergencyRejectReason) {
            emergencyRejectReason.addEventListener('input', () => {
                const btn = document.getElementById('confirm-emergency-reject-btn');
                const count = document.getElementById('emergency-reject-reason-count');
                if (btn) btn.disabled = !emergencyRejectReason.value.trim();
                if (count) count.textContent = emergencyRejectReason.value.length;
            });
        }

        // フィルタ変更時の再読み込み
        const filters = [
            'pending-filter-type', 'pending-filter-requester', 'pending-sort',
            'my-filter-status', 'my-filter-type'
        ];
        filters.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.addEventListener('change', () => {
                    if (id.startsWith('pending-')) {
                        this.refreshPendingRequests();
                    } else if (id.startsWith('my-')) {
                        this.refreshMyRequests();
                    }
                });
            }
        });

        // タブ切り替え時の更新
        document.getElementById('history-tab')?.addEventListener('shown.bs.tab', () => {
            this.refreshHistory(1);
        });
        document.getElementById('stats-tab')?.addEventListener('shown.bs.tab', () => {
            this.loadStatsTab();
        });
    }

    /**
     * 自動更新開始
     */
    startAutoRefresh() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
        }

        this.autoRefreshInterval = setInterval(async () => {
            console.log('Auto refresh...');

            // アクティブなタブに応じて更新
            const activeTab = document.querySelector('.approval-tabs .nav-link.active');
            if (activeTab) {
                const tabId = activeTab.id;
                if (tabId === 'pending-tab') {
                    await this.refreshPendingRequests();
                } else if (tabId === 'my-requests-tab') {
                    await this.refreshMyRequests();
                } else if (tabId === 'history-tab') {
                    await this.refreshHistory();
                } else if (tabId === 'stats-tab') {
                    await this.loadStatsTab();
                }
            }

            // 統計も更新（Admin のみ）
            if (this.currentUser && this.currentUser.role === 'Admin') {
                await this.loadStats();
            }
        }, 30000); // 30秒
    }

    /**
     * 承認待ちリクエスト更新
     */
    async refreshPendingRequests() {
        try {
            // フィルタパラメータ取得
            const params = new URLSearchParams();
            const typeFilter = document.getElementById('pending-filter-type')?.value;
            const requesterFilter = document.getElementById('pending-filter-requester')?.value;
            const sortBy = document.getElementById('pending-sort')?.value || 'expires_at';

            if (typeFilter) params.append('request_type', typeFilter);
            if (requesterFilter) params.append('requester_id', requesterFilter);
            params.append('sort_by', sortBy);
            params.append('sort_order', 'asc');

            const response = await api.request('GET', `/api/approval/pending?${params.toString()}`);
            if (response.status === 'success') {
                this.pendingRequests = response.requests || [];
                console.log('Pending requests loaded:', this.pendingRequests.length);

                // バッジ更新
                document.getElementById('pending-count').textContent = this.pendingRequests.length;

                // リスト描画
                this.renderPendingRequests();

                // 申請者フィルタのドロップダウン更新
                this.updateRequesterFilter();
            }
        } catch (error) {
            console.error('Failed to load pending requests:', error);
            this.showError('pending-list', '承認待ちリクエストの読み込みに失敗しました');
        }
    }

    /**
     * 自分の申請更新
     */
    async refreshMyRequests() {
        try {
            // フィルタパラメータ取得
            const params = new URLSearchParams();
            const statusFilter = document.getElementById('my-filter-status')?.value;
            const typeFilter = document.getElementById('my-filter-type')?.value;

            if (statusFilter) params.append('status', statusFilter);
            if (typeFilter) params.append('request_type', typeFilter);

            const response = await api.request('GET', `/api/approval/my-requests?${params.toString()}`);
            if (response.status === 'success') {
                this.myRequests = response.requests || [];
                console.log('My requests loaded:', this.myRequests.length);

                // バッジ更新
                document.getElementById('my-requests-count').textContent = this.myRequests.length;

                // リスト描画
                this.renderMyRequests();
            }
        } catch (error) {
            console.error('Failed to load my requests:', error);
            this.showError('my-requests-list', '自分の申請の読み込みに失敗しました');
        }
    }

    /**
     * 承認履歴更新
     */
    async refreshHistory(page) {
        if (typeof page === 'number') {
            this.historyPage = page;
        }
        try {
            // フィルタパラメータ取得
            const params = new URLSearchParams();
            const startDate = document.getElementById('history-start-date')?.value;
            const endDate = document.getElementById('history-end-date')?.value;
            const typeFilter = document.getElementById('history-filter-type')?.value;
            const actionFilter = document.getElementById('history-filter-action')?.value;

            if (startDate) params.append('start_date', startDate + 'T00:00:00Z');
            if (endDate) params.append('end_date', endDate + 'T23:59:59Z');
            if (typeFilter) params.append('request_type', typeFilter);
            if (actionFilter) params.append('action', actionFilter);
            params.append('page', String(this.historyPage));
            params.append('per_page', String(this.historyPerPage));

            const response = await api.request('GET', `/api/approval/history?${params.toString()}`);
            if (response.status === 'success') {
                this.historyEntries = response.items || response.history || [];
                this.historyTotal = response.total || this.historyEntries.length;
                this.historyTotalPages = response.total_pages || Math.ceil(this.historyTotal / this.historyPerPage) || 1;
                console.log('History entries loaded:', this.historyEntries.length, 'total:', this.historyTotal);

                // リスト描画
                this.renderHistory();
                this.renderHistoryPagination();
            }
        } catch (error) {
            console.error('Failed to load history:', error);
            this.showError('history-list', '承認履歴の読み込みに失敗しました');
        }
    }

    /**
     * 履歴のフィルタクエリ文字列を構築（エクスポート共用）
     */
    buildHistoryFilterParams() {
        const params = new URLSearchParams();
        const startDate = document.getElementById('history-start-date')?.value;
        const endDate = document.getElementById('history-end-date')?.value;
        const typeFilter = document.getElementById('history-filter-type')?.value;

        if (startDate) params.append('start_date', startDate + 'T00:00:00Z');
        if (endDate) params.append('end_date', endDate + 'T23:59:59Z');
        if (typeFilter) params.append('request_type', typeFilter);
        return params;
    }

    /**
     * 認証付きファイルダウンロード（fetch + Blob）
     */
    async downloadWithAuth(url) {
        try {
            const token = localStorage.getItem('access_token');
            const baseURL = window.location.origin;
            const fullUrl = baseURL + url;

            const response = await fetch(fullUrl, {
                method: 'GET',
                headers: {
                    'Authorization': 'Bearer ' + (token || ''),
                },
            });

            if (!response.ok) {
                throw new Error('ダウンロードに失敗しました (HTTP ' + response.status + ')');
            }

            const blob = await response.blob();
            const disposition = response.headers.get('Content-Disposition') || '';
            const filenameMatch = disposition.match(/filename=([^;]+)/);
            const filename = filenameMatch ? filenameMatch[1].trim() : 'export';

            const objectUrl = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = objectUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(objectUrl);

            this.showNotification('ダウンロードを開始しました', 'success');
        } catch (error) {
            console.error('Download failed:', error);
            this.showNotification('ダウンロードに失敗しました: ' + this.escapeHtml(String(error.message || error)), 'danger');
        }
    }

    /**
     * エクスポートボタンクリック
     */
    downloadExport(format) {
        const params = this.buildHistoryFilterParams();
        params.append('format', format);
        this.downloadWithAuth('/api/approval/history/export?' + params.toString());
    }

    /**
     * 申請者フィルタ更新
     */
    updateRequesterFilter() {
        const filter = document.getElementById('pending-filter-requester');
        if (!filter) return;

        // 既存の選択肢をクリア
        filter.innerHTML = '<option value="">全申請者</option>';

        // ユニークな申請者を抽出
        const requesters = new Set();
        this.pendingRequests.forEach(req => {
            requesters.add(req.requester_id + '::' + req.requester_name);
        });

        // ドロップダウンに追加
        requesters.forEach(requester => {
            const [id, name] = requester.split('::');
            const option = document.createElement('option');
            option.value = this.escapeHtml(id);
            option.textContent = this.escapeHtml(name);
            filter.appendChild(option);
        });
    }

    /**
     * 承認待ちリスト描画
     */
    renderPendingRequests() {
        const container = document.getElementById('pending-list');
        if (!container) return;

        if (this.pendingRequests.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📭</div>
                    <div class="empty-state-text">承認待ちのリクエストはありません</div>
                    <div class="empty-state-subtext">新しいリクエストが作成されるとここに表示されます</div>
                </div>
            `;
            return;
        }

        let html = '';
        this.pendingRequests.forEach(request => {
            const isSelfRequest = this.currentUser && request.requester_id === this.currentUser.user_id;
            const remainingHours = request.remaining_hours || 0;
            const expiringClass = remainingHours < 6 ? 'expiring-soon' : (remainingHours < 12 ? 'expiring-warning' : '');

            html += `
                <div class="request-card ${expiringClass}" onclick="approvalManager.showRequestDetail('${this.escapeHtml(request.id)}')">
                    <div class="request-card-header">
                        <div>
                            <div class="request-type">
                                ${this.escapeHtml(request.request_type_description)}
                                <span class="risk-badge risk-${this.escapeHtml(request.risk_level)}">${this.escapeHtml(request.risk_level)}</span>
                            </div>
                            <div class="request-id">ID: ${this.escapeHtml(request.id)}</div>
                        </div>
                        <div>
                            <span class="status-badge status-${this.escapeHtml(request.status || 'pending')}">
                                ${this.escapeHtml(request.status || 'pending')}
                            </span>
                        </div>
                    </div>
                    <div class="request-meta">
                        <div class="meta-item">
                            <div class="meta-label">申請者</div>
                            <div class="meta-value">${this.escapeHtml(request.requester_name)}</div>
                        </div>
                        <div class="meta-item">
                            <div class="meta-label">申請日時</div>
                            <div class="meta-value">${this.formatDateTime(request.created_at)}</div>
                        </div>
                        <div class="meta-item">
                            <div class="meta-label">承認期限</div>
                            <div class="meta-value" style="color: ${remainingHours < 6 ? '#dc3545' : (remainingHours < 12 ? '#ffc107' : '#28a745')}">
                                ${this.formatDateTime(request.expires_at)}
                                <br><small>(残り ${remainingHours.toFixed(1)}時間)</small>
                            </div>
                        </div>
                        <div class="meta-item">
                            <div class="meta-label">パラメータ</div>
                            <div class="meta-value" style="font-size: 12px; font-family: monospace;">
                                ${this.escapeHtml(request.payload_summary || '-')}
                            </div>
                        </div>
                    </div>
                    <div class="request-reason">
                        ${this.escapeHtml(request.reason)}
                    </div>
                    ${isSelfRequest ? '<div class="self-approval-warning" style="margin-top: 10px;"><span class="self-approval-warning-icon">⚠️</span><span class="self-approval-warning-text">自分の申請です（自己承認は禁止）</span></div>' : ''}
                    ${!isSelfRequest && this.currentUser && (this.currentUser.role === 'Approver' || this.currentUser.role === 'Admin') ? `
                    <div style="margin-top: 10px; text-align: right;">
                        <button class="btn btn-danger btn-sm" onclick="event.stopPropagation(); approvalManager.openEmergencyRejectModal('${this.escapeHtml(request.id)}', '${this.escapeHtml(request.request_type_description)}', '${this.escapeHtml(request.requester_name)}')">
                            緊急拒否
                        </button>
                    </div>
                    ` : ''}
                </div>
            `;
        });

        container.innerHTML = html;
    }

    /**
     * 自分の申請リスト描画
     */
    renderMyRequests() {
        const container = document.getElementById('my-requests-list');
        if (!container) return;

        if (this.myRequests.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📝</div>
                    <div class="empty-state-text">申請はありません</div>
                    <div class="empty-state-subtext">承認が必要な操作を実行すると、ここに申請が表示されます</div>
                </div>
            `;
            return;
        }

        let html = '';
        this.myRequests.forEach(request => {
            html += `
                <div class="request-card" onclick="approvalManager.showRequestDetail('${this.escapeHtml(request.id)}')">
                    <div class="request-card-header">
                        <div>
                            <div class="request-type">
                                ${this.escapeHtml(request.request_type_description)}
                                <span class="risk-badge risk-${this.escapeHtml(request.risk_level)}">${this.escapeHtml(request.risk_level)}</span>
                            </div>
                            <div class="request-id">ID: ${this.escapeHtml(request.id)}</div>
                        </div>
                        <div>
                            <span class="status-badge status-${this.escapeHtml(request.status)}">
                                ${this.escapeHtml(request.status)}
                            </span>
                        </div>
                    </div>
                    <div class="request-meta">
                        <div class="meta-item">
                            <div class="meta-label">申請日時</div>
                            <div class="meta-value">${this.formatDateTime(request.created_at)}</div>
                        </div>
                        <div class="meta-item">
                            <div class="meta-label">承認期限</div>
                            <div class="meta-value">${this.formatDateTime(request.expires_at)}</div>
                        </div>
                        ${request.approved_by_name ? `
                        <div class="meta-item">
                            <div class="meta-label">承認者</div>
                            <div class="meta-value">${this.escapeHtml(request.approved_by_name)}</div>
                        </div>
                        <div class="meta-item">
                            <div class="meta-label">承認日時</div>
                            <div class="meta-value">${this.formatDateTime(request.approved_at)}</div>
                        </div>
                        ` : ''}
                    </div>
                    <div class="request-reason">
                        ${this.escapeHtml(request.reason)}
                    </div>
                    ${request.rejection_reason ? `<div class="request-reason" style="border-left-color: #dc3545; background-color: #f8d7da;"><strong>拒否理由:</strong> ${this.escapeHtml(request.rejection_reason)}</div>` : ''}
                </div>
            `;
        });

        container.innerHTML = html;
    }

    /**
     * 承認履歴描画
     */
    renderHistory() {
        const container = document.getElementById('history-list');
        if (!container) return;

        if (this.historyEntries.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📜</div>
                    <div class="empty-state-text">履歴はありません</div>
                    <div class="empty-state-subtext">フィルタ条件を変更して再度検索してください</div>
                </div>
            `;
            return;
        }

        let html = '<table class="table table-sm table-hover table-bordered">';
        html += '<thead class="table-light"><tr>';
        html += '<th>リクエストID</th><th>種別</th><th>アクション</th><th>実行者</th><th>日時</th><th>署名</th>';
        html += '</tr></thead><tbody>';

        this.historyEntries.forEach(entry => {
            const shortId = entry.approval_request_id ? this.escapeHtml(entry.approval_request_id.substring(0, 8)) : '-';
            const sigIcon = entry.signature_valid === false
                ? '<span style="color: #dc3545; font-weight: bold;">無効</span>'
                : '<span style="color: #28a745;">有効</span>';
            html += '<tr style="cursor: pointer;" onclick="approvalManager.showRequestDetail(\'' + this.escapeHtml(entry.approval_request_id || '') + '\')">';
            html += '<td><code>' + shortId + '</code></td>';
            html += '<td>' + this.escapeHtml(entry.request_type || '-') + '</td>';
            html += '<td><span class="status-badge status-' + this.escapeHtml(entry.action || '') + '">' + this.escapeHtml(entry.action || '-') + '</span></td>';
            html += '<td>' + this.escapeHtml(entry.actor_name || '-') + '</td>';
            html += '<td>' + this.formatDateTime(entry.timestamp) + '</td>';
            html += '<td>' + sigIcon + '</td>';
            html += '</tr>';
        });

        html += '</tbody></table>';
        container.innerHTML = html;
    }

    /**
     * 履歴ページネーション描画
     */
    renderHistoryPagination() {
        const nav = document.getElementById('history-pagination');
        const info = document.getElementById('history-page-info');
        const buttons = document.getElementById('history-page-buttons');
        if (!nav || !info || !buttons) return;

        if (this.historyTotal <= this.historyPerPage) {
            nav.style.display = 'none';
            return;
        }
        nav.style.display = 'block';

        const start = (this.historyPage - 1) * this.historyPerPage + 1;
        const end = Math.min(this.historyPage * this.historyPerPage, this.historyTotal);
        info.textContent = start + ' - ' + end + ' / ' + this.historyTotal + ' 件';

        let btnHtml = '';
        // 前へ
        btnHtml += '<li class="page-item' + (this.historyPage <= 1 ? ' disabled' : '') + '">';
        btnHtml += '<a class="page-link" href="#" onclick="event.preventDefault(); approvalManager.refreshHistory(' + (this.historyPage - 1) + ')">前</a></li>';

        // ページ番号（最大5つ表示）
        const maxVisible = 5;
        let pageStart = Math.max(1, this.historyPage - Math.floor(maxVisible / 2));
        let pageEnd = Math.min(this.historyTotalPages, pageStart + maxVisible - 1);
        if (pageEnd - pageStart < maxVisible - 1) {
            pageStart = Math.max(1, pageEnd - maxVisible + 1);
        }

        for (let p = pageStart; p <= pageEnd; p++) {
            btnHtml += '<li class="page-item' + (p === this.historyPage ? ' active' : '') + '">';
            btnHtml += '<a class="page-link" href="#" onclick="event.preventDefault(); approvalManager.refreshHistory(' + p + ')">' + p + '</a></li>';
        }

        // 次へ
        btnHtml += '<li class="page-item' + (this.historyPage >= this.historyTotalPages ? ' disabled' : '') + '">';
        btnHtml += '<a class="page-link" href="#" onclick="event.preventDefault(); approvalManager.refreshHistory(' + (this.historyPage + 1) + ')">次</a></li>';

        buttons.innerHTML = btnHtml;
    }

    /**
     * リクエスト詳細表示
     */
    async showRequestDetail(requestId) {
        this.currentRequestId = requestId;

        // モーダル表示
        if (this.detailModal) {
            this.detailModal.show();
        }

        // ボディをローディング状態に
        const body = document.getElementById('detailModalBody');
        if (body) {
            body.innerHTML = `
                <div class="loading-spinner">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">読み込み中...</span>
                    </div>
                </div>
            `;
        }

        try {
            const response = await api.request('GET', `/api/approval/${requestId}`);
            if (response.status === 'success') {
                const request = response.request;
                this.renderRequestDetail(request);
            }
        } catch (error) {
            console.error('Failed to load request detail:', error);
            if (body) {
                body.innerHTML = `<div class="alert alert-danger">リクエスト詳細の読み込みに失敗しました</div>`;
            }
        }
    }

    /**
     * リクエスト詳細描画
     */
    renderRequestDetail(request) {
        const body = document.getElementById('detailModalBody');
        const footer = document.getElementById('detailModalFooter');
        if (!body || !footer) return;

        const isSelfRequest = this.currentUser && request.requester_id === this.currentUser.user_id;
        const canApprove = !isSelfRequest && request.status === 'pending' &&
                          this.currentUser && (this.currentUser.role === 'Approver' || this.currentUser.role === 'Admin');
        const canCancel = isSelfRequest && request.status === 'pending';

        let html = '';

        // 自己承認警告
        if (isSelfRequest && request.status === 'pending') {
            html += `
                <div class="self-approval-warning">
                    <span class="self-approval-warning-icon">⚠️</span>
                    <span class="self-approval-warning-text">これは自分の申請です。自己承認は禁止されています。</span>
                </div>
            `;
        }

        // 基本情報
        html += `
            <div class="detail-section">
                <div class="detail-section-title">基本情報</div>
                <div style="display: grid; grid-template-columns: 150px 1fr; gap: 10px; font-size: 14px;">
                    <div style="font-weight: bold;">リクエストID:</div>
                    <div style="font-family: monospace;">${this.escapeHtml(request.id)}</div>

                    <div style="font-weight: bold;">操作種別:</div>
                    <div>
                        ${this.escapeHtml(request.request_type_description)}
                        <span class="risk-badge risk-${this.escapeHtml(request.risk_level)}">${this.escapeHtml(request.risk_level)}</span>
                    </div>

                    <div style="font-weight: bold;">ステータス:</div>
                    <div><span class="status-badge status-${this.escapeHtml(request.status)}">${this.escapeHtml(request.status)}</span></div>

                    <div style="font-weight: bold;">申請者:</div>
                    <div>${this.escapeHtml(request.requester_name)} (${this.escapeHtml(request.requester_id)})</div>

                    <div style="font-weight: bold;">申請日時:</div>
                    <div>${this.formatDateTime(request.created_at)}</div>

                    <div style="font-weight: bold;">承認期限:</div>
                    <div>${this.formatDateTime(request.expires_at)}</div>
                </div>
            </div>
        `;

        // 操作内容
        html += `
            <div class="detail-section">
                <div class="detail-section-title">操作内容</div>
                <div class="payload-display">${this.escapeHtml(JSON.stringify(request.request_payload, null, 2))}</div>
            </div>
        `;

        // 申請理由
        html += `
            <div class="detail-section">
                <div class="detail-section-title">申請理由</div>
                <div class="request-reason">${this.escapeHtml(request.reason)}</div>
            </div>
        `;

        // 承認情報（承認済みの場合）
        if (request.approved_by) {
            html += `
                <div class="detail-section">
                    <div class="detail-section-title">承認情報</div>
                    <div style="display: grid; grid-template-columns: 150px 1fr; gap: 10px; font-size: 14px;">
                        <div style="font-weight: bold;">承認者:</div>
                        <div>${this.escapeHtml(request.approved_by_name)} (${this.escapeHtml(request.approved_by)})</div>

                        <div style="font-weight: bold;">承認日時:</div>
                        <div>${this.formatDateTime(request.approved_at)}</div>

                        ${request.approval_reason ? `
                        <div style="font-weight: bold;">承認理由:</div>
                        <div>${this.escapeHtml(request.approval_reason)}</div>
                        ` : ''}

                        ${request.approval_comment ? `
                        <div style="font-weight: bold;">承認コメント:</div>
                        <div>${this.escapeHtml(request.approval_comment)}</div>
                        ` : ''}
                    </div>
                </div>
            `;
        }

        // 拒否理由（拒否された場合）
        if (request.rejection_reason) {
            html += `
                <div class="detail-section">
                    <div class="detail-section-title">拒否理由</div>
                    <div class="request-reason" style="border-left-color: #dc3545; background-color: #f8d7da;">
                        ${this.escapeHtml(request.rejection_reason)}
                    </div>
                </div>
            `;
        }

        // 実行結果（実行済みの場合）
        if (request.execution_result) {
            html += `
                <div class="detail-section">
                    <div class="detail-section-title">実行結果</div>
                    <div class="payload-display">${this.escapeHtml(JSON.stringify(request.execution_result, null, 2))}</div>
                </div>
            `;
        }

        // 履歴
        if (request.history && request.history.length > 0) {
            html += `
                <div class="detail-section">
                    <div class="detail-section-title">履歴</div>
                    <div class="timeline">
            `;

            request.history.forEach(entry => {
                html += `
                    <div class="timeline-item">
                        <div class="timeline-time">${this.formatDateTime(entry.timestamp)}</div>
                        <div class="timeline-content">
                            <div class="timeline-actor">${this.escapeHtml(entry.actor_name)} (${this.escapeHtml(entry.actor_role)})</div>
                            <div><strong>${this.escapeHtml(entry.action)}</strong></div>
                        </div>
                    </div>
                `;
            });

            html += `
                    </div>
                </div>
            `;
        }

        body.innerHTML = html;

        // フッターボタン
        let footerHtml = '<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">閉じる</button>';

        if (canApprove) {
            footerHtml += `
                <button type="button" class="btn btn-reject" onclick="approvalManager.openRejectModal()">拒否</button>
                <button type="button" class="btn btn-approve" onclick="approvalManager.openApproveModal()">承認</button>
            `;
        }

        if (canCancel) {
            footerHtml += `
                <button type="button" class="btn btn-warning" onclick="approvalManager.handleCancel()">キャンセル</button>
            `;
        }

        footer.innerHTML = footerHtml;
    }

    /**
     * 承認モーダル表示（操作サマリー付き）
     */
    openApproveModal() {
        if (this.approveModal) {
            // 理由クリア
            const reasonEl = document.getElementById('approve-reason');
            if (reasonEl) reasonEl.value = '';
            const countEl = document.getElementById('approve-reason-count');
            if (countEl) countEl.textContent = '0';
            const btn = document.getElementById('confirm-approve-btn');
            if (btn) btn.disabled = true;

            // 操作内容サマリーを表示
            const summaryEl = document.getElementById('approve-request-summary');
            if (summaryEl) {
                const request = this.findRequestById(this.currentRequestId);
                if (request) {
                    summaryEl.innerHTML = `
                        <div style="font-size: 13px;">
                            <div><strong>操作種別:</strong> ${this.escapeHtml(request.request_type_description || request.request_type)}</div>
                            <div><strong>申請者:</strong> ${this.escapeHtml(request.requester_name)}</div>
                            <div><strong>リスクレベル:</strong> <span class="risk-badge risk-${this.escapeHtml(request.risk_level)}">${this.escapeHtml(request.risk_level)}</span></div>
                            <div><strong>申請理由:</strong> ${this.escapeHtml(request.reason)}</div>
                        </div>
                    `;
                } else {
                    summaryEl.innerHTML = '<div style="font-size: 13px; color: #6c757d;">リクエスト情報を取得中...</div>';
                }
            }

            this.approveModal.show();
        }
    }

    /**
     * 拒否モーダル表示
     */
    openRejectModal() {
        if (this.rejectModal) {
            // 理由クリア
            const reasonEl = document.getElementById('reject-reason');
            if (reasonEl) reasonEl.value = '';
            const countEl = document.getElementById('reject-reason-count');
            if (countEl) countEl.textContent = '0';
            const btn = document.getElementById('confirm-reject-btn');
            if (btn) btn.disabled = true;
            this.rejectModal.show();
        }
    }

    /**
     * 緊急拒否モーダル表示
     */
    openEmergencyRejectModal(requestId, typeDescription, requesterName) {
        this.emergencyRejectRequestId = requestId;

        if (this.emergencyRejectModal) {
            // 理由クリア
            const reasonEl = document.getElementById('emergency-reject-reason');
            if (reasonEl) reasonEl.value = '';
            const countEl = document.getElementById('emergency-reject-reason-count');
            if (countEl) countEl.textContent = '0';
            const btn = document.getElementById('confirm-emergency-reject-btn');
            if (btn) btn.disabled = true;

            // サマリー表示
            const summaryEl = document.getElementById('emergency-reject-summary');
            if (summaryEl) {
                summaryEl.innerHTML = `
                    <div style="font-size: 13px;">
                        <div><strong>操作種別:</strong> ${this.escapeHtml(typeDescription)}</div>
                        <div><strong>申請者:</strong> ${this.escapeHtml(requesterName)}</div>
                        <div><strong>リクエストID:</strong> <span style="font-family: monospace;">${this.escapeHtml(requestId)}</span></div>
                    </div>
                `;
            }

            this.emergencyRejectModal.show();
        }
    }

    /**
     * リクエストIDでpendingRequests/myRequestsから検索
     */
    findRequestById(requestId) {
        return this.pendingRequests.find(r => r.id === requestId) ||
               this.myRequests.find(r => r.id === requestId) ||
               null;
    }

    /**
     * 承認実行（理由必須）
     */
    async handleApprove() {
        if (!this.currentRequestId) return;

        const reason = document.getElementById('approve-reason')?.value || '';

        if (!reason.trim()) {
            this.showNotification('承認理由を入力してください', 'warning');
            return;
        }

        try {
            const response = await api.request('POST', `/api/approval/${this.currentRequestId}/approve`, {
                comment: reason,
                reason: reason
            });

            if (response.status === 'success') {
                this.showBanner('✅ 承認しました', 'success');

                // モーダルを閉じる
                if (this.approveModal) this.approveModal.hide();
                if (this.detailModal) this.detailModal.hide();

                // リスト更新
                await this.refreshPendingRequests();
                await this.refreshMyRequests();
            }
        } catch (error) {
            console.error('Failed to approve request:', error);
            this.showNotification('承認に失敗しました: ' + this.escapeHtml(error.message || '不明なエラー'), 'danger');
        }
    }

    /**
     * 拒否実行
     */
    async handleReject() {
        if (!this.currentRequestId) return;

        const reason = document.getElementById('reject-reason')?.value || '';

        if (!reason.trim()) {
            this.showNotification('拒否理由を入力してください', 'warning');
            return;
        }

        try {
            const response = await api.request('POST', `/api/approval/${this.currentRequestId}/reject`, {
                reason: reason
            });

            if (response.status === 'success') {
                this.showBanner('❌ 却下しました', 'danger');

                // モーダルを閉じる
                if (this.rejectModal) this.rejectModal.hide();
                if (this.detailModal) this.detailModal.hide();

                // リスト更新
                await this.refreshPendingRequests();
                await this.refreshMyRequests();
            }
        } catch (error) {
            console.error('Failed to reject request:', error);
            this.showNotification('拒否に失敗しました: ' + this.escapeHtml(error.message || '不明なエラー'), 'danger');
        }
    }

    /**
     * 緊急拒否実行
     */
    async handleEmergencyReject() {
        if (!this.emergencyRejectRequestId) return;

        const reason = document.getElementById('emergency-reject-reason')?.value || '';

        if (!reason.trim()) {
            this.showNotification('緊急拒否理由を入力してください', 'warning');
            return;
        }

        try {
            const response = await api.request('POST', `/api/approval/${this.emergencyRejectRequestId}/reject`, {
                reason: reason,
                emergency: true
            });

            if (response.status === 'success') {
                this.showNotification('緊急拒否しました', 'success');

                // モーダルを閉じる
                if (this.emergencyRejectModal) this.emergencyRejectModal.hide();

                // リスト更新
                await this.refreshPendingRequests();
                await this.refreshMyRequests();
            }
        } catch (error) {
            console.error('Failed to emergency reject request:', error);
            this.showNotification('緊急拒否に失敗しました: ' + this.escapeHtml(error.message || '不明なエラー'), 'danger');
        }
    }

    /**
     * キャンセルモーダル表示（confirm() の代替）
     */
    handleCancel() {
        if (!this.currentRequestId) return;

        if (this.cancelModal) {
            this.cancelModal.show();
        }
    }

    /**
     * キャンセル確認後の実行
     */
    async handleCancelConfirmed() {
        if (!this.currentRequestId) return;

        try {
            const response = await api.request('POST', `/api/approval/${this.currentRequestId}/cancel`, {
                reason: 'ユーザーによるキャンセル'
            });

            if (response.status === 'success') {
                this.showNotification('キャンセルしました', 'success');

                // モーダルを閉じる
                if (this.cancelModal) this.cancelModal.hide();
                if (this.detailModal) this.detailModal.hide();

                // リスト更新
                await this.refreshPendingRequests();
                await this.refreshMyRequests();
            }
        } catch (error) {
            console.error('Failed to cancel request:', error);
            this.showNotification('キャンセルに失敗しました: ' + this.escapeHtml(error.message || '不明なエラー'), 'danger');
        }
    }

    /**
     * 通知トースト表示（alert() の代替）
     * @param {string} message - 表示メッセージ
     * @param {string} type - 'success', 'danger', 'warning', 'info'
     */
    showNotification(message, type) {
        const toastHeader = document.getElementById('toastHeader');
        const toastTitle = document.getElementById('toastTitle');
        const toastBody = document.getElementById('toastBody');

        if (!toastHeader || !toastTitle || !toastBody) {
            console.log(`Notification (${type}): ${message}`);
            return;
        }

        const titles = { success: '成功', danger: 'エラー', warning: '警告', info: '情報' };
        const bgColors = { success: '#d4edda', danger: '#f8d7da', warning: '#fff3cd', info: '#d1ecf1' };

        toastTitle.textContent = titles[type] || '通知';
        toastHeader.style.backgroundColor = bgColors[type] || '#f8f9fa';
        toastBody.textContent = message;

        if (this.notificationToast) {
            this.notificationToast.show();
        }
    }

    /**
     * ページ上部に承認/却下通知バナーを5秒表示
     */
    showBanner(message, type) {
        const banner = document.getElementById('action-banner');
        if (!banner) {
            this.showNotification(message, type);
            return;
        }
        const bgColors = { success: '#d4edda', danger: '#f8d7da', warning: '#fff3cd', info: '#d1ecf1' };
        const textColors = { success: '#155724', danger: '#721c24', warning: '#856404', info: '#0c5460' };
        banner.textContent = message;
        banner.style.backgroundColor = bgColors[type] || '#f8f9fa';
        banner.style.color = textColors[type] || '#333';
        banner.style.border = `1px solid ${textColors[type] || '#ccc'}`;
        banner.style.display = 'block';
        clearTimeout(this._bannerTimer);
        this._bannerTimer = setTimeout(() => { banner.style.display = 'none'; }, 5000);
    }

    /**
     * エラー表示
     */
    showError(containerId, message) {
        const container = document.getElementById(containerId);
        if (container) {
            container.innerHTML = `
                <div class="alert alert-danger" role="alert">
                    <strong>エラー:</strong> ${this.escapeHtml(message)}
                </div>
            `;
        }
    }

    /**
     * 日時フォーマット
     */
    formatDateTime(dateString) {
        if (!dateString) return '-';
        const date = new Date(dateString);
        return date.toLocaleString('ja-JP', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    /**
     * XSS防止（HTMLエスケープ）
     */
    escapeHtml(text) {
        if (typeof text !== 'string') return text;
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, m => map[m]);
    }

    /**
     * 統計タブ読み込み
     */
    async loadStatsTab() {
        const loading = document.getElementById('stats-loading');
        const empty = document.getElementById('stats-empty');
        const cards = document.getElementById('stats-cards');
        const statusTable = document.getElementById('stats-status-table');
        const typeTable = document.getElementById('stats-type-table');

        // ローディング表示
        if (loading) loading.style.display = 'block';
        if (empty) empty.style.display = 'none';
        if (cards) cards.style.display = 'none';
        if (statusTable) statusTable.style.display = 'none';
        if (typeTable) typeTable.style.display = 'none';

        try {
            const period = document.getElementById('stats-period')?.value || '30d';
            const response = await api.request('GET', '/api/approval/stats?period=' + encodeURIComponent(period));

            if (loading) loading.style.display = 'none';

            if (response.status === 'success') {
                this.statsTabData = response.stats || response;
                this.renderStatsTab();
            } else {
                if (empty) empty.style.display = 'block';
            }
        } catch (error) {
            console.error('Failed to load stats tab:', error);
            if (loading) loading.style.display = 'none';
            if (empty) empty.style.display = 'block';
        }
    }

    /**
     * 統計タブ描画
     */
    renderStatsTab() {
        const data = this.statsTabData;
        if (!data) return;

        const cards = document.getElementById('stats-cards');
        const statusTable = document.getElementById('stats-status-table');
        const typeTable = document.getElementById('stats-type-table');
        const empty = document.getElementById('stats-empty');

        // カード表示
        if (cards) {
            cards.style.display = 'flex';
            const approvedEl = document.getElementById('stats-total-approved');
            const rejectedEl = document.getElementById('stats-total-rejected');
            const todayEl = document.getElementById('stats-today');
            const weekEl = document.getElementById('stats-this-week');

            if (approvedEl) approvedEl.textContent = data.approved || data.total_approved || 0;
            if (rejectedEl) rejectedEl.textContent = data.rejected || data.total_rejected || 0;
            if (todayEl) todayEl.textContent = data.today || data.today_requests || 0;
            if (weekEl) weekEl.textContent = data.this_week || data.week_requests || 0;
        }

        // ステータス別テーブル
        const statusCounts = data.status_counts;
        if (statusCounts && statusTable) {
            statusTable.style.display = 'block';
            const tbody = document.getElementById('stats-status-tbody');
            if (tbody) {
                let html = '';
                if (Array.isArray(statusCounts)) {
                    statusCounts.forEach(item => {
                        html += '<tr><td>' + this.escapeHtml(String(item.status || item.name || '-')) + '</td><td>' + this.escapeHtml(String(item.count || 0)) + '</td></tr>';
                    });
                } else {
                    Object.entries(statusCounts).forEach(([key, val]) => {
                        html += '<tr><td>' + this.escapeHtml(key) + '</td><td>' + this.escapeHtml(String(val)) + '</td></tr>';
                    });
                }
                tbody.innerHTML = html || '<tr><td colspan="2" class="text-muted text-center">データなし</td></tr>';
            }
        }

        // 種別別テーブル
        const typeCounts = data.type_counts;
        if (typeCounts && typeTable) {
            typeTable.style.display = 'block';
            const tbody = document.getElementById('stats-type-tbody');
            if (tbody) {
                let html = '';
                if (Array.isArray(typeCounts)) {
                    typeCounts.forEach(item => {
                        html += '<tr><td>' + this.escapeHtml(String(item.type || item.name || '-')) + '</td><td>' + this.escapeHtml(String(item.count || 0)) + '</td></tr>';
                    });
                } else {
                    Object.entries(typeCounts).forEach(([key, val]) => {
                        html += '<tr><td>' + this.escapeHtml(key) + '</td><td>' + this.escapeHtml(String(val)) + '</td></tr>';
                    });
                }
                tbody.innerHTML = html || '<tr><td colspan="2" class="text-muted text-center">データなし</td></tr>';
            }
        }

        // データが全くない場合
        if (!statusCounts && !typeCounts && empty) {
            const hasAnyData = (data.approved || data.total_approved || data.rejected || data.total_rejected || data.today || data.today_requests);
            if (!hasAnyData) {
                empty.style.display = 'block';
            }
        }
    }

    /**
     * クリーンアップ
     */
    destroy() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
        }
    }
}

// グローバルインスタンス
let approvalManager;

// 初期化
document.addEventListener('DOMContentLoaded', async function() {
    console.log('Approval page loaded');
    approvalManager = new ApprovalManager();
    await approvalManager.init();
});
