#!/bin/bash
# adminui-nfs.sh - NFS マウント管理ラッパースクリプト
# セキュリティ原則: allowlist のみ許可、特殊文字を拒否
set -euo pipefail

COMMAND="${1:-}"
ALLOWED_COMMANDS=("list" "mount" "umount" "check" "fstab")

# コマンド検証
VALID_CMD=false
for cmd in "${ALLOWED_COMMANDS[@]}"; do
    if [[ "$COMMAND" == "$cmd" ]]; then
        VALID_CMD=true
        break
    fi
done

if [[ "$VALID_CMD" == false ]]; then
    echo '{"status": "error", "message": "Command not allowed"}' >&2
    exit 1
fi

# マウントポイント allowlist
ALLOWED_MOUNT_DIRS=("/mnt" "/media" "/srv/nfs" "/data/nfs")

_validate_special_chars() {
    local value="$1"
    if [[ "$value" =~ [';|&$()><*?{}'\''\\'] ]] || [[ "$value" == *'`'* ]]; then
        echo '{"status": "error", "message": "Invalid characters detected"}' >&2
        exit 1
    fi
}

_validate_mount_point() {
    local mount_point="$1"
    local allowed=false
    for allowed_dir in "${ALLOWED_MOUNT_DIRS[@]}"; do
        if [[ "$mount_point" == "$allowed_dir" || "$mount_point" == "$allowed_dir/"* ]]; then
            allowed=true
            break
        fi
    done
    if [[ "$allowed" == false ]]; then
        echo '{"status": "error", "message": "Mount point not in allowed directories"}' >&2
        exit 1
    fi
}

case "$COMMAND" in
    list)
        # 現在のNFSマウント一覧を取得
        mount -t nfs,nfs4 2>/dev/null || echo ""
        ;;

    mount)
        NFS_SOURCE="${2:-}"
        MOUNT_POINT="${3:-}"

        if [[ -z "$NFS_SOURCE" || -z "$MOUNT_POINT" ]]; then
            echo '{"status": "error", "message": "NFS source and mount point required"}' >&2
            exit 1
        fi

        _validate_special_chars "$NFS_SOURCE"
        _validate_special_chars "$MOUNT_POINT"
        _validate_mount_point "$MOUNT_POINT"

        mkdir -p "$MOUNT_POINT"
        mount -t nfs "$NFS_SOURCE" "$MOUNT_POINT" -o ro,noexec,nosuid
        echo '{"status": "success", "message": "Mounted successfully"}'
        ;;

    umount)
        MOUNT_POINT="${2:-}"

        if [[ -z "$MOUNT_POINT" ]]; then
            echo '{"status": "error", "message": "Mount point required"}' >&2
            exit 1
        fi

        _validate_special_chars "$MOUNT_POINT"
        _validate_mount_point "$MOUNT_POINT"

        umount "$MOUNT_POINT"
        echo '{"status": "success", "message": "Unmounted successfully"}'
        ;;

    check)
        # /proc/mounts からNFSエントリを確認
        grep -E '^[^ ]+ [^ ]+ nfs' /proc/mounts 2>/dev/null || echo ""
        ;;

    fstab)
        # /etc/fstab からNFSエントリを取得
        grep -E '^[^#].*nfs' /etc/fstab 2>/dev/null || echo ""
        ;;
esac
