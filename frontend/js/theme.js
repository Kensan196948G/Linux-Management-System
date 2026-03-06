/**
 * theme.js - ダーク/ライトモード切り替え
 * localStorage の 'lms_theme' キーで保存 ('dark' | 'light')
 */
(function() {
    var STORAGE_KEY = 'lms_theme';

    function getTheme() {
        return localStorage.getItem(STORAGE_KEY) ||
               (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    }

    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        var btn = document.getElementById('theme-toggle-btn');
        if (btn) {
            btn.textContent = theme === 'dark' ? '☀️ ライト' : '🌙 ダーク';
            btn.title = theme === 'dark' ? 'ライトモードに切り替え' : 'ダークモードに切り替え';
        }
    }

    function toggleTheme() {
        var current = getTheme();
        var next = current === 'dark' ? 'light' : 'dark';
        localStorage.setItem(STORAGE_KEY, next);
        applyTheme(next);
    }

    // ページロード時に即適用（FLASHを防ぐ）
    applyTheme(getTheme());

    // グローバルに公開
    window.toggleTheme = toggleTheme;
    window.getTheme = getTheme;

    // DOMContentLoaded 後にボタンテキストを更新
    document.addEventListener('DOMContentLoaded', function() {
        applyTheme(getTheme());
    });
})();
