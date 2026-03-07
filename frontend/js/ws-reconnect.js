/**
 * ws-reconnect.js - WebSocket with exponential backoff auto-reconnect
 *
 * Usage:
 *   const ws = new WSReconnect(url, { initialDelay: 1000, maxDelay: 30000 });
 *   ws.on('connected', () => ws.send(JSON.stringify({ type: 'auth', token })));
 *   ws.on('message', (data) => console.log(data));
 *   ws.on('reconnecting', ({ attempt, delay }) => console.log(attempt, delay));
 *   ws.connect();
 */
class WSReconnect {
    /**
     * @param {string} url - WebSocket URL (ws:// or wss://)
     * @param {object} options
     * @param {number} options.initialDelay  - First reconnect delay ms (default 1000)
     * @param {number} options.maxDelay      - Maximum reconnect delay ms (default 30000)
     * @param {number} options.multiplier    - Backoff multiplier (default 1.5)
     * @param {number} options.jitter        - Random jitter fraction 0-1 (default 0.1)
     * @param {number} options.maxAttempts   - 0 = infinite (default 0)
     */
    constructor(url, options = {}) {
        this.url = url;
        this.options = {
            initialDelay: 1000,
            maxDelay: 30000,
            multiplier: 1.5,
            jitter: 0.1,
            maxAttempts: 0,
            ...options,
        };
        this.ws = null;
        this.attemptCount = 0;
        this.reconnectTimer = null;
        this._shouldReconnect = false;
        this._handlers = { message: [], connected: [], disconnected: [], reconnecting: [] };
    }

    /**
     * Register an event handler.
     * @param {'connected'|'disconnected'|'message'|'reconnecting'} event
     * @param {Function} handler
     */
    on(event, handler) {
        if (this._handlers[event]) {
            this._handlers[event].push(handler);
        }
        return this;
    }

    /** Convenience alias for on('message', handler). */
    onMessage(handler) {
        return this.on('message', handler);
    }

    /** Open the connection and enable auto-reconnect. */
    connect() {
        this._shouldReconnect = true;
        this.attemptCount = 0;
        this._connect();
    }

    /** Close the connection and disable auto-reconnect. */
    disconnect() {
        this._shouldReconnect = false;
        if (this.reconnectTimer !== null) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this._emit('disconnected', { intentional: true });
    }

    /**
     * Send data through the WebSocket.
     * @param {string|ArrayBuffer|Blob} data
     * @returns {boolean} true if sent, false if not connected
     */
    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(data);
            return true;
        }
        return false;
    }

    /**
     * Return current connection state string.
     * @returns {'connected'|'connecting'|'disconnected'|'reconnecting'}
     */
    getState() {
        if (!this.ws) {
            return this.attemptCount > 0 ? 'reconnecting' : 'disconnected';
        }
        switch (this.ws.readyState) {
            case WebSocket.CONNECTING: return this.attemptCount > 0 ? 'reconnecting' : 'connecting';
            case WebSocket.OPEN:       return 'connected';
            default:                   return 'disconnected';
        }
    }

    // ── Private methods ──────────────────────────────────────────────

    _connect() {
        if (this.ws) {
            this.ws.onopen = null;
            this.ws.onclose = null;
            this.ws.onerror = null;
            this.ws.onmessage = null;
            this.ws.close();
            this.ws = null;
        }

        try {
            this.ws = new WebSocket(this.url);
        } catch (e) {
            console.error('[WSReconnect] Failed to create WebSocket:', e);
            this._scheduleReconnect();
            return;
        }

        this.ws.onopen = () => {
            this.attemptCount = 0;
            this._emit('connected', {});
        };

        this.ws.onmessage = (event) => {
            this._emit('message', event);
        };

        this.ws.onerror = (event) => {
            // onerror is always followed by onclose, handle retry there
            console.warn('[WSReconnect] WebSocket error', event);
        };

        this.ws.onclose = (event) => {
            this.ws = null;
            if (this._shouldReconnect) {
                this._scheduleReconnect();
            } else {
                this._emit('disconnected', { code: event.code, reason: event.reason, intentional: false });
            }
        };
    }

    _scheduleReconnect() {
        const { maxAttempts } = this.options;
        if (maxAttempts > 0 && this.attemptCount >= maxAttempts) {
            console.warn('[WSReconnect] Max reconnect attempts reached:', maxAttempts);
            this._shouldReconnect = false;
            this._emit('disconnected', { maxAttemptsReached: true });
            return;
        }

        const delay = this._calcDelay();
        this.attemptCount += 1;
        this._emit('reconnecting', { attempt: this.attemptCount, delay });

        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            if (this._shouldReconnect) {
                this._connect();
            }
        }, delay);
    }

    _calcDelay() {
        const { initialDelay, maxDelay, multiplier, jitter } = this.options;
        // Exponential: initialDelay * multiplier^(attemptCount), capped at maxDelay
        const base = Math.min(initialDelay * Math.pow(multiplier, this.attemptCount), maxDelay);
        // Jitter: ± jitter * base
        const jitterAmount = base * jitter * (Math.random() * 2 - 1);
        return Math.max(0, Math.round(base + jitterAmount));
    }

    _emit(event, data) {
        const handlers = this._handlers[event];
        if (handlers) {
            handlers.forEach((h) => {
                try { h(data); } catch (e) { console.error('[WSReconnect] Handler error:', e); }
            });
        }
    }
}

// Export for module environments (ignored in plain browser scripts)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WSReconnect;
}
