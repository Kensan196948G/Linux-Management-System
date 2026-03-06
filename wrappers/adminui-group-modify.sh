#!/bin/bash
# adminui-group-modify.sh - Modify group membership (add/remove users)
#
# Purpose: Add or remove users from groups with security validation
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
# FORBIDDEN_GROUPS (35+ entries from constants.py)
# ===================================================================

FORBIDDEN_GROUPS=(
    # Critical (privilege escalation risk)
    'root' 'sudo' 'wheel' 'adm' 'staff'
    # System
    'bin' 'daemon' 'sys' 'disk' 'lp' 'dialout'
    'cdrom' 'floppy' 'tape' 'audio' 'video'
    'plugdev' 'netdev' 'scanner' 'bluetooth'
    'input' 'kvm' 'render' 'sgx'
    # Container & virtualization
    'docker' 'lxd' 'libvirt' 'libvirt-qemu'
    # Network & security
    'ssl-cert' 'shadow' 'utmp' 'tty' 'kmem'
    # systemd
    'systemd-journal' 'systemd-network' 'systemd-resolve'
    'systemd-timesync' 'systemd-coredump'
    # Hardware
    'i2c' 'gpio' 'spi'
)

# ===================================================================
# Allowlists
# ===================================================================

ALLOWED_ACTIONS=("add" "remove")

# ===================================================================
# Defaults
# ===================================================================

GROUP_NAME=""
ACTION=""
TARGET_USER=""

# ===================================================================
# Argument parsing
# ===================================================================

while [[ $# -gt 0 ]]; do
    case "$1" in
        --group=*)
            GROUP_NAME="${1#*=}"
            shift
            ;;
        --action=*)
            ACTION="${1#*=}"
            shift
            ;;
        --user=*)
            TARGET_USER="${1#*=}"
            shift
            ;;
        -h|--help)
            echo "Usage: sudo $0 --group=<name> --action=<add|remove> --user=<username>" >&2
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

# --- Required arguments ---
if [[ -z "$GROUP_NAME" ]]; then
    error_log "Missing required argument: --group"
    echo "{\"status\":\"error\",\"message\":\"Missing required argument: --group\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

if [[ -z "$ACTION" ]]; then
    error_log "Missing required argument: --action"
    echo "{\"status\":\"error\",\"message\":\"Missing required argument: --action\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

if [[ -z "$TARGET_USER" ]]; then
    error_log "Missing required argument: --user"
    echo "{\"status\":\"error\",\"message\":\"Missing required argument: --user\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# --- Forbidden chars ---
check_forbidden_chars "$GROUP_NAME" "group"
check_forbidden_chars "$ACTION" "action"
check_forbidden_chars "$TARGET_USER" "user"

# --- Action allowlist ---
ACTION_VALID=false
for allowed in "${ALLOWED_ACTIONS[@]}"; do
    if [[ "$ACTION" == "$allowed" ]]; then
        ACTION_VALID=true
        break
    fi
done
if [[ "$ACTION_VALID" == "false" ]]; then
    error_log "Invalid action: $ACTION"
    echo "{\"status\":\"error\",\"message\":\"Invalid action: must be 'add' or 'remove'\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# --- Group name format ---
if [[ ! "$GROUP_NAME" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then
    error_log "Invalid group name format: $GROUP_NAME"
    echo "{\"status\":\"error\",\"message\":\"Invalid group name format\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# --- Username format ---
if [[ ! "$TARGET_USER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then
    error_log "Invalid username format: $TARGET_USER"
    echo "{\"status\":\"error\",\"message\":\"Invalid username format\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# --- FORBIDDEN_GROUPS check ---
for forbidden in "${FORBIDDEN_GROUPS[@]}"; do
    if [[ "$GROUP_NAME" == "$forbidden" ]]; then
        security_log "Forbidden group modification blocked - group=$GROUP_NAME, action=$ACTION, user=$TARGET_USER, caller=${SUDO_USER:-$USER}"
        echo "{\"status\":\"error\",\"message\":\"Group is forbidden: $GROUP_NAME\",\"timestamp\":\"$(date -Iseconds)\"}"
        exit 1
    fi
done

# --- Group must exist ---
GROUP_ENTRY=$(getent group "$GROUP_NAME" 2>/dev/null) || {
    error_log "Group not found: $GROUP_NAME"
    echo "{\"status\":\"error\",\"message\":\"Group not found: $GROUP_NAME\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
}

GROUP_GID=$(echo "$GROUP_ENTRY" | cut -d: -f3)

# GID range check
if [[ "$GROUP_GID" -lt 1000 ]]; then
    security_log "System group modification blocked - group=$GROUP_NAME, gid=$GROUP_GID, caller=${SUDO_USER:-$USER}"
    echo "{\"status\":\"error\",\"message\":\"Cannot modify system group (GID < 1000)\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

if [[ "$GROUP_GID" -ge 60000 ]]; then
    security_log "Reserved group modification blocked - group=$GROUP_NAME, gid=$GROUP_GID, caller=${SUDO_USER:-$USER}"
    echo "{\"status\":\"error\",\"message\":\"Cannot modify reserved group (GID >= 60000)\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# --- User must exist ---
if ! getent passwd "$TARGET_USER" >/dev/null 2>&1; then
    error_log "User not found: $TARGET_USER"
    echo "{\"status\":\"error\",\"message\":\"User not found: $TARGET_USER\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

USER_UID=$(id -u "$TARGET_USER" 2>/dev/null)

# UID range check
if [[ "$USER_UID" -lt 1000 ]]; then
    security_log "System user group modification blocked - user=$TARGET_USER, uid=$USER_UID, caller=${SUDO_USER:-$USER}"
    echo "{\"status\":\"error\",\"message\":\"Cannot modify groups for system user (UID < 1000)\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

if [[ "$USER_UID" -ge 60000 ]]; then
    security_log "Reserved user group modification blocked - user=$TARGET_USER, uid=$USER_UID, caller=${SUDO_USER:-$USER}"
    echo "{\"status\":\"error\",\"message\":\"Cannot modify groups for reserved user (UID >= 60000)\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# Get current group membership
CURRENT_GROUPS=$(id -Gn "$TARGET_USER" 2>/dev/null || echo "")

# ===================================================================
# Execution
# ===================================================================

log "Group modification requested: group=$GROUP_NAME, action=$ACTION, user=$TARGET_USER, caller=${SUDO_USER:-$USER}"

if [[ "$ACTION" == "add" ]]; then
    # Check user is not already a member
    for grp in $CURRENT_GROUPS; do
        if [[ "$grp" == "$GROUP_NAME" ]]; then
            error_log "User already in group: $TARGET_USER in $GROUP_NAME"
            echo "{\"status\":\"error\",\"message\":\"User is already a member of group: $GROUP_NAME\",\"timestamp\":\"$(date -Iseconds)\"}"
            exit 1
        fi
    done

    # Execute: usermod -aG <groupname> <username>
    if ! usermod -aG "$GROUP_NAME" "$TARGET_USER" 2>/dev/null; then
        error_log "Failed to add user to group: $TARGET_USER -> $GROUP_NAME"
        echo "{\"status\":\"error\",\"message\":\"Failed to add user to group\",\"timestamp\":\"$(date -Iseconds)\"}"
        exit 1
    fi

    MESSAGE="User added to group"

elif [[ "$ACTION" == "remove" ]]; then
    # Check user IS a member
    is_member=false
    for grp in $CURRENT_GROUPS; do
        if [[ "$grp" == "$GROUP_NAME" ]]; then
            is_member=true
            break
        fi
    done
    if [[ "$is_member" == "false" ]]; then
        error_log "User not in group: $TARGET_USER not in $GROUP_NAME"
        echo "{\"status\":\"error\",\"message\":\"User is not a member of group: $GROUP_NAME\",\"timestamp\":\"$(date -Iseconds)\"}"
        exit 1
    fi

    # Check group is NOT user's primary group
    PRIMARY_GID=$(id -g "$TARGET_USER" 2>/dev/null)
    if [[ "$PRIMARY_GID" == "$GROUP_GID" ]]; then
        error_log "Cannot remove user from primary group: $TARGET_USER primary=$GROUP_NAME"
        echo "{\"status\":\"error\",\"message\":\"Cannot remove user from their primary group\",\"timestamp\":\"$(date -Iseconds)\"}"
        exit 1
    fi

    # Execute: gpasswd -d <username> <groupname>
    if ! gpasswd -d "$TARGET_USER" "$GROUP_NAME" 2>/dev/null; then
        error_log "Failed to remove user from group: $TARGET_USER from $GROUP_NAME"
        echo "{\"status\":\"error\",\"message\":\"Failed to remove user from group\",\"timestamp\":\"$(date -Iseconds)\"}"
        exit 1
    fi

    MESSAGE="User removed from group"
fi

# Get updated groups
UPDATED_GROUPS=$(id -Gn "$TARGET_USER" 2>/dev/null || echo "")

# Build groups JSON array
groups_json=""
first_group=true
for g in $UPDATED_GROUPS; do
    if [[ "$first_group" == "true" ]]; then
        groups_json="\"$(json_escape "$g")\""
        first_group=false
    else
        groups_json="$groups_json,\"$(json_escape "$g")\""
    fi
done

# ===================================================================
# Output JSON
# ===================================================================

cat <<ENDJSON
{
  "status": "success",
  "message": "$MESSAGE",
  "details": {
    "username": "$(json_escape "$TARGET_USER")",
    "group": "$(json_escape "$GROUP_NAME")",
    "action": "$ACTION",
    "current_groups": [$groups_json]
  },
  "timestamp": "$(date -Iseconds)"
}
ENDJSON

log "Group modification successful: group=$GROUP_NAME, action=$ACTION, user=$TARGET_USER, caller=${SUDO_USER:-$USER}"

exit 0
