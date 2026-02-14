# Users & Groups Management - Security Threat Analysis

**Created**: 2026-02-14
**Author**: users-planner (v03-planning-team)
**Module**: Users & Groups Management (v0.3)
**Security Level**: HIGH
**OWASP Top 10 (2021) Alignment**: Yes

---

## Executive Summary

The Users & Groups Management module handles **HIGH RISK** operations that directly affect system security boundaries. Unlike the Processes module (read-only), this module performs **write operations** (user creation, deletion, password changes) that require root privilege escalation via sudo.

### Risk Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 2 | Mitigated by design |
| HIGH | 4 | Mitigated by design |
| MEDIUM | 3 | Mitigated by design |
| LOW | 2 | Accepted with controls |

---

## Threat Model (STRIDE)

### T1: Unauthorized Privilege Escalation via Group Membership

**STRIDE Category**: Elevation of Privilege
**Severity**: CRITICAL
**CVSS 3.1**: 9.1 (CRITICAL) - AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H

#### Attack Scenario

```
Attacker: Compromised Operator account
Goal: Gain root-equivalent access

Steps:
1. Submit user creation request with groups=["sudo"]
2. If approval bypassed or validator flawed:
   - New user with sudo group membership is created
   - Attacker logs in as new user
   - "sudo su" grants root access
3. Complete system compromise
```

#### Impact

- **Confidentiality**: CRITICAL - Full system access, all data exposed
- **Integrity**: CRITICAL - Arbitrary system modification possible
- **Availability**: CRITICAL - Can destroy system entirely

#### Mitigation

| Layer | Control | Implementation |
|-------|---------|---------------|
| **API** | Forbidden groups validation | `FORBIDDEN_GROUPS` list checked in Pydantic validator |
| **Wrapper** | Redundant forbidden check | Second validation in bash before useradd |
| **sudoers** | Command restriction | Only specific useradd invocations allowed |
| **Approval** | Human verification | Approver sees group list and must verify |
| **Audit** | Full logging | All group assignments recorded with approval ID |

```python
# API Layer
FORBIDDEN_GROUPS = [
    "root", "sudo", "wheel", "adm", "disk", "lp", "dialout",
    "cdrom", "floppy", "audio", "video", "plugdev", "netdev",
    "docker", "lxd", "systemd-journal", "systemd-network",
    "shadow", "staff", "games", "users_admin"
]

@field_validator('groups')
@classmethod
def validate_groups(cls, v: list[str]) -> list[str]:
    for group in v:
        if group in FORBIDDEN_GROUPS:
            raise ValueError(f"Group '{group}' is forbidden: privilege escalation risk")
        if not re.match(r'^[a-z_][a-z0-9_-]{0,31}$', group):
            raise ValueError(f"Invalid group name format: '{group}'")
    return v
```

```bash
# Wrapper Layer (redundant check)
FORBIDDEN_GROUPS=("root" "sudo" "wheel" "adm" "disk" "docker" "lxd" "shadow" "staff")
for group in "${REQUESTED_GROUPS[@]}"; do
    for forbidden in "${FORBIDDEN_GROUPS[@]}"; do
        if [[ "$group" == "$forbidden" ]]; then
            error "SECURITY: Forbidden group detected: $group"
            log "SECURITY: Privilege escalation attempt blocked - group=$group, caller=${SUDO_USER:-$USER}"
            exit 1
        fi
    done
done
```

**Residual Risk**: LOW (multi-layer validation, approval gate, audit trail)

---

### T2: System User Deletion Causing Service Disruption

**STRIDE Category**: Denial of Service
**Severity**: CRITICAL
**CVSS 3.1**: 8.6 (HIGH) - AV:N/AC:L/PR:L/UI:N/S:C/C:N/I:N/A:H

#### Attack Scenario

```
Attacker: Compromised Operator or insider threat
Goal: Cause service disruption by deleting service accounts

Steps:
1. Submit deletion request for "postgres" (UID < 1000 but worth checking)
2. If validation flawed:
   - PostgreSQL service account deleted
   - Database service crashes
   - Data potentially inaccessible
3. Major service outage
```

#### Impact

- **Confidentiality**: None (direct)
- **Integrity**: HIGH - Service configuration corrupted
- **Availability**: CRITICAL - Multiple services may fail

#### Mitigation

| Layer | Control | Implementation |
|-------|---------|---------------|
| **API** | UID range check | Only UID >= 1000 users visible and modifiable |
| **Wrapper** | Redundant UID check | `id -u "$USERNAME"` verified >= 1000 before userdel |
| **Wrapper** | Running process check | Warns if user has active processes |
| **Wrapper** | Login session check | Rejects deletion of currently logged-in users |
| **Approval** | Admin-only approval | Only Admin role can approve user deletion |
| **Backup** | Home directory backup | `tar` before deletion (configurable) |

```bash
# Wrapper: System user protection
USER_UID=$(id -u "$USERNAME" 2>/dev/null)
if [ -z "$USER_UID" ]; then
    error "User does not exist: $USERNAME"
    exit 1
fi

if [ "$USER_UID" -lt 1000 ]; then
    error "SECURITY: Cannot delete system user (UID=$USER_UID < 1000)"
    log "SECURITY: System user deletion blocked - user=$USERNAME, uid=$USER_UID, caller=${SUDO_USER:-$USER}"
    exit 1
fi

# Check for active sessions
if who | grep -q "^${USERNAME} "; then
    error "User is currently logged in: $USERNAME"
    exit 1
fi
```

**Residual Risk**: LOW (UID protection, approval gate, backup)

---

### T3: Command Injection via Username/Group Name

**STRIDE Category**: Tampering / Elevation of Privilege
**Severity**: HIGH
**CVSS 3.1**: 8.8 (HIGH) - AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H

#### Attack Scenario

```
Attacker: Any authenticated user
Goal: Execute arbitrary commands via crafted username

Payload examples:
- username: "user;rm -rf /"
- username: "user$(cat /etc/shadow)"
- username: "user`id`"
- group: "users;chmod 777 /etc/sudoers"
```

#### Impact

- **Confidentiality**: HIGH - Arbitrary command execution
- **Integrity**: HIGH - System files modifiable
- **Availability**: HIGH - System destruction possible

#### Mitigation (Multi-Layer Defense)

| Layer | Validation | Pattern |
|-------|-----------|---------|
| **Frontend** | HTML5 pattern attribute | `pattern="[a-z_][a-z0-9_-]{0,31}"` |
| **API (Pydantic)** | Regex validator | `^[a-z_][a-z0-9_-]{0,31}$` |
| **API** | FORBIDDEN_CHARS check | `;|&$()><*?{}[]` all rejected |
| **Wrapper** | Redundant regex check | Same pattern validated in bash |
| **Wrapper** | FORBIDDEN_CHARS check | Redundant special character check |
| **subprocess** | Array invocation | `subprocess.run([...], shell=False)` |

```python
# API Layer: Triple validation
FORBIDDEN_CHARS = [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?", "{", "}", "[", "]"]

@field_validator('username')
@classmethod
def validate_username(cls, v: str) -> str:
    # 1. Forbidden characters
    for char in FORBIDDEN_CHARS:
        if char in v:
            raise ValueError(f"Forbidden character in username: {char}")

    # 2. Pattern match (allowlist approach)
    if not re.match(r'^[a-z_][a-z0-9_-]{0,31}$', v):
        raise ValueError("Username must match pattern: ^[a-z_][a-z0-9_-]{0,31}$")

    # 3. Forbidden usernames (reserved)
    if v in FORBIDDEN_USERNAMES:
        raise ValueError(f"Username '{v}' is reserved")

    return v
```

**Residual Risk**: MINIMAL (4 validation layers, no shell=True, array-based subprocess)

---

### T4: Weak Password Exploitation

**STRIDE Category**: Spoofing / Information Disclosure
**Severity**: HIGH
**CVSS 3.1**: 7.5 (HIGH) - AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N

#### Attack Scenario

```
Attacker: External or internal
Goal: Compromise newly created user account

Steps:
1. User created with weak password (e.g., "password1")
2. Attacker brute-forces SSH/WebUI login
3. Account compromised
```

#### Impact

- **Confidentiality**: HIGH - Unauthorized access
- **Integrity**: MEDIUM - Actions performed as compromised user
- **Availability**: LOW - Account lockout possible

#### Mitigation

```python
# Password Policy Enforcement
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

@field_validator('password')
@classmethod
def validate_password_strength(cls, v: str) -> str:
    if len(v) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters")
    if len(v) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Password must not exceed {PASSWORD_MAX_LENGTH} characters")
    if not re.search(r'[A-Z]', v):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r'[a-z]', v):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r'[0-9]', v):
        raise ValueError("Password must contain at least one digit")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
        raise ValueError("Password must contain at least one special character")

    # Common password check
    COMMON_PASSWORDS = [
        "password", "12345678", "qwerty", "admin123", "letmein",
        "welcome", "monkey", "dragon", "master", "login"
    ]
    if v.lower() in COMMON_PASSWORDS:
        raise ValueError("Password is too common")

    return v
```

**Residual Risk**: MEDIUM (policy enforced, but brute-force protection depends on SSH/PAM config)

---

### T5: Username Collision with System Accounts

**STRIDE Category**: Spoofing / Tampering
**Severity**: HIGH
**CVSS 3.1**: 7.2 (HIGH) - AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N

#### Attack Scenario

```
Attacker: Authenticated user with write:users permission
Goal: Create user with name that shadows a system account

Steps:
1. System account "backup" exists with UID < 1000
2. Attacker creates "backup" with UID >= 1000
3. Name conflict causes unexpected behavior:
   - File ownership confusion
   - Service authentication bypass
   - Log attribution errors
```

#### Impact

- **Confidentiality**: HIGH - Access confusion
- **Integrity**: HIGH - File ownership manipulation
- **Availability**: MEDIUM - Service disruption possible

#### Mitigation

```python
# Comprehensive forbidden username list
FORBIDDEN_USERNAMES = [
    # System accounts (Ubuntu default)
    "root", "bin", "daemon", "sys", "sync", "games", "man", "lp",
    "mail", "news", "uucp", "proxy", "www-data", "backup", "list",
    "irc", "gnats", "nobody", "systemd-network", "systemd-resolve",
    "messagebus", "syslog", "uuidd", "dnsmasq", "avahi",
    "speech-dispatcher", "fwupd-refresh", "sshd", "polkitd",
    "rtkit", "colord", "pulse", "gnome-initial-setup", "gdm",

    # Service accounts
    "postgres", "mysql", "redis", "nginx", "apache", "tomcat",
    "elasticsearch", "kibana", "grafana", "prometheus",
    "jenkins", "gitlab-runner", "docker",

    # Administrative (reserved for system)
    "admin", "administrator", "sudo", "wheel", "staff",
    "operator", "manager", "supervisor",

    # Application-specific
    "adminui", "adminui-service",
]
```

```bash
# Wrapper: Check if user already exists (any UID)
if id "$USERNAME" &>/dev/null; then
    error "User already exists: $USERNAME"
    exit 1
fi

# Also check /etc/passwd directly (catches deleted but referenced users)
if getent passwd "$USERNAME" &>/dev/null; then
    error "Username is reserved in passwd database: $USERNAME"
    exit 1
fi
```

**Residual Risk**: LOW (comprehensive forbidden list, existence check, UID range enforcement)

---

### T6: Password Hash Exposure in Logs/Transit

**STRIDE Category**: Information Disclosure
**Severity**: HIGH
**CVSS 3.1**: 6.5 (MEDIUM) - AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N

#### Attack Scenario

```
Attacker: Anyone with log access or network sniffer
Goal: Obtain password or hash for offline cracking

Exposure points:
1. API request body logged with password in plain text
2. Wrapper script arguments contain password hash
3. Audit log records password-related fields
4. Error message includes password in stack trace
5. Approval request stores password in approval database
```

#### Mitigation

```python
# 1. Immediate hashing at API boundary
@router.post("/users")
async def create_user(request: UserCreateRequest, ...):
    # Hash immediately, discard plain text
    password_hash = get_password_hash(request.password)
    # request.password is never used again

    # 2. Encrypted storage in approval payload
    encrypted_hash = encrypt_for_approval(password_hash)
    approval_request = await approval_service.create_request(
        payload={
            "username": request.username,
            "password_hash_encrypted": encrypted_hash,
            # NOTE: plain password is NOT stored anywhere
        }
    )

# 3. Logging exclusion
logger.info(
    f"User creation requested: username={request.username}, "
    f"groups={request.groups}"
    # NOTE: password is intentionally excluded from log
)

# 4. Audit log exclusion
audit_log.record(
    operation="user_add_request",
    details={
        "username": request.username,
        "groups": request.groups,
        # NOTE: no password or hash in audit log
    }
)
```

```bash
# Wrapper: password hash passed via stdin, not arguments
# BAD:  adminui-user-add.sh --password-hash='$2b$12$...'  (visible in ps)
# GOOD: echo "$HASH" | adminui-user-add.sh --username=newuser
```

**Residual Risk**: LOW (hash-only storage, encrypted in approval, excluded from logs)

---

### T7: Mass User Creation / Resource Exhaustion

**STRIDE Category**: Denial of Service
**Severity**: MEDIUM
**CVSS 3.1**: 5.3 (MEDIUM) - AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:L

#### Attack Scenario

```
Attacker: Compromised account with write:users permission
Goal: Exhaust system resources via mass user creation

Steps:
1. Submit 1000 user creation requests rapidly
2. Even with approval, queue fills up
3. If auto-approved somehow, disk/inode exhaustion from home directories
```

#### Mitigation

```python
# Rate limiting on write operations
@router.post("/users")
@limiter.limit("5/minute")  # Max 5 creation requests per minute
async def create_user(request: Request, ...):
    ...

# Pending request limit
MAX_PENDING_REQUESTS = 10  # Per user
pending = await approval_service.count_pending(
    requester_id=current_user.user_id,
    request_type="user_management"
)
if pending >= MAX_PENDING_REQUESTS:
    raise HTTPException(429, "Too many pending requests")
```

**Residual Risk**: LOW (rate limiting + approval gate + pending limit)

---

### T8: Approval Workflow Bypass

**STRIDE Category**: Elevation of Privilege / Tampering
**Severity**: HIGH
**CVSS 3.1**: 8.1 (HIGH) - AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N

#### Attack Scenario

```
Attacker: Developer with code access or API knowledge
Goal: Execute write operations without approval

Bypass attempts:
1. Direct wrapper script execution (bypassing API)
2. API parameter manipulation to skip approval check
3. Forging approval tokens
4. Self-approval (requester = approver)
```

#### Mitigation

| Bypass Attempt | Mitigation |
|---------------|-----------|
| Direct wrapper execution | sudoers restricts to adminui service user only |
| API parameter manipulation | Approval check is mandatory in code flow, not configurable |
| Forging approval tokens | Cryptographically signed, time-limited, stored server-side |
| Self-approval | Requester ID != Approver ID enforced |

```python
# Approval enforcement (cannot be bypassed by API parameters)
@router.post("/users")
async def create_user(request: UserCreateRequest, ...):
    # This ALWAYS creates an approval request
    # There is NO code path to directly execute user creation
    approval_request = await approval_service.create_request(...)
    return {"status": "approval_pending", "request_id": approval_request.id}

# The execution callback is only called by the approval service
# after a valid approval by a different user
```

**Residual Risk**: LOW (cryptographic tokens, server-side state, separation of duty)

---

### T9: Information Disclosure via User Enumeration

**STRIDE Category**: Information Disclosure
**Severity**: MEDIUM
**CVSS 3.1**: 4.3 (MEDIUM) - AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:N/A:N

#### Attack Scenario

```
Attacker: Authenticated Viewer
Goal: Enumerate all user accounts for targeted attacks

Information exposed:
- Usernames (for SSH brute-force)
- Home directories (for path traversal)
- Group memberships (for privilege understanding)
- Last login times (for identifying inactive accounts)
```

#### Mitigation

```python
# Role-based field filtering
def filter_user_fields(user: UserInfo, role: str) -> dict:
    """Filter user fields based on requester's role"""
    base_fields = {
        "username": user.username,
        "uid": user.uid,
        "groups": user.groups,
    }

    if role in ["Operator", "Approver", "Admin"]:
        base_fields.update({
            "home": user.home,
            "shell": user.shell,
            "last_login": user.last_login,
        })

    if role == "Admin":
        base_fields.update({
            "locked": user.locked,
            "gid": user.gid,
            "gecos": user.gecos,
        })

    return base_fields
```

**Residual Risk**: MEDIUM (authenticated access needed, role-based filtering, but user list is inherently visible)

---

### T10: Home Directory Path Traversal

**STRIDE Category**: Tampering / Information Disclosure
**Severity**: MEDIUM
**CVSS 3.1**: 5.4 (MEDIUM) - AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:L/A:N

#### Attack Scenario

```
Attacker: User with write:users permission
Goal: Create user with home directory pointing to sensitive location

Payload:
- home_dir: "/etc"
- home_dir: "/root"
- home_dir: "../../etc/nginx"
- home_dir: "/var/lib/postgresql"
```

#### Mitigation

```python
# Allowed home directory base paths
ALLOWED_HOME_BASES = ["/home"]

@field_validator('home_dir')
@classmethod
def validate_home_dir(cls, v: Optional[str]) -> Optional[str]:
    if v is None:
        return None  # Default to /home/<username>

    # Normalize path (resolve .., symlinks)
    normalized = os.path.normpath(v)

    # Must be under allowed base
    if not any(normalized.startswith(base) for base in ALLOWED_HOME_BASES):
        raise ValueError(f"Home directory must be under {ALLOWED_HOME_BASES}")

    # No path traversal
    if ".." in v:
        raise ValueError("Path traversal detected in home directory")

    # No symlink following
    if os.path.islink(v):
        raise ValueError("Symlink detected in home directory path")

    return normalized
```

```bash
# Wrapper: Enforce /home/ prefix
if [[ "$HOME_DIR" != /home/* ]]; then
    error "SECURITY: Home directory must be under /home/: $HOME_DIR"
    exit 1
fi
```

**Residual Risk**: LOW (path normalization, base directory enforcement, symlink check)

---

### T11: Timing Attack on User Existence Check

**STRIDE Category**: Information Disclosure
**Severity**: LOW
**CVSS 3.1**: 3.1 (LOW) - AV:N/AC:H/PR:L/UI:N/S:U/C:L/I:N/A:N

#### Attack Scenario

```
Attacker: Authenticated user
Goal: Determine if a specific username exists via response timing

Method:
- POST /api/users with existing username -> fast rejection
- POST /api/users with new username -> slower (validation + approval creation)
```

#### Mitigation

```python
# Constant-time response for creation requests
# Add artificial delay to normalize timing
import time

@router.post("/users")
async def create_user(request: UserCreateRequest, ...):
    start = time.monotonic()

    try:
        result = await _process_user_creation(request)
    finally:
        # Ensure minimum response time of 200ms
        elapsed = time.monotonic() - start
        if elapsed < 0.2:
            await asyncio.sleep(0.2 - elapsed)

    return result
```

**Residual Risk**: LOW (timing normalization, acceptable for this threat level)

---

## Risk Matrix Summary

| ID | Threat | Probability | Impact | Risk Level | Priority | Status |
|----|--------|------------|--------|-----------|----------|--------|
| T1 | Privilege escalation via groups | LOW | CRITICAL | HIGH | P0 | Mitigated |
| T2 | System user deletion | LOW | CRITICAL | HIGH | P0 | Mitigated |
| T3 | Command injection via names | LOW | HIGH | MEDIUM | P1 | Mitigated |
| T4 | Weak password exploitation | MEDIUM | HIGH | HIGH | P1 | Mitigated |
| T5 | Username collision | LOW | HIGH | MEDIUM | P1 | Mitigated |
| T6 | Password hash exposure | MEDIUM | HIGH | HIGH | P1 | Mitigated |
| T7 | Mass user creation DoS | LOW | MEDIUM | LOW | P2 | Mitigated |
| T8 | Approval workflow bypass | LOW | CRITICAL | HIGH | P0 | Mitigated |
| T9 | User enumeration | MEDIUM | LOW | MEDIUM | P2 | Mitigated |
| T10 | Home dir path traversal | LOW | MEDIUM | LOW | P2 | Mitigated |
| T11 | Timing attack on existence | LOW | LOW | LOW | P3 | Accepted |

---

## OWASP Top 10 (2021) Mapping

| OWASP Category | Related Threats | Mitigation Status |
|----------------|----------------|-------------------|
| A01 - Broken Access Control | T1, T2, T8, T9 | Multi-layer RBAC + approval |
| A02 - Cryptographic Failures | T4, T6 | bcrypt hashing, encrypted storage |
| A03 - Injection | T3 | 4-layer input validation |
| A04 - Insecure Design | T7, T8 | Rate limiting, approval workflow |
| A05 - Security Misconfiguration | T10 | Path validation, home dir restriction |
| A07 - Identity & Auth Failures | T4, T5 | Password policy, username validation |

---

## Security Test Requirements

### Mandatory Test Cases (minimum 30)

#### Injection Tests (10 cases)
1. Username with semicolon: `"user;id"`
2. Username with pipe: `"user|cat /etc/shadow"`
3. Username with backtick: `` "user`whoami`" ``
4. Username with dollar: `"user$(id)"`
5. Username with ampersand: `"user&rm -rf /"`
6. Group name with injection: `"group;chmod 777 /"`
7. Home directory traversal: `"../../etc"`
8. Shell injection: `"/bin/sh -c 'id'"`
9. All FORBIDDEN_CHARS individually
10. Unicode/control character injection

#### Privilege Escalation Tests (8 cases)
11. Add user to sudo group
12. Add user to wheel group
13. Add user to docker group
14. Add user to root group
15. Create user with UID < 1000
16. Delete system user (root)
17. Delete system user (www-data)
18. Modify system group membership

#### Approval Bypass Tests (7 cases)
19. Direct wrapper execution without approval
20. Self-approval (requester = approver)
21. Expired approval token
22. Reused approval token
23. Forged approval token
24. Cross-request approval token
25. Approval by insufficient role (Viewer approving)

#### RBAC Tests (5+ cases)
26. Viewer reading user list
27. Viewer attempting user creation
28. Operator creating request
29. Approver approving request
30. Admin full access

---

## Human Approval Required (CRITICAL)

The following actions require explicit human approval before implementation:

1. **sudoers additions**: Adding adminui-user-*.sh to sudoers allowlist
2. **FORBIDDEN_GROUPS updates**: Any modification to the forbidden groups list
3. **FORBIDDEN_USERNAMES updates**: Any modification to the forbidden usernames list
4. **Password policy changes**: Any relaxation of password requirements
5. **Approval flow changes**: Any modification to which operations require approval
6. **UID/GID boundary changes**: Any change from the 1000/60000 boundaries
7. **Home directory base changes**: Any addition to ALLOWED_HOME_BASES

---

**Last Updated**: 2026-02-14
**Next Review**: Before implementation phase begins
