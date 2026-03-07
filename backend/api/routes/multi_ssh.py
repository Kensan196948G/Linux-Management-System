"""
マルチサーバーSSH並列実行 API エンドポイント

提供エンドポイント:
  GET  /api/multi-ssh/commands              - 許可コマンド一覧 (read:ssh_hosts)
  POST /api/multi-ssh/execute               - 並列実行または承認フロー経由実行 (write:ssh_hosts)
  GET  /api/multi-ssh/results/{job_id}      - 実行結果取得 (read:ssh_hosts)
  GET  /api/multi-ssh/history               - 実行履歴 (read:ssh_hosts)

セキュリティ:
  - コマンドは ALLOWED_COMMANDS allowlist に含まれるもののみ
  - ホストIDは data/ssh_hosts.json に登録済みのもののみ
  - read-only コマンドは即時実行、その他は承認フロー経由
  - subprocess は wrapper スクリプト経由のみ（引数リスト渡し）
  - 入力バリデーション（禁止文字チェック）必須
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ...core import require_permission
from ...core.approval_service import ApprovalService
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.config import settings
from ...core.validation import ValidationError, validate_no_forbidden_chars

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/multi-ssh", tags=["multi-ssh"])

_approval_service = ApprovalService(db_path=settings.database.path)

# SSH ホストデータファイルパス
_SSH_HOSTS_FILE = Path(__file__).parent.parent.parent.parent / "data" / "ssh_hosts.json"

# マルチSSH実行ラッパースクリプト
_WRAPPER = "/usr/local/sbin/adminui-multi-ssh.sh"

# ===================================================================
# コマンド allowlist
# ===================================================================

ALLOWED_COMMANDS: frozenset[str] = frozenset(
    [
        "hostname",
        "uptime",
        "df -h",
        "free -m",
        "uname -a",
        "systemctl is-active nginx",
        "systemctl is-active postgresql",
        "systemctl is-active redis",
        "systemctl is-active sshd",
        "cat /etc/os-release",
        "date",
    ]
)

# read-only コマンド（承認不要で即時実行）
READONLY_COMMANDS: frozenset[str] = frozenset(
    [
        "hostname",
        "uptime",
        "df -h",
        "free -m",
        "uname -a",
        "systemctl is-active nginx",
        "systemctl is-active postgresql",
        "systemctl is-active redis",
        "systemctl is-active sshd",
        "cat /etc/os-release",
        "date",
    ]
)

# ===================================================================
# インメモリ結果ストレージ
# ===================================================================

_job_results: dict[str, dict[str, Any]] = {}

# ===================================================================
# Pydantic モデル
# ===================================================================


class ExecuteRequest(BaseModel):
    """並列SSH実行リクエスト"""

    host_ids: list[str] = Field(..., min_length=1, description="対象ホストIDリスト")
    command: str = Field(..., description="実行コマンド（allowlist内）")
    reason: str = Field(..., min_length=1, max_length=256, description="実行理由")

    @field_validator("host_ids")
    @classmethod
    def validate_host_ids(cls, v: list[str]) -> list[str]:
        """host_ids が空でないことを確認"""
        if not v:
            raise ValueError("host_ids must not be empty")
        return v

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: str) -> str:
        """コマンドが allowlist に含まれることを確認"""
        if v not in ALLOWED_COMMANDS:
            raise ValueError(f"Command not in allowlist: {v!r}")
        return v


class HostResult(BaseModel):
    """ホスト別実行結果"""

    host_id: str
    hostname: str
    ip: str
    success: bool
    output: str
    elapsed_ms: int


class JobResult(BaseModel):
    """ジョブ実行結果"""

    job_id: str
    command: str
    status: str
    created_at: str
    completed_at: Optional[str] = None
    results: list[HostResult] = Field(default_factory=list)
    total_hosts: int = 0
    success_count: int = 0
    failure_count: int = 0


class HistoryEntry(BaseModel):
    """実行履歴エントリ"""

    job_id: str
    command: str
    host_count: int
    success_count: int
    failure_count: int
    created_at: str
    completed_at: Optional[str] = None
    status: str
    requester: str
    reason: str


# ===================================================================
# 内部ユーティリティ
# ===================================================================


def _load_ssh_hosts() -> dict[str, dict[str, Any]]:
    """ssh_hosts.json からホスト情報を id をキーとして読み込む"""
    if not _SSH_HOSTS_FILE.exists():
        return {}
    try:
        data = json.loads(_SSH_HOSTS_FILE.read_text(encoding="utf-8"))
        hosts = data if isinstance(data, list) else data.get("hosts", [])
        return {h["id"]: h for h in hosts if "id" in h}
    except Exception as exc:
        logger.error("Failed to load ssh_hosts.json: %s", exc)
        return {}


def _run_ssh_command_sync(host: dict[str, Any], command: str) -> HostResult:
    """
    単一ホストに対して SSH コマンドを実行する（同期版、スレッドプール内で実行）

    wrapper スクリプト経由で実行し、引数リストを使用する。
    """
    start = datetime.now()
    host_id = host.get("id", "")
    hostname = host.get("hostname", host.get("host", ""))
    ip = host.get("ip", hostname)
    target = hostname or ip

    try:
        result = subprocess.run(  # noqa: S603
            [_WRAPPER, command, target],
            capture_output=True,
            text=True,
            timeout=15,
        )
        elapsed = int((datetime.now() - start).total_seconds() * 1000)
        success = result.returncode == 0
        output = result.stdout.strip() if success else (result.stderr.strip() or result.stdout.strip())
        return HostResult(
            host_id=host_id,
            hostname=hostname,
            ip=ip,
            success=success,
            output=output,
            elapsed_ms=elapsed,
        )
    except subprocess.TimeoutExpired:
        elapsed = int((datetime.now() - start).total_seconds() * 1000)
        return HostResult(
            host_id=host_id,
            hostname=hostname,
            ip=ip,
            success=False,
            output="Connection timed out",
            elapsed_ms=elapsed,
        )
    except Exception as exc:
        elapsed = int((datetime.now() - start).total_seconds() * 1000)
        return HostResult(
            host_id=host_id,
            hostname=hostname,
            ip=ip,
            success=False,
            output=f"Execution error: {exc}",
            elapsed_ms=elapsed,
        )


async def _execute_parallel(job_id: str, hosts: list[dict[str, Any]], command: str) -> None:
    """
    複数ホストに対して SSH コマンドを asyncio.gather で並列実行し、
    結果を _job_results に格納する。
    """
    loop = asyncio.get_event_loop()

    async def run_one(host: dict[str, Any]) -> HostResult:
        return await loop.run_in_executor(None, _run_ssh_command_sync, host, command)

    tasks = [run_one(h) for h in hosts]
    results: list[HostResult] = await asyncio.gather(*tasks, return_exceptions=False)

    success_count = sum(1 for r in results if r.success)
    completed_at = datetime.utcnow().isoformat()

    _job_results[job_id]["results"] = [r.model_dump() for r in results]
    _job_results[job_id]["status"] = "completed"
    _job_results[job_id]["completed_at"] = completed_at
    _job_results[job_id]["success_count"] = success_count
    _job_results[job_id]["failure_count"] = len(results) - success_count


# ===================================================================
# エンドポイント
# ===================================================================


@router.get("/commands")
async def list_allowed_commands(
    current_user: TokenData = Depends(require_permission("read:ssh_hosts")),
) -> dict[str, Any]:
    """
    許可コマンド一覧を返す

    Returns:
        allowlist に含まれる全コマンドのリスト
    """
    audit_log.record(
        operation="multi_ssh_list_commands",
        user_id=current_user.user_id,
        target="multi_ssh",
        status="success",
    )
    return {
        "status": "success",
        "commands": sorted(ALLOWED_COMMANDS),
        "readonly_commands": sorted(READONLY_COMMANDS),
        "total": len(ALLOWED_COMMANDS),
    }


@router.post("/execute", status_code=status.HTTP_202_ACCEPTED)
async def execute_multi_ssh(
    body: ExecuteRequest,
    current_user: TokenData = Depends(require_permission("write:ssh_hosts")),
) -> dict[str, Any]:
    """
    複数ホストに対して SSH コマンドを並列実行する。

    read-only コマンドは承認不要で即時実行する。
    それ以外は承認フロー経由でリクエストを作成する。

    Args:
        body: 実行リクエスト（host_ids, command, reason）

    Returns:
        job_id と実行ステータス
    """
    # reason の禁止文字チェック（command は allowlist 検証済み）
    try:
        validate_no_forbidden_chars(body.reason, "reason")
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    # ホスト解決
    all_hosts = _load_ssh_hosts()
    resolved: list[dict[str, Any]] = []
    missing: list[str] = []
    for hid in body.host_ids:
        if hid in all_hosts:
            resolved.append(all_hosts[hid])
        else:
            missing.append(hid)

    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown host_ids: {missing}",
        )

    job_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    # read-only コマンドは即時実行
    if body.command in READONLY_COMMANDS:
        _job_results[job_id] = {
            "job_id": job_id,
            "command": body.command,
            "status": "running",
            "created_at": now,
            "completed_at": None,
            "results": [],
            "total_hosts": len(resolved),
            "success_count": 0,
            "failure_count": 0,
            "requester": current_user.user_id,
            "reason": body.reason,
        }

        asyncio.create_task(_execute_parallel(job_id, resolved, body.command))

        audit_log.record(
            operation="multi_ssh_execute",
            user_id=current_user.user_id,
            target=f"command={body.command} hosts={len(resolved)}",
            status="started",
            details={"job_id": job_id, "host_ids": body.host_ids},
        )

        return {
            "status": "started",
            "job_id": job_id,
            "command": body.command,
            "total_hosts": len(resolved),
            "message": "Execution started (read-only command, no approval required)",
        }

    # その他コマンドは承認フロー経由
    try:
        approval_req = await _approval_service.create_request(
            request_type="multi_ssh_execute",
            payload={
                "job_id": job_id,
                "host_ids": body.host_ids,
                "command": body.command,
            },
            reason=body.reason,
            requester_id=current_user.user_id,
            requester_name=getattr(current_user, "name", current_user.user_id),
            requester_role=current_user.role,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    audit_log.record(
        operation="multi_ssh_approval_request",
        user_id=current_user.user_id,
        target=f"command={body.command} hosts={len(resolved)}",
        status="pending",
        details={"job_id": job_id, "approval_id": approval_req.get("id")},
    )

    return {
        "status": "pending_approval",
        "job_id": job_id,
        "approval_id": approval_req.get("id"),
        "command": body.command,
        "total_hosts": len(resolved),
        "message": "Approval required. Execution will start after approval.",
    }


@router.get("/results/{job_id}")
async def get_job_result(
    job_id: str,
    current_user: TokenData = Depends(require_permission("read:ssh_hosts")),
) -> dict[str, Any]:
    """
    job_id に対応する実行結果を返す。

    Args:
        job_id: ジョブID（uuid形式）

    Returns:
        ジョブ実行結果

    Raises:
        404: job_id が存在しない場合
    """
    if job_id not in _job_results:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job not found: {job_id}")

    audit_log.record(
        operation="multi_ssh_get_result",
        user_id=current_user.user_id,
        target=job_id,
        status="success",
    )

    return {"status": "success", "job": _job_results[job_id]}


@router.get("/history")
async def get_history(
    current_user: TokenData = Depends(require_permission("read:ssh_hosts")),
) -> dict[str, Any]:
    """
    過去の全ジョブ実行履歴を返す（インメモリ）。

    Returns:
        ジョブ履歴リスト（新しい順）
    """
    entries = [
        {
            "job_id": v["job_id"],
            "command": v["command"],
            "host_count": v.get("total_hosts", 0),
            "success_count": v.get("success_count", 0),
            "failure_count": v.get("failure_count", 0),
            "created_at": v["created_at"],
            "completed_at": v.get("completed_at"),
            "status": v["status"],
            "requester": v.get("requester", ""),
            "reason": v.get("reason", ""),
        }
        for v in _job_results.values()
    ]
    entries.sort(key=lambda e: e["created_at"], reverse=True)

    audit_log.record(
        operation="multi_ssh_history",
        user_id=current_user.user_id,
        target="multi_ssh",
        status="success",
    )

    return {
        "status": "success",
        "history": entries,
        "total": len(entries),
    }
