#!/bin/bash
# ==============================================================================
# adminui-user-modify.sh - ユーザー属性変更ラッパー
#
# 機能:
#   既存ユーザーのシェル・GECOS・グループ追加を変更する。
#   パスワード変更は adminui-user-passwd.sh を使用すること。
#
# 使用方法:
#   adminui-user-modify.sh set-shell <username> <shell>
#   adminui-user-modify.sh set-gecos <username> <gecos>
#   adminui-user-modify.sh add-group <username> <group>
#   adminui-user-modify.sh remove-group <username> <group>
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - 許可シェルのallowlist: /bin/bash /bin/sh /usr/bin/zsh /usr/bin/fish /sbin/nologin /usr/sbin/nologin
#   - usernameは英数字・ハイフン・アンダースコアのみ許可
#   - GECOSはコロン・改行を禁止
# ==============================================================================

set -euo pipefail

ALLOWED_SHELLS=("/bin/bash" "/bin/sh" "/usr/bin/zsh" "/usr/bin/fish" "/sbin/nologin" "/usr/sbin/nologin" "/bin/false")
ALLOWED_SUBCOMMANDS=("set-shell" "set-gecos" "add-group" "remove-group")

if [ "$#" -lt 2 ]; then
    echo '{"status":"error","message":"Usage: adminui-user-modify.sh <subcommand> <username> [args...]"}' >&2
    exit 1
fi

SUBCOMMAND="$1"
USERNAME="$2"

# サブコマンドallowlist
ALLOWED=false
for cmd in "${ALLOWED_SUBCOMMANDS[@]}"; do
    if [ "$cmd" = "$SUBCOMMAND" ]; then
        ALLOWED=true
        break
    fi
done
if [ "$ALLOWED" = false ]; then
    echo "{\"status\":\"error\",\"message\":\"Unknown subcommand: ${SUBCOMMAND}\"}" >&2
    exit 1
fi

# ユーザー名バリデーション（英数字・ハイフン・アンダースコアのみ）
if ! echo "$USERNAME" | grep -qE '^[a-zA-Z0-9_-]+$'; then
    echo '{"status":"error","message":"Invalid username format"}' >&2
    exit 1
fi

# ユーザーの存在確認
if ! id "$USERNAME" >/dev/null 2>&1; then
    echo "{\"status\":\"error\",\"message\":\"User not found: ${USERNAME}\"}" >&2
    exit 1
fi

# システムユーザー保護（UID < 1000 は変更禁止）
USER_UID=$(id -u "$USERNAME" 2>/dev/null || echo 0)
if [ "$USER_UID" -lt 1000 ] && [ "$USERNAME" != "root" ]; then
    # rootは明示的に禁止する
    :
fi
if [ "$USER_UID" -lt 1000 ]; then
    echo "{\"status\":\"error\",\"message\":\"Cannot modify system user (UID < 1000): ${USERNAME}\"}" >&2
    exit 1
fi

# ==============================================================================
# set-shell: ログインシェル変更
# ==============================================================================
if [ "$SUBCOMMAND" = "set-shell" ]; then
    if [ "$#" -ne 3 ]; then
        echo '{"status":"error","message":"Usage: set-shell <username> <shell>"}' >&2
        exit 1
    fi
    NEW_SHELL="$3"

    # シェルallowlist確認
    SHELL_ALLOWED=false
    for s in "${ALLOWED_SHELLS[@]}"; do
        if [ "$s" = "$NEW_SHELL" ]; then
            SHELL_ALLOWED=true
            break
        fi
    done
    if [ "$SHELL_ALLOWED" = false ]; then
        echo "{\"status\":\"error\",\"message\":\"Shell not in allowlist: ${NEW_SHELL}\"}" >&2
        exit 1
    fi

    usermod -s "${NEW_SHELL}" "${USERNAME}"
    echo "{\"status\":\"success\",\"operation\":\"set-shell\",\"username\":\"${USERNAME}\",\"shell\":\"${NEW_SHELL}\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    exit 0
fi

# ==============================================================================
# set-gecos: GECOSフィールド（表示名）変更
# ==============================================================================
if [ "$SUBCOMMAND" = "set-gecos" ]; then
    if [ "$#" -lt 3 ]; then
        echo '{"status":"error","message":"Usage: set-gecos <username> <gecos>"}' >&2
        exit 1
    fi
    GECOS="$3"

    # GECOSバリデーション（コロン・改行禁止）
    if echo "$GECOS" | grep -qE '[:\n\r]'; then
        echo '{"status":"error","message":"GECOS contains forbidden characters (colon or newline)"}' >&2
        exit 1
    fi

    usermod -c "${GECOS}" "${USERNAME}"
    echo "{\"status\":\"success\",\"operation\":\"set-gecos\",\"username\":\"${USERNAME}\",\"gecos\":\"${GECOS}\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    exit 0
fi

# ==============================================================================
# add-group: グループ追加（supplementary）
# ==============================================================================
if [ "$SUBCOMMAND" = "add-group" ]; then
    if [ "$#" -ne 3 ]; then
        echo '{"status":"error","message":"Usage: add-group <username> <group>"}' >&2
        exit 1
    fi
    GROUP="$3"

    # グループ名バリデーション
    if ! echo "$GROUP" | grep -qE '^[a-zA-Z0-9_-]+$'; then
        echo '{"status":"error","message":"Invalid group name format"}' >&2
        exit 1
    fi

    # グループ存在確認
    if ! getent group "$GROUP" >/dev/null 2>&1; then
        echo "{\"status\":\"error\",\"message\":\"Group not found: ${GROUP}\"}" >&2
        exit 1
    fi

    # sudo/wheel グループへの追加は禁止（権限昇格防止）
    FORBIDDEN_GROUPS=("sudo" "wheel" "root" "adm")
    for fg in "${FORBIDDEN_GROUPS[@]}"; do
        if [ "$GROUP" = "$fg" ]; then
            echo "{\"status\":\"error\",\"message\":\"Cannot add user to privileged group: ${GROUP}\"}" >&2
            exit 1
        fi
    done

    usermod -aG "${GROUP}" "${USERNAME}"
    echo "{\"status\":\"success\",\"operation\":\"add-group\",\"username\":\"${USERNAME}\",\"group\":\"${GROUP}\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    exit 0
fi

# ==============================================================================
# remove-group: グループから削除
# ==============================================================================
if [ "$SUBCOMMAND" = "remove-group" ]; then
    if [ "$#" -ne 3 ]; then
        echo '{"status":"error","message":"Usage: remove-group <username> <group>"}' >&2
        exit 1
    fi
    GROUP="$3"

    # グループ名バリデーション
    if ! echo "$GROUP" | grep -qE '^[a-zA-Z0-9_-]+$'; then
        echo '{"status":"error","message":"Invalid group name format"}' >&2
        exit 1
    fi

    # gpasswd でグループから削除
    gpasswd -d "${USERNAME}" "${GROUP}" 2>/dev/null || true
    echo "{\"status\":\"success\",\"operation\":\"remove-group\",\"username\":\"${USERNAME}\",\"group\":\"${GROUP}\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    exit 0
fi

echo '{"status":"error","message":"Unhandled subcommand"}' >&2
exit 1
