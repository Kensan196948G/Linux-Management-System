/**
 * メニュー国際化（i18n）ユーティリティ
 *
 * サイドメニューの多言語対応を提供します。
 * 対応言語: 日本語 (ja) / English (en)
 */

// ページタイトル翻訳マップ (ja/en)
const PAGE_TITLES = {
    ja: {
        dashboard: 'ダッシュボード',
        services: 'サービス管理',
        processes: '実行中プロセス',
        users: 'ユーザー・グループ管理',
        cron: 'Cron ジョブ管理',
        logs: 'システムログ',
        journal: 'Journal ログ',
        logsearch: 'ログ全文検索',
        packages: 'パッケージ管理',
        filesystem: 'ファイルシステム',
        disk: 'ディスク使用状況',
        partitions: 'パーティション管理',
        quotas: 'ディスククォータ',
        backup: 'バックアップ・リストア',
        sessions: 'ユーザーセッション管理',
        alerts: 'リソースアラート管理',
        audit: '監査ログ',
        approval: '承認ワークフロー',
        notifications: '通知設定',
        network: 'ネットワーク設定',
        firewall: 'ファイアウォール管理',
        netstat: 'ネットワーク統計',
        routing: 'ルーティング・ゲートウェイ',
        bandwidth: '帯域幅モニタリング',
        ssh: 'SSH サーバー設定',
        sshkeys: 'SSH 鍵管理',
        apache: 'Apache Web サーバー',
        nginx: 'Nginx Web サーバー',
        mysql: 'MySQL / MariaDB 監視',
        postgresql: 'PostgreSQL 監視',
        postfix: 'Postfix メールサーバー',
        bind: 'BIND DNS サーバー',
        ftp: 'FTP サーバー管理',
        squid: 'Squid プロキシ管理',
        dhcp: 'DHCP サーバー管理',
        dbmonitor: 'データベースモニター',
        hardware: 'ハードウェア情報',
        sensors: 'ハードウェアセンサー',
        smart: 'SMART ドライブ状態',
        system_time: 'システム時刻設定',
        sysconfig: 'システム設定',
        filemanager: 'ファイルマネージャー',
        security: 'セキュリティ設定',
        servers: 'システムサーバー',
        modules: 'モジュール管理',
        settings: '設定',
        bootup: '起動・シャットダウン管理',
    },
    en: {
        dashboard: 'Dashboard',
        services: 'System Services',
        processes: 'Running Processes',
        users: 'Users & Groups',
        cron: 'Cron Jobs',
        logs: 'System Logs',
        journal: 'Journal Logs',
        logsearch: 'Log Search',
        packages: 'Package Updates',
        filesystem: 'Filesystem',
        disk: 'Disk Usage',
        partitions: 'Disk Partitions',
        quotas: 'Disk Quotas',
        backup: 'Backup & Restore',
        sessions: 'User Sessions',
        alerts: 'Resource Alerts',
        audit: 'Audit Log',
        approval: 'Approval Workflow',
        notifications: 'Notifications',
        network: 'Network Configuration',
        firewall: 'Linux Firewall',
        netstat: 'Network Statistics',
        routing: 'Routing & Gateways',
        bandwidth: 'Bandwidth Monitoring',
        ssh: 'SSH Server',
        sshkeys: 'SSH Keys',
        apache: 'Apache Webserver',
        nginx: 'Nginx',
        mysql: 'MySQL / MariaDB',
        postgresql: 'PostgreSQL',
        postfix: 'Postfix Mail',
        bind: 'BIND DNS',
        ftp: 'FTP Server',
        squid: 'Squid Proxy',
        dhcp: 'DHCP Server',
        dbmonitor: 'Database Monitor',
        hardware: 'Hardware Info',
        sensors: 'Sensors',
        smart: 'SMART Drive Status',
        system_time: 'System Time',
        sysconfig: 'System Config',
        filemanager: 'File Manager',
        security: 'Security',
        servers: 'System Servers',
        modules: 'Modules',
        settings: 'Settings',
        bootup: 'Bootup & Shutdown',
    }
};

// UI汎用テキスト翻訳 (ja/en)
const UI_TEXT = {
    ja: {
        logout: 'ログアウト',
        user_label: 'ユーザー',
        role_label: 'ロール',
        pending_badge: '承認待ち',
        implemented: '実装済み',
        planned: '計画中',
        prohibited: '禁止',
        lang_switch: 'English',
        lang_icon: '🇺🇸',
    },
    en: {
        logout: 'Logout',
        user_label: 'User',
        role_label: 'Role',
        pending_badge: 'Pending',
        implemented: 'Implemented',
        planned: 'Planned',
        prohibited: 'Prohibited',
        lang_switch: '日本語',
        lang_icon: '🇯🇵',
    }
};

class MenuI18n {
    constructor() {
        this.currentLocale = localStorage.getItem('lms_locale') || 'ja';
        this.translations = null;
    }

    /** 現在のロケールのUIテキストを取得 */
    ui(key) {
        return (UI_TEXT[this.currentLocale] || UI_TEXT.ja)[key] || key;
    }

    /** ページタイトル翻訳 */
    pageTitle(page) {
        return (PAGE_TITLES[this.currentLocale] || PAGE_TITLES.ja)[page] || page;
    }

    /** ロケールを切り替えてページをリロード */
    switchLocale() {
        const next = this.currentLocale === 'ja' ? 'en' : 'ja';
        localStorage.setItem('lms_locale', next);
        window.location.reload();
    }

    /** 利用可能なロケール一覧 */
    getAvailableLocales() {
        return ['ja', 'en'];
    }

    /** 現在のロケール */
    getCurrentLocale() {
        return this.currentLocale;
    }

    /**
     * 翻訳データを読み込む
     */
    async loadTranslations(locale = null) {
        const targetLocale = locale || this.currentLocale;
        try {
            const response = await fetch(`/locales/menu-${targetLocale}.json`);
            if (!response.ok) {
                throw new Error(`Failed to load translations: ${response.status}`);
            }
            const data = await response.json();
            this.translations = data.menu_translation;
            this.currentLocale = targetLocale;
            return true;
        } catch (error) {
            console.error('Failed to load menu translations:', error);
            // フォールバック: jaをロード
            if (targetLocale !== 'ja') {
                return this.loadTranslations('ja');
            }
            return false;
        }
    }

    /**
     * メニュー項目を翻訳する
     * @param {string} key - 翻訳キー（英語の項目名）
     * @param {string} category - カテゴリ（オプション）
     * @returns {string} - 翻訳されたテキスト（見つからない場合は元のkey）
     */
    translate(key, category = null) {
        if (!this.translations) {
            return key;
        }

        // カテゴリ指定がある場合、submenu_items から検索
        if (category && this.translations.submenu_items[category]) {
            const translation = this.translations.submenu_items[category][key];
            if (translation) {
                return translation;
            }
        }

        // トップレベルメニューから検索
        if (this.translations.top_level_menu[key]) {
            return this.translations.top_level_menu[key];
        }

        // カテゴリから検索
        if (this.translations.categories[key]) {
            return this.translations.categories[key];
        }

        // 全submenu_itemsから検索
        for (const cat in this.translations.submenu_items) {
            if (this.translations.submenu_items[cat][key]) {
                return this.translations.submenu_items[cat][key];
            }
        }

        // ステータスバッジから検索
        if (this.translations.status_badges[key]) {
            return this.translations.status_badges[key];
        }

        // 見つからない場合は元のキーを返す
        console.warn(`Translation not found for key: "${key}"`);
        return key;
    }

    /**
     * DOMのメニュー項目を一括翻訳する
     */
    translateMenuDOM() {
        if (!this.translations) {
            console.error('Translations not loaded');
            return;
        }

        // トップレベルメニューの翻訳
        document.querySelectorAll('.menu-item span:last-child').forEach(element => {
            const originalText = element.textContent.trim();
            const translated = this.translate(originalText);
            if (translated !== originalText) {
                element.textContent = translated;
            }
        });

        // カテゴリタイトルの翻訳
        document.querySelectorAll('.accordion-title span:last-child').forEach(element => {
            const originalText = element.textContent.trim();
            const translated = this.translate(originalText);
            if (translated !== originalText) {
                element.textContent = translated;
            }
        });

        // サブメニュー項目の翻訳
        document.querySelectorAll('.submenu-item-name').forEach(element => {
            const originalText = element.textContent.trim();
            const translated = this.translate(originalText);
            if (translated !== originalText) {
                element.textContent = translated;
            }
        });

        // ステータスバッジの翻訳
        document.querySelectorAll('.submenu-item-badge').forEach(element => {
            const originalText = element.textContent.trim();
            const translated = this.translate(originalText);
            if (translated !== originalText) {
                element.textContent = translated;
            }
        });

        // サイドバーフッターの翻訳
        if (this.translations.sidebar && this.translations.sidebar.footer) {
            const footer = this.translations.sidebar.footer;

            // ユーザー・ロールラベルの翻訳
            const sidebarFooter = document.querySelector('.sidebar-footer');
            if (sidebarFooter) {
                sidebarFooter.innerHTML = sidebarFooter.innerHTML
                    .replace(/ユーザー:/g, `${footer.user_label}:`)
                    .replace(/ロール:/g, `${footer.role_label}:`);
            }

            // ログアウトボタンの翻訳
            const logoutButton = document.querySelector('.sidebar-footer button');
            if (logoutButton && footer.logout_button) {
                logoutButton.textContent = footer.logout_button;
            }
        }

        console.log('Menu translation completed');
    }

    /**
     * 特定のカテゴリのサブメニューアイテム一覧を取得
     * @param {string} category - カテゴリキー
     * @returns {Object} - キーと翻訳のマップ
     */
    getSubmenuItems(category) {
        if (!this.translations || !this.translations.submenu_items[category]) {
            return {};
        }
        return this.translations.submenu_items[category];
    }

    /**
     * サイドバーフッターに言語切り替えボタンを挿入
     */
    injectLangSwitcher() {
        const footer = document.querySelector('.sidebar-footer');
        if (!footer || document.getElementById('lang-switcher-btn')) return;

        const isEn = this.currentLocale === 'en';
        const btn = document.createElement('button');
        btn.id = 'lang-switcher-btn';
        btn.title = isEn ? '日本語に切り替え' : 'Switch to English';
        btn.style.cssText = [
            'display:flex', 'align-items:center', 'gap:4px',
            'padding:4px 10px', 'margin:6px auto 0', 'border-radius:16px',
            'border:1px solid rgba(255,255,255,0.3)', 'background:rgba(255,255,255,0.1)',
            'color:inherit', 'cursor:pointer', 'font-size:11px', 'font-weight:600',
            'width:calc(100% - 16px)', 'justify-content:center',
        ].join(';');
        btn.innerHTML = `<span>${isEn ? '🇯🇵' : '🇺🇸'}</span><span>${isEn ? '日本語' : 'English'}</span>`;
        btn.addEventListener('click', () => this.switchLocale());
        footer.appendChild(btn);
    }

    /**
     * 利用可能なロケール一覧を取得
     * @returns {Array<string>}
     */
    getAvailableLocales() {
        return ['ja', 'en'];
    }

    /**
     * 現在のロケールを取得
     * @returns {string}
     */
    getCurrentLocale() {
        return this.currentLocale;
    }
}

// グローバルインスタンスを作成
const menuI18n = new MenuI18n();

// DOMContentLoaded時に自動的に翻訳を適用
document.addEventListener('DOMContentLoaded', async () => {
    const loaded = await menuI18n.loadTranslations(menuI18n.currentLocale);
    if (loaded) {
        menuI18n.translateMenuDOM();
    }
    // 言語切り替えボタンをサイドバーフッターに追加
    menuI18n.injectLangSwitcher();
});
