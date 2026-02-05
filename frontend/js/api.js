/**
 * API クライアント
 * バックエンド API との連携を担当
 */

class APIClient {
    constructor(baseURL) {
        this.baseURL = baseURL || 'http://localhost:5012';
        this.token = localStorage.getItem('access_token');
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
                this.clearToken();
                window.location.href = '/login.html';
                throw new Error('Unauthorized');
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
        this.token = token;
        localStorage.setItem('access_token', token);
    }

    /**
     * トークンをクリア
     */
    clearToken() {
        this.token = null;
        localStorage.removeItem('access_token');
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
    // サービス API
    // ===================================================================

    async restartService(serviceName) {
        return await this.request('POST', '/api/services/restart', {
            service_name: serviceName
        });
    }

    // ===================================================================
    // ログ API
    // ===================================================================

    async getLogs(serviceName, lines = 100) {
        return await this.request('GET', `/api/logs/${serviceName}?lines=${lines}`);
    }
}

// グローバルインスタンス
const api = new APIClient();
