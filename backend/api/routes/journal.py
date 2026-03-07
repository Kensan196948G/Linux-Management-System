"""systemdジャーナルログ管理APIルーター"""

import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.core.auth import TokenData, require_permission
from backend.core.sudo_wrapper import sudo_wrapper

router = APIRouter()


@router.get("/list")
async def get_journal_list(
    lines: int = Query(default=100, ge=1, le=1000),
    current_user: Annotated[TokenData, Depends(require_permission("read:journal"))] = None,
):
    """ジャーナルログ一覧を取得"""
    try:
        result = sudo_wrapper.get_journal_list(lines)
        log_lines = [ln for ln in result["stdout"].splitlines() if ln]
        return {"logs": log_lines, "count": len(log_lines), "timestamp": datetime.now(timezone.utc).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/units")
async def get_journal_units(
    current_user: Annotated[TokenData, Depends(require_permission("read:journal"))] = None,
):
    """systemdユニット一覧を取得"""
    try:
        result = sudo_wrapper.get_journal_units()
        units = [ln for ln in result["stdout"].splitlines() if ln]
        return {"units": units, "count": len(units)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/unit-logs/{unit_name}")
async def get_unit_logs(
    unit_name: str,
    current_user: Annotated[TokenData, Depends(require_permission("read:journal"))] = None,
):
    """特定ユニットのログを取得"""
    if not re.match(r"^[a-zA-Z0-9._@:-]+$", unit_name):
        raise HTTPException(status_code=400, detail="Invalid unit name")
    try:
        result = sudo_wrapper.get_journal_unit_logs(unit_name)
        log_lines = [ln for ln in result["stdout"].splitlines() if ln]
        return {"unit": unit_name, "logs": log_lines, "count": len(log_lines)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/boot-logs")
async def get_boot_logs(
    current_user: Annotated[TokenData, Depends(require_permission("read:journal"))] = None,
):
    """ブートログを取得"""
    try:
        result = sudo_wrapper.get_journal_boot_logs()
        log_lines = [ln for ln in result["stdout"].splitlines() if ln]
        return {"logs": log_lines, "count": len(log_lines)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/kernel-logs")
async def get_kernel_logs(
    current_user: Annotated[TokenData, Depends(require_permission("read:journal"))] = None,
):
    """カーネルログを取得"""
    try:
        result = sudo_wrapper.get_journal_kernel_logs()
        log_lines = [ln for ln in result["stdout"].splitlines() if ln]
        return {"logs": log_lines, "count": len(log_lines)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/priority-logs")
async def get_priority_logs(
    priority: str = Query(default="err"),
    current_user: Annotated[TokenData, Depends(require_permission("read:journal"))] = None,
):
    """優先度別ログを取得"""
    ALLOWED = ["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"]
    if priority not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"Invalid priority. Allowed: {ALLOWED}")
    try:
        result = sudo_wrapper.get_journal_priority_logs(priority)
        log_lines = [ln for ln in result["stdout"].splitlines() if ln]
        return {"priority": priority, "logs": log_lines, "count": len(log_lines)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ===================================================================
# 高度フィルタ（時間範囲・ユニット・優先度複合検索）
# ===================================================================

_ALLOWED_PRIORITIES = frozenset(["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"])
_ALLOWED_UNITS_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.@]+$")


def _validate_unit_name(unit: str) -> None:
    """ユニット名の安全性を検証する"""
    if not unit or len(unit) > 128:
        raise HTTPException(status_code=400, detail="ユニット名が不正です")
    if not _ALLOWED_UNITS_PATTERN.match(unit):
        raise HTTPException(status_code=400, detail=f"ユニット名に不正な文字が含まれています: {unit}")


@router.get("/search")
async def search_journal(
    units: str = Query(default="", description="カンマ区切りユニット名 例: nginx.service,sshd.service"),
    priority: str = Query(default="", description="優先度 (err/warning/info等)"),
    since: str = Query(default="", description="開始時刻 ISO 8601 または 'today', '-1h', '-7d'"),
    until: str = Query(default="", description="終了時刻 ISO 8601"),
    grep: str = Query(default="", description="キーワードフィルタ（正規表現）"),
    lines: int = Query(default=200, ge=1, le=2000, description="最大行数"),
    current_user: Annotated[TokenData, Depends(require_permission("read:journal"))] = None,
) -> dict:
    """高度フィルタ付きジャーナル検索（時間範囲・ユニット・優先度複合）"""
    # journalctl コマンド構築（shell=False 固定）
    cmd = ["/usr/bin/journalctl", "--no-pager", "--output=short-iso", f"-n{lines}"]

    # 優先度フィルタ
    if priority:
        if priority not in _ALLOWED_PRIORITIES:
            raise HTTPException(status_code=400, detail=f"不正な優先度: {priority}")
        cmd += [f"-p{priority}"]

    # 時間範囲
    if since:
        # 相対指定 (-1h, -7d, today) と ISO 8601 を許容
        if not re.match(r"^[-a-zA-Z0-9: +TZ.]+$", since):
            raise HTTPException(status_code=400, detail="since パラメータに不正な文字が含まれています")
        cmd += [f"--since={since}"]
    if until:
        if not re.match(r"^[-a-zA-Z0-9: +TZ.]+$", until):
            raise HTTPException(status_code=400, detail="until パラメータに不正な文字が含まれています")
        cmd += [f"--until={until}"]

    # ユニットフィルタ（複数対応）
    unit_list: list[str] = []
    if units:
        for u in units.split(","):
            u = u.strip()
            if u:
                _validate_unit_name(u)
                cmd += ["-u", u]
                unit_list.append(u)

    # キーワードフィルタ（--grep=）
    if grep:
        if len(grep) > 256:
            raise HTTPException(status_code=400, detail="grep パターンが長すぎます")
        # 危険な文字（シェル展開につながるもの）を除外
        if re.search(r"[;|&$`()\[\]{}\\]", grep):
            raise HTTPException(status_code=400, detail="grep パターンに不正な文字が含まれています")
        cmd += [f"--grep={grep}"]

    try:
        import subprocess

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        log_lines = [ln for ln in result.stdout.splitlines() if ln]
        return {
            "status": "success",
            "query": {
                "units": unit_list,
                "priority": priority or None,
                "since": since or None,
                "until": until or None,
                "grep": grep or None,
                "lines": lines,
            },
            "count": len(log_lines),
            "logs": log_lines,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=503, detail="journalctl タイムアウト（30秒）")
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/stats")
async def get_journal_stats(
    hours: int = Query(default=24, ge=1, le=720, description="集計時間"),
    current_user: Annotated[TokenData, Depends(require_permission("read:journal"))] = None,
) -> dict:
    """時間帯別・優先度別ログ統計サマリー"""
    import subprocess

    stats: dict[str, int] = {}
    for pri in ["emerg", "alert", "crit", "err", "warning"]:
        try:
            result = subprocess.run(
                ["/usr/bin/journalctl", "--no-pager", f"-p{pri}", f"--since=-{hours}h", "--output=cat", "-q"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            stats[pri] = len([ln for ln in result.stdout.splitlines() if ln])
        except Exception:
            stats[pri] = -1  # エラー時は -1

    return {
        "status": "success",
        "period_hours": hours,
        "by_priority": stats,
        "total_errors": sum(v for v in stats.values() if v >= 0),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
