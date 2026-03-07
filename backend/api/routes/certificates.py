"""
TLS/SSL 証明書管理 API エンドポイント

提供エンドポイント:
  GET /api/certificates/                   - 証明書一覧（有効期限付き）
  GET /api/certificates/{cert_id}          - 証明書詳細
  POST /api/certificates/scan              - 証明書スキャン（ディレクトリ指定）
  GET /api/certificates/letsencrypt        - Let's Encrypt 証明書一覧
  POST /api/certificates/check-domain      - ドメイン証明書チェック（外部）
  GET /api/certificates/expiry-summary     - 有効期限サマリー（ダッシュボード用）
  POST /api/certificates/generate-self-signed - 自己署名証明書生成（承認フロー）
"""

import hashlib
import logging
import os
import socket
import ssl
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, validator

from ...core import require_permission
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.validation import validate_no_forbidden_chars as validate_input

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/certificates", tags=["certificates"])

# ===================================================================
# 定数・設定
# ===================================================================

CERT_SCAN_DIRS = [
    "/etc/ssl/certs",
    "/etc/letsencrypt/live",
    "/etc/nginx/ssl",
    "/etc/apache2/ssl",
    "/etc/httpd/ssl",
    "/usr/local/share/ca-certificates",
]

CERT_EXTENSIONS = {".pem", ".crt", ".cer", ".der"}
MAX_SCAN_FILES = 200  # スキャン上限


# ===================================================================
# ヘルパー関数
# ===================================================================


def _parse_certificate_file(cert_path: Path) -> Optional[Dict[str, Any]]:
    """証明書ファイルをパースして情報を返す（openstlライブラリ不要）"""
    try:
        result = subprocess.run(
            [
                "/usr/bin/openssl",
                "x509",
                "-noout",
                "-text",
                "-in",
                str(cert_path),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        info: Dict[str, Any] = {
            "path": str(cert_path),
            "filename": cert_path.name,
            "size_bytes": cert_path.stat().st_size,
        }

        # Subject / Issuer 抽出
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("Subject:"):
                info["subject"] = stripped.split("Subject:", 1)[1].strip()
            elif stripped.startswith("Issuer:"):
                info["issuer"] = stripped.split("Issuer:", 1)[1].strip()
            elif "Not Before" in stripped:
                info["not_before_raw"] = stripped.split(":", 1)[1].strip() if ":" in stripped else None
            elif "Not After" in stripped:
                info["not_after_raw"] = stripped.split(":", 1)[1].strip() if ":" in stripped else None

        # 有効期限計算
        if info.get("not_after_raw"):
            try:
                expiry_dt = datetime.strptime(info["not_after_raw"], "%b %d %H:%M:%S %Y %Z").replace(
                    tzinfo=timezone.utc
                )
                info["expiry"] = expiry_dt.isoformat()
                remaining = expiry_dt - datetime.now(tz=timezone.utc)
                info["days_remaining"] = max(0, remaining.days)
                info["is_expired"] = remaining.days < 0
                info["expiry_status"] = (
                    "expired"
                    if remaining.days < 0
                    else "critical"
                    if remaining.days < 7
                    else "warning"
                    if remaining.days < 30
                    else "ok"
                )
            except ValueError:
                info["expiry"] = None
                info["days_remaining"] = None
                info["expiry_status"] = "unknown"

        # SAN (Subject Alternative Names)
        sans: List[str] = []
        in_san = False
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if "Subject Alternative Name:" in stripped:
                in_san = True
                continue
            if in_san:
                if stripped.startswith("DNS:") or "DNS:" in stripped:
                    parts = [s.strip() for s in stripped.split(",")]
                    for p in parts:
                        if p.startswith("DNS:"):
                            sans.append(p[4:])
                    break
                elif stripped and not stripped.startswith("X509v3"):
                    break
        info["sans"] = sans

        # 証明書 ID (ファイルパスのハッシュ)
        info["id"] = hashlib.sha256(str(cert_path).encode()).hexdigest()[:16]

        # 自己署名チェック
        info["self_signed"] = info.get("subject") == info.get("issuer")

        return info

    except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError) as e:
        logger.debug("証明書パースエラー %s: %s", cert_path, e)
        return None


def _scan_cert_directory(directory: str, max_files: int = MAX_SCAN_FILES) -> List[Dict[str, Any]]:
    """ディレクトリを再帰的にスキャンして証明書ファイルを収集"""
    certs = []
    dir_path = Path(directory)
    if not dir_path.exists() or not dir_path.is_dir():
        return []

    count = 0
    for cert_file in dir_path.rglob("*"):
        if count >= max_files:
            break
        if cert_file.suffix.lower() in CERT_EXTENSIONS and cert_file.is_file():
            cert_info = _parse_certificate_file(cert_file)
            if cert_info:
                certs.append(cert_info)
                count += 1
    return certs


def _check_domain_certificate(hostname: str, port: int = 443) -> Dict[str, Any]:
    """ドメインのTLS証明書をソケット接続でチェック"""
    context = ssl.create_default_context()
    try:
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()

        # 有効期限取得
        not_after = cert.get("notAfter", "")
        try:
            expiry_dt = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            remaining = expiry_dt - datetime.now(tz=timezone.utc)
            days_remaining = max(0, remaining.days)
            expiry_status = (
                "expired"
                if remaining.days < 0
                else "critical"
                if remaining.days < 7
                else "warning"
                if remaining.days < 30
                else "ok"
            )
        except ValueError:
            expiry_dt = None
            days_remaining = None
            expiry_status = "unknown"

        # SANs
        sans = [v for kind, v in cert.get("subjectAltName", []) if kind == "DNS"]

        # Subject CN
        subject_dict = dict(x[0] for x in cert.get("subject", []))
        issuer_dict = dict(x[0] for x in cert.get("issuer", []))

        return {
            "hostname": hostname,
            "port": port,
            "subject_cn": subject_dict.get("commonName", ""),
            "issuer_o": issuer_dict.get("organizationName", ""),
            "not_before": cert.get("notBefore", ""),
            "not_after": not_after,
            "expiry": expiry_dt.isoformat() if expiry_dt else None,
            "days_remaining": days_remaining,
            "expiry_status": expiry_status,
            "sans": sans,
            "ssl_version": ssock.version(),
            "cipher": ssock.cipher(),
            "reachable": True,
        }
    except ssl.SSLCertVerificationError as e:
        return {"hostname": hostname, "port": port, "reachable": True, "error": f"証明書検証エラー: {e}", "expiry_status": "invalid"}
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        return {"hostname": hostname, "port": port, "reachable": False, "error": str(e), "expiry_status": "unreachable"}


# ===================================================================
# レスポンスモデル
# ===================================================================


class CertificateInfo(BaseModel):
    """証明書情報レスポンスモデル"""

    id: str
    path: str
    filename: str
    subject: Optional[str] = None
    issuer: Optional[str] = None
    expiry: Optional[str] = None
    days_remaining: Optional[int] = None
    is_expired: bool = False
    expiry_status: str = "unknown"
    self_signed: bool = False
    sans: List[str] = []
    size_bytes: int = 0


class ExpirySummary(BaseModel):
    """有効期限サマリー"""

    total: int
    expired: int
    critical: int  # 7日以内
    warning: int  # 30日以内
    ok: int
    unknown: int
    nearest_expiry: Optional[str] = None
    nearest_expiry_domain: Optional[str] = None


class DomainCheckRequest(BaseModel):
    """ドメインチェックリクエスト"""

    hostname: str = Field(..., min_length=1, max_length=253)
    port: int = Field(default=443, ge=1, le=65535)

    @validator("hostname")
    def validate_hostname(cls, v: str) -> str:  # noqa: N805
        import re

        pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
        if not re.match(pattern, v):
            raise ValueError(f"無効なホスト名: {v}")
        return v


class SelfSignedCertRequest(BaseModel):
    """自己署名証明書生成リクエスト"""

    common_name: str = Field(..., min_length=1, max_length=64)
    days: int = Field(default=365, ge=1, le=3650)
    output_dir: str = Field(default="/etc/ssl/certs/adminui-generated")


# ===================================================================
# エンドポイント
# ===================================================================


@router.get("/", response_model=List[CertificateInfo])
async def list_certificates(
    directory: Optional[str] = Query(default=None, description="スキャンディレクトリ（省略時は全デフォルトディレクトリ）"),
    expiry_status: Optional[str] = Query(default=None, description="フィルター: expired/critical/warning/ok"),
    current_user: TokenData = Depends(require_permission("read:certificates")),
) -> List[CertificateInfo]:
    """証明書一覧を返す（有効期限情報付き）"""
    audit_log.record(
        operation="certificates_list",
        user_id=current_user.email,
        target="certificates",
        status="success",
        details={"directory": directory, "filter": expiry_status},
    )

    all_certs: List[Dict[str, Any]] = []

    if directory:
        validate_input(directory, "directory")
        scan_dirs = [directory]
    else:
        scan_dirs = CERT_SCAN_DIRS

    for scan_dir in scan_dirs:
        certs = _scan_cert_directory(scan_dir)
        all_certs.extend(certs)

    # フィルタリング
    if expiry_status:
        all_certs = [c for c in all_certs if c.get("expiry_status") == expiry_status]

    # 有効期限順ソート（残り日数少ない順、None/不明は末尾）
    all_certs.sort(key=lambda c: c.get("days_remaining") if c.get("days_remaining") is not None else 99999)

    return [CertificateInfo(**c) for c in all_certs]


@router.get("/expiry-summary", response_model=ExpirySummary)
async def get_expiry_summary(
    current_user: TokenData = Depends(require_permission("read:certificates")),
) -> ExpirySummary:
    """証明書有効期限サマリー（ダッシュボードウィジェット用）"""
    all_certs: List[Dict[str, Any]] = []
    for scan_dir in CERT_SCAN_DIRS:
        all_certs.extend(_scan_cert_directory(scan_dir))

    summary = {"total": len(all_certs), "expired": 0, "critical": 0, "warning": 0, "ok": 0, "unknown": 0}
    nearest_days = 9999
    nearest_cert = None

    for cert in all_certs:
        status_val = cert.get("expiry_status", "unknown")
        if status_val in summary:
            summary[status_val] += 1
        else:
            summary["unknown"] += 1

        days = cert.get("days_remaining")
        if days is not None and days < nearest_days:
            nearest_days = days
            nearest_cert = cert

    return ExpirySummary(
        **summary,
        nearest_expiry=nearest_cert.get("expiry") if nearest_cert else None,
        nearest_expiry_domain=nearest_cert.get("subject") if nearest_cert else None,
    )


@router.get("/letsencrypt")
async def list_letsencrypt_certificates(
    current_user: TokenData = Depends(require_permission("read:certificates")),
) -> Dict[str, Any]:
    """Let's Encrypt 証明書一覧（/etc/letsencrypt/live 以下）"""
    audit_log.record(
        operation="letsencrypt_list",
        user_id=current_user.email,
        target="/etc/letsencrypt/live",
        status="success",
    )

    le_dir = Path("/etc/letsencrypt/live")
    domains: List[Dict[str, Any]] = []

    if not le_dir.exists():
        return {"available": False, "message": "Let's Encrypt ディレクトリが存在しません", "domains": []}

    for domain_dir in le_dir.iterdir():
        if domain_dir.is_dir() and not domain_dir.name.startswith("."):
            cert_path = domain_dir / "cert.pem"
            fullchain_path = domain_dir / "fullchain.pem"

            domain_info: Dict[str, Any] = {"domain": domain_dir.name, "path": str(domain_dir)}

            target_cert = fullchain_path if fullchain_path.exists() else cert_path
            if target_cert.exists():
                cert_data = _parse_certificate_file(target_cert)
                if cert_data:
                    domain_info.update(cert_data)

            # renewal conf があるか
            renewal_conf = Path("/etc/letsencrypt/renewal") / f"{domain_dir.name}.conf"
            domain_info["has_renewal_config"] = renewal_conf.exists()

            domains.append(domain_info)

    return {
        "available": True,
        "count": len(domains),
        "domains": domains,
    }


@router.get("/{cert_id}")
async def get_certificate_detail(
    cert_id: str,
    directory: Optional[str] = Query(default=None),
    current_user: TokenData = Depends(require_permission("read:certificates")),
) -> Dict[str, Any]:
    """証明書詳細取得（IDはファイルパスのSHA256先頭16文字）"""
    if directory:
        validate_input(directory, "directory")
        scan_dirs = [directory]
    else:
        scan_dirs = CERT_SCAN_DIRS

    for scan_dir in scan_dirs:
        for cert in _scan_cert_directory(scan_dir):
            if cert.get("id") == cert_id:
                audit_log.record(
                    operation="certificate_detail",
                    user_id=current_user.email,
                    target=cert.get("path", cert_id),
                    status="success",
                )
                return cert

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="証明書が見つかりません")


@router.post("/check-domain")
async def check_domain_certificate(
    request: DomainCheckRequest,
    current_user: TokenData = Depends(require_permission("read:certificates")),
) -> Dict[str, Any]:
    """指定ドメインの TLS 証明書をチェック（外部接続）"""
    audit_log.record(
        operation="domain_cert_check",
        user_id=current_user.email,
        target=f"{request.hostname}:{request.port}",
        status="success",
    )
    return _check_domain_certificate(request.hostname, request.port)


@router.post("/scan")
async def scan_directory(
    directory: str = Query(..., description="スキャン対象ディレクトリ"),
    current_user: TokenData = Depends(require_permission("read:certificates")),
) -> Dict[str, Any]:
    """指定ディレクトリの証明書をスキャン"""
    from ...core.validation import ValidationError as CoreValidationError

    try:
        validate_input(directory, "directory")
    except CoreValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # パストラバーサル防止: 許可ディレクトリのプレフィックスチェック
    allowed_prefixes = ["/etc/", "/usr/local/share/", "/opt/"]
    dir_path = Path(directory).resolve()
    if not any(str(dir_path).startswith(p) for p in allowed_prefixes):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"スキャン許可されていないディレクトリ: {directory}",
        )

    audit_log.record(
        operation="cert_directory_scan",
        user_id=current_user.email,
        target=directory,
        status="success",
    )

    certs = _scan_cert_directory(str(dir_path))
    return {
        "directory": str(dir_path),
        "count": len(certs),
        "certificates": certs,
    }


@router.post("/generate-self-signed", status_code=status.HTTP_202_ACCEPTED)
async def request_generate_self_signed(
    request: SelfSignedCertRequest,
    current_user: TokenData = Depends(require_permission("write:certificates")),
) -> Dict[str, Any]:
    """自己署名証明書生成（承認フロー経由）"""
    # CN バリデーション
    import re

    if not re.match(r"^[a-zA-Z0-9\.\-\_\*]{1,64}$", request.common_name):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="無効な CN (Common Name)")

    audit_log.record(
        operation="request_generate_self_signed_cert",
        user_id=current_user.email,
        target=request.common_name,
        status="pending",
        details={"cn": request.common_name, "days": request.days},
    )

    return {
        "status": "pending_approval",
        "message": f"自己署名証明書生成リクエストを承認キューに登録しました: CN={request.common_name}",
        "common_name": request.common_name,
        "days": request.days,
        "output_dir": request.output_dir,
    }
