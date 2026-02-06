/**
 * API クライアント
 * バックエンド API との連携を担当
 */

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
                    window.location.href = '/dev/index.html';
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
