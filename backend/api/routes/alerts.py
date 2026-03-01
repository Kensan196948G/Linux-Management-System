"""システムリソースアラート管理APIルーター"""
from datetime import datetime, timezone
import os

from fastapi import APIRouter, Depends, HTTPException

from ...core import require_permission
from ...core.auth import TokenData

router = APIRouter(prefix="/alerts", tags=["alerts"])

# デフォルトアラートルール（設定ファイルがない場合）
DEFAULT_RULES = [
    {"id": "cpu-high", "resource": "cpu", "threshold": 90.0, "comparison": "gte", "enabled": True, "description": "CPU使用率90%以上"},
    {"id": "mem-high", "resource": "memory", "threshold": 85.0, "comparison": "gte", "enabled": True, "description": "メモリ使用率85%以上"},
    {"id": "disk-root", "resource": "disk:/", "threshold": 80.0, "comparison": "gte", "enabled": True, "description": "ルートディスク使用率80%以上"},
    {"id": "disk-home", "resource": "disk:/home", "threshold": 90.0, "comparison": "gte", "enabled": True, "description": "/homeディスク使用率90%以上"},
    {"id": "load-high", "resource": "load", "threshold": 4.0, "comparison": "gte", "enabled": True, "description": "ロードアベレージ4.0以上"},
]


def get_current_cpu_usage() -> float:
    """CPU使用率を /proc/stat から計算（2回サンプリング）"""
    import time

    def read_cpu():
        try:
            with open("/proc/stat", "r") as f:
                line = f.readline()
            parts = line.split()
            total = sum(int(x) for x in parts[1:])
            idle = int(parts[4])
            return total, idle
        except Exception:
            return 0, 0

    t1, i1 = read_cpu()
    time.sleep(0.1)
    t2, i2 = read_cpu()
    diff_t = t2 - t1
    diff_i = i2 - i1
    if diff_t == 0:
        return 0.0
    return round((1 - diff_i / diff_t) * 100, 1)


def get_current_memory_usage() -> float:
    """メモリ使用率を /proc/meminfo から計算"""
    try:
        mem = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mem[parts[0].rstrip(":")] = int(parts[1])
        total = mem.get("MemTotal", 1)
        available = mem.get("MemAvailable", total)
        used = total - available
        return round(used / total * 100, 1)
    except Exception:
        return 0.0


def get_disk_usage_pct(path: str) -> float:
    """ディスク使用率を取得"""
    try:
        stat = os.statvfs(path)
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bfree * stat.f_frsize
        if total == 0:
            return 0.0
        return round((total - free) / total * 100, 1)
    except Exception:
        return 0.0


def get_load_average() -> float:
    """ロードアベレージ（1分）を取得"""
    try:
        with open("/proc/loadavg", "r") as f:
            return float(f.read().split()[0])
    except Exception:
        return 0.0


@router.get("/rules")
async def get_alert_rules(current_user: TokenData = Depends(require_permission("read:alerts"))):
    """アラートルール一覧"""
    return {"rules": DEFAULT_RULES, "count": len(DEFAULT_RULES)}


@router.get("/active")
async def get_active_alerts(current_user: TokenData = Depends(require_permission("read:alerts"))):
    """アクティブなアラート一覧（現在値が閾値超過）"""
    try:
        cpu = get_current_cpu_usage()
        mem = get_current_memory_usage()
        load = get_load_average()
        disk_root = get_disk_usage_pct("/")
        disk_home = get_disk_usage_pct("/home")

        current_values = {
            "cpu": cpu, "memory": mem, "load": load,
            "disk:/": disk_root, "disk:/home": disk_home
        }

        active = []
        for rule in DEFAULT_RULES:
            if not rule["enabled"]:
                continue
            resource = rule["resource"]
            current = current_values.get(resource, 0.0)
            triggered = current >= rule["threshold"] if rule["comparison"] == "gte" else current <= rule["threshold"]
            if triggered:
                active.append({
                    **rule,
                    "current_value": current,
                    "triggered_at": datetime.now(timezone.utc).isoformat()
                })

        return {
            "active_alerts": active,
            "count": len(active),
            "current_values": current_values,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/summary")
async def get_alerts_summary(current_user: TokenData = Depends(require_permission("read:alerts"))):
    """アラートサマリー（ルール数/アクティブ数）"""
    try:
        cpu = get_current_cpu_usage()
        mem = get_current_memory_usage()
        load = get_load_average()
        return {
            "total_rules": len(DEFAULT_RULES),
            "enabled_rules": sum(1 for r in DEFAULT_RULES if r["enabled"]),
            "current_cpu": cpu,
            "current_memory": mem,
            "current_load": load,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
