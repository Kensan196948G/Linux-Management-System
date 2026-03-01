"""
センサー管理 API エンドポイント（読み取り専用）

提供エンドポイント:
  GET /api/sensors/all         - 全センサー情報
  GET /api/sensors/temperature - 温度センサー（CPU/GPU/マザーボード）
  GET /api/sensors/fans        - ファン速度（RPM）
  GET /api/sensors/voltage     - 電圧センサー
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

router = APIRouter(prefix="/sensors", tags=["sensors"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class SensorsAllResponse(BaseModel):
    """全センサー情報レスポンス"""

    status: str
    source: str = ""
    sensors: Any = None
    timestamp: str


class SensorsTemperatureResponse(BaseModel):
    """温度センサーレスポンス"""

    status: str
    source: str = ""
    temperature: Any = None
    timestamp: str


class SensorsFansResponse(BaseModel):
    """ファン速度レスポンス"""

    status: str
    source: str = ""
    fans: Any = None
    timestamp: str


class SensorsVoltageResponse(BaseModel):
    """電圧センサーレスポンス"""

    status: str
    source: str = ""
    voltage: Any = None
    timestamp: str


# ===================================================================
# エンドポイント
# ===================================================================


@router.get("/all", response_model=SensorsAllResponse)
async def get_sensors_all(
    current_user: TokenData = Depends(require_permission("read:sensors")),
) -> SensorsAllResponse:
    """
    全センサー情報を取得 (sensors -j)

    Args:
        current_user: 現在のユーザー (read:sensors 権限必須)

    Returns:
        全センサー情報

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Sensors all requested by={current_user.username}")

    audit_log.record(
        operation="sensors_all",
        user_id=current_user.user_id,
        target="sensors",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_sensors_all()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error":
            audit_log.record(
                operation="sensors_all",
                user_id=current_user.user_id,
                target="sensors",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Sensor data unavailable"),
            )

        audit_log.record(
            operation="sensors_all",
            user_id=current_user.user_id,
            target="sensors",
            status="success",
            details={"source": parsed.get("source", "")},
        )

        return SensorsAllResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="sensors_all",
            user_id=current_user.user_id,
            target="sensors",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Sensors all failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sensor data retrieval failed: {str(e)}",
        )


@router.get("/temperature", response_model=SensorsTemperatureResponse)
async def get_sensors_temperature(
    current_user: TokenData = Depends(require_permission("read:sensors")),
) -> SensorsTemperatureResponse:
    """
    温度センサー情報を取得

    Args:
        current_user: 現在のユーザー (read:sensors 権限必須)

    Returns:
        温度センサー情報

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Sensors temperature requested by={current_user.username}")

    audit_log.record(
        operation="sensors_temperature",
        user_id=current_user.user_id,
        target="sensors",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_sensors_temperature()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error":
            audit_log.record(
                operation="sensors_temperature",
                user_id=current_user.user_id,
                target="sensors",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Temperature data unavailable"),
            )

        audit_log.record(
            operation="sensors_temperature",
            user_id=current_user.user_id,
            target="sensors",
            status="success",
            details={},
        )

        return SensorsTemperatureResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="sensors_temperature",
            user_id=current_user.user_id,
            target="sensors",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Sensors temperature failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Temperature data retrieval failed: {str(e)}",
        )


@router.get("/fans", response_model=SensorsFansResponse)
async def get_sensors_fans(
    current_user: TokenData = Depends(require_permission("read:sensors")),
) -> SensorsFansResponse:
    """
    ファン速度情報を取得 (RPM)

    Args:
        current_user: 現在のユーザー (read:sensors 権限必須)

    Returns:
        ファン速度情報

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Sensors fans requested by={current_user.username}")

    audit_log.record(
        operation="sensors_fans",
        user_id=current_user.user_id,
        target="sensors",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_sensors_fans()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error":
            audit_log.record(
                operation="sensors_fans",
                user_id=current_user.user_id,
                target="sensors",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Fan data unavailable"),
            )

        audit_log.record(
            operation="sensors_fans",
            user_id=current_user.user_id,
            target="sensors",
            status="success",
            details={},
        )

        return SensorsFansResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="sensors_fans",
            user_id=current_user.user_id,
            target="sensors",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Sensors fans failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fan data retrieval failed: {str(e)}",
        )


@router.get("/voltage", response_model=SensorsVoltageResponse)
async def get_sensors_voltage(
    current_user: TokenData = Depends(require_permission("read:sensors")),
) -> SensorsVoltageResponse:
    """
    電圧センサー情報を取得

    Args:
        current_user: 現在のユーザー (read:sensors 権限必須)

    Returns:
        電圧センサー情報

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Sensors voltage requested by={current_user.username}")

    audit_log.record(
        operation="sensors_voltage",
        user_id=current_user.user_id,
        target="sensors",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_sensors_voltage()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error":
            audit_log.record(
                operation="sensors_voltage",
                user_id=current_user.user_id,
                target="sensors",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Voltage data unavailable"),
            )

        audit_log.record(
            operation="sensors_voltage",
            user_id=current_user.user_id,
            target="sensors",
            status="success",
            details={},
        )

        return SensorsVoltageResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="sensors_voltage",
            user_id=current_user.user_id,
            target="sensors",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Sensors voltage failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Voltage data retrieval failed: {str(e)}",
        )
