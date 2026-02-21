#!/bin/bash
# adminui-group-add.sh - Create a new group
#
# Purpose: Create group with validation against FORBIDDEN_GROUPS and FORBIDDEN_USERNAMES
# Sudo Required: YES
# Risk Level: MEDIUM
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
# FORBIDDEN_USERNAMES (collision prevention, 100+ entries)
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

# Check FORBIDDEN_GROUPS
for forbidden in "${FORBIDDEN_GROUPS[@]}"; do
    if [[ "$GROUP_NAME" == "$forbidden" ]]; then
        security_log "Forbidden group creation attempt - group=$GROUP_NAME, caller=${SUDO_USER:-$USER}"
        echo "{\"status\":\"error\",\"message\":\"Group name is reserved: $GROUP_NAME\",\"timestamp\":\"$(date -Iseconds)\"}"
        exit 1
    fi
done

# Check FORBIDDEN_USERNAMES (collision prevention)
for forbidden in "${FORBIDDEN_USERNAMES[@]}"; do
    if [[ "$GROUP_NAME" == "$forbidden" ]]; then
        security_log "Group/username collision attempt - group=$GROUP_NAME, caller=${SUDO_USER:-$USER}"
        echo "{\"status\":\"error\",\"message\":\"Group name collides with reserved username: $GROUP_NAME\",\"timestamp\":\"$(date -Iseconds)\"}"
        exit 1
    fi
done

# Check group does not already exist
if getent group "$GROUP_NAME" >/dev/null 2>&1; then
    error_log "Group already exists: $GROUP_NAME"
    echo "{\"status\":\"error\",\"message\":\"Group already exists: $GROUP_NAME\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# ===================================================================
# Execution
# ===================================================================

log "Group creation requested: name=$GROUP_NAME, caller=${SUDO_USER:-$USER}"

# Execute groupadd via array (no shell expansion)
if ! groupadd "$GROUP_NAME" 2>/dev/null; then
    error_log "Failed to create group: $GROUP_NAME"
    echo "{\"status\":\"error\",\"message\":\"Failed to create group\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
fi

# Verify group created
GROUP_ENTRY=$(getent group "$GROUP_NAME" 2>/dev/null) || {
    error_log "Group creation verification failed: $GROUP_NAME"
    echo "{\"status\":\"error\",\"message\":\"Group creation verification failed\",\"timestamp\":\"$(date -Iseconds)\"}"
    exit 1
}

NEW_GID=$(echo "$GROUP_ENTRY" | cut -d: -f3)

# ===================================================================
# Output JSON
# ===================================================================

cat <<ENDJSON
{
  "status": "success",
  "message": "Group created successfully",
  "group": {
    "name": "$(json_escape "$GROUP_NAME")",
    "gid": $NEW_GID
  },
  "timestamp": "$(date -Iseconds)"
}
ENDJSON

log "Group created successfully: name=$GROUP_NAME, gid=$NEW_GID, caller=${SUDO_USER:-$USER}"

exit 0
