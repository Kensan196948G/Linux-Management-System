"""
NFS マウント管理 API エンドポイント

提供エンドポイント:
  GET  /api/nfs/mounts   - 現在のNFSマウント一覧
  GET  /api/nfs/fstab    - /etc/fstab のNFSエントリ一覧
  POST /api/nfs/mount    - マウント要求（承認フロー経由）
  POST /api/nfs/umount   - アンマウント要求（承認フロー経由）
  GET  /api/nfs/status   - NFSサービス状態
"""

from __future__ import annotations

import logging
import re
import subprocess
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ...core import require_permission
from ...core.approval_service import ApprovalService
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.config import settings
from ...core.validation import validate_no_forbidden_chars as validate_input

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nfs", tags=["nfs"])

_approval_service = ApprovalService(db_path=settings.database.path)

# マウントポイントの許可プレフィックス
ALLOWED_MOUNT_PREFIXES = ("/mnt", "/media", "/srv/nfs", "/data/nfs")

# NFS サーバー名の正規表現 (ホスト名または IP)
_NFS_SERVER_RE = re.compile(r"^[a-zA-Z0-9._-]{1,253}$")
# エクスポートパスの正規表現
_EXPORT_PATH_RE = re.compile(r"^/[a-zA-Z0-9./_-]{0,255}$")
# マウントポイントの正規表現
_MOUNT_POINT_RE = re.compile(r"^/[a-zA-Z0-9./_-]{1,255}$")


def _validate_mount_point(mount_point: str) -> None:
    """マウントポイントが allowlist プレフィックスに含まれるか検証する。"""
    if not _MOUNT_POINT_RE.match(mount_point):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid mount point format: {mount_point!r}",
        )
    if not any(mount_point == prefix or mount_point.startswith(prefix + "/") for prefix in ALLOWED_MOUNT_PREFIXES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mount point not in allowed directories: {mount_point!r}",
        )


def _run_nfs_wrapper(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """adminui-nfs.sh ラッパーを実行して結果を返す。"""
    cmd = ["sudo", "/usr/local/sbin/adminui-nfs.sh", *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _parse_mount_line(line: str) -> Optional[dict]:
    """mount コマンドの出力行をパースして dict を返す。"""
    # 形式: <device> on <mount_point> type <fstype> (<options>)
    m = re.match(r"^(\S+)\s+on\s+(\S+)\s+type\s+(\S+)\s+\(([^)]*)\)$", line.strip())
    if not m:
        return None
    return {
        "device": m.group(1),
        "mount_point": m.group(2),
        "fstype": m.group(3),
        "options": m.group(4),
    }


def _parse_fstab_line(line: str) -> Optional[dict]:
    """fstab 行をパースして dict を返す。"""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split()
    if len(parts) < 4:
        return None
    return {
        "device": parts[0],
        "mount_point": parts[1],
        "fstype": parts[2],
        "options": parts[3],
        "dump": parts[4] if len(parts) > 4 else "0",
        "pass": parts[5] if len(parts) > 5 else "0",
    }


# ===================================================================
# Pydantic モデル
# ===================================================================


class MountEntry(BaseModel):
    """NFSマウントエントリ情報"""

    device: str
    mount_point: str
    fstype: str
    options: str


class FstabEntry(BaseModel):
    """fstabエントリ情報"""

    device: str
    mount_point: str
    fstype: str
    options: str
    dump: str = "0"
    passno: str = "0"


class MountsResponse(BaseModel):
    """NFSマウント一覧レスポンス"""

    status: str
    mounts: List[MountEntry] = Field(default_factory=list)
    total: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class FstabResponse(BaseModel):
    """fstabエントリ一覧レスポンス"""

    status: str
    entries: List[FstabEntry] = Field(default_factory=list)
    total: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class NfsStatusResponse(BaseModel):
    """NFSサービス状態レスポンス"""

    status: str
    nfs_available: bool = False
    active_mounts: int = 0
    message: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class MountRequest(BaseModel):
    """NFSマウント要求ボディ"""

    nfs_server: str = Field(..., min_length=1, max_length=253, description="NFSサーバーのホスト名またはIPアドレス")
    export_path: str = Field(..., min_length=1, max_length=256, description="NFSエクスポートパス (例: /export/data)")
    mount_point: str = Field(..., min_length=1, max_length=256, description="ローカルマウントポイント (例: /mnt/data)")
    options: str = Field(default="ro,noexec,nosuid", max_length=256, description="マウントオプション")

    @field_validator("nfs_server")
    @classmethod
    def validate_nfs_server(cls, v: str) -> str:
        """NFSサーバー名のバリデーション"""
        validate_input(v)
        if not _NFS_SERVER_RE.match(v):
            raise ValueError(f"Invalid NFS server: {v!r}")
        return v

    @field_validator("export_path")
    @classmethod
    def validate_export_path(cls, v: str) -> str:
        """エクスポートパスのバリデーション"""
        validate_input(v)
        if not _EXPORT_PATH_RE.match(v):
            raise ValueError(f"Invalid export path: {v!r}")
        return v

    @field_validator("mount_point")
    @classmethod
    def validate_mount_point(cls, v: str) -> str:
        """マウントポイントのバリデーション"""
        validate_input(v)
        if not _MOUNT_POINT_RE.match(v):
            raise ValueError(f"Invalid mount point format: {v!r}")
        if not any(v == prefix or v.startswith(prefix + "/") for prefix in ALLOWED_MOUNT_PREFIXES):
            raise ValueError(f"Mount point not in allowed directories: {v!r}")
        return v

    @field_validator("options")
    @classmethod
    def validate_options(cls, v: str) -> str:
        """マウントオプションのバリデーション"""
        validate_input(v)
        # オプションは英数字、カンマ、イコール、ハイフン、アンダースコアのみ
        if not re.match(r"^[a-zA-Z0-9,=_-]+$", v):
            raise ValueError(f"Invalid mount options: {v!r}")
        return v


class UmountRequest(BaseModel):
    """NFSアンマウント要求ボディ"""

    mount_point: str = Field(..., min_length=1, max_length=256, description="アンマウント対象のマウントポイント")

    @field_validator("mount_point")
    @classmethod
    def validate_mount_point(cls, v: str) -> str:
        """マウントポイントのバリデーション"""
        validate_input(v)
        if not _MOUNT_POINT_RE.match(v):
            raise ValueError(f"Invalid mount point format: {v!r}")
        if not any(v == prefix or v.startswith(prefix + "/") for prefix in ALLOWED_MOUNT_PREFIXES):
            raise ValueError(f"Mount point not in allowed directories: {v!r}")
        return v


class ApprovalRequestResponse(BaseModel):
    """承認リクエスト作成結果レスポンス"""

    status: str
    message: str
    request_id: str
    action: str
    target: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/mounts",
    response_model=MountsResponse,
    summary="現在のNFSマウント一覧取得",
    description="現在マウントされているNFSファイルシステムの一覧を返します",
)
async def get_nfs_mounts(
    current_user: TokenData = Depends(require_permission("read:nfs")),
) -> MountsResponse:
    """現在のNFSマウント一覧を取得する。"""
    try:
        result = _run_nfs_wrapper("list")
        mounts: List[MountEntry] = []
        for line in result.stdout.splitlines():
            entry = _parse_mount_line(line)
            if entry:
                mounts.append(MountEntry(**entry))

        audit_log.record(
            operation="nfs_list",
            user_id=current_user.user_id,
            target="nfs",
            status="success",
        )
        return MountsResponse(status="success", mounts=mounts, total=len(mounts))
    except subprocess.TimeoutExpired:
        logger.error("nfs list timed out")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="NFS list command timed out",
        )
    except Exception as exc:
        logger.error("nfs list error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list NFS mounts: {exc}",
        )


@router.get(
    "/fstab",
    response_model=FstabResponse,
    summary="/etc/fstab のNFSエントリ取得",
    description="/etc/fstab に記載されているNFSエントリの一覧を返します",
)
async def get_fstab_entries(
    current_user: TokenData = Depends(require_permission("read:nfs")),
) -> FstabResponse:
    """fstab のNFSエントリ一覧を返す。"""
    try:
        result = _run_nfs_wrapper("fstab")
        entries: List[FstabEntry] = []
        for line in result.stdout.splitlines():
            parsed = _parse_fstab_line(line)
            if parsed:
                entries.append(
                    FstabEntry(
                        device=parsed["device"],
                        mount_point=parsed["mount_point"],
                        fstype=parsed["fstype"],
                        options=parsed["options"],
                        dump=parsed["dump"],
                        passno=parsed["pass"],
                    )
                )

        audit_log.record(
            operation="nfs_fstab",
            user_id=current_user.user_id,
            target="nfs_fstab",
            status="success",
        )
        return FstabResponse(status="success", entries=entries, total=len(entries))
    except subprocess.TimeoutExpired:
        logger.error("nfs fstab timed out")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="NFS fstab command timed out",
        )
    except Exception as exc:
        logger.error("nfs fstab error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read fstab: {exc}",
        )


@router.post(
    "/mount",
    response_model=ApprovalRequestResponse,
    summary="NFSマウント要求（承認フロー）",
    description="NFSマウント要求を承認フロー経由で送信します（write:nfs 権限必要）",
)
async def request_mount(
    body: MountRequest,
    current_user: TokenData = Depends(require_permission("write:nfs")),
) -> ApprovalRequestResponse:
    """NFSマウントの承認リクエストを作成する。"""
    nfs_source = f"{body.nfs_server}:{body.export_path}"
    mount_point = body.mount_point

    audit_log.record(
        operation="nfs_mount_request",
        user_id=current_user.user_id,
        target=mount_point,
        status="attempt",
    )

    try:
        approval_result = await _approval_service.create_request(
            request_type="nfs_mount",
            payload={
                "nfs_server": body.nfs_server,
                "export_path": body.export_path,
                "mount_point": mount_point,
                "options": body.options,
                "nfs_source": nfs_source,
            },
            reason=f"Mount NFS: {nfs_source} -> {mount_point}",
            requester_id=current_user.user_id,
            requester_name=current_user.username,
            requester_role=current_user.role,
        )
    except Exception as exc:
        logger.error("Failed to create NFS mount approval request: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create approval request: {exc}",
        )

    request_id = approval_result.get("request_id", "")

    audit_log.record(
        operation="nfs_mount_request",
        user_id=current_user.user_id,
        target=mount_point,
        status="pending",
        details={"request_id": request_id, "nfs_source": nfs_source},
    )

    return ApprovalRequestResponse(
        status="pending",
        message=f"NFSマウント要求を送信しました。承認待ち (ID: {request_id})",
        request_id=request_id,
        action="mount",
        target=mount_point,
    )


@router.post(
    "/umount",
    response_model=ApprovalRequestResponse,
    summary="NFSアンマウント要求（承認フロー）",
    description="NFSアンマウント要求を承認フロー経由で送信します（write:nfs 権限必要）",
)
async def request_umount(
    body: UmountRequest,
    current_user: TokenData = Depends(require_permission("write:nfs")),
) -> ApprovalRequestResponse:
    """NFSアンマウントの承認リクエストを作成する。"""
    mount_point = body.mount_point

    audit_log.record(
        operation="nfs_umount_request",
        user_id=current_user.user_id,
        target=mount_point,
        status="attempt",
    )

    try:
        approval_result = await _approval_service.create_request(
            request_type="nfs_umount",
            payload={"mount_point": mount_point},
            reason=f"Unmount NFS: {mount_point}",
            requester_id=current_user.user_id,
            requester_name=current_user.username,
            requester_role=current_user.role,
        )
    except Exception as exc:
        logger.error("Failed to create NFS umount approval request: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create approval request: {exc}",
        )

    request_id = approval_result.get("request_id", "")

    audit_log.record(
        operation="nfs_umount_request",
        user_id=current_user.user_id,
        target=mount_point,
        status="pending",
        details={"request_id": request_id},
    )

    return ApprovalRequestResponse(
        status="pending",
        message=f"NFSアンマウント要求を送信しました。承認待ち (ID: {request_id})",
        request_id=request_id,
        action="umount",
        target=mount_point,
    )


@router.get(
    "/status",
    response_model=NfsStatusResponse,
    summary="NFSサービス状態取得",
    description="NFS クライアントが利用可能か確認し、アクティブなマウント数を返します",
)
async def get_nfs_status(
    current_user: TokenData = Depends(require_permission("read:nfs")),
) -> NfsStatusResponse:
    """NFSサービスの状態を取得する。"""
    try:
        # mount コマンド自体の確認
        which_result = subprocess.run(
            ["which", "mount"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        nfs_available = which_result.returncode == 0

        active_mounts = 0
        if nfs_available:
            check_result = _run_nfs_wrapper("check")
            active_mounts = len([line for line in check_result.stdout.splitlines() if line.strip()])

        audit_log.record(
            operation="nfs_status",
            user_id=current_user.user_id,
            target="nfs",
            status="success",
        )
        return NfsStatusResponse(
            status="success",
            nfs_available=nfs_available,
            active_mounts=active_mounts,
            message="NFS client available" if nfs_available else "mount command not found",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="NFS status check timed out",
        )
    except Exception as exc:
        logger.error("nfs status error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get NFS status: {exc}",
        )
