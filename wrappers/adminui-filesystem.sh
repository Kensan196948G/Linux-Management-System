#!/bin/bash
set -euo pipefail

# adminui-filesystem.sh - ファイルシステム管理ラッパー（read-only）
SUBCOMMAND="${1:-}"

case "$SUBCOMMAND" in
    df)
        # ファイルシステム使用量（JSONライク出力）
        df -P -T | tail -n +2 | awk '
        BEGIN { print "[" }
        NR>1 { print "," }
        {
            printf "{\"filesystem\":\"%s\",\"type\":\"%s\",\"size_kb\":%s,\"used_kb\":%s,\"avail_kb\":%s,\"use_pct\":\"%s\",\"mount\":\"%s\"}",
            $1,$2,$3,$4,$5,$6,$7
        }
        END { print "]" }
        '
        ;;
    du)
        # ディレクトリ使用量（安全なパスのみ）
        TARGET="${2:-/}"
        # パス検証: allowlist
        ALLOWED_PATHS=("/" "/home" "/var" "/tmp" "/opt" "/srv" "/usr")
        ALLOWED=0
        for path in "${ALLOWED_PATHS[@]}"; do
            if [[ "$TARGET" == "$path" || "$TARGET" == "$path/"* ]]; then
                ALLOWED=1
                break
            fi
        done
        if [[ "$ALLOWED" -eq 0 ]]; then
            echo '{"status": "error", "message": "Path not in allowed list"}' >&2
            exit 1
        fi
        # パストラバーサル防止
        if [[ "$TARGET" == *".."* ]]; then
            echo '{"status": "error", "message": "Path traversal not allowed"}' >&2
            exit 1
        fi
        du -sk "${TARGET}"/* 2>/dev/null | sort -rn | head -20 | awk '{printf "{\"path\":\"%s\",\"size_kb\":%s}\n", $2, $1}' | paste -sd,
        ;;
    mounts)
        # マウントポイント一覧
        findmnt -J 2>/dev/null || findmnt -l | tail -n +2 | awk '{printf "{\"target\":\"%s\",\"source\":\"%s\",\"fstype\":\"%s\",\"options\":\"%s\"}\n",$1,$2,$3,$4}' | paste -sd,
        ;;
    *)
        echo '{"status": "error", "message": "Unknown subcommand: df/du/mounts"}' >&2
        exit 1
        ;;
esac
