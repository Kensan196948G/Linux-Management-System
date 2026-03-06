"""ログ検索APIルーター"""
import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.core.auth import TokenData, require_permission
from backend.core.sudo_wrapper import SudoWrapperError, sudo_wrapper

router = APIRouter()

FORBIDDEN_CHARS = [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?", "{", "}", "[", "]"]


def _validate_search_param(value: str, param_name: str) -> None:
    """検索パラメータに禁止文字が含まれていないか検証する。

    Args:
        value: 検証対象の文字列
        param_name: パラメータ名（エラーメッセージ用）

    Raises:
        HTTPException: 禁止文字が含まれている場合は 400
    """
    for char in FORBIDDEN_CHARS:
        if char in value:
            raise HTTPException(status_code=400, detail=f"Forbidden character '{char}' in {param_name}")


@router.get("/files")
async def list_log_files(
    current_user: Annotated[TokenData, Depends(require_permission("read:logsearch"))] = None,
):
    """ログファイル一覧を取得する"""
    try:
        result = sudo_wrapper.list_log_files()
        return {
            "files": result.get("files", []),
            "file_count": result.get("file_count", 0),
            "timestamp": result.get("timestamp", datetime.now(timezone.utc).isoformat()),
        }
    except SudoWrapperError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/search")
async def search_logs(
    pattern: str = Query(..., min_length=1, max_length=100),
    logfile: str = Query(default="syslog"),
    lines: int = Query(default=50, ge=1, le=200),
    current_user: Annotated[TokenData, Depends(require_permission("read:logsearch"))] = None,
):
    """ログを検索する

    Args:
        pattern: 検索パターン（必須、1〜100文字）
        logfile: 対象ログファイル名（デフォルト: syslog）
        lines: 返す最大行数（1〜200、デフォルト: 50）
    """
    _validate_search_param(pattern, "pattern")
    _validate_search_param(logfile, "logfile")

    if not re.match(r"^[a-zA-Z0-9._-]+$", logfile):
        raise HTTPException(status_code=400, detail="Invalid logfile name: only alphanumeric, dot, underscore, hyphen allowed")

    try:
        result = sudo_wrapper.search_logs(pattern, logfile, lines)
        return {
            "pattern": result.get("pattern", pattern),
            "logfile": result.get("logfile", logfile),
            "results": result.get("results", []),
            "lines_returned": result.get("lines_returned", 0),
            "timestamp": result.get("timestamp", datetime.now(timezone.utc).isoformat()),
        }
    except SudoWrapperError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/recent-errors")
async def get_recent_errors(
    current_user: Annotated[TokenData, Depends(require_permission("read:logsearch"))] = None,
):
    """最近のエラーログを取得する"""
    try:
        result = sudo_wrapper.get_recent_errors()
        return {
            "errors": result.get("errors", []),
            "error_count": result.get("error_count", 0),
            "timestamp": result.get("timestamp", datetime.now(timezone.utc).isoformat()),
        }
    except SudoWrapperError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
