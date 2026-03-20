"""
システム状態 API エンドポイント
"""

import glob as _glob
import logging
import subprocess
from datetime import datetime, timezone

import psutil
from fastapi import APIRouter, Depends

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData

logger = logging.getLogger(__name__)


# ===================================================================
# ヘルスコア計算ヘルパー
# ===================================================================


def _score_for_usage(
    value: float, warn_threshold: float, critical_threshold: float
) -> int:
    """使用率からスコア（0-100）を計算する。

    Args:
        value: 現在の使用率（0-100）
        warn_threshold: 警告閾値（この値以下なら60-100）
        critical_threshold: クリティカル閾値（この値以上で20以下）

    Returns:
        スコア 0-100
    """
    if value <= warn_threshold:
        return max(0, int(100 - (value / warn_threshold) * 40))
    elif value <= critical_threshold:
        range_pct = (value - warn_threshold) / (critical_threshold - warn_threshold)
        return max(0, int(60 - range_pct * 40))
    else:
        over = value - critical_threshold
        return max(0, int(20 - over * 4))


def _score_for_alerts(count: int) -> int:
    """アクティブアラート数からスコアを計算する。"""
    if count == 0:
        return 100
    elif count == 1:
        return 70
    elif count <= 3:
        return 50
    else:
        return max(0, 50 - (count - 3) * 10)


def _score_for_failed_services(count: int) -> int:
    """失敗サービス数からスコアを計算する。"""
    if count == 0:
        return 100
    elif count == 1:
        return 60
    else:
        return max(0, 60 - (count - 1) * 20)


def _status_label(score: int) -> str:
    """スコアからステータスラベルを返す。"""
    if score >= 90:
        return "excellent"
    elif score >= 70:
        return "good"
    elif score >= 50:
        return "warning"
    else:
        return "critical"


def _count_failed_services() -> int:
    """systemctl でフェイルしたサービス数を取得する（shell=False）。"""
    try:
        result = subprocess.run(
            ["systemctl", "list-units", "--state=failed", "--no-pager", "--no-legend"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        return len(lines)
    except Exception:
        return 0


# ===================================================================
# 詳細情報収集ヘルパー
# ===================================================================


def _collect_cpu_temperatures() -> list:
    """/sys/class/thermal/thermal_zone*/temp からCPU温度を収集する。"""
    cpu_temps = []
    for zone in _glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        try:
            with open(zone) as f:
                temp = int(f.read().strip()) / 1000.0
            zone_type = "unknown"
            try:
                with open(zone.replace("/temp", "/type")) as f:
                    zone_type = f.read().strip()
            except Exception:
                pass
            cpu_temps.append({"zone": zone_type, "temp_c": round(temp, 1)})
        except Exception:
            pass
    return cpu_temps


def _collect_memory_detail() -> dict:
    """/proc/meminfo からメモリ詳細情報を収集する。"""
    try:
        mem_info: dict = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mem_info[parts[0].rstrip(":")] = int(parts[1])
        return {
            "total_kb": mem_info.get("MemTotal", 0),
            "free_kb": mem_info.get("MemFree", 0),
            "available_kb": mem_info.get("MemAvailable", 0),
            "buffers_kb": mem_info.get("Buffers", 0),
            "cached_kb": mem_info.get("Cached", 0),
            "swap_total_kb": mem_info.get("SwapTotal", 0),
            "swap_free_kb": mem_info.get("SwapFree", 0),
        }
    except Exception as e:
        return {"error": str(e)}


def _collect_nic_stats() -> list:
    """/proc/net/dev からNIC統計情報を収集する（loopback除外）。"""
    try:
        with open("/proc/net/dev") as f:
            lines = f.readlines()[2:]
        stats = []
        for line in lines:
            parts = line.split()
            if len(parts) < 17:
                continue
            iface = parts[0].rstrip(":")
            if iface == "lo":
                continue
            stats.append(
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
        return stats
    except Exception as e:
        return [{"error": str(e)}]


def _collect_uptime() -> dict:
    """/proc/uptime からアップタイム情報を収集する。"""
    try:
        with open("/proc/uptime") as f:
            secs = float(f.read().split()[0])
        return {
            "seconds": secs,
            "days": int(secs // 86400),
            "hours": int((secs % 86400) // 3600),
            "minutes": int((secs % 3600) // 60),
        }
    except Exception:
        return {}


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
    info = {
        "cpu_temperatures": _collect_cpu_temperatures(),
        "memory_detail": _collect_memory_detail(),
        "network_interfaces": _collect_nic_stats(),
        "uptime": _collect_uptime(),
    }

    audit_log.record(
        operation="system_detailed_view",
        user_id=current_user.user_id,
        target="system",
        status="success",
    )

    return {"status": "success", "data": info}


@router.get("/health-score")
async def get_health_score(
    current_user: TokenData = Depends(require_permission("read:status")),
) -> dict:
    """システムヘルススコアを取得する（0-100の合成スコア）。

    各コンポーネントの重み付け:
        - CPU使用率: 30%
        - メモリ使用率: 25%
        - ディスク使用率: 25%
        - アクティブアラート数: 10%
        - 失敗サービス数: 10%

    Args:
        current_user: 現在のユーザー（read:status 権限必須）

    Returns:
        合成ヘルススコアとコンポーネント別詳細
    """
    # CPU使用率（0.1秒サンプリング）
    cpu_pct = psutil.cpu_percent(interval=0.1)
    cpu_score = _score_for_usage(cpu_pct, warn_threshold=80.0, critical_threshold=95.0)

    # メモリ使用率
    mem = psutil.virtual_memory()
    mem_pct = mem.percent
    mem_score = _score_for_usage(mem_pct, warn_threshold=80.0, critical_threshold=90.0)

    # ディスク使用率（ルートパーティション）
    disk = psutil.disk_usage("/")
    disk_pct = disk.percent
    disk_score = _score_for_usage(
        disk_pct, warn_threshold=80.0, critical_threshold=95.0
    )

    # アクティブアラート数（CPU/メモリ/ディスクの閾値超過をカウント）
    alerts_count = sum(
        [
            1 if cpu_pct > 90.0 else 0,
            1 if mem_pct > 90.0 else 0,
            1 if disk_pct > 90.0 else 0,
        ]
    )
    alerts_score = _score_for_alerts(alerts_count)

    # 失敗サービス数
    failed_count = _count_failed_services()
    services_score = _score_for_failed_services(failed_count)

    # 合成スコア（重み付け平均）
    overall_score = int(
        0.30 * cpu_score
        + 0.25 * mem_score
        + 0.25 * disk_score
        + 0.10 * alerts_score
        + 0.10 * services_score
    )

    audit_log.record(
        operation="health_score_view",
        user_id=current_user.user_id,
        target="system",
        status="success",
    )

    return {
        "score": overall_score,
        "status": _status_label(overall_score),
        "components": {
            "cpu": {
                "score": cpu_score,
                "value": round(cpu_pct, 1),
                "status": _status_label(cpu_score),
            },
            "memory": {
                "score": mem_score,
                "value": round(mem_pct, 1),
                "status": _status_label(mem_score),
            },
            "disk": {
                "score": disk_score,
                "value": round(disk_pct, 1),
                "status": _status_label(disk_score),
            },
            "alerts": {
                "score": alerts_score,
                "value": alerts_count,
                "status": _status_label(alerts_score),
            },
            "services": {
                "score": services_score,
                "value": failed_count,
                "status": _status_label(services_score),
            },
        },
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
