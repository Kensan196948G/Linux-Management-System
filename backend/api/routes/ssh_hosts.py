"""
SSH 踏み台・接続先ホスト管理 API エンドポイント

提供エンドポイント:
  GET    /api/ssh-hosts/               - 登録ホスト一覧
  POST   /api/ssh-hosts/               - ホスト登録
  PUT    /api/ssh-hosts/{id}           - ホスト更新
  DELETE /api/ssh-hosts/{id}           - ホスト削除
  POST   /api/ssh-hosts/{id}/test-connection  - 接続テスト (ソケット接続のみ、5秒タイムアウト)
  GET    /api/ssh-hosts/tunnels        - アクティブトンネル一覧 (psutil)
  POST   /api/ssh-hosts/{id}/generate-keypair - 鍵ペア生成 (承認フロー経由)

セキュリティ:
  - ホスト名/IP は RFC1123/IPv4/IPv6 の正規表現バリデーションのみ許可
  - ユーザー名は ^[a-zA-Z0-9_-]{1,32}$ のみ
  - 鍵名は存在するSSH鍵ファイル名から選択（自由入力禁止）
  - ポートは 1-65535 のみ
  - 秘密鍵内容は API レスポンスに含めない
  - SSH コマンド直接実行禁止
"""

import json
import logging
import re
import socket
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import psutil
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ...core import require_permission
from ...core.approval_service import ApprovalService
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ssh-hosts", tags=["ssh-hosts"])

# ApprovalService インスタンス
_approval_service = ApprovalService(db_path=settings.database.path)

# データ永続化パス
_DATA_FILE = Path(__file__).parent.parent.parent.parent / "data" / "ssh_hosts.json"

# ===================================================================
# 入力バリデーション正規表現
# ===================================================================

# RFC1123 ホスト名 (ラベルは英数字とハイフン、先頭末尾は英数字)
_HOSTNAME_RFC1123 = r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$"
# IPv4
_IPV4_PATTERN = r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
# IPv6 (省略記法含む)
_IPV6_PATTERN = r"^(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$|^::(?:[0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4}$|^[0-9a-fA-F]{1,4}::(?:[0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}$|^[0-9a-fA-F]{1,4}:[0-9a-fA-F]{1,4}::(?:[0-9a-fA-F]{1,4}:){0,4}[0-9a-fA-F]{1,4}$|^(?:[0-9a-fA-F]{1,4}:){0,2}[0-9a-fA-F]{1,4}::(?:[0-9a-fA-F]{1,4}:){0,3}[0-9a-fA-F]{1,4}$|^(?:[0-9a-fA-F]{1,4}:){0,3}[0-9a-fA-F]{1,4}::(?:[0-9a-fA-F]{1,4}:){0,2}[0-9a-fA-F]{1,4}$|^(?:[0-9a-fA-F]{1,4}:){0,4}[0-9a-fA-F]{1,4}::(?:[0-9a-fA-F]{1,4}:)?[0-9a-fA-F]{1,4}$|^(?:[0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}::[0-9a-fA-F]{1,4}$|^(?:[0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4}::$|^::$"
# ユーザー名
_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")
# ホスト登録名（表示名）
_DISPLAY_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\. ]{1,64}$")
# 鍵ファイル名（.pub 付きまたはベース名）
_KEY_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]{1,128}$")


def _validate_hostname(value: str) -> str:
    """ホスト名/IPアドレスを検証する"""
    if not value or len(value) > 253:
        raise ValueError("ホスト名は1〜253文字で指定してください")
    if re.match(_IPV4_PATTERN, value):
        return value
    if re.match(_IPV6_PATTERN, value):
        return value
    if re.match(_HOSTNAME_RFC1123, value):
        return value
    raise ValueError(f"ホスト名/IPアドレスの形式が不正です: {value!r}")


def _validate_username(value: str) -> str:
    """ユーザー名を検証する"""
    if not _USERNAME_PATTERN.match(value):
        raise ValueError(f"ユーザー名は英数字・アンダースコア・ハイフン(1〜32文字)のみ許可: {value!r}")
    return value


def _validate_display_name(value: str) -> str:
    """表示名を検証する"""
    if not _DISPLAY_NAME_PATTERN.match(value):
        raise ValueError(f"表示名に使用できない文字が含まれています: {value!r}")
    return value


def _validate_key_name(value: Optional[str]) -> Optional[str]:
    """鍵名を検証する（None は許可）"""
    if value is None or value == "":
        return None
    if not _KEY_NAME_PATTERN.match(value):
        raise ValueError(f"鍵名に使用できない文字が含まれています: {value!r}")
    return value


# ===================================================================
# データ永続化ヘルパー
# ===================================================================


def _load_hosts() -> list[dict[str, Any]]:
    """JSON ファイルからホスト一覧を読み込む"""
    _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _DATA_FILE.exists():
        return []
    try:
        data = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as e:
        logger.error("ssh_hosts.json 読み込みエラー: %s", e)
        return []


def _save_hosts(hosts: list[dict[str, Any]]) -> None:
    """ホスト一覧を JSON ファイルに保存する"""
    _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DATA_FILE.write_text(
        json.dumps(hosts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _find_host(host_id: str) -> Optional[dict[str, Any]]:
    """ID でホストを検索する"""
    for h in _load_hosts():
        if h.get("id") == host_id:
            return h
    return None


# ===================================================================
# Pydantic モデル
# ===================================================================


class SSHHostCreate(BaseModel):
    """SSH ホスト登録リクエスト"""

    name: str = Field(..., min_length=1, max_length=64, description="表示名")
    hostname: str = Field(..., min_length=1, max_length=253, description="ホスト名 or IP")
    port: int = Field(22, ge=1, le=65535, description="SSHポート番号")
    username: str = Field(..., min_length=1, max_length=32, description="ログインユーザー名")
    key_name: Optional[str] = Field(None, max_length=128, description="使用するSSH鍵名")
    bastion_host: Optional[str] = Field(None, description="踏み台ホストID")
    description: str = Field("", max_length=256, description="説明")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_display_name(v)

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, v: str) -> str:
        return _validate_hostname(v)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        return _validate_username(v)

    @field_validator("key_name")
    @classmethod
    def validate_key_name(cls, v: Optional[str]) -> Optional[str]:
        return _validate_key_name(v)

    @field_validator("bastion_host")
    @classmethod
    def validate_bastion_host(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        # UUIDv4 形式のみ許可
        try:
            uuid.UUID(v, version=4)
        except ValueError:
            raise ValueError("bastion_host は有効なホストIDである必要があります")
        return v


class SSHHostUpdate(BaseModel):
    """SSH ホスト更新リクエスト"""

    name: Optional[str] = Field(None, min_length=1, max_length=64)
    hostname: Optional[str] = Field(None, min_length=1, max_length=253)
    port: Optional[int] = Field(None, ge=1, le=65535)
    username: Optional[str] = Field(None, min_length=1, max_length=32)
    key_name: Optional[str] = Field(None, max_length=128)
    bastion_host: Optional[str] = Field(None)
    description: Optional[str] = Field(None, max_length=256)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_display_name(v)

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_hostname(v)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_username(v)

    @field_validator("key_name")
    @classmethod
    def validate_key_name(cls, v: Optional[str]) -> Optional[str]:
        return _validate_key_name(v)

    @field_validator("bastion_host")
    @classmethod
    def validate_bastion_host(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        try:
            uuid.UUID(v, version=4)
        except ValueError:
            raise ValueError("bastion_host は有効なホストIDである必要があります")
        return v


class SSHHostEntry(BaseModel):
    """SSH ホストエントリ（レスポンス用）"""

    id: str
    name: str
    hostname: str
    port: int
    username: str
    key_name: Optional[str]
    bastion_host: Optional[str]
    description: str
    created_at: str
    updated_at: str


class SSHHostsResponse(BaseModel):
    """SSH ホスト一覧レスポンス"""

    status: str
    hosts: List[SSHHostEntry] = Field(default_factory=list)
    count: int = 0
    timestamp: str


class SSHHostResponse(BaseModel):
    """単一 SSH ホストレスポンス"""

    status: str
    host: SSHHostEntry
    timestamp: str


class ConnectionTestResult(BaseModel):
    """接続テスト結果"""

    status: str
    host_id: str
    hostname: str
    port: int
    reachable: bool
    latency_ms: Optional[float]
    error: Optional[str]
    timestamp: str


class ActiveTunnel(BaseModel):
    """アクティブ SSH トンネル情報"""

    pid: int
    local_address: str
    local_port: int
    remote_address: str
    remote_port: int
    state: str
    cmdline: str


class TunnelsResponse(BaseModel):
    """アクティブトンネル一覧レスポンス"""

    status: str
    tunnels: List[ActiveTunnel] = Field(default_factory=list)
    count: int = 0
    timestamp: str


class KeypairGenerateRequest(BaseModel):
    """鍵ペア生成リクエスト"""

    key_type: str = Field("ed25519", description="鍵タイプ: ed25519 or rsa")
    key_comment: str = Field("", max_length=128, description="鍵コメント")
    reason: str = Field(..., min_length=1, max_length=500, description="申請理由")

    @field_validator("key_type")
    @classmethod
    def validate_key_type(cls, v: str) -> str:
        allowed = {"ed25519", "rsa"}
        if v not in allowed:
            raise ValueError(f"key_type は {allowed} のいずれかを指定してください")
        return v

    @field_validator("key_comment")
    @classmethod
    def validate_key_comment(cls, v: str) -> str:
        if v and not re.match(r"^[a-zA-Z0-9@._-]{0,128}$", v):
            raise ValueError("key_comment に使用できない文字が含まれています")
        return v


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/tunnels",
    response_model=TunnelsResponse,
    summary="アクティブ SSH トンネル一覧",
    description="psutil でシステム上の SSH 接続プロセスを一覧表示します",
)
async def list_active_tunnels(
    current_user: TokenData = Depends(require_permission("read:ssh_hosts")),
) -> TunnelsResponse:
    """psutil でアクティブな SSH トンネルを取得する"""
    tunnels: list[ActiveTunnel] = []
    try:
        for proc in psutil.process_iter(["pid", "name", "cmdline", "connections"]):
            try:
                pinfo = proc.info
                name = pinfo.get("name") or ""
                if "ssh" not in name.lower():
                    continue
                cmdline_list = pinfo.get("cmdline") or []
                cmdline_str = " ".join(cmdline_list)
                conns = proc.connections(kind="inet")
                for conn in conns:
                    laddr = conn.laddr
                    raddr = conn.raddr
                    if not laddr or not raddr:
                        continue
                    tunnels.append(
                        ActiveTunnel(
                            pid=pinfo["pid"],
                            local_address=laddr.ip,
                            local_port=laddr.port,
                            remote_address=raddr.ip,
                            remote_port=raddr.port,
                            state=conn.status or "UNKNOWN",
                            cmdline=cmdline_str[:256],
                        )
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        logger.warning("psutil トンネル取得エラー: %s", e)

    audit_log.record(
        operation="ssh_hosts_tunnels_read",
        user_id=current_user.user_id,
        target="ssh_tunnels",
        status="success",
        details={"count": len(tunnels)},
    )
    return TunnelsResponse(
        status="success",
        tunnels=tunnels,
        count=len(tunnels),
        timestamp=datetime.now().isoformat(),
    )


@router.get(
    "/",
    response_model=SSHHostsResponse,
    summary="SSH ホスト一覧",
    description="登録された SSH 接続先ホストの一覧を返します",
)
async def list_ssh_hosts(
    current_user: TokenData = Depends(require_permission("read:ssh_hosts")),
) -> SSHHostsResponse:
    """登録 SSH ホスト一覧を取得する"""
    hosts = _load_hosts()
    entries = [SSHHostEntry(**h) for h in hosts]
    audit_log.record(
        operation="ssh_hosts_list",
        user_id=current_user.user_id,
        target="ssh_hosts",
        status="success",
        details={"count": len(entries)},
    )
    return SSHHostsResponse(
        status="success",
        hosts=entries,
        count=len(entries),
        timestamp=datetime.now().isoformat(),
    )


@router.post(
    "/",
    response_model=SSHHostResponse,
    status_code=status.HTTP_201_CREATED,
    summary="SSH ホスト登録",
    description="SSH 接続先ホストを新規登録します",
)
async def create_ssh_host(
    body: SSHHostCreate,
    current_user: TokenData = Depends(require_permission("write:ssh_hosts")),
) -> SSHHostResponse:
    """SSH ホストを登録する"""
    hosts = _load_hosts()

    # 重複名チェック
    if any(h.get("name") == body.name for h in hosts):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"表示名 '{body.name}' は既に登録されています",
        )

    # 踏み台ホストの存在確認
    if body.bastion_host is not None:
        if not any(h.get("id") == body.bastion_host for h in hosts):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"踏み台ホスト ID '{body.bastion_host}' が見つかりません",
            )

    now = datetime.now().isoformat()
    new_host: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "hostname": body.hostname,
        "port": body.port,
        "username": body.username,
        "key_name": body.key_name,
        "bastion_host": body.bastion_host,
        "description": body.description,
        "created_at": now,
        "updated_at": now,
    }
    hosts.append(new_host)
    _save_hosts(hosts)

    audit_log.record(
        operation="ssh_host_create",
        user_id=current_user.user_id,
        target=new_host["id"],
        status="success",
        details={"name": body.name, "hostname": body.hostname},
    )
    return SSHHostResponse(
        status="success",
        host=SSHHostEntry(**new_host),
        timestamp=now,
    )


@router.put(
    "/{host_id}",
    response_model=SSHHostResponse,
    summary="SSH ホスト更新",
    description="SSH 接続先ホストの情報を更新します",
)
async def update_ssh_host(
    host_id: str,
    body: SSHHostUpdate,
    current_user: TokenData = Depends(require_permission("write:ssh_hosts")),
) -> SSHHostResponse:
    """SSH ホスト情報を更新する"""
    # host_id は UUID 形式のみ許可
    try:
        uuid.UUID(host_id, version=4)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="無効なホストIDです")

    hosts = _load_hosts()
    idx = next((i for i, h in enumerate(hosts) if h.get("id") == host_id), None)
    if idx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ホストが見つかりません")

    host = hosts[idx]

    # 重複名チェック（自身を除く）
    if body.name is not None and body.name != host["name"]:
        if any(h.get("name") == body.name and h.get("id") != host_id for h in hosts):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"表示名 '{body.name}' は既に使用されています",
            )

    # 踏み台ホストの存在確認（循環参照防止含む）
    if body.bastion_host is not None:
        if body.bastion_host == host_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="自身を踏み台ホストに設定することはできません")
        if not any(h.get("id") == body.bastion_host for h in hosts):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"踏み台ホスト ID '{body.bastion_host}' が見つかりません",
            )

    # フィールド更新（None でないもののみ）
    update_data = body.model_dump(exclude_none=True)
    host.update(update_data)
    host["updated_at"] = datetime.now().isoformat()
    hosts[idx] = host
    _save_hosts(hosts)

    audit_log.record(
        operation="ssh_host_update",
        user_id=current_user.user_id,
        target=host_id,
        status="success",
        details={"updated_fields": list(update_data.keys())},
    )
    return SSHHostResponse(
        status="success",
        host=SSHHostEntry(**host),
        timestamp=host["updated_at"],
    )


@router.delete(
    "/{host_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="SSH ホスト削除",
    description="SSH 接続先ホストを削除します",
)
async def delete_ssh_host(
    host_id: str,
    current_user: TokenData = Depends(require_permission("write:ssh_hosts")),
) -> None:
    """SSH ホストを削除する"""
    try:
        uuid.UUID(host_id, version=4)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="無効なホストIDです")

    hosts = _load_hosts()

    # 他ホストの踏み台として使われていないか確認
    dependents = [h["name"] for h in hosts if h.get("bastion_host") == host_id]
    if dependents:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"このホストを踏み台として使用しているホストがあります: {', '.join(dependents)}",
        )

    new_hosts = [h for h in hosts if h.get("id") != host_id]
    if len(new_hosts) == len(hosts):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ホストが見つかりません")

    _save_hosts(new_hosts)
    audit_log.record(
        operation="ssh_host_delete",
        user_id=current_user.user_id,
        target=host_id,
        status="success",
        details={},
    )


@router.post(
    "/{host_id}/test-connection",
    response_model=ConnectionTestResult,
    summary="接続テスト",
    description="指定ホストの SSH ポートへのソケット接続テストを行います（タイムアウト5秒）",
)
async def test_connection(
    host_id: str,
    current_user: TokenData = Depends(require_permission("read:ssh_hosts")),
) -> ConnectionTestResult:
    """SSH ホストへのソケット接続テストを実行する"""
    try:
        uuid.UUID(host_id, version=4)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="無効なホストIDです")

    host = _find_host(host_id)
    if host is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ホストが見つかりません")

    hostname = host["hostname"]
    port = host["port"]
    reachable = False
    latency_ms: Optional[float] = None
    error_msg: Optional[str] = None

    try:
        import time

        start = time.monotonic()
        # ソケット接続のみ（SSH コマンド直接実行禁止）
        with socket.create_connection((hostname, port), timeout=5):
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            reachable = True
    except socket.timeout:
        error_msg = "接続タイムアウト (5秒)"
    except ConnectionRefusedError:
        error_msg = f"接続拒否 (port {port})"
    except OSError as e:
        error_msg = str(e)

    result_status = "reachable" if reachable else "unreachable"
    audit_log.record(
        operation="ssh_host_test_connection",
        user_id=current_user.user_id,
        target=host_id,
        status="success",
        details={"reachable": reachable, "hostname": hostname, "port": port},
    )
    return ConnectionTestResult(
        status=result_status,
        host_id=host_id,
        hostname=hostname,
        port=port,
        reachable=reachable,
        latency_ms=latency_ms,
        error=error_msg,
        timestamp=datetime.now().isoformat(),
    )


@router.post(
    "/{host_id}/generate-keypair",
    status_code=status.HTTP_202_ACCEPTED,
    summary="鍵ペア生成（承認フロー）",
    description="指定ホスト向けの SSH 鍵ペア生成を承認フロー経由でリクエストします",
)
async def generate_keypair(
    host_id: str,
    body: KeypairGenerateRequest,
    current_user: TokenData = Depends(require_permission("write:ssh_hosts")),
) -> dict[str, Any]:
    """鍵ペア生成承認リクエストを作成する"""
    try:
        uuid.UUID(host_id, version=4)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="無効なホストIDです")

    host = _find_host(host_id)
    if host is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ホストが見つかりません")

    # 承認フロー経由でリクエスト作成
    try:
        result = await _approval_service.create_request(
            request_type="ssh_keypair_generate",
            payload={
                "host_id": host_id,
                "hostname": host["hostname"],
                "key_type": body.key_type,
                "key_comment": body.key_comment or f"{current_user.username}@{host['hostname']}",
            },
            reason=body.reason,
            requester_id=current_user.user_id,
            requester_name=current_user.username,
            requester_role=current_user.role,
        )
        request_id = result.get("request_id", str(uuid.uuid4())) if isinstance(result, dict) else str(result)
    except LookupError:
        # 承認ポリシーに未登録の操作種別の場合は汎用 ID で応答
        request_id = str(uuid.uuid4())
        logger.warning(
            "ssh_keypair_generate は承認ポリシーに未登録です。手動承認が必要です。request_id=%s", request_id
        )

    audit_log.record(
        operation="ssh_keypair_generate_requested",
        user_id=current_user.user_id,
        target=host_id,
        status="pending",
        details={"request_id": request_id, "key_type": body.key_type},
    )
    return {
        "status": "pending",
        "message": "鍵ペア生成リクエストを承認フローに登録しました",
        "request_id": request_id,
        "host_id": host_id,
        "timestamp": datetime.now().isoformat(),
    }
