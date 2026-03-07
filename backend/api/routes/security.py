"""
セキュリティ監査 API エンドポイント

提供エンドポイント:
  GET /api/security/audit-report      - 監査ログ統計
  GET /api/security/failed-logins     - 過去24時間の失敗ログイン時間別集計
  GET /api/security/sudo-logs         - sudo使用ログ (auth.log)
  GET /api/security/open-ports        - 開放ポート一覧 (psutil)
  GET /api/security/bandit-status     - bandit スキャン結果サマリ
  GET /api/security/sudo-history      - sudo操作履歴 (audit_log.jsonl)
  GET /api/security/score             - セキュリティスコア (0-100)
"""

import json
import logging
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

# data/audit_log.jsonl のパス (プロジェクトルート/data/audit_log.jsonl)
_PROJECT_ROOT = Path(__file__).parents[3]
_AUDIT_JSONL_PATH = _PROJECT_ROOT / "data" / "audit_log.jsonl"

# 既知の危険ポート
_DANGEROUS_PORTS = {21, 23, 25, 110, 143, 512, 513, 514, 3389, 5900}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/security", tags=["security"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class AuditReportResponse(BaseModel):
    """監査ログ統計レスポンス"""

    status: str
    auth_log_lines: int = 0
    accepted_logins: int = 0
    failed_logins: int = 0
    sudo_count: int = 0
    last_login: str = ""
    timestamp: str


class LogEntriesResponse(BaseModel):
    """ログエントリ一覧レスポンス"""

    status: str
    entries: List[str] = Field(default_factory=list)
    timestamp: str


class OpenPortsResponse(BaseModel):
    """開放ポート一覧レスポンス"""

    status: str
    output: str = ""
    timestamp: str


class FailedLoginHourlyItem(BaseModel):
    """時間別失敗ログイン集計アイテム"""

    hour: str
    count: int


class FailedLoginsHourlyResponse(BaseModel):
    """過去24時間の失敗ログイン時間別集計レスポンス"""

    hourly: List[FailedLoginHourlyItem] = Field(default_factory=list)
    total: int = 0
    unique_ips: int = 0


class PortInfo(BaseModel):
    """開放ポート情報"""

    port: int
    proto: str
    state: str
    pid: Optional[int] = None
    name: Optional[str] = None
    dangerous: bool = False


class OpenPortsStructuredResponse(BaseModel):
    """開放ポート一覧レスポンス (psutil ベース)"""

    ports: List[PortInfo] = Field(default_factory=list)


class SudoHistoryItem(BaseModel):
    """sudo 操作履歴アイテム"""

    timestamp: str
    user: str
    operation: str
    result: str


class SudoHistoryResponse(BaseModel):
    """sudo 操作履歴レスポンス"""

    history: List[SudoHistoryItem] = Field(default_factory=list)


class SecurityScoreDetails(BaseModel):
    """セキュリティスコア詳細"""

    failed_login_risk: int
    open_ports_risk: int
    recent_sudo_ops: int


class SecurityScoreResponse(BaseModel):
    """セキュリティスコアレスポンス"""

    score: int
    details: SecurityScoreDetails


class BanditStatusResponse(BaseModel):
    """bandit スキャン結果サマリ"""

    status: str
    high: int = 0
    medium: int = 0
    low: int = 0
    total_issues: int = 0
    scanned: bool = False
    error: Optional[str] = None


# ===================================================================
# ヘルパー関数
# ===================================================================


def _read_audit_jsonl(path: Path = _AUDIT_JSONL_PATH) -> List[Dict[str, Any]]:
    """audit_log.jsonl を読み込み、パース済みエントリのリストを返す。

    ファイルが存在しない場合は空リストを返す (FileNotFoundError を外に漏らさない)。
    """
    entries: List[Dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    return entries


def _collect_failed_logins_hourly(entries: List[Dict[str, Any]]) -> FailedLoginsHourlyResponse:
    """過去24時間の "login_failed" イベントを1時間単位で集計する。"""
    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(hours=24)

    hourly_counts: Dict[str, int] = defaultdict(int)
    unique_ips: set = set()
    total = 0

    for entry in entries:
        if entry.get("operation") != "login_failed":
            continue
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        if ts < cutoff:
            continue

        # 1時間単位のキー
        hour_key = ts.strftime("%Y-%m-%dT%H:00")
        hourly_counts[hour_key] += 1
        total += 1

        ip = entry.get("details", {}).get("ip") or entry.get("details", {}).get("source_ip") or entry.get("target", "")
        if ip:
            unique_ips.add(ip)

    # 過去24時間分のスロットを全て用意（データがない時間帯も0で埋める）
    hourly: List[FailedLoginHourlyItem] = []
    for h in range(23, -1, -1):
        slot_dt = now - timedelta(hours=h)
        key = slot_dt.strftime("%Y-%m-%dT%H:00")
        hourly.append(FailedLoginHourlyItem(hour=key, count=hourly_counts.get(key, 0)))

    return FailedLoginsHourlyResponse(hourly=hourly, total=total, unique_ips=len(unique_ips))


def _collect_open_ports_psutil() -> List[PortInfo]:
    """psutil でリスニング中の TCP/UDP ポート一覧を返す (sudo 不要)。"""
    ports: List[PortInfo] = []
    seen: set = set()

    try:
        connections = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, PermissionError):
        connections = []

    for conn in connections:
        if conn.status not in ("LISTEN", psutil.CONN_LISTEN):
            continue
        if not conn.laddr:
            continue

        port_no = conn.laddr.port
        proto = "tcp" if conn.type and conn.type.name == "SOCK_STREAM" else "tcp"
        key = (port_no, proto)
        if key in seen:
            continue
        seen.add(key)

        process_name: Optional[str] = None
        pid: Optional[int] = conn.pid
        if pid:
            try:
                process_name = psutil.Process(pid).name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        ports.append(
            PortInfo(
                port=port_no,
                proto=proto,
                state="LISTEN",
                pid=pid,
                name=process_name,
                dangerous=port_no in _DANGEROUS_PORTS,
            )
        )

    return sorted(ports, key=lambda p: p.port)


def _collect_sudo_history(entries: List[Dict[str, Any]], days: int = 7, limit: int = 20) -> List[SudoHistoryItem]:
    """audit_log.jsonl からsudo関連操作を最新 limit 件取得する（直近 days 日間）。"""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    results: List[SudoHistoryItem] = []

    for entry in reversed(entries):
        operation = entry.get("operation", "")
        if not operation:
            continue
        # sudo関連のオペレーションを含むエントリを収集
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        if ts < cutoff:
            continue

        results.append(
            SudoHistoryItem(
                timestamp=entry["timestamp"],
                user=entry.get("user_id", "unknown"),
                operation=operation,
                result=entry.get("status", "unknown"),
            )
        )
        if len(results) >= limit:
            break

    return results


def _calculate_security_score(
    failed_logins_total: int,
    open_ports_count: int,
    dangerous_ports_count: int,
    sudo_ops_count: int,
) -> SecurityScoreResponse:
    """セキュリティスコア (0-100) を計算する。"""
    # 失敗ログインリスク (0=100点、10件以上=0点)
    failed_login_risk = max(0, 100 - failed_logins_total * 5)
    # 開放ポートリスク (危険ポートあり=-20, ポート数が多いほど減点)
    open_ports_risk = max(0, 100 - dangerous_ports_count * 20 - max(0, open_ports_count - 5) * 5)
    # 総合スコア (加重平均)
    score = int(0.5 * failed_login_risk + 0.4 * open_ports_risk + 0.1 * max(0, 100 - sudo_ops_count * 2))
    score = max(0, min(100, score))

    return SecurityScoreResponse(
        score=score,
        details=SecurityScoreDetails(
            failed_login_risk=max(0, min(100, failed_login_risk)),
            open_ports_risk=max(0, min(100, open_ports_risk)),
            recent_sudo_ops=sudo_ops_count,
        ),
    )


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/audit-report",
    response_model=AuditReportResponse,
    summary="監査ログ統計",
)
async def get_audit_report(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> AuditReportResponse:
    """監査ログの統計情報（認証成功/失敗件数、sudo使用件数、最終ログイン）を返す"""
    try:
        result = sudo_wrapper.get_security_audit_report()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="security_audit_report_read",
            user_id=current_user.user_id,
            target="auth.log",
            status="success",
            details={},
        )
        return AuditReportResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("Security audit-report error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"監査レポート取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_audit_report: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/failed-logins",
    response_model=FailedLoginsHourlyResponse,
    summary="過去24時間の失敗ログイン時間別集計",
)
async def get_failed_logins(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> FailedLoginsHourlyResponse:
    """data/audit_log.jsonl から過去24時間の "login_failed" イベントを時間別に集計して返す。
    ファイルが存在しない場合は空データを返す。
    """
    try:
        entries = _read_audit_jsonl()
        result = _collect_failed_logins_hourly(entries)
        audit_log.record(
            operation="security_failed_logins_read",
            user_id=current_user.user_id,
            target="audit_log.jsonl",
            status="success",
            details={"total": result.total, "unique_ips": result.unique_ips},
        )
        return result
    except Exception as e:
        logger.error("Unexpected error in get_failed_logins: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/sudo-logs",
    response_model=LogEntriesResponse,
    summary="sudo使用ログ",
)
async def get_sudo_logs(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> LogEntriesResponse:
    """auth.log から sudo 使用ログ（最大50件）を返す"""
    try:
        result = sudo_wrapper.get_sudo_logs()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="security_sudo_logs_read",
            user_id=current_user.user_id,
            target="auth.log",
            status="success",
            details={"count": len(parsed.get("entries", []))},
        )
        return LogEntriesResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("Security sudo-logs error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"sudoログ取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_sudo_logs: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/open-ports",
    response_model=OpenPortsStructuredResponse,
    summary="開放ポート一覧 (psutil)",
)
async def get_open_ports(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> OpenPortsStructuredResponse:
    """psutil を使用してリスニング中のポートを取得する (sudo 不要)。
    危険ポート (telnet/ftp 等) は dangerous=True でフラグを立てる。
    """
    try:
        ports = _collect_open_ports_psutil()
        audit_log.record(
            operation="security_open_ports_read",
            user_id=current_user.user_id,
            target="open_ports",
            status="success",
            details={"count": len(ports)},
        )
        return OpenPortsStructuredResponse(ports=ports)
    except Exception as e:
        logger.error("Unexpected error in get_open_ports: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/sudo-history",
    response_model=SudoHistoryResponse,
    summary="sudo 操作履歴 (audit_log.jsonl)",
)
async def get_sudo_history(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> SudoHistoryResponse:
    """data/audit_log.jsonl から過去7日間のsudo操作履歴（最新20件）を返す。
    ファイルが存在しない場合は空データを返す。
    """
    try:
        entries = _read_audit_jsonl()
        history = _collect_sudo_history(entries)
        audit_log.record(
            operation="security_sudo_history_read",
            user_id=current_user.user_id,
            target="audit_log.jsonl",
            status="success",
            details={"count": len(history)},
        )
        return SudoHistoryResponse(history=history)
    except Exception as e:
        logger.error("Unexpected error in get_sudo_history: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/score",
    response_model=SecurityScoreResponse,
    summary="セキュリティスコア (0-100)",
)
async def get_security_score(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> SecurityScoreResponse:
    """失敗ログイン数・開放ポート数・sudo操作数からセキュリティスコア(0-100)を算出して返す。"""
    try:
        entries = _read_audit_jsonl()
        failed_resp = _collect_failed_logins_hourly(entries)
        ports = _collect_open_ports_psutil()
        sudo_history = _collect_sudo_history(entries)

        dangerous_count = sum(1 for p in ports if p.dangerous)
        result = _calculate_security_score(
            failed_logins_total=failed_resp.total,
            open_ports_count=len(ports),
            dangerous_ports_count=dangerous_count,
            sudo_ops_count=len(sudo_history),
        )
        audit_log.record(
            operation="security_score_read",
            user_id=current_user.user_id,
            target="security_score",
            status="success",
            details={"score": result.score},
        )
        return result
    except Exception as e:
        logger.error("Unexpected error in get_security_score: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/bandit-status",
    response_model=BanditStatusResponse,
    summary="bandit スキャン結果サマリ",
)
async def get_bandit_status(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> BanditStatusResponse:
    """bandit -r backend/ -ll -f json を実行し High/Medium 件数を返す（sudo なし）"""
    try:
        # shell=True 禁止 — 配列渡しで実行
        proc = subprocess.run(
            ["bandit", "-r", "backend/", "-ll", "-f", "json"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        # bandit は問題あり=1, なし=0, エラー=2 を返す
        raw = proc.stdout or proc.stderr or "{}"
        data = json.loads(raw)

        results = data.get("results", [])
        high = sum(1 for r in results if r.get("issue_severity") == "HIGH")
        medium = sum(1 for r in results if r.get("issue_severity") == "MEDIUM")
        low = sum(1 for r in results if r.get("issue_severity") == "LOW")

        audit_log.record(
            operation="security_bandit_scan",
            user_id=current_user.user_id,
            target="backend/",
            status="success",
            details={"high": high, "medium": medium, "low": low},
        )
        return BanditStatusResponse(
            status="success",
            high=high,
            medium=medium,
            low=low,
            total_issues=len(results),
            scanned=True,
        )
    except subprocess.TimeoutExpired:
        logger.error("bandit scan timed out")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="bandit スキャンがタイムアウトしました",
        )
    except FileNotFoundError:
        # bandit がインストールされていない場合
        return BanditStatusResponse(
            status="unavailable",
            scanned=False,
            error="bandit がインストールされていません",
        )
    except json.JSONDecodeError as e:
        logger.error("bandit JSON parse error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"bandit 出力解析エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_bandit_status: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )
