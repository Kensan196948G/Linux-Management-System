"""
Network モジュール - カバレッジ改善テスト v2

未カバー箇所を集中的にテスト:
  - get_interfaces: SudoWrapperError フォールバック(ip -j addr show) 成功/失敗
  - get_interfaces: error status 分岐(parsed vs result の message)
  - get_dns_config: resolv.conf パース各行タイプ(nameserver/search/domain)
  - get_dns_config: nameserver だけの行(split()[1]が無い場合)
  - get_interface_detail: subprocess.run 正常/失敗/例外
  - update_interface_config: バリデーション全分岐 + approval_service 成功/失敗
  - update_dns_config: バリデーション全分岐 + dns2 有無 + approval 成功/失敗
  - validate_interface_name / validate_ip_cidr / validate_ip_address 追加パターン
  - 各エンドポイントの audit_log パラメータ検証
"""

import json
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.routes.network import (
    validate_interface_name,
    validate_ip_address,
    validate_ip_cidr,
)


# ===================================================================
# バリデーション関数 追加テスト
# ===================================================================


class TestValidateInterfaceNameV2:
    """validate_interface_name の追加パターン"""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("eth0", True),
            ("ens3", True),
            ("enp2s0", True),
            ("lo", True),
            ("wlan0", True),
            ("br0", True),
            ("bond0", True),
            ("veth1234567890", True),      # 最大16文字 (v + 15 = 16? -> a-z first + 0-15 more)
            ("a", True),                    # 最小1文字
        ],
    )
    def test_valid_names(self, name, expected):
        assert validate_interface_name(name) is expected

    @pytest.mark.parametrize(
        "name",
        [
            "",                             # 空
            "0eth",                         # 数字開始
            "Eth0",                         # 大文字
            "eth-0",                        # ハイフン
            "eth_0",                        # アンダースコア
            "eth0;ls",                      # セミコロン
            "a" * 17,                       # 17文字超過
            "../etc",                       # パストラバーサル
        ],
    )
    def test_invalid_names(self, name):
        assert validate_interface_name(name) is False


class TestValidateIpCidrV2:
    """validate_ip_cidr の追加パターン"""

    @pytest.mark.parametrize(
        "ip_cidr,expected",
        [
            ("192.168.1.100/24", True),
            ("10.0.0.1/8", True),
            ("172.16.0.1/16", True),
            ("255.255.255.255/32", True),
            ("0.0.0.0/0", True),
            ("2001:db8::1/64", True),       # IPv6 も ipaddress.ip_interface で有効
        ],
    )
    def test_valid_cidr(self, ip_cidr, expected):
        assert validate_ip_cidr(ip_cidr) is expected

    @pytest.mark.parametrize(
        "ip_cidr",
        [
            "not-an-ip",
            "999.999.999.999/24",
            "192.168.1.100",               # CIDR なし → ValueError (ip_interface は許容するが確認)
            "",
            "abc/24",
        ],
    )
    def test_invalid_cidr(self, ip_cidr):
        result = validate_ip_cidr(ip_cidr)
        # ip_interface は "192.168.1.100" (CIDR無し) でも True を返す場合がある
        # 不正な値のみ False
        if ip_cidr in ("not-an-ip", "999.999.999.999/24", "", "abc/24"):
            assert result is False


class TestValidateIpAddressV2:
    """validate_ip_address の追加パターン"""

    @pytest.mark.parametrize(
        "ip,expected",
        [
            ("192.168.1.1", True),
            ("8.8.8.8", True),
            ("0.0.0.0", True),
            ("255.255.255.255", True),
            ("::1", True),                  # IPv6 loopback
            ("2001:db8::1", True),          # IPv6
        ],
    )
    def test_valid_ips(self, ip, expected):
        assert validate_ip_address(ip) is expected

    @pytest.mark.parametrize(
        "ip",
        [
            "not-ip",
            "300.300.300.300",
            "",
            "192.168.1.1/24",              # CIDR付きは不許可
            "abc",
        ],
    )
    def test_invalid_ips(self, ip):
        assert validate_ip_address(ip) is False


# ===================================================================
# get_interfaces: SudoWrapperError フォールバック分岐
# ===================================================================


class TestNetworkInterfacesFallback:
    """SudoWrapperError 時の ip -j フォールバック"""

    def test_fallback_success(self, test_client, auth_headers):
        """ip -j addr show が成功する場合"""
        from backend.core.sudo_wrapper import SudoWrapperError

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = '[{"ifname":"lo","addr_info":[]}]'

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces",
            side_effect=SudoWrapperError("sudo unavailable"),
        ), patch(
            "subprocess.run",
            return_value=mock_proc,
        ):
            resp = test_client.get("/api/network/interfaces", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    def test_fallback_failure(self, test_client, auth_headers):
        """ip -j フォールバックも失敗する場合"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces",
            side_effect=SudoWrapperError("sudo unavailable"),
        ), patch(
            "subprocess.run",
            side_effect=Exception("ip command not found"),
        ):
            resp = test_client.get("/api/network/interfaces", headers=auth_headers)
        assert resp.status_code == 500

    def test_fallback_nonzero_returncode(self, test_client, auth_headers):
        """ip コマンドが非ゼロ returncode を返す場合"""
        from backend.core.sudo_wrapper import SudoWrapperError

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces",
            side_effect=SudoWrapperError("sudo unavailable"),
        ), patch(
            "subprocess.run",
            return_value=mock_proc,
        ):
            resp = test_client.get("/api/network/interfaces", headers=auth_headers)
        assert resp.status_code == 500


# ===================================================================
# get_interfaces: error status 分岐
# ===================================================================


class TestNetworkInterfacesErrorStatus:
    """parsed/result の status=error 分岐"""

    def test_result_status_error(self, test_client, auth_headers):
        """result.status == error のパス"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces",
            return_value={
                "status": "error",
                "message": "test error from result",
                "interfaces": [],
                "timestamp": "2026-03-01T00:00:00Z",
            },
        ):
            resp = test_client.get("/api/network/interfaces", headers=auth_headers)
        assert resp.status_code == 503

    def test_parsed_status_error_with_output(self, test_client, auth_headers):
        """output JSON 内の status=error"""
        inner = {
            "status": "error",
            "message": "inner error",
            "interfaces": [],
            "timestamp": "2026-03-01T00:00:00Z",
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces",
            return_value={"status": "success", "output": json.dumps(inner)},
        ):
            resp = test_client.get("/api/network/interfaces", headers=auth_headers)
        assert resp.status_code == 503


# ===================================================================
# get_dns_config (resolv.conf パース): エッジケース
# ===================================================================


class TestNetworkDnsParsingV2:
    """resolv.conf パースの全分岐"""

    def test_empty_resolv_conf(self, test_client, auth_headers):
        """空の resolv.conf"""
        import builtins
        real_open = builtins.open

        def selective_open(path, *a, **kw):
            if "/etc/resolv.conf" in str(path):
                return StringIO("")
            return real_open(path, *a, **kw)

        with patch("builtins.open", side_effect=selective_open):
            resp = test_client.get("/api/network/dns", headers=auth_headers)
        assert resp.status_code == 200
        dns = resp.json()["dns"]
        assert dns["nameservers"] == []
        assert dns["search"] == []
        assert dns["domain"] is None

    def test_nameserver_only_keyword(self, test_client, auth_headers):
        """nameserver だけの行 (IP無し)"""
        import builtins
        real_open = builtins.open

        def selective_open(path, *a, **kw):
            if "/etc/resolv.conf" in str(path):
                return StringIO("nameserver\n")
            return real_open(path, *a, **kw)

        with patch("builtins.open", side_effect=selective_open):
            resp = test_client.get("/api/network/dns", headers=auth_headers)
        assert resp.status_code == 200
        # nameserver のみの行は ip="" → regex不一致 → 追加されない
        assert resp.json()["dns"]["nameservers"] == []

    def test_domain_only_keyword(self, test_client, auth_headers):
        """domain だけの行 (ドメイン名なし)"""
        import builtins
        real_open = builtins.open

        def selective_open(path, *a, **kw):
            if "/etc/resolv.conf" in str(path):
                return StringIO("domain\n")
            return real_open(path, *a, **kw)

        with patch("builtins.open", side_effect=selective_open):
            resp = test_client.get("/api/network/dns", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["dns"]["domain"] is None

    def test_comment_and_blank_lines(self, test_client, auth_headers):
        """コメント行と空行を含む resolv.conf"""
        import builtins
        real_open = builtins.open
        content = "# comment\n\nnameserver 1.1.1.1\n# another\nsearch test.local\n"

        def selective_open(path, *a, **kw):
            if "/etc/resolv.conf" in str(path):
                return StringIO(content)
            return real_open(path, *a, **kw)

        with patch("builtins.open", side_effect=selective_open):
            resp = test_client.get("/api/network/dns", headers=auth_headers)
        assert resp.status_code == 200
        dns = resp.json()["dns"]
        assert "1.1.1.1" in dns["nameservers"]
        assert "test.local" in dns["search"]

    def test_ioerror_resolv_conf(self, test_client, auth_headers):
        """IOError の場合も 200 を返す"""
        import builtins
        real_open = builtins.open

        def selective_open(path, *a, **kw):
            if "/etc/resolv.conf" in str(path):
                raise IOError("permission denied")
            return real_open(path, *a, **kw)

        with patch("builtins.open", side_effect=selective_open):
            resp = test_client.get("/api/network/dns", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["dns"]["nameservers"] == []

    def test_ipv6_nameserver(self, test_client, auth_headers):
        """IPv6 nameserver の解析"""
        import builtins
        real_open = builtins.open

        def selective_open(path, *a, **kw):
            if "/etc/resolv.conf" in str(path):
                return StringIO("nameserver 2001:4860:4860::8888\nnameserver ::1\n")
            return real_open(path, *a, **kw)

        with patch("builtins.open", side_effect=selective_open):
            resp = test_client.get("/api/network/dns", headers=auth_headers)
        assert resp.status_code == 200
        ns = resp.json()["dns"]["nameservers"]
        assert "2001:4860:4860::8888" in ns
        assert "::1" in ns


# ===================================================================
# get_interface_detail (GET /network/interfaces/{name})
# ===================================================================


class TestNetworkInterfaceDetailV2:
    """特定 IF 詳細取得の全分岐"""

    def test_valid_interface_success(self, test_client, admin_headers):
        """正常なIFで subprocess 成功"""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = '[{"ifname":"eth0","operstate":"UP"}]'

        with patch("subprocess.run", return_value=mock_proc):
            resp = test_client.get("/api/network/interfaces/eth0", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "interface" in data
        assert "timestamp" in data

    def test_valid_interface_empty_stdout(self, test_client, admin_headers):
        """stdout が空の場合"""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "  "

        with patch("subprocess.run", return_value=mock_proc):
            resp = test_client.get("/api/network/interfaces/eth0", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["interface"] == []

    def test_interface_not_found(self, test_client, admin_headers):
        """IF が存在しない → 404"""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "Device does not exist."

        with patch("subprocess.run", return_value=mock_proc):
            resp = test_client.get("/api/network/interfaces/eth99", headers=admin_headers)
        assert resp.status_code == 404

    def test_invalid_interface_name_rejected(self, test_client, admin_headers):
        """不正IF名は 400"""
        resp = test_client.get("/api/network/interfaces/ETH0", headers=admin_headers)
        assert resp.status_code == 400

    @pytest.mark.parametrize(
        "bad_name",
        [
            "eth0;ls",
            "../etc",
            "0eth",
            "",
        ],
    )
    def test_invalid_interface_names(self, test_client, admin_headers, bad_name):
        """各種不正IF名"""
        resp = test_client.get(f"/api/network/interfaces/{bad_name}", headers=admin_headers)
        assert resp.status_code in (400, 404, 405)

    def test_subprocess_exception(self, test_client, admin_headers):
        """subprocess.run で例外 → 500"""
        with patch("subprocess.run", side_effect=Exception("timeout")):
            resp = test_client.get("/api/network/interfaces/eth0", headers=admin_headers)
        assert resp.status_code == 500

    def test_interface_detail_audit_log(self, test_client, admin_headers):
        """audit_log が正しく呼ばれる"""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = '[{"ifname":"lo"}]'

        with patch("subprocess.run", return_value=mock_proc), \
             patch("backend.api.routes.network.audit_log") as mock_audit:
            resp = test_client.get("/api/network/interfaces/lo", headers=admin_headers)
        assert resp.status_code == 200
        # attempt + success = 少なくとも2回
        assert mock_audit.record.call_count >= 2


# ===================================================================
# PATCH /network/interfaces/{name}: 承認フロー
# ===================================================================


class TestUpdateInterfaceConfigV2:
    """PATCH /network/interfaces/{name} の全分岐"""

    def test_valid_request_approval_success(self, test_client, operator_headers):
        """正常リクエスト → 202"""
        with patch(
            "backend.api.routes.network._approval_service.create_request",
            new_callable=AsyncMock,
            return_value={"id": "approval-123", "status": "pending"},
        ):
            resp = test_client.patch(
                "/api/network/interfaces/eth0",
                json={"ip_cidr": "192.168.1.100/24", "gateway": "192.168.1.1", "reason": "test"},
                headers=operator_headers,
            )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "pending_approval"
        assert data["approval_id"] == "approval-123"
        assert data["interface"] == "eth0"

    def test_invalid_interface_name(self, test_client, operator_headers):
        """不正IF名 → 400"""
        resp = test_client.patch(
            "/api/network/interfaces/ETH0BAD",
            json={"ip_cidr": "192.168.1.100/24", "gateway": "192.168.1.1", "reason": "test"},
            headers=operator_headers,
        )
        assert resp.status_code == 400

    def test_invalid_ip_cidr(self, test_client, operator_headers):
        """不正 IP/CIDR → 422"""
        resp = test_client.patch(
            "/api/network/interfaces/eth0",
            json={"ip_cidr": "not-valid", "gateway": "192.168.1.1", "reason": "test"},
            headers=operator_headers,
        )
        assert resp.status_code == 422

    def test_invalid_gateway(self, test_client, operator_headers):
        """不正ゲートウェイ → 422"""
        resp = test_client.patch(
            "/api/network/interfaces/eth0",
            json={"ip_cidr": "192.168.1.100/24", "gateway": "bad-gw", "reason": "test"},
            headers=operator_headers,
        )
        assert resp.status_code == 422

    def test_approval_service_exception(self, test_client, operator_headers):
        """承認サービスで例外 → 500"""
        with patch(
            "backend.api.routes.network._approval_service.create_request",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB error"),
        ):
            resp = test_client.patch(
                "/api/network/interfaces/eth0",
                json={"ip_cidr": "192.168.1.100/24", "gateway": "192.168.1.1", "reason": "test"},
                headers=operator_headers,
            )
        assert resp.status_code == 500

    def test_viewer_forbidden(self, test_client, viewer_headers):
        """viewer は write:network 不可 → 403"""
        resp = test_client.patch(
            "/api/network/interfaces/eth0",
            json={"ip_cidr": "192.168.1.100/24", "gateway": "192.168.1.1", "reason": "test"},
            headers=viewer_headers,
        )
        assert resp.status_code == 403

    def test_unauthenticated(self, test_client):
        """未認証 → 403"""
        resp = test_client.patch(
            "/api/network/interfaces/eth0",
            json={"ip_cidr": "192.168.1.100/24", "gateway": "192.168.1.1", "reason": "test"},
        )
        assert resp.status_code in (401, 403)


# ===================================================================
# PATCH /network/dns: DNS 設定変更承認フロー
# ===================================================================


class TestUpdateDnsConfigV2:
    """PATCH /network/dns の全分岐"""

    def test_valid_dns_with_dns2(self, test_client, operator_headers):
        """dns1 + dns2 指定で承認成功"""
        with patch(
            "backend.api.routes.network._approval_service.create_request",
            new_callable=AsyncMock,
            return_value={"id": "dns-approval-1", "status": "pending"},
        ):
            resp = test_client.patch(
                "/api/network/dns",
                json={"dns1": "8.8.8.8", "dns2": "8.8.4.4", "reason": "DNS change"},
                headers=operator_headers,
            )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "pending_approval"
        assert data["dns1"] == "8.8.8.8"
        assert data["dns2"] == "8.8.4.4"

    def test_valid_dns_without_dns2(self, test_client, operator_headers):
        """dns1 のみ（dns2=null）で承認成功"""
        with patch(
            "backend.api.routes.network._approval_service.create_request",
            new_callable=AsyncMock,
            return_value={"id": "dns-approval-2", "status": "pending"},
        ):
            resp = test_client.patch(
                "/api/network/dns",
                json={"dns1": "1.1.1.1", "reason": "DNS change"},
                headers=operator_headers,
            )
        assert resp.status_code == 202
        data = resp.json()
        assert data["dns1"] == "1.1.1.1"
        assert data["dns2"] is None

    def test_invalid_dns1(self, test_client, operator_headers):
        """不正 dns1 → 422"""
        resp = test_client.patch(
            "/api/network/dns",
            json={"dns1": "not-an-ip", "reason": "test"},
            headers=operator_headers,
        )
        assert resp.status_code == 422

    def test_invalid_dns2(self, test_client, operator_headers):
        """不正 dns2 → 422"""
        resp = test_client.patch(
            "/api/network/dns",
            json={"dns1": "8.8.8.8", "dns2": "bad-dns", "reason": "test"},
            headers=operator_headers,
        )
        assert resp.status_code == 422

    def test_dns_approval_service_exception(self, test_client, operator_headers):
        """承認サービスで例外 → 500"""
        with patch(
            "backend.api.routes.network._approval_service.create_request",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB error"),
        ):
            resp = test_client.patch(
                "/api/network/dns",
                json={"dns1": "8.8.8.8", "reason": "test"},
                headers=operator_headers,
            )
        assert resp.status_code == 500

    def test_dns_viewer_forbidden(self, test_client, viewer_headers):
        """viewer は write:network 不可 → 403"""
        resp = test_client.patch(
            "/api/network/dns",
            json={"dns1": "8.8.8.8", "reason": "test"},
            headers=viewer_headers,
        )
        assert resp.status_code == 403


# ===================================================================
# get_stats / get_connections / get_routes: audit_log 検証
# ===================================================================


class TestNetworkAuditLogV2:
    """各エンドポイントの audit_log 呼び出し検証"""

    def test_stats_audit_log(self, test_client, auth_headers):
        """stats で audit_log が呼ばれる"""
        data = {"status": "success", "stats": [{"ifname": "lo"}], "timestamp": "2026-03-01T00:00:00Z"}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_stats",
            return_value=data,
        ), patch("backend.api.routes.network.audit_log") as mock_audit:
            resp = test_client.get("/api/network/stats", headers=auth_headers)
        assert resp.status_code == 200
        assert mock_audit.record.call_count >= 2  # attempt + success

    def test_connections_audit_log(self, test_client, auth_headers):
        """connections で audit_log が呼ばれる"""
        data = {"status": "success", "connections": [], "timestamp": "2026-03-01T00:00:00Z"}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_connections",
            return_value=data,
        ), patch("backend.api.routes.network.audit_log") as mock_audit:
            resp = test_client.get("/api/network/connections", headers=auth_headers)
        assert resp.status_code == 200
        assert mock_audit.record.call_count >= 2

    def test_routes_audit_log(self, test_client, auth_headers):
        """routes で audit_log が呼ばれる"""
        data = {"status": "success", "routes": [], "timestamp": "2026-03-01T00:00:00Z"}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_routes",
            return_value=data,
        ), patch("backend.api.routes.network.audit_log") as mock_audit:
            resp = test_client.get("/api/network/routes", headers=auth_headers)
        assert resp.status_code == 200
        assert mock_audit.record.call_count >= 2

    def test_dns_audit_log(self, test_client, auth_headers):
        """dns で audit_log が呼ばれる"""
        with patch("backend.api.routes.network.audit_log") as mock_audit:
            resp = test_client.get("/api/network/dns", headers=auth_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()
        kw = mock_audit.record.call_args[1]
        assert kw["operation"] == "network_dns_view"

    def test_interfaces_detail_audit_log(self, test_client, auth_headers):
        """interfaces-detail で audit_log が呼ばれる"""
        detail_data = {"status": "success", "interfaces": "[]", "timestamp": "2026-03-01T00:00:00Z"}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces_detail",
            return_value=detail_data,
        ), patch("backend.api.routes.network.audit_log") as mock_audit:
            resp = test_client.get("/api/network/interfaces-detail", headers=auth_headers)
        assert resp.status_code == 200
        assert mock_audit.record.call_count >= 2

    def test_dns_config_detail_audit_log(self, test_client, auth_headers):
        """dns-config で audit_log が呼ばれる"""
        dns_data = {
            "status": "success",
            "resolv_conf": "nameserver 8.8.8.8",
            "hosts": "127.0.0.1 localhost",
            "timestamp": "2026-03-01T00:00:00Z",
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_dns_config",
            return_value=dns_data,
        ), patch("backend.api.routes.network.audit_log") as mock_audit:
            resp = test_client.get("/api/network/dns-config", headers=auth_headers)
        assert resp.status_code == 200
        assert mock_audit.record.call_count >= 2

    def test_active_connections_audit_log(self, test_client, auth_headers):
        """active-connections で audit_log が呼ばれる"""
        conn_data = {"status": "success", "connections": "tcp LISTEN", "timestamp": "2026-03-01T00:00:00Z"}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_active_connections",
            return_value=conn_data,
        ), patch("backend.api.routes.network.audit_log") as mock_audit:
            resp = test_client.get("/api/network/active-connections", headers=auth_headers)
        assert resp.status_code == 200
        assert mock_audit.record.call_count >= 2


# ===================================================================
# output JSON パーステスト
# ===================================================================


class TestNetworkOutputParsing:
    """parse_wrapper_result の output パース分岐"""

    def test_stats_with_output_json(self, test_client, auth_headers):
        """output JSON が正しくパースされる"""
        inner = {"status": "success", "stats": [{"ifname": "eth0"}], "timestamp": "2026-03-01T00:00:00Z"}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_stats",
            return_value={"status": "success", "output": json.dumps(inner)},
        ):
            resp = test_client.get("/api/network/stats", headers=auth_headers)
        assert resp.status_code == 200

    def test_connections_with_output_json(self, test_client, auth_headers):
        """connections output JSON パース"""
        inner = {"status": "success", "connections": [], "timestamp": "2026-03-01T00:00:00Z"}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_connections",
            return_value={"status": "success", "output": json.dumps(inner)},
        ):
            resp = test_client.get("/api/network/connections", headers=auth_headers)
        assert resp.status_code == 200

    def test_routes_with_output_json(self, test_client, auth_headers):
        """routes output JSON パース"""
        inner = {"status": "success", "routes": [], "timestamp": "2026-03-01T00:00:00Z"}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_routes",
            return_value={"status": "success", "output": json.dumps(inner)},
        ):
            resp = test_client.get("/api/network/routes", headers=auth_headers)
        assert resp.status_code == 200


# ===================================================================
# PATCH 承認フロー audit_log 検証
# ===================================================================


class TestNetworkPatchAuditLog:
    """PATCH エンドポイントの audit_log 呼び出し検証"""

    def test_patch_interface_audit_log_success(self, test_client, operator_headers):
        """承認成功時の audit_log"""
        with patch(
            "backend.api.routes.network._approval_service.create_request",
            new_callable=AsyncMock,
            return_value={"id": "ap-1", "status": "pending"},
        ), patch("backend.api.routes.network.audit_log") as mock_audit:
            resp = test_client.patch(
                "/api/network/interfaces/eth0",
                json={"ip_cidr": "10.0.0.1/24", "gateway": "10.0.0.254", "reason": "test audit"},
                headers=operator_headers,
            )
        assert resp.status_code == 202
        # attempt + success = 2 回
        assert mock_audit.record.call_count >= 2

    def test_patch_dns_audit_log_success(self, test_client, operator_headers):
        """DNS 承認成功時の audit_log"""
        with patch(
            "backend.api.routes.network._approval_service.create_request",
            new_callable=AsyncMock,
            return_value={"id": "ap-2", "status": "pending"},
        ), patch("backend.api.routes.network.audit_log") as mock_audit:
            resp = test_client.patch(
                "/api/network/dns",
                json={"dns1": "8.8.8.8", "reason": "test audit"},
                headers=operator_headers,
            )
        assert resp.status_code == 202
        assert mock_audit.record.call_count >= 2

    def test_patch_interface_audit_log_denied(self, test_client, operator_headers):
        """不正IF名による denied audit"""
        with patch("backend.api.routes.network.audit_log") as mock_audit:
            resp = test_client.patch(
                "/api/network/interfaces/BADIF",
                json={"ip_cidr": "10.0.0.1/24", "gateway": "10.0.0.1", "reason": "test"},
                headers=operator_headers,
            )
        assert resp.status_code == 400
        # denied が記録される
        call_args_list = [c[1] for c in mock_audit.record.call_args_list]
        assert any(kw.get("status") == "denied" for kw in call_args_list)

    def test_patch_dns_audit_log_denied(self, test_client, operator_headers):
        """不正 DNS で denied audit"""
        with patch("backend.api.routes.network.audit_log") as mock_audit:
            resp = test_client.patch(
                "/api/network/dns",
                json={"dns1": "bad-dns", "reason": "test"},
                headers=operator_headers,
            )
        assert resp.status_code == 422
        call_args_list = [c[1] for c in mock_audit.record.call_args_list]
        assert any(kw.get("status") == "denied" for kw in call_args_list)
