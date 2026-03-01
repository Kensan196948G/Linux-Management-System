"""
モジュール管理 API エンドポイント

提供エンドポイント:
  GET /api/modules              - 全モジュール一覧（カテゴリ別、認証不要）
  GET /api/modules/status       - 各モジュールのヘルス状態（認証必要）
  GET /api/modules/{module_name} - 特定モジュールの詳細（認証不要）
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ...core import require_permission
from ...core.auth import TokenData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/modules", tags=["modules"])

# ===================================================================
# モジュール定義（Webmin互換カテゴリ構成）
# ===================================================================

MODULES: Dict[str, Any] = {
    "system": {
        "label": "System",
        "modules": [
            {"id": "processes", "name": "Running Processes", "endpoint": "/api/processes/list", "icon": "activity"},
            {"id": "users", "name": "Users and Groups", "endpoint": "/api/users/list", "icon": "people"},
            {"id": "cron", "name": "Scheduled Cron Jobs", "endpoint": "/api/cron/list", "icon": "clock"},
            {"id": "logs", "name": "System Logs", "endpoint": "/api/logs/recent", "icon": "file-text"},
            {"id": "filesystem", "name": "Filesystem Usage", "endpoint": "/api/filesystem/usage", "icon": "hdd"},
            {"id": "bootup", "name": "Bootup and Shutdown", "endpoint": "/api/bootup/status", "icon": "power"},
            {"id": "system_time", "name": "System Time", "endpoint": "/api/time/status", "icon": "clock"},
            {"id": "quotas", "name": "Disk Quotas", "endpoint": "/api/quotas/status", "icon": "database"},
            {"id": "ssh", "name": "SSH Server", "endpoint": "/api/ssh/status", "icon": "terminal"},
            {"id": "sshkeys", "name": "SSH Keys", "endpoint": "/api/ssh/keys", "icon": "key"},
            {"id": "sysconfig", "name": "System Configuration", "endpoint": "/api/sysconfig/hostname", "icon": "settings"},
            {"id": "filemanager", "name": "File Manager", "endpoint": "/api/files/allowed-dirs", "icon": "folder"},
        ],
    },
    "servers": {
        "label": "Servers",
        "modules": [
            {"id": "apache", "name": "Apache Webserver", "endpoint": "/api/apache/status", "icon": "globe"},
            {"id": "nginx", "name": "Nginx Webserver", "endpoint": "/api/nginx/status", "icon": "globe"},
            {"id": "mysql", "name": "MySQL/MariaDB", "endpoint": "/api/mysql/status", "icon": "database"},
            {"id": "postgresql", "name": "PostgreSQL", "endpoint": "/api/postgresql/status", "icon": "database"},
            {"id": "postfix", "name": "Postfix Mail Server", "endpoint": "/api/postfix/status", "icon": "mail"},
            {"id": "bind", "name": "BIND DNS Server", "endpoint": "/api/bind/status", "icon": "globe"},
            {"id": "dhcp", "name": "DHCP Server", "endpoint": "/api/dhcp/status", "icon": "server"},
            {"id": "ftp", "name": "FTP Server (ProFTPD)", "endpoint": "/api/ftp/status", "icon": "upload"},
            {"id": "squid", "name": "Squid Proxy", "endpoint": "/api/squid/status", "icon": "shuffle"},
        ],
    },
    "networking": {
        "label": "Networking",
        "modules": [
            {"id": "network", "name": "Network Configuration", "endpoint": "/api/network/interfaces", "icon": "wifi"},
            {"id": "firewall", "name": "Firewall (iptables/ufw)", "endpoint": "/api/firewall/status", "icon": "shield"},
            {"id": "bandwidth", "name": "Network Bandwidth", "endpoint": "/api/bandwidth/current", "icon": "activity"},
            {"id": "netstat", "name": "Network Statistics", "endpoint": "/api/netstat/connections", "icon": "bar-chart"},
            {"id": "routing", "name": "Routing & Gateways", "endpoint": "/api/routing/routes", "icon": "git-branch"},
        ],
    },
    "hardware": {
        "label": "Hardware",
        "modules": [
            {"id": "hardware", "name": "Hardware Info", "endpoint": "/api/hardware/cpu", "icon": "cpu"},
            {"id": "smart", "name": "SMART Drive Status", "endpoint": "/api/smart/disks", "icon": "hdd"},
            {"id": "partitions", "name": "Disk Partitions", "endpoint": "/api/partitions/list", "icon": "layers"},
            {"id": "sensors", "name": "Temperature & Sensors", "endpoint": "/api/sensors/all", "icon": "thermometer"},
        ],
    },
    "system_management": {
        "label": "Linux Management System",
        "modules": [
            {"id": "services", "name": "Service Control", "endpoint": "/api/services/status", "icon": "play"},
            {"id": "servers", "name": "Server Overview", "endpoint": "/api/servers/overview", "icon": "monitor"},
            {"id": "packages", "name": "Package Updates", "endpoint": "/api/packages/updates", "icon": "package"},
            {"id": "approval", "name": "Approval Workflow", "endpoint": "/api/approval/pending", "icon": "check-square"},
        ],
    },
}

# フラットなモジュール検索用インデックス
_MODULE_INDEX: Dict[str, Dict[str, Any]] = {}
for _cat_key, _cat_val in MODULES.items():
    for _mod in _cat_val["modules"]:
        _MODULE_INDEX[_mod["id"]] = {**_mod, "category": _cat_key, "category_label": _cat_val["label"]}


# ===================================================================
# レスポンスモデル
# ===================================================================


class ModuleEntry(BaseModel):
    """モジュールエントリ"""

    id: str
    name: str
    endpoint: str
    icon: str


class CategoryEntry(BaseModel):
    """カテゴリエントリ"""

    label: str
    modules: List[ModuleEntry]


class ModulesListResponse(BaseModel):
    """全モジュール一覧レスポンス"""

    categories: Dict[str, CategoryEntry]
    total_modules: int


class ModuleStatusEntry(BaseModel):
    """モジュールステータスエントリ"""

    id: str
    available: bool


class ModulesStatusResponse(BaseModel):
    """モジュールステータス一覧レスポンス"""

    statuses: List[ModuleStatusEntry]
    total: int


class ModuleDetailResponse(BaseModel):
    """モジュール詳細レスポンス"""

    id: str
    name: str
    endpoint: str
    icon: str
    category: str
    category_label: str


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "",
    response_model=ModulesListResponse,
    summary="全モジュール一覧（カテゴリ別）",
    description="実装済みモジュールをカテゴリ別に返します（認証不要）",
)
async def list_modules() -> ModulesListResponse:
    """全モジュール一覧をカテゴリ別に返す（認証不要）"""
    total = sum(len(cat["modules"]) for cat in MODULES.values())
    return ModulesListResponse(
        categories={k: CategoryEntry(**v) for k, v in MODULES.items()},
        total_modules=total,
    )


@router.get(
    "/status",
    response_model=ModulesStatusResponse,
    summary="各モジュールのヘルス状態",
    description="各モジュールのエンドポイントに対するヘルス状態を返します（認証必要）",
)
async def get_modules_status(
    current_user: TokenData = Depends(require_permission("read:modules")),
) -> ModulesStatusResponse:
    """各モジュールのステータスを返す（エンドポイントの存在確認のみ、外部通信なし）"""
    statuses: List[ModuleStatusEntry] = []
    for module_id, module_info in _MODULE_INDEX.items():
        # エンドポイントが定義されていれば available=True とみなす（外部通信なし）
        available = bool(module_info.get("endpoint"))
        statuses.append(ModuleStatusEntry(id=module_id, available=available))

    statuses.sort(key=lambda x: x.id)
    return ModulesStatusResponse(statuses=statuses, total=len(statuses))


@router.get(
    "/{module_name}",
    response_model=ModuleDetailResponse,
    summary="特定モジュールの詳細",
    description="指定したモジュールIDの詳細情報を返します（認証不要）",
)
async def get_module_detail(module_name: str) -> ModuleDetailResponse:
    """特定モジュールの詳細を返す（認証不要）"""
    module = _MODULE_INDEX.get(module_name)
    if module is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"モジュール '{module_name}' が見つかりません",
        )
    return ModuleDetailResponse(**module)
