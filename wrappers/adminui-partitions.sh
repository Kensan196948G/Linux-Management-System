#!/usr/bin/env bash
# ==============================================================================
# adminui-partitions.sh - Disk Partitions 管理ラッパー（読み取り専用）
#
# 機能:
#   lsblk, df, blkid を使用してパーティション情報を取得する。
#   全操作は読み取り専用。書き込み操作は一切行わない。
#
# 使用方法:
#   adminui-partitions.sh <subcommand>
#
# サブコマンド:
#   list   - パーティション一覧 (lsblk -J)
#   usage  - ディスク使用量 (df -h)
#   detail - ブロックデバイス詳細 (blkid)
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは直接実行
#   - 許可サブコマンドのみ実行（allowlist方式）
#   - 読み取り専用（パーティション操作・マウント操作等は行わない）
# ==============================================================================

set -euo pipefail

ALLOWED_SUBCOMMANDS=("list" "usage" "detail")

error_json() {
    printf '{"status": "error", "message": "%s"}\n' "$1" >&2
    exit 1
}

if [ "$#" -ne 1 ]; then
    error_json "Usage: adminui-partitions.sh <subcommand>"
fi

SUBCOMMAND="$1"

# allowlist 検証
ALLOWED=false
for cmd in "${ALLOWED_SUBCOMMANDS[@]}"; do
    if [ "$cmd" = "$SUBCOMMAND" ]; then
        ALLOWED=true
        break
    fi
done

if ! "$ALLOWED"; then
    error_json "Unknown subcommand: $SUBCOMMAND. Allowed: ${ALLOWED_SUBCOMMANDS[*]}"
fi

TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

case "$SUBCOMMAND" in
    list)
        # パーティション一覧 (lsblk -J)
        if ! command -v lsblk >/dev/null 2>&1; then
            printf '{"status": "unavailable", "message": "lsblk not found", "timestamp": "%s"}\n' "$TIMESTAMP"
            exit 0
        fi

        LSBLK_JSON=$(lsblk -J -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,LABEL,UUID 2>/dev/null || echo '{"blockdevices":[]}')
        # JSON 検証
        LSBLK_VALIDATED=$(printf '%s' "$LSBLK_JSON" | python3 -c "import sys,json; data=sys.stdin.read(); json.loads(data); print(data)" 2>/dev/null || echo '{"blockdevices":[]}')
        printf '{"status": "success", "partitions": %s, "timestamp": "%s"}\n' "$LSBLK_VALIDATED" "$TIMESTAMP"
        ;;

    usage)
        # ディスク使用量 (df -h)
        if ! command -v df >/dev/null 2>&1; then
            printf '{"status": "unavailable", "message": "df not found", "timestamp": "%s"}\n' "$TIMESTAMP"
            exit 0
        fi

        DF_OUTPUT=$(df -h --output=source,size,used,avail,pcent,target 2>/dev/null | tail -n +2 || df -h 2>/dev/null || true)
        DF_ESCAPED=$(printf '%s' "$DF_OUTPUT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || printf '"%s"' "$DF_OUTPUT")
        printf '{"status": "success", "usage_raw": %s, "timestamp": "%s"}\n' "$DF_ESCAPED" "$TIMESTAMP"
        ;;

    detail)
        # ブロックデバイス詳細 (blkid)
        if ! command -v blkid >/dev/null 2>&1; then
            printf '{"status": "unavailable", "message": "blkid not found", "timestamp": "%s"}\n' "$TIMESTAMP"
            exit 0
        fi

        BLKID_OUTPUT=$(blkid 2>/dev/null || true)
        BLKID_ESCAPED=$(printf '%s' "$BLKID_OUTPUT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || printf '"%s"' "$BLKID_OUTPUT")
        printf '{"status": "success", "blkid_raw": %s, "timestamp": "%s"}\n' "$BLKID_ESCAPED" "$TIMESTAMP"
        ;;

    *)
        error_json "Unexpected subcommand: $SUBCOMMAND"
        ;;
esac
