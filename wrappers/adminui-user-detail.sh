#!/bin/bash
# adminui-user-detail.sh - Retrieve detailed information for a single user
#
# Purpose: Read-only operation, query user by username or UID
# Sudo Required: NO
# Risk Level: LOW
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
            security_log "Forbidden character in $field_name, caller=${SUDO_USER:-$USER}"
            echo "{\"status\":\"error\",\"message\":\"Forbidden character detected in $field_name\"}" >&2
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
TARGET_UID=""

# ===================================================================
# Argument parsing
# ===================================================================

while [[ $# -gt 0 ]]; do
    case "$1" in
        --username=*)
            USERNAME="${1#*=}"
            shift
            ;;
        --uid=*)
            TARGET_UID="${1#*=}"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 --username=<name> | --uid=<number>" >&2
            exit 0
            ;;
        *)
            error_log "Unknown argument: $1"
            echo '{"status":"error","message":"Unknown argument"}' >&2
            exit 1
            ;;
    esac
done

# ===================================================================
# Input validation
# ===================================================================

# Exactly one of --username or --uid must be provided
if [[ -z "$USERNAME" ]] && [[ -z "$TARGET_UID" ]]; then
    error_log "Neither --username nor --uid provided"
    echo '{"status":"error","message":"Either --username or --uid required"}'
    exit 1
fi

if [[ -n "$USERNAME" ]] && [[ -n "$TARGET_UID" ]]; then
    error_log "Both --username and --uid provided"
    echo '{"status":"error","message":"Only one of --username or --uid allowed"}'
    exit 1
fi

# Validate username format
if [[ -n "$USERNAME" ]]; then
    check_forbidden_chars "$USERNAME" "username"
    if [[ ! "$USERNAME" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then
        error_log "Invalid username format: $USERNAME"
        echo '{"status":"error","message":"Invalid username format"}'
        exit 1
    fi
fi

# Validate UID format
if [[ -n "$TARGET_UID" ]]; then
    check_forbidden_chars "$TARGET_UID" "uid"
    if [[ ! "$TARGET_UID" =~ ^[0-9]+$ ]]; then
        error_log "Invalid UID format: $TARGET_UID"
        echo '{"status":"error","message":"Invalid UID format"}'
        exit 1
    fi
fi

# ===================================================================
# User lookup
# ===================================================================

if [[ -n "$USERNAME" ]]; then
    # Lookup by username
    PASSWD_ENTRY=$(getent passwd "$USERNAME" 2>/dev/null) || {
        error_log "User not found: $USERNAME"
        echo '{"status":"error","message":"User not found"}'
        exit 1
    }
else
    # Lookup by UID
    # Range check first
    if [[ "$TARGET_UID" -lt 1000 ]]; then
        security_log "System user query blocked - uid=$TARGET_UID, caller=${SUDO_USER:-$USER}"
        echo '{"status":"error","message":"Cannot query system user (UID < 1000)"}'
        exit 1
    fi
    if [[ "$TARGET_UID" -ge 60000 ]]; then
        security_log "Reserved UID query blocked - uid=$TARGET_UID, caller=${SUDO_USER:-$USER}"
        echo '{"status":"error","message":"Cannot query reserved user (UID >= 60000)"}'
        exit 1
    fi
    PASSWD_ENTRY=$(getent passwd "$TARGET_UID" 2>/dev/null) || {
        error_log "User not found: UID=$TARGET_UID"
        echo '{"status":"error","message":"User not found"}'
        exit 1
    }
fi

# Parse passwd entry
IFS=: read -r username _password uid gid gecos home shell <<< "$PASSWD_ENTRY"

# UID range check (system user protection)
if [[ "$uid" -lt 1000 ]]; then
    security_log "System user query blocked - user=$username, uid=$uid, caller=${SUDO_USER:-$USER}"
    echo '{"status":"error","message":"Cannot query system user (UID < 1000)"}'
    exit 1
fi

if [[ "$uid" -ge 60000 ]]; then
    security_log "Reserved user query blocked - user=$username, uid=$uid, caller=${SUDO_USER:-$USER}"
    echo '{"status":"error","message":"Cannot query reserved user (UID >= 60000)"}'
    exit 1
fi

log "User detail requested: user=$username, uid=$uid, caller=${SUDO_USER:-$USER}"

# ===================================================================
# Data collection
# ===================================================================

# Primary group name
primary_group=$(id -gn "$username" 2>/dev/null || echo "")

# All groups
groups_list=$(id -Gn "$username" 2>/dev/null || echo "")
groups_json=""
if [[ -n "$groups_list" ]]; then
    first_group=true
    for g in $groups_list; do
        if [[ "$first_group" == "true" ]]; then
            groups_json="\"$(json_escape "$g")\""
            first_group=false
        else
            groups_json="$groups_json,\"$(json_escape "$g")\""
        fi
    done
fi

# Lock status and password status
locked=false
password_status="no_password"
passwd_status_line=$(passwd -S "$username" 2>/dev/null || echo "")
if [[ -n "$passwd_status_line" ]]; then
    status_code=$(echo "$passwd_status_line" | awk '{print $2}')
    case "$status_code" in
        P) locked=false; password_status="set" ;;
        L) locked=true; password_status="locked" ;;
        NP) locked=false; password_status="no_password" ;;
        *) locked=false; password_status="no_password" ;;
    esac
fi

# Last login
last_login="null"
last_login_raw=$(lastlog -u "$username" 2>/dev/null | tail -1 || echo "")
if [[ -n "$last_login_raw" ]]; then
    if echo "$last_login_raw" | grep -q "Never logged in"; then
        last_login="null"
    elif echo "$last_login_raw" | grep -q "\*\*Never"; then
        last_login="null"
    elif echo "$last_login_raw" | grep -q "^Username"; then
        # Header line only, no data
        last_login="null"
    else
        login_date=$(echo "$last_login_raw" | awk '{for(i=4;i<=NF;i++) printf "%s ", $i}' | sed 's/ $//')
        if [[ -n "$login_date" ]]; then
            last_login="\"$(json_escape "$login_date")\""
        fi
    fi
fi

# Last password change (from chage -l)
last_password_change="null"
chage_output=$(chage -l "$username" 2>/dev/null || echo "")
if [[ -n "$chage_output" ]]; then
    lpw=$(echo "$chage_output" | grep "^Last password change" | sed 's/^Last password change[[:space:]]*:[[:space:]]*//')
    if [[ -n "$lpw" ]] && [[ "$lpw" != "never" ]] && [[ "$lpw" != "password must be changed" ]]; then
        last_password_change="\"$(json_escape "$lpw")\""
    fi
fi

# Account expiration
account_expires="null"
if [[ -n "$chage_output" ]]; then
    exp=$(echo "$chage_output" | grep "^Account expires" | sed 's/^Account expires[[:space:]]*:[[:space:]]*//')
    if [[ -n "$exp" ]] && [[ "$exp" != "never" ]]; then
        account_expires="\"$(json_escape "$exp")\""
    fi
fi

# Home directory existence and size
home_dir_exists=false
home_dir_size_kb="null"
if [[ -d "$home" ]]; then
    home_dir_exists=true
    size_output=$(du -sk "$home" 2>/dev/null | awk '{print $1}' || echo "")
    if [[ -n "$size_output" ]] && [[ "$size_output" =~ ^[0-9]+$ ]]; then
        home_dir_size_kb=$size_output
    fi
fi

# Running processes count
running_processes=0
proc_count=$(ps -u "$username" --no-headers 2>/dev/null | wc -l || echo "0")
if [[ "$proc_count" =~ ^[0-9]+$ ]]; then
    running_processes=$proc_count
fi

# ===================================================================
# Output JSON
# ===================================================================

cat <<ENDJSON
{
  "status": "success",
  "user": {
    "username": "$(json_escape "$username")",
    "uid": $uid,
    "gid": $gid,
    "primary_group": "$(json_escape "$primary_group")",
    "gecos": "$(json_escape "$gecos")",
    "home": "$(json_escape "$home")",
    "shell": "$(json_escape "$shell")",
    "groups": [$groups_json],
    "locked": $locked,
    "password_status": "$password_status",
    "last_login": $last_login,
    "last_password_change": $last_password_change,
    "account_expires": $account_expires,
    "home_dir_exists": $home_dir_exists,
    "home_dir_size_kb": $home_dir_size_kb,
    "running_processes": $running_processes
  },
  "timestamp": "$(date -Iseconds)"
}
ENDJSON

log "User detail retrieved: user=$username, uid=$uid, caller=${SUDO_USER:-$USER}"

exit 0
