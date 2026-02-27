#!/bin/bash
# ============================================================
# adminui-quotas.sh - Disk Quota 管理ラッパースクリプト
#
# 実行ユーザー: svc-adminui (sudo 経由)
# 用途: ディスククォータの取得・設定を安全に実行
#
# 使用方法:
#   ./adminui-quotas.sh status [filesystem]
#   ./adminui-quotas.sh user <username>
#   ./adminui-quotas.sh group <groupname>
#   ./adminui-quotas.sh users [filesystem]
#   ./adminui-quotas.sh set user <username> <fs> <soft_kb> <hard_kb> [isoft] [ihard]
#   ./adminui-quotas.sh set group <groupname> <fs> <soft_kb> <hard_kb> [isoft] [ihard]
#   ./adminui-quotas.sh report [filesystem]
# ============================================================
set -euo pipefail
IFS=$'\n\t'

# ============================================================
# セキュリティ: 許可フィールド
# ============================================================
ALLOWED_COMMANDS=("status" "user" "group" "users" "set" "report")

# 使用可能なファイルシステムの許可パターン (マウントポイント)
# /dev/で始まるもの, UUID=, または / や /home などのマウントポイント
ALLOWED_FS_PATTERN='^(/[a-zA-Z0-9/_.-]*|/dev/[a-zA-Z0-9/_.-]+|UUID=[a-zA-Z0-9-]+)$'

# ユーザー名/グループ名の許可パターン (英数字・ハイフン・アンダースコア・ドット)
ALLOWED_NAME_PATTERN='^[a-zA-Z0-9._-]{1,64}$'

# ============================================================
# 入力検証関数
# ============================================================
validate_name() {
    local name="$1"
    local label="$2"
    if [[ ! "$name" =~ $ALLOWED_NAME_PATTERN ]]; then
        echo "ERROR: Invalid ${label}: ${name}" >&2
        exit 1
    fi
}

validate_filesystem() {
    local fs="$1"
    if [[ -n "$fs" ]] && [[ ! "$fs" =~ $ALLOWED_FS_PATTERN ]]; then
        echo "ERROR: Invalid filesystem: ${fs}" >&2
        exit 1
    fi
}

validate_quota_value() {
    local val="$1"
    local label="$2"
    if [[ ! "$val" =~ ^[0-9]+$ ]]; then
        echo "ERROR: Invalid ${label} (must be non-negative integer): ${val}" >&2
        exit 1
    fi
}

# ============================================================
# quotaコマンドが利用可能か確認
# ============================================================
check_quota_available() {
    local has_quota=true
    command -v quota >/dev/null 2>&1 || has_quota=false
    command -v repquota >/dev/null 2>&1 || has_quota=false
    echo "$has_quota"
}

# ============================================================
# メイン処理
# ============================================================
if [[ $# -lt 1 ]]; then
    echo "ERROR: Missing command argument" >&2
    exit 1
fi

COMMAND="$1"

# コマンド検証
VALID_CMD=false
for allowed in "${ALLOWED_COMMANDS[@]}"; do
    if [[ "$COMMAND" == "$allowed" ]]; then
        VALID_CMD=true
        break
    fi
done

if [[ "$VALID_CMD" != "true" ]]; then
    echo "ERROR: Command not allowed: ${COMMAND}" >&2
    exit 1
fi

QUOTA_AVAILABLE=$(check_quota_available)

case "$COMMAND" in
    "status")
        # ファイルシステムのクォータ状態
        FS="${2:-}"
        validate_filesystem "$FS"
        if [[ "$QUOTA_AVAILABLE" != "true" ]]; then
            echo '{"status":"unavailable","message":"quota tools not installed","filesystems":[]}'
            exit 0
        fi
        if [[ -n "$FS" ]]; then
            repquota -s "$FS" 2>/dev/null && exit 0
        fi
        repquota -as 2>/dev/null || echo '{"status":"error","message":"repquota failed"}'
        ;;

    "user")
        # 特定ユーザーのクォータ情報
        if [[ $# -lt 2 ]]; then
            echo "ERROR: Missing username" >&2
            exit 1
        fi
        USERNAME="$2"
        validate_name "$USERNAME" "username"
        if [[ "$QUOTA_AVAILABLE" != "true" ]]; then
            echo '{"status":"unavailable","message":"quota tools not installed"}'
            exit 0
        fi
        # ユーザーが存在するか確認
        if ! id "$USERNAME" >/dev/null 2>&1; then
            echo "ERROR: User not found: ${USERNAME}" >&2
            exit 1
        fi
        quota -us "$USERNAME" 2>/dev/null || echo "{\"status\":\"no_quota\",\"user\":\"${USERNAME}\"}"
        ;;

    "group")
        # 特定グループのクォータ情報
        if [[ $# -lt 2 ]]; then
            echo "ERROR: Missing groupname" >&2
            exit 1
        fi
        GROUPNAME="$2"
        validate_name "$GROUPNAME" "groupname"
        if [[ "$QUOTA_AVAILABLE" != "true" ]]; then
            echo '{"status":"unavailable","message":"quota tools not installed"}'
            exit 0
        fi
        # グループが存在するか確認
        if ! getent group "$GROUPNAME" >/dev/null 2>&1; then
            echo "ERROR: Group not found: ${GROUPNAME}" >&2
            exit 1
        fi
        quota -gs "$GROUPNAME" 2>/dev/null || echo "{\"status\":\"no_quota\",\"group\":\"${GROUPNAME}\"}"
        ;;

    "users")
        # 全ユーザーのクォータ一覧 (JSON形式)
        FS="${2:-}"
        validate_filesystem "$FS"
        if [[ "$QUOTA_AVAILABLE" != "true" ]]; then
            echo '{"status":"unavailable","message":"quota tools not installed","users":[]}'
            exit 0
        fi
        if [[ -n "$FS" ]]; then
            repquota -as "$FS" 2>/dev/null || echo '{"status":"error","message":"repquota failed"}'
        else
            repquota -as 2>/dev/null || echo '{"status":"error","message":"repquota failed"}'
        fi
        ;;

    "set")
        # クォータ設定 (user または group)
        if [[ $# -lt 7 ]]; then
            echo "ERROR: Missing arguments for set command" >&2
            echo "Usage: set user|group <name> <filesystem> <soft_kb> <hard_kb> [isoft] [ihard]" >&2
            exit 1
        fi
        SET_TYPE="$2"
        SET_NAME="$3"
        SET_FS="$4"
        SOFT_KB="$5"
        HARD_KB="$6"
        ISOFT="${7:-0}"
        IHARD="${8:-0}"

        # 型の検証
        if [[ "$SET_TYPE" != "user" && "$SET_TYPE" != "group" ]]; then
            echo "ERROR: Type must be 'user' or 'group'" >&2
            exit 1
        fi

        validate_name "$SET_NAME" "$SET_TYPE"
        validate_filesystem "$SET_FS"
        validate_quota_value "$SOFT_KB" "soft_kb"
        validate_quota_value "$HARD_KB" "hard_kb"
        validate_quota_value "$ISOFT" "isoft"
        validate_quota_value "$IHARD" "ihard"

        # ファイルシステムが存在するか確認
        if [[ -n "$SET_FS" ]] && ! findmnt -n "$SET_FS" >/dev/null 2>&1; then
            echo "ERROR: Filesystem not mounted: ${SET_FS}" >&2
            exit 1
        fi

        if [[ "$QUOTA_AVAILABLE" != "true" ]]; then
            echo "ERROR: quota tools not available" >&2
            exit 1
        fi

        if [[ "$SET_TYPE" == "user" ]]; then
            # ユーザーが存在するか確認
            if ! id "$SET_NAME" >/dev/null 2>&1; then
                echo "ERROR: User not found: ${SET_NAME}" >&2
                exit 1
            fi
            setquota -u "$SET_NAME" "$SOFT_KB" "$HARD_KB" "$ISOFT" "$IHARD" "$SET_FS"
        else
            # グループが存在するか確認
            if ! getent group "$SET_NAME" >/dev/null 2>&1; then
                echo "ERROR: Group not found: ${SET_NAME}" >&2
                exit 1
            fi
            setquota -g "$SET_NAME" "$SOFT_KB" "$HARD_KB" "$ISOFT" "$IHARD" "$SET_FS"
        fi
        echo "{\"status\":\"success\",\"message\":\"Quota set for ${SET_TYPE} ${SET_NAME}\"}"
        ;;

    "report")
        # クォータレポート
        FS="${2:-}"
        validate_filesystem "$FS"
        if [[ "$QUOTA_AVAILABLE" != "true" ]]; then
            echo '{"status":"unavailable","message":"quota tools not installed"}'
            exit 0
        fi
        if [[ -n "$FS" ]]; then
            repquota -vs "$FS" 2>/dev/null || echo '{"status":"error","message":"repquota failed"}'
        else
            repquota -avs 2>/dev/null || echo '{"status":"error","message":"repquota failed"}'
        fi
        ;;
esac
