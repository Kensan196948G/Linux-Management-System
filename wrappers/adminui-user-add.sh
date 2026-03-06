#!/bin/bash
# adminui-user-add.sh - Create a new user account
#
# Purpose: Create user with validated inputs and pre-hashed password
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
# FORBIDDEN_USERNAMES (100+ entries from constants.py)
# ===================================================================

FORBIDDEN_USERNAMES=(
    # System critical
    'root' 'bin' 'daemon' 'sys' 'sync' 'games' 'man' 'lp'
    'mail' 'news' 'uucp' 'proxy' 'backup' 'list' 'irc'
    'gnats' 'nobody' '_apt' 'messagebus'
    # Service accounts
    'www-data' 'sshd' 'systemd-network' 'systemd-resolve'
    'systemd-timesync' 'syslog' 'uuidd'
    'tcpdump' 'landscape' 'pollinate' 'fwupd-refresh'
    'tss' 'usbmux' 'dnsmasq' 'avahi' 'speech-dispatcher'
    'pulse' 'rtkit' 'colord' 'geoclue' 'saned' 'whoopsie'
    # Database services
    'postgres' 'mysql' 'mongodb' 'redis' 'memcached'
    'elasticsearch' 'cassandra' 'couchdb'
    # Web servers
    'nginx' 'apache' 'httpd' 'lighttpd'
    # Application servers
    'tomcat' 'jetty' 'node' 'pm2'
    # Monitoring & logging
    'nagios' 'zabbix' 'prometheus' 'grafana' 'logstash'
    'kibana' 'fluentd' 'telegraf'
    # Container & orchestration
    'docker' 'containerd' 'kubernetes' 'k8s'
    # Message queues
    'rabbitmq' 'kafka' 'activemq'
    # Mail
    'postfix' 'dovecot' 'exim' 'sendmail'
    # Admin
    'admin' 'administrator' 'sudo' 'wheel' 'operator'
    'adm' 'staff' 'kmem' 'dialout' 'cdrom' 'floppy'
    'audio' 'video' 'plugdev' 'netdev' 'lxd'
    # Application specific
    'adminui' 'svc-adminui' 'webmin' 'cockpit'
    'usermin' 'virtualmin' 'cloudmin'
)

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
# ALLOWED_SHELLS (from spec)
# ===================================================================

ALLOWED_SHELLS=("/bin/bash" "/bin/sh" "/usr/bin/zsh" "/usr/sbin/nologin" "/bin/false")

# ===================================================================
# Defaults
# ===================================================================

USERNAME=""
GROUPS_INPUT=""
SHELL_PATH="/bin/bash"
HOME_DIR=""
GECOS=""

# ===================================================================
# Argument parsing
# ===================================================================

while [[ $# -gt 0 ]]; do
    case "$1" in
        --username=*)
            USERNAME="${1#*=}"
            shift
            ;;
        --groups=*)
            GROUPS_INPUT="${1#*=}"
            shift
            ;;
        --shell=*)
            SHELL_PATH="${1#*=}"
            shift
            ;;
        --home=*)
            HOME_DIR="${1#*=}"
            shift
            ;;
        --gecos=*)
            GECOS="${1#*=}"
            shift
            ;;
        -h|--help)
            echo "Usage: echo \"\$HASH\" | sudo $0 --username=<name> --groups=<g1,g2> --shell=<path> [--home=<path>] [--gecos=<comment>]" >&2
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
    error_log "Empty password hash"
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

# Check FORBIDDEN_USERNAMES
for forbidden in "${FORBIDDEN_USERNAMES[@]}"; do
    if [[ "$USERNAME" == "$forbidden" ]]; then
        security_log "Forbidden username attempt - user=$USERNAME, caller=${SUDO_USER:-$USER}"
        echo "{\"status\":\"error\",\"message\":\"Username is reserved: $USERNAME\",\"timestamp\":\"$(date -Iseconds)\"}"
        exit 1
    fi
done

# Check user does not already exist
if getent passwd "$USERNAME" >/dev/null 2>&1; then
    error_log "User already exists: $USERNAME"
    echo "{\"status\":\"error\",\"message\":\"User already exists: $USERNAME\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# --- Groups ---
declare -a USER_GROUPS=()
if [[ -n "$GROUPS_INPUT" ]]; then
    check_forbidden_chars "$GROUPS_INPUT" "groups"
    IFS=',' read -ra USER_GROUPS <<< "$GROUPS_INPUT"

    # Limit max groups
    if [[ ${#USER_GROUPS[@]} -gt 10 ]]; then
        error_log "Too many groups specified: ${#USER_GROUPS[@]} (max 10)"
        echo "{\"status\":\"error\",\"message\":\"Maximum 10 groups allowed\",\"timestamp\":\"$(date -Iseconds)\"}"
        exit 1
    fi

    for grp in "${USER_GROUPS[@]}"; do
        # Validate group name format
        if [[ ! "$grp" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then
            error_log "Invalid group name format: $grp"
            echo "{\"status\":\"error\",\"message\":\"Invalid group name format: $grp\",\"timestamp\":\"$(date -Iseconds)\"}"
            exit 1
        fi

        # Check FORBIDDEN_GROUPS
        for forbidden in "${FORBIDDEN_GROUPS[@]}"; do
            if [[ "$grp" == "$forbidden" ]]; then
                security_log "Forbidden group attempt - group=$grp, user=$USERNAME, caller=${SUDO_USER:-$USER}"
                echo "{\"status\":\"error\",\"message\":\"Group is forbidden: $grp\",\"timestamp\":\"$(date -Iseconds)\"}"
                exit 1
            fi
        done

        # Check group exists (allow "users" default group)
        if ! getent group "$grp" >/dev/null 2>&1; then
            error_log "Group does not exist: $grp"
            echo "{\"status\":\"error\",\"message\":\"Group does not exist: $grp\",\"timestamp\":\"$(date -Iseconds)\"}"
            exit 1
        fi
    done
fi

# --- Shell ---
check_forbidden_chars "$SHELL_PATH" "shell"
SHELL_VALID=false
for allowed in "${ALLOWED_SHELLS[@]}"; do
    if [[ "$SHELL_PATH" == "$allowed" ]]; then
        SHELL_VALID=true
        break
    fi
done
if [[ "$SHELL_VALID" == "false" ]]; then
    error_log "Shell not allowed: $SHELL_PATH"
    echo "{\"status\":\"error\",\"message\":\"Shell not allowed: $SHELL_PATH\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# --- Home directory ---
if [[ -z "$HOME_DIR" ]]; then
    HOME_DIR="/home/$USERNAME"
fi

check_forbidden_chars "$HOME_DIR" "home"

# Must start with /home/
if [[ ! "$HOME_DIR" =~ ^/home/ ]]; then
    error_log "Invalid home directory (must start with /home/): $HOME_DIR"
    echo "{\"status\":\"error\",\"message\":\"Invalid home directory: $HOME_DIR\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# No path traversal
if [[ "$HOME_DIR" == *".."* ]]; then
    security_log "Path traversal attempt in home directory: $HOME_DIR, caller=${SUDO_USER:-$USER}"
    echo "{\"status\":\"error\",\"message\":\"Invalid home directory: path traversal detected\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# Must be exactly /home/<name> (no deeper nesting)
home_basename="${HOME_DIR#/home/}"
if [[ "$home_basename" == *"/"* ]]; then
    error_log "Home directory too deep (must be /home/<name>): $HOME_DIR"
    echo "{\"status\":\"error\",\"message\":\"Invalid home directory: must be /home/<name>\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# Must not already exist
if [[ -d "$HOME_DIR" ]]; then
    error_log "Home directory already exists: $HOME_DIR"
    echo "{\"status\":\"error\",\"message\":\"Home directory already exists: $HOME_DIR\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# --- GECOS ---
if [[ -n "$GECOS" ]]; then
    check_forbidden_chars "$GECOS" "gecos"
    if [[ ! "$GECOS" =~ ^[a-zA-Z0-9\ ._-]{0,100}$ ]]; then
        error_log "Invalid GECOS format: $GECOS"
        echo "{\"status\":\"error\",\"message\":\"Invalid GECOS format\",\"timestamp\":\"$(date -Iseconds)\"}"
        exit 1
    fi
fi

# --- Password hash format (bcrypt) ---
if [[ ! "$PASSWORD_HASH" =~ ^\$2[aby]\$[0-9]{2}\$.{53}$ ]]; then
    error_log "Invalid password hash format"
    echo "{\"status\":\"error\",\"message\":\"Invalid password hash format\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# ===================================================================
# Execution
# ===================================================================

log "User creation requested: username=$USERNAME, groups=$GROUPS_INPUT, shell=$SHELL_PATH, home=$HOME_DIR, caller=${SUDO_USER:-$USER}"

# Build useradd command as array (no shell expansion)
USERADD_CMD=("useradd" "-m" "-s" "$SHELL_PATH" "-d" "$HOME_DIR")

if [[ ${#USER_GROUPS[@]} -gt 0 ]]; then
    USERADD_CMD+=("-G" "$GROUPS_INPUT")
fi

if [[ -n "$GECOS" ]]; then
    USERADD_CMD+=("-c" "$GECOS")
fi

USERADD_CMD+=("$USERNAME")

# Execute useradd
if ! "${USERADD_CMD[@]}" 2>/dev/null; then
    error_log "Failed to create user: $USERNAME"
    echo "{\"status\":\"error\",\"message\":\"Failed to create user\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# Set password via chpasswd -e (pre-hashed, via stdin)
if ! printf '%s:%s\n' "$USERNAME" "$PASSWORD_HASH" | chpasswd -e 2>/dev/null; then
    error_log "Failed to set password for: $USERNAME"
    # Attempt cleanup: remove the user we just created
    userdel -r "$USERNAME" 2>/dev/null || true
    echo "{\"status\":\"error\",\"message\":\"Failed to set password\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# Verify user created
if ! id "$USERNAME" >/dev/null 2>&1; then
    error_log "User creation verification failed: $USERNAME"
    echo "{\"status\":\"error\",\"message\":\"User creation verification failed\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# Get created user info
NEW_UID=$(id -u "$USERNAME" 2>/dev/null)
NEW_GID=$(id -g "$USERNAME" 2>/dev/null)
NEW_GROUPS=$(id -Gn "$USERNAME" 2>/dev/null || echo "")

# Build groups JSON
groups_json=""
first_group=true
for g in $NEW_GROUPS; do
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
  "message": "User created successfully",
  "user": {
    "username": "$(json_escape "$USERNAME")",
    "uid": $NEW_UID,
    "gid": $NEW_GID,
    "home": "$(json_escape "$HOME_DIR")",
    "shell": "$(json_escape "$SHELL_PATH")",
    "groups": [$groups_json]
  },
  "timestamp": "$(date -Iseconds)"
}
ENDJSON

log "User created successfully: username=$USERNAME, uid=$NEW_UID, groups=$NEW_GROUPS, caller=${SUDO_USER:-$USER}"

exit 0
