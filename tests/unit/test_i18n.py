"""
i18n 多言語化テスト

テスト対象: frontend/locales/menu-ja.json, menu-en.json
"""
import json
from pathlib import Path

import pytest

LOCALES_DIR = Path(__file__).parent.parent.parent / "frontend" / "locales"
JA_FILE = LOCALES_DIR / "menu-ja.json"
EN_FILE = LOCALES_DIR / "menu-en.json"


class TestLocaleFiles:
    """ロケールファイルの構造テスト"""

    def test_ja_file_exists(self):
        """TC001: menu-ja.json が存在すること"""
        assert JA_FILE.exists()

    def test_en_file_exists(self):
        """TC002: menu-en.json が存在すること"""
        assert EN_FILE.exists()

    def test_ja_valid_json(self):
        """TC003: menu-ja.json が有効な JSON であること"""
        data = json.loads(JA_FILE.read_text(encoding="utf-8"))
        assert "menu_translation" in data

    def test_en_valid_json(self):
        """TC004: menu-en.json が有効な JSON であること"""
        data = json.loads(EN_FILE.read_text(encoding="utf-8"))
        assert "menu_translation" in data

    def test_ja_has_required_keys(self):
        """TC005: menu-ja.json に必須キーが存在すること"""
        data = json.loads(JA_FILE.read_text(encoding="utf-8"))
        mt = data["menu_translation"]
        assert "top_level_menu" in mt
        assert "categories" in mt
        assert "submenu_items" in mt
        assert "status_badges" in mt
        assert "sidebar" in mt

    def test_en_has_required_keys(self):
        """TC006: menu-en.json に必須キーが存在すること"""
        data = json.loads(EN_FILE.read_text(encoding="utf-8"))
        mt = data["menu_translation"]
        assert "top_level_menu" in mt
        assert "categories" in mt
        assert "submenu_items" in mt
        assert "sidebar" in mt

    def test_en_has_ui_section(self):
        """TC007: menu-en.json に ui セクションが存在すること"""
        data = json.loads(EN_FILE.read_text(encoding="utf-8"))
        assert "ui" in data["menu_translation"]

    def test_both_have_same_categories(self):
        """TC008: ja/en で同じカテゴリ構造を持つこと"""
        ja = json.loads(JA_FILE.read_text(encoding="utf-8"))["menu_translation"]
        en = json.loads(EN_FILE.read_text(encoding="utf-8"))["menu_translation"]
        for key in ja["categories"]:
            assert key in en["categories"], f"Missing category in en: {key}"

    def test_both_have_same_submenu_categories(self):
        """TC009: ja/en でサブメニューカテゴリが一致すること"""
        ja = json.loads(JA_FILE.read_text(encoding="utf-8"))["menu_translation"]
        en = json.loads(EN_FILE.read_text(encoding="utf-8"))["menu_translation"]
        for cat in ja["submenu_items"]:
            assert cat in en["submenu_items"], f"Missing submenu category in en: {cat}"

    def test_both_have_same_submenu_items(self):
        """TC010: ja/en でサブメニュー項目が一致すること"""
        ja = json.loads(JA_FILE.read_text(encoding="utf-8"))["menu_translation"]
        en = json.loads(EN_FILE.read_text(encoding="utf-8"))["menu_translation"]
        for cat, items in ja["submenu_items"].items():
            for key in items:
                assert key in en["submenu_items"].get(cat, {}), \
                    f"Missing item '{key}' in en.submenu_items.{cat}"

    def test_en_status_badges_mapped(self):
        """TC011: en の status_badges が日本語→英語変換を持つこと"""
        en = json.loads(EN_FILE.read_text(encoding="utf-8"))["menu_translation"]
        badges = en["status_badges"]
        assert badges.get("実装済み") == "Implemented"
        assert badges.get("計画中") == "Planned"
        assert badges.get("禁止") == "Prohibited"

    def test_en_sidebar_footer_english(self):
        """TC012: en のサイドバーフッターが英語であること"""
        en = json.loads(EN_FILE.read_text(encoding="utf-8"))["menu_translation"]
        footer = en["sidebar"]["footer"]
        assert footer["logout_button"] == "Logout"
        assert footer["user_label"] == "User"
        assert footer["role_label"] == "Role"

    def test_ja_sidebar_footer_japanese(self):
        """TC013: ja のサイドバーフッターが日本語であること"""
        ja = json.loads(JA_FILE.read_text(encoding="utf-8"))["menu_translation"]
        footer = ja["sidebar"]["footer"]
        assert footer["logout_button"] == "ログアウト"

    def test_en_top_level_menu(self):
        """TC014: en のトップレベルメニューが英語であること"""
        en = json.loads(EN_FILE.read_text(encoding="utf-8"))["menu_translation"]
        tl = en["top_level_menu"]
        assert tl["Dashboard"] == "Dashboard"
        assert tl["Services"] == "Services"

    def test_en_networking_items(self):
        """TC015: en の networking サブメニューが正しいこと"""
        en = json.loads(EN_FILE.read_text(encoding="utf-8"))["menu_translation"]
        net = en["submenu_items"]["networking"]
        assert net["Linux Firewall"] == "Linux Firewall"
        assert net["Network Configuration"] == "Network Configuration"
        assert net["Bandwidth Monitoring"] == "Bandwidth Monitoring"

    def test_en_servers_items(self):
        """TC016: en の servers サブメニューが正しいこと"""
        en = json.loads(EN_FILE.read_text(encoding="utf-8"))["menu_translation"]
        sv = en["submenu_items"]["servers"]
        assert "Apache Webserver" in sv
        assert "MySQL / MariaDB" in sv
        assert "DHCP Server" in sv

    def test_en_hardware_items(self):
        """TC017: en の hardware サブメニューが正しいこと"""
        en = json.loads(EN_FILE.read_text(encoding="utf-8"))["menu_translation"]
        hw = en["submenu_items"]["hardware"]
        assert "SMART Drive Status" in hw
        assert "System Time" in hw

    def test_en_ui_section_has_all_pages(self):
        """TC018: en の ui セクションに全ページが含まれること"""
        en = json.loads(EN_FILE.read_text(encoding="utf-8"))["menu_translation"]
        ui = en["ui"]
        required_pages = [
            "dashboard", "services", "processes", "users_groups", "cron_jobs",
            "logs", "firewall", "network", "ssh", "apache", "mysql",
            "postgresql", "backup", "alerts", "notifications", "approval_workflow"
        ]
        for page in required_pages:
            assert page in ui, f"Missing ui key: {page}"

    def test_no_empty_values_in_en(self):
        """TC019: en の翻訳値に空文字列がないこと"""
        en = json.loads(EN_FILE.read_text(encoding="utf-8"))["menu_translation"]
        for key, val in en["top_level_menu"].items():
            assert val.strip(), f"Empty value for top_level_menu[{key}]"
        for cat, items in en["submenu_items"].items():
            for key, val in items.items():
                assert val.strip(), f"Empty value for submenu_items[{cat}][{key}]"

    def test_menu_i18n_js_has_switchlocale(self):
        """TC020: menu-i18n.js に switchLocale メソッドが存在すること"""
        js_file = Path(__file__).parent.parent.parent / "frontend" / "js" / "menu-i18n.js"
        content = js_file.read_text(encoding="utf-8")
        assert "switchLocale" in content
        assert "injectLangSwitcher" in content
        assert "localStorage.getItem" in content
        assert "lms_locale" in content
