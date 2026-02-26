"""
ファイアウォール管理 API エンドポイント

提供エンドポイント:
  GET    /api/firewall/rules        - ファイアウォールルール一覧
  GET    /api/firewall/policy       - デフォルトポリシー
  GET    /api/firewall/status       - ファイアウォール全体状態
  POST   /api/firewall/rules        - UFWルール追加（承認フロー）
  DELETE /api/firewall/rules/{num}  - UFWルール削除（承認フロー）
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...core import require_permission, sudo_wrapper
from ...core.approval_service import ApprovalService
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.config import settings
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

approval_service = ApprovalService(db_path=settings.database.path)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/firewall", tags=["firewall"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class FirewallRulesResponse(BaseModel):
    """ファイアウォールルール一覧レスポンス"""

    status: str
    backend: Optional[str] = None
    tables: Optional[dict] = None
    raw: Optional[str] = None
    raw_lines: Optional[list] = None
    ruleset: Optional[Any] = None
    message: Optional[str] = None
    timestamp: str


class FirewallPolicyResponse(BaseModel):
    """ファイアウォールポリシーレスポンス"""

    status: str
    backend: Optional[str] = None
    chains: list[Any] = Field(default_factory=list)
    message: Optional[str] = None
    timestamp: str


class FirewallStatusResponse(BaseModel):
    """ファイアウォール状態レスポンス"""

    status: str
    ufw_active: bool = False
    firewalld_active: bool = False
    iptables_available: bool = False
    nftables_available: bool = False
    available_backends: list[str] = Field(default_factory=list)
    timestamp: str


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/rules",
    response_model=FirewallRulesResponse,
    summary="ファイアウォールルール一覧",
    description="iptables-save / nft list ruleset でルール一覧を取得します（読み取り専用）",
)
async def get_firewall_rules(
    current_user: TokenData = Depends(require_permission("read:firewall")),
) -> FirewallRulesResponse:

    try:
        result = sudo_wrapper.get_firewall_rules()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="firewall_rules_read",
            user_id=current_user.user_id,
            target="firewall",
            status="success",
            details={},
        )
        return FirewallRulesResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("Firewall rules fetch error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ファイアウォールルール取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_firewall_rules: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/policy",
    response_model=FirewallPolicyResponse,
    summary="ファイアウォールポリシー取得",
    description="デフォルトポリシー（ACCEPT/DROP）をチェーンごとに取得します",
)
async def get_firewall_policy(
    current_user: TokenData = Depends(require_permission("read:firewall")),
) -> FirewallPolicyResponse:
    """デフォルトポリシーを取得する"""
    try:
        result = sudo_wrapper.get_firewall_policy()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="firewall_policy_read",
            user_id=current_user.user_id,
            target="firewall",
            status="success",
            details={},
        )
        return FirewallPolicyResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("Firewall policy fetch error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ファイアウォールポリシー取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_firewall_policy: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/status",
    response_model=FirewallStatusResponse,
    summary="ファイアウォール全体状態",
    description="UFW / firewalld / iptables / nftables の状態を確認します",
)
async def get_firewall_status(
    current_user: TokenData = Depends(require_permission("read:firewall")),
) -> FirewallStatusResponse:
    """ファイアウォール全体の状態を取得する"""
    try:
        result = sudo_wrapper.get_firewall_status()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="firewall_status_read",
            user_id=current_user.user_id,
            target="firewall",
            status="success",
            details={},
        )
        return FirewallStatusResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("Firewall status fetch error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ファイアウォール状態取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_firewall_status: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


# ===================================================================
# 書き込みモデル
# ===================================================================


class FirewallRuleCreate(BaseModel):
    """UFWルール追加リクエスト"""
    port: int = Field(..., ge=1, le=65535)
    protocol: str = Field("tcp", pattern="^(tcp|udp|any)$")
    action: str = Field(..., pattern="^(allow|deny)$")
    reason: str = Field("Firewall rule change", min_length=1, max_length=1000)


class FirewallRuleDelete(BaseModel):
    """UFWルール削除リクエスト"""
    rule_num: int = Field(..., ge=1, le=999)


# ===================================================================
# 書き込みエンドポイント（承認フロー経由）
# ===================================================================


@router.post(
    "/rules",
    status_code=status.HTTP_202_ACCEPTED,
    summary="UFWルール追加（承認フロー）",
)
async def create_firewall_rule(
    rule: FirewallRuleCreate,
    current_user: TokenData = Depends(require_permission("write:firewall")),
):
    """UFWルール追加（承認フロー経由）"""
    try:
        request_result = await approval_service.create_request(
            request_type="firewall_modify",
            payload={
                "action": rule.action,
                "port": rule.port,
                "protocol": rule.protocol,
            },
            reason=rule.reason,
            requester_id=current_user.user_id,
            requester_name=current_user.username,
            requester_role=current_user.role,
        )
        audit_log.record(
            operation="firewall_rule_create_requested",
            user_id=current_user.user_id,
            target=f"port:{rule.port}/{rule.protocol}",
            status="pending_approval",
            details={"action": rule.action, "port": rule.port, "protocol": rule.protocol},
        )
        return {
            "status": "pending_approval",
            "message": "Firewall rule creation requires approval",
            "request_id": request_result.get("request_id"),
        }
    except (ValueError, LookupError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Firewall rule create error: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete(
    "/rules/{rule_num}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="UFWルール削除（承認フロー）",
)
async def delete_firewall_rule(
    rule_num: int,
    current_user: TokenData = Depends(require_permission("write:firewall")),
):
    """UFWルール削除（承認フロー経由）"""
    if rule_num < 1 or rule_num > 999:
        raise HTTPException(status_code=422, detail="Invalid rule number")
    try:
        request_result = await approval_service.create_request(
            request_type="firewall_modify",
            payload={"action": "delete", "rule_num": rule_num},
            reason=f"Delete firewall rule {rule_num}",
            requester_id=current_user.user_id,
            requester_name=current_user.username,
            requester_role=current_user.role,
        )
        audit_log.record(
            operation="firewall_rule_delete_requested",
            user_id=current_user.user_id,
            target=f"rule:{rule_num}",
            status="pending_approval",
            details={"rule_num": rule_num},
        )
        return {
            "status": "pending_approval",
            "message": "Firewall rule deletion requires approval",
            "request_id": request_result.get("request_id"),
        }
    except (ValueError, LookupError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Firewall rule delete error: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
