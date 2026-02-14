# Users & Groups Management Module - Architecture Design

**Created**: 2026-02-14
**Author**: users-planner (v03-planning-team)
**Module**: Users & Groups Management (v0.3)
**Security Level**: HIGH (user creation/deletion affects system-wide security)

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Security Boundaries](#security-boundaries)
4. [Component Design](#component-design)
5. [Data Flow](#data-flow)
6. [Approval Workflow Integration](#approval-workflow-integration)
7. [Error Handling Strategy](#error-handling-strategy)
8. [RBAC Design](#rbac-design)
9. [Implementation Phases](#implementation-phases)
10. [Review Checklist](#review-checklist)

---

## Overview

### Purpose

Provide secure Linux user and group management through a WebUI, with mandatory approval workflows for all write operations. This module is classified as **HIGH RISK** because user management directly affects system security boundaries.

### Scope

**v0.3 Phase 1 - Read Operations** (no approval required):
- User list (UID >= 1000 only)
- Group list (GID >= 1000 only)
- User detail (membership, home directory, shell, last login)
- Group detail (members, GID)

**v0.3 Phase 2 - Write Operations** (approval required):
- User creation (approval mandatory)
- User deletion (approval mandatory)
- Password change (approval mandatory for admin-initiated, self-service TBD)
- Group creation (approval mandatory)
- Group deletion (approval mandatory)
- Group membership modification (approval mandatory)

**Explicitly Out of Scope (FORBIDDEN)**:
- root user operations
- sudo/wheel group membership changes
- UID < 1000 user modifications
- GID < 1000 group modifications
- sudoers file editing
- Direct /etc/passwd or /etc/shadow editing

### Security Risk Assessment

| Operation | Risk Level | Requires Approval | Reason |
|-----------|-----------|-------------------|--------|
| List users | LOW | No | Read-only, no system change |
| List groups | LOW | No | Read-only, no system change |
| User detail | LOW | No | Read-only, information exposure risk |
| Create user | **HIGH** | **YES** | New attack surface, resource allocation |
| Delete user | **CRITICAL** | **YES** | Data loss, service disruption risk |
| Change password | **HIGH** | **YES** | Credential management |
| Create group | MEDIUM | **YES** | Permission boundary change |
| Delete group | **HIGH** | **YES** | Membership disruption |
| Modify group membership | **HIGH** | **YES** | Privilege escalation risk |

---

## Architecture Diagram

```
+---------------------------------------------------------------+
|                      Web Browser (Client)                      |
|  +----------------------------------------------------------+ |
|  |  users.html + users.js                                    | |
|  |  - User/Group list tables                                 | |
|  |  - Add User modal (with approval reason)                  | |
|  |  - Delete User confirmation + approval reason             | |
|  |  - Group management UI                                    | |
|  |  - Approval request status display                        | |
|  +----------------------------------------------------------+ |
+-------------------------------+-------------------------------+
                                | HTTPS (JSON)
                                | GET  /api/users
                                | POST /api/users          (approval request)
                                | DELETE /api/users/{uid}   (approval request)
                                | GET  /api/groups
                                | POST /api/groups         (approval request)
                                v
+---------------------------------------------------------------+
|                    FastAPI Backend                              |
|  +----------------------------------------------------------+ |
|  |  backend/api/routes/users.py                              | |
|  |  - Input validation (Pydantic + allowlist)                | |
|  |  - Authentication (require_permission)                    | |
|  |  - Audit log recording                                    | |
|  |  - Approval workflow integration                          | |
|  +--+---+---+--------------------------------------------+--+ |
|     |   |   |                                            |     |
|     |   |   +-- approval_service.create_request() ------>|     |
|     |   |       (for write operations)                   |     |
|     |   |                                                |     |
|     |   +-- sudo_wrapper.list_users() ------+            |     |
|     +-- sudo_wrapper.list_groups() ----+    |            |     |
|                                        |    |            |     |
+-------------------------------+--------+----+------------+-----+
                                |        |    |
           sudo_wrapper.py <----+--------+    |
                                |             |
                                v             v
+---------------------------------------------------------------+
|         Wrapper Scripts (wrappers/adminui-user-*.sh)           |
|  +----------------------------------------------------------+ |
|  |  adminui-user-list.sh     (no sudo required)             | |
|  |  adminui-user-detail.sh   (no sudo required)             | |
|  |  adminui-user-add.sh      (sudo required, approval gate) | |
|  |  adminui-user-delete.sh   (sudo required, approval gate) | |
|  |  adminui-user-passwd.sh   (sudo required, approval gate) | |
|  |  adminui-group-list.sh    (no sudo required)             | |
|  |  adminui-group-add.sh     (sudo required, approval gate) | |
|  |  adminui-group-delete.sh  (sudo required, approval gate) | |
|  |  adminui-group-modify.sh  (sudo required, approval gate) | |
|  +----------------------------------------------------------+ |
+-------------------------------+-------------------------------+
                                |
                                | useradd / userdel / chpasswd
                                | groupadd / groupdel / usermod
                                v
                     Linux System (PAM/NSS)
```

---

## Security Boundaries

### Boundary 1: Client to API (Network)

```
[Browser] --HTTPS--> [FastAPI]
                       |
                       +-- JWT authentication required
                       +-- RBAC permission check
                       +-- Pydantic input validation
                       +-- Rate limiting (30 req/min for writes)
```

### Boundary 2: API to Wrapper (Process)

```
[FastAPI] --subprocess--> [Wrapper Script]
                            |
                            +-- No shell=True (array-based invocation)
                            +-- Approval token verification (for writes)
                            +-- Allowlist validation (redundant layer)
                            +-- Timeout enforcement (10s read, 30s write)
```

### Boundary 3: Wrapper to System (Privilege)

```
[Wrapper] --sudo--> [useradd/userdel/etc.]
                      |
                      +-- sudoers allowlist (specific commands only)
                      +-- UID >= 1000 enforcement
                      +-- Forbidden group protection
                      +-- Audit logging via logger
```

### Boundary 4: Approval Gate (Workflow)

```
[Write Request] --> [Approval Service] --> [Approver Decision]
                                              |
                                              +-- Approver/Admin role required
                                              +-- Time-limited token (1 hour)
                                              +-- Single-use execution
                                              +-- Full audit trail
```

---

## Component Design

### 1. Wrapper Scripts

#### 1.1 adminui-user-list.sh

**Purpose**: List non-system users (UID >= 1000)
**Sudo required**: No
**Risk**: LOW

```bash
#!/bin/bash
set -euo pipefail

# Read-only operation: list users with UID >= 1000
# Output: JSON array of user objects

getent passwd | awk -F: '$3 >= 1000 && $3 < 60000' | \
while IFS=: read -r username _ uid gid gecos home shell; do
    groups_list=$(id -Gn "$username" 2>/dev/null | tr ' ' ',')
    locked=$(passwd -S "$username" 2>/dev/null | awk '{print $2}')
    last_login=$(lastlog -u "$username" 2>/dev/null | tail -1 | awk '{
        if ($2 == "**Never") print "never";
        else print $4" "$5" "$6" "$7" "$9
    }')
    # ... JSON output
done
```

#### 1.2 adminui-user-add.sh

**Purpose**: Create a new user account
**Sudo required**: YES
**Risk**: HIGH
**Approval**: MANDATORY

```bash
#!/bin/bash
set -euo pipefail

# Arguments:
#   --username=<name>     User name (validated)
#   --password-hash=<hash> Pre-hashed password (bcrypt)
#   --groups=<g1,g2>      Comma-separated group list (validated)
#   --home=<path>         Home directory (default: /home/<username>)
#   --shell=<path>        Login shell (allowlist)
#   --approval-token=<token> Approval verification token

# Validation chain:
# 1. Username format (^[a-z_][a-z0-9_-]{0,31}$)
# 2. Username not in FORBIDDEN_USERNAMES
# 3. User does not already exist
# 4. Groups not in FORBIDDEN_GROUPS
# 5. Shell in ALLOWED_SHELLS
# 6. Approval token valid (verified by API layer)

# Execution:
# sudo useradd -m -s "$SHELL" -G "$GROUPS" "$USERNAME"
# echo "$USERNAME:$PASSWORD_HASH" | sudo chpasswd -e
```

#### 1.3 adminui-user-delete.sh

**Purpose**: Delete a user account
**Sudo required**: YES
**Risk**: CRITICAL
**Approval**: MANDATORY

```bash
#!/bin/bash
set -euo pipefail

# Arguments:
#   --username=<name>      User to delete
#   --remove-home          Also remove home directory (default: no)
#   --approval-token=<token>

# Safety checks:
# 1. User exists
# 2. UID >= 1000 (system user protection)
# 3. User is not currently logged in
# 4. User does not own running processes (warning)
# 5. Home directory backup before deletion

# Execution:
# sudo userdel [-r] "$USERNAME"
```

### 2. Backend API Routes

**File**: `backend/api/routes/users.py`

#### Endpoints

| Method | Path | Permission | Approval | Description |
|--------|------|-----------|----------|-------------|
| GET | /api/users | read:users | No | List all non-system users |
| GET | /api/users/{uid} | read:users | No | Get user detail |
| POST | /api/users | write:users | **Yes** | Create approval request for user creation |
| DELETE | /api/users/{uid} | write:users | **Yes** | Create approval request for user deletion |
| PUT | /api/users/{uid}/password | write:users | **Yes** | Create approval request for password change |
| GET | /api/groups | read:users | No | List all non-system groups |
| POST | /api/groups | write:users | **Yes** | Create approval request for group creation |
| DELETE | /api/groups/{gid} | write:users | **Yes** | Create approval request for group deletion |
| PUT | /api/groups/{gid}/members | write:users | **Yes** | Create approval request for membership change |

#### Pydantic Models

```python
class UserCreateRequest(BaseModel):
    """User creation request"""
    username: str = Field(
        min_length=1, max_length=32,
        pattern=r'^[a-z_][a-z0-9_-]{0,31}$'
    )
    password: str = Field(min_length=8, max_length=128)
    groups: list[str] = Field(default=["users"], max_length=10)
    home_dir: Optional[str] = None
    shell: str = Field(default="/bin/bash")
    reason: str = Field(min_length=10, max_length=500)

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        if v in FORBIDDEN_USERNAMES:
            raise ValueError(f"Username '{v}' is reserved")
        return v

    @field_validator('groups')
    @classmethod
    def validate_groups(cls, v: list[str]) -> list[str]:
        for group in v:
            if group in FORBIDDEN_GROUPS:
                raise ValueError(f"Group '{group}' is forbidden")
        return v

    @field_validator('shell')
    @classmethod
    def validate_shell(cls, v: str) -> str:
        if v not in ALLOWED_SHELLS:
            raise ValueError(f"Shell '{v}' is not allowed")
        return v

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        # Complexity check performed here
        # Actual password never stored in logs/audit
        return v


class UserListResponse(BaseModel):
    """User list response"""
    status: str
    users: list[UserInfo]
    total_count: int
    timestamp: str


class UserInfo(BaseModel):
    """Individual user information"""
    username: str
    uid: int
    gid: int
    gecos: str
    home: str
    shell: str
    groups: list[str]
    locked: bool
    last_login: Optional[str]
```

### 3. Frontend UI

**Files**: `frontend/dev/users.html`, `frontend/js/users.js`

#### Page Structure

```
+---------------------------------------------------------------+
|  Linux Management System > System > Users and Groups          |
+---------------------------------------------------------------+
|                                                                |
|  [Tab: Users] [Tab: Groups]                                   |
|                                                                |
|  +----------------------------------------------------------+ |
|  | Search: [____________]  Status: [All v]  [+ Add User]    | |
|  +----------------------------------------------------------+ |
|  | Username | UID  | Groups      | Home       | Shell  | ... | |
|  |----------|------|-------------|------------|--------|-----| |
|  | kensan   | 1000 | users,dev   | /home/ken  | /bin/b | [x]| |
|  | deploy   | 1001 | users,ops   | /home/dep  | /bin/b | [x]| |
|  +----------------------------------------------------------+ |
|                                                                |
|  Showing 2 of 2 users (system users hidden)                   |
+---------------------------------------------------------------+
```

#### Add User Modal

```
+---------------------------------------------------------------+
|  Add User - Approval Request                                   |
+---------------------------------------------------------------+
|                                                                |
|  Username:  [____________] (lowercase, a-z, 0-9, _, -)        |
|  Password:  [____________] (min 8 chars, complexity required) |
|  Confirm:   [____________]                                    |
|  Groups:    [users     v] [+ Add Group]                       |
|  Shell:     [/bin/bash v]                                     |
|  Reason:    [                                                 |
|              Please explain why this user is needed...        |
|             ________________________________________________] |
|                                                                |
|  [Cancel]                      [Submit Approval Request]      |
+---------------------------------------------------------------+
```

---

## Data Flow

### Read Operation: List Users

```
Browser                 API Server              Wrapper              Linux
   |                        |                      |                   |
   | GET /api/users         |                      |                   |
   |----------------------->|                      |                   |
   |                        | JWT verify           |                   |
   |                        | RBAC: read:users     |                   |
   |                        |                      |                   |
   |                        | _execute(            |                   |
   |                        |   "adminui-user-     |                   |
   |                        |    list.sh", [])     |                   |
   |                        |--------------------->|                   |
   |                        |                      | getent passwd     |
   |                        |                      |------------------>|
   |                        |                      | (UID >= 1000)     |
   |                        |                      |<------------------|
   |                        |                      | id -Gn username   |
   |                        |                      |------------------>|
   |                        |                      |<------------------|
   |                        |                      |                   |
   |                        | JSON response        |                   |
   |                        |<---------------------|                   |
   |                        |                      |                   |
   |                        | audit_log.record(    |                   |
   |                        |   "user_list",       |                   |
   |                        |   status="success")  |                   |
   |                        |                      |                   |
   | 200 OK + UserList      |                      |                   |
   |<-----------------------|                      |                   |
```

### Write Operation: Create User (with Approval)

```
Browser            API Server         Approval Service       Approver         Wrapper         Linux
   |                   |                    |                    |                |               |
   | POST /api/users   |                    |                    |                |               |
   | {username,pass,..} |                   |                    |                |               |
   |------------------>|                    |                    |                |               |
   |                   | validate input     |                    |                |               |
   |                   | hash password      |                    |                |               |
   |                   | check duplicates   |                    |                |               |
   |                   |                    |                    |                |               |
   |                   | create_request(    |                    |                |               |
   |                   |   type="user_add", |                    |                |               |
   |                   |   payload={...})   |                    |                |               |
   |                   |------------------->|                    |                |               |
   |                   |                    | store request      |                |               |
   |                   |                    | notify approvers   |                |               |
   |                   |                    |------------------->|                |               |
   |                   |                    |                    |                |               |
   | 202 Accepted      |                    |                    |                |               |
   | {request_id,      |                    |                    |                |               |
   |  status:pending}  |                    |                    |                |               |
   |<------------------|                    |                    |                |               |
   |                   |                    |                    |                |               |
   |                   |                    |    [Approver reviews and approves]  |               |
   |                   |                    |<-------------------|                |               |
   |                   |                    |                    |                |               |
   |                   |                    | execute_approved(  |                |               |
   |                   |                    |   request_id)      |                |               |
   |                   |                    |                    |                |               |
   |                   | on_approval(       |                    |                |               |
   |                   |   request_id)      |                    |                |               |
   |                   |<-------------------|                    |                |               |
   |                   |                    |                    |                |               |
   |                   | _execute(          |                    |                |               |
   |                   |   "adminui-user-   |                    |                |               |
   |                   |    add.sh",        |                    |                |               |
   |                   |   args=[...])      |                    |                |               |
   |                   |--------------------------------------------------->|               |
   |                   |                    |                    |          | sudo useradd  |
   |                   |                    |                    |          |-------------->|
   |                   |                    |                    |          |<--------------|
   |                   |                    |                    |          |               |
   |                   | JSON: success      |                    |          |               |
   |                   |<--------------------------------------------------|               |
   |                   |                    |                    |                |               |
   |                   | audit_log.record(  |                    |                |               |
   |                   |   "user_add",      |                    |                |               |
   |                   |   status="success",|                    |                |               |
   |                   |   approval_id=...) |                    |                |               |
   |                   |                    |                    |                |               |
   | WebSocket/Poll:   |                    |                    |                |               |
   | request approved  |                    |                    |                |               |
   |<------------------|                    |                    |                |               |
```

---

## Approval Workflow Integration

### Integration Points

Users & Groups module integrates with the Approval Workflow Service (designed by approval-architect) at the following points:

#### 1. Request Creation

```python
# POST /api/users - User creation
approval_request = await approval_service.create_request(
    request_type="user_management",
    sub_type="user_add",
    requester_id=current_user.user_id,
    risk_level="HIGH",
    payload={
        "username": request.username,
        "groups": request.groups,
        "home_dir": request.home_dir,
        "shell": request.shell,
        # NOTE: password hash is stored encrypted, never plain text
        "password_hash_encrypted": encrypt(password_hash),
    },
    reason=request.reason,
    required_approver_role="Approver",  # or "Admin"
    expires_in_hours=24,
)
```

#### 2. Approval Execution Callback

```python
# Called by approval service when request is approved
async def execute_user_add(approval_id: str, payload: dict):
    """Execute user creation after approval"""
    # Decrypt password hash
    password_hash = decrypt(payload["password_hash_encrypted"])

    # Execute wrapper
    result = sudo_wrapper.add_user(
        username=payload["username"],
        password_hash=password_hash,
        groups=payload["groups"],
        home_dir=payload["home_dir"],
        shell=payload["shell"],
    )

    # Record audit log with approval reference
    audit_log.record(
        operation="user_add",
        user_id=payload["requester_id"],
        target=payload["username"],
        status="success",
        details={
            "approval_id": approval_id,
            "approver_id": payload["approver_id"],
        },
    )

    return result
```

#### 3. Request Type Registry

```python
# Register Users & Groups operations with approval service
APPROVAL_REQUEST_TYPES = {
    "user_add": {
        "risk_level": "HIGH",
        "required_role": "Approver",
        "auto_expire_hours": 24,
        "callback": execute_user_add,
        "description": "Create new user account",
    },
    "user_delete": {
        "risk_level": "CRITICAL",
        "required_role": "Admin",  # Only Admin can approve deletion
        "auto_expire_hours": 12,
        "callback": execute_user_delete,
        "description": "Delete user account",
    },
    "user_passwd": {
        "risk_level": "HIGH",
        "required_role": "Approver",
        "auto_expire_hours": 4,  # Short expiry for password changes
        "callback": execute_user_passwd,
        "description": "Change user password",
    },
    "group_add": {
        "risk_level": "MEDIUM",
        "required_role": "Approver",
        "auto_expire_hours": 24,
        "callback": execute_group_add,
        "description": "Create new group",
    },
    "group_delete": {
        "risk_level": "HIGH",
        "required_role": "Admin",
        "auto_expire_hours": 12,
        "callback": execute_group_delete,
        "description": "Delete group",
    },
    "group_modify": {
        "risk_level": "HIGH",
        "required_role": "Approver",
        "auto_expire_hours": 24,
        "callback": execute_group_modify,
        "description": "Modify group membership",
    },
}
```

---

## Error Handling Strategy

### Error Classification

| Error Type | HTTP Status | Audit Status | User Message |
|-----------|-------------|-------------|--------------|
| Input validation error | 400 | attempt | "Invalid input: {field}" |
| Authentication error | 401 | denied | "Authentication required" |
| Authorization error | 403 | denied | "Permission denied" |
| Forbidden username/group | 403 | denied | "Username/group is reserved" |
| User already exists | 409 | denied | "User already exists" |
| Approval pending | 202 | pending | "Request submitted, awaiting approval" |
| Approval rejected | 403 | rejected | "Request was rejected by approver" |
| Wrapper execution failure | 500 | failure | "System error" |
| Timeout | 504 | failure | "Operation timed out" |

### Password Handling

```python
# CRITICAL: Password must never appear in:
# - Logs (application, audit, wrapper)
# - Error messages
# - API responses
# - Stack traces

# Password flow:
# 1. Client sends password over HTTPS
# 2. API hashes with bcrypt immediately
# 3. Plain password discarded from memory
# 4. Hash encrypted before storing in approval request
# 5. On approval, hash decrypted and passed to wrapper
# 6. Wrapper uses chpasswd -e (accepts pre-hashed)
```

---

## RBAC Design

### Permission Matrix

| Role | List Users | User Detail | Create User | Delete User | Change Password | Manage Groups |
|------|-----------|-------------|-------------|-------------|-----------------|---------------|
| Viewer | read-only | read-only | - | - | - | - |
| Operator | read-only | read-only | request | - | request (self) | - |
| Approver | read-only | full detail | request+approve | request | request+approve | request+approve |
| Admin | full access | full detail | request+approve | request+approve | request+approve | full access |

### New Permissions to Add to auth.py

```python
# Additions to ROLES in backend/core/auth.py
"read:users"    # View user/group lists and details
"write:users"   # Submit user/group modification requests
"approve:users" # Approve user/group modification requests
```

### Updated Role Definitions

```python
ROLES = {
    "Viewer": UserRole(
        name="Viewer",
        permissions=[
            "read:status", "read:logs", "read:processes",
            "read:users",  # NEW: view user lists
        ],
    ),
    "Operator": UserRole(
        name="Operator",
        permissions=[
            "read:status", "read:logs", "read:processes",
            "execute:service_restart",
            "read:users",   # NEW
            "write:users",  # NEW: submit requests
        ],
    ),
    "Approver": UserRole(
        name="Approver",
        permissions=[
            "read:status", "read:logs", "read:processes",
            "execute:service_restart",
            "approve:dangerous_operation",
            "read:users",    # NEW
            "write:users",   # NEW
            "approve:users", # NEW: approve requests
        ],
    ),
    "Admin": UserRole(
        name="Admin",
        permissions=[
            "read:status", "read:logs", "read:processes",
            "execute:service_restart",
            "approve:dangerous_operation",
            "manage:users", "manage:settings",
            "read:users",    # NEW
            "write:users",   # NEW
            "approve:users", # NEW
        ],
    ),
}
```

---

## Implementation Phases

### Phase 1: Read Operations (v0.3-alpha)

1. `adminui-user-list.sh` - List users (UID >= 1000)
2. `adminui-user-detail.sh` - User detail
3. `adminui-group-list.sh` - List groups (GID >= 1000)
4. `backend/api/routes/users.py` - GET endpoints only
5. `frontend/dev/users.html` + `frontend/js/users.js` - Read-only UI
6. Tests: 30+ test cases (input validation, RBAC, security)

### Phase 2: Write Operations (v0.3-beta)

1. `adminui-user-add.sh` - User creation
2. `adminui-user-delete.sh` - User deletion
3. `adminui-user-passwd.sh` - Password change
4. `adminui-group-add.sh` - Group creation
5. `adminui-group-delete.sh` - Group deletion
6. `adminui-group-modify.sh` - Group membership
7. POST/DELETE/PUT endpoints with approval integration
8. UI: Add/Delete/Modify modals with approval reason
9. Tests: 50+ additional test cases (approval flow, security, edge cases)

### Phase 3: Advanced Features (v0.3-rc)

1. Bulk operations (with multi-approval)
2. User account locking/unlocking
3. Password expiry management
4. Group hierarchy display
5. Import/export (CSV with approval)

---

## Review Checklist

### Security Review (mandatory before implementation)

- [ ] All write operations require approval workflow
- [ ] Username/group name validation: allowlist pattern + forbidden list
- [ ] UID/GID >= 1000 enforcement in both API and wrapper
- [ ] sudo/wheel/root group membership is impossible
- [ ] Password never appears in logs, audit, or API responses
- [ ] shell=True is never used (grep -r "shell=True" returns 0)
- [ ] All inputs validated against FORBIDDEN_CHARS
- [ ] Rate limiting on write operations (30 req/min)
- [ ] Audit log records all operations (attempt, success, denied, failure)
- [ ] Approval token is single-use and time-limited

### Architecture Review

- [ ] 3-layer architecture maintained: Wrapper -> sudo_wrapper -> API
- [ ] Consistent with existing patterns (processes, services, logs modules)
- [ ] Approval workflow integration follows approval-architect's design
- [ ] Error handling covers all failure modes
- [ ] RBAC permissions are properly defined and enforced

### Test Coverage Requirements

- [ ] Security tests: 30+ cases (injection, allowlist, forbidden patterns)
- [ ] Approval flow tests: 15+ cases (create, approve, reject, expire)
- [ ] RBAC tests: 10+ cases (each role, each permission)
- [ ] Wrapper tests: 100% pattern coverage (normal, error, security)
- [ ] Integration tests: End-to-end approval flow

---

## Consistency with Existing Modules

### File Layout (following processes module pattern)

```
backend/
  api/
    routes/
      users.py            # NEW: User & Group API endpoints
  core/
    sudo_wrapper.py       # MODIFIED: add user/group methods

wrappers/
  adminui-user-list.sh    # NEW
  adminui-user-detail.sh  # NEW
  adminui-user-add.sh     # NEW (Phase 2)
  adminui-user-delete.sh  # NEW (Phase 2)
  adminui-user-passwd.sh  # NEW (Phase 2)
  adminui-group-list.sh   # NEW
  adminui-group-add.sh    # NEW (Phase 2)
  adminui-group-delete.sh # NEW (Phase 2)
  adminui-group-modify.sh # NEW (Phase 2)
  spec/
    adminui-user-add.sh.spec    # NEW: Specification
    adminui-user-delete.sh.spec # NEW: Specification
    adminui-user-list.sh.spec   # NEW: Specification
    adminui-group-list.sh.spec  # NEW: Specification
  test/
    test-adminui-users.sh       # NEW: Wrapper tests

frontend/
  dev/
    users.html            # NEW: Users & Groups page
  js/
    users.js              # NEW: Users & Groups JavaScript

tests/
  test_users.py           # NEW: API tests
  test_users_security.py  # NEW: Security tests

docs/
  architecture/
    users-groups-design.md          # THIS FILE
  security/
    users-groups-threat-analysis.md # Threat analysis
    users-groups-allowlist-policy.md # Allowlist/denylist definitions
```

### API Convention Compliance

| Convention | Existing Pattern | Users Module |
|-----------|-----------------|--------------|
| Router prefix | `prefix="/processes"` | `prefix="/users"` |
| Permission | `require_permission("read:processes")` | `require_permission("read:users")` |
| Audit log | `audit_log.record(operation="process_list")` | `audit_log.record(operation="user_list")` |
| Wrapper call | `sudo_wrapper.get_processes()` | `sudo_wrapper.list_users()` |
| JSON output | `{"status": "success", ...}` | `{"status": "success", ...}` |
| Error output | `{"status": "error", "message": "..."}` | `{"status": "error", "message": "..."}` |
| Logger tag | `logger -t adminui-processes` | `logger -t adminui-users` |

### sudoers Configuration

**Service User**: `svc-adminui` (統一: 全モジュール共通)

```bash
# /etc/sudoers.d/adminui-users
# Users & Groups Management Module

# Read operations (sudo不要 - 念のため定義)
# svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-user-list.sh
# svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-user-detail.sh
# svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-group-list.sh

# Write operations (sudo必須)
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-user-add.sh
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-user-delete.sh
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-user-passwd.sh
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-group-add.sh
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-group-delete.sh
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-group-modify.sh

# セキュリティ注意事項:
# - ワイルドカード（adminui-user-*.sh）は使用しない（意図しないスクリプト実行を防止）
# - 各コマンドを明示的に列挙
# - NOPASSWD は最小権限の原則に従い、必要最小限のコマンドのみ許可
```

**統合確認**: cron-jobs-design.mdのsudoers設定と競合なし（異なるコマンド）

---

**Approval**: This design document requires team-lead approval before implementation phase begins.

**Change History**:
- 2026-02-14: Initial version (users-planner)
