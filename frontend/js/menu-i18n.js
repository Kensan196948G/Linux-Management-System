/**
 * メニュー国際化（i18n）ユーティリティ
 *
 * サイドメニューの多言語対応を提供します。
 * 現在は日本語のみ対応。
 */

class MenuI18n {
    constructor() {
        this.currentLocale = 'ja';
        this.translations = null;
    }

    /**
     * 翻訳データを読み込む
     */
    async loadTranslations(locale = 'ja') {
        try {
            const response = await fetch(`/locales/menu-${locale}.json`);
            if (!response.ok) {
                throw new Error(`Failed to load translations: ${response.status}`);
            }
            const data = await response.json();
            this.translations = data.menu_translation;
            this.currentLocale = locale;
            return true;
        } catch (error) {
            console.error('Failed to load menu translations:', error);
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
     * 利用可能なロケール一覧を取得
     * @returns {Array<string>}
     */
    getAvailableLocales() {
        return ['ja']; // 将来的に 'en', 'zh' などを追加可能
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
    const loaded = await menuI18n.loadTranslations('ja');
    if (loaded) {
        menuI18n.translateMenuDOM();
    }
});
