"""
ネットワーク管理 API エンドポイント（読み取り専用）

提供エンドポイント:
  GET /api/network/interfaces   - インターフェース一覧
  GET /api/network/stats        - インターフェース統計
  GET /api/network/connections  - アクティブな接続
  GET /api/network/routes       - ルーティングテーブル
  GET /api/network/dns          - DNS設定
"""

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...core import get_current_user, require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

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

            proc = _sp.run(
                ["/usr/sbin/ip", "-j", "addr", "show"],
                capture_output=True, text=True, timeout=10
            )
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
