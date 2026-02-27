"""
ハードウェア管理 API エンドポイント（読み取り専用）

提供エンドポイント:
  GET /api/hardware/disks       - ブロックデバイス一覧
  GET /api/hardware/disk_usage  - ディスク使用量
  GET /api/hardware/smart       - SMART情報 (?device=/dev/sda)
  GET /api/hardware/sensors     - 温度センサー
  GET /api/hardware/memory      - メモリ情報
"""

import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hardware", tags=["hardware"])

# デバイスパスのバリデーションパターン
DEVICE_PATTERN = re.compile(
    r"^/dev/(sd[a-z]|nvme[0-9]n[0-9]|vd[a-z]|xvd[a-z]|hd[a-z])$"
)


# ===================================================================
# レスポンスモデル
# ===================================================================


class HardwareDisksResponse(BaseModel):
    """ブロックデバイス一覧レスポンス"""

    status: str
    disks: list[Any] = Field(default_factory=list)
    timestamp: str


class DiskUsageEntry(BaseModel):
    """ディスク使用量エントリ"""

    filesystem: str
    size_kb: int
    used_kb: int
    avail_kb: int
    use_percent: int
    mountpoint: str


class HardwareDiskUsageResponse(BaseModel):
    """ディスク使用量レスポンス"""

    status: str
    usage: list[Any] = Field(default_factory=list)
    timestamp: str


class HardwareSmartResponse(BaseModel):
    """SMART情報レスポンス"""

    status: str
    device: str
    smart: Any = None
    timestamp: str


class HardwareSensorsResponse(BaseModel):
    """温度センサーレスポンス"""

    status: str
    source: str = ""
    sensors: Any = None
    timestamp: str


class MemoryInfo(BaseModel):
    """メモリ情報"""

    total_kb: int
    free_kb: int
    available_kb: int
    buffers_kb: int
    cached_kb: int
    swap_total_kb: int
    swap_free_kb: int


class HardwareMemoryResponse(BaseModel):
    """メモリ情報レスポンス"""

    status: str
    memory: Any = None
    timestamp: str


# ===================================================================
# エンドポイント
# ===================================================================


@router.get("/disks", response_model=HardwareDisksResponse)
async def get_disks(
    current_user: TokenData = Depends(require_permission("read:hardware")),
) -> HardwareDisksResponse:
    """
    ブロックデバイス一覧を取得 (lsblk -J)

    Args:
        current_user: 現在のユーザー (read:hardware 権限必須)

    Returns:
        ブロックデバイス一覧

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Hardware disks requested by={current_user.username}")

    audit_log.record(
        operation="hardware_disks",
        user_id=current_user.user_id,
        target="hardware",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_hardware_disks()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error" or result.get("status") == "error":
            audit_log.record(
                operation="hardware_disks",
                user_id=current_user.user_id,
                target="hardware",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Hardware disk info unavailable"),
            )

        audit_log.record(
            operation="hardware_disks",
            user_id=current_user.user_id,
            target="hardware",
            status="success",
            details={"count": len(result.get("disks", []))},
        )

        return HardwareDisksResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="hardware_disks",
            user_id=current_user.user_id,
            target="hardware",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Hardware disks failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Hardware disk retrieval failed: {str(e)}",
        )


@router.get("/disk_usage", response_model=HardwareDiskUsageResponse)
async def get_disk_usage(
    current_user: TokenData = Depends(require_permission("read:hardware")),
) -> HardwareDiskUsageResponse:
    """
    ディスク使用量を取得 (df -P)

    Args:
        current_user: 現在のユーザー (read:hardware 権限必須)

    Returns:
        マウントポイント別のディスク使用量

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Hardware disk_usage requested by={current_user.username}")

    audit_log.record(
        operation="hardware_disk_usage",
        user_id=current_user.user_id,
        target="hardware",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_hardware_disk_usage()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error" or result.get("status") == "error":
            audit_log.record(
                operation="hardware_disk_usage",
                user_id=current_user.user_id,
                target="hardware",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Disk usage unavailable"),
            )

        audit_log.record(
            operation="hardware_disk_usage",
            user_id=current_user.user_id,
            target="hardware",
            status="success",
            details={"count": len(result.get("usage", []))},
        )

        return HardwareDiskUsageResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="hardware_disk_usage",
            user_id=current_user.user_id,
            target="hardware",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Hardware disk_usage failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Disk usage retrieval failed: {str(e)}",
        )


@router.get("/smart", response_model=HardwareSmartResponse)
async def get_smart(
    device: str = Query(
        ...,
        description="デバイスパス (例: /dev/sda)",
        min_length=8,
        max_length=20,
    ),
    current_user: TokenData = Depends(require_permission("read:hardware")),
) -> HardwareSmartResponse:
    """
    SMART情報を取得 (smartctl -j -a)

    Args:
        device: デバイスパス (/dev/sda など)
        current_user: 現在のユーザー (read:hardware 権限必須)

    Returns:
        SMART情報

    Raises:
        HTTPException: 取得失敗時 / 不正なデバイスパス
    """
    # APIレベルでのデバイスパス検証
    if not DEVICE_PATTERN.match(device):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid device path: {device}. "
            "Allowed: /dev/sd[a-z], /dev/nvme[0-9]n[0-9], /dev/vd[a-z]",
        )

    logger.info(f"Hardware SMART requested: device={device}, by={current_user.username}")

    audit_log.record(
        operation="hardware_smart",
        user_id=current_user.user_id,
        target=device,
        status="attempt",
        details={"device": device},
    )

    try:
        result = sudo_wrapper.get_hardware_smart(device)
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error" or result.get("status") == "error":
            audit_log.record(
                operation="hardware_smart",
                user_id=current_user.user_id,
                target=device,
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "SMART data unavailable"),
            )

        audit_log.record(
            operation="hardware_smart",
            user_id=current_user.user_id,
            target=device,
            status="success",
            details={"device": device},
        )

        return HardwareSmartResponse(**parsed)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except SudoWrapperError as e:
        audit_log.record(
            operation="hardware_smart",
            user_id=current_user.user_id,
            target=device,
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Hardware SMART failed: device={device}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"SMART data retrieval failed: {str(e)}",
        )


@router.get("/sensors", response_model=HardwareSensorsResponse)
async def get_sensors(
    current_user: TokenData = Depends(require_permission("read:hardware")),
) -> HardwareSensorsResponse:
    """
    温度センサー情報を取得

    Args:
        current_user: 現在のユーザー (read:hardware 権限必須)

    Returns:
        センサー情報

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Hardware sensors requested by={current_user.username}")

    audit_log.record(
        operation="hardware_sensors",
        user_id=current_user.user_id,
        target="hardware",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_hardware_sensors()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error" or result.get("status") == "error":
            audit_log.record(
                operation="hardware_sensors",
                user_id=current_user.user_id,
                target="hardware",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Sensor data unavailable"),
            )

        audit_log.record(
            operation="hardware_sensors",
            user_id=current_user.user_id,
            target="hardware",
            status="success",
            details={},
        )

        return HardwareSensorsResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="hardware_sensors",
            user_id=current_user.user_id,
            target="hardware",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Hardware sensors failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sensor data retrieval failed: {str(e)}",
        )


@router.get("/memory", response_model=HardwareMemoryResponse)
async def get_memory(
    current_user: TokenData = Depends(require_permission("read:hardware")),
) -> HardwareMemoryResponse:
    """
    メモリ情報を取得 (/proc/meminfo)

    Args:
        current_user: 現在のユーザー (read:hardware 権限必須)

    Returns:
        メモリ情報

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Hardware memory requested by={current_user.username}")

    audit_log.record(
        operation="hardware_memory",
        user_id=current_user.user_id,
        target="hardware",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_hardware_memory()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error" or result.get("status") == "error":
            audit_log.record(
                operation="hardware_memory",
                user_id=current_user.user_id,
                target="hardware",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Memory info unavailable"),
            )

        audit_log.record(
            operation="hardware_memory",
            user_id=current_user.user_id,
            target="hardware",
            status="success",
            details={},
        )

        return HardwareMemoryResponse(**parsed)

    except SudoWrapperError as e:
        # sudoが使えない環境（NoNewPrivileges等）は /proc/meminfo から直接読む
        logger.warning(f"Sudo unavailable, falling back to /proc/meminfo: {e}")
        try:
            mem = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    key, _, val = line.partition(":")
                    mem[key.strip()] = int(val.split()[0]) if val.split() else 0
            parsed = {
                "status": "success",
                "memory": {
                    "total_kb": mem.get("MemTotal", 0),
                    "free_kb": mem.get("MemFree", 0),
                    "available_kb": mem.get("MemAvailable", 0),
                    "buffers_kb": mem.get("Buffers", 0),
                    "cached_kb": mem.get("Cached", 0),
                    "swap_total_kb": mem.get("SwapTotal", 0),
                    "swap_free_kb": mem.get("SwapFree", 0),
                },
                "timestamp": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            audit_log.record(
                operation="hardware_memory",
                user_id=current_user.user_id,
                target="hardware",
                status="success",
                details={"source": "proc_fallback"},
            )
            return HardwareMemoryResponse(**parsed)
        except Exception as fe:
            logger.error(f"Hardware memory fallback failed: {fe}")
        audit_log.record(
            operation="hardware_memory",
            user_id=current_user.user_id,
            target="hardware",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Hardware memory failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Memory info retrieval failed: {str(e)}",
        )
