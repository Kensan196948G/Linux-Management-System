"""ログ検索APIルーター"""
import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Annotated, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

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


_STREAM_ALLOWED_LOG_FILES = [
    "syslog",
    "auth.log",
    "kern.log",
    "dpkg.log",
    "nginx/access.log",
    "nginx/error.log",
]


@router.get("/tail")
async def get_log_tail_multi(
    lines: int = Query(default=30, ge=5, le=100, description="各ファイルから取得する末尾行数"),
    current_user: Annotated[TokenData, Depends(require_permission("read:logsearch"))] = None,
):
    """複数ログファイルの末尾を連結取得する"""
    try:
        result = sudo_wrapper.get_log_tail_multi(lines)
        return {
            "lines_per_file": lines,
            "output": result.get("lines", []),
            "lines_returned": result.get("lines_returned", 0),
            "timestamp": result.get("timestamp", datetime.now(timezone.utc).isoformat()),
        }
    except SudoWrapperError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/stream")
async def stream_log_tail(
    logfile: str = Query(default="syslog", description="ストリーミング対象ログファイル名"),
    token: str = Query(..., description="JWT認証トークン"),
):
    """ログの末尾をSSEで10秒ごとに配信するポーリング型ストリーム。

    EventSource API は Authorization ヘッダー非対応のため、
    クエリパラメータでトークンを受け取る。

    Args:
        logfile: 対象ログファイル名（許可リスト内のみ）
        token: JWT認証トークン
    """
    from backend.core.auth import decode_token

    user_data = decode_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid token")

    _validate_search_param(logfile, "logfile")
    if not re.match(r"^[a-zA-Z0-9._/-]+$", logfile):
        raise HTTPException(status_code=400, detail="Invalid logfile name")
    if logfile not in _STREAM_ALLOWED_LOG_FILES:
        raise HTTPException(status_code=400, detail=f"Log file not allowed: {logfile}")

    import logging

    logger = logging.getLogger(__name__)

    async def event_generator() -> AsyncGenerator[str, None]:
        last_lines: list = []
        try:
            while True:
                try:
                    result = await asyncio.to_thread(sudo_wrapper.get_log_tail_multi, 20)
                    new_lines = result.get("lines", [])
                    if new_lines != last_lines:
                        last_lines = new_lines
                        payload = json.dumps(
                            {
                                "lines": new_lines,
                                "logfile": logfile,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                        yield f"data: {payload}\n\n"
                    else:
                        yield f"data: {json.dumps({'heartbeat': True})}\n\n"
                except Exception as e:
                    logger.error("SSE poll error: %s", e)
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            logger.info("SSE log stream cancelled")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
