"""システムリソースアラート管理APIルーター"""
import asyncio
import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

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


@router.get("/stream")
async def stream_alerts(
    interval: float = Query(default=10.0, ge=5.0, le=60.0, description="チェック間隔（秒）"),
    token: str = Query(..., description="JWT認証トークン"),
):
    """アラート状態をSSEでリアルタイム配信する。

    EventSource API 向け（Authorization ヘッダー非対応のためクエリパラメータ認証）。
    接続時に connected イベントを送出し、以後 interval 秒ごとにアラート状態を配信する。
    """
    from ...core.auth import decode_token

    user_data = decode_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid token")

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'connected', 'interval': interval})}\n\n"
            while True:
                try:
                    cpu = get_current_cpu_usage()
                    mem = get_current_memory_usage()
                    load = get_load_average()
                    disk_root = get_disk_usage_pct("/")
                    disk_home = get_disk_usage_pct("/home")

                    current_values = {
                        "cpu": cpu,
                        "memory": mem,
                        "load": load,
                        "disk:/": disk_root,
                        "disk:/home": disk_home,
                    }

                    active = []
                    for rule in DEFAULT_RULES:
                        if not rule.get("enabled"):
                            continue
                        resource = rule["resource"]
                        val = current_values.get(resource)
                        if val is None:
                            continue
                        triggered = (
                            (rule["comparison"] == "gte" and val >= rule["threshold"])
                            or (rule["comparison"] == "lte" and val <= rule["threshold"])
                        )
                        if triggered:
                            active.append({
                                "id": rule["id"],
                                "description": rule["description"],
                                "value": round(val, 1),
                                "threshold": rule["threshold"],
                            })

                    payload = json.dumps({
                        "type": "update",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "active_alerts": active,
                        "metrics": {k: round(v, 1) for k, v in current_values.items()},
                    })
                    yield f"data: {payload}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
