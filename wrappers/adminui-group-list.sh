#!/bin/bash
# adminui-group-list.sh - List non-system groups in JSON format
#
# Purpose: Read-only operation, list groups with GID >= 1000 and < 60000
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
# Allowlists
# ===================================================================

ALLOWED_SORTS=("name" "gid" "member_count")

# ===================================================================
# Defaults
# ===================================================================

SORT_BY="name"
LIMIT=100
MAX_LIMIT=500

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
        -h|--help)
            echo "Usage: $0 [--sort=name|gid|member_count] [--limit=N]" >&2
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

log "Group list requested: sort=$SORT_BY, limit=$LIMIT, caller=${SUDO_USER:-$USER}"

# ===================================================================
# Data collection
# ===================================================================

# Get group list from getent group
GROUP_DATA=$(getent group 2>/dev/null) || {
    error_log "Failed to retrieve group list"
    echo '{"status":"error","message":"Failed to retrieve group list"}'
    exit 1
}

# Get passwd data for cross-referencing primary groups
PASSWD_DATA=$(getent passwd 2>/dev/null) || {
    error_log "Failed to retrieve user list for primary group cross-reference"
    echo '{"status":"error","message":"Failed to retrieve user data"}'
    exit 1
}

# Build group data array
declare -a GROUPS_JSON=()
TOTAL_GROUPS=0

while IFS=: read -r groupname _password gid members; do
    # Filter: GID >= 1000 and < 60000
    if [[ "$gid" -lt 1000 ]] || [[ "$gid" -ge 60000 ]]; then
        continue
    fi

    # Build members list
    # Combine explicit members from /etc/group with users who have this as primary group
    declare -a all_members=()

    # Explicit members (comma-separated)
    if [[ -n "$members" ]]; then
        IFS=',' read -ra explicit_members <<< "$members"
        for m in "${explicit_members[@]}"; do
            if [[ -n "$m" ]]; then
                all_members+=("$m")
            fi
        done
    fi

    # Users with this group as primary (check passwd data by GID)
    while IFS=: read -r pw_username _ _ pw_gid _ _ _; do
        if [[ "$pw_gid" == "$gid" ]]; then
            # Check not already in list
            already_listed=false
            for existing in "${all_members[@]+"${all_members[@]}"}"; do
                if [[ "$existing" == "$pw_username" ]]; then
                    already_listed=true
                    break
                fi
            done
            if [[ "$already_listed" == "false" ]]; then
                all_members+=("$pw_username")
            fi
        fi
    done <<< "$PASSWD_DATA"

    # Build members JSON
    members_json=""
    first_member=true
    for m in "${all_members[@]+"${all_members[@]}"}"; do
        if [[ "$first_member" == "true" ]]; then
            members_json="\"$(json_escape "$m")\""
            first_member=false
        else
            members_json="$members_json,\"$(json_escape "$m")\""
        fi
    done

    member_count=${#all_members[@]}

    group_entry="{\"name\":\"$(json_escape "$groupname")\",\"gid\":$gid,\"members\":[$members_json],\"member_count\":$member_count}"

    GROUPS_JSON+=("$group_entry")
    TOTAL_GROUPS=$((TOTAL_GROUPS + 1))
done <<< "$GROUP_DATA"

# ===================================================================
# Sorting
# ===================================================================

SORTED_JSON=()
if [[ ${#GROUPS_JSON[@]} -gt 0 ]]; then
    case "$SORT_BY" in
        name)
            # Sort by group name (alphabetical)
            while IFS= read -r entry; do
                SORTED_JSON+=("$entry")
            done < <(printf '%s\n' "${GROUPS_JSON[@]}" | sort -t'"' -k4,4)
            ;;
        gid)
            # Sort by GID (numeric)
            while IFS= read -r entry; do
                SORTED_JSON+=("$entry")
            done < <(for entry in "${GROUPS_JSON[@]}"; do
                gid_val=$(echo "$entry" | grep -o '"gid":[0-9]*' | grep -o '[0-9]*')
                echo "$gid_val $entry"
            done | sort -n -k1,1 | sed 's/^[0-9]* //')
            ;;
        member_count)
            # Sort by member_count (numeric, descending)
            while IFS= read -r entry; do
                SORTED_JSON+=("$entry")
            done < <(for entry in "${GROUPS_JSON[@]}"; do
                mc_val=$(echo "$entry" | grep -o '"member_count":[0-9]*' | grep -o '[0-9]*')
                echo "$mc_val $entry"
            done | sort -rn -k1,1 | sed 's/^[0-9]* //')
            ;;
    esac
fi

# If sorting produced empty result, use original order
if [[ ${#SORTED_JSON[@]} -eq 0 ]] && [[ ${#GROUPS_JSON[@]} -gt 0 ]]; then
    SORTED_JSON=("${GROUPS_JSON[@]}")
fi

# ===================================================================
# Output JSON
# ===================================================================

# Apply limit
RETURNED_GROUPS=0
if [[ ${#SORTED_JSON[@]} -eq 0 ]]; then
    RETURNED_GROUPS=0
elif [[ "$LIMIT" -gt "${#SORTED_JSON[@]}" ]]; then
    RETURNED_GROUPS=${#SORTED_JSON[@]}
else
    RETURNED_GROUPS=$LIMIT
fi

echo "{"
echo "  \"status\": \"success\","
echo "  \"total_groups\": $TOTAL_GROUPS,"
echo "  \"returned_groups\": $RETURNED_GROUPS,"
echo "  \"sort_by\": \"$SORT_BY\","
echo "  \"groups\": ["

for ((i=0; i<RETURNED_GROUPS; i++)); do
    if [[ $i -gt 0 ]]; then
        echo ","
    fi
    echo -n "    ${SORTED_JSON[$i]}"
done

echo ""
echo "  ],"
echo "  \"timestamp\": \"$(date -Iseconds)\""
echo "}"

log "Group list retrieved: total=$TOTAL_GROUPS, returned=$RETURNED_GROUPS, caller=${SUDO_USER:-$USER}"

exit 0
