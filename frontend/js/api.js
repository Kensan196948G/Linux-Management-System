/**
 * API クライアント
 * バックエンド API との連携を担当
 */

/** dev/prod 両対応: ログインページURLを動的に取得 */
function getLoginUrl() {
    return window.location.pathname.replace(/[^/]*$/, '') + 'index.html';
}

class APIClient {
    constructor(baseURL) {
        // 現在のオリジンを使用（同一オリジンで動作）
        // 例: http://192.168.0.185:5012
        this.baseURL = baseURL || window.location.origin;
        this.token = localStorage.getItem('access_token');
        console.log('APIClient initialized with baseURL:', this.baseURL);
    }

    /**
     * HTTP リクエストを送信
     */
    async request(method, endpoint, data = null) {
        const url = `${this.baseURL}${endpoint}`;

        const headers = {
            'Content-Type': 'application/json',
        };

        // トークンがあれば Authorization ヘッダーに追加
        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        const options = {
            method,
            headers,
        };

        if (data && (method === 'POST' || method === 'PUT')) {
            options.body = JSON.stringify(data);
        }

        try {
            const response = await fetch(url, options);

            if (response.status === 401) {
                // 認証エラー: トークンをクリアしてログイン画面へ
                console.error('❌ 401 Unauthorized - Token expired or invalid');
                this.clearToken();
                // ログイン画面にいない場合のみリダイレクト（無限ループ防止）
                if (!window.location.pathname.includes('index.html')) {
                    alert('セッションが期限切れです。再度ログインしてください。');
                    // dev/prod 両対応: 現在のパスから index.html を構築
                    const basePath = window.location.pathname.replace(/[^/]*$/, '');
                    window.location.href = basePath + 'index.html';
                }
                throw new Error('Token expired or invalid');
            }

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.message || `HTTP ${response.status}`);
            }

            return result;

        } catch (error) {
            console.error(`API Error: ${method} ${endpoint}`, error);
            throw error;
        }
    }

    /**
     * トークンを設定
     */
    setToken(token) {
        console.log('Setting token... (length:', token ? token.length : 0, ')');
        this.token = token;
        localStorage.setItem('access_token', token);

        // Edge対策: 保存確認
        const stored = localStorage.getItem('access_token');
        if (stored !== token) {
            console.error('❌ Token storage verification failed!');
            console.error('Expected:', token.substring(0, 50));
            console.error('Stored:', stored ? stored.substring(0, 50) : 'NULL');
        } else {
            console.log('✅ Token stored and verified in localStorage');
        }
    }

    /**
     * トークンをクリア
     */
    clearToken() {
        this.token = null;
        localStorage.removeItem('access_token');
    }

    // ===================================================================
    // HTTP ショートハンド（GET / POST / PUT / DELETE）
    // ===================================================================

    async get(endpoint) {
        return this.request('GET', endpoint);
    }

    async post(endpoint, data) {
        return this.request('POST', endpoint, data);
    }

    async put(endpoint, data) {
        return this.request('PUT', endpoint, data);
    }

    async delete(endpoint) {
        return this.request('DELETE', endpoint);
    }

    /**
     * ログイン状態を確認
     */
    isAuthenticated() {
        return !!this.token;
    }

    // ===================================================================
    // 認証 API
    // ===================================================================

    async login(email, password) {
        const result = await this.request('POST', '/api/auth/login', { email, password });
        this.setToken(result.access_token);
        return result;
    }

    async logout() {
        try {
            await this.request('POST', '/api/auth/logout');
        } finally {
            this.clearToken();
        }
    }

    async getCurrentUser() {
        return await this.request('GET', '/api/auth/me');
    }

    // ===================================================================
    // システム API
    // ===================================================================

    async getSystemStatus() {
        return await this.request('GET', '/api/system/status');
    }

    // ===================================================================
    // ネットワーク API
    // ===================================================================

    async getNetworkInterfaces() {
        return await this.request('GET', '/api/network/interfaces');
    }

    async getNetworkStats() {
        return await this.request('GET', '/api/network/stats');
    }

    async getNetworkConnections() {
        return await this.request('GET', '/api/network/connections');
    }

    async getNetworkRoutes() {
        return await this.request('GET', '/api/network/routes');
    }

    // ===================================================================
    // サーバー API
    // ===================================================================

    async getAllServerStatus() {
        return await this.request('GET', '/api/servers/status');
    }

    async getServerStatus(server) {
        return await this.request('GET', `/api/servers/${server}/status`);
    }

    async getServerVersion(server) {
        return await this.request('GET', `/api/servers/${server}/version`);
    }

    async getServerConfig(server) {
        return await this.request('GET', `/api/servers/${server}/config`);
    }

    // ===================================================================
    // ハードウェア API
    // ===================================================================

    async getHardwareMemory() {
        return await this.request('GET', '/api/hardware/memory');
    }

    async getHardwareDiskUsage() {
        return await this.request('GET', '/api/hardware/disk_usage');
    }

    async getHardwareDisks() {
        return await this.request('GET', '/api/hardware/disks');
    }

    async getHardwareSensors() {
        return await this.request('GET', '/api/hardware/sensors');
    }

    async getHardwareSmart(device) {
        return await this.request('GET', `/api/hardware/smart?device=${encodeURIComponent(device)}`);
    }

    // ===================================================================
    // サービス API
    // ===================================================================

    async restartService(serviceName) {
        return await this.request('POST', '/api/services/restart', {
            service_name: serviceName
        });
    }

    async getAllServerStatus() {
        return await this.request('GET', '/api/servers/status');
    }

    async getServerStatus(server) {
        return await this.request('GET', `/api/servers/${server}/status`);
    }

    // ===================================================================
    // ログ API
    // ===================================================================

    async getLogs(serviceName, lines = 100) {
        return await this.request('GET', `/api/logs/${serviceName}?lines=${lines}`);
    }

    // ===================================================================
    // ユーザー・グループ API
    // ===================================================================

    async getUsers(limit = 100) {
        return await this.request('GET', `/api/users?limit=${limit}`);
    }

    async getUserGroups() {
        return await this.request('GET', '/api/users/groups/list');
    }

    // ===================================================================
    // Cron API
    // ===================================================================

    async getCronJobs(username = 'root') {
        return await this.request('GET', `/api/cron/${encodeURIComponent(username)}`);
    }

    // ===================================================================
    // 監査ログ API
    // ===================================================================

    async getAuditLogs(page = 1, perPage = 50) {
        return await this.request('GET', `/api/audit/logs?page=${page}&per_page=${perPage}`);
    }

    async exportAuditLogs() {
        return await this.request('GET', '/api/audit/logs/export');
    }

    // ===================================================================
    // 時刻 API
    // ===================================================================

    async getTimeStatus() {
        return await this.request('GET', '/api/time/status');
    }

    async getTimezones() {
        return await this.request('GET', '/api/time/timezones');
    }

    // ===================================================================
    // クォータ API
    // ===================================================================

    async getQuotasStatus() {
        return await this.request('GET', '/api/quotas/status');
    }

    async getQuotaUsers() {
        return await this.request('GET', '/api/quotas/users');
    }

    // ===================================================================
    // 帯域幅 API
    // ===================================================================

    async getBandwidthSummary() {
        return await this.request('GET', '/api/bandwidth/summary');
    }

    async getBandwidthInterfaces() {
        return await this.request('GET', '/api/bandwidth/interfaces');
    }

    async getBandwidthLive(iface = '') {
        const q = iface ? `?iface=${encodeURIComponent(iface)}` : '';
        return await this.request('GET', `/api/bandwidth/live${q}`);
    }

    async getBandwidthDaily(iface = '') {
        const q = iface ? `?iface=${encodeURIComponent(iface)}` : '';
        return await this.request('GET', `/api/bandwidth/daily${q}`);
    }

    async getBandwidthHourly(iface = '') {
        const q = iface ? `?iface=${encodeURIComponent(iface)}` : '';
        return await this.request('GET', `/api/bandwidth/hourly${q}`);
    }

    async getBandwidthTop() {
        return await this.request('GET', '/api/bandwidth/top');
    }

    // ===================================================================
    // DB モニター API
    // ===================================================================

    async getDbStatus(dbType = 'mysql') {
        return await this.request('GET', `/api/dbmonitor/${dbType}/status`);
    }

    async getDbProcesses(dbType = 'mysql') {
        return await this.request('GET', `/api/dbmonitor/${dbType}/processes`);
    }

    async getDbDatabases(dbType = 'mysql') {
        return await this.request('GET', `/api/dbmonitor/${dbType}/databases`);
    }

    async getDbConnections(dbType = 'mysql') {
        return await this.request('GET', `/api/dbmonitor/${dbType}/connections`);
    }

    async getDbVariables(dbType = 'mysql') {
        return await this.request('GET', `/api/dbmonitor/${dbType}/variables`);
    }

    // ===================================================================
    // Apache API
    // ===================================================================

    async getApacheStatus() {
        return await this.request('GET', '/api/apache/status');
    }

    async getApacheConfig() {
        return await this.request('GET', '/api/apache/config');
    }

    async getApacheVhosts() {
        return await this.request('GET', '/api/apache/vhosts');
    }

    async getApacheLogs(logType = 'error', lines = 50) {
        return await this.request('GET', `/api/apache/logs?log_type=${logType}&lines=${lines}`);
    }

    // ===================================================================
    // SSH API
    // ===================================================================

    async getSshStatus() {
        return await this.request('GET', '/api/ssh/status');
    }

    async getSshConfig() {
        return await this.request('GET', '/api/ssh/config');
    }

    // ===================================================================
    // Postfix API
    // ===================================================================

    async getPostfixStatus() {
        return await this.request('GET', '/api/postfix/status');
    }

    async getPostfixQueue() {
        return await this.request('GET', '/api/postfix/queue');
    }

    async getPostfixLogs(lines = 50) {
        return await this.request('GET', `/api/postfix/logs?lines=${lines}`);
    }

    // ===================================================================
    // ネットワーク追加 API
    // ===================================================================

    async getNetworkDns() {
        return await this.request('GET', '/api/network/dns');
    }

    async getNetworkConnections() {
        return await this.request('GET', '/api/network/connections');
    }

    async getNetworkRoutes() {
        return await this.request('GET', '/api/network/routes');
    }

    // ===================================================================
    // ファイアウォール API
    // ===================================================================

    async getFirewallStatus() {
        return await this.request('GET', '/api/firewall/status');
    }

    async getFirewallRules() {
        return await this.request('GET', '/api/firewall/rules');
    }

    async getFirewallPolicy() {
        return await this.request('GET', '/api/firewall/policy');
    }

    async createFirewallRule(port, protocol, action, reason) {
        return await this.request('POST', '/api/firewall/rules', { port, protocol, action, reason });
    }

    async deleteFirewallRule(ruleNum) {
        return await this.request('DELETE', `/api/firewall/rules/${ruleNum}`);
    }

    // ===================================================================
    // ブートアップ API
    // ===================================================================

    async getBootupStatus() {
        return await this.request('GET', '/api/bootup/status');
    }

    async getBootupServices() {
        return await this.request('GET', '/api/bootup/services');
    }

    async enableBootupService(service, reason) {
        return await this.request('POST', '/api/bootup/enable', { service, reason });
    }

    async disableBootupService(service, reason) {
        return await this.request('POST', '/api/bootup/disable', { service, reason });
    }

    async bootupAction(action, delay = 'now', reason) {
        return await this.request('POST', '/api/bootup/action', { action, delay, reason });
    }

    // ===================================================================
    // 承認フロー API
    // ===================================================================

    async getApprovalPending() {
        return await this.request('GET', '/api/approval/pending');
    }

    async getMyApprovalRequests() {
        return await this.request('GET', '/api/approval/my-requests');
    }

    // ===================================================================
    // ファイルシステム API
    // ===================================================================

    async getFilesystemUsage() {
        return await this.request('GET', '/api/filesystem/usage');
    }

    async getFilesystemMounts() {
        return await this.request('GET', '/api/filesystem/mounts');
    }
}

// グローバルインスタンス
const api = new APIClient();
