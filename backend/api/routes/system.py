"""
システム状態 API エンドポイント
"""

import glob as _glob
import logging

from fastapi import APIRouter, Depends

from ...core import get_current_user, require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])


# ===================================================================
# エンドポイント
# ===================================================================


@router.get("/status")
async def get_system_status(
    current_user: TokenData = Depends(require_permission("read:status")),
):
    """
    システム状態を取得

    Args:
        current_user: 現在のユーザー（read:status 権限必須）

    Returns:
        システム状態（CPU, メモリ, ディスク, 稼働時間）
    """
    logger.info(f"System status requested by: {current_user.username}")

    try:
        # sudo ラッパー経由でシステム状態を取得
        status_data = sudo_wrapper.get_system_status()

        # 監査ログ記録
        audit_log.record(
            operation="system_status_view",
            user_id=current_user.user_id,
            target="system",
            status="success",
        )

        return status_data

    except Exception as e:
        logger.error(f"Failed to get system status: {e}")

        # 監査ログ記録（失敗）
        audit_log.record(
            operation="system_status_view",
            user_id=current_user.user_id,
            target="system",
            status="failure",
            details={"error": str(e)},
        )

        raise


@router.get("/detailed")
async def get_detailed_system_info(
    current_user: TokenData = Depends(require_permission("read:status")),
) -> dict:
    """詳細なシステム情報を取得する（CPU温度/メモリ詳細/NIC統計/アップタイム）。

    Args:
        current_user: 現在のユーザー（read:status 権限必須）

    Returns:
        CPU温度・メモリ詳細・NICネットワーク統計・アップタイムの辞書
    """
    info: dict = {}

    # CPU温度（/sys/class/thermal/thermal_zone*/temp）
    cpu_temps = []
    for zone in _glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        try:
            with open(zone) as f:
                temp = int(f.read().strip()) / 1000.0
            zone_type_file = zone.replace("/temp", "/type")
            zone_type = "unknown"
            try:
                with open(zone_type_file) as f:
                    zone_type = f.read().strip()
            except Exception:
                pass
            cpu_temps.append({"zone": zone_type, "temp_c": round(temp, 1)})
        except Exception:
            pass
    info["cpu_temperatures"] = cpu_temps

    # メモリ詳細（/proc/meminfo）
    mem_info: dict = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    val = int(parts[1])
                    mem_info[key] = val
        info["memory_detail"] = {
            "total_kb": mem_info.get("MemTotal", 0),
            "free_kb": mem_info.get("MemFree", 0),
            "available_kb": mem_info.get("MemAvailable", 0),
            "buffers_kb": mem_info.get("Buffers", 0),
            "cached_kb": mem_info.get("Cached", 0),
            "swap_total_kb": mem_info.get("SwapTotal", 0),
            "swap_free_kb": mem_info.get("SwapFree", 0),
        }
    except Exception as e:
        info["memory_detail"] = {"error": str(e)}

    # NICネットワーク統計（/proc/net/dev）
    nic_stats = []
    try:
        with open("/proc/net/dev") as f:
            lines = f.readlines()[2:]  # ヘッダー2行をスキップ
        for line in lines:
            parts = line.split()
            if len(parts) < 17:
                continue
            iface = parts[0].rstrip(":")
            if iface == "lo":
                continue
            nic_stats.append(
                {
                    "interface": iface,
                    "rx_bytes": int(parts[1]),
                    "rx_packets": int(parts[2]),
                    "rx_errors": int(parts[3]),
                    "tx_bytes": int(parts[9]),
                    "tx_packets": int(parts[10]),
                    "tx_errors": int(parts[11]),
                }
            )
    except Exception as e:
        nic_stats = [{"error": str(e)}]
    info["network_interfaces"] = nic_stats

    # アップタイム（/proc/uptime）
    try:
        with open("/proc/uptime") as f:
            uptime_secs = float(f.read().split()[0])
        days = int(uptime_secs // 86400)
        hours = int((uptime_secs % 86400) // 3600)
        minutes = int((uptime_secs % 3600) // 60)
        info["uptime"] = {
            "seconds": uptime_secs,
            "days": days,
            "hours": hours,
            "minutes": minutes,
        }
    except Exception:
        info["uptime"] = {}

    audit_log.record(
        operation="system_detailed_view",
        user_id=current_user.user_id,
        target="system",
        status="success",
    )

    return {"status": "success", "data": info}
