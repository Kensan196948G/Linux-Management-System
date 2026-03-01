/**
 * users.js - Users & Groups Management UI
 *
 * Features:
 * - User list (non-system users, UID >= 1000)
 * - User add dialog (username/password validation, forbidden chars, approval workflow)
 * - User delete (with approval for non-admin)
 * - Password change
 * - Groups tab (list, add to group, remove from group)
 * - XSS prevention (escapeHtml)
 * - Role-based UI (Admin sees all actions, others see read-only + approval)
 */

class UserManager {
    constructor() {
        this.users = [];
        this.groups = [];
        this.currentUser = null;
        this.autoRefreshInterval = null;
        this.autoRefreshEnabled = false;
        this.currentTab = 'users'; // 'users' or 'groups'
        this.currentFilters = {
            sortBy: 'username',
            filterLocked: '',
            limit: 100
        };

        this.init();
    }

    /**
     * Initialize
     */
    async init() {
        console.log('UserManager: Initializing...');

        // Load current user info
        await this.loadCurrentUser();

        // Setup event listeners
        this.setupEventListeners();

        // Initial data load
        await this.loadUsers();
        await this.loadGroups();
    }

    /**
     * Load current user info
     */
    async loadCurrentUser() {
        try {
            const response = await api.request('GET', '/api/auth/me');
            this.currentUser = response.user || response;
            console.log('Current user:', this.currentUser);

            // Update sidebar user info
            if (typeof updateSidebarUserInfo === 'function') {
                updateSidebarUserInfo(this.currentUser);
            }
        } catch (error) {
            console.error('Failed to load current user:', error);
        }
    }

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // Refresh button
        const refreshBtn = document.getElementById('refreshBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                if (this.currentTab === 'users') {
                    this.loadUsers();
                } else {
                    this.loadGroups();
                }
            });
        }

        // Auto-Refresh toggle
        const autoRefreshBtn = document.getElementById('autoRefreshBtn');
        if (autoRefreshBtn) {
            autoRefreshBtn.addEventListener('click', () => {
                this.toggleAutoRefresh();
            });
        }

        // Tab switching
        const usersTab = document.getElementById('users-tab');
        const groupsTab = document.getElementById('groups-tab');
        if (usersTab) {
            usersTab.addEventListener('click', () => {
                this.currentTab = 'users';
                this.loadUsers();
            });
        }
        if (groupsTab) {
            groupsTab.addEventListener('click', () => {
                this.currentTab = 'groups';
                this.loadGroups();
            });
        }

        // Sort filter
        const sortBy = document.getElementById('sortBy');
        if (sortBy) {
            sortBy.addEventListener('change', (e) => {
                this.currentFilters.sortBy = e.target.value;
                this.loadUsers();
            });
        }

        // Lock filter
        const filterLocked = document.getElementById('filterLocked');
        if (filterLocked) {
            filterLocked.addEventListener('change', (e) => {
                this.currentFilters.filterLocked = e.target.value;
                this.loadUsers();
            });
        }

        // Add user button
        const addUserBtn = document.getElementById('addUserBtn');
        if (addUserBtn) {
            addUserBtn.addEventListener('click', () => {
                this.openAddUserModal();
            });
        }

        // Add user form submit
        const confirmAddUserBtn = document.getElementById('confirmAddUserBtn');
        if (confirmAddUserBtn) {
            confirmAddUserBtn.addEventListener('click', () => {
                this.handleAddUser();
            });
        }

        // Password change form submit
        const confirmPasswordBtn = document.getElementById('confirmPasswordBtn');
        if (confirmPasswordBtn) {
            confirmPasswordBtn.addEventListener('click', () => {
                this.handlePasswordChange();
            });
        }

        // Username input validation (real-time)
        const usernameInput = document.getElementById('add-username');
        if (usernameInput) {
            usernameInput.addEventListener('input', (e) => {
                this.validateUsernameInput(e.target);
            });
        }

        // Password strength indicator
        const passwordInput = document.getElementById('add-password');
        if (passwordInput) {
            passwordInput.addEventListener('input', (e) => {
                this.updatePasswordStrength(e.target.value);
            });
        }
    }

    // ===================================================================
    // User List
    // ===================================================================

    /**
     * Load user list
     */
    async loadUsers() {
        console.log('UserManager: Loading users...', this.currentFilters);
        this.showLoading('userTableBody');

        try {
            const params = new URLSearchParams();
            params.append('sort_by', this.currentFilters.sortBy);
            params.append('limit', this.currentFilters.limit);
            if (this.currentFilters.filterLocked) {
                params.append('filter_locked', this.currentFilters.filterLocked);
            }

            const response = await api.request('GET', `/api/users/list?${params.toString()}`);
            console.log('UserManager: Users loaded', response);

            this.users = response.users || [];
            this.renderUserTable();
            this.showStatus('success', `${this.users.length} users loaded`);
        } catch (error) {
            console.error('UserManager: Failed to load users', error);
            this.showStatus('error', `Failed to load users: ${error.message}`);
            this.showNoData('userTableBody', 'Failed to load user list');
        }
    }

    /**
     * Render user table
     */
    /**
     * Get role badge CSS class
     */
    getRoleBadgeClass(role) {
        if (!role) return 'role-unknown';
        switch (role) {
            case 'Admin':    return 'role-admin';
            case 'Approver': return 'role-approver';
            case 'Operator': return 'role-operator';
            case 'Viewer':   return 'role-viewer';
            default:         return 'role-unknown';
        }
    }

    renderUserTable() {
        const tbody = document.getElementById('usersTableBody') || document.getElementById('userTableBody');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (this.users.length === 0) {
            this.showNoData(tbody.id || 'usersTableBody', 'ユーザーが見つかりません');
            return;
        }

        this.users.forEach(user => {
            const row = document.createElement('tr');
            row.style.cursor = 'pointer';

            // Locked user highlight
            if (user.locked) {
                row.classList.add('locked-user');
            }

            // Username
            const nameCell = document.createElement('td');
            nameCell.textContent = user.username;
            nameCell.style.fontWeight = 'bold';
            row.appendChild(nameCell);

            // Email
            const emailCell = document.createElement('td');
            emailCell.textContent = user.email || '-';
            emailCell.style.fontSize = '13px';
            if (!user.email) emailCell.style.color = '#9ca3af';
            row.appendChild(emailCell);

            // Role badge
            const roleCell = document.createElement('td');
            if (user.role) {
                const badge = document.createElement('span');
                badge.className = `role-badge ${this.getRoleBadgeClass(user.role)}`;
                badge.textContent = user.role;
                roleCell.appendChild(badge);
            } else {
                const badge = document.createElement('span');
                badge.className = 'role-badge role-unknown';
                badge.textContent = '-';
                roleCell.appendChild(badge);
            }
            row.appendChild(roleCell);

            // Status (locked/unlocked)
            const statusCell = document.createElement('td');
            const statusBadge = document.createElement('span');
            if (user.locked) {
                statusBadge.className = 'status-badge status-locked';
                statusBadge.textContent = 'ロック';
            } else {
                statusBadge.className = 'status-badge status-active';
                statusBadge.textContent = 'アクティブ';
            }
            statusCell.appendChild(statusBadge);
            row.appendChild(statusCell);

            // Last Login
            const loginCell = document.createElement('td');
            loginCell.textContent = user.last_login ? this.formatDateTime(user.last_login) : '-';
            loginCell.style.fontSize = '11px';
            if (!user.last_login) loginCell.style.color = '#9ca3af';
            row.appendChild(loginCell);

            // Actions
            const actionsCell = document.createElement('td');
            actionsCell.className = 'actions-cell';

            // Password change button (Admin only)
            if (this.isAdmin()) {
                const pwdBtn = document.createElement('button');
                pwdBtn.className = 'btn btn-sm btn-outline-warning';
                pwdBtn.textContent = 'PW変更';
                pwdBtn.title = 'パスワード変更';
                pwdBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.openPasswordModal(user.username);
                });
                actionsCell.appendChild(pwdBtn);

                // Delete button (Admin only)
                const delBtn = document.createElement('button');
                delBtn.className = 'btn btn-sm btn-outline-danger ms-1';
                delBtn.textContent = '削除';
                delBtn.title = 'ユーザー削除';
                delBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.handleDeleteUser(user.username);
                });
                actionsCell.appendChild(delBtn);
            }

            row.appendChild(actionsCell);

            // Row click: show user detail
            row.addEventListener('click', () => {
                this.showUserDetail(user);
            });

            tbody.appendChild(row);
        });
    }

    // ===================================================================
    // Groups List
    // ===================================================================

    /**
     * Load group list
     */
    async loadGroups() {
        console.log('UserManager: Loading groups...');
        this.showLoading('groupTableBody');

        try {
            const response = await api.request('GET', '/api/users/groups');
            console.log('UserManager: Groups loaded', response);

            this.groups = response.groups || [];
            this.renderGroupTable();
            this.showStatus('success', `${this.groups.length} groups loaded`);
        } catch (error) {
            console.error('UserManager: Failed to load groups', error);
            this.showStatus('error', `Failed to load groups: ${error.message}`);
            this.showNoData('groupTableBody', 'Failed to load group list');
        }
    }

    /**
     * Render group table
     */
    renderGroupTable() {
        const tbody = document.getElementById('groupTableBody');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (this.groups.length === 0) {
            this.showNoData('groupTableBody', 'No groups found');
            return;
        }

        this.groups.forEach(group => {
            const row = document.createElement('tr');

            // Group name
            const nameCell = document.createElement('td');
            nameCell.textContent = group.group_name || group.name;
            nameCell.style.fontWeight = 'bold';
            row.appendChild(nameCell);

            // GID
            const gidCell = document.createElement('td');
            gidCell.textContent = group.gid;
            gidCell.style.textAlign = 'right';
            row.appendChild(gidCell);

            // Members
            const membersCell = document.createElement('td');
            const members = group.members || [];
            if (members.length > 0) {
                members.forEach(m => {
                    const badge = document.createElement('span');
                    badge.className = 'group-badge';
                    badge.textContent = m;
                    membersCell.appendChild(badge);
                });
            } else {
                membersCell.textContent = '(no members)';
                membersCell.style.color = '#6c757d';
            }
            row.appendChild(membersCell);

            // Member count
            const countCell = document.createElement('td');
            countCell.textContent = members.length;
            countCell.style.textAlign = 'right';
            row.appendChild(countCell);

            tbody.appendChild(row);
        });
    }

    // ===================================================================
    // Add User
    // ===================================================================

    /**
     * Open add user modal
     */
    openAddUserModal() {
        // Clear form
        const form = document.getElementById('addUserForm');
        if (form) form.reset();

        // Clear validation
        const feedback = document.querySelectorAll('.invalid-feedback');
        feedback.forEach(el => el.style.display = 'none');
        const inputs = document.querySelectorAll('.is-invalid');
        inputs.forEach(el => el.classList.remove('is-invalid'));

        // Reset password strength
        const strengthBar = document.getElementById('password-strength-bar');
        if (strengthBar) {
            strengthBar.style.width = '0%';
            strengthBar.className = 'progress-bar';
        }

        // Show reason field if non-admin (needs approval)
        const reasonGroup = document.getElementById('add-reason-group');
        if (reasonGroup) {
            reasonGroup.style.display = this.isAdmin() ? 'none' : 'block';
        }

        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('addUserModal'));
        modal.show();
    }

    /**
     * Validate username input in real-time
     */
    validateUsernameInput(input) {
        const value = input.value;
        const feedback = document.getElementById('username-feedback');

        // Check forbidden characters
        if (/[;|&$()`><*?{}\[\]]/.test(value)) {
            input.classList.add('is-invalid');
            if (feedback) {
                feedback.textContent = 'Forbidden characters detected';
                feedback.style.display = 'block';
            }
            return false;
        }

        // Check pattern: lowercase letter or underscore, then alphanumeric/underscore/hyphen, max 32 chars
        if (value && !/^[a-z_][a-z0-9_-]{0,31}$/.test(value)) {
            input.classList.add('is-invalid');
            if (feedback) {
                feedback.textContent = 'Username must start with lowercase letter or underscore, contain only a-z, 0-9, _, -, max 32 chars';
                feedback.style.display = 'block';
            }
            return false;
        }

        input.classList.remove('is-invalid');
        if (feedback) feedback.style.display = 'none';
        return true;
    }

    /**
     * Update password strength indicator
     */
    updatePasswordStrength(password) {
        const bar = document.getElementById('password-strength-bar');
        const text = document.getElementById('password-strength-text');
        if (!bar || !text) return;

        let score = 0;
        if (password.length >= 8) score++;
        if (password.length >= 12) score++;
        if (/[A-Z]/.test(password)) score++;
        if (/[a-z]/.test(password)) score++;
        if (/[0-9]/.test(password)) score++;
        if (/[^A-Za-z0-9]/.test(password)) score++;

        let width, colorClass, label;
        if (score <= 2) {
            width = '25%'; colorClass = 'bg-danger'; label = 'Weak';
        } else if (score <= 3) {
            width = '50%'; colorClass = 'bg-warning'; label = 'Fair';
        } else if (score <= 4) {
            width = '75%'; colorClass = 'bg-info'; label = 'Good';
        } else {
            width = '100%'; colorClass = 'bg-success'; label = 'Strong';
        }

        bar.style.width = width;
        bar.className = `progress-bar ${colorClass}`;
        text.textContent = label;
    }

    /**
     * Handle add user form submission
     */
    async handleAddUser() {
        const username = document.getElementById('add-username')?.value?.trim();
        const password = document.getElementById('add-password')?.value;
        const confirmPassword = document.getElementById('add-password-confirm')?.value;
        const gecos = document.getElementById('add-gecos')?.value?.trim() || '';
        const shell = document.getElementById('add-shell')?.value || '/bin/bash';
        const reason = document.getElementById('add-reason')?.value?.trim() || '';

        // Validation
        if (!username) {
            this.showToast('warning', 'Username is required');
            return;
        }

        if (!/^[a-z_][a-z0-9_-]{0,31}$/.test(username)) {
            this.showToast('warning', 'Invalid username format. Must start with lowercase letter or underscore, max 32 characters.');
            return;
        }

        if (/[;|&$()`><*?{}\[\]]/.test(username)) {
            this.showToast('error', 'Username contains forbidden characters');
            return;
        }

        if (!password || password.length < 8) {
            this.showToast('warning', 'Password must be at least 8 characters');
            return;
        }

        if (password !== confirmPassword) {
            this.showToast('warning', 'Passwords do not match');
            return;
        }

        // Non-admin: submit as approval request
        if (!this.isAdmin()) {
            if (!reason) {
                this.showToast('warning', 'Reason is required for approval request');
                return;
            }

            try {
                const response = await api.request('POST', '/api/approval/request', {
                    request_type: 'user_add',
                    payload: { username, gecos, shell },
                    reason: reason
                });

                if (response.status === 'success') {
                    this.showToast('success', 'Approval request submitted. An administrator will review your request.');
                    bootstrap.Modal.getInstance(document.getElementById('addUserModal'))?.hide();
                }
            } catch (error) {
                console.error('Failed to submit approval request:', error);
                this.showToast('error', 'Failed to submit approval request: ' + (error.message || 'Unknown error'));
            }
            return;
        }

        // Admin: directly create user
        try {
            const response = await api.request('POST', '/api/users', {
                username,
                password,
                gecos,
                shell
            });

            if (response.status === 'success') {
                this.showToast('success', 'User created successfully: ' + username);
                bootstrap.Modal.getInstance(document.getElementById('addUserModal'))?.hide();
                await this.loadUsers();
            }
        } catch (error) {
            console.error('Failed to create user:', error);
            this.showToast('error', 'Failed to create user: ' + (error.message || 'Unknown error'));
        }
    }

    // ===================================================================
    // Delete User
    // ===================================================================

    /**
     * Handle user deletion
     */
    async handleDeleteUser(username) {
        if (!this.isAdmin()) {
            this.showToast('error', 'Only administrators can delete users.');
            return;
        }

        const confirmed = await this.showConfirm(
            'ユーザー削除の確認',
            `ユーザー "${username}" を削除しますか？この操作は取り消せません。`
        );
        if (!confirmed) return;

        try {
            const response = await api.request('POST', '/api/users/delete', {
                username: username
            });

            if (response.status === 'success') {
                this.showToast('success', 'User deleted: ' + username);
                await this.loadUsers();
            }
        } catch (error) {
            console.error('Failed to delete user:', error);
            this.showToast('error', 'Failed to delete user: ' + (error.message || 'Unknown error'));
        }
    }

    // ===================================================================
    // Password Change
    // ===================================================================

    /**
     * Open password change modal
     */
    openPasswordModal(username) {
        document.getElementById('passwd-username').textContent = username;
        document.getElementById('passwd-target').value = username;
        document.getElementById('new-password').value = '';
        document.getElementById('new-password-confirm').value = '';

        const modal = new bootstrap.Modal(document.getElementById('passwordModal'));
        modal.show();
    }

    /**
     * Handle password change
     */
    async handlePasswordChange() {
        const username = document.getElementById('passwd-target')?.value;
        const newPassword = document.getElementById('new-password')?.value;
        const confirmPassword = document.getElementById('new-password-confirm')?.value;

        if (!newPassword || newPassword.length < 8) {
            this.showToast('warning', 'Password must be at least 8 characters');
            return;
        }

        if (newPassword !== confirmPassword) {
            this.showToast('warning', 'Passwords do not match');
            return;
        }

        try {
            const response = await api.request('POST', '/api/users/passwd', {
                username: username,
                password: newPassword
            });

            if (response.status === 'success') {
                this.showToast('success', 'Password changed successfully for: ' + username);
                bootstrap.Modal.getInstance(document.getElementById('passwordModal'))?.hide();
            }
        } catch (error) {
            console.error('Failed to change password:', error);
            this.showToast('error', 'Failed to change password: ' + (error.message || 'Unknown error'));
        }
    }

    // ===================================================================
    // User Detail
    // ===================================================================

    /**
     * Show user detail in modal
     */
    showUserDetail(user) {
        const body = document.getElementById('userDetailBody');
        if (!body) return;

        const roleBadgeClass = this.getRoleBadgeClass(user.role);
        const roleDisplay = user.role
            ? `<span class="role-badge ${roleBadgeClass}">${this.escapeHtml(user.role)}</span>`
            : '<span class="role-badge role-unknown">-</span>';
        const roleNote = this.isAdmin() && user.role
            ? `<div class="role-note">⚠️ (変更不可: 承認フロー必要)</div>` : '';

        body.innerHTML = `
            <div class="row">
                <div class="col-md-6">
                    <p><strong>ユーザー名:</strong> ${this.escapeHtml(user.username)}</p>
                    <p><strong>メールアドレス:</strong> ${this.escapeHtml(user.email || '-')}</p>
                    <p><strong>ロール:</strong> ${roleDisplay}${roleNote}</p>
                    <p><strong>状態:</strong> ${user.locked
                        ? '<span class="status-badge status-locked">ロック</span>'
                        : '<span class="status-badge status-active">アクティブ</span>'}</p>
                    <p><strong>最終ログイン:</strong> ${this.escapeHtml(user.last_login ? this.formatDateTime(user.last_login) : '-')}</p>
                </div>
                <div class="col-md-6">
                    <p><strong>UID:</strong> ${this.escapeHtml(user.uid != null ? String(user.uid) : '-')}</p>
                    <p><strong>GID:</strong> ${this.escapeHtml(user.gid != null ? String(user.gid) : '-')}</p>
                    <p><strong>説明:</strong> ${this.escapeHtml(user.gecos || '-')}</p>
                    <p><strong>ホーム:</strong> <code>${this.escapeHtml(user.home || '-')}</code></p>
                    <p><strong>シェル:</strong> <code>${this.escapeHtml(user.shell || '-')}</code></p>
                </div>
            </div>
            ${user.groups && user.groups.length > 0 ? `
            <hr>
            <p><strong>グループ:</strong></p>
            <div class="groups-list">
                ${user.groups.map(g => `<span class="group-badge">${this.escapeHtml(g)}</span>`).join(' ')}
            </div>` : ''}
        `;

        const modal = new bootstrap.Modal(document.getElementById('userDetailModal'));
        modal.show();
    }

    // ===================================================================
    // Utility
    // ===================================================================

    /**
     * Check if current user is Admin
     */
    isAdmin() {
        return this.currentUser && this.currentUser.role === 'Admin';
    }

    /**
     * Toggle auto-refresh
     */
    toggleAutoRefresh() {
        this.autoRefreshEnabled = !this.autoRefreshEnabled;
        const btn = document.getElementById('autoRefreshBtn');

        if (this.autoRefreshEnabled) {
            if (btn) {
                btn.textContent = 'Auto-Refresh: ON';
                btn.classList.add('active');
            }

            this.autoRefreshInterval = setInterval(() => {
                if (this.currentTab === 'users') {
                    this.loadUsers();
                } else {
                    this.loadGroups();
                }
            }, 10000); // 10 seconds

            this.showStatus('info', 'Auto-refresh enabled (10s interval)');
        } else {
            if (btn) {
                btn.textContent = 'Auto-Refresh: OFF';
                btn.classList.remove('active');
            }

            if (this.autoRefreshInterval) {
                clearInterval(this.autoRefreshInterval);
                this.autoRefreshInterval = null;
            }

            this.showStatus('info', 'Auto-refresh disabled');
        }
    }

    /**
     * Show status message
     */
    showStatus(type, message) {
        const statusDiv = document.getElementById('statusDisplay');
        if (!statusDiv) return;
        statusDiv.className = `status ${type}`;
        statusDiv.textContent = message;

        setTimeout(() => {
            statusDiv.textContent = '';
            statusDiv.className = '';
        }, 3000);
    }

    /**
     * Show loading state
     */
    showLoading(tbodyId) {
        const tbody = document.getElementById(tbodyId);
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="6" class="loading">読み込み中...</td></tr>';
        }
    }

    /**
     * Show no data state
     */
    showNoData(tbodyId, message) {
        const tbody = document.getElementById(tbodyId);
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="6" class="no-data">${this.escapeHtml(message)}</td></tr>`;
        }
    }

    /**
     * Format datetime
     */
    formatDateTime(isoString) {
        if (!isoString) return '-';
        try {
            const date = new Date(isoString);
            const now = new Date();
            const diff = now - date;

            if (diff < 86400000) {
                const hours = Math.floor(diff / 3600000);
                const minutes = Math.floor((diff % 3600000) / 60000);
                if (hours > 0) return `${hours}h ago`;
                if (minutes > 0) return `${minutes}m ago`;
                return 'just now';
            }

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
     * Show Bootstrap toast notification
     * @param {string} type - 'success', 'error', 'warning', 'info'
     * @param {string} message - Message to display
     */
    showToast(type, message) {
        // Remove existing toast if present
        const existing = document.getElementById('userManagerToast');
        if (existing) existing.remove();

        const bgClass = {
            success: 'bg-success',
            error: 'bg-danger',
            warning: 'bg-warning text-dark',
            info: 'bg-info text-dark'
        }[type] || 'bg-secondary';

        const toastHtml = document.createElement('div');
        toastHtml.className = 'toast-container position-fixed top-0 end-0 p-3';
        toastHtml.style.zIndex = '1090';
        toastHtml.innerHTML = `
            <div id="userManagerToast" class="toast align-items-center ${bgClass} text-white border-0" role="alert" aria-live="assertive" aria-atomic="true">
                <div class="d-flex">
                    <div class="toast-body">${this.escapeHtml(message)}</div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
            </div>
        `;
        document.body.appendChild(toastHtml);

        const toastEl = document.getElementById('userManagerToast');
        const toast = new bootstrap.Toast(toastEl, { delay: 4000 });
        toast.show();

        toastEl.addEventListener('hidden.bs.toast', () => {
            toastHtml.remove();
        });
    }

    /**
     * Show Bootstrap confirm modal and return a Promise<boolean>
     * @param {string} title - Modal title
     * @param {string} message - Confirm message
     * @returns {Promise<boolean>}
     */
    showConfirm(title, message) {
        return new Promise((resolve) => {
            // Remove existing confirm modal if present
            const existing = document.getElementById('userManagerConfirmModal');
            if (existing) existing.remove();

            const modalDiv = document.createElement('div');
            modalDiv.innerHTML = `
                <div class="modal fade" id="userManagerConfirmModal" tabindex="-1" aria-hidden="true">
                    <div class="modal-dialog modal-dialog-centered">
                        <div class="modal-content bg-dark text-white">
                            <div class="modal-header border-secondary">
                                <h5 class="modal-title">${this.escapeHtml(title)}</h5>
                                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
                            </div>
                            <div class="modal-body">${this.escapeHtml(message)}</div>
                            <div class="modal-footer border-secondary">
                                <button type="button" class="btn btn-secondary" id="confirmCancelBtn" data-bs-dismiss="modal">キャンセル</button>
                                <button type="button" class="btn btn-danger" id="confirmOkBtn">実行</button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(modalDiv);

            const modalEl = document.getElementById('userManagerConfirmModal');
            const modal = new bootstrap.Modal(modalEl);

            let resolved = false;
            document.getElementById('confirmOkBtn').addEventListener('click', () => {
                resolved = true;
                modal.hide();
            });

            modalEl.addEventListener('hidden.bs.modal', () => {
                if (!resolved) resolve(false);
                else resolve(true);
                modalDiv.remove();
            });

            modal.show();
        });
    }

    /**
     * HTML escape (XSS prevention)
     */
    escapeHtml(text) {
        if (typeof text !== 'string') text = String(text);
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Cleanup
     */
    destroy() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
        }
    }
}

// Global instance
let userManager;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async function() {
    console.log('Users & Groups page loaded');

    // Auth check
    if (!api.isAuthenticated()) {
        console.warn('Not authenticated, redirecting to dashboard');
        window.location.href = 'dashboard.html';
        return;
    }

    // Restore accordion state
    if (typeof restoreAccordionState === 'function') {
        restoreAccordionState();
    }

    // Initialize UserManager
    userManager = new UserManager();
});
