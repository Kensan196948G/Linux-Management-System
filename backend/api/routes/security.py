"""
セキュリティ監査 API エンドポイント

提供エンドポイント:
  GET /api/security/audit-report           - 監査ログ統計
  GET /api/security/failed-logins          - 過去24時間の失敗ログイン時間別集計
  GET /api/security/sudo-logs              - sudo使用ログ (auth.log)
  GET /api/security/open-ports             - 開放ポート一覧 (psutil)
  GET /api/security/bandit-status          - bandit スキャン結果サマリ
  GET /api/security/sudo-history           - sudo操作履歴 (audit_log.jsonl)
  GET /api/security/score                  - セキュリティスコア (0-100)
  GET /api/security/compliance             - CISベンチマーク簡易コンプライアンスチェック
  GET /api/security/vulnerability-summary  - アップグレード可能パッケージの脆弱性サマリー
  GET /api/security/report                 - 総合セキュリティレポート (JSON集約)
  POST /api/security/report/export         - HTMLレポートエクスポート (Jinja2)
"""

import json
import logging
import os
import re
import socket
import stat
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

# data/audit_log.jsonl のパス (プロジェクトルート/data/audit_log.jsonl)
_PROJECT_ROOT = Path(__file__).parents[3]
_AUDIT_JSONL_PATH = _PROJECT_ROOT / "data" / "audit_log.jsonl"

# 既知の危険ポート
_DANGEROUS_PORTS = {21, 23, 25, 110, 143, 512, 513, 514, 3389, 5900}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/security", tags=["security"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class AuditReportResponse(BaseModel):
    """監査ログ統計レスポンス"""

    status: str
    auth_log_lines: int = 0
    accepted_logins: int = 0
    failed_logins: int = 0
    sudo_count: int = 0
    last_login: str = ""
    timestamp: str


class LogEntriesResponse(BaseModel):
    """ログエントリ一覧レスポンス"""

    status: str
    entries: List[str] = Field(default_factory=list)
    timestamp: str


class OpenPortsResponse(BaseModel):
    """開放ポート一覧レスポンス"""

    status: str
    output: str = ""
    timestamp: str


class FailedLoginHourlyItem(BaseModel):
    """時間別失敗ログイン集計アイテム"""

    hour: str
    count: int


class FailedLoginsHourlyResponse(BaseModel):
    """過去24時間の失敗ログイン時間別集計レスポンス"""

    hourly: List[FailedLoginHourlyItem] = Field(default_factory=list)
    total: int = 0
    unique_ips: int = 0


class PortInfo(BaseModel):
    """開放ポート情報"""

    port: int
    proto: str
    state: str
    pid: Optional[int] = None
    name: Optional[str] = None
    dangerous: bool = False


class OpenPortsStructuredResponse(BaseModel):
    """開放ポート一覧レスポンス (psutil ベース)"""

    ports: List[PortInfo] = Field(default_factory=list)


class SudoHistoryItem(BaseModel):
    """sudo 操作履歴アイテム"""

    timestamp: str
    user: str
    operation: str
    result: str


class SudoHistoryResponse(BaseModel):
    """sudo 操作履歴レスポンス"""

    history: List[SudoHistoryItem] = Field(default_factory=list)


class SecurityScoreDetails(BaseModel):
    """セキュリティスコア詳細"""

    failed_login_risk: int
    open_ports_risk: int
    recent_sudo_ops: int


class SecurityScoreResponse(BaseModel):
    """セキュリティスコアレスポンス"""

    score: int
    details: SecurityScoreDetails


class BanditStatusResponse(BaseModel):
    """bandit スキャン結果サマリ"""

    status: str
    high: int = 0
    medium: int = 0
    low: int = 0
    total_issues: int = 0
    scanned: bool = False
    error: Optional[str] = None


# ─── 新規モデル ───────────────────────────────────────────────────────────────


class ComplianceCheckItem(BaseModel):
    """コンプライアンスチェック個別項目"""

    id: str
    category: str
    description: str
    compliant: bool
    value: str = ""
    recommendation: str = ""


class ComplianceResponse(BaseModel):
    """CISベンチマーク簡易コンプライアンスチェックレスポンス"""

    checks: List[ComplianceCheckItem] = Field(default_factory=list)
    compliant_count: int = 0
    non_compliant_count: int = 0
    total_count: int = 0
    compliance_rate: float = 0.0


class VulnerablePackage(BaseModel):
    """アップグレード可能なパッケージ情報"""

    name: str
    current_version: str = ""
    available_version: str = ""
    severity: str = "LOW"  # HIGH / MEDIUM / LOW


class VulnerabilitySummaryResponse(BaseModel):
    """脆弱性サマリーレスポンス"""

    total_upgradable: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    packages: List[VulnerablePackage] = Field(default_factory=list)
    last_updated: str = ""


class SecurityReportResponse(BaseModel):
    """総合セキュリティレポート"""

    generated_at: str
    hostname: str
    score: SecurityScoreResponse
    failed_logins: FailedLoginsHourlyResponse
    open_ports: OpenPortsStructuredResponse
    sudo_history: SudoHistoryResponse
    compliance: ComplianceResponse
    vulnerability_summary: VulnerabilitySummaryResponse


# ===================================================================
# ヘルパー関数
# ===================================================================


def _read_audit_jsonl(path: Path = _AUDIT_JSONL_PATH) -> List[Dict[str, Any]]:
    """audit_log.jsonl を読み込み、パース済みエントリのリストを返す。

    ファイルが存在しない場合は空リストを返す (FileNotFoundError を外に漏らさない)。
    """
    entries: List[Dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    return entries


def _collect_failed_logins_hourly(entries: List[Dict[str, Any]]) -> FailedLoginsHourlyResponse:
    """過去24時間の "login_failed" イベントを1時間単位で集計する。"""
    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(hours=24)

    hourly_counts: Dict[str, int] = defaultdict(int)
    unique_ips: set = set()
    total = 0

    for entry in entries:
        if entry.get("operation") != "login_failed":
            continue
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        if ts < cutoff:
            continue

        # 1時間単位のキー
        hour_key = ts.strftime("%Y-%m-%dT%H:00")
        hourly_counts[hour_key] += 1
        total += 1

        ip = entry.get("details", {}).get("ip") or entry.get("details", {}).get("source_ip") or entry.get("target", "")
        if ip:
            unique_ips.add(ip)

    # 過去24時間分のスロットを全て用意（データがない時間帯も0で埋める）
    hourly: List[FailedLoginHourlyItem] = []
    for h in range(23, -1, -1):
        slot_dt = now - timedelta(hours=h)
        key = slot_dt.strftime("%Y-%m-%dT%H:00")
        hourly.append(FailedLoginHourlyItem(hour=key, count=hourly_counts.get(key, 0)))

    return FailedLoginsHourlyResponse(hourly=hourly, total=total, unique_ips=len(unique_ips))


def _collect_open_ports_psutil() -> List[PortInfo]:
    """psutil でリスニング中の TCP/UDP ポート一覧を返す (sudo 不要)。"""
    ports: List[PortInfo] = []
    seen: set = set()

    try:
        connections = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, PermissionError):
        connections = []

    for conn in connections:
        if conn.status not in ("LISTEN", psutil.CONN_LISTEN):
            continue
        if not conn.laddr:
            continue

        port_no = conn.laddr.port
        proto = "tcp" if conn.type and conn.type.name == "SOCK_STREAM" else "tcp"
        key = (port_no, proto)
        if key in seen:
            continue
        seen.add(key)

        process_name: Optional[str] = None
        pid: Optional[int] = conn.pid
        if pid:
            try:
                process_name = psutil.Process(pid).name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        ports.append(
            PortInfo(
                port=port_no,
                proto=proto,
                state="LISTEN",
                pid=pid,
                name=process_name,
                dangerous=port_no in _DANGEROUS_PORTS,
            )
        )

    return sorted(ports, key=lambda p: p.port)


def _collect_sudo_history(entries: List[Dict[str, Any]], days: int = 7, limit: int = 20) -> List[SudoHistoryItem]:
    """audit_log.jsonl からsudo関連操作を最新 limit 件取得する（直近 days 日間）。"""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    results: List[SudoHistoryItem] = []

    for entry in reversed(entries):
        operation = entry.get("operation", "")
        if not operation:
            continue
        # sudo関連のオペレーションを含むエントリを収集
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        if ts < cutoff:
            continue

        results.append(
            SudoHistoryItem(
                timestamp=entry["timestamp"],
                user=entry.get("user_id", "unknown"),
                operation=operation,
                result=entry.get("status", "unknown"),
            )
        )
        if len(results) >= limit:
            break

    return results


def _calculate_security_score(
    failed_logins_total: int,
    open_ports_count: int,
    dangerous_ports_count: int,
    sudo_ops_count: int,
) -> SecurityScoreResponse:
    """セキュリティスコア (0-100) を計算する。"""
    # 失敗ログインリスク (0=100点、10件以上=0点)
    failed_login_risk = max(0, 100 - failed_logins_total * 5)
    # 開放ポートリスク (危険ポートあり=-20, ポート数が多いほど減点)
    open_ports_risk = max(0, 100 - dangerous_ports_count * 20 - max(0, open_ports_count - 5) * 5)
    # 総合スコア (加重平均)
    score = int(0.5 * failed_login_risk + 0.4 * open_ports_risk + 0.1 * max(0, 100 - sudo_ops_count * 2))
    score = max(0, min(100, score))

    return SecurityScoreResponse(
        score=score,
        details=SecurityScoreDetails(
            failed_login_risk=max(0, min(100, failed_login_risk)),
            open_ports_risk=max(0, min(100, open_ports_risk)),
            recent_sudo_ops=sudo_ops_count,
        ),
    )


# ─── コンプライアンスチェックヘルパー ─────────────────────────────────────────


def _check_ssh_config() -> List[Tuple[str, bool, str, str]]:
    """sshd_config を直接読み取って設定チェックを行う。

    Returns:
        List of (check_id, compliant, value, recommendation) tuples
    """
    sshd_config = Path("/etc/ssh/sshd_config")
    settings: Dict[str, str] = {}
    results: List[Tuple[str, bool, str, str]] = []

    if sshd_config.exists():
        try:
            for line in sshd_config.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(None, 1)
                if len(parts) == 2:
                    settings[parts[0].lower()] = parts[1].strip()
        except OSError:
            pass

    # PasswordAuthentication no が推奨
    pa_val = settings.get("passwordauthentication", "yes")
    results.append((
        "ssh_password_auth",
        pa_val.lower() == "no",
        pa_val,
        "PasswordAuthentication no を設定してパスワード認証を無効にしてください",
    ))

    # PermitRootLogin no が推奨
    prl_val = settings.get("permitrootlogin", "yes")
    results.append((
        "ssh_permit_root",
        prl_val.lower() in ("no", "prohibit-password"),
        prl_val,
        "PermitRootLogin no を設定してrootログインを禁止してください",
    ))

    # PubkeyAuthentication yes が推奨
    pka_val = settings.get("pubkeyauthentication", "yes")
    results.append((
        "ssh_pubkey_auth",
        pka_val.lower() == "yes",
        pka_val,
        "PubkeyAuthentication yes を設定して公開鍵認証を有効にしてください",
    ))

    # Protocol 2 のみ許可
    proto_val = settings.get("protocol", "2")
    results.append((
        "ssh_protocol",
        "1" not in proto_val,
        proto_val,
        "SSH Protocol 1 は無効にしてください（Protocol 2 のみ）",
    ))

    return results


def _check_password_policy() -> List[Tuple[str, bool, str, str]]:
    """login.defs のパスワードポリシーをチェックする。

    Returns:
        List of (check_id, compliant, value, recommendation) tuples
    """
    login_defs = Path("/etc/login.defs")
    settings: Dict[str, str] = {}
    results: List[Tuple[str, bool, str, str]] = []

    if login_defs.exists():
        try:
            for line in login_defs.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(None, 1)
                if len(parts) == 2:
                    settings[parts[0].upper()] = parts[1].strip()
        except OSError:
            pass

    # PASS_MAX_DAYS <= 90 が推奨
    pass_max = settings.get("PASS_MAX_DAYS", "99999")
    try:
        max_days = int(pass_max)
        compliant = max_days <= 90
    except ValueError:
        max_days = -1
        compliant = False
    results.append((
        "passwd_max_days",
        compliant,
        pass_max,
        "PASS_MAX_DAYS を 90 以下に設定してください",
    ))

    # PASS_MIN_LEN >= 8 が推奨
    pass_min = settings.get("PASS_MIN_LEN", "0")
    try:
        min_len = int(pass_min)
        compliant_len = min_len >= 8
    except ValueError:
        compliant_len = False
    results.append((
        "passwd_min_len",
        compliant_len,
        pass_min,
        "PASS_MIN_LEN を 8 以上に設定してください",
    ))

    # PASS_WARN_AGE >= 7 が推奨
    pass_warn = settings.get("PASS_WARN_AGE", "0")
    try:
        warn_age = int(pass_warn)
        compliant_warn = warn_age >= 7
    except ValueError:
        compliant_warn = False
    results.append((
        "passwd_warn_age",
        compliant_warn,
        pass_warn,
        "PASS_WARN_AGE を 7 以上に設定して期限切れ前に警告を表示してください",
    ))

    return results


def _check_firewall_status() -> List[Tuple[str, bool, str, str]]:
    """ファイアウォール状態を確認する（ufw/firewalld/iptables）。

    Returns:
        List of (check_id, compliant, value, recommendation) tuples
    """
    results: List[Tuple[str, bool, str, str]] = []

    # ufw チェック（/etc/ufw/ufw.conf を読む - subprocess不使用）
    ufw_conf = Path("/etc/ufw/ufw.conf")
    ufw_enabled = False
    ufw_val = "inactive"
    if ufw_conf.exists():
        try:
            for line in ufw_conf.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip().upper().startswith("ENABLED="):
                    val = line.split("=", 1)[1].strip().lower()
                    ufw_enabled = val in ("yes", "true", "1")
                    ufw_val = "active" if ufw_enabled else "inactive"
                    break
        except OSError:
            pass

    # firewalld チェック（/etc/firewalld/firewalld.conf を読む）
    firewalld_conf = Path("/etc/firewalld/firewalld.conf")
    firewalld_enabled = firewalld_conf.exists()

    # iptables チェック（/proc/net/ip_tables_names を読む）
    iptables_active = False
    iptables_path = Path("/proc/net/ip_tables_names")
    if iptables_path.exists():
        try:
            content = iptables_path.read_text(encoding="utf-8", errors="replace").strip()
            iptables_active = bool(content)
        except OSError:
            pass

    fw_active = ufw_enabled or firewalld_enabled or iptables_active
    if ufw_enabled:
        fw_val = f"ufw: {ufw_val}"
    elif firewalld_enabled:
        fw_val = "firewalld: active"
    elif iptables_active:
        fw_val = "iptables: active"
    else:
        fw_val = "未検出"

    results.append((
        "firewall_enabled",
        fw_active,
        fw_val,
        "ufw, firewalld, または iptables でファイアウォールを有効にしてください",
    ))

    return results


def _check_sudoers() -> List[Tuple[str, bool, str, str]]:
    """sudoers 設定の危険パターンをチェックする（読み取り専用）。

    Returns:
        List of (check_id, compliant, value, recommendation) tuples
    """
    results: List[Tuple[str, bool, str, str]] = []
    # NOPASSWD ALL の不適切な使用パターン
    dangerous_pattern = re.compile(r"NOPASSWD\s*:\s*ALL", re.IGNORECASE)
    dangerous_found = False
    dangerous_lines: List[str] = []

    sudoers_files = [Path("/etc/sudoers")]
    sudoers_d = Path("/etc/sudoers.d")
    if sudoers_d.is_dir():
        try:
            sudoers_files.extend(p for p in sudoers_d.iterdir() if p.is_file())
        except PermissionError:
            pass

    for sfile in sudoers_files:
        try:
            for line in sfile.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if dangerous_pattern.search(stripped):
                    dangerous_found = True
                    dangerous_lines.append(sfile.name)
        except (PermissionError, OSError):
            continue

    val = f"危険な設定検出: {', '.join(set(dangerous_lines))}" if dangerous_found else "問題なし"
    results.append((
        "sudoers_nopasswd_all",
        not dangerous_found,
        val,
        "NOPASSWD: ALL の使用は避け、特定コマンドのみ許可してください",
    ))

    return results


def _check_suid_sgid_world_writable() -> List[Tuple[str, bool, str, str]]:
    """world-writable な SUID/SGID ファイルを os.stat() で検出する。

    Returns:
        List of (check_id, compliant, value, recommendation) tuples
    """
    results: List[Tuple[str, bool, str, str]] = []
    scan_dirs = [Path("/usr/bin"), Path("/usr/sbin"), Path("/bin"), Path("/sbin")]
    dangerous_files: List[str] = []

    for scan_dir in scan_dirs:
        if not scan_dir.is_dir():
            continue
        try:
            for fpath in scan_dir.iterdir():
                if not fpath.is_file():
                    continue
                try:
                    file_stat = os.stat(fpath)
                    mode = file_stat.st_mode
                    has_suid = bool(mode & stat.S_ISUID)
                    has_world_write = bool(mode & stat.S_IWOTH)
                    if has_suid and has_world_write:
                        dangerous_files.append(str(fpath))
                except OSError:
                    continue
        except PermissionError:
            continue

    val = f"{len(dangerous_files)} 件検出" if dangerous_files else "問題なし"
    results.append((
        "suid_world_writable",
        len(dangerous_files) == 0,
        val,
        "world-writable な SUID ファイルは chmod o-w で書き込み権限を削除してください",
    ))

    return results


def _run_compliance_checks() -> ComplianceResponse:
    """全コンプライアンスチェックを実行して結果をまとめる。"""
    all_checks: List[ComplianceCheckItem] = []

    check_groups = [
        ("SSH設定", _check_ssh_config()),
        ("パスワードポリシー", _check_password_policy()),
        ("ファイアウォール", _check_firewall_status()),
        ("sudoers設定", _check_sudoers()),
        ("SUID/SGIDファイル", _check_suid_sgid_world_writable()),
    ]

    for category, checks in check_groups:
        for check_id, compliant, value, recommendation in checks:
            all_checks.append(
                ComplianceCheckItem(
                    id=check_id,
                    category=category,
                    description=_COMPLIANCE_DESCRIPTIONS.get(check_id, check_id),
                    compliant=compliant,
                    value=value,
                    recommendation=recommendation if not compliant else "",
                )
            )

    compliant_count = sum(1 for c in all_checks if c.compliant)
    total = len(all_checks)
    return ComplianceResponse(
        checks=all_checks,
        compliant_count=compliant_count,
        non_compliant_count=total - compliant_count,
        total_count=total,
        compliance_rate=round(compliant_count / total * 100, 1) if total > 0 else 0.0,
    )


_COMPLIANCE_DESCRIPTIONS: Dict[str, str] = {
    "ssh_password_auth": "SSH パスワード認証が無効化されていること",
    "ssh_permit_root": "SSH root ログインが禁止されていること",
    "ssh_pubkey_auth": "SSH 公開鍵認証が有効であること",
    "ssh_protocol": "SSH Protocol 2 のみ使用していること",
    "passwd_max_days": "パスワード最大有効期限が 90 日以内であること",
    "passwd_min_len": "パスワード最小長が 8 文字以上であること",
    "passwd_warn_age": "パスワード期限切れ警告が 7 日以上前に通知されること",
    "firewall_enabled": "ファイアウォールが有効であること",
    "sudoers_nopasswd_all": "NOPASSWD: ALL の不適切な使用がないこと",
    "suid_world_writable": "world-writable な SUID ファイルがないこと",
}


# ─── 脆弱性サマリーヘルパー ──────────────────────────────────────────────────

# セキュリティ関連キーワード（HIGH判定）
_HIGH_KEYWORDS = {"openssl", "openssh", "linux-image", "kernel", "libc", "glibc", "sudo", "curl", "wget"}
# MEDIUM判定キーワード
_MEDIUM_KEYWORDS = {"python", "perl", "ruby", "nodejs", "npm", "apache", "nginx", "mysql", "postgresql"}


def _estimate_severity(package_name: str) -> str:
    """パッケージ名から重大度を推定する（apt list 情報のみ使用）。"""
    name_lower = package_name.lower()
    for kw in _HIGH_KEYWORDS:
        if kw in name_lower:
            return "HIGH"
    for kw in _MEDIUM_KEYWORDS:
        if kw in name_lower:
            return "MEDIUM"
    return "LOW"


def _collect_vulnerability_summary() -> VulnerabilitySummaryResponse:
    """apt list --upgradable からアップグレード可能なパッケージを取得して重大度推定する。

    subprocess はリスト形式で実行（シェル経由禁止）。apt が存在しない場合は空を返す。
    """
    packages: List[VulnerablePackage] = []

    try:
        proc = subprocess.run(
            ["apt", "list", "--upgradable"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        lines = proc.stdout.splitlines()
        # apt list の出力形式: "package/codename version arch [upgradable from: old]"
        pattern = re.compile(r"^([^/]+)/\S+\s+(\S+)\s+\S+\s+\[upgradable from:\s*([^\]]+)\]")
        for line in lines:
            m = pattern.match(line)
            if not m:
                continue
            name, new_ver, old_ver = m.group(1), m.group(2), m.group(3).strip()
            severity = _estimate_severity(name)
            packages.append(VulnerablePackage(
                name=name,
                current_version=old_ver,
                available_version=new_ver,
                severity=severity,
            ))
    except FileNotFoundError:
        pass  # apt がインストールされていない環境
    except subprocess.TimeoutExpired:
        logger.warning("apt list --upgradable timed out")

    high = sum(1 for p in packages if p.severity == "HIGH")
    medium = sum(1 for p in packages if p.severity == "MEDIUM")
    low = sum(1 for p in packages if p.severity == "LOW")

    return VulnerabilitySummaryResponse(
        total_upgradable=len(packages),
        high=high,
        medium=medium,
        low=low,
        packages=packages[:50],  # 最大50件
        last_updated=datetime.now(tz=timezone.utc).isoformat(),
    )


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/audit-report",
    response_model=AuditReportResponse,
    summary="監査ログ統計",
)
async def get_audit_report(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> AuditReportResponse:
    """監査ログの統計情報（認証成功/失敗件数、sudo使用件数、最終ログイン）を返す"""
    try:
        result = sudo_wrapper.get_security_audit_report()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="security_audit_report_read",
            user_id=current_user.user_id,
            target="auth.log",
            status="success",
            details={},
        )
        return AuditReportResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("Security audit-report error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"監査レポート取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_audit_report: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/failed-logins",
    response_model=FailedLoginsHourlyResponse,
    summary="過去24時間の失敗ログイン時間別集計",
)
async def get_failed_logins(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> FailedLoginsHourlyResponse:
    """data/audit_log.jsonl から過去24時間の "login_failed" イベントを時間別に集計して返す。
    ファイルが存在しない場合は空データを返す。
    """
    try:
        entries = _read_audit_jsonl()
        result = _collect_failed_logins_hourly(entries)
        audit_log.record(
            operation="security_failed_logins_read",
            user_id=current_user.user_id,
            target="audit_log.jsonl",
            status="success",
            details={"total": result.total, "unique_ips": result.unique_ips},
        )
        return result
    except Exception as e:
        logger.error("Unexpected error in get_failed_logins: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/sudo-logs",
    response_model=LogEntriesResponse,
    summary="sudo使用ログ",
)
async def get_sudo_logs(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> LogEntriesResponse:
    """auth.log から sudo 使用ログ（最大50件）を返す"""
    try:
        result = sudo_wrapper.get_sudo_logs()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="security_sudo_logs_read",
            user_id=current_user.user_id,
            target="auth.log",
            status="success",
            details={"count": len(parsed.get("entries", []))},
        )
        return LogEntriesResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("Security sudo-logs error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"sudoログ取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_sudo_logs: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/open-ports",
    response_model=OpenPortsStructuredResponse,
    summary="開放ポート一覧 (psutil)",
)
async def get_open_ports(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> OpenPortsStructuredResponse:
    """psutil を使用してリスニング中のポートを取得する (sudo 不要)。
    危険ポート (telnet/ftp 等) は dangerous=True でフラグを立てる。
    """
    try:
        ports = _collect_open_ports_psutil()
        audit_log.record(
            operation="security_open_ports_read",
            user_id=current_user.user_id,
            target="open_ports",
            status="success",
            details={"count": len(ports)},
        )
        return OpenPortsStructuredResponse(ports=ports)
    except Exception as e:
        logger.error("Unexpected error in get_open_ports: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/sudo-history",
    response_model=SudoHistoryResponse,
    summary="sudo 操作履歴 (audit_log.jsonl)",
)
async def get_sudo_history(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> SudoHistoryResponse:
    """data/audit_log.jsonl から過去7日間のsudo操作履歴（最新20件）を返す。
    ファイルが存在しない場合は空データを返す。
    """
    try:
        entries = _read_audit_jsonl()
        history = _collect_sudo_history(entries)
        audit_log.record(
            operation="security_sudo_history_read",
            user_id=current_user.user_id,
            target="audit_log.jsonl",
            status="success",
            details={"count": len(history)},
        )
        return SudoHistoryResponse(history=history)
    except Exception as e:
        logger.error("Unexpected error in get_sudo_history: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/score",
    response_model=SecurityScoreResponse,
    summary="セキュリティスコア (0-100)",
)
async def get_security_score(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> SecurityScoreResponse:
    """失敗ログイン数・開放ポート数・sudo操作数からセキュリティスコア(0-100)を算出して返す。"""
    try:
        entries = _read_audit_jsonl()
        failed_resp = _collect_failed_logins_hourly(entries)
        ports = _collect_open_ports_psutil()
        sudo_history = _collect_sudo_history(entries)

        dangerous_count = sum(1 for p in ports if p.dangerous)
        result = _calculate_security_score(
            failed_logins_total=failed_resp.total,
            open_ports_count=len(ports),
            dangerous_ports_count=dangerous_count,
            sudo_ops_count=len(sudo_history),
        )
        audit_log.record(
            operation="security_score_read",
            user_id=current_user.user_id,
            target="security_score",
            status="success",
            details={"score": result.score},
        )
        return result
    except Exception as e:
        logger.error("Unexpected error in get_security_score: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/bandit-status",
    response_model=BanditStatusResponse,
    summary="bandit スキャン結果サマリ",
)
async def get_bandit_status(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> BanditStatusResponse:
    """bandit -r backend/ -ll -f json を実行し High/Medium 件数を返す（sudo なし）"""
    try:
        # シェル経由禁止 — 配列渡しで実行
        proc = subprocess.run(
            ["bandit", "-r", "backend/", "-ll", "-f", "json"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        # bandit は問題あり=1, なし=0, エラー=2 を返す
        raw = proc.stdout or proc.stderr or "{}"
        data = json.loads(raw)

        results = data.get("results", [])
        high = sum(1 for r in results if r.get("issue_severity") == "HIGH")
        medium = sum(1 for r in results if r.get("issue_severity") == "MEDIUM")
        low = sum(1 for r in results if r.get("issue_severity") == "LOW")

        audit_log.record(
            operation="security_bandit_scan",
            user_id=current_user.user_id,
            target="backend/",
            status="success",
            details={"high": high, "medium": medium, "low": low},
        )
        return BanditStatusResponse(
            status="success",
            high=high,
            medium=medium,
            low=low,
            total_issues=len(results),
            scanned=True,
        )
    except subprocess.TimeoutExpired:
        logger.error("bandit scan timed out")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="bandit スキャンがタイムアウトしました",
        )
    except FileNotFoundError:
        # bandit がインストールされていない場合
        return BanditStatusResponse(
            status="unavailable",
            scanned=False,
            error="bandit がインストールされていません",
        )
    except json.JSONDecodeError as e:
        logger.error("bandit JSON parse error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"bandit 出力解析エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_bandit_status: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/compliance",
    response_model=ComplianceResponse,
    summary="CISベンチマーク簡易コンプライアンスチェック",
)
async def get_compliance(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> ComplianceResponse:
    """SSH設定・パスワードポリシー・ファイアウォール・sudoers・SUID/SGIDのチェックを実行する。
    全てのチェックはファイル読み取りのみ実施（subprocess シェル起動禁止）。
    """
    try:
        result = _run_compliance_checks()
        audit_log.record(
            operation="security_compliance_check",
            user_id=current_user.user_id,
            target="system_config",
            status="success",
            details={
                "compliant": result.compliant_count,
                "non_compliant": result.non_compliant_count,
                "rate": result.compliance_rate,
            },
        )
        return result
    except Exception as e:
        logger.error("Unexpected error in get_compliance: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/vulnerability-summary",
    response_model=VulnerabilitySummaryResponse,
    summary="アップグレード可能パッケージの脆弱性サマリー",
)
async def get_vulnerability_summary(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> VulnerabilitySummaryResponse:
    """apt list --upgradable からアップグレード可能パッケージを収集し、
    パッケージ名からHIGH/MEDIUM/LOWの重大度を推定して返す。
    apt が存在しない環境では空データを返す。
    """
    try:
        result = _collect_vulnerability_summary()
        audit_log.record(
            operation="security_vulnerability_summary_read",
            user_id=current_user.user_id,
            target="apt_upgradable",
            status="success",
            details={"total": result.total_upgradable, "high": result.high},
        )
        return result
    except Exception as e:
        logger.error("Unexpected error in get_vulnerability_summary: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/report",
    response_model=SecurityReportResponse,
    summary="総合セキュリティレポート (JSON集約)",
)
async def get_security_report(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> SecurityReportResponse:
    """全セキュリティデータを集約した総合レポートをJSONで返す。
    score / failed_logins / open_ports / sudo_history / compliance / vulnerability_summary を含む。
    """
    try:
        entries = _read_audit_jsonl()
        failed_resp = _collect_failed_logins_hourly(entries)
        ports = _collect_open_ports_psutil()
        sudo_hist = _collect_sudo_history(entries)
        dangerous_count = sum(1 for p in ports if p.dangerous)
        score_resp = _calculate_security_score(
            failed_logins_total=failed_resp.total,
            open_ports_count=len(ports),
            dangerous_ports_count=dangerous_count,
            sudo_ops_count=len(sudo_hist),
        )
        compliance_resp = _run_compliance_checks()
        vuln_resp = _collect_vulnerability_summary()

        try:
            hostname = socket.gethostname()
        except OSError:
            hostname = "unknown"

        result = SecurityReportResponse(
            generated_at=datetime.now(tz=timezone.utc).isoformat(),
            hostname=hostname,
            score=score_resp,
            failed_logins=failed_resp,
            open_ports=OpenPortsStructuredResponse(ports=ports),
            sudo_history=SudoHistoryResponse(history=sudo_hist),
            compliance=compliance_resp,
            vulnerability_summary=vuln_resp,
        )
        audit_log.record(
            operation="security_report_generated",
            user_id=current_user.user_id,
            target="security_report",
            status="success",
            details={"score": score_resp.score},
        )
        return result
    except Exception as e:
        logger.error("Unexpected error in get_security_report: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.post(
    "/report/export",
    summary="セキュリティレポートHTMLエクスポート",
    response_class=Response,
)
async def export_security_report(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> Response:
    """総合セキュリティレポートをJinja2テンプレートでHTMLに変換して返す。
    Content-Disposition: attachment でダウンロード形式で提供する。
    """
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        entries = _read_audit_jsonl()
        failed_resp = _collect_failed_logins_hourly(entries)
        ports = _collect_open_ports_psutil()
        sudo_hist = _collect_sudo_history(entries)
        dangerous_count = sum(1 for p in ports if p.dangerous)
        score_resp = _calculate_security_score(
            failed_logins_total=failed_resp.total,
            open_ports_count=len(ports),
            dangerous_ports_count=dangerous_count,
            sudo_ops_count=len(sudo_hist),
        )
        compliance_resp = _run_compliance_checks()
        vuln_resp = _collect_vulnerability_summary()

        try:
            hostname = socket.gethostname()
        except OSError:
            hostname = "unknown"

        templates_dir = Path(__file__).parents[3] / "backend" / "templates"
        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html"]),
        )
        template = env.get_template("security_report.html")
        html_content = template.render(
            generated_at=datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            hostname=hostname,
            score=score_resp.score,
            score_color="#22c55e" if score_resp.score >= 80 else "#f59e0b" if score_resp.score >= 60 else "#ef4444",
            score_details=score_resp.details,
            failed_logins_total=failed_resp.total,
            failed_logins_unique_ips=failed_resp.unique_ips,
            open_ports=ports,
            sudo_history=sudo_hist,
            compliance=compliance_resp,
            vuln=vuln_resp,
        )

        filename = f"security-report-{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}.html"
        audit_log.record(
            operation="security_report_exported",
            user_id=current_user.user_id,
            target="security_report_html",
            status="success",
            details={"filename": filename},
        )
        return Response(
            content=html_content,
            media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error("Unexpected error in export_security_report: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"HTMLエクスポートエラー: {e}",
        )
