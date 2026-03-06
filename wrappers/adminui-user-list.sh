#!/bin/bash
# adminui-user-list.sh - List non-system users in JSON format
#
# Purpose: Read-only operation, list users with UID >= 1000 and < 60000
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
            echo '{"status":"error","message":"Forbidden character detected in '"$field_name"'"}' >&2
            exit 1
        fi
    done
}

# ===================================================================
# Allowlists
# ===================================================================

ALLOWED_SORTS=("username" "uid" "last_login")
ALLOWED_FILTER_LOCKED=("true" "false" "")

# ===================================================================
# Defaults
# ===================================================================

SORT_BY="username"
LIMIT=100
MAX_LIMIT=500
FILTER_LOCKED=""

# ===================================================================
# Argument parsing
# ===================================================================

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sort=*)
            SORT_BY="${1#*=}"
            shift
            ;;
        --limit=*)
            LIMIT="${1#*=}"
            shift
            ;;
        --filter-locked=*)
            FILTER_LOCKED="${1#*=}"
            shift
            ;;
        --username-filter=*)
            USERNAME_FILTER="${1#*=}"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--sort=username|uid|last_login] [--limit=N] [--filter-locked=true|false] [--username-filter=pattern]" >&2
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

# Validate sort key
check_forbidden_chars "$SORT_BY" "sort"
SORT_VALID=false
for allowed in "${ALLOWED_SORTS[@]}"; do
    if [[ "$SORT_BY" == "$allowed" ]]; then
        SORT_VALID=true
        break
    fi
done
if [[ "$SORT_VALID" == "false" ]]; then
    error_log "Invalid sort key: $SORT_BY"
    echo '{"status":"error","message":"Invalid sort key"}'
    exit 1
fi

# Validate limit
check_forbidden_chars "$LIMIT" "limit"
if [[ ! "$LIMIT" =~ ^[0-9]+$ ]]; then
    error_log "Invalid limit value: $LIMIT"
    echo '{"status":"error","message":"Invalid limit value"}'
    exit 1
fi
if [[ "$LIMIT" -lt 1 ]]; then
    error_log "Negative or zero limit: $LIMIT"
    echo '{"status":"error","message":"Invalid limit value"}'
    exit 1
fi
if [[ "$LIMIT" -gt "$MAX_LIMIT" ]]; then
    log "WARN: Requested limit ($LIMIT) exceeds max ($MAX_LIMIT), capping"
    LIMIT=$MAX_LIMIT
fi

# Validate filter-locked
if [[ -n "$FILTER_LOCKED" ]]; then
    check_forbidden_chars "$FILTER_LOCKED" "filter-locked"
    LOCK_VALID=false
    for allowed in "${ALLOWED_FILTER_LOCKED[@]}"; do
        if [[ "$FILTER_LOCKED" == "$allowed" ]]; then
            LOCK_VALID=true
            break
        fi
    done
    if [[ "$LOCK_VALID" == "false" ]]; then
        error_log "Invalid filter-locked value: $FILTER_LOCKED"
        echo '{"status":"error","message":"Invalid filter-locked value"}'
        exit 1
    fi
fi

# Validate username-filter if set
if [[ -n "${USERNAME_FILTER:-}" ]]; then
    check_forbidden_chars "$USERNAME_FILTER" "username-filter"
    if [[ ! "$USERNAME_FILTER" =~ ^[a-z0-9_-]+$ ]]; then
        error_log "Invalid username-filter: $USERNAME_FILTER"
        echo '{"status":"error","message":"Invalid username-filter format"}'
        exit 1
    fi
fi

log "User list requested: sort=$SORT_BY, limit=$LIMIT, filter_locked=$FILTER_LOCKED, caller=${SUDO_USER:-$USER}"

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
# Data collection
# ===================================================================

# Get user list from getent passwd
PASSWD_DATA=$(getent passwd 2>/dev/null) || {
    error_log "Failed to retrieve user list"
    echo '{"status":"error","message":"Failed to retrieve user list"}'
    exit 1
}

# Build user data array
declare -a USERS_JSON=()
TOTAL_USERS=0

while IFS=: read -r username _ uid gid gecos home shell; do
    # Filter: UID >= 1000 and < 60000
    if [[ "$uid" -lt 1000 ]] || [[ "$uid" -ge 60000 ]]; then
        continue
    fi

    # Username filter if specified
    if [[ -n "${USERNAME_FILTER:-}" ]]; then
        if [[ "$username" != *"$USERNAME_FILTER"* ]]; then
            continue
        fi
    fi

    # Get groups
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

    # Get lock status
    locked=false
    passwd_status=$(passwd -S "$username" 2>/dev/null | awk '{print $2}' || echo "")
    if [[ "$passwd_status" == "L" ]]; then
        locked=true
    fi

    # Apply locked filter
    if [[ -n "$FILTER_LOCKED" ]]; then
        if [[ "$FILTER_LOCKED" == "true" ]] && [[ "$locked" == "false" ]]; then
            continue
        fi
        if [[ "$FILTER_LOCKED" == "false" ]] && [[ "$locked" == "true" ]]; then
            continue
        fi
    fi

    # Get last login
    last_login_raw=$(lastlog -u "$username" 2>/dev/null | tail -1 || echo "")
    last_login="null"
    if [[ -n "$last_login_raw" ]]; then
        if echo "$last_login_raw" | grep -q "Never logged in"; then
            last_login="null"
        elif echo "$last_login_raw" | grep -q "\*\*Never"; then
            last_login="null"
        else
            # Extract date portion (skip username and terminal columns)
            login_date=$(echo "$last_login_raw" | awk '{for(i=4;i<=NF;i++) printf "%s ", $i}' | sed 's/ $//')
            if [[ -n "$login_date" ]]; then
                last_login="\"$(json_escape "$login_date")\""
            fi
        fi
    fi

    # Build JSON entry (password field is NEVER included)
    user_entry="{\"username\":\"$(json_escape "$username")\",\"uid\":$uid,\"gid\":$gid,\"gecos\":\"$(json_escape "$gecos")\",\"home\":\"$(json_escape "$home")\",\"shell\":\"$(json_escape "$shell")\",\"groups\":[$groups_json],\"locked\":$locked,\"last_login\":$last_login}"

    USERS_JSON+=("$user_entry")
    TOTAL_USERS=$((TOTAL_USERS + 1))
done <<< "$PASSWD_DATA"

# ===================================================================
# Sorting
# ===================================================================

# Sort the entries
SORTED_JSON=()
case "$SORT_BY" in
    username)
        # Sort by username (alphabetical)
        while IFS= read -r entry; do
            SORTED_JSON+=("$entry")
        done < <(printf '%s\n' "${USERS_JSON[@]}" | sort -t'"' -k4,4)
        ;;
    uid)
        # Sort by uid (numeric)
        while IFS= read -r entry; do
            SORTED_JSON+=("$entry")
        done < <(for entry in "${USERS_JSON[@]}"; do
            uid_val=$(echo "$entry" | grep -o '"uid":[0-9]*' | grep -o '[0-9]*')
            echo "$uid_val $entry"
        done | sort -n -k1,1 | sed 's/^[0-9]* //')
        ;;
    last_login)
        # Sort by last_login (entries with null last)
        while IFS= read -r entry; do
            SORTED_JSON+=("$entry")
        done < <(printf '%s\n' "${USERS_JSON[@]}" | sort -t'"' -k4,4)
        ;;
esac

# If sorting produced empty result, use original order
if [[ ${#SORTED_JSON[@]} -eq 0 ]]; then
    SORTED_JSON=("${USERS_JSON[@]}")
fi

# ===================================================================
# Output JSON
# ===================================================================

# Apply limit
RETURNED_USERS=0
if [[ "$LIMIT" -gt "${#SORTED_JSON[@]}" ]]; then
    RETURNED_USERS=${#SORTED_JSON[@]}
else
    RETURNED_USERS=$LIMIT
fi

echo "{"
echo "  \"status\": \"success\","
echo "  \"total_users\": $TOTAL_USERS,"
echo "  \"returned_users\": $RETURNED_USERS,"
echo "  \"sort_by\": \"$SORT_BY\","
echo "  \"users\": ["

for ((i=0; i<RETURNED_USERS; i++)); do
    if [[ $i -gt 0 ]]; then
        echo ","
    fi
    echo -n "    ${SORTED_JSON[$i]}"
done

echo ""
echo "  ],"
echo "  \"timestamp\": \"$(date -Iseconds)\""
echo "}"

log "User list retrieved: total=$TOTAL_USERS, returned=$RETURNED_USERS, caller=${SUDO_USER:-$USER}"

exit 0
