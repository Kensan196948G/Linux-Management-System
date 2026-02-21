#!/bin/bash
# adminui-group-delete.sh - Delete a group
#
# Purpose: Delete group with safety checks (primary group, GID range)
# Sudo Required: YES
# Risk Level: HIGH
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

GROUP_NAME=""

# ===================================================================
# Argument parsing
# ===================================================================

while [[ $# -gt 0 ]]; do
    case "$1" in
        --name=*)
            GROUP_NAME="${1#*=}"
            shift
            ;;
        -h|--help)
            echo "Usage: sudo $0 --name=<groupname>" >&2
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

if [[ -z "$GROUP_NAME" ]]; then
    error_log "Missing required argument: --name"
    echo "{\"status\":\"error\",\"message\":\"Missing required argument: --name\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

check_forbidden_chars "$GROUP_NAME" "name"

# Group name format
if [[ ! "$GROUP_NAME" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then
    error_log "Invalid group name format: $GROUP_NAME"
    echo "{\"status\":\"error\",\"message\":\"Invalid group name format\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# Group must exist
GROUP_ENTRY=$(getent group "$GROUP_NAME" 2>/dev/null) || {
    error_log "Group not found: $GROUP_NAME"
    echo "{\"status\":\"error\",\"message\":\"Group not found: $GROUP_NAME\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
}

# Parse group entry
GROUP_GID=$(echo "$GROUP_ENTRY" | cut -d: -f3)
GROUP_MEMBERS=$(echo "$GROUP_ENTRY" | cut -d: -f4)

# GID range check - system group protection
if [[ "$GROUP_GID" -lt 1000 ]]; then
    security_log "System group deletion blocked - group=$GROUP_NAME, gid=$GROUP_GID, caller=${SUDO_USER:-$USER}"
    echo "{\"status\":\"error\",\"message\":\"Cannot delete system group (GID < 1000)\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

if [[ "$GROUP_GID" -ge 60000 ]]; then
    security_log "Reserved group deletion blocked - group=$GROUP_NAME, gid=$GROUP_GID, caller=${SUDO_USER:-$USER}"
    echo "{\"status\":\"error\",\"message\":\"Cannot delete reserved group (GID >= 60000)\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# Check no users have this as primary group
PRIMARY_USERS=$(getent passwd 2>/dev/null | awk -F: -v gid="$GROUP_GID" '$4 == gid {print $1}' || echo "")
if [[ -n "$PRIMARY_USERS" ]]; then
    # Build list of dependent users
    user_list=$(echo "$PRIMARY_USERS" | tr '\n' ',' | sed 's/,$//')
    error_log "Group is primary group for users: $user_list"
    echo "{\"status\":\"error\",\"message\":\"Cannot delete group: it is the primary group for users: $user_list\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# Count supplementary members
HAD_MEMBERS=0
if [[ -n "$GROUP_MEMBERS" ]]; then
    IFS=',' read -ra members_arr <<< "$GROUP_MEMBERS"
    HAD_MEMBERS=${#members_arr[@]}
fi

# ===================================================================
# Execution
# ===================================================================

log "Group deletion requested: name=$GROUP_NAME, gid=$GROUP_GID, members=$HAD_MEMBERS, caller=${SUDO_USER:-$USER}"

# Execute groupdel via array (no shell expansion)
if ! groupdel "$GROUP_NAME" 2>/dev/null; then
    error_log "Failed to delete group: $GROUP_NAME"
    echo "{\"status\":\"error\",\"message\":\"Failed to delete group\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# Verify deletion
if getent group "$GROUP_NAME" >/dev/null 2>&1; then
    error_log "Group deletion verification failed: $GROUP_NAME still exists"
    echo "{\"status\":\"error\",\"message\":\"Group deletion verification failed\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# ===================================================================
# Output JSON
# ===================================================================

cat <<ENDJSON
{
  "status": "success",
  "message": "Group deleted successfully",
  "deleted_group": {
    "name": "$(json_escape "$GROUP_NAME")",
    "gid": $GROUP_GID,
    "had_members": $HAD_MEMBERS
  },
  "timestamp": "$(date -Iseconds)"
}
ENDJSON

log "Group deleted successfully: name=$GROUP_NAME, gid=$GROUP_GID, caller=${SUDO_USER:-$USER}"

exit 0
