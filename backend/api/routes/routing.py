"""
ルーティング・ゲートウェイ管理 API エンドポイント（読み取り専用）

提供エンドポイント:
  GET /api/routing/routes     - ルーティングテーブル (ip route show)
  GET /api/routing/gateways   - デフォルトゲートウェイ情報
  GET /api/routing/arp        - ARP テーブル (ip neigh show)
  GET /api/routing/interfaces - インターフェース詳細 (ip addr show)
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/routing", tags=["routing"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class RoutingRoutesResponse(BaseModel):
    """ルーティングテーブルレスポンス"""

    status: str
    routes: list[Any] = Field(default_factory=list)
    timestamp: str


class RoutingGatewaysResponse(BaseModel):
    """デフォルトゲートウェイレスポンス"""

    status: str
    gateways: list[Any] = Field(default_factory=list)
    timestamp: str


class RoutingArpResponse(BaseModel):
    """ARP テーブルレスポンス"""

    status: str
    arp: list[Any] = Field(default_factory=list)
    timestamp: str


class RoutingInterfacesResponse(BaseModel):
    """インターフェース詳細レスポンス"""

    status: str
    interfaces: list[Any] = Field(default_factory=list)
    timestamp: str


# ===================================================================
# エンドポイント
# ===================================================================


@router.get("/routes", response_model=RoutingRoutesResponse)
async def get_routing_routes(
    current_user: TokenData = Depends(require_permission("read:routing")),
) -> RoutingRoutesResponse:
    """
    ルーティングテーブルを取得 (ip route show)

    Args:
        current_user: 現在のユーザー (read:routing 権限必須)

    Returns:
        ルーティングテーブル

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Routing routes requested by={current_user.username}")

    audit_log.record(
        operation="routing_routes",
        user_id=current_user.user_id,
        target="routing",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_routing_routes()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error":
            audit_log.record(
                operation="routing_routes",
                user_id=current_user.user_id,
                target="routing",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Routing data unavailable"),
            )

        audit_log.record(
            operation="routing_routes",
            user_id=current_user.user_id,
            target="routing",
            status="success",
            details={"count": len(parsed.get("routes", []))},
        )

        return RoutingRoutesResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="routing_routes",
            user_id=current_user.user_id,
            target="routing",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Routing routes failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Routing data retrieval failed: {str(e)}",
        )


@router.get("/gateways", response_model=RoutingGatewaysResponse)
async def get_routing_gateways(
    current_user: TokenData = Depends(require_permission("read:routing")),
) -> RoutingGatewaysResponse:
    """
    デフォルトゲートウェイ情報を取得 (ip route show default)

    Args:
        current_user: 現在のユーザー (read:routing 権限必須)

    Returns:
        デフォルトゲートウェイ情報

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Routing gateways requested by={current_user.username}")

    audit_log.record(
        operation="routing_gateways",
        user_id=current_user.user_id,
        target="routing",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_routing_gateways()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error":
            audit_log.record(
                operation="routing_gateways",
                user_id=current_user.user_id,
                target="routing",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Gateway data unavailable"),
            )

        audit_log.record(
            operation="routing_gateways",
            user_id=current_user.user_id,
            target="routing",
            status="success",
            details={"count": len(parsed.get("gateways", []))},
        )

        return RoutingGatewaysResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="routing_gateways",
            user_id=current_user.user_id,
            target="routing",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Routing gateways failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gateway data retrieval failed: {str(e)}",
        )


@router.get("/arp", response_model=RoutingArpResponse)
async def get_routing_arp(
    current_user: TokenData = Depends(require_permission("read:routing")),
) -> RoutingArpResponse:
    """
    ARP テーブルを取得 (ip neigh show)

    Args:
        current_user: 現在のユーザー (read:routing 権限必須)

    Returns:
        ARP テーブル

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Routing ARP requested by={current_user.username}")

    audit_log.record(
        operation="routing_arp",
        user_id=current_user.user_id,
        target="routing",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_routing_arp()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error":
            audit_log.record(
                operation="routing_arp",
                user_id=current_user.user_id,
                target="routing",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "ARP data unavailable"),
            )

        audit_log.record(
            operation="routing_arp",
            user_id=current_user.user_id,
            target="routing",
            status="success",
            details={"count": len(parsed.get("arp", []))},
        )

        return RoutingArpResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="routing_arp",
            user_id=current_user.user_id,
            target="routing",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Routing ARP failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ARP data retrieval failed: {str(e)}",
        )


@router.get("/interfaces", response_model=RoutingInterfacesResponse)
async def get_routing_interfaces(
    current_user: TokenData = Depends(require_permission("read:routing")),
) -> RoutingInterfacesResponse:
    """
    インターフェース詳細を取得 (ip addr show)

    Args:
        current_user: 現在のユーザー (read:routing 権限必須)

    Returns:
        インターフェース詳細情報

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Routing interfaces requested by={current_user.username}")

    audit_log.record(
        operation="routing_interfaces",
        user_id=current_user.user_id,
        target="routing",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_routing_interfaces()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error":
            audit_log.record(
                operation="routing_interfaces",
                user_id=current_user.user_id,
                target="routing",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Interface data unavailable"),
            )

        audit_log.record(
            operation="routing_interfaces",
            user_id=current_user.user_id,
            target="routing",
            status="success",
            details={"count": len(parsed.get("interfaces", []))},
        )

        return RoutingInterfacesResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="routing_interfaces",
            user_id=current_user.user_id,
            target="routing",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Routing interfaces failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Interface data retrieval failed: {str(e)}",
        )
