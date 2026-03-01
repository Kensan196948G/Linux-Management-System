"""
Sensors モジュール - 統合テスト

APIエンドポイントの統合テスト（sudo_wrapperをモック）
"""

from unittest.mock import patch

import pytest

# テスト用センサーデータ
SAMPLE_SENSORS_ALL_RESPONSE = {
    "status": "success",
    "source": "lm-sensors",
    "sensors": {
        "coretemp-isa-0000": {
            "Adapter": "ISA adapter",
            "Core 0": {"temp2_input": 45.0, "temp2_max": 100.0, "temp2_crit": 100.0},
            "Core 1": {"temp3_input": 43.0, "temp3_max": 100.0, "temp3_crit": 100.0},
        },
        "it8728-isa-0228": {
            "Adapter": "ISA adapter",
            "in0": {"in0_input": 0.836, "in0_min": 0.0, "in0_max": 3.06},
            "fan1": {"fan1_input": 1200.0, "fan1_min": 0.0},
        },
    },
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_SENSORS_TEMPERATURE_RESPONSE = {
    "status": "success",
    "source": "lm-sensors",
    "temperature": {
        "coretemp-isa-0000": {
            "Core 0": {"temp2_input": 45.0, "temp2_max": 100.0},
            "Core 1": {"temp3_input": 43.0, "temp3_max": 100.0},
        }
    },
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_SENSORS_FANS_RESPONSE = {
    "status": "success",
    "source": "lm-sensors",
    "fans": {
        "it8728-isa-0228": {
            "fan1": {"fan1_input": 1200.0, "fan1_min": 0.0},
            "fan2": {"fan2_input": 850.0, "fan2_min": 0.0},
        }
    },
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_SENSORS_VOLTAGE_RESPONSE = {
    "status": "success",
    "source": "lm-sensors",
    "voltage": {
        "it8728-isa-0228": {
            "in0": {"in0_input": 0.836, "in0_min": 0.0, "in0_max": 3.06},
            "in1": {"in1_input": 1.824, "in1_min": 0.0, "in1_max": 3.06},
        }
    },
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_SENSORS_UNAVAILABLE_RESPONSE = {
    "status": "unavailable",
    "message": "lm-sensors not installed",
    "source": "thermal_zone",
    "sensors": {"temperature": [], "fans": [], "voltage": []},
    "timestamp": "2026-01-01T00:00:00Z",
}


class TestSensorsAuth:
    """認証・権限テスト"""

    def test_anonymous_user_rejected_all(self, test_client):
        response = test_client.get("/api/sensors/all")
        assert response.status_code == 403  # Bearer token required

    def test_anonymous_user_rejected_temperature(self, test_client):
        response = test_client.get("/api/sensors/temperature")
        assert response.status_code == 403  # Bearer token required

    def test_anonymous_user_rejected_fans(self, test_client):
        response = test_client.get("/api/sensors/fans")
        assert response.status_code == 403  # Bearer token required

    def test_anonymous_user_rejected_voltage(self, test_client):
        response = test_client.get("/api/sensors/voltage")
        assert response.status_code == 403  # Bearer token required

    def test_viewer_can_read_sensors_all(self, test_client, viewer_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sensors_all") as mock:
            mock.return_value = SAMPLE_SENSORS_ALL_RESPONSE
            response = test_client.get("/api/sensors/all", headers=viewer_headers)
        assert response.status_code == 200

    def test_viewer_can_read_sensors_temperature(self, test_client, viewer_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sensors_temperature") as mock:
            mock.return_value = SAMPLE_SENSORS_TEMPERATURE_RESPONSE
            response = test_client.get("/api/sensors/temperature", headers=viewer_headers)
        assert response.status_code == 200


class TestSensorsAll:
    """GET /api/sensors/all テスト"""

    def test_get_sensors_all_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sensors_all") as mock:
            mock.return_value = SAMPLE_SENSORS_ALL_RESPONSE
            response = test_client.get("/api/sensors/all", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["source"] == "lm-sensors"
        assert "sensors" in data
        assert "timestamp" in data

    def test_get_sensors_all_unavailable(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sensors_all") as mock:
            mock.return_value = SAMPLE_SENSORS_UNAVAILABLE_RESPONSE
            response = test_client.get("/api/sensors/all", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unavailable"

    def test_get_sensors_all_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sensors_all") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/sensors/all", headers=auth_headers)
        assert response.status_code == 500

    def test_get_sensors_all_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sensors_all") as mock:
            mock.return_value = {"status": "error", "message": "sensors command failed"}
            response = test_client.get("/api/sensors/all", headers=auth_headers)
        assert response.status_code == 503


class TestSensorsTemperature:
    """GET /api/sensors/temperature テスト"""

    def test_get_temperature_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sensors_temperature") as mock:
            mock.return_value = SAMPLE_SENSORS_TEMPERATURE_RESPONSE
            response = test_client.get("/api/sensors/temperature", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "temperature" in data
        assert "timestamp" in data

    def test_get_temperature_empty(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sensors_temperature") as mock:
            mock.return_value = {
                "status": "success",
                "source": "lm-sensors",
                "temperature": {},
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/sensors/temperature", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["temperature"] == {}

    def test_get_temperature_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sensors_temperature") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/sensors/temperature", headers=auth_headers)
        assert response.status_code == 500

    def test_get_temperature_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sensors_temperature") as mock:
            mock.return_value = {"status": "error", "message": "failed"}
            response = test_client.get("/api/sensors/temperature", headers=auth_headers)
        assert response.status_code == 503


class TestSensorsFans:
    """GET /api/sensors/fans テスト"""

    def test_get_fans_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sensors_fans") as mock:
            mock.return_value = SAMPLE_SENSORS_FANS_RESPONSE
            response = test_client.get("/api/sensors/fans", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "fans" in data

    def test_get_fans_unavailable(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sensors_fans") as mock:
            mock.return_value = {
                "status": "unavailable",
                "message": "lm-sensors not installed",
                "fans": [],
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/sensors/fans", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unavailable"

    def test_get_fans_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sensors_fans") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/sensors/fans", headers=auth_headers)
        assert response.status_code == 500

    def test_get_fans_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sensors_fans") as mock:
            mock.return_value = {"status": "error", "message": "failed"}
            response = test_client.get("/api/sensors/fans", headers=auth_headers)
        assert response.status_code == 503


class TestSensorsVoltage:
    """GET /api/sensors/voltage テスト"""

    def test_get_voltage_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sensors_voltage") as mock:
            mock.return_value = SAMPLE_SENSORS_VOLTAGE_RESPONSE
            response = test_client.get("/api/sensors/voltage", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "voltage" in data

    def test_get_voltage_empty(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sensors_voltage") as mock:
            mock.return_value = {
                "status": "success",
                "source": "lm-sensors",
                "voltage": {},
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/sensors/voltage", headers=auth_headers)
        assert response.status_code == 200

    def test_get_voltage_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sensors_voltage") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/sensors/voltage", headers=auth_headers)
        assert response.status_code == 500

    def test_get_voltage_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sensors_voltage") as mock:
            mock.return_value = {"status": "error", "message": "failed"}
            response = test_client.get("/api/sensors/voltage", headers=auth_headers)
        assert response.status_code == 503
