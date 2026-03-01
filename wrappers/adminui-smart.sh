#!/usr/bin/env bash
# ==============================================================================
# adminui-smart.sh - SMART Drive Status ラッパー（読み取り専用）
#
# 機能:
#   smartctl を使用してディスクの SMART 情報を取得する。
#   全操作は読み取り専用。
#
# 使用方法:
#   adminui-smart.sh <subcommand> [disk]
#
# サブコマンド:
#   list         - SMART 対応ディスク一覧 (lsblk)
#   info <disk>  - ディスク詳細情報 (smartctl -i)
#   health <disk>- ディスク健全性 (smartctl -H)
#   tests        - テスト結果一覧 (smartctl -l selftest)
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは直接実行
#   - ディスク名 allowlist: /dev/sd[a-z], /dev/nvme[0-9]n[0-9]
#   - 許可サブコマンドのみ実行（allowlist方式）
#   - smartctl 未インストール時は {"status":"unavailable"} を返す
# ==============================================================================

set -euo pipefail

ALLOWED_SUBCOMMANDS=("list" "info" "health" "tests")

error_json() {
    printf '{"status": "error", "message": "%s"}\n' "$1" >&2
    exit 1
}

if [ "$#" -lt 1 ]; then
    error_json "Usage: adminui-smart.sh <subcommand> [disk]"
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

# ディスク名バリデーション関数
# allowlist: /dev/sd[a-z], /dev/nvme[0-9]n[0-9]
validate_disk() {
    local disk="$1"
    if [[ "$disk" =~ ^/dev/sd[a-z]$ ]] || [[ "$disk" =~ ^/dev/nvme[0-9]n[0-9]$ ]]; then
        return 0
    fi
    error_json "Invalid disk name: $disk. Allowed: /dev/sd[a-z], /dev/nvme[0-9]n[0-9]"
}

# smartctl 存在チェック
SMARTCTL_BIN=""
if command -v smartctl >/dev/null 2>&1; then
    SMARTCTL_BIN="smartctl"
fi

# lsblk の存在チェック
LSBLK_BIN=""
if command -v lsblk >/dev/null 2>&1; then
    LSBLK_BIN="lsblk"
fi

case "$SUBCOMMAND" in
    list)
        # SMART 対応ディスク一覧（lsblk 使用）
        if [ -z "$LSBLK_BIN" ]; then
            printf '{"status": "unavailable", "message": "lsblk not found", "disks": [], "timestamp": "%s"}\n' "$TIMESTAMP"
            exit 0
        fi

        LSBLK_JSON=$("$LSBLK_BIN" -d -J -o NAME,SIZE,TYPE,TRAN,MODEL 2>/dev/null || echo '{"blockdevices":[]}')
        LSBLK_ESCAPED=$(printf '%s' "$LSBLK_JSON" | python3 -c "import sys,json; data=sys.stdin.read(); json.loads(data); print(data)" 2>/dev/null || echo '{"blockdevices":[]}')
        SMARTCTL_AVAILABLE="false"
        if [ -n "$SMARTCTL_BIN" ]; then
            SMARTCTL_AVAILABLE="true"
        fi

        printf '{"status": "success", "smartctl_available": %s, "lsblk": %s, "timestamp": "%s"}\n' \
            "$SMARTCTL_AVAILABLE" "$LSBLK_ESCAPED" "$TIMESTAMP"
        ;;

    info)
        # ディスク詳細情報
        if [ "$#" -lt 2 ]; then
            error_json "Usage: adminui-smart.sh info <disk>"
        fi
        DISK="$2"
        validate_disk "$DISK"

        if [ -z "$SMARTCTL_BIN" ]; then
            printf '{"status": "unavailable", "message": "smartctl not found", "timestamp": "%s"}\n' "$TIMESTAMP"
            exit 0
        fi

        INFO_OUTPUT=$("$SMARTCTL_BIN" -i "$DISK" 2>&1 || true)
        INFO_ESCAPED=$(printf '%s' "$INFO_OUTPUT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || printf '"%s"' "$INFO_OUTPUT")
        printf '{"status": "success", "disk": "%s", "info_raw": %s, "timestamp": "%s"}\n' \
            "$DISK" "$INFO_ESCAPED" "$TIMESTAMP"
        ;;

    health)
        # ディスク健全性チェック
        if [ "$#" -lt 2 ]; then
            error_json "Usage: adminui-smart.sh health <disk>"
        fi
        DISK="$2"
        validate_disk "$DISK"

        if [ -z "$SMARTCTL_BIN" ]; then
            printf '{"status": "unavailable", "message": "smartctl not found", "timestamp": "%s"}\n' "$TIMESTAMP"
            exit 0
        fi

        HEALTH_OUTPUT=$("$SMARTCTL_BIN" -H "$DISK" 2>&1 || true)

        # PASSED / FAILED 判定
        HEALTH_STATUS="unknown"
        if printf '%s' "$HEALTH_OUTPUT" | grep -q "PASSED"; then
            HEALTH_STATUS="PASSED"
        elif printf '%s' "$HEALTH_OUTPUT" | grep -q "FAILED"; then
            HEALTH_STATUS="FAILED"
        fi

        HEALTH_ESCAPED=$(printf '%s' "$HEALTH_OUTPUT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || printf '"%s"' "$HEALTH_OUTPUT")
        printf '{"status": "success", "disk": "%s", "health": "%s", "output_raw": %s, "timestamp": "%s"}\n' \
            "$DISK" "$HEALTH_STATUS" "$HEALTH_ESCAPED" "$TIMESTAMP"
        ;;

    tests)
        # selftest ログ一覧（全ディスク対象）
        if [ -z "$SMARTCTL_BIN" ]; then
            printf '{"status": "unavailable", "message": "smartctl not found", "tests": [], "timestamp": "%s"}\n' "$TIMESTAMP"
            exit 0
        fi

        # 全ブロックデバイスのテスト結果を収集
        TESTS_JSON="[]"
        if [ -n "$LSBLK_BIN" ]; then
            DISK_LIST=$("$LSBLK_BIN" -d -n -o NAME,TYPE 2>/dev/null | grep -E "^(sd[a-z]|nvme[0-9]n[0-9]) +disk" | awk '{print "/dev/" $1}' || true)
            RESULTS=""
            FIRST=true
            while IFS= read -r DISK; do
                [ -z "$DISK" ] && continue
                TEST_OUT=$("$SMARTCTL_BIN" -l selftest "$DISK" 2>&1 || true)
                TEST_ESCAPED=$(printf '%s' "$TEST_OUT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || printf '"%s"' "$TEST_OUT")
                ENTRY=$(printf '{"disk": "%s", "selftest_raw": %s}' "$DISK" "$TEST_ESCAPED")
                if "$FIRST"; then
                    RESULTS="$ENTRY"
                    FIRST=false
                else
                    RESULTS="$RESULTS,$ENTRY"
                fi
            done <<< "$DISK_LIST"
            if [ -n "$RESULTS" ]; then
                TESTS_JSON="[$RESULTS]"
            fi
        fi

        printf '{"status": "success", "tests": %s, "timestamp": "%s"}\n' "$TESTS_JSON" "$TIMESTAMP"
        ;;

    *)
        error_json "Unexpected subcommand: $SUBCOMMAND"
        ;;
esac
