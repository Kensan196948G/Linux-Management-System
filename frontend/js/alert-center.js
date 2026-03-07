/**
 * アラートセンター
 * WebSocket によるリアルタイムアラート受信とブラウザ通知を管理する。
 */

class AlertCenter {
    constructor() {
        /** @type {WebSocket|null} */
        this.ws = null;
        /** @type {number} */
        this.unreadCount = 0;
        /** @type {HTMLElement|null} サイドバーバッジ要素 */
        this.badgeEl = null;
        /** ローカルストレージ既読管理キー */
        this.STORAGE_KEY = 'lms_read_alerts';
        this._reconnectTimer = null;
        this._reconnectDelay = 5000;
    }

    /**
     * WebSocket /api/ws/alerts に接続してリアルタイムアラート受信を開始する。
     * @param {string} token - JWT アクセストークン
     */
    connect(token) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) return;

        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${proto}//${location.host}/api/ws/alerts`;

        try {
            this.ws = new WebSocket(url);
        } catch (e) {
            console.warn('[AlertCenter] WebSocket 接続失敗:', e);
            this.updateStatus(false);
            return;
        }

        this.ws.onopen = () => {
            // トークンを最初のメッセージで送信（URLに含めない＝ログに残らない）
            this.ws.send(JSON.stringify({ type: 'auth', token: token }));
            console.info('[AlertCenter] WebSocket 接続確立');
            this.updateStatus(true);
            this._reconnectDelay = 5000;
            if (this._reconnectTimer) {
                clearTimeout(this._reconnectTimer);
                this._reconnectTimer = null;
            }
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this._handleMessage(data, token);
            } catch (e) {
                console.warn('[AlertCenter] メッセージ解析エラー:', e);
            }
        };

        this.ws.onerror = () => {
            console.warn('[AlertCenter] WebSocket エラー');
            this.updateStatus(false);
        };

        this.ws.onclose = () => {
            console.info('[AlertCenter] WebSocket 切断 — 再接続予定');
            this.updateStatus(false);
            this._scheduleReconnect(token);
        };
    }

    /**
     * WebSocket 接続を切断する。
     */
    disconnect() {
        if (this._reconnectTimer) {
            clearTimeout(this._reconnectTimer);
            this._reconnectTimer = null;
        }
        if (this.ws) {
            this.ws.onclose = null;
            this.ws.close();
            this.ws = null;
        }
        this.updateStatus(false);
    }

    /**
     * ブラウザ通知許可を要求する。
     * @returns {Promise<NotificationPermission>}
     */
    async requestPermission() {
        if (!('Notification' in window)) return 'denied';
        if (Notification.permission === 'default') {
            return await Notification.requestPermission();
        }
        return Notification.permission;
    }

    /**
     * ブラウザ通知を発火する。
     * @param {string} title
     * @param {string} body
     * @param {string} [icon='/favicon.ico']
     */
    notify(title, body, icon = '/favicon.ico') {
        if (!('Notification' in window) || Notification.permission !== 'granted') return;
        try {
            new Notification(title, { body, icon });
        } catch (e) {
            console.warn('[AlertCenter] 通知エラー:', e);
        }
    }

    /**
     * サイドバーのバッジカウントを更新する。
     * count が 0 のときはバッジを非表示にする。
     * @param {number} count
     */
    updateBadge(count) {
        this.unreadCount = count;
        if (!this.badgeEl) {
            this.badgeEl = document.getElementById('alert-badge');
        }
        if (this.badgeEl) {
            this.badgeEl.textContent = count;
            this.badgeEl.style.display = count > 0 ? '' : 'none';
        }
    }

    /**
     * WebSocket 接続状態を DOM 上に表示する。
     * @param {boolean} connected
     */
    updateStatus(connected) {
        const el = document.getElementById('ws-status-badge');
        if (!el) return;
        if (connected) {
            el.textContent = '🔔 リアルタイム接続中';
            el.className = 'ws-status ws-status--connected';
        } else {
            el.textContent = '🔕 切断中';
            el.className = 'ws-status ws-status--disconnected';
        }
    }

    /**
     * アラート ID を既読としてローカルストレージに保存する。
     * @param {string} alertId
     */
    markRead(alertId) {
        const read = this._getReadSet();
        read.add(alertId);
        this._saveReadSet(read);
    }

    /**
     * アラート ID が既読かどうかを返す。
     * @param {string} alertId
     * @returns {boolean}
     */
    isRead(alertId) {
        return this._getReadSet().has(alertId);
    }

    // ---------------------------------------------------------------
    // プライベートメソッド
    // ---------------------------------------------------------------

    /** @private */
    _handleMessage(data, token) {
        if (data.type === 'update') {
            const alerts = data.active_alerts || [];
            const unread = alerts.filter(a => !this.isRead(a.id));
            this.updateBadge(unread.length);

            // 未読の新着アラートを通知
            for (const a of unread) {
                this.notify(
                    `⚠️ アラート: ${a.description || a.id}`,
                    `現在値: ${a.value}  閾値: ${a.threshold}`
                );
            }

            // ページタイトルに件数表示
            this._updatePageTitle(unread.length);
        }
    }

    /** @private */
    _scheduleReconnect(token) {
        if (this._reconnectTimer) return;
        this._reconnectTimer = setTimeout(() => {
            this._reconnectTimer = null;
            this._reconnectDelay = Math.min(this._reconnectDelay * 2, 60000);
            this.connect(token);
        }, this._reconnectDelay);
    }

    /** @private @returns {Set<string>} */
    _getReadSet() {
        try {
            const raw = localStorage.getItem(this.STORAGE_KEY);
            return new Set(raw ? JSON.parse(raw) : []);
        } catch {
            return new Set();
        }
    }

    /** @private */
    _saveReadSet(set) {
        try {
            localStorage.setItem(this.STORAGE_KEY, JSON.stringify([...set]));
        } catch {}
    }

    /** @private */
    _updatePageTitle(unreadCount) {
        const base = document.title.replace(/^\(\d+件\)\s*/, '');
        document.title = unreadCount > 0 ? `(${unreadCount}件) ${base}` : base;
    }
}

const alertCenter = new AlertCenter();
