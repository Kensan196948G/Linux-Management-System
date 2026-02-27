/**
 * env-config.js - 実行環境設定・動的URL管理
 *
 * /api/info エンドポイントからサーバー情報を取得し、
 * アクセスURLをコンソールに表示する。
 * 他のスクリプトは window._serverInfo でアクセス可能。
 */

(function () {
    'use strict';

    // サーバー情報キャッシュ
    window._serverInfo = null;

    /**
     * サーバー情報を取得
     * @returns {Promise<Object>} サーバー情報
     */
    async function fetchServerInfo() {
        if (window._serverInfo) return window._serverInfo;
        try {
            const resp = await fetch('/api/info', { cache: 'no-store' });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            window._serverInfo = data;
            return data;
        } catch (e) {
            // フォールバック: window.location から生成
            const origin = window.location.origin;
            window._serverInfo = {
                environment: 'unknown',
                urls: { api_http: origin + '/api', api_https: origin + '/api' },
                detected_ip: window.location.hostname,
                ports: {
                    http: parseInt(window.location.port) || 80,
                    https: parseInt(window.location.port) || 443
                }
            };
            return window._serverInfo;
        }
    }

    /**
     * API ベースURL を返す（非同期）
     * @returns {Promise<string>}
     */
    window.getApiBaseUrl = async function () {
        const info = await fetchServerInfo();
        // api_base があれば優先（本番/開発で最適なプロトコルを返す）
        if (info.urls && info.urls.api_base) return info.urls.api_base;
        const isHttps = window.location.protocol === 'https:';
        return isHttps ? info.urls.api_https : info.urls.api_http;
    };

    // ページ読み込み時にサーバー情報を取得してコンソールに表示
    document.addEventListener('DOMContentLoaded', async function () {
        try {
            const info = await fetchServerInfo();
            console.group('🖥️ Linux Management System');
            console.log('環境:', info.environment);
            console.log('検出IP:', info.detected_ip);
            console.log('HTTP URL:', info.urls.http);
            console.log('HTTPS URL:', info.urls.https);
            if (info.urls.docs) {
                console.log('API Docs:', info.urls.docs);
            }
            console.groupEnd();

            // 環境バッジを表示（開発環境: 黄、本番環境: 赤）
            const isProd = info.environment === 'production';
            const envLabel = isProd ? '【本番】' : '【開発】';
            const envColor = isProd ? '#dc2626' : '#f59e0b';
            const envTextColor = isProd ? '#fff' : '#1c1917';

            // document.title を環境に合わせて更新
            if (document.title) {
                document.title = document.title
                    .replace(/【開発】|【本番】/g, envLabel);
            }

            // ページ内の .env-badge 要素のテキストを動的更新
            document.querySelectorAll('.env-badge').forEach(function (el) {
                el.textContent = envLabel;
                el.style.background = envColor;
                el.style.color = envTextColor;
                el.classList.toggle('dev', !isProd);
                el.classList.toggle('prod', isProd);
            });

            // 右下固定バッジ
            if (info.environment === 'development' || info.environment === 'production') {
                const badge = document.createElement('div');
                badge.id = 'env-badge';
                badge.style.cssText = [
                    'position:fixed', 'bottom:8px', 'right:8px', 'z-index:9999',
                    `background:${envColor}`,
                    `color:${envTextColor}`,
                    'font-size:10px',
                    'font-weight:700', 'padding:3px 8px', 'border-radius:4px',
                    'opacity:0.85', 'pointer-events:none', 'font-family:monospace'
                ].join(';');
                const label = isProd ? 'PROD' : 'DEV';
                badge.textContent = `${label} ${info.detected_ip}:${info.ports.http}`;
                document.body.appendChild(badge);
            }
        } catch (_) {
            // サイレントフェール
        }
    });
})();
