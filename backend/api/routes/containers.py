"""
Docker/Podman コンテナ管理 API エンドポイント

提供エンドポイント:
  GET  /api/containers/         - コンテナ一覧 (running/stopped)
  GET  /api/containers/images   - イメージ一覧
  POST /api/containers/prune    - 停止コンテナ削除（承認フロー）
  GET  /api/containers/{name}   - コンテナ詳細（inspect）
  POST /api/containers/{name}/start   - コンテナ起動
  POST /api/containers/{name}/stop    - コンテナ停止（承認フロー）
  POST /api/containers/{name}/restart - コンテナ再起動（承認フロー）
  GET  /api/containers/{name}/logs    - ログ取得（最新100行）
  GET  /api/containers/{name}/logs/stream - ログSSEストリーミング
  GET  /api/containers/{name}/stats   - CPU/メモリ統計

セキュリティ:
  - コンテナ名は ^[a-zA-Z0-9_.-]{1,128}$ で検証
  - wrapper 経由のみ（直接 docker/podman CLI 実行禁止）
  - stop/restart/prune は audit_log 必須
  - docker/podman 不在時は 503
"""

import asyncio
import json
import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ...core import require_permission
from ...core.approval_service import ApprovalService
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/containers", tags=["containers"])

_approval_service = ApprovalService(db_path=settings.database.path)

# コンテナ名バリデーションパターン
_CONTAINER_NAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]{1,128}$")

# ラッパースクリプトパス（開発環境は wrappers/ を使用）
def _wrapper_path() -> str:
    """ラッパースクリプトのパスを返す（本番: /usr/local/sbin、開発: wrappers/）"""
    prod = Path("/usr/local/sbin/adminui-containers.sh")
    if prod.exists():
        return str(prod)
    dev = Path(__file__).parent.parent.parent.parent / "wrappers" / "adminui-containers.sh"
    return str(dev)


# ===================================================================
# ランタイム検出
# ===================================================================


def _detect_runtime() -> Optional[str]:
    """docker か podman を検出する"""
    for rt in ("docker", "podman"):
        if shutil.which(rt):
            return rt
    return None


# ===================================================================
# ラッパー呼び出し
# ===================================================================


def _run_wrapper(args: list[str], timeout: int = 30) -> dict[str, Any]:
    """
    コンテナ管理ラッパースクリプトを実行する

    Args:
        args: コマンド引数（サブコマンドと引数）
        timeout: タイムアウト秒数

    Returns:
        実行結果の辞書

    Raises:
        HTTPException: ランタイム不在(503)、ラッパー不在(503)
    """
    wrapper = _wrapper_path()
    cmd = ["sudo", wrapper] + args

    logger.info("Running container wrapper: %s", args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        # ランタイム不在チェック（exit code 2）
        if result.returncode == 2:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Neither docker nor podman is installed on this system",
            )

        # コンテナ名不正チェック（exit code 1 でエラーメッセージ付き）
        if result.returncode == 1 and "Error:" in stderr:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=stderr,
            )

        return {
            "status": "success" if result.returncode == 0 else "error",
            "stdout": stdout,
            "stderr": stderr,
            "returncode": result.returncode,
        }

    except HTTPException:
        raise
    except FileNotFoundError:
        logger.error("Container wrapper not found: %s", wrapper)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Container management wrapper not found",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Command timed out after {timeout}s",
        )
    except Exception as exc:
        logger.error("Wrapper execution error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


def _require_runtime() -> str:
    """docker/podman が存在しない場合は 503 を返す"""
    rt = _detect_runtime()
    if rt is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neither docker nor podman is installed on this system",
        )
    return rt


def _validate_container_name(name: str) -> None:
    """コンテナ名を検証する"""
    if not _CONTAINER_NAME_RE.match(name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid container name: only alphanumeric, underscore, dot, hyphen allowed (1-128 chars)",
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ===================================================================
# レスポンスモデル
# ===================================================================


class ContainerInfo(BaseModel):
    """コンテナ情報（一覧用）"""

    id: str = ""
    name: str = ""
    image: str = ""
    status: str = ""
    state: str = ""
    created: str = ""
    ports: str = ""
    runtime: str = ""


class ContainerListResponse(BaseModel):
    """コンテナ一覧レスポンス"""

    status: str
    runtime: Optional[str]
    containers: list[ContainerInfo]
    total: int
    running: int
    stopped: int
    timestamp: str


class ContainerDetailResponse(BaseModel):
    """コンテナ詳細レスポンス"""

    status: str
    name: str
    detail: Any
    timestamp: str


class ContainerActionResponse(BaseModel):
    """コンテナ操作レスポンス"""

    status: str
    name: str
    action: str
    message: str
    timestamp: str


class ContainerLogsResponse(BaseModel):
    """コンテナログレスポンス"""

    status: str
    name: str
    logs: str
    timestamp: str


class ContainerStatsResponse(BaseModel):
    """コンテナ統計レスポンス"""

    status: str
    name: str
    stats: Any
    timestamp: str


class ImageInfo(BaseModel):
    """イメージ情報"""

    id: str = ""
    repository: str = ""
    tag: str = ""
    size: str = ""
    created: str = ""


class ImageListResponse(BaseModel):
    """イメージ一覧レスポンス"""

    status: str
    runtime: Optional[str]
    images: list[ImageInfo]
    total: int
    timestamp: str


class PruneResponse(BaseModel):
    """停止コンテナ削除レスポンス"""

    status: str
    message: str
    output: str
    timestamp: str


class ApprovalRequestResponse(BaseModel):
    """承認リクエストレスポンス"""

    status: str
    message: str
    request_id: str
    action: str
    target: str
    timestamp: str


# ===================================================================
# ヘルパー: 出力パース
# ===================================================================


def _parse_container_list(stdout: str, runtime: str) -> list[ContainerInfo]:
    """
    docker/podman ps --format json の出力をパースする

    JSON Lines（1行1オブジェクト）と JSON 配列の両方に対応
    """
    containers: list[ContainerInfo] = []
    if not stdout:
        return containers

    # JSON 配列の場合
    if stdout.strip().startswith("["):
        try:
            items = json.loads(stdout)
            for item in items:
                containers.append(_dict_to_container(item, runtime))
            return containers
        except json.JSONDecodeError:
            pass

    # JSON Lines の場合
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            containers.append(_dict_to_container(item, runtime))
        except json.JSONDecodeError:
            logger.debug("Could not parse container line: %s", line)

    return containers


def _dict_to_container(d: dict[str, Any], runtime: str) -> ContainerInfo:
    """辞書をContainerInfoに変換（docker/podman フィールド差吸収）"""
    # Docker と Podman でフィールド名が異なる
    name = (
        d.get("Names") or d.get("Name") or d.get("name") or ""
    )
    if isinstance(name, list):
        name = ", ".join(name)
    # Docker の Names は "/nginx" のように / 付きのことがある
    if isinstance(name, str):
        name = name.lstrip("/")

    image = d.get("Image") or d.get("image") or ""
    cid = d.get("ID") or d.get("Id") or d.get("id") or ""
    state = d.get("State") or d.get("state") or d.get("Status") or d.get("status") or ""
    stat = d.get("Status") or d.get("status") or state
    created = d.get("CreatedAt") or d.get("Created") or d.get("created") or ""
    ports = d.get("Ports") or d.get("ports") or ""
    if isinstance(ports, (dict, list)):
        ports = str(ports)

    return ContainerInfo(
        id=str(cid)[:12],
        name=str(name),
        image=str(image),
        status=str(stat),
        state=str(state).lower(),
        created=str(created),
        ports=str(ports),
        runtime=runtime,
    )


def _parse_image_list(stdout: str, runtime: str) -> list[ImageInfo]:
    """docker/podman images --format json の出力をパースする"""
    images: list[ImageInfo] = []
    if not stdout:
        return images

    # JSON 配列
    if stdout.strip().startswith("["):
        try:
            items = json.loads(stdout)
            for item in items:
                images.append(_dict_to_image(item))
            return images
        except json.JSONDecodeError:
            pass

    # JSON Lines
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            images.append(_dict_to_image(item))
        except json.JSONDecodeError:
            logger.debug("Could not parse image line: %s", line)

    return images


def _dict_to_image(d: dict[str, Any]) -> ImageInfo:
    """辞書をImageInfoに変換"""
    repo = d.get("Repository") or d.get("repository") or d.get("Repo") or ""
    tag = d.get("Tag") or d.get("tag") or "latest"
    cid = d.get("ID") or d.get("Id") or d.get("id") or ""
    size = d.get("Size") or d.get("size") or d.get("VirtualSize") or ""
    created = d.get("CreatedAt") or d.get("Created") or d.get("created") or ""
    return ImageInfo(
        id=str(cid)[:12],
        repository=str(repo),
        tag=str(tag),
        size=str(size),
        created=str(created),
    )


# ===================================================================
# エンドポイント - 参照系（GET）
# ===================================================================


@router.get("", response_model=ContainerListResponse)
async def list_containers(
    current_user: TokenData = Depends(require_permission("read:containers")),
) -> ContainerListResponse:
    """
    コンテナ一覧を取得

    running / stopped 全コンテナを返す。
    docker/podman 不在時は 503。
    """
    runtime = _require_runtime()
    result = _run_wrapper(["list"])

    containers = _parse_container_list(result.get("stdout", ""), runtime)
    running = sum(1 for c in containers if "running" in c.state.lower() or "up" in c.status.lower())
    stopped = len(containers) - running

    return ContainerListResponse(
        status="success",
        runtime=runtime,
        containers=containers,
        total=len(containers),
        running=running,
        stopped=stopped,
        timestamp=_now_iso(),
    )


@router.get("/images", response_model=ImageListResponse)
async def list_images(
    current_user: TokenData = Depends(require_permission("read:containers")),
) -> ImageListResponse:
    """
    イメージ一覧を取得

    docker/podman 不在時は 503。
    """
    runtime = _require_runtime()
    result = _run_wrapper(["images"])

    images = _parse_image_list(result.get("stdout", ""), runtime)

    return ImageListResponse(
        status="success",
        runtime=runtime,
        images=images,
        total=len(images),
        timestamp=_now_iso(),
    )


@router.get("/{name}", response_model=ContainerDetailResponse)
async def inspect_container(
    name: str,
    current_user: TokenData = Depends(require_permission("read:containers")),
) -> ContainerDetailResponse:
    """
    コンテナ詳細情報（docker inspect）を取得
    """
    _validate_container_name(name)
    _require_runtime()

    result = _run_wrapper(["inspect", name])
    stdout = result.get("stdout", "")

    detail: Any = stdout
    try:
        detail = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        pass

    return ContainerDetailResponse(
        status="success",
        name=name,
        detail=detail,
        timestamp=_now_iso(),
    )


@router.get("/{name}/logs", response_model=ContainerLogsResponse)
async def get_container_logs(
    name: str,
    current_user: TokenData = Depends(require_permission("read:containers")),
) -> ContainerLogsResponse:
    """
    コンテナのログを取得（最新100行）
    """
    _validate_container_name(name)
    _require_runtime()

    result = _run_wrapper(["logs", name], timeout=15)

    return ContainerLogsResponse(
        status="success",
        name=name,
        logs=result.get("stdout", ""),
        timestamp=_now_iso(),
    )


@router.get("/{name}/stats", response_model=ContainerStatsResponse)
async def get_container_stats(
    name: str,
    current_user: TokenData = Depends(require_permission("read:containers")),
) -> ContainerStatsResponse:
    """
    コンテナの CPU / メモリ統計を取得
    """
    _validate_container_name(name)
    _require_runtime()

    result = _run_wrapper(["stats", name], timeout=15)
    stdout = result.get("stdout", "{}")

    stats: Any = {}
    try:
        stats = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        stats = {"raw": stdout}

    return ContainerStatsResponse(
        status="success",
        name=name,
        stats=stats,
        timestamp=_now_iso(),
    )


# ===================================================================
# エンドポイント - 操作系（POST）
# ===================================================================


@router.post("/{name}/start", response_model=ContainerActionResponse)
async def start_container(
    name: str,
    current_user: TokenData = Depends(require_permission("write:containers")),
) -> ContainerActionResponse:
    """
    コンテナを起動する（Operator 以上、承認フロー不要）

    audit_log に記録する。
    """
    _validate_container_name(name)
    _require_runtime()

    audit_log.record(
        operation="container_start",
        user_id=current_user.user_id,
        target=name,
        status="attempt",
    )

    result = _run_wrapper(["start", name])

    if result.get("returncode", 1) != 0:
        audit_log.record(
            operation="container_start",
            user_id=current_user.user_id,
            target=name,
            status="failure",
            details={"stderr": result.get("stderr", "")},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start container '{name}': {result.get('stderr', 'unknown error')}",
        )

    audit_log.record(
        operation="container_start",
        user_id=current_user.user_id,
        target=name,
        status="success",
    )
    logger.info("Container started: %s by %s", name, current_user.username)

    return ContainerActionResponse(
        status="success",
        name=name,
        action="start",
        message=f"Container '{name}' started successfully",
        timestamp=_now_iso(),
    )


@router.post("/{name}/stop", response_model=ApprovalRequestResponse)
async def stop_container(
    name: str,
    current_user: TokenData = Depends(require_permission("write:containers")),
) -> ApprovalRequestResponse:
    """
    コンテナ停止リクエストを承認フロー経由で作成する

    コンテナ停止は影響が大きいため承認が必要。
    承認後に approval_service が自動実行する。
    """
    _validate_container_name(name)
    _require_runtime()

    audit_log.record(
        operation="container_stop_request",
        user_id=current_user.user_id,
        target=name,
        status="attempt",
    )

    try:
        approval_result = await _approval_service.create_request(
            request_type="container_stop",
            payload={"container_name": name},
            reason=f"Stop container: {name}",
            requester_id=current_user.user_id,
            requester_name=current_user.username,
            requester_role=current_user.role,
        )
    except Exception as exc:
        logger.error("Failed to create stop approval request for container %s: %s", name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create approval request: {exc}",
        )

    request_id = approval_result.get("request_id", "")

    audit_log.record(
        operation="container_stop_request",
        user_id=current_user.user_id,
        target=name,
        status="pending",
        details={"request_id": request_id},
    )

    return ApprovalRequestResponse(
        status="pending",
        message=f"Container stop request submitted. Awaiting approval (ID: {request_id})",
        request_id=request_id,
        action="stop",
        target=name,
        timestamp=_now_iso(),
    )


@router.post("/{name}/restart", response_model=ApprovalRequestResponse)
async def restart_container(
    name: str,
    current_user: TokenData = Depends(require_permission("write:containers")),
) -> ApprovalRequestResponse:
    """
    コンテナ再起動リクエストを承認フロー経由で作成する

    コンテナ再起動は影響が大きいため承認が必要。
    """
    _validate_container_name(name)
    _require_runtime()

    audit_log.record(
        operation="container_restart_request",
        user_id=current_user.user_id,
        target=name,
        status="attempt",
    )

    try:
        approval_result = await _approval_service.create_request(
            request_type="container_restart",
            payload={"container_name": name},
            reason=f"Restart container: {name}",
            requester_id=current_user.user_id,
            requester_name=current_user.username,
            requester_role=current_user.role,
        )
    except Exception as exc:
        logger.error("Failed to create restart approval request for container %s: %s", name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create approval request: {exc}",
        )

    request_id = approval_result.get("request_id", "")

    audit_log.record(
        operation="container_restart_request",
        user_id=current_user.user_id,
        target=name,
        status="pending",
        details={"request_id": request_id},
    )

    return ApprovalRequestResponse(
        status="pending",
        message=f"Container restart request submitted. Awaiting approval (ID: {request_id})",
        request_id=request_id,
        action="restart",
        target=name,
        timestamp=_now_iso(),
    )


@router.post("/prune", response_model=ApprovalRequestResponse)
async def prune_stopped_containers(
    current_user: TokenData = Depends(require_permission("write:containers")),
) -> ApprovalRequestResponse:
    """
    停止コンテナ削除リクエストを承認フロー経由で作成する

    prune は全停止コンテナを削除するため承認が必要。
    """
    _require_runtime()

    audit_log.record(
        operation="container_prune_request",
        user_id=current_user.user_id,
        target="all-stopped",
        status="attempt",
    )

    try:
        approval_result = await _approval_service.create_request(
            request_type="container_prune",
            payload={"action": "prune-stopped"},
            reason="Prune all stopped containers",
            requester_id=current_user.user_id,
            requester_name=current_user.username,
            requester_role=current_user.role,
        )
    except Exception as exc:
        logger.error("Failed to create prune approval request: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create approval request: {exc}",
        )

    request_id = approval_result.get("request_id", "")

    audit_log.record(
        operation="container_prune_request",
        user_id=current_user.user_id,
        target="all-stopped",
        status="pending",
        details={"request_id": request_id},
    )

    return ApprovalRequestResponse(
        status="pending",
        message=f"Container prune request submitted. Awaiting approval (ID: {request_id})",
        request_id=request_id,
        action="prune",
        target="all-stopped-containers",
        timestamp=_now_iso(),
    )


# ===================================================================
# エンドポイント - SSE ログストリーミング
# ===================================================================


@router.get("/{name}/logs/stream")
async def stream_container_logs(
    name: str,
    tail: int = Query(default=100, ge=1, le=1000, description="取得する末尾行数（1〜1000）"),
    token: str = Query(..., description="JWT認証トークン（EventSource はヘッダー非対応のためクエリパラメータで渡す）"),
) -> StreamingResponse:
    """コンテナログを SSE (Server-Sent Events) でストリーミング配信する。

    EventSource API は Authorization ヘッダーを付与できないため、
    クエリパラメータ ``token`` で JWT を受け取り検証する。

    Args:
        name: コンテナ名（allowlist パターン検証済み）
        tail: 初期取得行数（1〜1000、デフォルト 100）
        token: JWT 認証トークン
    """
    from backend.core.auth import decode_token

    user_data = decode_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # read:containers 権限チェック
    from backend.core.auth import ROLES

    required = "read:containers"
    user_role = ROLES.get(user_data.role)
    if not user_role or required not in user_role.permissions:
        raise HTTPException(status_code=403, detail="Permission denied: read:containers required")

    _validate_container_name(name)
    _require_runtime()

    audit_log.record(
        operation="container_log_stream",
        user_id=user_data.user_id,
        target=name,
        status="start",
        details={"tail": tail},
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        proc = None
        try:
            connected_msg = json.dumps(
                {
                    "type": "start",
                    "container": name,
                    "tail": tail,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            yield f"data: {connected_msg}\n\n"

            proc = await asyncio.create_subprocess_exec(
                "sudo",
                "/usr/local/sbin/adminui-containers.sh",
                "logs",
                name,
                str(tail),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )

            while True:
                try:
                    line_bytes = await asyncio.wait_for(
                        proc.stdout.readline(),
                        timeout=30.0,
                    )
                    if not line_bytes:
                        break
                    line = line_bytes.decode("utf-8", errors="replace").rstrip("\n")
                    if line:
                        payload = json.dumps({"type": "log", "line": line})
                        yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

            done_msg = json.dumps({"type": "done", "container": name})
            yield f"data: {done_msg}\n\n"

        except asyncio.CancelledError:
            logger.info("SSE container log stream cancelled for %s", name)
        except Exception as exc:
            logger.error("SSE container log stream error for %s: %s", name, exc)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        finally:
            if proc and proc.returncode is None:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except Exception:
                    pass
            audit_log.record(
                operation="container_log_stream",
                user_id=user_data.user_id,
                target=name,
                status="end",
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
