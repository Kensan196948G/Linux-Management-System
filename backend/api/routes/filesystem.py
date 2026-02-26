"""ファイルシステム管理 API エンドポイント

提供エンドポイント:
  GET /api/filesystem/usage   - ファイルシステム使用量一覧
  GET /api/filesystem/mounts  - マウントポイント一覧
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/filesystem", tags=["filesystem"])

WARNING_THRESHOLD = 85  # 使用率警告閾値(%)


@router.get("/usage", status_code=status.HTTP_200_OK)
async def get_filesystem_usage(
    current_user: TokenData = Depends(require_permission("read:hardware")),
):
    """ファイルシステム使用量一覧"""
    try:
        result = sudo_wrapper.get_filesystem_usage()
        stdout = result.get("stdout", "") if isinstance(result, dict) else ""
        filesystems = []
        if stdout:
            try:
                filesystems = json.loads(stdout)
            except (json.JSONDecodeError, TypeError):
                pass
        # Add warning flags
        warnings = []
        for fs in filesystems if isinstance(filesystems, list) else []:
            pct_str = str(fs.get("use_pct", "0")).rstrip("%")
            try:
                pct = int(pct_str)
                fs["use_percent"] = pct
                if pct >= WARNING_THRESHOLD:
                    warnings.append({"filesystem": fs.get("mount"), "use_percent": pct})
            except (ValueError, AttributeError):
                pass
        audit_log.record(
            operation="filesystem_usage_view",
            user_id=current_user.user_id,
            target="filesystem",
            status="success",
            details={},
        )
        return {"status": "success", "filesystems": filesystems, "warnings": warnings}
    except SudoWrapperError as e:
        logger.error("Filesystem usage failed: %s", e)
        raise HTTPException(status_code=500, detail="Filesystem usage retrieval failed")


@router.get("/mounts", status_code=status.HTTP_200_OK)
async def get_filesystem_mounts(
    current_user: TokenData = Depends(require_permission("read:hardware")),
):
    """マウントポイント一覧"""
    try:
        result = sudo_wrapper.get_filesystem_mounts()
        audit_log.record(
            operation="filesystem_mounts_view",
            user_id=current_user.user_id,
            target="filesystem",
            status="success",
            details={},
        )
        return {"status": "success", "mounts": result}
    except SudoWrapperError as e:
        logger.error("Filesystem mounts failed: %s", e)
        raise HTTPException(status_code=500, detail="Filesystem mounts retrieval failed")
