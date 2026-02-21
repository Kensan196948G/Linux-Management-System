#!/bin/bash
# adminui-user-delete.sh - Delete a user account
#
# Purpose: Delete user with safety checks, optional backup and force-logout
# Sudo Required: YES
# Risk Level: CRITICAL
# Approval Required: YES (Admin role ONLY)
# Logger tag: adminui-users

set -euo pipefail

# ===================================================================
# Logging
# ===================================================================

log() {
    logger -t adminui-users -p user.info "$*"
}

error_log() {
    logger -t adminui-users -p user.err "ERROR: $*"
}

security_log() {
    logger -t adminui-users -p user.warning "SECURITY: $*"
}

# ===================================================================
# Forbidden characters check (CLAUDE.md compliance)
# ===================================================================

FORBIDDEN_CHARS=(';' '|' '&' '$' '(' ')' '`' '>' '<' '*' '?' '{' '}' '[' ']')

check_forbidden_chars() {
    local input="$1"
    local field_name="$2"
    for char in "${FORBIDDEN_CHARS[@]}"; do
        if [[ "$input" == *"$char"* ]]; then
            security_log "Forbidden character detected - input=$field_name, caller=${SUDO_USER:-$USER}"
            echo "{\"status\":\"error\",\"message\":\"Forbidden character detected in $field_name\",\"timestamp\":\"$(date -Iseconds)\"}"
            exit 1
        fi
    done
}

# ===================================================================
# JSON escape helper
# ===================================================================

json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\t'/\\t}"
    printf '%s' "$s"
}

# ===================================================================
# Defaults
# ===================================================================

USERNAME=""
REMOVE_HOME=false
BACKUP_HOME=false
FORCE_LOGOUT=false

# ===================================================================
# Argument parsing
# ===================================================================

while [[ $# -gt 0 ]]; do
    case "$1" in
        --username=*)
            USERNAME="${1#*=}"
            shift
            ;;
        --remove-home)
            REMOVE_HOME=true
            shift
            ;;
        --backup-home)
            BACKUP_HOME=true
            shift
            ;;
        --force-logout)
            FORCE_LOGOUT=true
            shift
            ;;
        -h|--help)
            echo "Usage: sudo $0 --username=<name> [--remove-home] [--backup-home] [--force-logout]" >&2
            exit 0
            ;;
        *)
            error_log "Unknown argument: $1"
            echo "{\"status\":\"error\",\"message\":\"Unknown argument\",\"timestamp\":\"$(date -Iseconds)\"}"
            exit 1
            ;;
    esac
done

# ===================================================================
# Input validation
# ===================================================================

# --- Username ---
if [[ -z "$USERNAME" ]]; then
    error_log "Missing required argument: --username"
    echo "{\"status\":\"error\",\"message\":\"Missing required argument: --username\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

check_forbidden_chars "$USERNAME" "username"

if [[ ! "$USERNAME" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then
    error_log "Invalid username format: $USERNAME"
    echo "{\"status\":\"error\",\"message\":\"Invalid username format\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# User must exist
PASSWD_ENTRY=$(getent passwd "$USERNAME" 2>/dev/null) || {
    error_log "User not found: $USERNAME"
    echo "{\"status\":\"error\",\"message\":\"User not found: $USERNAME\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
}

# Get UID
USER_UID=$(echo "$PASSWD_ENTRY" | cut -d: -f3)
USER_HOME=$(echo "$PASSWD_ENTRY" | cut -d: -f6)

# UID range check - system user protection
if [[ "$USER_UID" -lt 1000 ]]; then
    security_log "System user deletion blocked - user=$USERNAME, uid=$USER_UID, caller=${SUDO_USER:-$USER}"
    echo "{\"status\":\"error\",\"message\":\"Cannot delete system user (UID < 1000)\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

if [[ "$USER_UID" -ge 60000 ]]; then
    security_log "Reserved user deletion blocked - user=$USERNAME, uid=$USER_UID, caller=${SUDO_USER:-$USER}"
    echo "{\"status\":\"error\",\"message\":\"Cannot delete reserved user (UID >= 60000)\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

log "User deletion requested: username=$USERNAME, uid=$USER_UID, remove_home=$REMOVE_HOME, backup=$BACKUP_HOME, caller=${SUDO_USER:-$USER}"

# ===================================================================
# Safety checks
# ===================================================================

# Check for active login sessions
SESSIONS_KILLED=0
active_sessions=$(who 2>/dev/null | grep -c "^${USERNAME} " || echo "0")

if [[ "$active_sessions" -gt 0 ]]; then
    log "WARN: User has active sessions: username=$USERNAME, sessions=$active_sessions"
    if [[ "$FORCE_LOGOUT" == "false" ]]; then
        error_log "User has active sessions and --force-logout not specified: $USERNAME"
        echo "{\"status\":\"error\",\"message\":\"User has active sessions. Use --force-logout\",\"timestamp\":\"$(date -Iseconds)\"}"
        exit 1
    else
        # Kill user sessions
        log "Force logout: killing sessions for $USERNAME"
        pkill -u "$USERNAME" 2>/dev/null || true
        SESSIONS_KILLED=$active_sessions
        # Brief pause to allow processes to terminate
        sleep 1
    fi
fi

# Check for running processes (warning only, does not block)
running_procs=$(ps -u "$USERNAME" --no-headers 2>/dev/null | wc -l || echo "0")
if [[ "$running_procs" -gt 0 ]]; then
    log "WARN: User has $running_procs running processes: username=$USERNAME"
fi

# ===================================================================
# Backup home directory (if requested)
# ===================================================================

BACKUP_PATH="null"
HOME_BACKED_UP=false

if [[ "$BACKUP_HOME" == "true" ]] && [[ -d "$USER_HOME" ]]; then
    BACKUP_DIR="/var/backups/adminui/users"

    # Create backup directory if it doesn't exist
    if ! mkdir -p "$BACKUP_DIR" 2>/dev/null; then
        error_log "Failed to create backup directory: $BACKUP_DIR"
        echo "{\"status\":\"error\",\"message\":\"Failed to create backup directory\",\"timestamp\":\"$(date -Iseconds)\"}"
        exit 1
    fi

    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="${BACKUP_DIR}/${USERNAME}_${TIMESTAMP}.tar.gz"

    if tar -czf "$BACKUP_FILE" -C "$(dirname "$USER_HOME")" "$(basename "$USER_HOME")" 2>/dev/null; then
        BACKUP_SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || echo "0")
        log "Home directory backed up: user=$USERNAME, path=$BACKUP_FILE, size=$BACKUP_SIZE"
        BACKUP_PATH="\"$(json_escape "$BACKUP_FILE")\""
        HOME_BACKED_UP=true
    else
        error_log "Failed to backup home directory for: $USERNAME"
        echo "{\"status\":\"error\",\"message\":\"Failed to backup home directory\",\"timestamp\":\"$(date -Iseconds)\"}"
        exit 1
    fi
fi

# ===================================================================
# Delete user
# ===================================================================

# Build userdel command as array
USERDEL_CMD=("userdel")
if [[ "$REMOVE_HOME" == "true" ]]; then
    USERDEL_CMD+=("-r")
fi
USERDEL_CMD+=("$USERNAME")

if ! "${USERDEL_CMD[@]}" 2>/dev/null; then
    error_log "Failed to delete user: $USERNAME"
    echo "{\"status\":\"error\",\"message\":\"Failed to delete user\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# Verify deletion
if id "$USERNAME" >/dev/null 2>&1; then
    error_log "User deletion verification failed: $USERNAME still exists"
    echo "{\"status\":\"error\",\"message\":\"User deletion verification failed\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# ===================================================================
# Output JSON
# ===================================================================

cat <<ENDJSON
{
  "status": "success",
  "message": "User deleted successfully",
  "deleted_user": {
    "username": "$(json_escape "$USERNAME")",
    "uid": $USER_UID,
    "home_removed": $REMOVE_HOME,
    "home_backed_up": $HOME_BACKED_UP,
    "backup_path": $BACKUP_PATH,
    "sessions_killed": $SESSIONS_KILLED
  },
  "timestamp": "$(date -Iseconds)"
}
ENDJSON

log "User deleted successfully: username=$USERNAME, uid=$USER_UID, home_removed=$REMOVE_HOME, caller=${SUDO_USER:-$USER}"

exit 0
