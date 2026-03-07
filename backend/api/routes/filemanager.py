"""ファイルマネージャー API エンドポイント

読み取り専用のファイルブラウジングを提供。パストラバーサル攻撃を防ぐ。

エンドポイント:
  GET  /api/files/allowed-dirs  - アクセス許可ディレクトリ一覧 (認証不要)
  GET  /api/files/list          - ディレクトリ内容一覧
  GET  /api/files/stat          - ファイル属性
  GET  /api/files/read          - ファイル内容 (1-200行)
  GET  /api/files/search        - ファイル検索
  POST /api/files/upload        - ファイルアップロード (許可ディレクトリのみ)
  POST /api/files/chmod         - パーミッション変更
"""

import logging
import os
import re

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/files", tags=["filemanager"])

# アクセス許可ベースディレクトリ (セキュリティ: validate_path()でパストラバーサル防止済み)
ALLOWED_BASE_DIRS = [
    "/tmp",  # nosec B108 - allowlist管理済み・validate_path()でパストラバーサル防止
    "/var/log",
    "/etc/nginx",
    "/etc/apache2",
    "/etc/ssh",
    "/var/www",
    "/home",
]


def validate_path(path: str) -> str:
    """パストラバーサル攻撃を防ぐパス検証。

    Args:
        path: 検証対象のパス文字列

    Returns:
        正規化済みパス

    Raises:
        HTTPException: 不正なパスの場合 (400)
    """
    if not path:
        raise HTTPException(status_code=400, detail="Invalid or disallowed path")

    # ../ 含有チェック
    if "../" in path or "/.." in path or path == "..":
        raise HTTPException(status_code=400, detail="Invalid or disallowed path")

    # Null バイトチェック
    if "\x00" in path:
        raise HTTPException(status_code=400, detail="Invalid or disallowed path")

    # 絶対パスで始まることを要求
    if not path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid or disallowed path")

    # ALLOWED_BASE_DIRS 検証
    allowed = False
    for base_dir in ALLOWED_BASE_DIRS:
        if path == base_dir or path.startswith(base_dir + "/"):
            allowed = True
            break

    if not allowed:
        raise HTTPException(status_code=400, detail="Invalid or disallowed path")

    # os.path.realpath() で正規化後に再検証
    real_path = os.path.realpath(path)
    allowed_real = False
    for base_dir in ALLOWED_BASE_DIRS:
        real_base = os.path.realpath(base_dir)
        if real_path == real_base or real_path.startswith(real_base + "/"):
            allowed_real = True
            break

    if not allowed_real:
        raise HTTPException(status_code=400, detail="Invalid or disallowed path")

    return real_path


@router.get("/allowed-dirs", status_code=status.HTTP_200_OK)
async def get_allowed_dirs():
    """アクセス許可ディレクトリ一覧を返す（認証不要）。"""
    return {"status": "success", "allowed_dirs": ALLOWED_BASE_DIRS}


@router.get("/list", status_code=status.HTTP_200_OK)
async def list_directory(
    path: str = Query(..., description="一覧表示するディレクトリパス"),
    current_user: TokenData = Depends(require_permission("read:filemanager")),
):
    """ディレクトリ内容一覧を返す。"""
    validated_path = validate_path(path)
    try:
        result = sudo_wrapper.list_files(validated_path)
        audit_log.record(
            operation="filemanager_list",
            user_id=current_user.user_id,
            target=validated_path,
            status="success",
            details={},
        )
        return {"status": "success", "path": validated_path, "output": result.get("stdout", "")}
    except SudoWrapperError as e:
        logger.error("filemanager list failed: %s", e)
        raise HTTPException(status_code=500, detail="Directory listing failed")


@router.get("/stat", status_code=status.HTTP_200_OK)
async def stat_file(
    path: str = Query(..., description="属性を取得するファイルパス"),
    current_user: TokenData = Depends(require_permission("read:filemanager")),
):
    """ファイル属性を返す。"""
    validated_path = validate_path(path)
    try:
        result = sudo_wrapper.stat_file(validated_path)
        audit_log.record(
            operation="filemanager_stat",
            user_id=current_user.user_id,
            target=validated_path,
            status="success",
            details={},
        )
        return {"status": "success", "path": validated_path, "output": result.get("stdout", "")}
    except SudoWrapperError as e:
        logger.error("filemanager stat failed: %s", e)
        raise HTTPException(status_code=500, detail="File stat failed")


@router.get("/read", status_code=status.HTTP_200_OK)
async def read_file(
    path: str = Query(..., description="読み取るファイルパス"),
    lines: int = Query(default=50, ge=1, le=200, description="読み取る行数 (1-200)"),
    current_user: TokenData = Depends(require_permission("read:filemanager")),
):
    """ファイル内容を返す（最大200行）。"""
    validated_path = validate_path(path)
    try:
        result = sudo_wrapper.read_file(validated_path, lines)
        audit_log.record(
            operation="filemanager_read",
            user_id=current_user.user_id,
            target=validated_path,
            status="success",
            details={"lines": lines},
        )
        return {"status": "success", "path": validated_path, "lines": lines, "content": result.get("stdout", "")}
    except SudoWrapperError as e:
        logger.error("filemanager read failed: %s", e)
        raise HTTPException(status_code=500, detail="File read failed")


@router.get("/search", status_code=status.HTTP_200_OK)
async def search_files(
    directory: str = Query(..., description="検索するディレクトリパス"),
    pattern: str = Query(..., description="検索パターン (例: *.log)"),
    current_user: TokenData = Depends(require_permission("read:filemanager")),
):
    """ディレクトリ内のファイルを検索する（maxdepth=2）。"""
    validated_dir = validate_path(directory)
    # パターンの基本検証（禁止文字）
    forbidden = [";", "|", "&", "$", "(", ")", "`", ">", "<"]
    for char in forbidden:
        if char in pattern:
            raise HTTPException(status_code=400, detail="Invalid or disallowed path")
    try:
        result = sudo_wrapper.search_files(validated_dir, pattern)
        audit_log.record(
            operation="filemanager_search",
            user_id=current_user.user_id,
            target=validated_dir,
            status="success",
            details={"pattern": pattern},
        )
        files = [line for line in result.get("stdout", "").splitlines() if line]
        return {"status": "success", "directory": validated_dir, "pattern": pattern, "files": files}
    except SudoWrapperError as e:
        logger.error("filemanager search failed: %s", e)
        raise HTTPException(status_code=500, detail="File search failed")


class ChmodRequest(BaseModel):
    """パーミッション変更リクエスト"""

    path: str
    mode: str


# ファイルアップロード許可ディレクトリ (書き込み可能ディレクトリのみ)
UPLOAD_ALLOWED_DIRS = ["/var/www", "/home", "/tmp"]  # nosec B108 - allowlist管理済み

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/upload", status_code=status.HTTP_200_OK)
async def upload_file(
    file: UploadFile = File(...),
    dest_path: str = Form(...),
    current_user: TokenData = Depends(require_permission("write:filemanager")),
):
    """ファイルをアップロードする (許可ディレクトリのみ・最大10MB)"""
    # アップロード先パス検証
    validated_dest = validate_path(dest_path)
    allowed = any(validated_dest.startswith(d) for d in UPLOAD_ALLOWED_DIRS)
    if not allowed:
        raise HTTPException(status_code=403, detail="Upload not allowed in this directory")

    # ファイル名検証
    filename = os.path.basename(file.filename or "")
    if not filename or not re.match(r"^[a-zA-Z0-9._\-]+$", filename):
        raise HTTPException(status_code=422, detail="Invalid filename")

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")

    try:
        result = sudo_wrapper.upload_file(validated_dest, filename, content)
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("stderr", "Upload failed"))
        audit_log.record(
            operation="filemanager_upload",
            user_id=current_user.user_id,
            target=f"{validated_dest}/{filename}",
            status="success",
            details={"size": len(content)},
        )
        return {"status": "success", "path": f"{validated_dest}/{filename}", "size": len(content)}
    except (SudoWrapperError, ValueError) as e:
        logger.error("filemanager upload failed: %s", e)
        raise HTTPException(status_code=500, detail="File upload failed")


@router.post("/chmod", status_code=status.HTTP_200_OK)
async def chmod_file(
    req: ChmodRequest,
    current_user: TokenData = Depends(require_permission("write:filemanager")),
):
    """ファイル/ディレクトリのパーミッションを変更する (octal: 例 644, 755)"""
    if not re.match(r"^[0-7]{3,4}$", req.mode):
        raise HTTPException(status_code=422, detail="Invalid mode: must be 3-4 octal digits")

    validated_path = validate_path(req.path)
    try:
        result = sudo_wrapper.chmod_file(validated_path, req.mode)
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("stderr", "chmod failed"))
        audit_log.record(
            operation="filemanager_chmod",
            user_id=current_user.user_id,
            target=validated_path,
            status="success",
            details={"mode": req.mode},
        )
        return {"status": "success", "path": validated_path, "mode": req.mode}
    except (SudoWrapperError, ValueError) as e:
        logger.error("filemanager chmod failed: %s", e)
        raise HTTPException(status_code=500, detail="chmod failed")
