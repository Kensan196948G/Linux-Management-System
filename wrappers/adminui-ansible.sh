#!/bin/bash
# adminui-ansible.sh - Ansible連携ラッパースクリプト
#
# 用途: Ansibleコマンドを安全に実行するラッパー
# 権限: root 権限必要（ansible実行）
# 呼び出し: sudo /usr/local/sbin/adminui-ansible.sh <subcommand> [args...]
#
# セキュリティ原則:
# - allowlist 方式（許可サブコマンドのみ）
# - 入力検証必須（特殊文字拒否）
# - Playbook名はパターン検証（[a-zA-Z0-9_-]+.yml のみ）
# - 配列渡し（shell 展開防止）

set -euo pipefail

# ログ出力
log() {
    logger -t adminui-ansible -p user.info "$*"
    echo "[$(date -Iseconds)] $*" >&2
}

# エラーログ
error() {
    logger -t adminui-ansible -p user.err "ERROR: $*"
    echo "[$(date -Iseconds)] ERROR: $*" >&2
}

# 使用方法
usage() {
    echo "Usage: $0 <subcommand> [args...]" >&2
    echo "" >&2
    echo "Allowed subcommands:" >&2
    echo "  inventory-list           - インベントリ一覧表示" >&2
    echo "  ping-all                 - 全ホストにping" >&2
    echo "  run-playbook <name.yml>  - Playbook実行（承認フロー経由のみ）" >&2
    echo "  show-playbook <name.yml> - Playbookコンテンツ表示" >&2
    exit 1
}

# ===================================================================
# 許可サブコマンドリスト（allowlist）
# ===================================================================
ALLOWED_SUBCOMMANDS=("inventory-list" "ping-all" "run-playbook" "show-playbook")

# ===================================================================
# パス定義
# ===================================================================
ANSIBLE_HOSTS="/etc/ansible/hosts"
ANSIBLE_PLAYBOOK_DIR="/etc/ansible/playbooks"

# ===================================================================
# 禁止文字パターン
# ===================================================================
# shellcheck disable=SC2016
FORBIDDEN_CHARS='[;|&$()` ><*?{}[\]]'

# ===================================================================
# 入力検証
# ===================================================================

# 引数チェック
if [ $# -lt 1 ]; then
    error "Invalid number of arguments: expected at least 1, got $#"
    usage
fi

SUBCOMMAND="$1"
shift

# 実行前ログ
log "Ansible command requested: subcommand=$SUBCOMMAND, caller_uid=${SUDO_UID:-$UID}, caller_user=${SUDO_USER:-$USER}"

# 1. サブコマンド空文字チェック
if [ -z "$SUBCOMMAND" ]; then
    error "Subcommand is empty"
    exit 1
fi

# 2. サブコマンド長チェック
if [ ${#SUBCOMMAND} -gt 64 ]; then
    error "Subcommand too long: ${#SUBCOMMAND} characters (max 64)"
    exit 1
fi

# 3. サブコマンド特殊文字チェック
if [[ "$SUBCOMMAND" =~ $FORBIDDEN_CHARS ]]; then
    error "Forbidden character detected in subcommand: $SUBCOMMAND"
    log "SECURITY: Injection attempt detected - subcommand=$SUBCOMMAND, caller=${SUDO_USER:-$USER}"
    exit 1
fi

# 4. サブコマンド allowlist チェック
SUBCOMMAND_ALLOWED=false
for allowed in "${ALLOWED_SUBCOMMANDS[@]}"; do
    if [ "$SUBCOMMAND" = "$allowed" ]; then
        SUBCOMMAND_ALLOWED=true
        break
    fi
done

if [ "$SUBCOMMAND_ALLOWED" = false ]; then
    error "Subcommand not in allowlist: $SUBCOMMAND"
    log "SECURITY: Unauthorized subcommand attempt - subcommand=$SUBCOMMAND, caller=${SUDO_USER:-$USER}"
    echo "{\"status\": \"error\", \"message\": \"Subcommand not allowed: $SUBCOMMAND\"}"
    exit 1
fi

# ===================================================================
# Playbook名検証（run-playbook / show-playbook 用）
# ===================================================================
validate_playbook_name() {
    local name="$1"

    # 空文字チェック
    if [ -z "$name" ]; then
        error "Playbook name is empty"
        echo "{\"status\": \"error\", \"message\": \"Playbook name is required\"}"
        exit 1
    fi

    # 長さチェック
    if [ ${#name} -gt 128 ]; then
        error "Playbook name too long: ${#name} characters (max 128)"
        echo "{\"status\": \"error\", \"message\": \"Playbook name too long\"}"
        exit 1
    fi

    # パターン検証: [a-zA-Z0-9_-]+.yml のみ許可
    if [[ ! "$name" =~ ^[a-zA-Z0-9_-]+\.yml$ ]]; then
        error "Invalid playbook name format: $name"
        log "SECURITY: Invalid playbook name - name=$name, caller=${SUDO_USER:-$USER}"
        echo "{\"status\": \"error\", \"message\": \"Invalid playbook name: must match [a-zA-Z0-9_-]+.yml\"}"
        exit 1
    fi

    # パストラバーサル防止
    if [[ "$name" == *".."* ]]; then
        error "Path traversal attempt detected: $name"
        log "SECURITY: Path traversal attempt - name=$name, caller=${SUDO_USER:-$USER}"
        echo "{\"status\": \"error\", \"message\": \"Path traversal not allowed\"}"
        exit 1
    fi
}

# ===================================================================
# Ansibleコマンド存在確認
# ===================================================================
check_ansible() {
    if ! command -v ansible >/dev/null 2>&1; then
        echo "{\"status\": \"ansible_not_installed\", \"message\": \"Ansible is not installed\"}"
        exit 0
    fi
}

# ===================================================================
# サブコマンド実行
# ===================================================================

case "$SUBCOMMAND" in
    "inventory-list")
        log "Executing: inventory-list"
        check_ansible

        if [ ! -f "$ANSIBLE_HOSTS" ]; then
            echo "{\"status\": \"error\", \"message\": \"Ansible hosts file not found: $ANSIBLE_HOSTS\"}"
            exit 1
        fi

        # ansible-inventory でJSON出力
        if ansible-inventory -i "$ANSIBLE_HOSTS" --list 2>/dev/null; then
            log "inventory-list completed successfully"
        else
            error "inventory-list failed"
            echo "{\"status\": \"error\", \"message\": \"Failed to list inventory\"}"
            exit 1
        fi
        ;;

    "ping-all")
        log "Executing: ping-all"
        check_ansible

        if [ ! -f "$ANSIBLE_HOSTS" ]; then
            echo "{\"status\": \"error\", \"message\": \"Ansible hosts file not found: $ANSIBLE_HOSTS\"}"
            exit 1
        fi

        # ansible ping（--one-line で結果を1行に）
        ansible all -i "$ANSIBLE_HOSTS" -m ping --one-line 2>&1 || true
        log "ping-all completed"
        ;;

    "run-playbook")
        if [ $# -lt 1 ]; then
            error "run-playbook requires playbook name argument"
            echo "{\"status\": \"error\", \"message\": \"Playbook name required\"}"
            exit 1
        fi

        PLAYBOOK_NAME="$1"
        validate_playbook_name "$PLAYBOOK_NAME"

        log "Executing: run-playbook $PLAYBOOK_NAME"
        check_ansible

        PLAYBOOK_PATH="${ANSIBLE_PLAYBOOK_DIR}/${PLAYBOOK_NAME}"

        if [ ! -f "$PLAYBOOK_PATH" ]; then
            error "Playbook not found: $PLAYBOOK_PATH"
            echo "{\"status\": \"error\", \"message\": \"Playbook not found: $PLAYBOOK_NAME\"}"
            exit 1
        fi

        # Playbook実行（配列渡し、shell展開なし）
        if ansible-playbook -i "$ANSIBLE_HOSTS" "$PLAYBOOK_PATH" 2>&1; then
            log "run-playbook completed: $PLAYBOOK_NAME"
            echo "{\"status\": \"success\", \"playbook\": \"$PLAYBOOK_NAME\"}"
        else
            error "run-playbook failed: $PLAYBOOK_NAME"
            echo "{\"status\": \"error\", \"message\": \"Playbook execution failed: $PLAYBOOK_NAME\"}"
            exit 1
        fi
        ;;

    "show-playbook")
        if [ $# -lt 1 ]; then
            error "show-playbook requires playbook name argument"
            echo "{\"status\": \"error\", \"message\": \"Playbook name required\"}"
            exit 1
        fi

        PLAYBOOK_NAME="$1"
        validate_playbook_name "$PLAYBOOK_NAME"

        log "Executing: show-playbook $PLAYBOOK_NAME"

        PLAYBOOK_PATH="${ANSIBLE_PLAYBOOK_DIR}/${PLAYBOOK_NAME}"

        if [ ! -f "$PLAYBOOK_PATH" ]; then
            error "Playbook not found: $PLAYBOOK_PATH"
            echo "{\"status\": \"error\", \"message\": \"Playbook not found: $PLAYBOOK_NAME\"}"
            exit 1
        fi

        # catのみ（読み取り専用）
        cat "$PLAYBOOK_PATH"
        log "show-playbook completed: $PLAYBOOK_NAME"
        ;;

    *)
        error "Unknown subcommand: $SUBCOMMAND"
        echo "{\"status\": \"error\", \"message\": \"Unknown subcommand: $SUBCOMMAND\"}"
        exit 1
        ;;
esac
