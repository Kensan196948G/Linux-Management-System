"""バックアップ管理APIルーター"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.api.routes.approval import approval_service
from backend.core.audit_log import AuditLog
from backend.core.auth import TokenData, require_permission
from backend.core.sudo_wrapper import sudo_wrapper
from backend.core.validation import validate_no_forbidden_chars

router = APIRouter()
audit_log = AuditLog()

# バックアップ対象ディレクトリの allowlist
ALLOWED_BACKUP_TARGETS = ["/home", "/etc", "/var/www", "/opt", "/var/backups"]

# スケジュールデータ保存先
SCHEDULES_FILE = Path(__file__).parents[3] / "data" / "backup_schedules.json"
# 履歴データ保存先
HISTORY_FILE = Path(__file__).parents[3] / "data" / "backup_history.json"

# cron プリセット
CRON_PRESETS = {
    "daily": "0 2 * * *",
    "weekly": "0 2 * * 0",
    "monthly": "0 2 1 * *",
}


# ─── Pydantic モデル ────────────────────────────────────────────────────────


class ScheduleCreate(BaseModel):
    """スケジュール作成リクエスト"""

    name: str = Field(..., min_length=1, max_length=100)
    cron: str = Field(..., description="cron式 または プリセット名(daily/weekly/monthly)")
    target: str = Field(..., description="バックアップ対象ディレクトリ (allowlist内)")
    enabled: bool = Field(default=True)


class RestoreRequest(BaseModel):
    """リストアリクエスト"""

    backup_file: str = Field(..., description="バックアップファイルのパス")
    restore_target: str = Field(default="/var/tmp/adminui-restore", description="リストア先ディレクトリ")  # nosec B108
    reason: str = Field(..., min_length=5, max_length=500, description="リストア理由")


# ─── ヘルパー関数 ────────────────────────────────────────────────────────────


def _load_schedules() -> dict:
    """スケジュールJSONを読み込む"""
    if not SCHEDULES_FILE.exists():
        SCHEDULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        SCHEDULES_FILE.write_text(json.dumps({"schedules": []}, ensure_ascii=False, indent=2))
    try:
        return json.loads(SCHEDULES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schedules": []}


def _save_schedules(data: dict) -> None:
    """スケジュールJSONを保存する"""
    SCHEDULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def _load_history() -> dict:
    """実行履歴JSONを読み込む"""
    if not HISTORY_FILE.exists():
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(json.dumps({"history": []}, ensure_ascii=False, indent=2))
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"history": []}


def _validate_cron(cron: str) -> str:
    """cron式またはプリセット名を検証し、cron式を返す"""
    if cron in CRON_PRESETS:
        return CRON_PRESETS[cron]
    parts = cron.split()
    if len(parts) != 5:
        raise HTTPException(status_code=400, detail="cron式は5フィールド(分 時 日 月 曜日)で入力してください")
    return cron


def _validate_target(target: str) -> str:
    """バックアップ対象ディレクトリをallowlistで検証する"""
    if target not in ALLOWED_BACKUP_TARGETS:
        raise HTTPException(
            status_code=400,
            detail=f"対象ディレクトリが許可リスト外です。許可: {ALLOWED_BACKUP_TARGETS}",
        )
    return target


# ─── 既存エンドポイント（変更なし） ─────────────────────────────────────────


@router.get("/list")
async def get_backup_list(
    current_user: Annotated[TokenData, Depends(require_permission("read:backup"))] = None,
):
    """バックアップファイル一覧 (read:backup権限)"""
    try:
        result = sudo_wrapper.get_backup_list()
        lines = [ln for ln in result["stdout"].splitlines() if ln]
        return {"backups": lines, "count": len(lines), "timestamp": datetime.now(timezone.utc).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/disk-usage")
async def get_backup_disk_usage(
    current_user: Annotated[TokenData, Depends(require_permission("read:backup"))] = None,
):
    """バックアップディスク使用量 (read:backup権限)"""
    try:
        result = sudo_wrapper.get_backup_disk_usage()
        return {"usage": result["stdout"].strip(), "timestamp": datetime.now(timezone.utc).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/recent-logs")
async def get_backup_recent_logs(
    current_user: Annotated[TokenData, Depends(require_permission("read:backup"))] = None,
):
    """バックアップ関連ログ (read:backup権限)"""
    try:
        result = sudo_wrapper.get_backup_recent_logs()
        lines = [ln for ln in result["stdout"].splitlines() if ln]
        return {"logs": lines, "count": len(lines)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ─── 新規エンドポイント ──────────────────────────────────────────────────────


@router.get("/status")
async def get_backup_status(
    current_user: Annotated[TokenData, Depends(require_permission("read:backup"))] = None,
):
    """現在実行中のバックアップ状態 (read:backup権限)"""
    try:
        result = sudo_wrapper.get_backup_status()
        lines = [ln for ln in result["stdout"].splitlines() if ln]
        # 実行中かどうかを簡易判定
        running = any("running" in ln.lower() or "active" in ln.lower() for ln in lines)
        return {
            "running": running,
            "status": result["stdout"],
            "status_lines": lines,
            "returncode": result["returncode"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/storage")
async def get_backup_storage(
    current_user: Annotated[TokenData, Depends(require_permission("read:backup"))] = None,
):
    """ストレージ使用量とバックアップファイル一覧 (read:backup権限)"""
    try:
        files_result = sudo_wrapper.list_backup_files()
        usage_result = sudo_wrapper.get_backup_disk_usage()

        files: list[dict] = []
        for line in files_result["stdout"].splitlines():
            line = line.strip()
            if not line or line.startswith("Backup") or line.startswith("No backup"):
                continue
            try:
                entry = json.loads(line)
                files.append(entry)
            except json.JSONDecodeError:
                files.append({"name": line, "path": line, "size": None, "mtime": None})

        return {
            "files": files,
            "count": len(files),
            "total_usage": usage_result["stdout"].strip(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/history")
async def get_backup_history(
    current_user: Annotated[TokenData, Depends(require_permission("read:backup"))] = None,
):
    """バックアップ実行履歴（最新50件）(read:backup権限)"""
    try:
        data = _load_history()
        history = data.get("history", [])
        # 最新50件を返す（新しい順）
        return {
            "history": history[:50],
            "count": len(history[:50]),
            "total": len(history),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ─── スケジュール管理 ────────────────────────────────────────────────────────


@router.get("/schedules")
async def list_schedules(
    current_user: Annotated[TokenData, Depends(require_permission("read:backup"))] = None,
):
    """バックアップスケジュール一覧 (read:backup権限)"""
    try:
        data = _load_schedules()
        return {
            "schedules": data.get("schedules", []),
            "count": len(data.get("schedules", [])),
            "presets": CRON_PRESETS,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/schedules", status_code=status.HTTP_201_CREATED)
async def create_schedule(
    req: ScheduleCreate,
    current_user: Annotated[TokenData, Depends(require_permission("write:backup"))] = None,
):
    """スケジュール追加（write:backup権限）"""
    try:
        validate_no_forbidden_chars(req.name, "name")
        cron_expr = _validate_cron(req.cron)
        target = _validate_target(req.target)

        data = _load_schedules()
        new_id = str(uuid.uuid4())
        entry = {
            "id": new_id,
            "name": req.name,
            "cron": cron_expr,
            "target": target,
            "enabled": req.enabled,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        data["schedules"].append(entry)
        _save_schedules(data)

        audit_log.record(
            user_id=current_user.user_id,
            operation="backup_schedule_create",
            target=target,
            status="success",
            details={"schedule_id": new_id, "cron": cron_expr},
        )
        return {"schedule": entry, "status": "created"}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_200_OK)
async def delete_schedule(
    schedule_id: str,
    current_user: Annotated[TokenData, Depends(require_permission("write:backup"))] = None,
):
    """スケジュール削除（write:backup権限）"""
    try:
        validate_no_forbidden_chars(schedule_id, "schedule_id")
        data = _load_schedules()
        schedules = data.get("schedules", [])
        original_count = len(schedules)
        schedules = [s for s in schedules if s["id"] != schedule_id]

        if len(schedules) == original_count:
            raise HTTPException(status_code=404, detail=f"スケジュールが見つかりません: {schedule_id}")

        data["schedules"] = schedules
        _save_schedules(data)

        audit_log.record(
            user_id=current_user.user_id,
            operation="backup_schedule_delete",
            target=schedule_id,
            status="success",
        )
        return {"status": "deleted", "schedule_id": schedule_id}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ─── リストア（承認フロー経由） ──────────────────────────────────────────────


@router.post("/restore", status_code=status.HTTP_202_ACCEPTED)
async def request_restore(
    req: RestoreRequest,
    current_user: Annotated[TokenData, Depends(require_permission("write:backup"))] = None,
):
    """リストアリクエスト（承認フロー経由・202返却）(write:backup権限)"""
    try:
        validate_no_forbidden_chars(req.backup_file, "backup_file")
        validate_no_forbidden_chars(req.restore_target, "restore_target")

        # 承認フローにリクエストを登録
        result = await approval_service.create_request(
            request_type="backup_restore",
            payload={
                "backup_file": req.backup_file,
                "restore_target": req.restore_target,
            },
            reason=req.reason,
            requester_id=current_user.user_id,
            requester_name=current_user.username,
            requester_role=current_user.role,
        )

        audit_log.record(
            user_id=current_user.user_id,
            operation="backup_restore_request",
            target=req.backup_file,
            status="pending_approval",
            details={"request_id": result.get("request_id"), "restore_target": req.restore_target},
        )

        return {
            "status": "accepted",
            "message": "リストアリクエストが承認待ちキューに追加されました",
            "request_id": result.get("request_id"),
            "approval_required": True,
        }
    except HTTPException:
        raise
    except LookupError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.patch("/schedules/{schedule_id}/toggle", status_code=status.HTTP_200_OK)
async def toggle_schedule(
    schedule_id: str,
    current_user: Annotated[TokenData, Depends(require_permission("write:backup"))] = None,
):
    """スケジュールの有効/無効を切り替える（write:backup権限）"""
    try:
        data = _load_schedules()
        target_sched = next((s for s in data["schedules"] if s["id"] == schedule_id), None)
        if not target_sched:
            raise HTTPException(status_code=404, detail=f"スケジュール '{schedule_id}' が見つかりません")

        target_sched["enabled"] = not target_sched.get("enabled", True)
        target_sched["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save_schedules(data)

        audit_log.record(
            user_id=current_user.user_id,
            operation="backup_schedule_toggle",
            target=target_sched.get("target", ""),
            status="success",
            details={"schedule_id": schedule_id, "enabled": target_sched["enabled"]},
        )
        return {
            "status": "updated",
            "schedule_id": schedule_id,
            "enabled": target_sched["enabled"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/schedules/{schedule_id}/run-now", status_code=status.HTTP_202_ACCEPTED)
async def run_schedule_now(
    schedule_id: str,
    current_user: Annotated[TokenData, Depends(require_permission("write:backup"))] = None,
):
    """スケジュールを即時実行（承認フロー経由・write:backup権限）"""
    try:
        data = _load_schedules()
        target_sched = next((s for s in data["schedules"] if s["id"] == schedule_id), None)
        if not target_sched:
            raise HTTPException(status_code=404, detail=f"スケジュール '{schedule_id}' が見つかりません")

        result = await approval_service.create_request(
            request_type="backup_run",
            payload={"schedule_id": schedule_id, "target": target_sched.get("target", ""), "triggered_by": "manual"},
            reason=f"手動実行: {target_sched.get('name', schedule_id)}",
            requester_id=current_user.user_id,
            requester_name=current_user.username,
            requester_role=current_user.role,
        )

        audit_log.record(
            user_id=current_user.user_id,
            operation="backup_schedule_run_now",
            target=target_sched.get("target", ""),
            status="pending_approval",
            details={"schedule_id": schedule_id, "request_id": result.get("request_id")},
        )

        return {
            "status": "accepted",
            "message": f"バックアップ実行リクエストを承認待ちに追加しました",
            "schedule_id": schedule_id,
            "request_id": result.get("request_id"),
        }
    except HTTPException:
        raise
    except LookupError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
