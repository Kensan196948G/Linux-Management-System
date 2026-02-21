#!/bin/bash
# adminui-user-passwd.sh - Change a user's password
#
# Purpose: Set pre-hashed (bcrypt) password for a user via stdin
# Sudo Required: YES
# Risk Level: HIGH
# Approval Required: YES (Approver or Admin role)
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

# ===================================================================
# Argument parsing
# ===================================================================

while [[ $# -gt 0 ]]; do
    case "$1" in
        --username=*)
            USERNAME="${1#*=}"
            shift
            ;;
        -h|--help)
            echo "Usage: echo \"\$HASH\" | sudo $0 --username=<name>" >&2
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
# Read password hash from stdin
# ===================================================================

PASSWORD_HASH=""
if [[ ! -t 0 ]]; then
    read -r PASSWORD_HASH || true
else
    error_log "No password hash provided on stdin"
    echo "{\"status\":\"error\",\"message\":\"Password hash must be provided via stdin\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

if [[ -z "$PASSWORD_HASH" ]]; then
    error_log "Empty password hash on stdin"
    echo "{\"status\":\"error\",\"message\":\"Password hash must not be empty\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

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

# UID range check
if [[ "$USER_UID" -lt 1000 ]]; then
    security_log "System user password change blocked - user=$USERNAME, uid=$USER_UID, caller=${SUDO_USER:-$USER}"
    echo "{\"status\":\"error\",\"message\":\"Cannot change password for system user (UID < 1000)\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

if [[ "$USER_UID" -ge 60000 ]]; then
    security_log "Reserved user password change blocked - user=$USERNAME, uid=$USER_UID, caller=${SUDO_USER:-$USER}"
    echo "{\"status\":\"error\",\"message\":\"Cannot change password for reserved user (UID >= 60000)\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# --- Password hash format (bcrypt) ---
# NOTE: bcrypt hash contains $ characters, so we do NOT run forbidden chars check on the hash
if [[ ! "$PASSWORD_HASH" =~ ^\$2[aby]\$[0-9]{2}\$.{53}$ ]]; then
    error_log "Invalid password hash format"
    echo "{\"status\":\"error\",\"message\":\"Invalid password hash format\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# ===================================================================
# Execution
# ===================================================================

log "Password change requested: username=$USERNAME, uid=$USER_UID, caller=${SUDO_USER:-$USER}"

# Set password via chpasswd -e (pre-hashed, via stdin)
if ! printf '%s:%s\n' "$USERNAME" "$PASSWORD_HASH" | chpasswd -e 2>/dev/null; then
    error_log "Failed to change password for: $USERNAME"
    echo "{\"status\":\"error\",\"message\":\"Failed to change password\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# Verify password change (check status)
passwd_status_code=""
passwd_status_line=$(passwd -S "$USERNAME" 2>/dev/null || echo "")
if [[ -n "$passwd_status_line" ]]; then
    passwd_status_code=$(echo "$passwd_status_line" | awk '{print $2}')
fi

password_status="set"
if [[ "$passwd_status_code" == "L" ]]; then
    password_status="locked"
elif [[ "$passwd_status_code" == "NP" ]]; then
    password_status="no_password"
fi

# ===================================================================
# Output JSON
# ===================================================================

cat <<ENDJSON
{
  "status": "success",
  "message": "Password changed successfully",
  "user": {
    "username": "$(json_escape "$USERNAME")",
    "uid": $USER_UID,
    "password_status": "$password_status"
  },
  "timestamp": "$(date -Iseconds)"
}
ENDJSON

log "Password changed successfully: username=$USERNAME, uid=$USER_UID, caller=${SUDO_USER:-$USER}"

exit 0
