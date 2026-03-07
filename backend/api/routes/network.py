"""
ネットワーク管理 API エンドポイント

提供エンドポイント（読み取り）:
  GET /api/network/interfaces         - インターフェース一覧
  GET /api/network/interfaces/{name}  - 特定インターフェース詳細
  GET /api/network/stats              - インターフェース統計
  GET /api/network/connections        - アクティブな接続
  GET /api/network/routes             - ルーティングテーブル
  GET /api/network/dns                - DNS設定

提供エンドポイント（設定変更 - 承認フロー経由）:
  PATCH /api/network/interfaces/{name} - IP/CIDR/GW変更リクエスト
  PATCH /api/network/dns               - DNS設定変更リクエスト
"""

import ipaddress
import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...core import require_permission, sudo_wrapper
from ...core.approval_service import ApprovalService
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.config import settings
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

_approval_service = ApprovalService(db_path=settings.database.path)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/network", tags=["network"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class NetworkInterfacesResponse(BaseModel):
    """ネットワークインターフェース一覧レスポンス"""

    status: str
    interfaces: list[Any] = Field(default_factory=list)
    timestamp: str


class NetworkStatsResponse(BaseModel):
    """ネットワーク統計レスポンス"""

    status: str
    stats: list[Any] = Field(default_factory=list)
    timestamp: str


class NetworkConnectionsResponse(BaseModel):
    """ネットワーク接続レスポンス"""

    status: str
    connections: list[Any] = Field(default_factory=list)
    timestamp: str


class NetworkRoutesResponse(BaseModel):
    """ルーティングテーブルレスポンス"""

    status: str
    routes: list[Any] = Field(default_factory=list)
    timestamp: str


# -------------------------------------------------------------------
# 設定変更リクエストモデル (v0.40)
# -------------------------------------------------------------------


class NetworkInterfaceConfigRequest(BaseModel):
    """IPアドレス/CIDR/ゲートウェイ変更リクエスト"""

    ip_cidr: str = Field(..., description="IPアドレス/CIDR形式 (例: 192.168.1.100/24)")
    gateway: str = Field(..., description="デフォルトゲートウェイIPアドレス (例: 192.168.1.1)")
    reason: str = Field(..., min_length=1, max_length=500, description="変更理由")


class NetworkDnsConfigRequest(BaseModel):
    """DNS設定変更リクエスト"""

    dns1: str = Field(..., description="プライマリDNSサーバIPアドレス")
    dns2: Optional[str] = Field(None, description="セカンダリDNSサーバIPアドレス（省略可）")
    reason: str = Field(..., min_length=1, max_length=500, description="変更理由")


# -------------------------------------------------------------------
# バリデーション関数 (v0.40)
# -------------------------------------------------------------------


def validate_interface_name(name: str) -> bool:
    """
    インターフェース名を検証する。

    eth0, ens3, enp2s0, lo, wlan0 等の形式のみ許可。

    Args:
        name: 検証するインターフェース名

    Returns:
        有効な場合 True
    """
    return bool(re.match(r"^[a-z][a-z0-9]{0,15}$", name))


def validate_ip_cidr(ip_cidr: str) -> bool:
    """
    IPアドレス/CIDR形式を検証する。

    192.168.1.100/24 形式のIPv4アドレスのみ許可（CIDR必須）。

    Args:
        ip_cidr: 検証するIP/CIDR文字列

    Returns:
        有効な場合 True
    """
    try:
        ipaddress.ip_interface(ip_cidr)
        return True
    except ValueError:
        return False


def validate_ip_address(ip: str) -> bool:
    """
    IPアドレス（CIDR無し）を検証する。

    Args:
        ip: 検証するIPアドレス文字列

    Returns:
        有効な場合 True
    """
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


# ===================================================================
# エンドポイント
# ===================================================================


@router.get("/interfaces", response_model=NetworkInterfacesResponse)
async def get_interfaces(
    current_user: TokenData = Depends(require_permission("read:network")),
) -> NetworkInterfacesResponse:
    """
    ネットワークインターフェース一覧を取得

    Args:
        current_user: 現在のユーザー (read:network 権限必須)

    Returns:
        インターフェース一覧

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Network interfaces requested by={current_user.username}")

    audit_log.record(
        operation="network_interfaces",
        user_id=current_user.user_id,
        target="network",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_network_interfaces()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error" or result.get("status") == "error":
            audit_log.record(
                operation="network_interfaces",
                user_id=current_user.user_id,
                target="network",
                status="denied",
                details={"reason": parsed.get("message", result.get("message", "unknown"))},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=parsed.get("message", result.get("message", "Network information unavailable")),
            )

        audit_log.record(
            operation="network_interfaces",
            user_id=current_user.user_id,
            target="network",
            status="success",
            details={"count": len(parsed.get("interfaces", []))},
        )

        return NetworkInterfacesResponse(**parsed)

    except SudoWrapperError as e:
        # sudoが使えない環境: ip -j コマンドを直接実行（sudo不要）
        logger.warning(f"Sudo unavailable, falling back to direct ip command: {e}")
        try:
            import json as _json
            import subprocess as _sp
            from datetime import datetime as _dt

            proc = _sp.run(["/usr/sbin/ip", "-j", "addr", "show"], capture_output=True, text=True, timeout=10)
            if proc.returncode == 0:
                interfaces = _json.loads(proc.stdout)
                parsed = {
                    "status": "success",
                    "interfaces": interfaces,
                    "timestamp": _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                audit_log.record(
                    operation="network_interfaces",
                    user_id=current_user.user_id,
                    target="network",
                    status="success",
                    details={"source": "ip_fallback", "count": len(interfaces)},
                )
                return NetworkInterfacesResponse(**parsed)
        except Exception as fe:
            logger.error(f"Network interfaces fallback failed: {fe}")
        audit_log.record(
            operation="network_interfaces",
            user_id=current_user.user_id,
            target="network",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Network interfaces failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Network interface retrieval failed: {str(e)}",
        )


@router.get("/stats", response_model=NetworkStatsResponse)
async def get_stats(
    current_user: TokenData = Depends(require_permission("read:network")),
) -> NetworkStatsResponse:
    """
    ネットワークインターフェース統計を取得

    Args:
        current_user: 現在のユーザー (read:network 権限必須)

    Returns:
        統計情報

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Network stats requested by={current_user.username}")

    audit_log.record(
        operation="network_stats",
        user_id=current_user.user_id,
        target="network",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_network_stats()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error" or result.get("status") == "error":
            audit_log.record(
                operation="network_stats",
                user_id=current_user.user_id,
                target="network",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Network stats unavailable"),
            )

        audit_log.record(
            operation="network_stats",
            user_id=current_user.user_id,
            target="network",
            status="success",
            details={"count": len(parsed.get("stats", []))},
        )

        return NetworkStatsResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="network_stats",
            user_id=current_user.user_id,
            target="network",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Network stats failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Network stats retrieval failed: {str(e)}",
        )


@router.get("/connections", response_model=NetworkConnectionsResponse)
async def get_connections(
    current_user: TokenData = Depends(require_permission("read:network")),
) -> NetworkConnectionsResponse:
    """
    アクティブなネットワーク接続一覧を取得

    Args:
        current_user: 現在のユーザー (read:network 権限必須)

    Returns:
        接続一覧

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Network connections requested by={current_user.username}")

    audit_log.record(
        operation="network_connections",
        user_id=current_user.user_id,
        target="network",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_network_connections()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error" or result.get("status") == "error":
            audit_log.record(
                operation="network_connections",
                user_id=current_user.user_id,
                target="network",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Network connections unavailable"),
            )

        audit_log.record(
            operation="network_connections",
            user_id=current_user.user_id,
            target="network",
            status="success",
            details={"count": len(parsed.get("connections", []))},
        )

        return NetworkConnectionsResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="network_connections",
            user_id=current_user.user_id,
            target="network",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Network connections failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Network connections retrieval failed: {str(e)}",
        )


@router.get("/routes", response_model=NetworkRoutesResponse)
async def get_routes(
    current_user: TokenData = Depends(require_permission("read:network")),
) -> NetworkRoutesResponse:
    """
    ルーティングテーブルを取得

    Args:
        current_user: 現在のユーザー (read:network 権限必須)

    Returns:
        ルーティングテーブル

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Network routes requested by={current_user.username}")

    audit_log.record(
        operation="network_routes",
        user_id=current_user.user_id,
        target="network",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_network_routes()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error" or result.get("status") == "error":
            audit_log.record(
                operation="network_routes",
                user_id=current_user.user_id,
                target="network",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Network routes unavailable"),
            )

        audit_log.record(
            operation="network_routes",
            user_id=current_user.user_id,
            target="network",
            status="success",
            details={"count": len(parsed.get("routes", []))},
        )

        return NetworkRoutesResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="network_routes",
            user_id=current_user.user_id,
            target="network",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Network routes failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Network routes retrieval failed: {str(e)}",
        )


@router.get("/dns")
async def get_dns_config(
    current_user: TokenData = Depends(require_permission("read:network")),
):
    """DNS設定を取得（/etc/resolv.conf 読み取り）"""
    dns_info: dict = {"nameservers": [], "search": [], "domain": None}
    try:
        with open("/etc/resolv.conf", "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("nameserver"):
                    ip = line.split()[1] if len(line.split()) > 1 else ""
                    # IPアドレスバリデーション（基本）
                    if re.match(r"^[\d.:a-fA-F]+$", ip):
                        dns_info["nameservers"].append(ip)
                elif line.startswith("search"):
                    dns_info["search"] = line.split()[1:]
                elif line.startswith("domain"):
                    parts = line.split()
                    if len(parts) > 1:
                        dns_info["domain"] = parts[1]
    except (OSError, IOError):
        pass
    audit_log.record(
        operation="network_dns_view",
        user_id=current_user.user_id,
        target="network",
        status="success",
        details={},
    )
    return {"status": "success", "dns": dns_info}


# ===================================================================
# 拡張エンドポイント (v0.23)
# ===================================================================


@router.get("/interfaces-detail")
async def get_interfaces_detail(
    current_user: TokenData = Depends(require_permission("read:network")),
):
    """
    ネットワークインターフェース詳細を取得 (ip -j addr show)

    Args:
        current_user: 現在のユーザー (read:network 権限必須)

    Returns:
        インターフェース詳細情報

    Raises:
        HTTPException: 取得失敗時
    """
    import datetime

    logger.info(f"Network interfaces-detail requested by={current_user.username}")
    audit_log.record(
        operation="network_interfaces_detail",
        user_id=current_user.user_id,
        target="network",
        status="attempt",
        details={},
    )
    try:
        result = sudo_wrapper.get_network_interfaces_detail()
        if result.get("returncode", result.get("status")) not in (0, "success", None):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("stderr") or result.get("message", "interfaces-detail unavailable"),
            )
        audit_log.record(
            operation="network_interfaces_detail",
            user_id=current_user.user_id,
            target="network",
            status="success",
            details={},
        )
        return {
            "interfaces": result.get("stdout", result.get("interfaces", "")),
            "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Network interfaces-detail failed: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


@router.get("/dns-config")
async def get_dns_config_detail(
    current_user: TokenData = Depends(require_permission("read:network")),
):
    """
    DNS設定詳細を取得 (/etc/resolv.conf + /etc/hosts)

    Args:
        current_user: 現在のユーザー (read:network 権限必須)

    Returns:
        DNS設定情報

    Raises:
        HTTPException: 取得失敗時
    """
    import datetime

    logger.info(f"Network dns-config requested by={current_user.username}")
    audit_log.record(
        operation="network_dns_config",
        user_id=current_user.user_id,
        target="network",
        status="attempt",
        details={},
    )
    try:
        result = sudo_wrapper.get_network_dns_config()
        if result.get("returncode", result.get("status")) not in (0, "success", None):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("stderr") or result.get("message", "dns-config unavailable"),
            )
        audit_log.record(
            operation="network_dns_config",
            user_id=current_user.user_id,
            target="network",
            status="success",
            details={},
        )
        return {
            "resolv_conf": result.get("stdout", result.get("resolv_conf", "")),
            "hosts": result.get("hosts", ""),
            "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Network dns-config failed: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


@router.get("/active-connections")
async def get_active_connections(
    current_user: TokenData = Depends(require_permission("read:network")),
):
    """
    アクティブ接続一覧を取得 (ss -tunp)

    Args:
        current_user: 現在のユーザー (read:network 権限必須)

    Returns:
        アクティブ接続情報

    Raises:
        HTTPException: 取得失敗時
    """
    import datetime

    logger.info(f"Network active-connections requested by={current_user.username}")
    audit_log.record(
        operation="network_active_connections",
        user_id=current_user.user_id,
        target="network",
        status="attempt",
        details={},
    )
    try:
        result = sudo_wrapper.get_network_active_connections()
        if result.get("returncode", result.get("status")) not in (0, "success", None):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("stderr") or result.get("message", "active-connections unavailable"),
            )
        audit_log.record(
            operation="network_active_connections",
            user_id=current_user.user_id,
            target="network",
            status="success",
            details={},
        )
        return {
            "connections": result.get("stdout", result.get("connections", "")),
            "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Network active-connections failed: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


# ===================================================================
# v0.40 追加エンドポイント: 特定IF詳細取得・設定変更（承認フロー）
# ===================================================================


@router.get("/interfaces/{interface_name}")
async def get_interface_detail(
    interface_name: str,
    current_user: TokenData = Depends(require_permission("read:network")),
):
    """
    特定ネットワークインターフェースの詳細を取得する。

    Args:
        interface_name: インターフェース名 (例: eth0, ens3)
        current_user: 現在のユーザー (read:network 権限必須)

    Returns:
        インターフェース詳細情報

    Raises:
        HTTPException 400: 不正なインターフェース名
        HTTPException 404: インターフェースが存在しない
    """
    if not validate_interface_name(interface_name):
        audit_log.record(
            operation="network_interface_detail",
            user_id=current_user.user_id,
            target=interface_name,
            status="denied",
            details={"reason": "invalid_interface_name"},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "error", "message": f"Invalid interface name: {interface_name}"},
        )

    logger.info(f"Network interface detail requested: if={interface_name} by={current_user.username}")

    audit_log.record(
        operation="network_interface_detail",
        user_id=current_user.user_id,
        target=interface_name,
        status="attempt",
        details={},
    )

    import datetime
    import subprocess

    try:
        proc = subprocess.run(
            ["/usr/sbin/ip", "-j", "addr", "show", "dev", interface_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            audit_log.record(
                operation="network_interface_detail",
                user_id=current_user.user_id,
                target=interface_name,
                status="failure",
                details={"stderr": proc.stderr},
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"status": "error", "message": f"Interface not found: {interface_name}"},
            )

        import json as _json

        iface_data = _json.loads(proc.stdout) if proc.stdout.strip() else []
        audit_log.record(
            operation="network_interface_detail",
            user_id=current_user.user_id,
            target=interface_name,
            status="success",
            details={},
        )
        return {
            "status": "success",
            "interface": iface_data,
            "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Network interface detail failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": str(e)},
        )


@router.patch("/interfaces/{interface_name}", status_code=status.HTTP_202_ACCEPTED)
async def update_interface_config(
    interface_name: str,
    req: NetworkInterfaceConfigRequest,
    current_user: TokenData = Depends(require_permission("write:network")),
):
    """
    ネットワークインターフェースのIP/CIDR/ゲートウェイ変更を承認フロー経由でリクエストする。

    変更は直接適用されず、承認フロー経由で実行される（危険操作）。

    Args:
        interface_name: 対象インターフェース名 (例: eth0)
        req: 変更内容（ip_cidr, gateway, reason）
        current_user: 現在のユーザー (write:network 権限必須)

    Returns:
        202 Accepted: 承認リクエストID

    Raises:
        HTTPException 400: 不正なIF名・IP形式
        HTTPException 403: 権限不足
    """
    # インターフェース名バリデーション
    if not validate_interface_name(interface_name):
        audit_log.record(
            operation="network_interface_config_request",
            user_id=current_user.user_id,
            target=interface_name,
            status="denied",
            details={"reason": "invalid_interface_name"},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "error", "message": f"Invalid interface name: {interface_name}"},
        )

    # IP/CIDR バリデーション
    if not validate_ip_cidr(req.ip_cidr):
        audit_log.record(
            operation="network_interface_config_request",
            user_id=current_user.user_id,
            target=interface_name,
            status="denied",
            details={"reason": "invalid_ip_cidr", "ip_cidr": req.ip_cidr},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"status": "error", "message": f"Invalid IP/CIDR format: {req.ip_cidr}"},
        )

    # ゲートウェイ バリデーション
    if not validate_ip_address(req.gateway):
        audit_log.record(
            operation="network_interface_config_request",
            user_id=current_user.user_id,
            target=interface_name,
            status="denied",
            details={"reason": "invalid_gateway", "gateway": req.gateway},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"status": "error", "message": f"Invalid gateway address: {req.gateway}"},
        )

    logger.info(
        f"Network interface config change requested: if={interface_name} "
        f"ip={req.ip_cidr} gw={req.gateway} by={current_user.username}"
    )

    audit_log.record(
        operation="network_interface_config_request",
        user_id=current_user.user_id,
        target=interface_name,
        status="attempt",
        details={"ip_cidr": req.ip_cidr, "gateway": req.gateway},
    )

    try:
        approval_req = await _approval_service.create_request(
            request_type="network_config_change",
            payload={
                "interface": interface_name,
                "ip_cidr": req.ip_cidr,
                "gateway": req.gateway,
            },
            reason=req.reason,
            requester_id=current_user.user_id,
            requester_name=current_user.email,
            requester_role=current_user.role,
        )

        audit_log.record(
            operation="network_interface_config_request",
            user_id=current_user.user_id,
            target=interface_name,
            status="success",
            details={
                "approval_id": approval_req.get("id"),
                "ip_cidr": req.ip_cidr,
                "gateway": req.gateway,
            },
        )

        return {
            "status": "pending_approval",
            "message": "ネットワーク設定変更リクエストを承認待ちキューに登録しました",
            "approval_id": approval_req.get("id"),
            "interface": interface_name,
            "ip_cidr": req.ip_cidr,
            "gateway": req.gateway,
        }

    except Exception as e:
        audit_log.record(
            operation="network_interface_config_request",
            user_id=current_user.user_id,
            target=interface_name,
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Network interface config request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": f"承認リクエスト作成失敗: {str(e)}"},
        )


@router.patch("/dns", status_code=status.HTTP_202_ACCEPTED)
async def update_dns_config(
    req: NetworkDnsConfigRequest,
    current_user: TokenData = Depends(require_permission("write:network")),
):
    """
    DNS設定変更を承認フロー経由でリクエストする。

    変更は直接適用されず、承認フロー経由で実行される（危険操作）。

    Args:
        req: DNS変更内容（dns1, dns2, reason）
        current_user: 現在のユーザー (write:network 権限必須)

    Returns:
        202 Accepted: 承認リクエストID

    Raises:
        HTTPException 422: 不正なIPアドレス形式
        HTTPException 403: 権限不足
    """
    # DNS1 バリデーション
    if not validate_ip_address(req.dns1):
        audit_log.record(
            operation="network_dns_config_request",
            user_id=current_user.user_id,
            target="dns",
            status="denied",
            details={"reason": "invalid_dns1", "dns1": req.dns1},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"status": "error", "message": f"Invalid DNS1 address: {req.dns1}"},
        )

    # DNS2 バリデーション（指定時のみ）
    if req.dns2 is not None and not validate_ip_address(req.dns2):
        audit_log.record(
            operation="network_dns_config_request",
            user_id=current_user.user_id,
            target="dns",
            status="denied",
            details={"reason": "invalid_dns2", "dns2": req.dns2},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"status": "error", "message": f"Invalid DNS2 address: {req.dns2}"},
        )

    logger.info(
        f"DNS config change requested: dns1={req.dns1} dns2={req.dns2} by={current_user.username}"
    )

    audit_log.record(
        operation="network_dns_config_request",
        user_id=current_user.user_id,
        target="dns",
        status="attempt",
        details={"dns1": req.dns1, "dns2": req.dns2},
    )

    try:
        payload: dict = {"dns1": req.dns1}
        if req.dns2:
            payload["dns2"] = req.dns2

        approval_req = await _approval_service.create_request(
            request_type="dns_config_change",
            payload=payload,
            reason=req.reason,
            requester_id=current_user.user_id,
            requester_name=current_user.email,
            requester_role=current_user.role,
        )

        audit_log.record(
            operation="network_dns_config_request",
            user_id=current_user.user_id,
            target="dns",
            status="success",
            details={"approval_id": approval_req.get("id"), "dns1": req.dns1, "dns2": req.dns2},
        )

        return {
            "status": "pending_approval",
            "message": "DNS設定変更リクエストを承認待ちキューに登録しました",
            "approval_id": approval_req.get("id"),
            "dns1": req.dns1,
            "dns2": req.dns2,
        }

    except Exception as e:
        audit_log.record(
            operation="network_dns_config_request",
            user_id=current_user.user_id,
            target="dns",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"DNS config request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": f"承認リクエスト作成失敗: {str(e)}"},
        )
