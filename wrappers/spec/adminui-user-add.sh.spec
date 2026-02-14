# Wrapper Specification: adminui-user-add.sh
#
# Created: 2026-02-14
# Author: users-planner (v03-planning-team)
# Phase: v0.3 Phase 2 (Write Operations)
# Risk Level: HIGH
# Sudo Required: YES
# Approval Required: YES (Approver or Admin role)
#
# ===================================================================
# PURPOSE
# ===================================================================
#
# Create a new user account on the Linux system.
# This is a HIGH-RISK write operation that requires:
#   1. Prior approval from Approver/Admin role
#   2. sudo privilege for useradd execution
#   3. Multi-layer input validation
#
# ===================================================================
# INSTALLATION
# ===================================================================
#
# Location: /usr/local/sbin/adminui-user-add.sh
# Owner: root:root
# Permissions: 0755
# sudoers: adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-user-add.sh
#
# ===================================================================
# USAGE
# ===================================================================
#
# sudo /usr/local/sbin/adminui-user-add.sh \
#   --username=<name> \
#   --groups=<group1,group2,...> \
#   --shell=<path> \
#   [--home=<path>] \
#   [--gecos=<comment>]
#
# Password hash is read from STDIN (never as argument):
#   echo "$PASSWORD_HASH" | sudo adminui-user-add.sh --username=newuser ...
#
# ===================================================================
# INPUT VALIDATION
# ===================================================================
#
# Username:
#   Pattern: ^[a-z_][a-z0-9_-]{0,31}$
#   FORBIDDEN_USERNAMES check (100+ entries)
#   FORBIDDEN_CHARS check
#   Must NOT already exist (getent passwd)
#
# Groups:
#   Pattern per group: ^[a-z_][a-z0-9_-]{0,31}$
#   FORBIDDEN_GROUPS check (35+ entries, includes sudo/wheel/docker/root)
#   Max groups: 10
#   Each group must exist (getent group check) OR be "users" (default)
#
# Shell:
#   Allowlist: ("/bin/bash" "/bin/sh" "/usr/bin/zsh" "/usr/sbin/nologin" "/bin/false")
#   Exact match only
#
# Home:
#   Default: /home/<username>
#   Must start with /home/
#   No path traversal (..)
#   Must be exactly /home/<name> (no deeper nesting)
#   Must not already exist as directory
#
# GECOS:
#   Pattern: ^[a-zA-Z0-9 ._-]{0,100}$
#   Optional (default: empty)
#
# Password Hash (stdin):
#   Pattern: ^\$2[aby]\$[0-9]{2}\$.{53}$ (bcrypt format)
#   Must not be empty
#   Read from stdin only (never from arguments - prevents ps exposure)
#
# ===================================================================
# SECURITY CONTROLS
# ===================================================================
#
# 1.  set -euo pipefail (strict mode)
# 2.  FORBIDDEN_CHARS check on ALL text inputs
# 3.  FORBIDDEN_USERNAMES check (100+ system/service/admin names)
# 4.  FORBIDDEN_GROUPS check (35+ privilege/system/container groups)
# 5.  ALLOWED_SHELLS exact match (5 entries)
# 6.  Home directory path validation (/home/ only, no traversal)
# 7.  Password hash via stdin (not visible in ps output)
# 8.  useradd executed via array (no shell expansion)
# 9.  chpasswd -e for pre-hashed password
# 10. Logger tag: adminui-users
# 11. All arguments logged EXCEPT password hash
# 12. Caller identity logged via ${SUDO_USER:-$USER}
#
# ===================================================================
# EXECUTION FLOW
# ===================================================================
#
# 1. Parse arguments
# 2. Read password hash from stdin
# 3. Validate all inputs
# 4. Check user does not exist
# 5. Check all groups exist and are not forbidden
# 6. Execute: useradd -m -s <shell> -G <groups> [-c <gecos>] [-d <home>] <username>
# 7. Execute: echo "<username>:<hash>" | chpasswd -e
# 8. Verify user created (id <username>)
# 9. Output JSON result
# 10. Log success
#
# ===================================================================
# OUTPUT FORMAT (JSON)
# ===================================================================
#
# Success:
# {
#   "status": "success",
#   "message": "User created successfully",
#   "user": {
#     "username": "<string>",
#     "uid": <int>,
#     "gid": <int>,
#     "home": "<string>",
#     "shell": "<string>",
#     "groups": ["<string>", ...]
#   },
#   "timestamp": "<ISO8601>"
# }
#
# Error:
# {
#   "status": "error",
#   "message": "<error description>",
#   "timestamp": "<ISO8601>"
# }
#
# ===================================================================
# LINUX COMMANDS USED
# ===================================================================
#
# useradd -m -s <shell> -G <groups> [-c <gecos>] [-d <home>] <username>
#   -m          : Create home directory
#   -s <shell>  : Login shell
#   -G <groups> : Supplementary groups (comma-separated)
#   -c <gecos>  : Comment/GECOS field
#   -d <home>   : Home directory path
#
# chpasswd -e
#   -e : Accept encrypted (pre-hashed) password
#   Input format: username:hash (via stdin)
#
# id <username>
#   Verify user creation
#
# getent passwd <username>
#   Check if user exists before creation
#
# getent group <groupname>
#   Check if group exists before assignment
#
# ===================================================================
# ERROR CASES
# ===================================================================
#
# Username already exists:
#   Exit: 1, Output: {"status":"error","message":"User already exists: <name>"}
#
# Forbidden username:
#   Exit: 1, Output: {"status":"error","message":"Username is reserved: <name>"}
#   Log: "SECURITY: Forbidden username attempt - user=<name>, caller=<caller>"
#
# Forbidden group:
#   Exit: 1, Output: {"status":"error","message":"Group is forbidden: <group>"}
#   Log: "SECURITY: Forbidden group attempt - group=<group>, caller=<caller>"
#
# Group does not exist:
#   Exit: 1, Output: {"status":"error","message":"Group does not exist: <group>"}
#
# Shell not allowed:
#   Exit: 1, Output: {"status":"error","message":"Shell not allowed: <shell>"}
#
# Invalid home directory:
#   Exit: 1, Output: {"status":"error","message":"Invalid home directory: <path>"}
#
# Password hash format invalid:
#   Exit: 1, Output: {"status":"error","message":"Invalid password hash format"}
#
# useradd failure:
#   Exit: 1, Output: {"status":"error","message":"Failed to create user"}
#
# chpasswd failure:
#   Exit: 1, Output: {"status":"error","message":"Failed to set password"}
#
# ===================================================================
# LOGGING
# ===================================================================
#
# Pre-execution:
#   "User creation requested: username=<name>, groups=<groups>, shell=<shell>, home=<home>, caller=<caller>"
#
# Success:
#   "User created successfully: username=<name>, uid=<uid>, groups=<groups>, caller=<caller>"
#
# Error:
#   "ERROR: <description>"
#
# Security:
#   "SECURITY: Forbidden username attempt - user=<name>, caller=<caller>"
#   "SECURITY: Forbidden group attempt - group=<group>, user=<name>, caller=<caller>"
#   "SECURITY: Forbidden character detected - input=<field>, caller=<caller>"
#
# NOTE: Password hash is NEVER logged
#
# ===================================================================
# TEST CASES (Required)
# ===================================================================
#
# Normal:
#   1. Create user with all defaults (username + password only)
#   2. Create user with specific groups
#   3. Create user with specific shell (/usr/sbin/nologin)
#   4. Create user with GECOS comment
#   5. Create user with custom home directory (/home/custom-name)
#   6. Verify created user has correct UID (>= 1000)
#   7. Verify created user has correct groups
#   8. Verify created user has correct home directory
#   9. Verify created user can authenticate with given password hash
#
# Security (CRITICAL):
#   10. FORBIDDEN_USERNAMES: "root" -> rejected
#   11. FORBIDDEN_USERNAMES: "admin" -> rejected
#   12. FORBIDDEN_USERNAMES: "postgres" -> rejected
#   13. FORBIDDEN_USERNAMES: "docker" -> rejected
#   14. FORBIDDEN_GROUPS: "sudo" -> rejected
#   15. FORBIDDEN_GROUPS: "wheel" -> rejected
#   16. FORBIDDEN_GROUPS: "docker" -> rejected
#   17. FORBIDDEN_GROUPS: "root" -> rejected
#   18. FORBIDDEN_GROUPS: "shadow" -> rejected
#   19. FORBIDDEN_GROUPS: "lxd" -> rejected
#   20. Command injection in username: "user;id" -> rejected
#   21. Command injection in username: "user$(id)" -> rejected
#   22. Command injection in username: "user`id`" -> rejected
#   23. Command injection in group: "users;chmod" -> rejected
#   24. Shell not in allowlist: "/bin/csh" -> rejected
#   25. Shell with arguments: "/bin/bash -c cmd" -> rejected
#   26. Home directory traversal: "../../etc" -> rejected
#   27. Home directory outside /home: "/etc" -> rejected
#   28. Home directory outside /home: "/root" -> rejected
#   29. Invalid password hash format -> rejected
#   30. Empty password hash -> rejected
#   31. Verify password hash NOT visible in ps output
#   32. Verify password hash NOT in any log file
#
# Error:
#   33. Username already exists -> error
#   34. Group does not exist -> error
#   35. No stdin (missing password hash) -> error
#   36. Missing required arguments -> error
#   37. Unknown arguments -> error
