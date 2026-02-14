# Users & Groups Management - Allowlist / Denylist Policy

**Created**: 2026-02-14
**Author**: users-planner (v03-planning-team)
**Module**: Users & Groups Management (v0.3)
**Security Level**: HIGH
**Related**: [users-groups-design.md](../architecture/users-groups-design.md), [users-groups-threat-analysis.md](./users-groups-threat-analysis.md)

---

## Policy Principles

1. **Allowlist-first**: Only explicitly permitted values are accepted
2. **Deny by default**: Anything not in the allowlist is rejected
3. **Multi-layer enforcement**: Every rule is checked at minimum 2 layers (API + Wrapper)
4. **Immutable at runtime**: Lists cannot be modified by API or WebUI; changes require code deployment and human approval

---

## 1. Username Policy

### 1.1 Allowed Username Pattern (Allowlist)

```
Pattern: ^[a-z_][a-z0-9_-]{0,31}$

Rules:
- Must start with lowercase letter or underscore
- May contain: lowercase letters (a-z), digits (0-9), underscore (_), hyphen (-)
- Minimum length: 1 character
- Maximum length: 32 characters
- Case-sensitive: only lowercase allowed
```

**Validation layers**:

| Layer | Implementation | Pattern |
|-------|---------------|---------|
| Frontend | HTML5 `pattern` attribute | `pattern="[a-z_][a-z0-9_-]{0,31}"` |
| API (Pydantic) | `Field(pattern=...)` + `@field_validator` | `re.match(r'^[a-z_][a-z0-9_-]{0,31}$', v)` |
| Wrapper (Bash) | `[[ =~ ]]` regex match | `^[a-z_][a-z0-9_-]{0,31}$` |

### 1.2 Forbidden Usernames (Denylist)

All usernames below are **permanently forbidden** and cannot be created through the WebUI under any circumstances. Modification of this list requires human approval (see [Threat T5](./users-groups-threat-analysis.md#t5)).

#### System Accounts (Ubuntu Default)

```python
FORBIDDEN_USERNAMES_SYSTEM = [
    "root", "bin", "daemon", "sys", "sync", "games", "man", "lp",
    "mail", "news", "uucp", "proxy", "www-data", "backup", "list",
    "irc", "gnats", "nobody", "systemd-network", "systemd-resolve",
    "systemd-timesync", "systemd-bus-proxy", "systemd-coredump",
    "messagebus", "syslog", "_apt", "uuidd", "dnsmasq", "avahi",
    "avahi-autoipd", "speech-dispatcher", "fwupd-refresh", "sshd",
    "polkitd", "rtkit", "colord", "pulse", "hplip",
    "gnome-initial-setup", "gdm", "geoclue",
    "tss", "tcpdump", "kernoops", "whoopsie",
]
```

#### Service Accounts

```python
FORBIDDEN_USERNAMES_SERVICE = [
    "postgres", "mysql", "redis", "nginx", "apache", "apache2",
    "tomcat", "elasticsearch", "kibana", "grafana", "prometheus",
    "jenkins", "gitlab-runner", "docker", "mongod", "mongodb",
    "rabbitmq", "memcache", "memcached", "couchdb", "influxdb",
    "telegraf", "logstash", "filebeat", "metricbeat",
    "vault", "consul", "nomad", "etcd",
    "haproxy", "squid", "bind", "named", "ntp", "chrony",
    "postfix", "dovecot", "cyrus", "exim",
    "git", "svn", "hg",
    "node", "nodejs", "python", "ruby", "php",
    "ftp", "ftpuser", "sftp",
]
```

#### Administrative / Reserved Names

```python
FORBIDDEN_USERNAMES_ADMIN = [
    "admin", "administrator", "sudo", "wheel", "staff",
    "operator", "manager", "supervisor", "sysadmin", "superuser",
    "test", "testing", "guest", "anonymous", "public",
    "default", "user", "system", "service", "daemon",
]
```

#### Application-Specific Reserved Names

```python
FORBIDDEN_USERNAMES_APP = [
    "adminui", "adminui-service", "adminui-worker",
    "webmin", "cockpit", "cpanel",
]
```

#### Combined Forbidden List

```python
FORBIDDEN_USERNAMES = (
    FORBIDDEN_USERNAMES_SYSTEM +
    FORBIDDEN_USERNAMES_SERVICE +
    FORBIDDEN_USERNAMES_ADMIN +
    FORBIDDEN_USERNAMES_APP
)
# Total: 100+ entries
```

### 1.3 Additional Username Checks

```python
# In addition to the forbidden list, these runtime checks apply:
USERNAME_ADDITIONAL_CHECKS = {
    "existence_check": "getent passwd {username} must return empty",
    "case_collision": "case-insensitive comparison against existing users",
    "max_total_users": 100,  # Maximum managed users (configurable, requires restart)
}
```

---

## 2. Group Policy

### 2.1 Allowed Group Name Pattern (Allowlist)

```
Pattern: ^[a-z_][a-z0-9_-]{0,31}$

Rules:
- Identical to username pattern
- Must start with lowercase letter or underscore
- May contain: lowercase letters, digits, underscore, hyphen
- Minimum length: 1 character
- Maximum length: 32 characters
```

### 2.2 Forbidden Groups (Denylist)

Groups listed below **cannot be assigned** to any user through the WebUI. Attempting to add a user to any of these groups triggers a security alert.

#### Privilege Escalation Groups (CRITICAL)

```python
FORBIDDEN_GROUPS_CRITICAL = [
    "root",           # root group - full system access
    "sudo",           # sudo access - command execution as root
    "wheel",          # sudo alternative on some distributions
    "admin",          # Administrative access
]
```

#### System Access Groups (HIGH)

```python
FORBIDDEN_GROUPS_SYSTEM = [
    "adm",            # System log access (/var/log)
    "disk",           # Raw disk device access
    "shadow",         # /etc/shadow read access
    "staff",          # Local system modifications without root
    "kmem",           # Kernel memory access
    "tty",            # Terminal device access
]
```

#### Container / Virtualization Groups (HIGH)

```python
FORBIDDEN_GROUPS_CONTAINER = [
    "docker",         # Docker socket access = root equivalent
    "lxd",            # LXD container management = root equivalent
    "libvirt",        # Virtual machine management
    "kvm",            # KVM hypervisor access
    "vboxusers",      # VirtualBox management
    "podman",         # Podman container management
]
```

#### Network / Service Groups (MEDIUM)

```python
FORBIDDEN_GROUPS_NETWORK = [
    "netdev",         # Network device management
    "dialout",        # Modem/serial access
    "bluetooth",      # Bluetooth device access
    "wireshark",      # Network packet capture
]
```

#### Systemd / D-Bus Groups (MEDIUM)

```python
FORBIDDEN_GROUPS_SYSTEMD = [
    "systemd-journal",   # Journal log access
    "systemd-network",   # Network management
    "systemd-resolve",   # DNS resolver management
    "systemd-timesync",  # Time synchronization
]
```

#### Multimedia / Hardware Groups (LOW - but still forbidden)

```python
FORBIDDEN_GROUPS_HARDWARE = [
    "audio",          # Audio device access
    "video",          # Video device access
    "cdrom",          # CD-ROM device access
    "floppy",         # Floppy device access
    "plugdev",        # Pluggable device access
    "lp",             # Printer access
    "scanner",        # Scanner access
    "input",          # Input device access
    "render",         # GPU render access
]
```

#### Combined Forbidden Groups

```python
FORBIDDEN_GROUPS = (
    FORBIDDEN_GROUPS_CRITICAL +
    FORBIDDEN_GROUPS_SYSTEM +
    FORBIDDEN_GROUPS_CONTAINER +
    FORBIDDEN_GROUPS_NETWORK +
    FORBIDDEN_GROUPS_SYSTEMD +
    FORBIDDEN_GROUPS_HARDWARE
)
# Total: 35+ entries
```

### 2.3 Allowed User-Created Groups

Only groups meeting ALL of the following criteria can be created:

```
1. Name matches pattern: ^[a-z_][a-z0-9_-]{0,31}$
2. Name is NOT in FORBIDDEN_GROUPS
3. Name is NOT in FORBIDDEN_USERNAMES (prevent user/group name collision)
4. GID will be assigned automatically (>= 1000, < 60000)
5. Group does not already exist (getent group check)
```

### 2.4 Default Group Assignment

```python
# Default groups for new users
DEFAULT_GROUPS = ["users"]

# Maximum additional groups per user
MAX_GROUPS_PER_USER = 10

# Only groups with GID >= 1000 can be assigned (unless in DEFAULT_GROUPS)
```

---

## 3. UID / GID Range Policy

### 3.1 Allowed Ranges

| Range | Category | WebUI Access |
|-------|----------|-------------|
| 0 | root | FORBIDDEN - invisible and unmodifiable |
| 1 - 99 | System static | FORBIDDEN - invisible and unmodifiable |
| 100 - 999 | System dynamic | FORBIDDEN - invisible and unmodifiable |
| **1000 - 59999** | **Normal users** | **ALLOWED - visible and modifiable** |
| 60000 - 64999 | Reserved | FORBIDDEN - invisible and unmodifiable |
| 65534 | nobody/nogroup | FORBIDDEN - invisible and unmodifiable |
| 65535+ | Invalid/overflow | FORBIDDEN - rejected |

### 3.2 UID/GID Assignment

```python
UID_GID_POLICY = {
    "min_uid": 1000,
    "max_uid": 59999,
    "min_gid": 1000,
    "max_gid": 59999,
    "assignment": "automatic",  # Let useradd/groupadd assign next available
    "manual_assignment": False,  # Users cannot specify UID/GID via WebUI
}
```

### 3.3 Validation Implementation

```python
# API Layer
def validate_uid_range(uid: int) -> bool:
    """Validate that UID is in the allowed range for WebUI operations"""
    return 1000 <= uid <= 59999

def validate_gid_range(gid: int) -> bool:
    """Validate that GID is in the allowed range for WebUI operations"""
    return 1000 <= gid <= 59999
```

```bash
# Wrapper Layer (redundant check)
if [ "$USER_UID" -lt 1000 ] || [ "$USER_UID" -ge 60000 ]; then
    error "SECURITY: UID $USER_UID is outside allowed range (1000-59999)"
    exit 1
fi
```

---

## 4. Shell Policy

### 4.1 Allowed Shells (Allowlist)

```python
ALLOWED_SHELLS = [
    "/bin/bash",       # Default shell
    "/bin/sh",         # POSIX shell
    "/usr/bin/zsh",    # Zsh shell (if installed)
    "/usr/sbin/nologin",  # No login access
    "/bin/false",      # Login disabled
]
```

### 4.2 Forbidden Shells (Implicit Denylist)

Any shell not in `ALLOWED_SHELLS` is automatically rejected. This prevents:

```
REJECTED (examples):
- /bin/csh                # Not in allowlist
- /usr/bin/fish           # Not in allowlist
- /usr/bin/screen         # Not a shell
- /bin/bash -c "cmd"      # Arguments not allowed
- /tmp/malicious_shell    # Arbitrary path
- ../../bin/sh            # Path traversal
- /bin/bash;id            # Injection attempt
```

### 4.3 Shell Validation

```python
# API Layer
@field_validator('shell')
@classmethod
def validate_shell(cls, v: str) -> str:
    # Exact match only (no normalization, no symlink following)
    if v not in ALLOWED_SHELLS:
        raise ValueError(f"Shell '{v}' is not in the allowed list: {ALLOWED_SHELLS}")
    return v
```

```bash
# Wrapper Layer
ALLOWED_SHELLS=("/bin/bash" "/bin/sh" "/usr/bin/zsh" "/usr/sbin/nologin" "/bin/false")
shell_allowed=false
for allowed in "${ALLOWED_SHELLS[@]}"; do
    if [ "$SHELL_PATH" = "$allowed" ]; then
        shell_allowed=true
        break
    fi
done
if [ "$shell_allowed" = false ]; then
    error "SECURITY: Shell not allowed: $SHELL_PATH"
    exit 1
fi
```

---

## 5. Password Policy

### 5.1 Password Strength Requirements

```python
PASSWORD_POLICY = {
    "min_length": 8,
    "max_length": 128,
    "require_uppercase": True,    # At least 1 uppercase letter (A-Z)
    "require_lowercase": True,    # At least 1 lowercase letter (a-z)
    "require_digit": True,        # At least 1 digit (0-9)
    "require_special": True,      # At least 1 special character
    "allowed_special_chars": "!@#$%^&*(),.?\":{}|<>-_=+[]~`/\\';",
    "reject_common": True,        # Reject known common passwords
    "reject_username_in_password": True,  # Password must not contain username
}
```

### 5.2 Common Password Denylist

```python
COMMON_PASSWORDS = [
    "password", "12345678", "123456789", "1234567890",
    "qwerty", "qwerty123", "abc123", "abcdef",
    "admin123", "admin1234", "administrator",
    "letmein", "welcome", "welcome1",
    "monkey", "dragon", "master",
    "login", "passw0rd", "p@ssw0rd", "p@ssword",
    "iloveyou", "trustno1", "sunshine",
    "princess", "football", "baseball", "shadow",
    "michael", "password1", "password123",
    "changeme", "changeit", "default",
    # Platform-specific
    "ubuntu", "linux", "debian", "server",
]
```

### 5.3 Password Handling Rules (Security)

```
1. Password is transmitted over HTTPS only
2. Password is hashed with bcrypt (cost factor 12) immediately at API boundary
3. Plain-text password is never stored anywhere
4. Plain-text password is never logged (application, audit, or wrapper logs)
5. Password hash is encrypted before storage in approval request payload
6. Password hash is passed to wrapper via stdin (never as command argument)
7. Password hash is not included in API responses
8. Password hash is not included in audit log details
9. Failed password validation returns generic error (no hint about which rule failed)
   Exception: During user creation, specific validation feedback is acceptable
```

---

## 6. Home Directory Policy

### 6.1 Allowed Base Directories (Allowlist)

```python
ALLOWED_HOME_BASES = ["/home"]
```

### 6.2 Home Directory Rules

```python
HOME_DIR_POLICY = {
    "default_pattern": "/home/{username}",  # Auto-generated if not specified
    "allowed_bases": ["/home"],
    "max_path_length": 255,
    "allow_custom_subdir": False,  # Only /home/{username} allowed
    "create_on_add": True,         # -m flag for useradd
    "backup_on_delete": True,      # tar before userdel -r
    "backup_location": "/var/backups/adminui/users/",
}
```

### 6.3 Home Directory Validation

```python
@field_validator('home_dir')
@classmethod
def validate_home_dir(cls, v: Optional[str]) -> Optional[str]:
    if v is None:
        return None  # Will default to /home/{username}

    # 1. Path traversal check
    if ".." in v:
        raise ValueError("Path traversal detected")

    # 2. Normalize and check base
    normalized = os.path.normpath(v)
    if not normalized.startswith("/home/"):
        raise ValueError("Home directory must be under /home/")

    # 3. Symlink check (at validation time, not yet created)
    parent = os.path.dirname(normalized)
    if os.path.exists(parent) and os.path.islink(parent):
        raise ValueError("Symlink detected in parent path")

    # 4. Depth limit (only /home/<username>, no deeper nesting)
    parts = normalized.strip("/").split("/")
    if len(parts) != 2:  # ["home", "username"]
        raise ValueError("Home directory must be exactly /home/{username}")

    return normalized
```

```bash
# Wrapper Layer
if [[ "$HOME_DIR" != /home/* ]]; then
    error "SECURITY: Home directory must be under /home/: $HOME_DIR"
    exit 1
fi

# Depth check: must be exactly /home/<name>
dir_depth=$(echo "$HOME_DIR" | tr -cd '/' | wc -c)
if [ "$dir_depth" -ne 2 ]; then
    error "SECURITY: Home directory nesting not allowed: $HOME_DIR"
    exit 1
fi
```

---

## 7. Forbidden Characters Policy

### 7.1 Forbidden Character Set

These characters are **rejected in all user-facing inputs** (username, group name, GECOS field, reason text):

```python
FORBIDDEN_CHARS = [
    ";",   # Command separator
    "|",   # Pipe
    "&",   # Background execution / AND
    "$",   # Variable expansion
    "(",   # Subshell open
    ")",   # Subshell close
    "`",   # Command substitution (backtick)
    ">",   # Output redirection
    "<",   # Input redirection
    "*",   # Glob wildcard
    "?",   # Glob single character
    "{",   # Brace expansion open
    "}",   # Brace expansion close
    "[",   # Bracket expression open
    "]",   # Bracket expression close
    "\\",  # Escape character
    "'",   # Single quote
    "\"",  # Double quote
    "\n",  # Newline
    "\r",  # Carriage return
    "\t",  # Tab
    "\0",  # Null byte
]

FORBIDDEN_CHARS_PATTERN = r'[;|&$()` ><*?{}\[\]\\\'\"\\n\\r\\t\\0]'
```

### 7.2 Forbidden Character Validation

```python
# API Layer
def validate_no_forbidden_chars(value: str, field_name: str) -> str:
    """Check for forbidden characters in user input"""
    for char in FORBIDDEN_CHARS:
        if char in value:
            raise ValueError(
                f"Forbidden character detected in {field_name}: "
                f"character code {ord(char)}"
            )
    return value
```

```bash
# Wrapper Layer
FORBIDDEN_CHARS='[;|&$()` ><*?{}\[\]\\'"'"'"\\]'
if [[ "$INPUT" =~ $FORBIDDEN_CHARS ]]; then
    error "SECURITY: Forbidden character detected in input"
    log "SECURITY: Forbidden character - input=$INPUT, caller=${SUDO_USER:-$USER}"
    exit 1
fi
```

### 7.3 Field-Specific Character Policies

| Field | Allowed Characters | Max Length |
|-------|-------------------|-----------|
| username | `[a-z_][a-z0-9_-]*` | 32 |
| group name | `[a-z_][a-z0-9_-]*` | 32 |
| password | All printable ASCII (0x20-0x7E) | 128 |
| GECOS (comment) | `[a-zA-Z0-9 ._-]` | 100 |
| reason (approval) | `[a-zA-Z0-9 .,!?:;()\-_/]` | 500 |
| home directory | `[a-zA-Z0-9/_-]` | 255 |
| shell path | Exact match from ALLOWED_SHELLS | N/A |

---

## 8. Rate Limiting Policy

### 8.1 Per-Endpoint Rate Limits

| Endpoint | Method | Rate Limit | Rationale |
|----------|--------|-----------|-----------|
| /api/users | GET | 30/minute | Read-only, moderate |
| /api/users/{uid} | GET | 30/minute | Read-only, moderate |
| /api/users | POST | 5/minute | Write operation, strict |
| /api/users/{uid} | DELETE | 3/minute | Critical operation, very strict |
| /api/users/{uid}/password | PUT | 3/minute | Credential operation, very strict |
| /api/groups | GET | 30/minute | Read-only, moderate |
| /api/groups | POST | 5/minute | Write operation, strict |
| /api/groups/{gid} | DELETE | 3/minute | Critical operation, very strict |
| /api/groups/{gid}/members | PUT | 5/minute | Write operation, strict |

### 8.2 Global Limits

```python
RATE_LIMIT_POLICY = {
    "pending_requests_per_user": 10,      # Max pending approval requests per user
    "total_pending_requests": 50,          # System-wide pending limit
    "lockout_after_failures": 5,           # Lock after N consecutive validation failures
    "lockout_duration_minutes": 15,        # Lockout duration
}
```

---

## 9. Audit Logging Policy

### 9.1 Mandatory Audit Events

Every operation on the Users & Groups module MUST generate an audit log entry:

```python
AUDIT_EVENTS = {
    # Read operations
    "user_list":        {"log_level": "INFO",    "includes_result": False},
    "user_detail":      {"log_level": "INFO",    "includes_result": False},
    "group_list":       {"log_level": "INFO",    "includes_result": False},

    # Write request operations
    "user_add_request":     {"log_level": "INFO",    "includes_result": True},
    "user_delete_request":  {"log_level": "WARNING", "includes_result": True},
    "user_passwd_request":  {"log_level": "WARNING", "includes_result": True},
    "group_add_request":    {"log_level": "INFO",    "includes_result": True},
    "group_delete_request": {"log_level": "WARNING", "includes_result": True},
    "group_modify_request": {"log_level": "INFO",    "includes_result": True},

    # Execution operations (post-approval)
    "user_add_execute":     {"log_level": "WARNING", "includes_result": True},
    "user_delete_execute":  {"log_level": "WARNING", "includes_result": True},
    "user_passwd_execute":  {"log_level": "WARNING", "includes_result": True},
    "group_add_execute":    {"log_level": "INFO",    "includes_result": True},
    "group_delete_execute": {"log_level": "WARNING", "includes_result": True},
    "group_modify_execute": {"log_level": "INFO",    "includes_result": True},

    # Security events
    "forbidden_username_attempt":  {"log_level": "ERROR",   "includes_result": True},
    "forbidden_group_attempt":     {"log_level": "ERROR",   "includes_result": True},
    "uid_range_violation":         {"log_level": "ERROR",   "includes_result": True},
    "injection_attempt":           {"log_level": "CRITICAL","includes_result": True},
    "approval_bypass_attempt":     {"log_level": "CRITICAL","includes_result": True},
}
```

### 9.2 Audit Log Field Requirements

```python
# Mandatory fields for every audit entry
AUDIT_REQUIRED_FIELDS = {
    "timestamp": "ISO 8601 format",
    "operation": "Operation name from AUDIT_EVENTS",
    "user_id": "Authenticated user ID",
    "username": "Authenticated username",
    "role": "User's role at time of request",
    "source_ip": "Client IP address",
    "status": "attempt | success | denied | failure",
}

# Optional fields (operation-dependent)
AUDIT_OPTIONAL_FIELDS = {
    "target_username": "Target user being operated on",
    "target_uid": "Target UID",
    "target_groups": "Groups being assigned/modified",
    "approval_id": "Linked approval request ID",
    "approver_id": "ID of the approver",
    "reason": "Approval reason provided by requester",
    "error_message": "Error details (sanitized, no passwords)",
}

# NEVER include in audit logs
AUDIT_EXCLUDED_FIELDS = [
    "password",
    "password_hash",
    "password_hash_encrypted",
    "token",
    "session_id",
]
```

---

## 10. sudoers Configuration Policy

### 10.1 Required sudoers Entries

The following entries must be added to `/etc/sudoers.d/adminui-users` (human approval required):

```
# /etc/sudoers.d/adminui-users
# Managed by Linux Management System
# DO NOT EDIT MANUALLY

# Read operations (no sudo required - these are listed for documentation)
# adminui-user-list.sh    - runs as adminui user, no sudo
# adminui-user-detail.sh  - runs as adminui user, no sudo
# adminui-group-list.sh   - runs as adminui user, no sudo

# Write operations (sudo required)
adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-user-add.sh
adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-user-delete.sh
adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-user-passwd.sh
adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-group-add.sh
adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-group-delete.sh
adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-group-modify.sh
```

### 10.2 sudoers Security Rules

```
1. Only the `adminui` service user can execute wrapper scripts via sudo
2. Only specific wrapper scripts are allowed (no wildcard paths)
3. NOPASSWD is required because the API service runs non-interactively
4. Arguments are NOT restricted in sudoers (validated by wrapper scripts themselves)
5. No SETENV allowed (prevents environment variable injection)
6. Changes to sudoers require human approval and system administrator action
```

---

## 11. GECOS (Comment) Field Policy

### 11.1 Allowed GECOS Content

```python
GECOS_POLICY = {
    "allowed_pattern": r'^[a-zA-Z0-9 ._-]{0,100}$',
    "max_length": 100,
    "default_value": "",  # Empty if not provided
    "forbidden_chars": FORBIDDEN_CHARS,  # Same as global forbidden chars
}
```

### 11.2 GECOS Validation

```python
@field_validator('gecos')
@classmethod
def validate_gecos(cls, v: Optional[str]) -> str:
    if v is None or v == "":
        return ""
    if len(v) > 100:
        raise ValueError("GECOS field must be 100 characters or less")
    if not re.match(r'^[a-zA-Z0-9 ._-]+$', v):
        raise ValueError("GECOS field contains invalid characters")
    return v
```

---

## 12. Policy Change Control

### 12.1 Human Approval Required

Any modification to the following policies requires explicit human approval and a code deployment:

| Policy | Approval Level | Justification Required |
|--------|---------------|----------------------|
| FORBIDDEN_USERNAMES additions/removals | Admin | Written justification |
| FORBIDDEN_GROUPS additions/removals | Admin | Written justification + security review |
| UID/GID range boundaries | Admin | Written justification + security review |
| ALLOWED_SHELLS modifications | Admin | Written justification |
| Password policy relaxation | Admin | Written justification + risk assessment |
| Rate limit increases | Admin | Written justification |
| FORBIDDEN_CHARS removals | **PROHIBITED** | Not allowed under any circumstances |
| Home directory base additions | Admin | Written justification + security review |

### 12.2 Policy Versioning

```python
POLICY_VERSION = "1.0.0"
POLICY_EFFECTIVE_DATE = "2026-02-14"
POLICY_LAST_REVIEWED = "2026-02-14"
POLICY_NEXT_REVIEW = "Before v0.3 implementation begins"
```

### 12.3 Compliance Verification

The following automated checks should run in CI:

```bash
# 1. Verify forbidden lists are not empty
test $(python3 -c "from policy import FORBIDDEN_USERNAMES; print(len(FORBIDDEN_USERNAMES))") -ge 50

# 2. Verify critical entries exist
python3 -c "
from policy import FORBIDDEN_GROUPS
assert 'root' in FORBIDDEN_GROUPS
assert 'sudo' in FORBIDDEN_GROUPS
assert 'wheel' in FORBIDDEN_GROUPS
assert 'docker' in FORBIDDEN_GROUPS
assert 'lxd' in FORBIDDEN_GROUPS
"

# 3. Verify no shell=True
grep -r "shell=True" backend/ && exit 1 || exit 0

# 4. Verify FORBIDDEN_CHARS includes all required characters
python3 -c "
from policy import FORBIDDEN_CHARS
required = [';', '|', '&', '\$', '(', ')', '\`', '>', '<']
for char in required:
    assert char in FORBIDDEN_CHARS, f'Missing: {char}'
"
```

---

## Appendix A: Quick Reference Card

```
USERNAME:   ^[a-z_][a-z0-9_-]{0,31}$  + not in FORBIDDEN_USERNAMES
GROUP:      ^[a-z_][a-z0-9_-]{0,31}$  + not in FORBIDDEN_GROUPS
UID/GID:    1000 <= id <= 59999
SHELL:      /bin/bash | /bin/sh | /usr/bin/zsh | /usr/sbin/nologin | /bin/false
HOME:       /home/{username} only
PASSWORD:   8-128 chars, upper+lower+digit+special, not common
GECOS:      ^[a-zA-Z0-9 ._-]{0,100}$
CHARS:      ;|&$()` ><*?{}[]\'"  ALL FORBIDDEN
```

## Appendix B: Cross-Reference to Threat Analysis

| Policy Section | Mitigates Threat |
|---------------|-----------------|
| Username Forbidden List | T3, T5 |
| Group Forbidden List | T1 |
| UID/GID Range | T2, T5 |
| Shell Allowlist | T3 |
| Password Policy | T4 |
| Home Directory Policy | T10 |
| Forbidden Characters | T3 |
| Rate Limiting | T7 |
| Audit Logging | T8, T9 |
| sudoers Policy | T1, T8 |

---

**Last Updated**: 2026-02-14
**Next Review**: Before implementation phase begins
