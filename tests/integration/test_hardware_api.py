"""
Hardwareモジュール - 統合テスト

APIエンドポイントの統合テスト（sudo_wrapperをモック）
"""

from unittest.mock import patch

import pytest


# テスト用ハードウェアデータ
SAMPLE_DISKS_RESPONSE = {
    "status": "success",
    "disks": [
        {
            "name": "sda",
            "size": "500G",
            "type": "disk",
            "mountpoint": None,
            "fstype": None,
            "model": "Samsung SSD 860",
        },
        {
            "name": "sda1",
            "size": "50G",
            "type": "part",
            "mountpoint": "/",
            "fstype": "ext4",
            "model": None,
        },
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_DISK_USAGE_RESPONSE = {
    "status": "success",
    "usage": [
        {
            "filesystem": "/dev/sda1",
            "size_kb": 51200000,
            "used_kb": 20480000,
            "avail_kb": 28160000,
            "use_percent": 42,
            "mountpoint": "/",
        },
        {
            "filesystem": "/dev/sda2",
            "size_kb": 10240000,
            "used_kb": 1024000,
            "avail_kb": 8704000,
            "use_percent": 11,
            "mountpoint": "/boot",
        },
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_SMART_RESPONSE = {
    "status": "success",
    "device": "/dev/sda",
    "smart": {
        "smartctl": {"version": [7, 3]},
        "model_name": "Samsung SSD 860",
        "smart_status": {"passed": True},
        "temperature": {"current": 35},
    },
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_SENSORS_RESPONSE = {
    "status": "success",
    "source": "lm-sensors",
    "sensors": {
        "coretemp-isa-0000": {
            "Core 0": {"temp1_input": 45.0, "temp1_max": 100.0},
            "Core 1": {"temp2_input": 43.0, "temp2_max": 100.0},
        }
    },
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_MEMORY_RESPONSE = {
    "status": "success",
    "memory": {
        "total_kb": 16384000,
        "free_kb": 4096000,
        "available_kb": 8192000,
        "buffers_kb": 512000,
        "cached_kb": 2048000,
        "swap_total_kb": 4096000,
        "swap_free_kb": 4096000,
    },
    "timestamp": "2026-01-01T00:00:00Z",
}


# ==============================================================================
# 認証テスト
# ==============================================================================


class TestHardwareAuthentication:
    """認証・認可テスト"""

    def test_anonymous_user_rejected_disks(self, test_client):
        response = test_client.get("/api/hardware/disks")
        assert response.status_code == 403  # Bearer token required

    def test_anonymous_user_rejected_disk_usage(self, test_client):
        response = test_client.get("/api/hardware/disk_usage")
        assert response.status_code == 403

    def test_anonymous_user_rejected_sensors(self, test_client):
        response = test_client.get("/api/hardware/sensors")
        assert response.status_code == 403

    def test_anonymous_user_rejected_memory(self, test_client):
        response = test_client.get("/api/hardware/memory")
        assert response.status_code == 403

    def test_viewer_can_read_hardware(self, test_client, viewer_headers):
        """Viewer ロールはハードウェア情報を読み取れる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_disks") as mock_get:
            mock_get.return_value = SAMPLE_DISKS_RESPONSE
            response = test_client.get("/api/hardware/disks", headers=viewer_headers)
            assert response.status_code == 200

    def test_smart_invalid_device_returns_400(self, test_client, auth_headers):
        """allowlist 外のデバイスパスは 400 を返す"""
        response = test_client.get(
            "/api/hardware/smart?device=/dev/sda;rm+-rf",
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_smart_no_device_returns_422(self, test_client, auth_headers):
        """device パラメータなしは 422 を返す"""
        response = test_client.get("/api/hardware/smart", headers=auth_headers)
        assert response.status_code == 422


# ==============================================================================
# ディスク一覧テスト
# ==============================================================================


class TestHardwareDisks:
    """GET /api/hardware/disks テスト"""

    def test_get_disks_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_disks") as mock_get:
            mock_get.return_value = SAMPLE_DISKS_RESPONSE
            response = test_client.get("/api/hardware/disks", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "disks" in data
        assert len(data["disks"]) == 2
        assert "timestamp" in data

    def test_get_disks_empty(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_disks") as mock_get:
            mock_get.return_value = {
                "status": "success",
                "disks": [],
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/hardware/disks", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["disks"] == []

    def test_get_disks_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_disks") as mock_get:
            mock_get.side_effect = SudoWrapperError("lsblk failed")
            response = test_client.get("/api/hardware/disks", headers=auth_headers)

        assert response.status_code == 500

    def test_get_disks_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_disks") as mock_get:
            mock_get.return_value = {
                "status": "error",
                "message": "lsblk command not found",
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/hardware/disks", headers=auth_headers)

        assert response.status_code == 503


# ==============================================================================
# ディスク使用量テスト
# ==============================================================================


class TestHardwareDiskUsage:
    """GET /api/hardware/disk_usage テスト"""

    def test_get_disk_usage_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_disk_usage") as mock_get:
            mock_get.return_value = SAMPLE_DISK_USAGE_RESPONSE
            response = test_client.get("/api/hardware/disk_usage", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "usage" in data
        assert len(data["usage"]) == 2

    def test_get_disk_usage_empty(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_disk_usage") as mock_get:
            mock_get.return_value = {
                "status": "success",
                "usage": [],
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/hardware/disk_usage", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["usage"] == []

    def test_get_disk_usage_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_disk_usage") as mock_get:
            mock_get.side_effect = SudoWrapperError("df failed")
            response = test_client.get("/api/hardware/disk_usage", headers=auth_headers)

        assert response.status_code == 500

    def test_get_disk_usage_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_disk_usage") as mock_get:
            mock_get.return_value = {
                "status": "error",
                "message": "df command not found",
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/hardware/disk_usage", headers=auth_headers)

        assert response.status_code == 503


# ==============================================================================
# SMARTテスト
# ==============================================================================


class TestHardwareSmart:
    """GET /api/hardware/smart テスト"""

    def test_get_smart_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_smart") as mock_get:
            mock_get.return_value = SAMPLE_SMART_RESPONSE
            response = test_client.get(
                "/api/hardware/smart?device=/dev/sda", headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["device"] == "/dev/sda"
        assert "smart" in data

    @pytest.mark.parametrize(
        "device",
        ["/dev/sda", "/dev/sdb", "/dev/nvme0n1", "/dev/vda"],
    )
    def test_get_smart_valid_devices(self, test_client, auth_headers, device):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_smart") as mock_get:
            resp = dict(SAMPLE_SMART_RESPONSE)
            resp["device"] = device
            mock_get.return_value = resp
            response = test_client.get(
                f"/api/hardware/smart?device={device}", headers=auth_headers
            )
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "bad_device,expected_status",
        [
            ("/dev/sda;ls", 400),
            ("/etc/passwd", 400),
            ("/dev/../etc/shadow", 400),
            ("sda", 422),        # min_length=8 未満のため 422
            ("/dev/sda1", 400),  # パーティション不可
        ],
    )
    def test_get_smart_invalid_devices_rejected(
        self, test_client, auth_headers, bad_device, expected_status
    ):
        """不正なデバイスパスは 400 を返す"""
        from urllib.parse import quote

        response = test_client.get(
            f"/api/hardware/smart?device={quote(bad_device)}", headers=auth_headers
        )
        assert response.status_code == expected_status

    def test_get_smart_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_smart") as mock_get:
            mock_get.side_effect = SudoWrapperError("smartctl failed")
            response = test_client.get(
                "/api/hardware/smart?device=/dev/sda", headers=auth_headers
            )

        assert response.status_code == 500

    def test_get_smart_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_smart") as mock_get:
            mock_get.return_value = {
                "status": "error",
                "message": "smartctl not found",
                "device": "/dev/sda",
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get(
                "/api/hardware/smart?device=/dev/sda", headers=auth_headers
            )

        assert response.status_code == 503


# ==============================================================================
# センサーテスト
# ==============================================================================


class TestHardwareSensors:
    """GET /api/hardware/sensors テスト"""

    def test_get_sensors_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_sensors") as mock_get:
            mock_get.return_value = SAMPLE_SENSORS_RESPONSE
            response = test_client.get("/api/hardware/sensors", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "sensors" in data

    def test_get_sensors_thermal_zone_fallback(self, test_client, auth_headers):
        """thermal_zone フォールバックデータも受け付ける"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_sensors") as mock_get:
            mock_get.return_value = {
                "status": "success",
                "source": "thermal_zone",
                "sensors": [
                    {"zone": "thermal_zone0", "type": "x86_pkg_temp", "temp_celsius": 42.0}
                ],
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/hardware/sensors", headers=auth_headers)

        assert response.status_code == 200

    def test_get_sensors_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_sensors") as mock_get:
            mock_get.side_effect = SudoWrapperError("sensors failed")
            response = test_client.get("/api/hardware/sensors", headers=auth_headers)

        assert response.status_code == 500

    def test_get_sensors_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_sensors") as mock_get:
            mock_get.return_value = {
                "status": "error",
                "message": "sensors not available",
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/hardware/sensors", headers=auth_headers)

        assert response.status_code == 503


# ==============================================================================
# メモリテスト
# ==============================================================================


class TestHardwareMemory:
    """GET /api/hardware/memory テスト"""

    def test_get_memory_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_memory") as mock_get:
            mock_get.return_value = SAMPLE_MEMORY_RESPONSE
            response = test_client.get("/api/hardware/memory", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "memory" in data
        mem = data["memory"]
        assert "total_kb" in mem
        assert "free_kb" in mem
        assert "available_kb" in mem

    def test_get_memory_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_memory") as mock_get:
            mock_get.side_effect = SudoWrapperError("memory failed")
            response = test_client.get("/api/hardware/memory", headers=auth_headers)

        # SudoWrapperError 時は /proc/meminfo フォールバックが動作し 200 が返る（実環境）
        # フォールバックも失敗した場合は 500
        assert response.status_code in (200, 500)

    def test_get_memory_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_hardware_memory") as mock_get:
            mock_get.return_value = {
                "status": "error",
                "message": "/proc/meminfo not available",
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/hardware/memory", headers=auth_headers)

        assert response.status_code == 503
