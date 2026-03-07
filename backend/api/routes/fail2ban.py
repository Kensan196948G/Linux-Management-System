"""
Fail2ban 管理 API エンドポイント

提供エンドポイント:
  GET  /api/fail2ban/status                   - fail2ban サービス状態
  GET  /api/fail2ban/jails                    - jail 一覧
  GET  /api/fail2ban/jails/{jail_name}        - jail 詳細
  GET  /api/fail2ban/jails/{jail_name}/banned - 禁止 IP 一覧
  POST /api/fail2ban/jails/{jail_name}/unban  - IP unban（Operator 以上）
  POST /api/fail2ban/jails/{jail_name}/ban    - IP ban（Approver/Admin のみ）
  GET  /api/fail2ban/summary                  - 全 jail 統計サマリー
  POST /api/fail2ban/reload                   - 設定リロード（承認フロー）
"""

import logging
import re
import subprocess
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fail2ban", tags=["fail2ban"])

# jail 名の正規表現
_JAIL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
# IPv4 と IPv6 の正規表現
_IPV4_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
_IPV6_RE = re.compile(r"^[0-9a-fA-F:]{2,39}$")


def _validate_jail_name(jail_name: str) -> str:
    """jail 名をバリデーションして返す。不正な場合は 400 を返す。"""
    if not _JAIL_NAME_RE.match(jail_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid jail name: {jail_name!r}",
        )
    return jail_name


def _validate_ip(ip: str) -> str:
    """IP アドレスをバリデーションして返す。不正な場合は 400 を返す。"""
    if not (_IPV4_RE.match(ip) or _IPV6_RE.match(ip)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid IP address: {ip!r}",
        )
    return ip


def _check_fail2ban_available() -> None:
    """
    fail2ban-client が利用可能か確認する。

    Raises:
        HTTPException: fail2ban-client が見つからない場合は 503
    """
    try:
        result = subprocess.run(
            ["which", "fail2ban-client"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="fail2ban-client not found. Is fail2ban installed?",
            )
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="fail2ban availability check timed out",
        )


def _run_fail2ban(command: str, jail: str = "", ip: str = "") -> dict:
    """
    adminui-fail2ban.sh ラッパーを実行する。

    Args:
        command: fail2ban サブコマンド
        jail: jail 名（省略可）
        ip: IP アドレス（省略可）

    Returns:
        実行結果 dict

    Raises:
        HTTPException: fail2ban-client が存在しない場合は 503
        SudoWrapperError: ラッパー実行失敗時
    """
    args = [command]
    if jail:
        args.append(jail)
    if ip:
        args.append(ip)
    return sudo_wrapper._execute("adminui-fail2ban.sh", args)


# ===================================================================
# リクエスト/レスポンスモデル
# ===================================================================


class Fail2banStatusResponse(BaseModel):
    """fail2ban サービス状態レスポンス"""

    status: str
    output: Optional[str] = None
    message: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class JailInfo(BaseModel):
    """jail 情報"""

    name: str
    currently_failed: int = 0
    total_failed: int = 0
    currently_banned: int = 0
    total_banned: int = 0
    filter_file: Optional[str] = None
    log_path: Optional[str] = None
    max_retry: Optional[int] = None
    ban_time: Optional[int] = None
    find_time: Optional[int] = None


class JailListResponse(BaseModel):
    """jail 一覧レスポンス"""

    status: str
    jails: List[str] = Field(default_factory=list)
    total: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class JailDetailResponse(BaseModel):
    """jail 詳細レスポンス"""

    status: str
    jail: Optional[JailInfo] = None
    raw_output: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class BannedIPsResponse(BaseModel):
    """禁止 IP 一覧レスポンス"""

    status: str
    jail: str
    banned_ips: List[str] = Field(default_factory=list)
    total: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class UnbanRequest(BaseModel):
    """IP unban リクエスト"""

    ip: str

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        """IP アドレスバリデーション"""
        if not (_IPV4_RE.match(v) or _IPV6_RE.match(v)):
            raise ValueError(f"Invalid IP address: {v!r}")
        return v


class BanRequest(BaseModel):
    """IP ban リクエスト"""

    ip: str

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        """IP アドレスバリデーション"""
        if not (_IPV4_RE.match(v) or _IPV6_RE.match(v)):
            raise ValueError(f"Invalid IP address: {v!r}")
        return v


class BanUnbanResponse(BaseModel):
    """ban/unban 操作結果レスポンス"""

    status: str
    jail: str
    ip: str
    action: str
    output: Optional[str] = None
    message: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class JailSummaryItem(BaseModel):
    """jail サマリーアイテム"""

    name: str
    currently_banned: int = 0
    total_banned: int = 0
    currently_failed: int = 0


class SummaryResponse(BaseModel):
    """全 jail 統計サマリーレスポンス"""

    status: str
    total_banned: int = 0
    total_failed: int = 0
    jail_count: int = 0
    most_active_jail: Optional[str] = None
    jails: List[JailSummaryItem] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class ReloadResponse(BaseModel):
    """設定リロードレスポンス"""

    status: str
    message: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


# ===================================================================
# ヘルパー: fail2ban-client status <jail> 出力のパース
# ===================================================================


def _parse_jail_status(jail_name: str, raw: str) -> JailInfo:
    """
    fail2ban-client status <jail> の出力を JailInfo にパースする。

    Args:
        jail_name: jail 名
        raw: fail2ban-client の出力テキスト

    Returns:
        JailInfo オブジェクト
    """

    def _extract_int(pattern: str, text: str, default: int = 0) -> int:
        m = re.search(pattern, text)
        return int(m.group(1)) if m else default

    def _extract_str(pattern: str, text: str) -> Optional[str]:
        m = re.search(pattern, text)
        return m.group(1).strip() if m else None

    return JailInfo(
        name=jail_name,
        currently_failed=_extract_int(r"Currently failed:\s+(\d+)", raw),
        total_failed=_extract_int(r"Total failed:\s+(\d+)", raw),
        currently_banned=_extract_int(r"Currently banned:\s+(\d+)", raw),
        total_banned=_extract_int(r"Total banned:\s+(\d+)", raw),
        filter_file=_extract_str(r"Filter\s*\n.*?File name:\s*([^\n]+)", raw),
        log_path=_extract_str(r"Log path\s*:\s*([^\n]+)", raw),
        max_retry=_extract_int(r"Max retry:\s+(\d+)", raw) or None,
        ban_time=_extract_int(r"Banned:\s+(\d+)", raw) or None,
        find_time=None,
    )


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/status",
    response_model=Fail2banStatusResponse,
    summary="fail2ban サービス状態取得",
    description="fail2ban-client status を実行してサービス全体の状態を返します",
)
async def get_fail2ban_status(
    current_user: TokenData = Depends(require_permission("read:fail2ban")),
) -> Fail2banStatusResponse:
    """fail2ban サービス全体の状態を取得する。"""
    _check_fail2ban_available()
    try:
        result = _run_fail2ban("status")
        output = result.get("output", "")
        audit_log.record(
            operation="fail2ban_status",
            user_id=current_user.user_id,
            target="fail2ban",
            status="success",
        )
        return Fail2banStatusResponse(status="success", output=output)
    except SudoWrapperError as e:
        logger.error("fail2ban status error: %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


@router.get(
    "/jails",
    response_model=JailListResponse,
    summary="jail 一覧取得",
    description="fail2ban に設定された jail の一覧を返します",
)
async def get_jails(
    current_user: TokenData = Depends(require_permission("read:fail2ban")),
) -> JailListResponse:
    """全 jail 名の一覧を返す。"""
    _check_fail2ban_available()
    try:
        result = _run_fail2ban("jail-list")
        output = result.get("output", "")
        jails = [j.strip() for j in output.splitlines() if j.strip()]
        audit_log.record(
            operation="fail2ban_jail_list",
            user_id=current_user.user_id,
            target="fail2ban",
            status="success",
        )
        return JailListResponse(status="success", jails=jails, total=len(jails))
    except SudoWrapperError as e:
        logger.error("fail2ban jail-list error: %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


@router.get(
    "/jails/{jail_name}",
    response_model=JailDetailResponse,
    summary="jail 詳細取得",
    description="指定した jail の詳細（禁止 IP 数・ログファイル・最大試行数）を返します",
)
async def get_jail_detail(
    jail_name: str,
    current_user: TokenData = Depends(require_permission("read:fail2ban")),
) -> JailDetailResponse:
    """指定 jail の詳細情報を返す。"""
    _validate_jail_name(jail_name)
    _check_fail2ban_available()
    try:
        result = _run_fail2ban("jail-status", jail=jail_name)
        raw = result.get("output", "")
        jail_info = _parse_jail_status(jail_name, raw)
        audit_log.record(
            operation="fail2ban_jail_status",
            user_id=current_user.user_id,
            target=f"fail2ban:{jail_name}",
            status="success",
        )
        return JailDetailResponse(status="success", jail=jail_info, raw_output=raw)
    except SudoWrapperError as e:
        logger.error("fail2ban jail-status error: %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


@router.get(
    "/jails/{jail_name}/banned",
    response_model=BannedIPsResponse,
    summary="禁止 IP 一覧取得",
    description="指定した jail で現在 ban されている IP アドレスの一覧を返します",
)
async def get_banned_ips(
    jail_name: str,
    current_user: TokenData = Depends(require_permission("read:fail2ban")),
) -> BannedIPsResponse:
    """指定 jail の禁止 IP 一覧を返す。"""
    _validate_jail_name(jail_name)
    _check_fail2ban_available()
    try:
        result = _run_fail2ban("banned-ips", jail=jail_name)
        output = result.get("output", "")
        banned_ips = [ip.strip() for ip in output.splitlines() if ip.strip()]
        audit_log.record(
            operation="fail2ban_banned_ips",
            user_id=current_user.user_id,
            target=f"fail2ban:{jail_name}",
            status="success",
        )
        return BannedIPsResponse(
            status="success",
            jail=jail_name,
            banned_ips=banned_ips,
            total=len(banned_ips),
        )
    except SudoWrapperError as e:
        logger.error("fail2ban banned-ips error: %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


@router.post(
    "/jails/{jail_name}/unban",
    response_model=BanUnbanResponse,
    summary="IP unban",
    description="指定した jail から IP を unban します（Operator 以上）",
)
async def unban_ip(
    jail_name: str,
    body: UnbanRequest,
    current_user: TokenData = Depends(require_permission("write:fail2ban")),
) -> BanUnbanResponse:
    """指定 jail から IP を unban する。"""
    _validate_jail_name(jail_name)
    _validate_ip(body.ip)
    _check_fail2ban_available()
    try:
        result = _run_fail2ban("unban", jail=jail_name, ip=body.ip)
        output = result.get("output", "")
        audit_log.record(
            operation="fail2ban_unban",
            user_id=current_user.user_id,
            target=f"fail2ban:{jail_name}",
            status="success",
            details={"ip": body.ip, "jail": jail_name},
        )
        return BanUnbanResponse(
            status="success",
            jail=jail_name,
            ip=body.ip,
            action="unban",
            output=output,
        )
    except SudoWrapperError as e:
        audit_log.record(
            operation="fail2ban_unban",
            user_id=current_user.user_id,
            target=f"fail2ban:{jail_name}",
            status="failure",
            details={"ip": body.ip, "jail": jail_name, "error": str(e)},
        )
        logger.error("fail2ban unban error: %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


@router.post(
    "/jails/{jail_name}/ban",
    response_model=BanUnbanResponse,
    summary="IP ban",
    description="指定した jail に IP を手動 ban します（Approver/Admin のみ）",
)
async def ban_ip(
    jail_name: str,
    body: BanRequest,
    current_user: TokenData = Depends(require_permission("admin:fail2ban")),
) -> BanUnbanResponse:
    """指定 jail に IP を手動 ban する。"""
    _validate_jail_name(jail_name)
    _validate_ip(body.ip)
    _check_fail2ban_available()
    try:
        result = _run_fail2ban("ban", jail=jail_name, ip=body.ip)
        output = result.get("output", "")
        audit_log.record(
            operation="fail2ban_ban",
            user_id=current_user.user_id,
            target=f"fail2ban:{jail_name}",
            status="success",
            details={"ip": body.ip, "jail": jail_name},
        )
        return BanUnbanResponse(
            status="success",
            jail=jail_name,
            ip=body.ip,
            action="ban",
            output=output,
        )
    except SudoWrapperError as e:
        audit_log.record(
            operation="fail2ban_ban",
            user_id=current_user.user_id,
            target=f"fail2ban:{jail_name}",
            status="failure",
            details={"ip": body.ip, "jail": jail_name, "error": str(e)},
        )
        logger.error("fail2ban ban error: %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


@router.get(
    "/summary",
    response_model=SummaryResponse,
    summary="全 jail 統計サマリー",
    description="全 jail の禁止 IP 総数・最もアクティブな jail を返します",
)
async def get_summary(
    current_user: TokenData = Depends(require_permission("read:fail2ban")),
) -> SummaryResponse:
    """全 jail の統計サマリーを返す。"""
    _check_fail2ban_available()
    try:
        # jail 一覧取得
        list_result = _run_fail2ban("jail-list")
        jails_output = list_result.get("output", "")
        jail_names = [j.strip() for j in jails_output.splitlines() if j.strip()]

        # 各 jail の詳細取得
        jail_summaries: List[JailSummaryItem] = []
        total_banned = 0
        total_failed = 0

        for jail_name in jail_names:
            try:
                detail_result = _run_fail2ban("jail-status", jail=jail_name)
                raw = detail_result.get("output", "")
                info = _parse_jail_status(jail_name, raw)
                jail_summaries.append(
                    JailSummaryItem(
                        name=jail_name,
                        currently_banned=info.currently_banned,
                        total_banned=info.total_banned,
                        currently_failed=info.currently_failed,
                    )
                )
                total_banned += info.currently_banned
                total_failed += info.currently_failed
            except (SudoWrapperError, Exception) as e:
                logger.warning("Could not get status for jail %s: %s", jail_name, e)
                jail_summaries.append(JailSummaryItem(name=jail_name))

        # 最もアクティブな jail（currently_banned が最大）
        most_active = None
        if jail_summaries:
            top = max(jail_summaries, key=lambda j: j.currently_banned)
            if top.currently_banned > 0:
                most_active = top.name

        audit_log.record(
            operation="fail2ban_summary",
            user_id=current_user.user_id,
            target="fail2ban",
            status="success",
        )
        return SummaryResponse(
            status="success",
            total_banned=total_banned,
            total_failed=total_failed,
            jail_count=len(jail_names),
            most_active_jail=most_active,
            jails=jail_summaries,
        )
    except SudoWrapperError as e:
        logger.error("fail2ban summary error: %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


@router.post(
    "/reload",
    response_model=ReloadResponse,
    summary="fail2ban 設定リロード",
    description="fail2ban-client reload を実行して設定を再読み込みします（Admin のみ）",
)
async def reload_fail2ban(
    current_user: TokenData = Depends(require_permission("admin:fail2ban")),
) -> ReloadResponse:
    """fail2ban 設定をリロードする。"""
    _check_fail2ban_available()
    try:
        _run_fail2ban("reload")
        audit_log.record(
            operation="fail2ban_reload",
            user_id=current_user.user_id,
            target="fail2ban",
            status="success",
        )
        return ReloadResponse(status="success", message="fail2ban configuration reloaded successfully")
    except SudoWrapperError as e:
        audit_log.record(
            operation="fail2ban_reload",
            user_id=current_user.user_id,
            target="fail2ban",
            status="failure",
            details={"error": str(e)},
        )
        logger.error("fail2ban reload error: %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
