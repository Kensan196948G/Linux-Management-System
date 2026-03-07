"""
Ansible連携・マルチサーバー管理 API エンドポイント

提供エンドポイント:
  GET  /api/ansible/inventory              - インベントリ一覧（/etc/ansible/hosts パース）
  GET  /api/ansible/hosts                  - ホスト一覧とステータス（ping結果キャッシュ）
  POST /api/ansible/ping                   - 全ホストping（バックグラウンド）
  GET  /api/ansible/playbooks              - 利用可能Playbook一覧
  GET  /api/ansible/playbooks/{name}       - Playbookコンテンツ表示
  POST /api/ansible/playbooks/{name}/run   - Playbook実行（承認フロー経由、202返却）
  GET  /api/ansible/history                - 実行履歴（audit_logから）
"""

import asyncio
import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ...core import require_permission
from ...core.approval_service import ApprovalService
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.config import settings

logger = logging.getLogger(__name__)

# ApprovalService インスタンス
_approval_service = ApprovalService(db_path=settings.database.path)

router = APIRouter(prefix="/ansible", tags=["ansible"])

# Playbook名の許可パターン
_PLAYBOOK_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+\.yml$")

# Ansibleラッパーパス
_ANSIBLE_WRAPPER = "/usr/local/sbin/adminui-ansible.sh"

# ping結果のインメモリキャッシュ（{hostname: {status, last_seen}}）
_ping_cache: dict[str, dict[str, Any]] = {}
_ping_running: bool = False


# ===================================================================
# レスポンスモデル
# ===================================================================


class HostInfo(BaseModel):
    """ホスト情報"""

    hostname: str
    ip: str = ""
    group: str = ""
    os: str = ""
    ping_status: str = "unknown"
    last_seen: Optional[str] = None
    variables: dict[str, Any] = Field(default_factory=dict)


class InventoryResponse(BaseModel):
    """インベントリレスポンス"""

    status: str
    groups: dict[str, Any] = Field(default_factory=dict)
    hosts: list[HostInfo] = Field(default_factory=list)
    total_hosts: int = 0
    timestamp: str


class HostsResponse(BaseModel):
    """ホスト一覧レスポンス"""

    status: str
    hosts: list[HostInfo] = Field(default_factory=list)
    total: int = 0
    online: int = 0
    offline: int = 0
    unknown: int = 0
    timestamp: str


class PingResponse(BaseModel):
    """Ping実行レスポンス"""

    status: str
    message: str
    timestamp: str


class PlaybookInfo(BaseModel):
    """Playbook情報"""

    name: str
    path: str = ""
    description: str = ""
    task_count: int = 0
    size_bytes: int = 0
    modified_at: Optional[str] = None


class PlaybooksResponse(BaseModel):
    """Playbook一覧レスポンス"""

    status: str
    playbooks: list[PlaybookInfo] = Field(default_factory=list)
    count: int = 0
    timestamp: str


class PlaybookContentResponse(BaseModel):
    """Playbookコンテンツレスポンス"""

    status: str
    name: str
    content: str
    timestamp: str


class PlaybookRunRequest(BaseModel):
    """Playbook実行リクエスト"""

    reason: str = Field(..., min_length=1, max_length=500, description="実行理由")
    extra_vars: dict[str, str] = Field(default_factory=dict, description="追加変数（allowlistのみ）")

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        """実行理由のバリデーション"""
        if not v.strip():
            raise ValueError("Reason cannot be empty")
        return v.strip()


class PlaybookRunResponse(BaseModel):
    """Playbook実行承認リクエストレスポンス"""

    status: str
    message: str
    request_id: str
    playbook: str
    timestamp: str


class HistoryEntry(BaseModel):
    """実行履歴エントリ"""

    timestamp: str
    operation: str
    user_id: str
    target: str
    result: str
    details: dict[str, Any] = Field(default_factory=dict)


class HistoryResponse(BaseModel):
    """実行履歴レスポンス"""

    status: str
    history: list[HistoryEntry] = Field(default_factory=list)
    count: int = 0
    timestamp: str


# ===================================================================
# ヘルパー関数
# ===================================================================


def _validate_playbook_name(name: str) -> None:
    """
    Playbook名のバリデーション

    Args:
        name: Playbook名

    Raises:
        HTTPException: バリデーション失敗時
    """
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Playbook name is required")

    if len(name) > 128:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Playbook name too long (max 128 characters)")

    if not _PLAYBOOK_NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid playbook name: must match pattern [a-zA-Z0-9_-]+.yml",
        )

    if ".." in name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path traversal not allowed")


def _run_wrapper(args: list[str], timeout: int = 60) -> dict[str, Any]:
    """
    Ansibleラッパースクリプトを実行する

    Ansibleがインストールされていない場合は ansible_not_installed を返す。

    Args:
        args: コマンド引数（サブコマンドと引数）
        timeout: タイムアウト秒数

    Returns:
        実行結果の辞書
    """
    cmd = ["sudo", _ANSIBLE_WRAPPER] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = result.stdout.strip()

        # ansible_not_installed チェック
        if stdout:
            try:
                parsed = json.loads(stdout)
                if parsed.get("status") == "ansible_not_installed":
                    return {"status": "ansible_not_installed", "hosts": [], "message": "Ansible is not installed"}
                return parsed
            except json.JSONDecodeError:
                pass

        return {
            "status": "success" if result.returncode == 0 else "error",
            "stdout": stdout,
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except FileNotFoundError:
        logger.warning("Ansible wrapper not found: %s", _ANSIBLE_WRAPPER)
        return {"status": "ansible_not_installed", "hosts": [], "message": "Ansible wrapper not found"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"Command timed out after {timeout}s"}
    except Exception as exc:
        logger.error("Wrapper execution error: %s", exc)
        return {"status": "error", "message": str(exc)}


def _parse_ping_output(stdout: str) -> dict[str, str]:
    """
    ansible ping --one-line の出力をパースする

    Args:
        stdout: コマンド出力

    Returns:
        {hostname: "online"|"offline"} の辞書
    """
    results: dict[str, str] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # "hostname | SUCCESS => {...}" or "hostname | UNREACHABLE! => {...}"
        match = re.match(r"^([^\s|]+)\s*\|\s*(SUCCESS|UNREACHABLE|FAILED)", line)
        if match:
            hostname = match.group(1)
            ping_result = match.group(2)
            results[hostname] = "online" if ping_result == "SUCCESS" else "offline"
    return results


def _parse_inventory_hosts(inventory_data: dict[str, Any]) -> list[HostInfo]:
    """
    ansible-inventory --list の出力からホスト一覧を生成する

    Args:
        inventory_data: ansible-inventory JSON出力

    Returns:
        HostInfo のリスト
    """
    hosts: list[HostInfo] = []
    seen: set[str] = set()

    # _meta.hostvars からホスト変数取得
    meta = inventory_data.get("_meta", {})
    hostvars = meta.get("hostvars", {})

    # 各グループからホスト抽出
    for group_name, group_data in inventory_data.items():
        if group_name == "_meta":
            continue
        if not isinstance(group_data, dict):
            continue

        group_hosts = group_data.get("hosts", [])
        for hostname in group_hosts:
            if hostname in seen:
                continue
            seen.add(hostname)

            vars_data = hostvars.get(hostname, {})
            ip = vars_data.get("ansible_host", vars_data.get("ansible_ip", ""))
            os_info = vars_data.get("ansible_distribution", vars_data.get("os", ""))

            # キャッシュからpingステータス取得
            cached = _ping_cache.get(hostname, {})

            hosts.append(
                HostInfo(
                    hostname=hostname,
                    ip=ip,
                    group=group_name,
                    os=os_info,
                    ping_status=cached.get("status", "unknown"),
                    last_seen=cached.get("last_seen"),
                    variables={k: v for k, v in vars_data.items() if k not in ("ansible_password", "ansible_ssh_pass")},
                )
            )

    return hosts


def _count_tasks_in_playbook(content: str) -> int:
    """
    Playbookのタスク数をカウントする

    Args:
        content: Playbookコンテンツ（YAML）

    Returns:
        タスク数（概算）
    """
    return len(re.findall(r"^\s*-\s+name:", content, re.MULTILINE))


async def _run_ping_background(user_id: str) -> None:
    """
    バックグラウンドでpingを実行しキャッシュを更新する

    Args:
        user_id: 実行ユーザーID
    """
    global _ping_running
    _ping_running = True
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: _run_wrapper(["ping-all"], timeout=120))

        if result.get("status") == "success":
            stdout = result.get("stdout", "")
            ping_results = _parse_ping_output(stdout)
            now = datetime.now().isoformat()
            for hostname, ping_status in ping_results.items():
                _ping_cache[hostname] = {
                    "status": ping_status,
                    "last_seen": now if ping_status == "online" else _ping_cache.get(hostname, {}).get("last_seen"),
                }
            logger.info("Ping completed: %d hosts checked", len(ping_results))
            audit_log.record(
                operation="ansible_ping_all",
                user_id=user_id,
                target="all",
                status="success",
                details={"hosts_checked": len(ping_results)},
            )
        elif result.get("status") == "ansible_not_installed":
            logger.info("Ansible not installed, skipping ping")
        else:
            logger.warning("Ping background task failed: %s", result.get("message"))
    except Exception as exc:
        logger.error("Ping background task error: %s", exc)
    finally:
        _ping_running = False


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/inventory",
    response_model=InventoryResponse,
    summary="インベントリ一覧",
    description="Ansibleインベントリ（/etc/ansible/hosts）のホスト・グループ一覧を取得します",
)
async def get_inventory(
    current_user: TokenData = Depends(require_permission("read:ansible")),
) -> InventoryResponse:
    """Ansibleインベントリ一覧を取得する"""
    now = datetime.now().isoformat()

    result = _run_wrapper(["inventory-list"], timeout=30)

    if result.get("status") == "ansible_not_installed":
        audit_log.record(
            operation="ansible_inventory_list",
            user_id=current_user.user_id,
            target="inventory",
            status="ansible_not_installed",
        )
        return InventoryResponse(
            status="ansible_not_installed",
            groups={},
            hosts=[],
            total_hosts=0,
            timestamp=now,
        )

    if result.get("status") == "error":
        audit_log.record(
            operation="ansible_inventory_list",
            user_id=current_user.user_id,
            target="inventory",
            status="error",
            details={"message": result.get("message", "")},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.get("message", "Failed to get inventory")
        )

    # inventory_data は ansible-inventory --list の JSON出力
    inventory_data = result if isinstance(result, dict) and "_meta" in result else {}

    # stdout が JSON の場合はパース
    if "stdout" in result:
        try:
            inventory_data = json.loads(result["stdout"])
        except (json.JSONDecodeError, TypeError):
            inventory_data = {}

    hosts = _parse_inventory_hosts(inventory_data)

    # グループ情報整理（_meta除く）
    groups = {k: v for k, v in inventory_data.items() if k != "_meta" and isinstance(v, dict)}

    audit_log.record(
        operation="ansible_inventory_list",
        user_id=current_user.user_id,
        target="inventory",
        status="success",
        details={"host_count": len(hosts)},
    )

    return InventoryResponse(
        status="success",
        groups=groups,
        hosts=hosts,
        total_hosts=len(hosts),
        timestamp=now,
    )


@router.get(
    "/hosts",
    response_model=HostsResponse,
    summary="ホスト一覧とステータス",
    description="インベントリのホスト一覧とpingキャッシュからのステータスを返します",
)
async def get_hosts(
    current_user: TokenData = Depends(require_permission("read:ansible")),
) -> HostsResponse:
    """ホスト一覧とping結果キャッシュを返す"""
    now = datetime.now().isoformat()

    result = _run_wrapper(["inventory-list"], timeout=30)

    if result.get("status") == "ansible_not_installed":
        return HostsResponse(
            status="ansible_not_installed",
            hosts=[],
            total=0,
            online=0,
            offline=0,
            unknown=0,
            timestamp=now,
        )

    inventory_data: dict[str, Any] = {}
    if "stdout" in result:
        try:
            inventory_data = json.loads(result["stdout"])
        except (json.JSONDecodeError, TypeError):
            pass
    elif "_meta" in result:
        inventory_data = result

    hosts = _parse_inventory_hosts(inventory_data)

    online = sum(1 for h in hosts if h.ping_status == "online")
    offline = sum(1 for h in hosts if h.ping_status == "offline")
    unknown = sum(1 for h in hosts if h.ping_status == "unknown")

    audit_log.record(
        operation="ansible_hosts_list",
        user_id=current_user.user_id,
        target="hosts",
        status="success",
        details={"total": len(hosts), "online": online, "offline": offline},
    )

    return HostsResponse(
        status="success",
        hosts=hosts,
        total=len(hosts),
        online=online,
        offline=offline,
        unknown=unknown,
        timestamp=now,
    )


@router.post(
    "/ping",
    response_model=PingResponse,
    summary="全ホストping",
    description="全ホストにpingを実行します（バックグラウンド処理）。結果はキャッシュされ /api/ansible/hosts で取得可能です",
)
async def ping_all_hosts(
    background_tasks: BackgroundTasks,
    current_user: TokenData = Depends(require_permission("write:ansible")),
) -> PingResponse:
    """全ホストへのpingをバックグラウンドで実行する"""
    global _ping_running

    if _ping_running:
        return PingResponse(
            status="already_running",
            message="Ping is already running in the background",
            timestamp=datetime.now().isoformat(),
        )

    audit_log.record(
        operation="ansible_ping_all_requested",
        user_id=current_user.user_id,
        target="all",
        status="requested",
    )

    background_tasks.add_task(_run_ping_background, current_user.user_id)

    return PingResponse(
        status="accepted",
        message="Ping started in background. Check /api/ansible/hosts for results.",
        timestamp=datetime.now().isoformat(),
    )


@router.get(
    "/playbooks",
    response_model=PlaybooksResponse,
    summary="Playbook一覧",
    description="/etc/ansible/playbooks/*.yml の一覧を返します",
)
async def get_playbooks(
    current_user: TokenData = Depends(require_permission("read:ansible")),
) -> PlaybooksResponse:
    """利用可能なPlaybook一覧を取得する"""
    now = datetime.now().isoformat()
    playbook_dir = Path("/etc/ansible/playbooks")
    playbooks: list[PlaybookInfo] = []

    if not playbook_dir.exists():
        audit_log.record(
            operation="ansible_playbooks_list",
            user_id=current_user.user_id,
            target="playbooks",
            status="no_directory",
        )
        return PlaybooksResponse(
            status="success",
            playbooks=[],
            count=0,
            timestamp=now,
        )

    for yml_path in sorted(playbook_dir.glob("*.yml")):
        name = yml_path.name

        # 安全なファイル名のみ処理
        if not _PLAYBOOK_NAME_PATTERN.match(name):
            continue

        try:
            content = yml_path.read_text(encoding="utf-8", errors="replace")
            task_count = _count_tasks_in_playbook(content)

            # 説明はコメントの最初の行から取得
            description = ""
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    description = stripped.lstrip("#").strip()
                    break

            stat = yml_path.stat()
            playbooks.append(
                PlaybookInfo(
                    name=name,
                    path=str(yml_path),
                    description=description,
                    task_count=task_count,
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                )
            )
        except (OSError, PermissionError) as exc:
            logger.warning("Cannot read playbook %s: %s", yml_path, exc)

    audit_log.record(
        operation="ansible_playbooks_list",
        user_id=current_user.user_id,
        target="playbooks",
        status="success",
        details={"count": len(playbooks)},
    )

    return PlaybooksResponse(
        status="success",
        playbooks=playbooks,
        count=len(playbooks),
        timestamp=now,
    )


@router.get(
    "/playbooks/{name}",
    response_model=PlaybookContentResponse,
    summary="Playbookコンテンツ表示",
    description="指定したPlaybookの内容を表示します（読み取り専用）",
)
async def get_playbook_content(
    name: str,
    current_user: TokenData = Depends(require_permission("read:ansible")),
) -> PlaybookContentResponse:
    """Playbookのコンテンツを取得する"""
    _validate_playbook_name(name)

    result = _run_wrapper(["show-playbook", name], timeout=10)

    if result.get("status") == "ansible_not_installed":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Ansible is not installed")

    if result.get("status") == "error":
        msg = result.get("message", "Failed to read playbook")
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Playbook not found: {name}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg)

    content = result.get("stdout", "")

    audit_log.record(
        operation="ansible_playbook_view",
        user_id=current_user.user_id,
        target=name,
        status="success",
    )

    return PlaybookContentResponse(
        status="success",
        name=name,
        content=content,
        timestamp=datetime.now().isoformat(),
    )


@router.post(
    "/playbooks/{name}/run",
    response_model=PlaybookRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Playbook実行（承認フロー経由）",
    description="Playbook実行リクエストを承認フローに送信します。直接実行は禁止されています（202 Accepted）",
)
async def run_playbook(
    name: str,
    request: PlaybookRunRequest,
    current_user: TokenData = Depends(require_permission("write:ansible")),
) -> PlaybookRunResponse:
    """Playbook実行リクエストを承認フローに送信する（直接実行禁止）"""
    _validate_playbook_name(name)

    # Playbookの存在確認（show-playbook で確認）
    check_result = _run_wrapper(["show-playbook", name], timeout=10)
    if check_result.get("status") == "error":
        msg = check_result.get("message", "Playbook check failed")
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Playbook not found: {name}")

    # 承認フロー経由でリクエスト作成
    try:
        approval_result = await _approval_service.create_request(
            request_type="ansible_playbook_run",
            payload={
                "playbook_name": name,
                "extra_vars": request.extra_vars,
            },
            reason=request.reason,
            requester_id=current_user.user_id,
            requester_name=current_user.username,
            requester_role=current_user.role,
        )

        audit_log.record(
            operation="ansible_playbook_run_requested",
            user_id=current_user.user_id,
            target=name,
            status="pending_approval",
            details={
                "request_id": approval_result["request_id"],
                "reason": request.reason,
            },
        )

        return PlaybookRunResponse(
            status="pending_approval",
            message=f"Playbook run request submitted for approval. Request ID: {approval_result['request_id']}",
            request_id=approval_result["request_id"],
            playbook=name,
            timestamp=datetime.now().isoformat(),
        )
    except Exception as exc:
        logger.error("Failed to create approval request for playbook %s: %s", name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create approval request: {exc}",
        )


@router.get(
    "/history",
    response_model=HistoryResponse,
    summary="実行履歴",
    description="Ansible操作の実行履歴（監査ログから）を返します",
)
async def get_history(
    limit: int = 50,
    current_user: TokenData = Depends(require_permission("read:ansible")),
) -> HistoryResponse:
    """Ansible操作の実行履歴を取得する"""
    if limit < 1 or limit > 500:
        limit = 50

    history: list[HistoryEntry] = []
    log_dir = Path(settings.logging.file).parent / "audit"

    if log_dir.exists():
        # 監査ログファイルを新しい順に読み込む
        log_files = sorted(log_dir.glob("audit_*.json"), reverse=True)
        for log_file in log_files:
            if len(history) >= limit:
                break
            try:
                for line in log_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        op = entry.get("operation", "")
                        if "ansible" in op:
                            history.append(
                                HistoryEntry(
                                    timestamp=entry.get("timestamp", ""),
                                    operation=op,
                                    user_id=entry.get("user_id", ""),
                                    target=entry.get("target", ""),
                                    result=entry.get("status", ""),
                                    details=entry.get("details", {}),
                                )
                            )
                    except (json.JSONDecodeError, KeyError):
                        continue
            except (OSError, PermissionError) as exc:
                logger.warning("Cannot read audit log %s: %s", log_file, exc)

    # 新しい順に並び替え・件数制限
    history = sorted(history, key=lambda e: e.timestamp, reverse=True)[:limit]

    audit_log.record(
        operation="ansible_history_view",
        user_id=current_user.user_id,
        target="history",
        status="success",
        details={"count": len(history)},
    )

    return HistoryResponse(
        status="success",
        history=history,
        count=len(history),
        timestamp=datetime.now().isoformat(),
    )


@router.post(
    "/playbooks/{name}/validate",
    status_code=status.HTTP_200_OK,
    summary="Playbook構文チェック",
    description="ansible-lint / --syntax-check でPlaybookの構文を検証します（実行はしません）",
)
async def validate_playbook(
    name: str,
    current_user: TokenData = Depends(require_permission("read:ansible")),
) -> dict:
    """Playbookの構文チェックを実行する（書き込み不要、read権限で実行可能）"""
    _validate_playbook_name(name)

    result = _run_wrapper(["validate-playbook", name], timeout=60)

    audit_log.record(
        operation="ansible_playbook_validate",
        user_id=current_user.user_id,
        target=name,
        status=result.get("status", "unknown"),
    )

    if result.get("status") == "error" and "not found" in result.get("message", "").lower():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Playbook not found: {name}")

    return {
        "status": result.get("status", "unknown"),
        "playbook": name,
        "message": result.get("message", ""),
        "output": result.get("stdout", ""),
        "timestamp": datetime.now().isoformat(),
    }
