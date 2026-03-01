"""
Hardware API エンドポイントのユニットテスト

backend/api/routes/hardware.py のカバレッジ向上
"""

import json
from unittest.mock import MagicMock, mock_open, patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


class TestGetDisks:
    """GET /api/hardware/disks テスト"""

    def test_get_disks_success(self, test_client, auth_headers):
        """正常系: ディスク一覧取得"""
        mock_result = {
            "status": "success",
            "output": json.dumps({
                "status": "success",
                "disks": [{"name": "sda", "size": "500G", "type": "disk"}],
                "timestamp": "2026-03-01T00:00:00Z",
            }),
        }
        with patch("backend.api.routes.hardware.sudo_wrapper") as mock_sw:
            mock_sw.get_hardware_disks.return_value = mock_result
            response = test_client.get("/api/hardware/disks", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["disks"]) == 1

    def test_get_disks_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.get("/api/hardware/disks")
        assert response.status_code == 403

    def test_get_disks_error_status(self, test_client, auth_headers):
        """sudo_wrapper がエラーを返すケース"""
        mock_result = {
            "status": "error",
            "message": "lsblk not found",
        }
        with patch("backend.api.routes.hardware.sudo_wrapper") as mock_sw:
            mock_sw.get_hardware_disks.return_value = mock_result
            response = test_client.get("/api/hardware/disks", headers=auth_headers)

        assert response.status_code == 503

    def test_get_disks_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時"""
        with patch("backend.api.routes.hardware.sudo_wrapper") as mock_sw:
            mock_sw.get_hardware_disks.side_effect = SudoWrapperError("Wrapper not found")
            response = test_client.get("/api/hardware/disks", headers=auth_headers)

        assert response.status_code == 500
        assert "Wrapper not found" in response.json()["message"]


class TestGetDiskUsage:
    """GET /api/hardware/disk_usage テスト"""

    def test_get_disk_usage_success(self, test_client, auth_headers):
        """正常系: ディスク使用量取得"""
        mock_result = {
            "status": "success",
            "output": json.dumps({
                "status": "success",
                "usage": [
                    {
                        "filesystem": "/dev/sda1",
                        "size_kb": 500000000,
                        "used_kb": 250000000,
                        "avail_kb": 250000000,
                        "use_percent": 50,
                        "mountpoint": "/",
                    }
                ],
                "timestamp": "2026-03-01T00:00:00Z",
            }),
        }
        with patch("backend.api.routes.hardware.sudo_wrapper") as mock_sw:
            mock_sw.get_hardware_disk_usage.return_value = mock_result
            response = test_client.get("/api/hardware/disk_usage", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["usage"]) == 1

    def test_get_disk_usage_error_status(self, test_client, auth_headers):
        """エラーステータスのケース"""
        mock_result = {"status": "error", "message": "df command failed"}
        with patch("backend.api.routes.hardware.sudo_wrapper") as mock_sw:
            mock_sw.get_hardware_disk_usage.return_value = mock_result
            response = test_client.get("/api/hardware/disk_usage", headers=auth_headers)

        assert response.status_code == 503

    def test_get_disk_usage_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時"""
        with patch("backend.api.routes.hardware.sudo_wrapper") as mock_sw:
            mock_sw.get_hardware_disk_usage.side_effect = SudoWrapperError("Permission denied")
            response = test_client.get("/api/hardware/disk_usage", headers=auth_headers)

        assert response.status_code == 500


class TestGetSmart:
    """GET /api/hardware/smart テスト"""

    def test_get_smart_success(self, test_client, auth_headers):
        """正常系: SMART情報取得"""
        mock_result = {
            "status": "success",
            "output": json.dumps({
                "status": "success",
                "device": "/dev/sda",
                "smart": {"health": "PASSED", "temperature": 35},
                "timestamp": "2026-03-01T00:00:00Z",
            }),
        }
        with patch("backend.api.routes.hardware.sudo_wrapper") as mock_sw:
            mock_sw.get_hardware_smart.return_value = mock_result
            response = test_client.get(
                "/api/hardware/smart?device=/dev/sda", headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["device"] == "/dev/sda"

    def test_get_smart_invalid_device_path(self, test_client, auth_headers):
        """不正なデバイスパス（バリデーション失敗）"""
        response = test_client.get(
            "/api/hardware/smart?device=/etc/passwd", headers=auth_headers
        )
        assert response.status_code == 400
        assert "Invalid device path" in response.json()["message"]

    def test_get_smart_injection_attempt(self, test_client, auth_headers):
        """パスインジェクション攻撃"""
        response = test_client.get(
            "/api/hardware/smart?device=/dev/sda;rm+-rf+/", headers=auth_headers
        )
        assert response.status_code == 400

    def test_get_smart_nvme_device(self, test_client, auth_headers):
        """NVMe デバイスパス"""
        mock_result = {
            "status": "success",
            "output": json.dumps({
                "status": "success",
                "device": "/dev/nvme0n1",
                "smart": {"health": "PASSED"},
                "timestamp": "2026-03-01T00:00:00Z",
            }),
        }
        with patch("backend.api.routes.hardware.sudo_wrapper") as mock_sw:
            mock_sw.get_hardware_smart.return_value = mock_result
            response = test_client.get(
                "/api/hardware/smart?device=/dev/nvme0n1", headers=auth_headers
            )

        assert response.status_code == 200

    def test_get_smart_error_status(self, test_client, auth_headers):
        """SMART取得エラー"""
        mock_result = {"status": "error", "message": "smartctl not found"}
        with patch("backend.api.routes.hardware.sudo_wrapper") as mock_sw:
            mock_sw.get_hardware_smart.return_value = mock_result
            response = test_client.get(
                "/api/hardware/smart?device=/dev/sda", headers=auth_headers
            )

        assert response.status_code == 503

    def test_get_smart_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時"""
        with patch("backend.api.routes.hardware.sudo_wrapper") as mock_sw:
            mock_sw.get_hardware_smart.side_effect = SudoWrapperError("smartctl failed")
            response = test_client.get(
                "/api/hardware/smart?device=/dev/sda", headers=auth_headers
            )

        assert response.status_code == 500

    def test_get_smart_value_error(self, test_client, auth_headers):
        """ValueError 発生時"""
        with patch("backend.api.routes.hardware.sudo_wrapper") as mock_sw:
            mock_sw.get_hardware_smart.side_effect = ValueError("Invalid device")
            response = test_client.get(
                "/api/hardware/smart?device=/dev/sda", headers=auth_headers
            )

        assert response.status_code == 400


class TestGetSensors:
    """GET /api/hardware/sensors テスト"""

    def test_get_sensors_success(self, test_client, auth_headers):
        """正常系: センサー情報取得"""
        mock_result = {
            "status": "success",
            "output": json.dumps({
                "status": "success",
                "source": "lm-sensors",
                "sensors": {"coretemp": {"Core 0": "+45.0 C"}},
                "timestamp": "2026-03-01T00:00:00Z",
            }),
        }
        with patch("backend.api.routes.hardware.sudo_wrapper") as mock_sw:
            mock_sw.get_hardware_sensors.return_value = mock_result
            response = test_client.get("/api/hardware/sensors", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_sensors_error_status(self, test_client, auth_headers):
        """エラーステータスのケース"""
        mock_result = {"status": "error", "message": "sensors not available"}
        with patch("backend.api.routes.hardware.sudo_wrapper") as mock_sw:
            mock_sw.get_hardware_sensors.return_value = mock_result
            response = test_client.get("/api/hardware/sensors", headers=auth_headers)

        assert response.status_code == 503

    def test_get_sensors_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時"""
        with patch("backend.api.routes.hardware.sudo_wrapper") as mock_sw:
            mock_sw.get_hardware_sensors.side_effect = SudoWrapperError("sensors failed")
            response = test_client.get("/api/hardware/sensors", headers=auth_headers)

        assert response.status_code == 500


class TestGetMemory:
    """GET /api/hardware/memory テスト"""

    def test_get_memory_success(self, test_client, auth_headers):
        """正常系: メモリ情報取得"""
        mock_result = {
            "status": "success",
            "output": json.dumps({
                "status": "success",
                "memory": {
                    "total_kb": 16000000,
                    "free_kb": 8000000,
                    "available_kb": 12000000,
                    "buffers_kb": 500000,
                    "cached_kb": 3000000,
                    "swap_total_kb": 4000000,
                    "swap_free_kb": 4000000,
                },
                "timestamp": "2026-03-01T00:00:00Z",
            }),
        }
        with patch("backend.api.routes.hardware.sudo_wrapper") as mock_sw:
            mock_sw.get_hardware_memory.return_value = mock_result
            response = test_client.get("/api/hardware/memory", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["memory"]["total_kb"] == 16000000

    def test_get_memory_error_status(self, test_client, auth_headers):
        """エラーステータスのケース"""
        mock_result = {"status": "error", "message": "meminfo unavailable"}
        with patch("backend.api.routes.hardware.sudo_wrapper") as mock_sw:
            mock_sw.get_hardware_memory.return_value = mock_result
            response = test_client.get("/api/hardware/memory", headers=auth_headers)

        assert response.status_code == 503

    def test_get_memory_wrapper_error_with_proc_fallback(self, test_client, auth_headers):
        """SudoWrapperError 発生時 → /proc/meminfo フォールバック"""
        meminfo_content = (
            "MemTotal:       16000000 kB\n"
            "MemFree:         8000000 kB\n"
            "MemAvailable:   12000000 kB\n"
            "Buffers:          500000 kB\n"
            "Cached:          3000000 kB\n"
            "SwapTotal:       4000000 kB\n"
            "SwapFree:        4000000 kB\n"
        )
        with patch("backend.api.routes.hardware.sudo_wrapper") as mock_sw:
            mock_sw.get_hardware_memory.side_effect = SudoWrapperError("NoNewPrivileges")
            with patch("builtins.open", mock_open(read_data=meminfo_content)):
                response = test_client.get("/api/hardware/memory", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["memory"]["total_kb"] == 16000000

    def test_get_memory_wrapper_error_fallback_also_fails(self, test_client, auth_headers):
        """SudoWrapperError + /proc/meminfo も失敗するケース"""
        original_open = open

        def patched_open(path, *args, **kwargs):
            if str(path) == "/proc/meminfo":
                raise OSError("File not found")
            return original_open(path, *args, **kwargs)

        with patch("backend.api.routes.hardware.sudo_wrapper") as mock_sw:
            mock_sw.get_hardware_memory.side_effect = SudoWrapperError("Permission denied")
            with patch("builtins.open", side_effect=patched_open):
                response = test_client.get("/api/hardware/memory", headers=auth_headers)

        assert response.status_code == 500
