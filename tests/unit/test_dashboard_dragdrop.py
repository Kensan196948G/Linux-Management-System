"""
ダッシュボード ドラッグ&ドロップ機能テスト

テスト対象: frontend/dev/dashboard.html のSortable.js統合
"""
from pathlib import Path

import pytest

DASHBOARD_FILE = Path(__file__).parent.parent.parent / "frontend" / "dev" / "dashboard.html"


class TestDashboardDragDrop:
    """ダッシュボードドラッグ&ドロップのDOM/JSテスト"""

    @pytest.fixture(autouse=True)
    def load_html(self):
        self.content = DASHBOARD_FILE.read_text(encoding="utf-8")

    def test_sortablejs_cdn_loaded(self):
        """TC001: SortableJS CDN が読み込まれること"""
        assert "sortablejs" in self.content.lower()
        assert "Sortable.min.js" in self.content

    def test_widgets_grid_id(self):
        """TC002: widgets-grid IDが存在すること"""
        assert 'id="widgets-grid"' in self.content

    def test_health_score_widget_id(self):
        """TC003: ヘルススコアカードにdata-widget-idがあること"""
        assert 'data-widget-id="health-score"' in self.content

    def test_cpu_ring_widget_id(self):
        """TC004: CPUリングカードにdata-widget-idがあること"""
        assert 'data-widget-id="cpu-ring"' in self.content

    def test_cpu_line_widget_id(self):
        """TC005: CPU折れ線カードにdata-widget-idがあること"""
        assert 'data-widget-id="cpu-line"' in self.content

    def test_mem_bar_widget_id(self):
        """TC006: メモリバーカードにdata-widget-idがあること"""
        assert 'data-widget-id="mem-bar"' in self.content

    def test_net_line_widget_id(self):
        """TC007: ネットワーク折れ線カードにdata-widget-idがあること"""
        assert 'data-widget-id="net-line"' in self.content

    def test_error_log_widget_id(self):
        """TC008: エラーログカードにdata-widget-idがあること"""
        assert 'data-widget-id="error-log"' in self.content

    def test_nic_stats_widget_id(self):
        """TC009: NIC統計カードにdata-widget-idがあること"""
        assert 'data-widget-id="nic-stats"' in self.content

    def test_drag_handles_present(self):
        """TC010: ドラッグハンドルが複数存在すること"""
        count = self.content.count('class="drag-handle"')
        assert count >= 6, f"Expected >= 6 drag handles, got {count}"

    def test_sortable_ghost_class(self):
        """TC011: sortable-ghost CSSクラスが定義されること"""
        assert "sortable-ghost" in self.content

    def test_sortable_chosen_class(self):
        """TC012: sortable-chosen CSSクラスが定義されること"""
        assert "sortable-chosen" in self.content

    def test_init_drag_drop_function(self):
        """TC013: initDragDrop() 関数が存在すること"""
        assert "function initDragDrop()" in self.content

    def test_save_widget_order_function(self):
        """TC014: saveWidgetOrder() 関数が存在すること"""
        assert "function saveWidgetOrder()" in self.content

    def test_restore_widget_order_function(self):
        """TC015: restoreWidgetOrder() 関数が存在すること"""
        assert "function restoreWidgetOrder()" in self.content

    def test_reset_widget_layout_function(self):
        """TC016: resetWidgetLayout() 関数が存在すること"""
        assert "function resetWidgetLayout()" in self.content

    def test_localstorage_key(self):
        """TC017: localStorageキーが定義されること"""
        assert "lms_dashboard_widget_order" in self.content

    def test_reset_button_present(self):
        """TC018: 並び順リセットボタンが存在すること"""
        assert "resetWidgetLayout()" in self.content
        assert "並び順リセット" in self.content

    def test_drag_handle_handle_option(self):
        """TC019: Sortableのhandle指定にdrag-handleクラスが使われること"""
        assert "handle: '.drag-handle'" in self.content

    def test_prod_copy_consistent(self):
        """TC020: prod版も同じ内容であること"""
        prod = Path(__file__).parent.parent.parent / "frontend" / "prod" / "dashboard.html"
        if prod.exists():
            prod_content = prod.read_text(encoding="utf-8")
            assert 'data-widget-id="health-score"' in prod_content
            assert "Sortable.min.js" in prod_content

    def test_domcontentloaded_init(self):
        """TC021: DOMContentLoaded後にinitDragDropが呼ばれること"""
        assert "DOMContentLoaded" in self.content
        assert "initDragDrop" in self.content

    def test_animation_value(self):
        """TC022: Sortableのanimation設定があること"""
        assert "animation: 200" in self.content
