"""
ログ閲覧 API エンドポイント（高度検索・統計・タイムライン・保存フィルター含む）
"""

import json
import logging
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path as FPath, Query, status
from pydantic import BaseModel, field_validator

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/logs", tags=["logs"])

# ===================================================================
# 高度検索 定数
# ===================================================================

# 許可ログファイル allowlist（絶対パスのみ）
ADVANCED_ALLOWED_LOG_FILES: List[str] = [
    "/var/log/syslog",
    "/var/log/auth.log",
    "/var/log/kern.log",
    "/var/log/dpkg.log",
    "/var/log/nginx/access.log",
    "/var/log/nginx/error.log",
    "/var/log/apache2/access.log",
    "/var/log/apache2/error.log",
    "/var/log/postgresql/postgresql.log",
    "/var/log/mysql/error.log",
]

MAX_RESULT_LINES = 1000
MAX_REGEX_LENGTH = 200
FORBIDDEN_CHARS_ADV = [";", "|", "&", "$", "`", ">", "<"]

SAVED_FILTERS_PATH = Path(__file__).parent.parent.parent.parent / "data" / "saved_log_filters.json"

# ログレベル検出パターン
_LEVEL_PATTERNS = {
    "ERROR": re.compile(r"\b(error|err|critical|crit|emerg|alert|fatal)\b", re.IGNORECASE),
    "WARN": re.compile(r"\b(warn|warning)\b", re.IGNORECASE),
    "INFO": re.compile(r"\b(info|notice)\b", re.IGNORECASE),
    "DEBUG": re.compile(r"\b(debug)\b", re.IGNORECASE),
}


# ===================================================================
# 高度検索 モデル
# ===================================================================


class AdvancedSearchRequest(BaseModel):
    """横断フルテキスト検索リクエスト"""

    query: str
    files: List[str] = ["/var/log/syslog"]
    regex: bool = False
    limit: int = 100
    from_time: Optional[str] = None
    to_time: Optional[str] = None

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """クエリの基本バリデーション"""
        if len(v) > MAX_REGEX_LENGTH:
            raise ValueError(f"Query too long (max {MAX_REGEX_LENGTH} chars)")
        return v

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        """結果件数の上限チェック"""
        if v < 1 or v > MAX_RESULT_LINES:
            raise ValueError(f"limit must be 1-{MAX_RESULT_LINES}")
        return v


class SavedFilterCreateRequest(BaseModel):
    """保存フィルター作成リクエスト"""

    name: str
    query: str
    files: List[str] = ["/var/log/syslog"]
    regex: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Filter name must not be empty")
        if len(v) > 100:
            raise ValueError("Filter name too long (max 100 chars)")
        return v.strip()


# ===================================================================
# ヘルパー関数
# ===================================================================


def _validate_adv_query(value: str, allow_regex: bool = False) -> None:
    """高度検索クエリの禁止文字チェック（非regexのみ）。

    Args:
        value: 検証する文字列
        allow_regex: 正規表現モード時は一部チェックをスキップ

    Raises:
        HTTPException: 禁止文字が含まれる場合
    """
    if not allow_regex:
        for char in FORBIDDEN_CHARS_ADV:
            if char in value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Forbidden character '{char}' in query",
                )


def _compile_pattern(query: str, is_regex: bool) -> re.Pattern:
    """検索パターンをコンパイルする。

    Args:
        query: 検索文字列
        is_regex: 正規表現として扱うか

    Returns:
        コンパイル済みパターン

    Raises:
        HTTPException: 正規表現エラー時
    """
    try:
        if is_regex:
            return re.compile(query, re.IGNORECASE)
        else:
            return re.compile(re.escape(query), re.IGNORECASE)
    except re.error as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid regex pattern: {e}",
        )


def _detect_level(line: str) -> str:
    """ログ行からログレベルを検出する。

    Args:
        line: ログ行テキスト

    Returns:
        ログレベル文字列 (ERROR/WARN/INFO/DEBUG/UNKNOWN)
    """
    for level, pat in _LEVEL_PATTERNS.items():
        if pat.search(line):
            return level
    return "UNKNOWN"


def _load_saved_filters() -> dict:
    """saved_log_filters.json を読み込む。

    Returns:
        フィルターデータ辞書
    """
    if not SAVED_FILTERS_PATH.exists():
        return {"filters": []}
    try:
        with open(SAVED_FILTERS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"filters": []}


def _save_saved_filters(data: dict) -> None:
    """saved_log_filters.json に書き込む。

    Args:
        data: 書き込むフィルターデータ

    Raises:
        HTTPException: 書き込みエラー時
    """
    try:
        SAVED_FILTERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SAVED_FILTERS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist filter: {e}",
        )


# ===================================================================
# レスポンスモデル
# ===================================================================


class LogsResponse(BaseModel):
    """ログレスポンス"""

    status: str
    service: str
    lines_requested: int
    lines_returned: int
    logs: list[str]
    timestamp: str


# ===================================================================
# エンドポイント
# ===================================================================


# ===================================================================
# ログ検索エンドポイント (Step 25)
# ===================================================================

FORBIDDEN_CHARS_LOG = [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?"]


def _validate_query(value: str) -> None:
    """検索クエリの禁止文字チェック。

    Args:
        value: 検証する文字列

    Raises:
        HTTPException: 禁止文字が含まれる場合
    """
    for char in FORBIDDEN_CHARS_LOG:
        if char in value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Forbidden character in query: {char}",
            )


@router.get("/search")
async def search_logs(
    q: str = Query(..., min_length=1, max_length=100, description="検索キーワード"),
    file: str = Query(default="syslog", description="検索対象ログファイル"),
    lines: int = Query(default=50, ge=1, le=200),
    current_user: TokenData = Depends(require_permission("read:logs")),
) -> Dict[str, Any]:
    """ログファイルを全文検索

    Args:
        q: 検索キーワード（1-100文字）
        file: 検索対象ログファイル名
        lines: 返却最大行数（1-200）
        current_user: 現在のユーザー（read:logs 権限必須）

    Returns:
        検索結果の辞書

    Raises:
        HTTPException: 禁止文字または検索失敗時
    """
    _validate_query(q)
    _validate_query(file)

    logger.info(f"Log search requested: q={q!r}, file={file}, lines={lines}, user={current_user.username}")

    audit_log.record(
        operation="log_search",
        user_id=current_user.user_id,
        target=file,
        status="attempt",
        details={"query": q, "lines": lines},
    )

    try:
        result = sudo_wrapper.search_logs(q, file, lines)

        if result.get("status") == "error":
            audit_log.record(
                operation="log_search",
                user_id=current_user.user_id,
                target=file,
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Log search denied"),
            )

        audit_log.record(
            operation="log_search",
            user_id=current_user.user_id,
            target=file,
            status="success",
            details={"lines_returned": result.get("lines_returned", 0)},
        )

        return result

    except SudoWrapperError as e:
        if "Forbidden character" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        audit_log.record(
            operation="log_search",
            user_id=current_user.user_id,
            target=file,
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Log search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Log search failed: {str(e)}",
        )


@router.get("/files")
async def list_log_files(
    current_user: TokenData = Depends(require_permission("read:logs")),
) -> Dict[str, Any]:
    """利用可能なログファイル一覧

    Args:
        current_user: 現在のユーザー（read:logs 権限必須）

    Returns:
        ログファイル一覧の辞書

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Log files list requested: user={current_user.username}")

    audit_log.record(
        operation="log_files_list",
        user_id=current_user.user_id,
        target="log_files",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.list_log_files()

        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("message", "Failed to list log files"),
            )

        audit_log.record(
            operation="log_files_list",
            user_id=current_user.user_id,
            target="log_files",
            status="success",
            details={"file_count": result.get("file_count", 0)},
        )

        return result

    except SudoWrapperError as e:
        logger.error(f"Log files list failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Log files list failed: {str(e)}",
        )


@router.get("/recent-errors")
async def get_recent_errors(
    current_user: TokenData = Depends(require_permission("read:logs")),
) -> Dict[str, Any]:
    """直近のエラーログ集約

    Args:
        current_user: 現在のユーザー（read:logs 権限必須）

    Returns:
        直近エラーログの辞書

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Recent errors requested: user={current_user.username}")

    audit_log.record(
        operation="log_recent_errors",
        user_id=current_user.user_id,
        target="recent_errors",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_recent_errors()

        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("message", "Failed to get recent errors"),
            )

        audit_log.record(
            operation="log_recent_errors",
            user_id=current_user.user_id,
            target="recent_errors",
            status="success",
            details={"error_count": result.get("error_count", 0)},
        )

        return result

    except SudoWrapperError as e:
        logger.error(f"Recent errors fetch failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Recent errors fetch failed: {str(e)}",
        )


# ===================================================================
# 高度検索エンドポイント
# ===================================================================


@router.post("/search")
async def advanced_search_logs(
    request: AdvancedSearchRequest,
    current_user: TokenData = Depends(require_permission("read:logs")),
) -> Dict[str, Any]:
    """複数ログファイルを横断してフルテキスト検索する。

    Args:
        request: 検索リクエスト（クエリ、対象ファイル一覧、regex フラグ等）
        current_user: 現在のユーザー（read:logs 権限必須）

    Returns:
        マッチした行のリスト（ファイル名・行番号・レベル付き）

    Raises:
        HTTPException: allowlist 外ファイル指定、不正パターン、上限超過時
    """
    # allowlist 検証
    for f in request.files:
        if f not in ADVANCED_ALLOWED_LOG_FILES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Log file not in allowlist: {f}",
            )

    _validate_adv_query(request.query, allow_regex=request.regex)
    pattern = _compile_pattern(request.query, request.regex)

    audit_log.record(
        operation="log_advanced_search",
        user_id=current_user.user_id,
        target=str(request.files),
        status="attempt",
        details={"query": request.query, "regex": request.regex, "limit": request.limit},
    )

    results: List[Dict[str, Any]] = []

    for filepath in request.files:
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, start=1):
                    if len(results) >= request.limit:
                        break
                    line_stripped = line.rstrip("\n")
                    if pattern.search(line_stripped):
                        results.append(
                            {
                                "file": filepath,
                                "lineno": lineno,
                                "level": _detect_level(line_stripped),
                                "message": line_stripped,
                            }
                        )
        except PermissionError:
            logger.warning("Permission denied reading log file: %s", filepath)
            results.append({"file": filepath, "lineno": 0, "level": "ERROR", "message": f"[Permission denied: {filepath}]"})
        except FileNotFoundError:
            logger.warning("Log file not found: %s", filepath)

        if len(results) >= request.limit:
            break

    audit_log.record(
        operation="log_advanced_search",
        user_id=current_user.user_id,
        target=str(request.files),
        status="success",
        details={"matches": len(results)},
    )

    return {
        "query": request.query,
        "regex": request.regex,
        "files_searched": request.files,
        "matches": len(results),
        "results": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/allowed-files")
async def list_advanced_log_files(
    current_user: TokenData = Depends(require_permission("read:logs")),
) -> Dict[str, Any]:
    """高度検索で利用可能な allowlist ファイル一覧を返す。

    Args:
        current_user: 現在のユーザー（read:logs 権限必須）

    Returns:
        allowlist ファイル一覧
    """
    files_info = []
    for fp in ADVANCED_ALLOWED_LOG_FILES:
        p = Path(fp)
        files_info.append(
            {
                "path": fp,
                "name": p.name,
                "exists": p.exists(),
            }
        )
    return {
        "files": files_info,
        "file_count": len(files_info),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/stats")
async def get_log_stats(
    current_user: TokenData = Depends(require_permission("read:logs")),
) -> Dict[str, Any]:
    """allowlist ログファイルのログレベル別件数を返す。

    最大 5000 行を末尾から走査し ERROR/WARN/INFO/DEBUG 件数を集計する。

    Args:
        current_user: 現在のユーザー（read:logs 権限必須）

    Returns:
        レベル別件数辞書（全ファイル合計 + ファイル別）
    """
    audit_log.record(
        operation="log_stats",
        user_id=current_user.user_id,
        target="all",
        status="attempt",
        details={},
    )

    totals: Dict[str, int] = {"ERROR": 0, "WARN": 0, "INFO": 0, "DEBUG": 0, "UNKNOWN": 0}
    per_file: Dict[str, Dict[str, int]] = {}
    SCAN_LINES = 5000

    for filepath in ADVANCED_ALLOWED_LOG_FILES:
        p = Path(filepath)
        if not p.exists():
            continue
        counts: Dict[str, int] = {"ERROR": 0, "WARN": 0, "INFO": 0, "DEBUG": 0, "UNKNOWN": 0}
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
                lines_buf: List[str] = []
                for line in fh:
                    lines_buf.append(line)
                    if len(lines_buf) > SCAN_LINES:
                        lines_buf.pop(0)
                for line in lines_buf:
                    lvl = _detect_level(line)
                    counts[lvl] += 1
                    totals[lvl] += 1
        except PermissionError:
            logger.warning("Permission denied reading %s for stats", filepath)
            continue
        per_file[filepath] = counts

    audit_log.record(
        operation="log_stats",
        user_id=current_user.user_id,
        target="all",
        status="success",
        details={"total_errors": totals["ERROR"]},
    )

    return {
        "totals": totals,
        "per_file": per_file,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/timeline")
async def get_log_timeline(
    current_user: TokenData = Depends(require_permission("read:logs")),
) -> Dict[str, Any]:
    """直近 24 時間のエラー数を 1 時間ごとに集計して返す（Chart.js 用）。

    syslog と auth.log を走査し、タイムスタンプを解析して集計する。

    Args:
        current_user: 現在のユーザー（read:logs 権限必須）

    Returns:
        labels（時刻文字列）と datasets（エラー数配列）
    """
    audit_log.record(
        operation="log_timeline",
        user_id=current_user.user_id,
        target="timeline",
        status="attempt",
        details={},
    )

    now = datetime.now(timezone.utc)
    # 0〜23 の各時刻バケット（24時間分）
    hourly: Dict[int, int] = {h: 0 for h in range(24)}

    # 月略称 -> 数字マッピング
    MONTH_MAP = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }
    # syslog 形式: "Jan  1 12:34:56 ..." or ISO 形式
    _syslog_re = re.compile(r"^(\w{3})\s+(\d+)\s+(\d{2}):(\d{2}):(\d{2})")
    _iso_re = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2})")

    scan_files = ["/var/log/syslog", "/var/log/auth.log"]

    for filepath in scan_files:
        if filepath not in ADVANCED_ALLOWED_LOG_FILES:
            continue
        p = Path(filepath)
        if not p.exists():
            continue
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    lvl = _detect_level(line)
                    if lvl not in ("ERROR", "WARN"):
                        continue
                    # タイムスタンプ解析
                    hour: Optional[int] = None
                    m = _syslog_re.match(line)
                    if m:
                        month = MONTH_MAP.get(m.group(1), 0)
                        day = int(m.group(2))
                        h = int(m.group(3))
                        try:
                            log_dt = datetime(now.year, month, day, h, tzinfo=timezone.utc)
                            diff_hours = int((now - log_dt).total_seconds() // 3600)
                            if 0 <= diff_hours < 24:
                                hour = now.hour - diff_hours
                                if hour < 0:
                                    hour += 24
                        except ValueError:
                            pass
                    else:
                        m2 = _iso_re.match(line)
                        if m2:
                            try:
                                log_dt = datetime(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)), int(m2.group(4)), tzinfo=timezone.utc)
                                diff_hours = int((now - log_dt).total_seconds() // 3600)
                                if 0 <= diff_hours < 24:
                                    hour = now.hour - diff_hours
                                    if hour < 0:
                                        hour += 24
                            except ValueError:
                                pass
                    if hour is not None:
                        hourly[hour] = hourly.get(hour, 0) + 1
        except PermissionError:
            logger.warning("Permission denied reading %s for timeline", filepath)
            continue

    # Chart.js 用ラベルと値を生成（過去24時間順）
    labels = []
    data_values = []
    for h in range(24):
        slot = (now.hour - 23 + h) % 24
        labels.append(f"{slot:02d}:00")
        data_values.append(hourly.get(slot, 0))

    audit_log.record(
        operation="log_timeline",
        user_id=current_user.user_id,
        target="timeline",
        status="success",
        details={"total_errors": sum(data_values)},
    )

    return {
        "labels": labels,
        "datasets": [
            {
                "label": "エラー/警告数",
                "data": data_values,
            }
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ===================================================================
# 保存フィルター エンドポイント
# ===================================================================


@router.post("/saved-filters", status_code=status.HTTP_201_CREATED)
async def create_saved_filter(
    request: SavedFilterCreateRequest,
    current_user: TokenData = Depends(require_permission("read:logs")),
) -> Dict[str, Any]:
    """検索フィルターに名前をつけて保存する。

    Args:
        request: フィルター作成リクエスト
        current_user: 現在のユーザー（read:logs 権限必須）

    Returns:
        作成されたフィルターオブジェクト

    Raises:
        HTTPException: ファイル書き込みエラー時
    """
    # ファイルも allowlist 検証
    for f in request.files:
        if f not in ADVANCED_ALLOWED_LOG_FILES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Log file not in allowlist: {f}",
            )

    data = _load_saved_filters()
    new_filter = {
        "id": str(uuid.uuid4()),
        "name": request.name,
        "query": request.query,
        "files": request.files,
        "regex": request.regex,
        "created_by": current_user.username,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    data["filters"].append(new_filter)
    _save_saved_filters(data)

    audit_log.record(
        operation="log_filter_create",
        user_id=current_user.user_id,
        target=new_filter["id"],
        status="success",
        details={"name": request.name},
    )

    return new_filter


@router.get("/saved-filters")
async def list_saved_filters(
    current_user: TokenData = Depends(require_permission("read:logs")),
) -> Dict[str, Any]:
    """保存済みフィルター一覧を返す。

    Args:
        current_user: 現在のユーザー（read:logs 権限必須）

    Returns:
        フィルター一覧
    """
    data = _load_saved_filters()
    return {
        "filters": data.get("filters", []),
        "count": len(data.get("filters", [])),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.delete("/saved-filters/{filter_id}", status_code=status.HTTP_200_OK)
async def delete_saved_filter(
    filter_id: str = FPath(..., min_length=1, max_length=64),
    current_user: TokenData = Depends(require_permission("read:logs")),
) -> Dict[str, Any]:
    """保存済みフィルターを削除する。

    Args:
        filter_id: 削除対象フィルターの UUID
        current_user: 現在のユーザー（read:logs 権限必須）

    Returns:
        削除結果

    Raises:
        HTTPException: フィルターが見つからない場合
    """
    data = _load_saved_filters()
    original_count = len(data.get("filters", []))
    data["filters"] = [f for f in data.get("filters", []) if f.get("id") != filter_id]

    if len(data["filters"]) == original_count:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Filter not found: {filter_id}",
        )

    _save_saved_filters(data)

    audit_log.record(
        operation="log_filter_delete",
        user_id=current_user.user_id,
        target=filter_id,
        status="success",
        details={},
    )

    return {"deleted": filter_id, "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/{service_name}", response_model=LogsResponse)
async def get_service_logs(
    service_name: str = FPath(..., min_length=1, max_length=64, pattern="^[a-zA-Z0-9_-]+$"),
    lines: int = Query(100, ge=1, le=1000, description="取得行数（1-1000）"),
    current_user: TokenData = Depends(require_permission("read:logs")),
):
    """
    サービスのログを取得

    Args:
        service_name: サービス名
        lines: 取得行数（1-1000）
        current_user: 現在のユーザー（read:logs 権限必須）

    Returns:
        ログデータ

    Raises:
        HTTPException: ログ取得失敗時
    """
    logger.info(f"Log view requested: service={service_name}, lines={lines}, user={current_user.username}")

    # 監査ログ記録（試行）
    audit_log.record(
        operation="log_view",
        user_id=current_user.user_id,
        target=service_name,
        status="attempt",
        details={"lines": lines},
    )

    try:
        # sudo ラッパー経由でログを取得
        result = sudo_wrapper.get_logs(service_name, lines)

        # ラッパーがエラーを返した場合
        if result.get("status") == "error":
            # 監査ログ記録（拒否）
            audit_log.record(
                operation="log_view",
                user_id=current_user.user_id,
                target=service_name,
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=result.get("message", "Log view denied"),
            )

        # 監査ログ記録（成功）
        audit_log.record(
            operation="log_view",
            user_id=current_user.user_id,
            target=service_name,
            status="success",
            details={"lines_returned": result.get("lines_returned", 0)},
        )

        logger.info(f"Log view successful: {service_name}")

        return LogsResponse(**result)

    except SudoWrapperError as e:
        # 監査ログ記録（失敗）
        audit_log.record(
            operation="log_view",
            user_id=current_user.user_id,
            target=service_name,
            status="failure",
            details={"error": str(e)},
        )

        logger.error(f"Log view failed: {service_name}, error={e}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Log retrieval failed: {str(e)}",
        )
