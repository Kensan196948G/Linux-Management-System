"""
帯域幅監視 API エンドポイント

提供エンドポイント:
  GET /api/bandwidth/interfaces          - インターフェース一覧
  GET /api/bandwidth/summary             - 帯域幅サマリ（vnstat/ip）
  GET /api/bandwidth/daily               - 日別統計
  GET /api/bandwidth/hourly              - 時間別統計
  GET /api/bandwidth/live                - リアルタイム帯域幅
  GET /api/bandwidth/top                 - 全IFトラフィック
"""

import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bandwidth", tags=["bandwidth"])

# インターフェース名パターン（バリデーション）
import re
_IFACE_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{1,32}$")


def _validate_iface(iface: str) -> None:
    if not _IFACE_PATTERN.match(iface):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid interface name: {iface}",
        )


# ===================================================================
# レスポンスモデル
# ===================================================================


class BandwidthInterfaceResponse(BaseModel):
    """インターフェース一覧レスポンス"""

    status: str
    interfaces: List[str] = []
    timestamp: str = ""


class BandwidthSummaryResponse(BaseModel):
    """帯域幅サマリレスポンス"""

    status: str
    source: str = ""
    interface: Optional[str] = None
    data: Any = None
    rx_bytes: Optional[int] = None
    tx_bytes: Optional[int] = None
    message: Optional[str] = None
    timestamp: str = ""


class BandwidthLiveResponse(BaseModel):
    """リアルタイム帯域幅レスポンス"""

    status: str
    interface: str = ""
    rx_bps: int = 0
    tx_bps: int = 0
    rx_kbps: int = 0
    tx_kbps: int = 0
    timestamp: str = ""


class BandwidthTopResponse(BaseModel):
    """全IFトラフィックレスポンス"""

    status: str
    interfaces: Any = []
    timestamp: str = ""


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/interfaces",
    response_model=BandwidthInterfaceResponse,
    summary="インターフェース一覧",
    description="利用可能なネットワークインターフェース一覧を取得します",
)
async def get_interfaces(
    current_user: TokenData = Depends(require_permission("read:network")),
) -> BandwidthInterfaceResponse:
    """インターフェース一覧を取得する"""
    try:
        result = sudo_wrapper.get_bandwidth_interfaces()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="bandwidth_interfaces_read",
            user_id=current_user.user_id,
            target="all",
            status="success",
        )
        return BandwidthInterfaceResponse(
            status=parsed.get("status", "ok"),
            interfaces=parsed.get("interfaces", []),
            timestamp=parsed.get("timestamp", ""),
        )
    except SudoWrapperError as e:
        logger.error("Bandwidth interfaces error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"インターフェース一覧取得エラー: {e}",
        )


@router.get(
    "/summary",
    response_model=BandwidthSummaryResponse,
    summary="帯域幅サマリ",
    description="vnstat または ip -s link を使用して帯域幅統計サマリを取得します",
)
async def get_bandwidth_summary(
    iface: str = Query(default="", description="インターフェース名（省略時: 全体）", max_length=32),
    current_user: TokenData = Depends(require_permission("read:network")),
) -> BandwidthSummaryResponse:
    """帯域幅サマリを取得する"""
    if iface:
        _validate_iface(iface)
    try:
        result = sudo_wrapper.get_bandwidth_summary(iface)
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="bandwidth_summary_read",
            user_id=current_user.user_id,
            target=iface or "all",
            status="success",
        )
        return BandwidthSummaryResponse(
            status=parsed.get("status", "ok"),
            source=parsed.get("source", ""),
            interface=parsed.get("interface") or (iface if iface else None),
            data=parsed.get("data"),
            rx_bytes=parsed.get("rx_bytes"),
            tx_bytes=parsed.get("tx_bytes"),
            message=parsed.get("message"),
            timestamp=parsed.get("timestamp", ""),
        )
    except (SudoWrapperError, ValueError) as e:
        logger.error("Bandwidth summary error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"帯域幅サマリ取得エラー: {e}",
        )


@router.get(
    "/daily",
    response_model=BandwidthSummaryResponse,
    summary="日別帯域幅統計",
    description="vnstat の日別トラフィック統計を取得します",
)
async def get_bandwidth_daily(
    iface: str = Query(default="", description="インターフェース名", max_length=32),
    current_user: TokenData = Depends(require_permission("read:network")),
) -> BandwidthSummaryResponse:
    """日別帯域幅統計を取得する"""
    if iface:
        _validate_iface(iface)
    try:
        result = sudo_wrapper.get_bandwidth_daily(iface)
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="bandwidth_daily_read",
            user_id=current_user.user_id,
            target=iface or "all",
            status="success",
        )
        return BandwidthSummaryResponse(
            status=parsed.get("status", "ok"),
            source=parsed.get("source", "vnstat"),
            interface=iface or None,
            data=parsed.get("data"),
            message=parsed.get("message"),
            timestamp=parsed.get("timestamp", ""),
        )
    except (SudoWrapperError, ValueError) as e:
        logger.error("Bandwidth daily error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"日別帯域幅取得エラー: {e}",
        )


@router.get(
    "/hourly",
    response_model=BandwidthSummaryResponse,
    summary="時間別帯域幅統計",
    description="vnstat の時間別トラフィック統計を取得します",
)
async def get_bandwidth_hourly(
    iface: str = Query(default="", description="インターフェース名", max_length=32),
    current_user: TokenData = Depends(require_permission("read:network")),
) -> BandwidthSummaryResponse:
    """時間別帯域幅統計を取得する"""
    if iface:
        _validate_iface(iface)
    try:
        result = sudo_wrapper.get_bandwidth_hourly(iface)
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="bandwidth_hourly_read",
            user_id=current_user.user_id,
            target=iface or "all",
            status="success",
        )
        return BandwidthSummaryResponse(
            status=parsed.get("status", "ok"),
            source=parsed.get("source", "vnstat"),
            interface=iface or None,
            data=parsed.get("data"),
            message=parsed.get("message"),
            timestamp=parsed.get("timestamp", ""),
        )
    except (SudoWrapperError, ValueError) as e:
        logger.error("Bandwidth hourly error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"時間別帯域幅取得エラー: {e}",
        )


@router.get(
    "/live",
    response_model=BandwidthLiveResponse,
    summary="リアルタイム帯域幅",
    description="1秒間サンプリングによるリアルタイム帯域幅（bps）を取得します",
)
async def get_bandwidth_live(
    iface: str = Query(default="", description="インターフェース名", max_length=32),
    current_user: TokenData = Depends(require_permission("read:network")),
) -> BandwidthLiveResponse:
    """リアルタイム帯域幅を取得する"""
    if iface:
        _validate_iface(iface)
    try:
        result = sudo_wrapper.get_bandwidth_live(iface)
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="bandwidth_live_read",
            user_id=current_user.user_id,
            target=iface or "default",
            status="success",
        )
        return BandwidthLiveResponse(
            status=parsed.get("status", "ok"),
            interface=parsed.get("interface", iface),
            rx_bps=parsed.get("rx_bps", 0),
            tx_bps=parsed.get("tx_bps", 0),
            rx_kbps=parsed.get("rx_kbps", 0),
            tx_kbps=parsed.get("tx_kbps", 0),
            timestamp=parsed.get("timestamp", ""),
        )
    except (SudoWrapperError, ValueError) as e:
        logger.error("Bandwidth live error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"リアルタイム帯域幅取得エラー: {e}",
        )


@router.get(
    "/top",
    response_model=BandwidthTopResponse,
    summary="全IF累積トラフィック",
    description="全インターフェースの累積送受信バイト数を取得します",
)
async def get_bandwidth_top(
    current_user: TokenData = Depends(require_permission("read:network")),
) -> BandwidthTopResponse:
    """全IFトラフィックを取得する"""
    try:
        result = sudo_wrapper.get_bandwidth_top()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="bandwidth_top_read",
            user_id=current_user.user_id,
            target="all",
            status="success",
        )
        return BandwidthTopResponse(
            status=parsed.get("status", "ok"),
            interfaces=parsed.get("interfaces", []),
            timestamp=parsed.get("timestamp", ""),
        )
    except SudoWrapperError as e:
        logger.error("Bandwidth top error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"トラフィック統計取得エラー: {e}",
        )
