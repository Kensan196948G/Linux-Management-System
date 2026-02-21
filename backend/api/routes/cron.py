"""
Cron ジョブ管理 API エンドポイント

ユーザーの crontab エントリの一覧取得・追加・削除・有効/無効切替を提供
セキュリティ: allowlist方式、多重防御、監査証跡
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from ...core import get_current_user, require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError
from ...core.validation import (
    ValidationError,
    validate_no_forbidden_chars,
    validate_username,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cron", tags=["cron"])


# ===================================================================
# 定数定義（allowlist / denylist）
# ===================================================================

ALLOWED_CRON_COMMANDS: list[str] = [
    "/usr/bin/rsync",
    "/usr/local/bin/healthcheck.sh",
    "/usr/bin/find",
    "/usr/bin/tar",
    "/usr/bin/gzip",
    "/usr/bin/curl",
    "/usr/bin/wget",
    "/usr/bin/python3",
    "/usr/bin/node",
]

FORBIDDEN_CRON_COMMANDS: list[str] = [
    "/bin/bash",
    "/bin/sh",
    "/bin/zsh",
    "/bin/dash",
    "/usr/bin/bash",
    "/usr/bin/sh",
    "/bin/rm",
    "/usr/bin/rm",
    "/sbin/reboot",
    "/sbin/shutdown",
    "/sbin/init",
    "/sbin/mkfs",
    "/sbin/fdisk",
    "/usr/bin/dd",
    "/bin/dd",
    "/usr/bin/sudo",
    "/usr/sbin/visudo",
    "/usr/bin/chmod",
    "/usr/bin/chown",
    "/bin/chmod",
    "/bin/chown",
]

# 引数に許可しない文字（スケジュール用の * / は許可するが、引数では禁止）
FORBIDDEN_ARGUMENT_CHARS: list[str] = [
    ";",
    "|",
    "&",
    "$",
    "(",
    ")",
    "`",
    "{",
    "}",
    "[",
    "]",
]

MAX_CRON_JOBS_PER_USER: int = 10
MAX_ARGS_LENGTH: int = 512
MAX_COMMENT_LENGTH: int = 256


# ===================================================================
# リクエスト/レスポンスモデル
# ===================================================================


class CronJobInfo(BaseModel):
    """個別 Cron ジョブ情報"""

    id: str
    line_number: int
    schedule: str
    command: str
    arguments: str = ""
    comment: str = ""
    enabled: bool


class CronJobListResponse(BaseModel):
    """Cron ジョブ一覧レスポンス"""

    status: str
    user: str
    jobs: list[CronJobInfo]
    total_count: int
    max_allowed: int


class AddCronJobRequest(BaseModel):
    """Cron ジョブ追加リクエスト"""

    schedule: str = Field(
        ...,
        description="Cron 式スケジュール (例: '0 2 * * *')",
        max_length=50,
    )
    command: str = Field(
        ...,
        description="実行コマンド（絶対パス必須、allowlist のみ）",
        max_length=256,
    )
    arguments: Optional[str] = Field(
        None,
        description="コマンド引数",
        max_length=MAX_ARGS_LENGTH,
    )
    comment: Optional[str] = Field(
        None,
        description="ジョブの説明",
        max_length=MAX_COMMENT_LENGTH,
    )

    @field_validator("schedule")
    @classmethod
    def validate_schedule_format(cls, v: str) -> str:
        """スケジュール形式の基本検証"""
        # インジェクション文字を拒否
        for char in [
            ";",
            "|",
            "&",
            "$",
            "(",
            ")",
            "`",
            ">",
            "<",
            "?",
            "{",
            "}",
            "[",
            "]",
        ]:
            if char in v:
                raise ValueError(f"Forbidden character in schedule: {char}")

        # 5フィールドであることを確認
        fields = v.strip().split()
        if len(fields) != 5:
            raise ValueError("Schedule must have exactly 5 fields")

        # 各フィールドが許可文字のみであることを確認
        import re

        field_pattern = re.compile(r"^[0-9\*\/\,\-]+$")
        for field in fields:
            if not field_pattern.match(field):
                raise ValueError(f"Invalid characters in schedule field: {field}")

        # 最小間隔チェック（毎分や */1 ~ */4 は拒否）
        minute = fields[0]
        if minute == "*":
            raise ValueError("Execution interval too short (minimum: */5)")
        if re.match(r"^\*/[1-4]$", minute):
            raise ValueError(f"Execution interval too short: {minute} (minimum: */5)")

        return v

    @field_validator("command")
    @classmethod
    def validate_command_allowlist(cls, v: str) -> str:
        """コマンドが allowlist に含まれることを検証"""
        # 禁止文字チェック
        for char in [
            ";",
            "|",
            "&",
            "$",
            "(",
            ")",
            "`",
            ">",
            "<",
            "*",
            "?",
            "{",
            "}",
            "[",
            "]",
        ]:
            if char in v:
                raise ValueError(f"Forbidden character in command: {char}")

        # 絶対パスチェック
        if not v.startswith("/"):
            raise ValueError("Command must be an absolute path")

        # 禁止コマンドチェック
        if v in FORBIDDEN_CRON_COMMANDS:
            raise ValueError(f"Forbidden command: {v}")

        # allowlist チェック
        if v not in ALLOWED_CRON_COMMANDS:
            raise ValueError(f"Command not in allowlist: {v}")

        return v

    @field_validator("arguments")
    @classmethod
    def validate_arguments_safe(cls, v: Optional[str]) -> Optional[str]:
        """引数の安全性チェック"""
        if v is None:
            return v

        # 禁止文字チェック
        for char in FORBIDDEN_ARGUMENT_CHARS:
            if char in v:
                raise ValueError(f"Forbidden character in arguments: {char}")

        # パストラバーサルチェック
        if ".." in v:
            raise ValueError("Path traversal detected in arguments")

        return v

    @field_validator("comment")
    @classmethod
    def validate_comment_safe(cls, v: Optional[str]) -> Optional[str]:
        """コメントの安全性チェック"""
        if v is None:
            return v

        # 禁止文字チェック
        for char in FORBIDDEN_ARGUMENT_CHARS:
            if char in v:
                raise ValueError(f"Forbidden character in comment: {char}")

        return v


class RemoveCronJobRequest(BaseModel):
    """Cron ジョブ削除リクエスト"""

    line_number: int = Field(
        ...,
        ge=1,
        le=9999,
        description="削除対象の行番号",
    )


class ToggleCronJobRequest(BaseModel):
    """Cron ジョブ有効/無効切替リクエスト"""

    line_number: int = Field(
        ...,
        ge=1,
        le=9999,
        description="対象の行番号",
    )
    enabled: bool = Field(
        ...,
        description="true で有効化、false で無効化",
    )


class CronJobActionResponse(BaseModel):
    """Cron ジョブ操作結果レスポンス"""

    status: str
    message: str
    user: str


# ===================================================================
# エンドポイント
# ===================================================================


@router.get("/{username}", response_model=CronJobListResponse)
async def list_cron_jobs(
    username: str,
    current_user: TokenData = Depends(require_permission("read:cron")),
):
    """
    指定ユーザーの Cron ジョブ一覧を取得

    Args:
        username: 対象ユーザー名
        current_user: 現在のユーザー (read:cron 権限必須)

    Returns:
        Cron ジョブ一覧

    Raises:
        HTTPException: 取得失敗時
    """
    # ユーザー名の検証
    try:
        validate_username(username)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    logger.info(f"Cron list requested: target={username}, by={current_user.username}")

    # 監査ログ記録（試行）
    audit_log.record(
        operation="cron_list",
        user_id=current_user.user_id,
        target=username,
        status="attempt",
        details={"target_user": username},
    )

    try:
        result = sudo_wrapper.list_cron_jobs(username)

        # ラッパーがエラーを返した場合
        if result.get("status") == "error":
            error_code = result.get("code", "UNKNOWN")
            error_message = result.get("message", "Unknown error")

            audit_log.record(
                operation="cron_list",
                user_id=current_user.user_id,
                target=username,
                status="denied",
                details={"code": error_code, "message": error_message},
            )

            # エラーコードに応じた HTTP ステータス
            if error_code in ("INVALID_USERNAME", "INVALID_ARGS"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_message,
                )
            elif error_code in ("FORBIDDEN_USER", "FORBIDDEN_CHARS"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=error_message,
                )
            elif error_code == "USER_NOT_FOUND":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=error_message,
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=error_message,
                )

        # 監査ログ記録（成功）
        audit_log.record(
            operation="cron_list",
            user_id=current_user.user_id,
            target=username,
            status="success",
            details={"total_count": result.get("total_count", 0)},
        )

        logger.info(
            f"Cron list retrieved: user={username}, "
            f"count={result.get('total_count', 0)}"
        )

        return CronJobListResponse(**result)

    except SudoWrapperError as e:
        audit_log.record(
            operation="cron_list",
            user_id=current_user.user_id,
            target=username,
            status="failure",
            details={"error": str(e)},
        )

        logger.error(f"Cron list failed: user={username}, error={e}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cron job list retrieval failed: {str(e)}",
        )


@router.post("/{username}", response_model=CronJobActionResponse)
async def add_cron_job(
    username: str,
    request: AddCronJobRequest,
    current_user: TokenData = Depends(require_permission("write:cron")),
):
    """
    指定ユーザーに Cron ジョブを追加

    Args:
        username: 対象ユーザー名
        request: 追加ジョブ情報
        current_user: 現在のユーザー (write:cron 権限必須)

    Returns:
        操作結果

    Raises:
        HTTPException: 追加失敗時
    """
    # ユーザー名の検証
    try:
        validate_username(username)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    logger.info(
        f"Cron add requested: target={username}, command={request.command}, "
        f"schedule={request.schedule}, by={current_user.username}"
    )

    # 監査ログ記録（試行）
    audit_log.record(
        operation="cron_add",
        user_id=current_user.user_id,
        target=username,
        status="attempt",
        details={
            "schedule": request.schedule,
            "command": request.command,
            "arguments": request.arguments or "",
        },
    )

    try:
        result = sudo_wrapper.add_cron_job(
            username=username,
            schedule=request.schedule,
            command=request.command,
            arguments=request.arguments or "",
            comment=request.comment or "",
        )

        # ラッパーがエラーを返した場合
        if result.get("status") == "error":
            error_code = result.get("code", "UNKNOWN")
            error_message = result.get("message", "Unknown error")

            audit_log.record(
                operation="cron_add",
                user_id=current_user.user_id,
                target=username,
                status="denied",
                details={"code": error_code, "message": error_message},
            )

            if error_code in (
                "INVALID_USERNAME",
                "INVALID_ARGS",
                "INVALID_SCHEDULE",
                "INVALID_COMMAND",
                "INVALID_ARGUMENTS",
                "INVALID_COMMENT",
                "PATH_TRAVERSAL",
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_message,
                )
            elif error_code in (
                "FORBIDDEN_USER",
                "FORBIDDEN_CHARS",
                "FORBIDDEN_COMMAND",
                "COMMAND_NOT_ALLOWED",
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=error_message,
                )
            elif error_code == "USER_NOT_FOUND":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=error_message,
                )
            elif error_code in ("MAX_JOBS_EXCEEDED", "DUPLICATE_JOB"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=error_message,
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=error_message,
                )

        # 監査ログ記録（成功）
        audit_log.record(
            operation="cron_add",
            user_id=current_user.user_id,
            target=username,
            status="success",
            details={
                "schedule": request.schedule,
                "command": request.command,
                "total_jobs": result.get("total_jobs", 0),
            },
        )

        logger.info(f"Cron add successful: user={username}, command={request.command}")

        return CronJobActionResponse(
            status="success",
            message=result.get("message", "Cron job added successfully"),
            user=username,
        )

    except SudoWrapperError as e:
        audit_log.record(
            operation="cron_add",
            user_id=current_user.user_id,
            target=username,
            status="failure",
            details={"error": str(e)},
        )

        logger.error(f"Cron add failed: user={username}, error={e}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cron job addition failed: {str(e)}",
        )


@router.delete("/{username}", response_model=CronJobActionResponse)
async def remove_cron_job(
    username: str,
    request: RemoveCronJobRequest,
    current_user: TokenData = Depends(require_permission("write:cron")),
):
    """
    指定ユーザーの Cron ジョブを削除（コメントアウト方式）

    Args:
        username: 対象ユーザー名
        request: 削除対象の行番号
        current_user: 現在のユーザー (write:cron 権限必須)

    Returns:
        操作結果

    Raises:
        HTTPException: 削除失敗時
    """
    # ユーザー名の検証
    try:
        validate_username(username)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    logger.info(
        f"Cron remove requested: target={username}, "
        f"line={request.line_number}, by={current_user.username}"
    )

    # 監査ログ記録（試行）
    audit_log.record(
        operation="cron_remove",
        user_id=current_user.user_id,
        target=username,
        status="attempt",
        details={"line_number": request.line_number},
    )

    try:
        result = sudo_wrapper.remove_cron_job(
            username=username,
            line_number=request.line_number,
        )

        # ラッパーがエラーを返した場合
        if result.get("status") == "error":
            error_code = result.get("code", "UNKNOWN")
            error_message = result.get("message", "Unknown error")

            audit_log.record(
                operation="cron_remove",
                user_id=current_user.user_id,
                target=username,
                status="denied",
                details={"code": error_code, "message": error_message},
            )

            if error_code in (
                "INVALID_USERNAME",
                "INVALID_ARGS",
                "INVALID_LINE_NUMBER",
                "NOT_A_JOB",
                "ALREADY_DISABLED",
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_message,
                )
            elif error_code in ("FORBIDDEN_USER", "FORBIDDEN_CHARS"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=error_message,
                )
            elif error_code in ("USER_NOT_FOUND", "LINE_NOT_FOUND"):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=error_message,
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=error_message,
                )

        # 監査ログ記録（成功）
        audit_log.record(
            operation="cron_remove",
            user_id=current_user.user_id,
            target=username,
            status="success",
            details={
                "line_number": request.line_number,
                "remaining_jobs": result.get("remaining_jobs", 0),
            },
        )

        logger.info(
            f"Cron remove successful: user={username}, line={request.line_number}"
        )

        return CronJobActionResponse(
            status="success",
            message=result.get("message", "Cron job disabled (commented out)"),
            user=username,
        )

    except SudoWrapperError as e:
        audit_log.record(
            operation="cron_remove",
            user_id=current_user.user_id,
            target=username,
            status="failure",
            details={"error": str(e)},
        )

        logger.error(f"Cron remove failed: user={username}, error={e}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cron job removal failed: {str(e)}",
        )


@router.put("/{username}/toggle", response_model=CronJobActionResponse)
async def toggle_cron_job(
    username: str,
    request: ToggleCronJobRequest,
    current_user: TokenData = Depends(require_permission("write:cron")),
):
    """
    指定ユーザーの Cron ジョブの有効/無効を切り替え

    Args:
        username: 対象ユーザー名
        request: 切替対象の行番号と状態
        current_user: 現在のユーザー (write:cron 権限必須)

    Returns:
        操作結果

    Raises:
        HTTPException: 切替失敗時
    """
    # ユーザー名の検証
    try:
        validate_username(username)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    action = "enable" if request.enabled else "disable"

    logger.info(
        f"Cron toggle requested: target={username}, "
        f"line={request.line_number}, action={action}, "
        f"by={current_user.username}"
    )

    # 監査ログ記録（試行）
    audit_log.record(
        operation="cron_toggle",
        user_id=current_user.user_id,
        target=username,
        status="attempt",
        details={
            "line_number": request.line_number,
            "action": action,
        },
    )

    try:
        result = sudo_wrapper.toggle_cron_job(
            username=username,
            line_number=request.line_number,
            action=action,
        )

        # ラッパーがエラーを返した場合
        if result.get("status") == "error":
            error_code = result.get("code", "UNKNOWN")
            error_message = result.get("message", "Unknown error")

            audit_log.record(
                operation="cron_toggle",
                user_id=current_user.user_id,
                target=username,
                status="denied",
                details={"code": error_code, "message": error_message},
            )

            if error_code in (
                "INVALID_USERNAME",
                "INVALID_ARGS",
                "INVALID_LINE_NUMBER",
                "INVALID_ACTION",
                "NOT_A_JOB",
                "ALREADY_DISABLED",
                "ALREADY_ENABLED",
                "NOT_ADMINUI_COMMENT",
                "PARSE_ERROR",
                "INVALID_SCHEDULE",
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_message,
                )
            elif error_code in (
                "FORBIDDEN_USER",
                "FORBIDDEN_CHARS",
                "COMMAND_NOT_ALLOWED",
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=error_message,
                )
            elif error_code in ("USER_NOT_FOUND", "LINE_NOT_FOUND"):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=error_message,
                )
            elif error_code == "MAX_JOBS_EXCEEDED":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=error_message,
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=error_message,
                )

        # 監査ログ記録（成功）
        audit_log.record(
            operation="cron_toggle",
            user_id=current_user.user_id,
            target=username,
            status="success",
            details={
                "line_number": request.line_number,
                "action": action,
                "active_jobs": result.get("active_jobs", 0),
            },
        )

        logger.info(
            f"Cron toggle successful: user={username}, "
            f"line={request.line_number}, action={action}"
        )

        return CronJobActionResponse(
            status="success",
            message=result.get("message", f"Cron job {action}d"),
            user=username,
        )

    except SudoWrapperError as e:
        audit_log.record(
            operation="cron_toggle",
            user_id=current_user.user_id,
            target=username,
            status="failure",
            details={"error": str(e)},
        )

        logger.error(f"Cron toggle failed: user={username}, error={e}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cron job toggle failed: {str(e)}",
        )
