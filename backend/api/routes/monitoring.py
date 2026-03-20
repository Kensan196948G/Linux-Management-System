"""
システムリソース時系列モニタリング API

提供エンドポイント:
  GET /api/monitoring/metrics           - 現在のリソース使用量スナップショット
  GET /api/monitoring/history           - 過去N点の時系列データ（メモリ内）
  GET /api/monitoring/history/range     - 時間範囲指定の時系列データ（SQLite永続）
  GET /api/monitoring/trends/daily      - 日別平均トレンド（7日分）
  GET /api/monitoring/alerts            - リソースアラート一覧
  POST /api/monitoring/alerts/threshold - アラート閾値設定
  GET /api/monitoring/processes/top     - CPU/メモリ上位プロセス
  GET /api/monitoring/network/io        - ネットワークI/O統計
  GET /api/monitoring/disk/io           - ディスクI/O統計
  GET /api/monitoring/prometheus        - Prometheusスクレイプ形式メトリクス
"""

import json
import logging
import sqlite3
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import psutil
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from ...core import require_permission
from ...core.audit_log import audit_log
from ...core.auth import TokenData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

# メモリ内時系列バッファ（直近120点の高速アクセス用）
_HISTORY_MAXLEN = 120
_metrics_history: deque = deque(maxlen=_HISTORY_MAXLEN)

# SQLite 永続化設定
_METRICS_DB_PATH = Path("data/metrics_history.db")
_DB_RETENTION_DAYS = 7  # 7日分を保持

# 閾値設定ファイル
_THRESHOLD_FILE = Path("data/monitoring_thresholds.json")

# デフォルト閾値
DEFAULT_THRESHOLDS = {
    "cpu_warn": 80.0,
    "cpu_critical": 95.0,
    "mem_warn": 80.0,
    "mem_critical": 95.0,
    "disk_warn": 85.0,
    "disk_critical": 95.0,
}


# ===================================================================
# SQLite メトリクス永続化
# ===================================================================


def _get_db_connection() -> sqlite3.Connection:
    """メトリクス履歴 SQLite 接続を返す"""
    _METRICS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_METRICS_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_metrics_db() -> None:
    """メトリクス履歴テーブルを初期化"""
    with _get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics_history (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        REAL NOT NULL,
                timestamp TEXT NOT NULL,
                cpu       REAL NOT NULL DEFAULT 0,
                memory    REAL NOT NULL DEFAULT 0,
                disk      REAL NOT NULL DEFAULT 0,
                load1     REAL NOT NULL DEFAULT 0,
                load5     REAL NOT NULL DEFAULT 0,
                load15    REAL NOT NULL DEFAULT 0,
                mem_used  INTEGER NOT NULL DEFAULT 0,
                mem_total INTEGER NOT NULL DEFAULT 0
            )
        """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics_history(ts)")
        conn.commit()


def _persist_snapshot(snapshot: Dict[str, Any]) -> None:
    """スナップショットを SQLite に保存し、古いレコードを削除"""
    try:
        _init_metrics_db()
        cutoff = time.time() - (_DB_RETENTION_DAYS * 86400)
        with _get_db_connection() as conn:
            conn.execute(
                """INSERT INTO metrics_history
                   (ts, timestamp, cpu, memory, disk, load1, load5, load15, mem_used, mem_total)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot.get("ts", time.time()),
                    snapshot.get("timestamp", ""),
                    snapshot.get("cpu_percent", 0),
                    snapshot.get("mem_percent", 0),
                    snapshot.get("disk_percent", 0),
                    snapshot.get("load1", 0),
                    snapshot.get("load5", 0),
                    snapshot.get("load15", 0),
                    snapshot.get("mem_used", 0),
                    snapshot.get("mem_total", 0),
                ),
            )
            # 保持期間外レコードを削除
            conn.execute("DELETE FROM metrics_history WHERE ts < ?", (cutoff,))
            conn.commit()
    except Exception as e:
        logger.debug("メトリクスDB保存エラー（無視）: %s", e)


def _query_metrics_range(from_ts: float, to_ts: float, max_points: int = 1440) -> List[Dict[str, Any]]:
    """時間範囲でメトリクス履歴を取得（最大 max_points 点に間引き）"""
    try:
        _init_metrics_db()
        with _get_db_connection() as conn:
            rows = conn.execute(
                """SELECT ts, timestamp, cpu, memory, disk, load1, load5, load15, mem_used, mem_total
                   FROM metrics_history
                   WHERE ts BETWEEN ? AND ?
                   ORDER BY ts ASC""",
                (from_ts, to_ts),
            ).fetchall()

        # データ点数が多い場合は間引き
        records = [dict(r) for r in rows]
        if len(records) > max_points and max_points > 0:
            step = len(records) / max_points
            records = [records[int(i * step)] for i in range(max_points)]
        return records
    except Exception as e:
        logger.debug("メトリクスDB読み取りエラー: %s", e)
        return []


def _query_daily_averages(days: int = 7) -> List[Dict[str, Any]]:
    """日別平均値を返す（トレンドグラフ用）"""
    try:
        _init_metrics_db()
        cutoff = time.time() - (days * 86400)
        with _get_db_connection() as conn:
            rows = conn.execute(
                """SELECT
                       DATE(timestamp) as day,
                       ROUND(AVG(cpu), 1)    as avg_cpu,
                       ROUND(MAX(cpu), 1)    as max_cpu,
                       ROUND(AVG(memory), 1) as avg_memory,
                       ROUND(MAX(memory), 1) as max_memory,
                       ROUND(AVG(disk), 1)   as avg_disk,
                       COUNT(*)              as samples
                   FROM metrics_history
                   WHERE ts > ?
                   GROUP BY DATE(timestamp)
                   ORDER BY day ASC""",
                (cutoff,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.debug("日別平均取得エラー: %s", e)
        return []


# ===================================================================
# モデル
# ===================================================================


class MetricsSnapshot(BaseModel):
    """リソース使用量スナップショット"""

    timestamp: str
    cpu_percent: float
    cpu_count: int
    mem_total: int
    mem_used: int
    mem_percent: float
    swap_total: int
    swap_used: int
    swap_percent: float
    disk_total: int
    disk_used: int
    disk_percent: float
    load_avg_1: float
    load_avg_5: float
    load_avg_15: float


class NetworkIOStats(BaseModel):
    """ネットワークI/O統計"""

    interface: str
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int
    errin: int
    errout: int
    dropin: int
    dropout: int


class DiskIOStats(BaseModel):
    """ディスクI/O統計"""

    device: str
    read_count: int
    write_count: int
    read_bytes: int
    write_bytes: int
    read_time: int
    write_time: int


class TopProcess(BaseModel):
    """上位プロセス情報"""

    pid: int
    name: str
    cpu_percent: float
    mem_percent: float
    mem_rss: int
    status: str
    username: str


class ThresholdConfig(BaseModel):
    """アラート閾値設定"""

    cpu_warn: float = Field(default=80.0, ge=0, le=100)
    cpu_critical: float = Field(default=95.0, ge=0, le=100)
    mem_warn: float = Field(default=80.0, ge=0, le=100)
    mem_critical: float = Field(default=95.0, ge=0, le=100)
    disk_warn: float = Field(default=85.0, ge=0, le=100)
    disk_critical: float = Field(default=95.0, ge=0, le=100)


# ===================================================================
# 内部ヘルパー
# ===================================================================


def _load_thresholds() -> Dict[str, float]:
    """閾値設定をファイルから読み込む"""
    try:
        if _THRESHOLD_FILE.exists():
            return json.loads(_THRESHOLD_FILE.read_text())
    except Exception:
        pass
    return DEFAULT_THRESHOLDS.copy()


def _save_thresholds(config: Dict[str, float]) -> None:
    """閾値設定をファイルに保存"""
    _THRESHOLD_FILE.parent.mkdir(parents=True, exist_ok=True)
    _THRESHOLD_FILE.write_text(json.dumps(config, indent=2))


def _collect_snapshot() -> Dict[str, Any]:
    """現在のリソーススナップショットを収集"""
    cpu = psutil.cpu_percent(interval=0.1)
    cpu_count = psutil.cpu_count(logical=True) or 1
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    load = psutil.getloadavg()
    ts = datetime.now(timezone.utc).isoformat()

    return {
        "timestamp": ts,
        "cpu_percent": cpu,
        "cpu_count": cpu_count,
        "mem_total": mem.total,
        "mem_used": mem.used,
        "mem_percent": mem.percent,
        "swap_total": swap.total,
        "swap_used": swap.used,
        "swap_percent": swap.percent,
        "disk_total": disk.total,
        "disk_used": disk.used,
        "disk_percent": disk.percent,
        "load_avg_1": load[0],
        "load_avg_5": load[1],
        "load_avg_15": load[2],
    }


def _check_alerts(snapshot: Dict[str, Any], thresholds: Dict[str, float]) -> List[Dict[str, Any]]:
    """スナップショットとアラート閾値を比較し、アラートリストを返す"""
    alerts = []
    checks = [
        ("cpu_percent", "CPU使用率", thresholds["cpu_warn"], thresholds["cpu_critical"]),
        ("mem_percent", "メモリ使用率", thresholds["mem_warn"], thresholds["mem_critical"]),
        ("disk_percent", "ディスク使用率", thresholds["disk_warn"], thresholds["disk_critical"]),
    ]
    for key, label, warn, critical in checks:
        val = snapshot.get(key, 0)
        if val >= critical:
            alerts.append({"resource": key, "label": label, "value": val, "level": "critical", "threshold": critical})
        elif val >= warn:
            alerts.append({"resource": key, "label": label, "value": val, "level": "warning", "threshold": warn})
    return alerts


# ===================================================================
# エンドポイント
# ===================================================================


@router.get("/metrics", response_model=MetricsSnapshot)
async def get_current_metrics(
    current_user: TokenData = Depends(require_permission("read:system")),
) -> Dict[str, Any]:
    """現在のリソース使用量スナップショットを返す（メモリ内バッファとSQLiteに追記）"""
    snapshot = _collect_snapshot()
    _metrics_history.append(snapshot)
    _persist_snapshot(snapshot)  # SQLite 永続化

    audit_log.record(
        user_id=current_user.username,
        operation="monitoring_metrics",
        target="system",
        status="success",
    )
    return snapshot


@router.get("/history")
async def get_metrics_history(
    points: int = 60,
    current_user: TokenData = Depends(require_permission("read:system")),
) -> Dict[str, Any]:
    """過去N点分の時系列データを返す（Chart.js用）"""
    if points < 1 or points > _HISTORY_MAXLEN:
        points = min(max(points, 1), _HISTORY_MAXLEN)

    history = list(_metrics_history)[-points:]
    return {
        "status": "success",
        "points": len(history),
        "labels": [h["timestamp"] for h in history],
        "cpu": [h["cpu_percent"] for h in history],
        "memory": [h["mem_percent"] for h in history],
        "disk": [h["disk_percent"] for h in history],
        "load_avg_1": [h["load_avg_1"] for h in history],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/alerts")
async def get_resource_alerts(
    current_user: TokenData = Depends(require_permission("read:system")),
) -> Dict[str, Any]:
    """現在のリソース使用量に基づくアラート一覧"""
    snapshot = _collect_snapshot()
    thresholds = _load_thresholds()
    alerts = _check_alerts(snapshot, thresholds)

    return {
        "status": "success",
        "alerts": alerts,
        "alert_count": len(alerts),
        "timestamp": snapshot["timestamp"],
    }


@router.post("/alerts/threshold", status_code=status.HTTP_200_OK)
async def set_alert_thresholds(
    config: ThresholdConfig,
    current_user: TokenData = Depends(require_permission("write:system")),
) -> Dict[str, Any]:
    """アラート閾値を設定・保存する"""
    # warn < critical のバリデーション
    if config.cpu_warn >= config.cpu_critical:
        raise HTTPException(status_code=400, detail="cpu_warn must be less than cpu_critical")
    if config.mem_warn >= config.mem_critical:
        raise HTTPException(status_code=400, detail="mem_warn must be less than mem_critical")
    if config.disk_warn >= config.disk_critical:
        raise HTTPException(status_code=400, detail="disk_warn must be less than disk_critical")

    new_config = config.model_dump()
    _save_thresholds(new_config)

    audit_log.record(
        user_id=current_user.username,
        operation="monitoring_threshold_update",
        target="system",
        status="success",
        details=new_config,
    )
    return {"status": "success", "thresholds": new_config}


@router.get("/processes/top")
async def get_top_processes(
    sort_by: str = "cpu",
    limit: int = 15,
    current_user: TokenData = Depends(require_permission("read:system")),
) -> Dict[str, Any]:
    """CPU/メモリ上位プロセス一覧"""
    if sort_by not in ("cpu", "memory"):
        sort_by = "cpu"
    if limit < 1 or limit > 50:
        limit = 15

    processes = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "memory_info", "status", "username"]):
        try:
            info = proc.info
            processes.append(
                {
                    "pid": info["pid"],
                    "name": info["name"] or "unknown",
                    "cpu_percent": info["cpu_percent"] or 0.0,
                    "mem_percent": round(info["memory_percent"] or 0.0, 2),
                    "mem_rss": info["memory_info"].rss if info["memory_info"] else 0,
                    "status": info["status"] or "unknown",
                    "username": info["username"] or "unknown",
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    sort_key = "cpu_percent" if sort_by == "cpu" else "mem_percent"
    processes.sort(key=lambda x: x[sort_key], reverse=True)

    return {
        "status": "success",
        "processes": processes[:limit],
        "total_count": len(processes),
        "sort_by": sort_by,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/network/io")
async def get_network_io(
    current_user: TokenData = Depends(require_permission("read:system")),
) -> Dict[str, Any]:
    """ネットワークインターフェース別I/O統計"""
    net_io = psutil.net_io_counters(pernic=True)
    interfaces = []
    for iface, stats in net_io.items():
        interfaces.append(
            {
                "interface": iface,
                "bytes_sent": stats.bytes_sent,
                "bytes_recv": stats.bytes_recv,
                "packets_sent": stats.packets_sent,
                "packets_recv": stats.packets_recv,
                "errin": stats.errin,
                "errout": stats.errout,
                "dropin": stats.dropin,
                "dropout": stats.dropout,
            }
        )

    return {
        "status": "success",
        "interfaces": interfaces,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/disk/io")
async def get_disk_io(
    current_user: TokenData = Depends(require_permission("read:system")),
) -> Dict[str, Any]:
    """ディスクデバイス別I/O統計"""
    disk_io = psutil.disk_io_counters(perdisk=True)
    devices = []
    if disk_io:
        for device, stats in disk_io.items():
            devices.append(
                {
                    "device": device,
                    "read_count": stats.read_count,
                    "write_count": stats.write_count,
                    "read_bytes": stats.read_bytes,
                    "write_bytes": stats.write_bytes,
                    "read_time": stats.read_time,
                    "write_time": stats.write_time,
                }
            )

    return {
        "status": "success",
        "devices": devices,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/history/range")
async def get_metrics_history_range(
    hours: int = Query(default=1, ge=1, le=168, description="過去N時間（最大168=7日）"),
    max_points: int = Query(default=300, ge=10, le=1440, description="最大データ点数"),
    current_user: TokenData = Depends(require_permission("read:system")),
) -> Dict[str, Any]:
    """SQLite から時間範囲指定でメトリクス履歴を返す（Chart.js長期グラフ用）"""
    to_ts = time.time()
    from_ts = to_ts - (hours * 3600)

    records = _query_metrics_range(from_ts, to_ts, max_points)

    return {
        "status": "success",
        "hours": hours,
        "points": len(records),
        "from": datetime.fromtimestamp(from_ts, tz=timezone.utc).isoformat(),
        "to": datetime.fromtimestamp(to_ts, tz=timezone.utc).isoformat(),
        "labels": [r["timestamp"] for r in records],
        "cpu": [r["cpu"] for r in records],
        "memory": [r["memory"] for r in records],
        "disk": [r["disk"] for r in records],
        "load1": [r["load1"] for r in records],
    }


@router.get("/trends/daily")
async def get_daily_trends(
    days: int = Query(default=7, ge=1, le=30, description="集計日数"),
    current_user: TokenData = Depends(require_permission("read:system")),
) -> Dict[str, Any]:
    """日別平均・最大値トレンドを返す（週次レポート用）"""
    daily = _query_daily_averages(days)

    return {
        "status": "success",
        "days": days,
        "retention_days": _DB_RETENTION_DAYS,
        "data": daily,
        "labels": [d["day"] for d in daily],
        "avg_cpu": [d["avg_cpu"] for d in daily],
        "max_cpu": [d["max_cpu"] for d in daily],
        "avg_memory": [d["avg_memory"] for d in daily],
        "max_memory": [d["max_memory"] for d in daily],
        "avg_disk": [d["avg_disk"] for d in daily],
        "samples": [d["samples"] for d in daily],
    }


@router.delete("/history", status_code=status.HTTP_200_OK)
async def clear_metrics_history(
    current_user: TokenData = Depends(require_permission("write:system")),
) -> Dict[str, Any]:
    """メトリクス履歴を全削除（管理者向け）"""
    _metrics_history.clear()
    try:
        _init_metrics_db()
        with _get_db_connection() as conn:
            result = conn.execute("DELETE FROM metrics_history")
            deleted = result.rowcount
            conn.commit()
    except Exception as e:
        logger.warning("DB履歴削除エラー: %s", e)
        deleted = 0

    audit_log.record(
        operation="monitoring_history_clear",
        user_id=current_user.email,
        target="metrics_history",
        status="success",
        details={"deleted_rows": deleted},
    )
    return {"status": "success", "message": "メトリクス履歴を削除しました", "deleted_rows": deleted}


@router.get(
    "/prometheus",
    summary="Prometheusメトリクスエクスポート",
    description="Prometheus scrapeフォーマット (text/plain) でメトリクスを返します",
    response_class=PlainTextResponse,
)
async def get_prometheus_metrics(
    current_user: TokenData = Depends(require_permission("read:system")),
) -> str:
    """Prometheus/OpenMetrics形式でシステムメトリクスを返す"""
    snapshot = _collect_snapshot()
    thresholds = _load_thresholds()
    alerts = _check_alerts(snapshot, thresholds)
    ts_ms = int(time.time() * 1000)

    lines = [
        "# HELP linux_mgmt_cpu_percent CPU使用率(%)",
        "# TYPE linux_mgmt_cpu_percent gauge",
        f"linux_mgmt_cpu_percent {snapshot['cpu_percent']:.2f} {ts_ms}",
        "",
        "# HELP linux_mgmt_memory_percent メモリ使用率(%)",
        "# TYPE linux_mgmt_memory_percent gauge",
        f"linux_mgmt_memory_percent {snapshot['mem_percent']:.2f} {ts_ms}",
        "",
        "# HELP linux_mgmt_memory_used_bytes 使用中メモリ(bytes)",
        "# TYPE linux_mgmt_memory_used_bytes gauge",
        f"linux_mgmt_memory_used_bytes {snapshot.get('mem_used', 0)} {ts_ms}",
        "",
        "# HELP linux_mgmt_memory_total_bytes 総メモリ(bytes)",
        "# TYPE linux_mgmt_memory_total_bytes gauge",
        f"linux_mgmt_memory_total_bytes {snapshot.get('mem_total', 0)} {ts_ms}",
        "",
        "# HELP linux_mgmt_disk_percent ディスク使用率(%)",
        "# TYPE linux_mgmt_disk_percent gauge",
        f"linux_mgmt_disk_percent {snapshot['disk_percent']:.2f} {ts_ms}",
        "",
        "# HELP linux_mgmt_load_average_1m 1分ロードアベレージ",
        "# TYPE linux_mgmt_load_average_1m gauge",
        f"linux_mgmt_load_average_1m {snapshot['load_avg_1']:.2f} {ts_ms}",
        "",
        "# HELP linux_mgmt_load_average_5m 5分ロードアベレージ",
        "# TYPE linux_mgmt_load_average_5m gauge",
        f"linux_mgmt_load_average_5m {snapshot['load_avg_5']:.2f} {ts_ms}",
        "",
        "# HELP linux_mgmt_load_average_15m 15分ロードアベレージ",
        "# TYPE linux_mgmt_load_average_15m gauge",
        f"linux_mgmt_load_average_15m {snapshot['load_avg_15']:.2f} {ts_ms}",
        "",
        "# HELP linux_mgmt_active_alerts アクティブアラート数",
        "# TYPE linux_mgmt_active_alerts gauge",
        f"linux_mgmt_active_alerts {len(alerts)} {ts_ms}",
        "",
    ]

    # アラートごとのラベル付きメトリクス
    if alerts:
        lines += [
            "# HELP linux_mgmt_alert_severity アラート重要度 (1=warning, 2=critical)",
            "# TYPE linux_mgmt_alert_severity gauge",
        ]
        for alert in alerts:
            resource = alert.get("resource", "unknown").replace(" ", "_").lower()
            severity_val = 2 if alert.get("level") == "critical" else 1
            lines.append(
                f'linux_mgmt_alert_severity{{resource="{resource}", level="{alert.get("level", "unknown")}"}} '
                f"{severity_val} {ts_ms}"
            )
        lines.append("")

    audit_log.record(
        user_id=current_user.username,
        operation="monitoring_prometheus_export",
        target="system",
        status="success",
    )

    return "\n".join(lines) + "\n"
