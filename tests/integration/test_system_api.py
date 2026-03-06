"""システム情報API統合テスト（/api/system/detailed）"""
import sys

sys.path.insert(0, "/mnt/LinuxHDD/Linux-Management-Systm")

import os
os.environ["ENV"] = "dev"

from unittest.mock import mock_open, patch

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def get_auth_headers(client: TestClient) -> dict:
    resp = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


FAKE_MEMINFO = (
    "MemTotal:       16384000 kB\n"
    "MemFree:         2048000 kB\n"
    "MemAvailable:    8192000 kB\n"
    "Buffers:          512000 kB\n"
    "Cached:          4096000 kB\n"
    "SwapTotal:       4096000 kB\n"
    "SwapFree:        4096000 kB\n"
)

FAKE_NETDEV = (
    "Inter-|   Receive                                                |  Transmit\n"
    " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed\n"
    "    lo: 1000 10 0 0 0 0 0 0 2000 20 0 0 0 0 0 0\n"
    "  eth0: 500000 1000 1 0 0 0 0 0 300000 800 0 0 0 0 0 0\n"
)

FAKE_UPTIME = "86400.0 3600.0\n"


class TestSystemDetailedEndpoint:
    """GET /api/system/detailed テスト"""

    def test_requires_auth(self, client):
        """認証なしで401/403を返す"""
        resp = client.get("/api/system/detailed")
        assert resp.status_code in (401, 403)

    def test_returns_200_with_valid_auth(self, client):
        """認証ありで200を返す"""
        headers = get_auth_headers(client)
        with (
            patch("builtins.open", mock_open(read_data=FAKE_MEMINFO)),
            patch("glob.glob", return_value=[]),
        ):
            resp = client.get("/api/system/detailed", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    def test_memory_detail_keys(self, client):
        """memory_detail に必要なキーが含まれる"""
        headers = get_auth_headers(client)
        with (
            patch("glob.glob", return_value=[]),
            patch("builtins.open", mock_open(read_data=FAKE_MEMINFO)),
        ):
            resp = client.get("/api/system/detailed", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "memory_detail" in data

    def test_network_interfaces_excludes_lo(self, client):
        """network_interfaces に lo は含まれない"""
        headers = get_auth_headers(client)

        open_calls = {
            "/proc/meminfo": FAKE_MEMINFO,
            "/proc/net/dev": FAKE_NETDEV,
            "/proc/uptime": FAKE_UPTIME,
        }

        def fake_open(path, *args, **kwargs):
            path = str(path)
            for key, content in open_calls.items():
                if key in path:
                    return mock_open(read_data=content)()
            return mock_open(read_data="")()

        with (
            patch("glob.glob", return_value=[]),
            patch("builtins.open", side_effect=fake_open),
        ):
            resp = client.get("/api/system/detailed", headers=headers)
        assert resp.status_code == 200
        ifaces = [n["interface"] for n in resp.json()["data"].get("network_interfaces", [])]
        assert "lo" not in ifaces

    def test_uptime_structure(self, client):
        """uptime に days/hours/minutes が含まれる"""
        headers = get_auth_headers(client)

        def fake_open(path, *args, **kwargs):
            path = str(path)
            if "uptime" in path:
                return mock_open(read_data=FAKE_UPTIME)()
            if "meminfo" in path:
                return mock_open(read_data=FAKE_MEMINFO)()
            if "net/dev" in path:
                return mock_open(read_data=FAKE_NETDEV)()
            return mock_open(read_data="")()

        with (
            patch("glob.glob", return_value=[]),
            patch("builtins.open", side_effect=fake_open),
        ):
            resp = client.get("/api/system/detailed", headers=headers)
        assert resp.status_code == 200
        uptime = resp.json()["data"]["uptime"]
        assert "days" in uptime
        assert "hours" in uptime
        assert "minutes" in uptime
        assert uptime["days"] == 1

    def test_meminfo_read_failure_returns_error_key(self, client):
        """meminfo 読み取り失敗時は memory_detail に error キーが含まれる"""
        headers = get_auth_headers(client)

        def fake_open(path, *args, **kwargs):
            path = str(path)
            if "meminfo" in path:
                raise OSError("permission denied")
            if "net/dev" in path:
                return mock_open(read_data=FAKE_NETDEV)()
            if "uptime" in path:
                return mock_open(read_data=FAKE_UPTIME)()
            return mock_open(read_data="")()

        with (
            patch("glob.glob", return_value=[]),
            patch("builtins.open", side_effect=fake_open),
        ):
            resp = client.get("/api/system/detailed", headers=headers)
        assert resp.status_code == 200
        assert "error" in resp.json()["data"]["memory_detail"]

    def test_netdev_read_failure_returns_error_entry(self, client):
        """net/dev 読み取り失敗時は network_interfaces にエラーエントリが含まれる"""
        headers = get_auth_headers(client)

        def fake_open(path, *args, **kwargs):
            path = str(path)
            if "meminfo" in path:
                return mock_open(read_data=FAKE_MEMINFO)()
            if "net/dev" in path:
                raise OSError("no such file")
            if "uptime" in path:
                return mock_open(read_data=FAKE_UPTIME)()
            return mock_open(read_data="")()

        with (
            patch("glob.glob", return_value=[]),
            patch("builtins.open", side_effect=fake_open),
        ):
            resp = client.get("/api/system/detailed", headers=headers)
        assert resp.status_code == 200
        nics = resp.json()["data"]["network_interfaces"]
        assert isinstance(nics, list)
        assert len(nics) > 0
        assert "error" in nics[0]

    def test_uptime_read_failure_returns_empty_dict(self, client):
        """uptime 読み取り失敗時は uptime が空辞書を返す"""
        headers = get_auth_headers(client)

        def fake_open(path, *args, **kwargs):
            path = str(path)
            if "meminfo" in path:
                return mock_open(read_data=FAKE_MEMINFO)()
            if "net/dev" in path:
                return mock_open(read_data=FAKE_NETDEV)()
            if "uptime" in path:
                raise OSError("no such file")
            return mock_open(read_data="")()

        with (
            patch("glob.glob", return_value=[]),
            patch("builtins.open", side_effect=fake_open),
        ):
            resp = client.get("/api/system/detailed", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["uptime"] == {}

    def test_cpu_temperatures_populated_when_files_exist(self, client):
        """thermal_zone ファイルが存在する場合に cpu_temperatures が設定される"""
        headers = get_auth_headers(client)

        def fake_open(path, *args, **kwargs):
            path = str(path)
            if "thermal_zone0/temp" in path:
                return mock_open(read_data="45000")()
            if "thermal_zone0/type" in path:
                return mock_open(read_data="x86_pkg_temp")()
            if "meminfo" in path:
                return mock_open(read_data=FAKE_MEMINFO)()
            if "net/dev" in path:
                return mock_open(read_data=FAKE_NETDEV)()
            if "uptime" in path:
                return mock_open(read_data=FAKE_UPTIME)()
            return mock_open(read_data="")()

        with (
            patch("glob.glob", return_value=["/sys/class/thermal/thermal_zone0/temp"]),
            patch("builtins.open", side_effect=fake_open),
        ):
            resp = client.get("/api/system/detailed", headers=headers)
        assert resp.status_code == 200
        temps = resp.json()["data"]["cpu_temperatures"]
        assert len(temps) == 1
        assert temps[0]["temp_c"] == 45.0
        assert temps[0]["zone"] == "x86_pkg_temp"

    def test_viewer_role_can_access(self, client):
        """viewer ロールも /api/system/detailed にアクセスできる"""
        resp = client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer123"})
        assert resp.status_code == 200
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        with (
            patch("glob.glob", return_value=[]),
            patch("builtins.open", mock_open(read_data=FAKE_MEMINFO)),
        ):
            resp = client.get("/api/system/detailed", headers=headers)
        assert resp.status_code == 200

    def test_response_has_data_key(self, client):
        """レスポンスに data キーが含まれる"""
        headers = get_auth_headers(client)
        with (
            patch("glob.glob", return_value=[]),
            patch("builtins.open", mock_open(read_data=FAKE_MEMINFO)),
        ):
            resp = client.get("/api/system/detailed", headers=headers)
        assert "data" in resp.json()
        assert "cpu_temperatures" in resp.json()["data"]
        assert "network_interfaces" in resp.json()["data"]
